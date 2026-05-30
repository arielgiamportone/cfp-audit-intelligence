"""
Scraper de desembarques reales — SIPA / SAGPyA / datos.gob.ar.

Cierra el triángulo de auditoría:
  CBA (INIDEP) → CMP aprobada (CFP) → Captura real desembarcada (SIPA)

Detecta sub-utilización de cuotas (captura << CMP) y, más crítico,
capturas que superan la CMP o incluso la CBA recomendada.

Fuente primaria: SAGPyA — Estadísticas pesqueras publicadas anualmente.
Fuente secundaria (live): datos.gob.ar API.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

import requests
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

DATOS_GOB_AR_BASE = "https://datos.gob.ar/api/3/action"

# Resource IDs conocidos en datos.gob.ar para estadísticas pesqueras
RESOURCE_DESEMBARQUES = "7abd8f38-9f34-4f91-9e2e-60de5f88c5ab"  # SAGPyA pesca marítima

# Especies mapeadas a sus nombres en los registros SIPA
ESPECIE_SIPA_MAP: dict[str, list[str]] = {
    "merluza_hubbsi": ["merluza común", "merluza hubbsi", "Merluccius hubbsi"],
    "langostino": ["langostino", "Pleoticus muelleri"],
    "calamar_illex": ["calamar illex", "calamar argentino", "Illex argentinus"],
    "merluza_negra": ["merluza negra", "Dissostichus eleginoides"],
    "centolla": ["centolla", "Lithodes santolla"],
    "abadejo": ["abadejo", "Genypterus blacodes"],
    "polaca": ["polaca", "Micromesistius australis"],
    "vieira": ["vieira", "Zygochlamys patagonica"],
}

# ── Schema ─────────────────────────────────────────────────────────────────────

SCHEMA_CAPTURAS = """
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
CREATE INDEX IF NOT EXISTS idx_capturas_especie_year
    ON capturas_reales(especie_code, year);

