"""
Motor de alertas configurables para el sistema CFP Audit.

Permite definir reglas por tipo (exceso de CBA, stock crítico, quórum mínimo,
reversión de decisiones) y evaluarlas contra los datos disponibles en la BD.
Las reglas y el historial se persisten en SQLite.
"""
import sqlite3
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
from loguru import logger


SCHEMA_ALERTAS = """
CREATE TABLE IF NOT EXISTS alertas_reglas (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre          TEXT NOT NULL,
    tipo            TEXT NOT NULL,
    especie_code    TEXT,
    zona            TEXT,
    year_desde      INTEGER,
    year_hasta      INTEGER,
    umbral_pct      REAL,
    umbral_estado   TEXT,
    severidad       TEXT NOT NULL DEFAULT 'warning',
    activa          INTEGER NOT NULL DEFAULT 1,
    descripcion     TEXT,
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS alertas_historial (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    regla_id        INTEGER REFERENCES alertas_reglas(id),
    tipo            TEXT NOT NULL,
    especie         TEXT,
    especie_code    TEXT,
    zona            TEXT,
    year            INTEGER,
    valor_detectado REAL,
    umbral          REAL,
    mensaje         TEXT NOT NULL,
    severidad       TEXT NOT NULL,
    acta_referencia TEXT,
    resuelta        INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_alertas_reglas_activa ON alertas_reglas(activa, tipo);
CREATE INDEX IF NOT EXISTS idx_alertas_hist_especie ON alertas_historial(especie_code, year);
CREATE INDEX IF NOT EXISTS idx_alertas_hist_severidad ON alertas_historial(severidad, resuelta);
"""

# Tipos de regla
TIPO_CBA_EXCESO = "cba_exceso"
TIPO_STOCK_CRITICO = "stock_critico"
TIPO_QUORUM_MINIMO = "quorum_minimo"
TIPO_REVERSION = "reversion"
TIPOS_VALIDOS = {TIPO_CBA_EXCESO, TIPO_STOCK_CRITICO, TIPO_QUORUM_MINIMO, TIPO_REVERSION}

# Severidades
SEV_INFO = "info"
SEV_WARNING = "warning"
SEV_CRITICAL = "critical"
SEVERIDADES = [SEV_INFO, SEV_WARNING, SEV_CRITICAL]

SEVERITY_COLORS = {
    SEV_INFO: "#2196F3",
    SEV_WARNING: "#FF9800",
    SEV_CRITICAL: "#F44336",
}
SEVERITY_ICONS = {
    SEV_INFO: "ℹ️",
    SEV_WARNING: "⚠️",
    SEV_CRITICAL: "🔴",
}

# Reglas por defecto instaladas en la primera ejecución
DEFAULT_RULES = [
    {
        "nombre": "Exceso CBA ≥ 115% (alerta moderada)",
        "tipo": TIPO_CBA_EXCESO,
        "especie_code": None,
        "zona": None,
        "year_desde": 2000,
        "year_hasta": 2030,
        "umbral_pct": 115.0,
        "umbral_estado": None,
        "severidad": SEV_WARNING,
        "descripcion": "Cuota CFP supera el 115% de la CBA recomendada por INIDEP",
    },
    {
        "nombre": "Exceso CBA ≥ 130% (alerta crítica)",
        "tipo": TIPO_CBA_EXCESO,
        "especie_code": None,
        "zona": None,
        "year_desde": 2000,
        "year_hasta": 2030,
        "umbral_pct": 130.0,
        "umbral_estado": None,
        "severidad": SEV_CRITICAL,
        "descripcion": "Cuota CFP supera el 130% de la CBA — violación grave del Art. 9 Ley 24.922",
    },
    {
        "nombre": "Stock sobrexplotado con cuota asignada",
        "tipo": TIPO_STOCK_CRITICO,
        "especie_code": None,
        "zona": None,
        "year_desde": 2000,
        "year_hasta": 2030,
        "umbral_pct": None,
        "umbral_estado": "sobrexplotado",
        "severidad": SEV_CRITICAL,
        "descripcion": "INIDEP reporta stock sobrexplotado pero CFP asignó cuota de captura",
    },
    {
        "nombre": "Stock en recuperación — monitoreo",
        "tipo": TIPO_STOCK_CRITICO,
        "especie_code": None,
        "zona": None,
        "year_desde": 2000,
        "year_hasta": 2030,
        "umbral_pct": None,
        "umbral_estado": "en_recuperacion",
        "severidad": SEV_WARNING,
        "descripcion": "Stock en recuperación: cuota debe mantenerse conservadora",
    },
]


@dataclass
class AlertaRegla:
    nombre: str
    tipo: str
    severidad: str = SEV_WARNING
    especie_code: Optional[str] = None
    zona: Optional[str] = None
    year_desde: Optional[int] = None
    year_hasta: Optional[int] = None
    umbral_pct: Optional[float] = None
    umbral_estado: Optional[str] = None
    descripcion: Optional[str] = None
    activa: bool = True
    id: Optional[int] = None

    def aplica_a(self, especie_code: str, zona: Optional[str], year: int) -> bool:
        """Comprueba si esta regla aplica a un conjunto especie/zona/año."""
        if self.especie_code and self.especie_code != especie_code:
            return False
        if self.zona and self.zona != zona:
            return False
        if self.year_desde and year < self.year_desde:
            return False
        if self.year_hasta and year > self.year_hasta:
            return False
        return True


@dataclass
class AlertaFired:
    regla_id: Optional[int]
    tipo: str
    mensaje: str
    severidad: str
    especie: Optional[str] = None
    especie_code: Optional[str] = None
    zona: Optional[str] = None
    year: Optional[int] = None
    valor_detectado: Optional[float] = None
    umbral: Optional[float] = None
    acta_referencia: Optional[str] = None
    resuelta: bool = False
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    id: Optional[int] = None


