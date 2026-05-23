"""
Comparador CFP vs INIDEP: cuotas aprobadas vs. CBA/CMP recomendada científicamente.

Genera alertas cuando el CFP aprueba cuotas superiores a las recomendaciones del INIDEP,
evidenciando potenciales decisiones contra la sostenibilidad (Ley 24.922, Art. 9).
"""
import json
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

import pandas as pd
from loguru import logger

from src.acquisition.inidep_scraper import SEED_DATA


SCHEMA_INIDEP = """
CREATE TABLE IF NOT EXISTS inidep_evaluaciones (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    especie         TEXT NOT NULL,
    especie_code    TEXT NOT NULL,
    zona            TEXT,
    year            INTEGER NOT NULL,
    cba_recomendada_tn   REAL,
    cba_alternativa_tn   REAL,
    estado_stock    TEXT,
    numero_ito      TEXT,
    fuente_url      TEXT,
    notas           TEXT,
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS cfp_cuotas (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    especie         TEXT NOT NULL,
    especie_code    TEXT NOT NULL,
    zona            TEXT,
    year            INTEGER NOT NULL,
    cmp_aprobada_tn REAL,
    tipo_decision   TEXT,
    acta_referencia TEXT,
    resolucion_cfp  TEXT,
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS comparacion_cfp_inidep (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    especie                 TEXT NOT NULL,
    especie_code            TEXT NOT NULL,
    zona                    TEXT,
    year                    INTEGER NOT NULL,
    cba_inidep_tn           REAL,
    cmp_cfp_tn              REAL,
    diferencia_tn           REAL,
    ratio_sobreasignacion   REAL,
    nivel_alerta            TEXT,
    descripcion_alerta      TEXT,
    numero_ito              TEXT,
    acta_cfp                TEXT,
    created_at              TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_inidep_especie_year ON inidep_evaluaciones(especie_code, year);
CREATE INDEX IF NOT EXISTS idx_cfp_cuotas_especie_year ON cfp_cuotas(especie_code, year);
CREATE INDEX IF NOT EXISTS idx_comparacion_year ON comparacion_cfp_inidep(year);
"""

# ── Niveles de alerta ─────────────────────────────────────────────────────────
ALERTA_VERDE = "verde"       # cuota ≤ 100% CBA
ALERTA_AMARILLA = "amarillo"  # cuota 101–115% CBA
ALERTA_ROJA = "rojo"          # cuota 116–130% CBA
ALERTA_CRITICA = "critico"    # cuota > 130% CBA
ALERTA_SIN_DATOS = "sin_datos"


@dataclass
class AlertaComparacion:
    especie: str
    zona: str
    year: int
    cba_inidep_tn: Optional[float]
    cmp_cfp_tn: Optional[float]
    diferencia_tn: Optional[float]
    ratio: Optional[float]
    nivel: str
    descripcion: str
    numero_ito: Optional[str]
    acta_cfp: Optional[str]


class INIDEPComparator:
    """Motor de comparación CFP vs. INIDEP."""

    def __init__(self, db_path: Path | str = "data/processed/catalog.db"):
        self.db_path = Path(db_path)
        self._init_schema()
        self._seed_inidep_data()

    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._conn() as conn:
            conn.executescript(SCHEMA_INIDEP)
        logger.debug("Schema INIDEP inicializado")

    def _seed_inidep_data(self) -> None:
        """Carga datos semilla del INIDEP (ya verificados con fuentes oficiales)."""
        with self._conn() as conn:
            existing = conn.execute("SELECT COUNT(*) FROM inidep_evaluaciones").fetchone()[0]
            if existing > 0:
                return
            for rec in SEED_DATA:
                conn.execute(
                    """
                    INSERT INTO inidep_evaluaciones
                        (especie, especie_code, zona, year, cba_recomendada_tn,
                         cba_alternativa_tn, estado_stock, numero_ito, fuente_url, notas)
                    VALUES
                        (:especie, :especie_code, :zona, :year, :cba_recomendada_tn,
                         :cba_alternativa_tn, :estado_stock, :numero_ito, :fuente_url, :notas)
                    """,
                    {
                        "especie": rec["especie"],
                        "especie_code": rec["especie_code"],
                        "zona": rec.get("zona"),
                        "year": rec["year"],
                        "cba_recomendada_tn": rec.get("cba_recomendada_tn"),
                        "cba_alternativa_tn": rec.get("cba_alternativa_tn"),
                        "estado_stock": rec.get("estado_stock"),
                        "numero_ito": rec.get("numero_ito"),
                        "fuente_url": rec.get("fuente_url"),
                        "notas": rec.get("notas"),
                    },
                )
            conn.commit()
            logger.info(f"Seed INIDEP: {len(SEED_DATA)} registros cargados")

    # ── CRUD cuotas CFP ───────────────────────────────────────────────────────

    def upsert_cfp_cuota(
        self,
        especie: str,
        especie_code: str,
        year: int,
        cmp_aprobada_tn: float,
        zona: Optional[str] = None,
        acta_referencia: Optional[str] = None,
        resolucion_cfp: Optional[str] = None,
        tipo_decision: str = "CMP",
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO cfp_cuotas
                    (especie, especie_code, zona, year, cmp_aprobada_tn,
                     tipo_decision, acta_referencia, resolucion_cfp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (especie, especie_code, zona, year, cmp_aprobada_tn,
                 tipo_decision, acta_referencia, resolucion_cfp),
            )
            conn.commit()

    def upsert_inidep_evaluacion(self, rec: dict) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO inidep_evaluaciones
                    (especie, especie_code, zona, year, cba_recomendada_tn,
                     estado_stock, numero_ito, fuente_url, notas)
                VALUES (:especie, :especie_code, :zona, :year, :cba_recomendada_tn,
                        :estado_stock, :numero_ito, :fuente_url, :notas)
                """,
                rec,
            )
            conn.commit()

    # ── Comparación y alertas ─────────────────────────────────────────────────

    def compute_comparisons(self) -> list[AlertaComparacion]:
        """
        Cruza cuotas CFP con recomendaciones INIDEP por especie+zona+año
        y genera alertas según el ratio de sobreasignación.
        """
        alertas = []

        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT
                    i.especie, i.especie_code, COALESCE(i.zona, 'Nacional') as zona,
                    i.year, i.cba_recomendada_tn, i.numero_ito, i.estado_stock,
                    c.cmp_aprobada_tn, c.acta_referencia, c.resolucion_cfp
                FROM inidep_evaluaciones i
                LEFT JOIN cfp_cuotas c
                    ON i.especie_code = c.especie_code
                    AND i.year = c.year
                    AND (i.zona = c.zona OR c.zona IS NULL)
                ORDER BY i.year DESC, i.especie
                """
            ).fetchall()

        for row in rows:
            cba = row["cba_recomendada_tn"]
            cmp = row["cmp_aprobada_tn"]

            if cba is None:
                nivel = ALERTA_SIN_DATOS
                desc = "CBA del INIDEP no disponible para comparar"
                ratio = None
                diff = None
            elif cmp is None:
                nivel = ALERTA_SIN_DATOS
                desc = "Cuota CFP no registrada en el sistema (completar con scraping completo)"
                ratio = None
                diff = None
            else:
                ratio = cmp / cba
                diff = cmp - cba
                if ratio <= 1.0:
                    nivel = ALERTA_VERDE
                    desc = f"Cuota CFP ({cmp:,.0f} tn) dentro del límite recomendado por INIDEP ({cba:,.0f} tn)"
                elif ratio <= 1.15:
                    nivel = ALERTA_AMARILLA
                    desc = (
                        f"Cuota CFP ({cmp:,.0f} tn) supera en {(ratio-1)*100:.1f}% "
                        f"la CBA del INIDEP ({cba:,.0f} tn). Monitorear."
                    )
                elif ratio <= 1.30:
                    nivel = ALERTA_ROJA
                    desc = (
                        f"⚠️ Cuota CFP ({cmp:,.0f} tn) supera en {(ratio-1)*100:.1f}% "
                        f"la CBA del INIDEP ({cba:,.0f} tn). Sobreasignación significativa."
                    )
                else:
                    nivel = ALERTA_CRITICA
                    desc = (
                        f"🚨 Cuota CFP ({cmp:,.0f} tn) supera en {(ratio-1)*100:.1f}% "
                        f"la CBA del INIDEP ({cba:,.0f} tn). Riesgo crítico de sostenibilidad."
                    )

            alertas.append(AlertaComparacion(
                especie=row["especie"],
                zona=row["zona"],
                year=row["year"],
                cba_inidep_tn=cba,
                cmp_cfp_tn=cmp,
                diferencia_tn=diff,
                ratio=ratio,
                nivel=nivel,
                descripcion=desc,
                numero_ito=row["numero_ito"],
                acta_cfp=row["acta_referencia"],
            ))

        # Guardar en BD
        self._persist_comparisons(alertas)
        return alertas

    def _persist_comparisons(self, alertas: list[AlertaComparacion]) -> None:
        with self._conn() as conn:
            conn.execute("DELETE FROM comparacion_cfp_inidep")
            for a in alertas:
                conn.execute(
                    """
                    INSERT INTO comparacion_cfp_inidep
                        (especie, especie_code, zona, year, cba_inidep_tn, cmp_cfp_tn,
                         diferencia_tn, ratio_sobreasignacion, nivel_alerta,
                         descripcion_alerta, numero_ito, acta_cfp)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        a.especie, a.especie.lower().replace(" ", "_"),
                        a.zona, a.year, a.cba_inidep_tn, a.cmp_cfp_tn,
                        a.diferencia_tn, a.ratio, a.nivel, a.descripcion,
                        a.numero_ito, a.acta_cfp,
                    ),
                )
            conn.commit()

    # ── Queries de análisis ───────────────────────────────────────────────────

    def get_alertas_activas(self, nivel_minimo: str = ALERTA_AMARILLA) -> pd.DataFrame:
        niveles_orden = {ALERTA_VERDE: 0, ALERTA_AMARILLA: 1,
                         ALERTA_ROJA: 2, ALERTA_CRITICA: 3, ALERTA_SIN_DATOS: -1}
        nivel_num = niveles_orden.get(nivel_minimo, 1)

        with self._conn() as conn:
            df = pd.read_sql_query(
                """
                SELECT especie, zona, year, cba_inidep_tn, cmp_cfp_tn,
                       diferencia_tn, ratio_sobreasignacion, nivel_alerta,
                       descripcion_alerta, numero_ito
                FROM comparacion_cfp_inidep
                ORDER BY ratio_sobreasignacion DESC NULLS LAST
                """,
                conn,
            )
        return df

    def get_inidep_data(self) -> pd.DataFrame:
        with self._conn() as conn:
            return pd.read_sql_query(
                "SELECT * FROM inidep_evaluaciones ORDER BY year DESC, especie",
                conn,
            )

    def get_cfp_data(self) -> pd.DataFrame:
        with self._conn() as conn:
            return pd.read_sql_query(
                "SELECT * FROM cfp_cuotas ORDER BY year DESC, especie",
                conn,
            )

    def summary_report(self) -> dict:
        alertas = self.compute_comparisons()
        from collections import Counter
        conteo = Counter(a.nivel for a in alertas)
        criticas = [a for a in alertas if a.nivel == ALERTA_CRITICA]
        rojas = [a for a in alertas if a.nivel == ALERTA_ROJA]

        return {
            "total_comparaciones": len(alertas),
            "por_nivel": dict(conteo),
            "alertas_criticas": [asdict(a) for a in criticas],
            "alertas_rojas": [asdict(a) for a in rojas],
            "especies_monitoreadas": list({a.especie for a in alertas}),
            "años_cubiertos": sorted({a.year for a in alertas}),
        }
