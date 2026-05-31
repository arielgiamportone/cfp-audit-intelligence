"""
Comparador CFP vs INIDEP: cuotas aprobadas vs. CBA/CMP recomendada científicamente.

Genera alertas cuando el CFP aprueba cuotas superiores a las recomendaciones del INIDEP,
evidenciando potenciales decisiones contra la sostenibilidad (Ley 24.922, Art. 9).

v0.5: incluye capturas reales SAGPyA para completar el Triángulo de Auditoría
      CBA (INIDEP) → CMP (CFP) → Captura real (SIPA/SAGPyA).
"""

import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd
from loguru import logger

from src.acquisition.inidep_scraper import SEED_DATA
from src.acquisition.sipa_scraper import SEED_DATA_CAPTURAS, _clasificar_alerta_captura

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

CREATE TABLE IF NOT EXISTS capturas_reales (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    especie         TEXT NOT NULL,
    especie_code    TEXT NOT NULL,
    year            INTEGER NOT NULL,
    captura_tn      REAL NOT NULL,
    fuente          TEXT DEFAULT 'SAGPyA',
    notas           TEXT,
    created_at      TEXT DEFAULT (datetime('now')),
    UNIQUE(especie_code, year)
);

CREATE TABLE IF NOT EXISTS comparacion_cfp_inidep (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    especie                 TEXT NOT NULL,
    especie_code            TEXT NOT NULL,
    zona                    TEXT,
    year                    INTEGER NOT NULL,
    cba_inidep_tn           REAL,
    cmp_cfp_tn              REAL,
    captura_real_tn         REAL,
    diferencia_tn           REAL,
    ratio_sobreasignacion   REAL,
    nivel_alerta            TEXT,
    descripcion_alerta      TEXT,
    alerta_captura          TEXT,
    numero_ito              TEXT,
    acta_cfp                TEXT,
    created_at              TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_inidep_especie_year ON inidep_evaluaciones(especie_code, year);
CREATE INDEX IF NOT EXISTS idx_cfp_cuotas_especie_year ON cfp_cuotas(especie_code, year);
CREATE INDEX IF NOT EXISTS idx_capturas_especie_year ON capturas_reales(especie_code, year);
CREATE INDEX IF NOT EXISTS idx_comparacion_year ON comparacion_cfp_inidep(year);
"""

# ── Niveles de alerta CMP vs CBA ──────────────────────────────────────────────
ALERTA_VERDE = "verde"
ALERTA_AMARILLA = "amarillo"
ALERTA_ROJA = "rojo"
ALERTA_CRITICA = "critico"
ALERTA_SIN_DATOS = "sin_datos"


@dataclass
class AlertaComparacion:
    especie: str
    zona: str
    year: int
    cba_inidep_tn: float | None
    cmp_cfp_tn: float | None
    diferencia_tn: float | None
    ratio: float | None
    nivel: str
    descripcion: str
    numero_ito: str | None
    acta_cfp: str | None
    # Tercer vértice del triángulo: captura real SAGPyA
    captura_real_tn: float | None = None
    alerta_captura: str | None = None


class INIDEPComparator:
    """Motor de comparación CFP vs. INIDEP con triángulo de auditoría completo."""

    def __init__(self, db_path: Path | str = "data/processed/catalog.db"):
        self.db_path = Path(db_path)
        self._init_schema()
        self._migrate_schema()
        self._seed_inidep_data()
        self._seed_capturas_data()

    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._conn() as conn:
            conn.executescript(SCHEMA_INIDEP)
        logger.debug("Schema INIDEP inicializado")

    def _migrate_schema(self) -> None:
        """Agrega columnas nuevas a tablas existentes si no existen (idempotente)."""
        migrations = [
            "ALTER TABLE comparacion_cfp_inidep ADD COLUMN captura_real_tn REAL",
            "ALTER TABLE comparacion_cfp_inidep ADD COLUMN alerta_captura TEXT",
        ]
        with self._conn() as conn:
            for sql in migrations:
                try:
                    conn.execute(sql)
                except sqlite3.OperationalError:
                    pass  # columna ya existe
            conn.commit()

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

    def _seed_capturas_data(self) -> None:
        """Carga datos semilla SAGPyA (capturas reales verificadas)."""
        with self._conn() as conn:
            existing = conn.execute("SELECT COUNT(*) FROM capturas_reales").fetchone()[0]
            if existing > 0:
                return
            inserted = 0
            for rec in SEED_DATA_CAPTURAS:
                try:
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO capturas_reales
                            (especie, especie_code, year, captura_tn, fuente, notas)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            rec["especie"],
                            rec["especie_code"],
                            rec["year"],
                            rec["captura_tn"],
                            rec.get("fuente", "SAGPyA"),
                            rec.get("notas"),
                        ),
                    )
                    inserted += 1
                except sqlite3.IntegrityError:
                    pass
            conn.commit()
            logger.info(f"Seed capturas_reales: {inserted} registros cargados")

    # ── CRUD cuotas CFP ───────────────────────────────────────────────────────

    def upsert_cfp_cuota(
        self,
        especie: str,
        especie_code: str,
        year: int,
        cmp_aprobada_tn: float,
        zona: str | None = None,
        acta_referencia: str | None = None,
        resolucion_cfp: str | None = None,
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
                (
                    especie,
                    especie_code,
                    zona,
                    year,
                    cmp_aprobada_tn,
                    tipo_decision,
                    acta_referencia,
                    resolucion_cfp,
                ),
            )
            conn.commit()

    def upsert_inidep_evaluacion(self, rec: dict) -> None:
        """Inserta una evaluación INIDEP. Ignora duplicados (mismo especie_code+zona+year+ito)."""
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO inidep_evaluaciones
                    (especie, especie_code, zona, year, cba_recomendada_tn,
                     cba_alternativa_tn, estado_stock, numero_ito, fuente_url, notas)
                VALUES (:especie, :especie_code, :zona, :year, :cba_recomendada_tn,
                        :cba_alternativa_tn, :estado_stock, :numero_ito, :fuente_url, :notas)
                """,
                {
                    "especie": rec.get("especie"),
                    "especie_code": rec.get("especie_code"),
                    "zona": rec.get("zona"),
                    "year": rec.get("year"),
                    "cba_recomendada_tn": rec.get("cba_recomendada_tn"),
                    "cba_alternativa_tn": rec.get("cba_alternativa_tn"),
                    "estado_stock": rec.get("estado_stock"),
                    "numero_ito": rec.get("numero_ito"),
                    "fuente_url": rec.get("fuente_url"),
                    "notas": rec.get("notas"),
                },
            )
            conn.commit()

    # ── Comparación y alertas ─────────────────────────────────────────────────

    def compute_comparisons(self) -> list[AlertaComparacion]:
        """
        Cruza cuotas CFP con recomendaciones INIDEP y capturas reales SAGPyA
        por especie+zona+año y genera alertas de sobreasignación y captura.
        """
        alertas = []

        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT
                    i.especie, i.especie_code, COALESCE(i.zona, 'Nacional') as zona,
                    i.year, i.cba_recomendada_tn, i.numero_ito, i.estado_stock,
                    c.cmp_aprobada_tn, c.acta_referencia, c.resolucion_cfp,
                    cr.captura_tn AS captura_real_tn
                FROM inidep_evaluaciones i
                LEFT JOIN cfp_cuotas c
                    ON i.especie_code = c.especie_code
                    AND i.year = c.year
                    AND (i.zona = c.zona OR c.zona IS NULL)
                LEFT JOIN capturas_reales cr
                    ON i.especie_code = cr.especie_code
                    AND i.year = cr.year
                ORDER BY i.year DESC, i.especie
                """
            ).fetchall()

        for row in rows:
            cba = row["cba_recomendada_tn"]
            cmp = row["cmp_aprobada_tn"]
            captura_real = row["captura_real_tn"]

            # Alerta CMP vs CBA
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
                        f"Cuota CFP ({cmp:,.0f} tn) supera en {(ratio - 1) * 100:.1f}% "
                        f"la CBA del INIDEP ({cba:,.0f} tn). Monitorear."
                    )
                elif ratio <= 1.30:
                    nivel = ALERTA_ROJA
                    desc = (
                        f"⚠️ Cuota CFP ({cmp:,.0f} tn) supera en {(ratio - 1) * 100:.1f}% "
                        f"la CBA del INIDEP ({cba:,.0f} tn). Sobreasignación significativa."
                    )
                else:
                    nivel = ALERTA_CRITICA
                    desc = (
                        f"🚨 Cuota CFP ({cmp:,.0f} tn) supera en {(ratio - 1) * 100:.1f}% "
                        f"la CBA del INIDEP ({cba:,.0f} tn). Riesgo crítico de sostenibilidad."
                    )

            # Alerta captura real vs CBA (tercer vértice del triángulo)
            ratio_captura_cba = (captura_real / cba) if (captura_real and cba) else None
            ratio_captura_cmp = (captura_real / cmp) if (captura_real and cmp) else None
            alerta_captura = _clasificar_alerta_captura(ratio_captura_cba, ratio_captura_cmp)

            alertas.append(
                AlertaComparacion(
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
                    captura_real_tn=captura_real,
                    alerta_captura=alerta_captura,
                )
            )

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
                         captura_real_tn, diferencia_tn, ratio_sobreasignacion, nivel_alerta,
                         descripcion_alerta, alerta_captura, numero_ito, acta_cfp)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        a.especie,
                        a.especie.lower().replace(" ", "_"),
                        a.zona,
                        a.year,
                        a.cba_inidep_tn,
                        a.cmp_cfp_tn,
                        a.captura_real_tn,
                        a.diferencia_tn,
                        a.ratio,
                        a.nivel,
                        a.descripcion,
                        a.alerta_captura,
                        a.numero_ito,
                        a.acta_cfp,
                    ),
                )
            conn.commit()

    # ── Queries de análisis ───────────────────────────────────────────────────

    def get_alertas_activas(self, nivel_minimo: str = ALERTA_AMARILLA) -> pd.DataFrame:
        niveles_orden = {
            ALERTA_VERDE: 0,
            ALERTA_AMARILLA: 1,
            ALERTA_ROJA: 2,
            ALERTA_CRITICA: 3,
            ALERTA_SIN_DATOS: -1,
        }
        umbral = niveles_orden.get(nivel_minimo, 1)
        niveles_incluidos = [k for k, v in niveles_orden.items() if v >= umbral]

        with self._conn() as conn:
            placeholders = ",".join("?" * len(niveles_incluidos))
            df = pd.read_sql_query(
                f"""
                SELECT especie, zona, year, cba_inidep_tn, cmp_cfp_tn, captura_real_tn,
                       diferencia_tn, ratio_sobreasignacion, nivel_alerta,
                       descripcion_alerta, alerta_captura, numero_ito
                FROM comparacion_cfp_inidep
                WHERE nivel_alerta IN ({placeholders})
                ORDER BY ratio_sobreasignacion DESC NULLS LAST
                """,
                conn,
                params=niveles_incluidos,
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

    def get_capturas_data(self) -> pd.DataFrame:
        """Retorna DataFrame de capturas reales SAGPyA."""
        with self._conn() as conn:
            return pd.read_sql_query(
                "SELECT * FROM capturas_reales ORDER BY year DESC, especie",
                conn,
            )

    def get_triangulo_completo(self, especie_code: str | None = None) -> pd.DataFrame:
        """
        Retorna DataFrame con los tres vértices del triángulo de auditoría:
        CBA (INIDEP), CMP (CFP) y captura real (SAGPyA).
        """
        with self._conn() as conn:
            base_query = """
            SELECT
                i.especie,
                i.especie_code,
                COALESCE(i.zona, 'Nacional') AS zona,
                i.year,
                i.cba_recomendada_tn,
                c.cmp_aprobada_tn,
                cr.captura_tn AS captura_real_tn,
                CASE
                    WHEN c.cmp_aprobada_tn IS NOT NULL AND i.cba_recomendada_tn IS NOT NULL
                    THEN ROUND(c.cmp_aprobada_tn / i.cba_recomendada_tn, 3)
                END AS ratio_cmp_cba,
                CASE
                    WHEN cr.captura_tn IS NOT NULL AND i.cba_recomendada_tn IS NOT NULL
                    THEN ROUND(cr.captura_tn / i.cba_recomendada_tn, 3)
                END AS ratio_captura_cba
            FROM inidep_evaluaciones i
            LEFT JOIN cfp_cuotas c
                ON i.especie_code = c.especie_code
                AND i.year = c.year
                AND (i.zona = c.zona OR c.zona IS NULL)
            LEFT JOIN capturas_reales cr
                ON i.especie_code = cr.especie_code
                AND i.year = cr.year
            """
            if especie_code:
                base_query += " WHERE i.especie_code = ?"
                base_query += " ORDER BY i.year DESC, i.especie"
                return pd.read_sql_query(base_query, conn, params=(especie_code,))
            base_query += " ORDER BY i.year DESC, i.especie"
            return pd.read_sql_query(base_query, conn)

    def summary_report(self) -> dict:
        alertas = self.compute_comparisons()
        from collections import Counter

        conteo = Counter(a.nivel for a in alertas)
        criticas = [a for a in alertas if a.nivel == ALERTA_CRITICA]
        rojas = [a for a in alertas if a.nivel == ALERTA_ROJA]
        sub_utilizacion = [a for a in alertas if a.alerta_captura == "sub_utilizacion"]

        return {
            "total_comparaciones": len(alertas),
            "por_nivel": dict(conteo),
            "alertas_criticas": [asdict(a) for a in criticas],
            "alertas_rojas": [asdict(a) for a in rojas],
            "n_sub_utilizacion": len(sub_utilizacion),
            "especies_monitoreadas": list({a.especie for a in alertas}),
            "años_cubiertos": sorted({a.year for a in alertas}),
        }