class AlertEngine:
    """Motor de alertas configurables para el sistema CFP Audit."""

    def __init__(self, db_path: Path | str = "data/processed/catalog.db"):
        self.db_path = Path(db_path)
        self._init_schema()
        self._seed_default_rules()

    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._conn() as conn:
            conn.executescript(SCHEMA_ALERTAS)
            conn.commit()

    def _seed_default_rules(self) -> None:
        """Instala las reglas por defecto si la tabla está vacía."""
        with self._conn() as conn:
            count = conn.execute("SELECT COUNT(*) FROM alertas_reglas").fetchone()[0]
            if count > 0:
                return
        for rule in DEFAULT_RULES:
            self.upsert_regla(AlertaRegla(**rule))
        logger.info(f"Reglas de alerta por defecto instaladas ({len(DEFAULT_RULES)})")

    # ── CRUD de reglas ─────────────────────────────────────────────────────────

    def upsert_regla(self, regla: AlertaRegla) -> int:
        """Inserta o actualiza una regla de alerta. Retorna el ID."""
        with self._conn() as conn:
            if regla.id:
                conn.execute(
                    """UPDATE alertas_reglas SET
                       nombre=:nombre, tipo=:tipo, especie_code=:especie_code,
                       zona=:zona, year_desde=:year_desde, year_hasta=:year_hasta,
                       umbral_pct=:umbral_pct, umbral_estado=:umbral_estado,
                       severidad=:severidad, activa=:activa, descripcion=:descripcion
                       WHERE id=:id""",
                    {**asdict(regla), "activa": int(regla.activa)},
                )
                conn.commit()
                return regla.id
            else:
                cur = conn.execute(
                    """INSERT INTO alertas_reglas
                       (nombre, tipo, especie_code, zona, year_desde, year_hasta,
                        umbral_pct, umbral_estado, severidad, activa, descripcion)
                       VALUES (:nombre, :tipo, :especie_code, :zona, :year_desde,
                               :year_hasta, :umbral_pct, :umbral_estado,
                               :severidad, :activa, :descripcion)""",
                    {**asdict(regla), "activa": int(regla.activa)},
                )
                conn.commit()
                return cur.lastrowid

    def get_reglas(self, solo_activas: bool = False) -> list[AlertaRegla]:
        """Retorna todas las reglas (o solo las activas)."""
        with self._conn() as conn:
            q = "SELECT * FROM alertas_reglas"
            if solo_activas:
                q += " WHERE activa = 1"
            q += " ORDER BY severidad DESC, tipo, nombre"
            rows = conn.execute(q).fetchall()
        return [
            AlertaRegla(
                id=r["id"],
                nombre=r["nombre"],
                tipo=r["tipo"],
                especie_code=r["especie_code"],
                zona=r["zona"],
                year_desde=r["year_desde"],
                year_hasta=r["year_hasta"],
                umbral_pct=r["umbral_pct"],
                umbral_estado=r["umbral_estado"],
                severidad=r["severidad"],
                activa=bool(r["activa"]),
                descripcion=r["descripcion"],
            )
            for r in rows
        ]

    def toggle_regla(self, regla_id: int, activa: bool) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE alertas_reglas SET activa=? WHERE id=?",
                (int(activa), regla_id),
            )
            conn.commit()

    def delete_regla(self, regla_id: int) -> None:
        with self._conn() as conn:
            conn.execute("DELETE FROM alertas_reglas WHERE id=?", (regla_id,))
            conn.commit()

    # ── Evaluación ─────────────────────────────────────────────────────────────

    def evaluate(self, clear_previous: bool = False) -> list[AlertaFired]:
        """Evalúa todas las reglas activas y persiste las alertas generadas."""
        reglas = self.get_reglas(solo_activas=True)
        if not reglas:
            logger.warning("No hay reglas de alerta activas")
            return []

        if clear_previous:
            with self._conn() as conn:
                conn.execute("DELETE FROM alertas_historial WHERE resuelta = 0")
                conn.commit()

        alertas: list[AlertaFired] = []

        reglas_cba = [r for r in reglas if r.tipo == TIPO_CBA_EXCESO]
        reglas_stock = [r for r in reglas if r.tipo == TIPO_STOCK_CRITICO]
        reglas_quorum = [r for r in reglas if r.tipo == TIPO_QUORUM_MINIMO]
        reglas_rev = [r for r in reglas if r.tipo == TIPO_REVERSION]

        if reglas_cba:
            alertas.extend(self._eval_cba_exceso(reglas_cba))
        if reglas_stock:
            alertas.extend(self._eval_stock_critico(reglas_stock))
        if reglas_quorum:
            alertas.extend(self._eval_quorum_minimo(reglas_quorum))
        if reglas_rev:
            alertas.extend(self._eval_reversiones(reglas_rev))

        self._persist_alerts(alertas)
        logger.info(f"Evaluación completada: {len(alertas)} alertas generadas")
        return alertas

    def _eval_cba_exceso(self, reglas: list[AlertaRegla]) -> list[AlertaFired]:
        """Evalúa excesos de cuota vs CBA por porcentaje umbral."""
        fired = []
        try:
            with self._conn() as conn:
                rows = conn.execute(
                    """SELECT especie, especie_code, zona, year,
                              cba_inidep_tn, cmp_cfp_tn, ratio_sobreasignacion,
                              acta_cfp, numero_ito
                       FROM comparacion_cfp_inidep
                       WHERE cba_inidep_tn IS NOT NULL AND cmp_cfp_tn IS NOT NULL
                       ORDER BY year, especie_code"""
                ).fetchall()
        except sqlite3.OperationalError:
            return fired

        for row in rows:
            ratio = row["ratio_sobreasignacion"] or 0.0
            pct = ratio * 100

            for regla in reglas:
                if not regla.aplica_a(row["especie_code"], row["zona"], row["year"]):
                    continue
                if regla.umbral_pct and pct >= regla.umbral_pct:
                    fired.append(AlertaFired(
                        regla_id=regla.id,
                        tipo=TIPO_CBA_EXCESO,
                        especie=row["especie"],
                        especie_code=row["especie_code"],
                        zona=row["zona"],
                        year=row["year"],
                        valor_detectado=round(pct, 1),
                        umbral=regla.umbral_pct,
                        mensaje=(
                            f"{row['especie']} {row['year']}"
                            + (f" ({row['zona']})" if row["zona"] else "")
                            + f": CMP aprobada = {row['cmp_cfp_tn']:,.0f} tn "
                            + f"({pct:.1f}% de CBA {row['cba_inidep_tn']:,.0f} tn)"
                        ),
                        severidad=regla.severidad,
                        acta_referencia=row["acta_cfp"],
                    ))

        return fired

    def _eval_stock_critico(self, reglas: list[AlertaRegla]) -> list[AlertaFired]:
        """Evalúa alertas de estado de stock (sobrexplotado, en recuperación)."""
        fired = []
        try:
            with self._conn() as conn:
                rows = conn.execute(
                    """SELECT ie.especie, ie.especie_code, ie.zona, ie.year,
                              ie.estado_stock, ie.cba_recomendada_tn, ie.numero_ito,
                              cc.cmp_aprobada_tn
                       FROM inidep_evaluaciones ie
                       LEFT JOIN cfp_cuotas cc
                         ON ie.especie_code = cc.especie_code
                         AND ie.year = cc.year
                         AND (ie.zona = cc.zona OR ie.zona IS NULL)
                       WHERE ie.estado_stock IS NOT NULL"""
                ).fetchall()
        except sqlite3.OperationalError:
            return fired

        for row in rows:
            for regla in reglas:
                if not regla.aplica_a(row["especie_code"], row["zona"], row["year"]):
                    continue
                if regla.umbral_estado and row["estado_stock"] == regla.umbral_estado:
                    tiene_cuota = row["cmp_aprobada_tn"] is not None
                    fired.append(AlertaFired(
                        regla_id=regla.id,
                        tipo=TIPO_STOCK_CRITICO,
                        especie=row["especie"],
                        especie_code=row["especie_code"],
                        zona=row["zona"],
                        year=row["year"],
                        valor_detectado=row["cmp_aprobada_tn"],
                        umbral=None,
                        mensaje=(
                            f"{row['especie']} {row['year']}: estado stock = "
                            f"'{row['estado_stock']}'"
                            + (f" — CFP asignó {row['cmp_aprobada_tn']:,.0f} tn" if tiene_cuota else "")
                            + (f" (ITO: {row['numero_ito']})" if row["numero_ito"] else "")
                        ),
                        severidad=regla.severidad,
                    ))

        return fired

    def _eval_quorum_minimo(self, reglas: list[AlertaRegla]) -> list[AlertaFired]:
        """Evalúa decisiones aprobadas con quórum mínimo (votos a favor = mayoría justa)."""
        fired = []
        try:
            with self._conn() as conn:
                rows = conn.execute(
                    """SELECT r.id, r.acta_id, r.numero, r.categoria,
                              r.votos_favor, r.votos_contra, r.quorum,
                              a.year, a.nombre as nombre_acta
                       FROM resoluciones r
                       JOIN actas a ON r.acta_id = a.id
                       WHERE r.votos_favor IS NOT NULL
                         AND r.votos_contra IS NOT NULL
                         AND r.categoria = 'cuota_captura'"""
                ).fetchall()
        except sqlite3.OperationalError:
            return fired

        for row in rows:
            total = (row["votos_favor"] or 0) + (row["votos_contra"] or 0)
            if total < 2:
                continue
            margen = (row["votos_favor"] or 0) - (row["votos_contra"] or 0)
            if margen == 1:
                for regla in reglas:
                    if not regla.aplica_a("", None, row["year"]):
                        continue
                    fired.append(AlertaFired(
                        regla_id=regla.id,
                        tipo=TIPO_QUORUM_MINIMO,
                        year=row["year"],
                        valor_detectado=float(row["votos_favor"]),
                        umbral=None,
                        mensaje=(
                            f"Resolución CFP {row['numero']}/{row['year']} aprobada "
                            f"por quórum mínimo ({row['votos_favor']}-{row['votos_contra']}) "
                            f"en acta {row['nombre_acta']}"
                        ),
                        severidad=regla.severidad,
                        acta_referencia=row["nombre_acta"],
                    ))

        return fired

    def _eval_reversiones(self, reglas: list[AlertaRegla]) -> list[AlertaFired]:
        """Detecta reversiones de decisiones previas sobre la misma especie."""
        fired = []
        try:
            with self._conn() as conn:
                rows = conn.execute(
                    """SELECT r.texto_resumen, r.categoria, a.year, a.nombre
                       FROM resoluciones r
                       JOIN actas a ON r.acta_id = a.id
                       WHERE lower(r.texto_resumen) LIKE '%deja sin efecto%'
                          OR lower(r.texto_resumen) LIKE '%modifica la resolución%'
                          OR lower(r.texto_resumen) LIKE '%deroga%'"""
                ).fetchall()
        except sqlite3.OperationalError:
            return fired

        for row in rows:
            for regla in reglas:
                if not regla.aplica_a("", None, row["year"]):
                    continue
                fired.append(AlertaFired(
                    regla_id=regla.id,
                    tipo=TIPO_REVERSION,
                    year=row["year"],
                    mensaje=(
                        f"Posible reversión de decisión detectada en acta {row['nombre']} "
                        f"({row['year']}): {(row['texto_resumen'] or '')[:120]}..."
                    ),
                    severidad=regla.severidad,
                    acta_referencia=row["nombre"],
                ))

        return fired

    def _persist_alerts(self, alertas: list[AlertaFired]) -> None:
        with self._conn() as conn:
            for a in alertas:
                conn.execute(
                    """INSERT INTO alertas_historial
                       (regla_id, tipo, especie, especie_code, zona, year,
                        valor_detectado, umbral, mensaje, severidad,
                        acta_referencia, resuelta)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        a.regla_id, a.tipo, a.especie, a.especie_code,
                        a.zona, a.year, a.valor_detectado, a.umbral,
                        a.mensaje, a.severidad, a.acta_referencia,
                        int(a.resuelta),
                    ),
                )
            conn.commit()

    # ── Consulta del historial ─────────────────────────────────────────────────

    def get_historial(
        self,
        severidad_min: Optional[str] = None,
        solo_abiertas: bool = True,
        especie_code: Optional[str] = None,
        year_desde: Optional[int] = None,
        year_hasta: Optional[int] = None,
        limit: int = 500,
    ) -> pd.DataFrame:
        """Retorna el historial de alertas como DataFrame."""
        filters = []
        params: list = []

        if solo_abiertas:
            filters.append("h.resuelta = 0")
        if especie_code:
            filters.append("h.especie_code = ?")
            params.append(especie_code)
        if year_desde:
            filters.append("h.year >= ?")
            params.append(year_desde)
        if year_hasta:
            filters.append("h.year <= ?")
            params.append(year_hasta)

        sev_order = {"critical": 0, "warning": 1, "info": 2}
        if severidad_min:
            allowed = [s for s in SEVERIDADES if sev_order[s] <= sev_order.get(severidad_min, 2)]
            placeholders = ",".join("?" * len(allowed))
            filters.append(f"h.severidad IN ({placeholders})")
            params.extend(allowed)

        where = ("WHERE " + " AND ".join(filters)) if filters else ""

        query = f"""
            SELECT h.id, h.tipo, h.especie, h.especie_code, h.zona, h.year,
                   h.valor_detectado, h.umbral, h.mensaje,
                   h.severidad, h.acta_referencia, h.resuelta,
                   h.created_at, r.nombre as regla_nombre
            FROM alertas_historial h
            LEFT JOIN alertas_reglas r ON h.regla_id = r.id
            {where}
            ORDER BY
              CASE h.severidad WHEN 'critical' THEN 0 WHEN 'warning' THEN 1 ELSE 2 END,
              h.year DESC
            LIMIT ?
        """
        params.append(limit)

        try:
            with self._conn() as conn:
                return pd.read_sql_query(query, conn, params=params)
        except sqlite3.OperationalError:
            return pd.DataFrame()

    def resolve_alerta(self, alerta_id: int) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE alertas_historial SET resuelta = 1 WHERE id = ?",
                (alerta_id,),
            )
            conn.commit()

    def get_summary(self) -> dict:
        """Retorna estadísticas resumidas del estado de alertas."""
        try:
            with self._conn() as conn:
                total = conn.execute(
                    "SELECT COUNT(*) FROM alertas_historial WHERE resuelta = 0"
                ).fetchone()[0]
                criticas = conn.execute(
                    "SELECT COUNT(*) FROM alertas_historial WHERE severidad='critical' AND resuelta=0"
                ).fetchone()[0]
                warnings = conn.execute(
                    "SELECT COUNT(*) FROM alertas_historial WHERE severidad='warning' AND resuelta=0"
                ).fetchone()[0]
                n_reglas = conn.execute(
                    "SELECT COUNT(*) FROM alertas_reglas WHERE activa=1"
                ).fetchone()[0]
                ultima = conn.execute(
                    "SELECT created_at FROM alertas_historial ORDER BY created_at DESC LIMIT 1"
                ).fetchone()
        except sqlite3.OperationalError:
            return {"total": 0, "criticas": 0, "warnings": 0, "n_reglas": 0, "ultima_evaluacion": None}

        return {
            "total": total,
            "criticas": criticas,
            "warnings": warnings,
            "info": total - criticas - warnings,
            "n_reglas": n_reglas,
            "ultima_evaluacion": ultima[0] if ultima else None,
        }