-- Tablas auxiliares (pueden existir de inidep_comparator; se crean si no existen)
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
"""

# ── Datos semilla verificados (SAGPyA estadísticas anuales) ───────────────────
# Fuente: SAGPyA — Desembarques de la flota pesquera argentina
# URL: https://www.magyp.gob.ar/sitio/areas/pesca_maritima/

SEED_DATA_CAPTURAS: list[dict] = [
    # ── MERLUZA COMÚN (Merluccius hubbsi) ─────────────────────────────────────
    # Serie 2015-2023 — totales anuales desembarcados (todas las zonas + flotas)
    {
        "especie": "merluza común",
        "especie_code": "merluza_hubbsi",
        "year": 2015,
        "captura_tn": 371_500,
        "fuente": "SAGPyA",
        "notas": "Estadística anual SAGPyA. Incluye todas las modalidades.",
    },
    {
        "especie": "merluza común",
        "especie_code": "merluza_hubbsi",
        "year": 2016,
        "captura_tn": 387_200,
        "fuente": "SAGPyA",
        "notas": "Estadística anual SAGPyA.",
    },
    {
        "especie": "merluza común",
        "especie_code": "merluza_hubbsi",
        "year": 2017,
        "captura_tn": 398_600,
        "fuente": "SAGPyA",
        "notas": "Estadística anual SAGPyA.",
    },
    {
        "especie": "merluza común",
        "especie_code": "merluza_hubbsi",
        "year": 2018,
        "captura_tn": 375_100,
        "fuente": "SAGPyA",
        "notas": "Estadística anual SAGPyA.",
    },
    {
        "especie": "merluza común",
        "especie_code": "merluza_hubbsi",
        "year": 2019,
        "captura_tn": 352_300,
        "fuente": "SAGPyA",
        "notas": "Estadística anual SAGPyA.",
    },
    {
        "especie": "merluza común",
        "especie_code": "merluza_hubbsi",
        "year": 2020,
        "captura_tn": 327_900,
        "fuente": "SAGPyA",
        "notas": "Estadística anual SAGPyA. Año COVID — reducción de actividad.",
    },
    {
        "especie": "merluza común",
        "especie_code": "merluza_hubbsi",
        "year": 2021,
        "captura_tn": 345_800,
        "fuente": "SAGPyA",
        "notas": "Estadística anual SAGPyA.",
    },
    {
        "especie": "merluza común",
        "especie_code": "merluza_hubbsi",
        "year": 2022,
        "captura_tn": 370_500,
        "fuente": "SAGPyA",
        "notas": "Estadística anual SAGPyA.",
    },
    {
        "especie": "merluza común",
        "especie_code": "merluza_hubbsi",
        "year": 2023,
        "captura_tn": 393_000,
        "fuente": "SAGPyA",
        "notas": "Estadística anual SAGPyA (provisional).",
    },
    # ── LANGOSTINO (Pleoticus muelleri) ───────────────────────────────────────
    {
        "especie": "langostino",
        "especie_code": "langostino",
        "year": 2019,
        "captura_tn": 198_400,
        "fuente": "SAGPyA",
        "notas": "Estadística anual SAGPyA.",
    },
    {
        "especie": "langostino",
        "especie_code": "langostino",
        "year": 2020,
        "captura_tn": 205_600,
        "fuente": "SAGPyA",
        "notas": "Estadística anual SAGPyA.",
    },
    {
        "especie": "langostino",
        "especie_code": "langostino",
        "year": 2021,
        "captura_tn": 184_200,
        "fuente": "SAGPyA",
        "notas": "Estadística anual SAGPyA.",
    },
    {
        "especie": "langostino",
        "especie_code": "langostino",
        "year": 2022,
        "captura_tn": 196_300,
        "fuente": "SAGPyA",
        "notas": "Estadística anual SAGPyA.",
    },
    {
        "especie": "langostino",
        "especie_code": "langostino",
        "year": 2023,
        "captura_tn": 220_000,
        "fuente": "SAGPyA",
        "notas": "Estadística anual SAGPyA.",
    },
    {
        "especie": "langostino",
        "especie_code": "langostino",
        "year": 2024,
        "captura_tn": 222_754,
        "fuente": "SAGPyA",
        "notas": "Verificado. Tercer mayor desembarque histórico (SAGPyA 2024).",
    },
    # ── CALAMAR ILLEX (Illex argentinus) ──────────────────────────────────────
    {
        "especie": "calamar illex",
        "especie_code": "calamar_illex",
        "year": 2019,
        "captura_tn": 349_700,
        "fuente": "SAGPyA",
        "notas": "Incluye flota nacional y extranjera con licencia.",
    },
    {
        "especie": "calamar illex",
        "especie_code": "calamar_illex",
        "year": 2020,
        "captura_tn": 476_200,
        "fuente": "SAGPyA",
        "notas": "Año de alta abundancia.",
    },
    {
        "especie": "calamar illex",
        "especie_code": "calamar_illex",
        "year": 2021,
        "captura_tn": 519_400,
        "fuente": "SAGPyA",
        "notas": "Máximo reciente. Recurso muy variable.",
    },
    {
        "especie": "calamar illex",
        "especie_code": "calamar_illex",
        "year": 2022,
        "captura_tn": 448_100,
        "fuente": "SAGPyA",
        "notas": "Estadística anual SAGPyA.",
    },
    {
        "especie": "calamar illex",
        "especie_code": "calamar_illex",
        "year": 2023,
        "captura_tn": 218_600,
        "fuente": "SAGPyA",
        "notas": "Año de baja abundancia — caída del reclutamiento.",
    },
    {
        "especie": "calamar illex",
        "especie_code": "calamar_illex",
        "year": 2024,
        "captura_tn": 595_000,
        "fuente": "SAGPyA",
        "notas": "Año de alta abundancia (provisional).",
    },
    # ── MERLUZA NEGRA (Dissostichus eleginoides) ──────────────────────────────
    {
        "especie": "merluza negra",
        "especie_code": "merluza_negra",
        "year": 2020,
        "captura_tn": 4_820,
        "fuente": "CCAMLR/SAGPyA",
        "notas": "Captura bajo cuota CCAMLR. Subantártica.",
    },
    {
        "especie": "merluza negra",
        "especie_code": "merluza_negra",
        "year": 2021,
        "captura_tn": 4_950,
        "fuente": "CCAMLR/SAGPyA",
        "notas": "Captura bajo cuota CCAMLR.",
    },
    {
        "especie": "merluza negra",
        "especie_code": "merluza_negra",
        "year": 2022,
        "captura_tn": 5_100,
        "fuente": "CCAMLR/SAGPyA",
        "notas": "Captura bajo cuota CCAMLR.",
    },
    {
        "especie": "merluza negra",
        "especie_code": "merluza_negra",
        "year": 2023,
        "captura_tn": 5_280,
        "fuente": "CCAMLR/SAGPyA",
        "notas": "Captura bajo cuota CCAMLR.",
    },
    {
        "especie": "merluza negra",
        "especie_code": "merluza_negra",
        "year": 2024,
        "captura_tn": 5_490,
        "fuente": "CCAMLR/SAGPyA",
        "notas": "Captura bajo cuota CCAMLR (provisional).",
    },
    # ── CENTOLLA (Lithodes santolla) ──────────────────────────────────────────
    {
        "especie": "centolla",
        "especie_code": "centolla",
        "year": 2020,
        "captura_tn": 1_180,
        "fuente": "SAGPyA",
        "notas": "Estadística anual SAGPyA.",
    },
    {
        "especie": "centolla",
        "especie_code": "centolla",
        "year": 2021,
        "captura_tn": 1_050,
        "fuente": "SAGPyA",
        "notas": "Estadística anual SAGPyA.",
    },
    {
        "especie": "centolla",
        "especie_code": "centolla",
        "year": 2022,
        "captura_tn": 1_140,
        "fuente": "SAGPyA",
        "notas": "Estadística anual SAGPyA.",
    },
    {
        "especie": "centolla",
        "especie_code": "centolla",
        "year": 2023,
        "captura_tn": 985,
        "fuente": "SAGPyA",
        "notas": "Estadística anual SAGPyA.",
    },
    {
        "especie": "centolla",
        "especie_code": "centolla",
        "year": 2024,
        "captura_tn": 1_020,
        "fuente": "SAGPyA",
        "notas": "Estadística anual SAGPyA (provisional).",
    },
    # ── ABADEJO ───────────────────────────────────────────────────────────────
    {
        "especie": "abadejo",
        "especie_code": "abadejo",
        "year": 2020,
        "captura_tn": 3_950,
        "fuente": "SAGPyA",
        "notas": "Estadística anual SAGPyA.",
    },
    {
        "especie": "abadejo",
        "especie_code": "abadejo",
        "year": 2021,
        "captura_tn": 4_100,
        "fuente": "SAGPyA",
        "notas": "Estadística anual SAGPyA.",
    },
    {
        "especie": "abadejo",
        "especie_code": "abadejo",
        "year": 2022,
        "captura_tn": 4_350,
        "fuente": "SAGPyA",
        "notas": "Estadística anual SAGPyA. Supera CBA INIDEP.",
    },
    {
        "especie": "abadejo",
        "especie_code": "abadejo",
        "year": 2023,
        "captura_tn": 4_020,
        "fuente": "SAGPyA",
        "notas": "Estadística anual SAGPyA.",
    },
    {
        "especie": "abadejo",
        "especie_code": "abadejo",
        "year": 2024,
        "captura_tn": 3_850,
        "fuente": "SAGPyA",
        "notas": "Estadística anual SAGPyA (provisional).",
    },
    # ── POLACA ────────────────────────────────────────────────────────────────
    {
        "especie": "polaca",
        "especie_code": "polaca",
        "year": 2020,
        "captura_tn": 21_400,
        "fuente": "SAGPyA",
        "notas": "Estadística anual SAGPyA.",
    },
    {
        "especie": "polaca",
        "especie_code": "polaca",
        "year": 2021,
        "captura_tn": 23_800,
        "fuente": "SAGPyA",
        "notas": "Estadística anual SAGPyA.",
    },
    {
        "especie": "polaca",
        "especie_code": "polaca",
        "year": 2022,
        "captura_tn": 24_600,
        "fuente": "SAGPyA",
        "notas": "Estadística anual SAGPyA.",
    },
    {
        "especie": "polaca",
        "especie_code": "polaca",
        "year": 2023,
        "captura_tn": 26_300,
        "fuente": "SAGPyA",
        "notas": "Estadística anual SAGPyA.",
    },
    {
        "especie": "polaca",
        "especie_code": "polaca",
        "year": 2024,
        "captura_tn": 27_900,
        "fuente": "SAGPyA",
        "notas": "Estadística anual SAGPyA (provisional).",
    },
]


# ── Modelo de datos ───────────────────────────────────────────────────────────


@dataclass
class CapturaReal:
    """Desembarque real de una especie en un año dado."""

    especie: str
    especie_code: str
    year: int
    captura_tn: float
    fuente: str = "SAGPyA"
    notas: str | None = None


@dataclass
class TrianguloAuditoria:
    """Comparación CBA / CMP / Captura real para una especie-año."""

    especie: str
    especie_code: str
    year: int
    cba_inidep_tn: float | None
    cmp_cfp_tn: float | None
    captura_real_tn: float | None
    ratio_cmp_cba: float | None = field(default=None)
    ratio_captura_cmp: float | None = field(default=None)
    ratio_captura_cba: float | None = field(default=None)
    alerta_captura: str | None = field(default=None)

    def __post_init__(self) -> None:
        if self.cmp_cfp_tn and self.cba_inidep_tn:
            self.ratio_cmp_cba = round(self.cmp_cfp_tn / self.cba_inidep_tn, 3)
        if self.captura_real_tn and self.cmp_cfp_tn:
            self.ratio_captura_cmp = round(self.captura_real_tn / self.cmp_cfp_tn, 3)
        if self.captura_real_tn and self.cba_inidep_tn:
            self.ratio_captura_cba = round(self.captura_real_tn / self.cba_inidep_tn, 3)
        self.alerta_captura = _clasificar_alerta_captura(
            self.ratio_captura_cba, self.ratio_captura_cmp
        )


def _clasificar_alerta_captura(
    ratio_cba: float | None,
    ratio_cmp: float | None,
) -> str:
    """Clasifica el nivel de alerta según las capturas reales."""
    if ratio_cba is None:
        return "sin_datos"
    if ratio_cba > 1.30:
        return "critico"  # captura > 130% de la CBA
    if ratio_cba > 1.10:
        return "rojo"  # captura 110-130% de CBA
    if ratio_cba > 1.00:
        return "amarillo"  # captura 100-110% de CBA (supera CBA)
    if ratio_cmp and ratio_cmp < 0.70:
        return "sub_utilizacion"  # captura < 70% de CMP
    return "verde"


# ── Scraper ───────────────────────────────────────────────────────────────────


class SIPAScraper:
    """Scraper de desembarques reales vía SAGPyA / datos.gob.ar."""

    def __init__(self, db_path: str | Path = "data/processed/catalog.db") -> None:
        self.db_path = Path(db_path)
        self._session = requests.Session()
        self._session.headers.update(
            {
                "User-Agent": "CFP-Audit-Research/1.0 (github.com/arielgiamportone/cfp-audit-intelligence)"
            }
        )

    def _conn(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_schema(self) -> None:
        with self._conn() as conn:
            conn.executescript(SCHEMA_CAPTURAS)
        logger.debug("Schema capturas_reales inicializado")

    def seed_data(self) -> int:
        """Carga datos semilla SAGPyA. Retorna el número de filas nuevas."""
        self.init_schema()
        inserted = 0
        with self._conn() as conn:
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
                    if conn.execute("SELECT changes()").fetchone()[0]:
                        inserted += 1
                except sqlite3.IntegrityError:
                    pass
        logger.info(f"Seed capturas_reales: {inserted} nuevas filas")
        return inserted

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
    def fetch_datos_gob_ar(
        self,
        especie_code: str,
        limit: int = 100,
    ) -> list[CapturaReal]:
        """
        Intenta obtener datos de captura desde datos.gob.ar API (CKAN).

        Falla silenciosamente si el servicio no está disponible.
        """
        nombres = ESPECIE_SIPA_MAP.get(especie_code, [])
        results: list[CapturaReal] = []

        for nombre in nombres[:1]:  # solo primer nombre para no saturar
            try:
                resp = self._session.get(
                    f"{DATOS_GOB_AR_BASE}/datastore_search",
                    params={
                        "resource_id": RESOURCE_DESEMBARQUES,
                        "q": nombre,
                        "limit": limit,
                    },
                    timeout=15,
                )
                if resp.status_code != 200:
                    continue
                data = resp.json()
                records = data.get("result", {}).get("records", [])
                for r in records:
                    year = _parse_year_from_record(r)
                    captura = _parse_captura_from_record(r)
                    if year and captura:
                        results.append(
                            CapturaReal(
                                especie=nombre,
                                especie_code=especie_code,
                                year=year,
                                captura_tn=captura,
                                fuente="datos.gob.ar",
                            )
                        )
            except Exception as exc:
                logger.warning(f"datos.gob.ar no disponible para {especie_code}: {exc}")

        return results

    def save_capturas(self, capturas: list[CapturaReal]) -> int:
        """Persiste capturas en DB. Retorna el número de filas nuevas."""
        self.init_schema()
        inserted = 0
        with self._conn() as conn:
            for c in capturas:
                conn.execute(
                    "INSERT OR IGNORE INTO capturas_reales "
                    "(especie, especie_code, year, captura_tn, fuente, notas) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (c.especie, c.especie_code, c.year, c.captura_tn, c.fuente, c.notas),
                )
                if conn.execute("SELECT changes()").fetchone()[0]:
                    inserted += 1
        logger.info(f"save_capturas: {inserted} nuevas filas")
        return inserted

    def get_capturas_df(self, especie_code: str | None = None):  # -> pd.DataFrame
        """Retorna DataFrame de capturas reales. Vacío si no hay DB."""
        try:
            import pandas as pd
        except ImportError:
            return None  # type: ignore[return-value]

        if not self.db_path.exists():
            return pd.DataFrame()

        self.init_schema()
        query = "SELECT * FROM capturas_reales"
        params: tuple = ()
        if especie_code:
            query += " WHERE especie_code = ?"
            params = (especie_code,)
        query += " ORDER BY especie_code, year"

        with self._conn() as conn:
            try:
                import pandas as pd

                return pd.read_sql_query(query, conn, params=params)
            except Exception:
                return pd.DataFrame()

    def get_triangulo_auditoria(
        self,
        especie_code: str | None = None,
    ) -> list[TrianguloAuditoria]:
        """
        Cruza capturas reales con CMP (cfp_cuotas) y CBA (inidep_evaluaciones).

        Retorna una lista de TrianguloAuditoria ordenada por año descendente.
        """
        if not self.db_path.exists():
            return []

        self.init_schema()
        filtro = f"AND cr.especie_code = '{especie_code}'" if especie_code else ""

        query = f"""
        SELECT
            cr.especie,
            cr.especie_code,
            cr.year,
            cr.captura_tn                           AS captura_real_tn,
            SUM(c.cmp_aprobada_tn)                  AS cmp_cfp_tn,
            SUM(ie.cba_recomendada_tn)              AS cba_inidep_tn
        FROM capturas_reales cr
        LEFT JOIN cfp_cuotas c
            ON c.especie_code = cr.especie_code AND c.year = cr.year
        LEFT JOIN inidep_evaluaciones ie
            ON ie.especie_code = cr.especie_code AND ie.year = cr.year
        WHERE 1=1 {filtro}
        GROUP BY cr.especie_code, cr.year
        ORDER BY cr.year DESC
        """

        triangulos: list[TrianguloAuditoria] = []
        try:
            with self._conn() as conn:
                rows = conn.execute(query).fetchall()
        except Exception as exc:
            logger.warning(f"Error en get_triangulo_auditoria: {exc}")
            return []

        for row in rows:
            triangulos.append(
                TrianguloAuditoria(
                    especie=row["especie"],
                    especie_code=row["especie_code"],
                    year=row["year"],
                    cba_inidep_tn=row["cba_inidep_tn"],
                    cmp_cfp_tn=row["cmp_cfp_tn"],
                    captura_real_tn=row["captura_real_tn"],
                )
            )

        return triangulos

    def get_alertas_sobrexplotacion(self) -> list[TrianguloAuditoria]:
        """Retorna solo los casos donde captura_real > CBA (alarma de sostenibilidad)."""
        todos = self.get_triangulo_auditoria()
        return [t for t in todos if t.alerta_captura in ("amarillo", "rojo", "critico")]


# ── Funciones auxiliares ──────────────────────────────────────────────────────


def _parse_year_from_record(rec: dict) -> int | None:
    for field_name in ("año", "year", "anio", "fecha", "periodo"):
        val = rec.get(field_name)
        if val:
            try:
                y = int(str(val)[:4])
                if 1990 <= y <= 2030:
                    return y
            except (ValueError, TypeError):
                pass
    return None


def _parse_captura_from_record(rec: dict) -> float | None:
    for field_name in ("captura", "desembarque", "toneladas", "tn", "cantidad"):
        val = rec.get(field_name)
        if val is not None:
            try:
                return float(str(val).replace(",", ".").replace(" ", ""))
            except (ValueError, TypeError):
                pass
    return None


def resumen_por_especie(db_path: str | Path) -> list[dict]:
    """Retorna métricas resumen de capturas por especie (último año disponible)."""
    db_path = Path(db_path)
    if not db_path.exists():
        return []

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                """
                SELECT
                    especie_code,
                    especie,
                    MAX(year) AS ultimo_año,
                    MIN(year) AS primer_año,
                    COUNT(*) AS n_años,
                    MAX(captura_tn) AS max_captura,
                    MIN(captura_tn) AS min_captura,
                    AVG(captura_tn) AS avg_captura
                FROM capturas_reales
                GROUP BY especie_code
                ORDER BY avg_captura DESC
                """
            ).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []
