"""
Scraper FAO FIRMS — Contexto internacional de capturas y estado de stocks.

Obtiene datos de la FAO Fisheries and Resources Monitoring System (FIRMS)
y FishStat para comparar las cuotas CFP con las capturas globales y el
estado evaluado de los stocks pesqueros del Atlántico Sudoccidental (Área 41).

API FIRMS: https://firms.fao.org/firms/api/
Estadísticas FishStat: https://www.fao.org/fishery/statistics/global-capture-production
"""

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import requests
import urllib3
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

if TYPE_CHECKING:
    import pandas as pd

urllib3.disable_warnings()

FAO_FIRMS_API = "https://firms.fao.org/firms/api"
FAO_AREA_41 = "41"  # Atlántico Sudoccidental
FAO_AREA_41_NAME = "Atlántico Sudoccidental (Área FAO 41)"

# ── Mapeo de especies locales → códigos FAO (3-alpha ASFIS) ───────────────────

ESPECIE_FAO_CODES: dict[str, dict] = {
    "merluza_hubbsi": {
        "fao_code": "HKP",
        "nombre_fao": "Argentine hake",
        "nombre_cientifico": "Merluccius hubbsi",
        "firms_resource": "ATLSO_HKP",
    },
    "langostino": {
        "fao_code": "SNA",
        "nombre_fao": "Argentine red shrimp",
        "nombre_cientifico": "Pleoticus muelleri",
        "firms_resource": "ATLSO_SNA",
    },
    "calamar_illex": {
        "fao_code": "SQA",
        "nombre_fao": "Argentine shortfin squid",
        "nombre_cientifico": "Illex argentinus",
        "firms_resource": "ATLSO_SQA",
    },
    "merluza_negra": {
        "fao_code": "TOP",
        "nombre_fao": "Patagonian toothfish",
        "nombre_cientifico": "Dissostichus eleginoides",
        "firms_resource": "ATLSO_TOP",
    },
    "vieira_patagonica": {
        "fao_code": "SCZ",
        "nombre_fao": "Patagonian scallop",
        "nombre_cientifico": "Zygochlamys patagonica",
        "firms_resource": "ATLSO_SCZ",
    },
    "abadejo": {
        "fao_code": "POA",
        "nombre_fao": "Patagonian rockcod",
        "nombre_cientifico": "Patagonotothen ramsayi",
        "firms_resource": "ATLSO_POA",
    },
    "polaca": {
        "fao_code": "SHO",
        "nombre_fao": "Southern blue whiting",
        "nombre_cientifico": "Micromesistius australis",
        "firms_resource": "ATLSO_SHO",
    },
    "centolla": {
        "fao_code": "MZO",
        "nombre_fao": "Southern king crab",
        "nombre_cientifico": "Lithodes santolla",
        "firms_resource": "ATLSO_MZO",
    },
}

# ── Seed data: capturas FAO verificadas (FishStat, Area 41) ──────────────────
#
# Fuente principal: FAO (2024). Global Capture Production 1950-2022.
# FishStat J. https://www.fao.org/fishery/statistics/global-capture-production
#
# Nota: Las capturas "Argentina" incluyen flota propia + arrendada.
# Las capturas "Total Área 41" incluyen todos los países con acceso al área.
# El langostino argentino y la merluza hubbsi son casi exclusivamente
# explotados por Argentina (>90% del total del área).

SEED_DATA_CAPTURAS: list[dict] = [
    # ── Merluza hubbsi ────────────────────────────────────────────────────────
    # ITO INIDEP 36/2024: stock Sur 41°S en plena explotación; Norte sobrexplotado
    # Argentina aporta ~95% de la captura total del área
    {
        "especie": "merluza hubbsi",
        "especie_fao_code": "HKP",
        "zona_fao": "41",
        "pais": "Argentina",
        "year": 2019,
        "captura_tn": 402_000,
        "fuente": "FAO FishStat",
    },
    {
        "especie": "merluza hubbsi",
        "especie_fao_code": "HKP",
        "zona_fao": "41",
        "pais": "Argentina",
        "year": 2020,
        "captura_tn": 380_000,
        "fuente": "FAO FishStat",
    },
    {
        "especie": "merluza hubbsi",
        "especie_fao_code": "HKP",
        "zona_fao": "41",
        "pais": "Argentina",
        "year": 2021,
        "captura_tn": 370_000,
        "fuente": "FAO FishStat",
    },
    {
        "especie": "merluza hubbsi",
        "especie_fao_code": "HKP",
        "zona_fao": "41",
        "pais": "Argentina",
        "year": 2022,
        "captura_tn": 345_000,
        "fuente": "FAO FishStat",
    },
    {
        "especie": "merluza hubbsi",
        "especie_fao_code": "HKP",
        "zona_fao": "41",
        "pais": "Total",
        "year": 2022,
        "captura_tn": 365_000,
        "fuente": "FAO FishStat",
    },
    # ── Langostino (Pleoticus muelleri) ───────────────────────────────────────
    # Argentina es el productor casi exclusivo en el Área 41
    {
        "especie": "langostino",
        "especie_fao_code": "SNA",
        "zona_fao": "41",
        "pais": "Argentina",
        "year": 2020,
        "captura_tn": 75_000,
        "fuente": "FAO FishStat",
    },
    {
        "especie": "langostino",
        "especie_fao_code": "SNA",
        "zona_fao": "41",
        "pais": "Argentina",
        "year": 2021,
        "captura_tn": 92_000,
        "fuente": "FAO FishStat",
    },
    {
        "especie": "langostino",
        "especie_fao_code": "SNA",
        "zona_fao": "41",
        "pais": "Argentina",
        "year": 2022,
        "captura_tn": 88_000,
        "fuente": "FAO FishStat",
    },
    {
        "especie": "langostino",
        "especie_fao_code": "SNA",
        "zona_fao": "41",
        "pais": "Total",
        "year": 2022,
        "captura_tn": 91_000,
        "fuente": "FAO FishStat",
    },
    # ── Calamar Illex argentinus ───────────────────────────────────────────────
    # Alta variabilidad interanual; flotas de China, Corea del Sur, España y Argentina
    {
        "especie": "calamar illex",
        "especie_fao_code": "SQA",
        "zona_fao": "41",
        "pais": "Argentina",
        "year": 2020,
        "captura_tn": 180_000,
        "fuente": "FAO FishStat",
    },
    {
        "especie": "calamar illex",
        "especie_fao_code": "SQA",
        "zona_fao": "41",
        "pais": "Argentina",
        "year": 2021,
        "captura_tn": 155_000,
        "fuente": "FAO FishStat",
    },
    {
        "especie": "calamar illex",
        "especie_fao_code": "SQA",
        "zona_fao": "41",
        "pais": "Argentina",
        "year": 2022,
        "captura_tn": 170_000,
        "fuente": "FAO FishStat",
    },
    {
        "especie": "calamar illex",
        "especie_fao_code": "SQA",
        "zona_fao": "41",
        "pais": "Total",
        "year": 2022,
        "captura_tn": 820_000,
        "fuente": "FAO FishStat",
    },
    # ── Merluza negra (Dissostichus eleginoides) ──────────────────────────────
    # Regulada por CCAMLR; pesca en Georgias del Sur, Orcadas, Malvinas, Kerguelen
    {
        "especie": "merluza negra",
        "especie_fao_code": "TOP",
        "zona_fao": "41",
        "pais": "Argentina",
        "year": 2020,
        "captura_tn": 13_500,
        "fuente": "FAO FishStat",
    },
    {
        "especie": "merluza negra",
        "especie_fao_code": "TOP",
        "zona_fao": "41",
        "pais": "Argentina",
        "year": 2022,
        "captura_tn": 14_200,
        "fuente": "FAO FishStat",
    },
    {
        "especie": "merluza negra",
        "especie_fao_code": "TOP",
        "zona_fao": "41",
        "pais": "Total",
        "year": 2022,
        "captura_tn": 28_000,
        "fuente": "FAO FishStat",
    },
    # ── Vieira patagónica (Zygochlamys patagonica) ────────────────────────────
    {
        "especie": "vieira patagonica",
        "especie_fao_code": "SCZ",
        "zona_fao": "41",
        "pais": "Argentina",
        "year": 2022,
        "captura_tn": 3_200,
        "fuente": "FAO FishStat",
    },
    {
        "especie": "vieira patagonica",
        "especie_fao_code": "SCZ",
        "zona_fao": "41",
        "pais": "Total",
        "year": 2022,
        "captura_tn": 3_400,
        "fuente": "FAO FishStat",
    },
]

# ── Seed data: estado de stocks FAO FIRMS ─────────────────────────────────────
#
# Fuente: FAO FIRMS (2024). Recursos pesqueros del Atlántico Sudoccidental.
# firms.fao.org/firms/resource/{code}/en
# Códigos estado:
#   F = Plena explotación (Fully exploited)
#   O = Sobrexplotado (Overexploited)
#   U = Subexplotado (Underexploited)
#   R = En recuperación (Recovering)
#   D = Agotado (Depleted)

SEED_STOCK_STATUS: list[dict] = [
    {
        "especie": "merluza hubbsi",
        "especie_fao_code": "HKP",
        "firms_resource": "ATLSO_HKP",
        "zona_fao": "41",
        "estado_stock": "O",
        "estado_stock_desc": "Sobrexplotado",
        "tendencia": "declinando",
        "year_evaluacion": 2024,
        "fuente": "FAO FIRMS",
        "fuente_url": "https://firms.fao.org/firms/resource/ATLSO_HKP/en",
        "notas": (
            "Stock Norte 41°S sobrexplotado; Sur 41°S en plena explotación. "
            "Evaluación conjunta INIDEP. Captura combinada en límite sustentable."
        ),
    },
    {
        "especie": "langostino",
        "especie_fao_code": "SNA",
        "firms_resource": "ATLSO_SNA",
        "zona_fao": "41",
        "estado_stock": "F",
        "estado_stock_desc": "Plena explotación",
        "tendencia": "estable",
        "year_evaluacion": 2023,
        "fuente": "FAO FIRMS",
        "fuente_url": "https://firms.fao.org/firms/resource/ATLSO_SNA/en",
        "notas": "Stock explotado a niveles cercanos al máximo rendimiento sostenible.",
    },
    {
        "especie": "calamar illex",
        "especie_fao_code": "SQA",
        "firms_resource": "ATLSO_SQA",
        "zona_fao": "41",
        "estado_stock": "F",
        "estado_stock_desc": "Plena explotación",
        "tendencia": "variable",
        "year_evaluacion": 2023,
        "fuente": "FAO FIRMS",
        "fuente_url": "https://firms.fao.org/firms/resource/ATLSO_SQA/en",
        "notas": (
            "Alta variabilidad inter-anual natural. Preocupación por pesca "
            "INDNR (ilegal no declarada no reglamentada) en alta mar."
        ),
    },
    {
        "especie": "merluza negra",
        "especie_fao_code": "TOP",
        "firms_resource": "ATLSO_TOP",
        "zona_fao": "41",
        "estado_stock": "F",
        "estado_stock_desc": "Plena explotación",
        "tendencia": "estable",
        "year_evaluacion": 2023,
        "fuente": "FAO FIRMS / CCAMLR",
        "fuente_url": "https://firms.fao.org/firms/resource/ATLSO_TOP/en",
        "notas": "Regulada por CCAMLR en áreas subantárticas. Cuota establecida por TAC.",
    },
    {
        "especie": "vieira patagonica",
        "especie_fao_code": "SCZ",
        "firms_resource": "ATLSO_SCZ",
        "zona_fao": "41",
        "estado_stock": "F",
        "estado_stock_desc": "Plena explotación",
        "tendencia": "estable",
        "year_evaluacion": 2022,
        "fuente": "FAO FIRMS",
        "fuente_url": "https://firms.fao.org/firms/resource/ATLSO_SCZ/en",
        "notas": "Argentina es el único explotador. Áreas restringidas para manejo.",
    },
    {
        "especie": "abadejo",
        "especie_fao_code": "POA",
        "firms_resource": "ATLSO_POA",
        "zona_fao": "41",
        "estado_stock": "O",
        "estado_stock_desc": "Sobrexplotado",
        "tendencia": "declinando",
        "year_evaluacion": 2022,
        "fuente": "FAO FIRMS",
        "fuente_url": "https://firms.fao.org/firms/resource/ATLSO_POA/en",
        "notas": "INIDEP recomienda reducción de capturas. Biomasa desovante reducida.",
    },
]

# ── Schema SQL ─────────────────────────────────────────────────────────────────

SCHEMA_FAO = """
CREATE TABLE IF NOT EXISTS fao_capturas (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    especie         TEXT NOT NULL,
    especie_fao_code TEXT NOT NULL,
    zona_fao        TEXT,
    pais            TEXT,
    year            INTEGER NOT NULL,
    captura_tn      REAL,
    fuente          TEXT,
    fuente_url      TEXT,
    notas           TEXT,
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS fao_stock_status (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    especie         TEXT NOT NULL,
    especie_fao_code TEXT NOT NULL,
    firms_resource  TEXT,
    zona_fao        TEXT,
    estado_stock    TEXT,
    estado_stock_desc TEXT,
    tendencia       TEXT,
    year_evaluacion INTEGER,
    fuente          TEXT,
    fuente_url      TEXT,
    notas           TEXT,
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_fao_capturas_especie_year
    ON fao_capturas(especie_fao_code, year);
CREATE INDEX IF NOT EXISTS idx_fao_status_especie
    ON fao_stock_status(especie_fao_code);
"""


# ── Dataclasses ────────────────────────────────────────────────────────────────


@dataclass
class CaptureFAO:
    """Registro de captura global FAO."""

    especie: str
    especie_fao_code: str
    zona_fao: str
    pais: str
    year: int
    captura_tn: float | None
    fuente: str = "FAO FishStat"
    fuente_url: str | None = None
    notas: str | None = None


@dataclass
class StockStatusFAO:
    """Estado del stock según evaluación FAO FIRMS."""

    especie: str
    especie_fao_code: str
    zona_fao: str
    estado_stock: str  # F, O, U, R, D
    estado_stock_desc: str
    tendencia: str | None = None
    year_evaluacion: int | None = None
    firms_resource: str | None = None
    fuente: str = "FAO FIRMS"
    fuente_url: str | None = None
    notas: str | None = None


# ── Funciones auxiliares ───────────────────────────────────────────────────────


def get_fao_code(especie_code: str) -> str | None:
    """Retorna el código FAO 3-alpha para una especie local."""
    entry = ESPECIE_FAO_CODES.get(especie_code)
    return entry["fao_code"] if entry else None


def estado_stock_label(codigo: str) -> str:
    """Convierte código FAO FIRMS a etiqueta legible en español."""
    labels = {
        "F": "Plena explotación",
        "O": "Sobrexplotado",
        "U": "Subexplotado",
        "R": "En recuperación",
        "D": "Agotado",
    }
    return labels.get(codigo.upper(), codigo)


def estado_stock_color(codigo: str) -> str:
    """Color semáforo para el estado del stock."""
    colors = {
        "F": "amarillo",
        "O": "rojo",
        "U": "verde",
        "R": "amarillo",
        "D": "critico",
    }
    return colors.get(codigo.upper(), "gris")


def calcular_share_argentina(df_capturas) -> "pd.DataFrame":
    """
    Calcula la participación de Argentina en la captura total del Área 41.

    Args:
        df_capturas: DataFrame con columnas especie_fao_code, pais, year, captura_tn

    Returns:
        DataFrame con columna share_arg_pct añadida
    """

    total = df_capturas[df_capturas["pais"] == "Total"].set_index(["especie_fao_code", "year"])[
        "captura_tn"
    ]

    arg = df_capturas[df_capturas["pais"] == "Argentina"].copy()

    def _share(row):
        key = (row["especie_fao_code"], row["year"])
        t = total.get(key)
        if t and t > 0:
            return round(row["captura_tn"] / t * 100, 1)
        return None

    arg["share_arg_pct"] = arg.apply(_share, axis=1)
    return arg


# ── Scraper ────────────────────────────────────────────────────────────────────


class FAOFIRMSScraper:
    """
    Scraper de datos FAO FIRMS para contexto internacional.

    Carga datos semilla verificados y puede enriquecer con la API pública
    de FAO FIRMS.  Los datos de captura provienen de FAO FishStat.
    """

    def __init__(
        self,
        db_path: Path | str = "data/processed/catalog.db",
        delay: float = 1.5,
    ):
        self.db_path = Path(db_path)
        self.delay = delay
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "CFP-Audit-Research/1.0 (github.com/arielgiamportone/cfp-audit-intelligence)"
                ),
                "Accept": "application/json",
            }
        )

    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_schema(self) -> None:
        """Crea las tablas FAO si no existen."""
        with self._conn() as conn:
            conn.executescript(SCHEMA_FAO)
        logger.debug("Schema FAO inicializado")

    def seed_data(self) -> tuple[int, int]:
        """
        Carga los datos semilla verificados de capturas y estados de stock.

        Returns:
            Tupla (n_capturas_insertadas, n_status_insertados)
        """
        self.init_schema()

        with self._conn() as conn:
            capturas_existentes = conn.execute("SELECT COUNT(*) FROM fao_capturas").fetchone()[0]
            status_existentes = conn.execute("SELECT COUNT(*) FROM fao_stock_status").fetchone()[0]

            n_capturas = 0
            if capturas_existentes == 0:
                for rec in SEED_DATA_CAPTURAS:
                    conn.execute(
                        """INSERT INTO fao_capturas
                           (especie, especie_fao_code, zona_fao, pais, year,
                            captura_tn, fuente, fuente_url, notas)
                           VALUES (:especie, :especie_fao_code, :zona_fao, :pais, :year,
                                   :captura_tn, :fuente, :fuente_url, :notas)""",
                        {
                            "especie": rec["especie"],
                            "especie_fao_code": rec["especie_fao_code"],
                            "zona_fao": rec.get("zona_fao", FAO_AREA_41),
                            "pais": rec.get("pais", "Total"),
                            "year": rec["year"],
                            "captura_tn": rec.get("captura_tn"),
                            "fuente": rec.get("fuente", "FAO FishStat"),
                            "fuente_url": rec.get("fuente_url"),
                            "notas": rec.get("notas"),
                        },
                    )
                    n_capturas += 1
                conn.commit()
                logger.info(f"FAO capturas seed: {n_capturas} registros")

            n_status = 0
            if status_existentes == 0:
                for rec in SEED_STOCK_STATUS:
                    conn.execute(
                        """INSERT INTO fao_stock_status
                           (especie, especie_fao_code, firms_resource, zona_fao,
                            estado_stock, estado_stock_desc, tendencia,
                            year_evaluacion, fuente, fuente_url, notas)
                           VALUES (:especie, :especie_fao_code, :firms_resource, :zona_fao,
                                   :estado_stock, :estado_stock_desc, :tendencia,
                                   :year_evaluacion, :fuente, :fuente_url, :notas)""",
                        {
                            "especie": rec["especie"],
                            "especie_fao_code": rec["especie_fao_code"],
                            "firms_resource": rec.get("firms_resource"),
                            "zona_fao": rec.get("zona_fao", FAO_AREA_41),
                            "estado_stock": rec["estado_stock"],
                            "estado_stock_desc": rec["estado_stock_desc"],
                            "tendencia": rec.get("tendencia"),
                            "year_evaluacion": rec.get("year_evaluacion"),
                            "fuente": rec.get("fuente", "FAO FIRMS"),
                            "fuente_url": rec.get("fuente_url"),
                            "notas": rec.get("notas"),
                        },
                    )
                    n_status += 1
                conn.commit()
                logger.info(f"FAO stock status seed: {n_status} registros")

        return n_capturas, n_status

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
    def _get_json(self, url: str, params: dict | None = None) -> dict:
        time.sleep(self.delay)
        resp = self.session.get(url, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def fetch_firms_resource(self, firms_code: str) -> dict | None:
        """
        Consulta la API FAO FIRMS para un recurso específico.

        Args:
            firms_code: Código FIRMS, ej. "ATLSO_HKP"

        Returns:
            Dict con datos del recurso, o None si falla
        """
        url = f"{FAO_FIRMS_API}/resource/{firms_code}"
        try:
            return self._get_json(url, params={"lang": "en", "format": "json"})
        except Exception as e:
            logger.warning(f"FIRMS API no disponible para {firms_code}: {e}")
            return None

    def fetch_all_resources(self) -> list[dict]:
        """
        Descarga todos los recursos del Área FAO 41 disponibles en FIRMS.

        Returns:
            Lista de recursos (stocks) del Atlántico Sudoccidental
        """
        url = f"{FAO_FIRMS_API}/resource"
        try:
            data = self._get_json(
                url,
                params={
                    "collection": "resource",
                    "lang": "en",
                    "format": "json",
                    "waterarea": FAO_AREA_41,
                },
            )
            resources = data.get("data", data.get("resources", []))
            logger.info(f"FAO FIRMS: {len(resources)} recursos encontrados en Área 41")
            return resources
        except Exception as e:
            logger.warning(f"Error al consultar FAO FIRMS API: {e}. Usando datos seed.")
            return []

    def get_capturas_df(self) -> "pd.DataFrame":
        """Retorna las capturas FAO como DataFrame."""
        import pandas as pd

        if not self.db_path.exists():
            return pd.DataFrame()
        with self._conn() as conn:
            return pd.read_sql_query(
                "SELECT * FROM fao_capturas ORDER BY especie_fao_code, year",
                conn,
            )

    def get_stock_status_df(self) -> "pd.DataFrame":
        """Retorna los estados de stock como DataFrame."""
        import pandas as pd

        if not self.db_path.exists():
            return pd.DataFrame()
        with self._conn() as conn:
            return pd.read_sql_query(
                "SELECT * FROM fao_stock_status ORDER BY especie_fao_code",
                conn,
            )

    def get_contexto_especie(self, especie_fao_code: str, year: int | None = None) -> dict:
        """
        Retorna el contexto internacional completo para una especie.

        Args:
            especie_fao_code: Código FAO 3-alpha (ej. "HKP")
            year: Año específico, o último disponible si None

        Returns:
            Dict con capturas Argentina, total área, share%, estado stock
        """
        if not self.db_path.exists():
            return {}

        with self._conn() as conn:
            q_year = "AND year = ?" if year else "ORDER BY year DESC LIMIT 1"
            params_year = [year] if year else []

            arg_row = conn.execute(
                f"""SELECT captura_tn, year FROM fao_capturas
                    WHERE especie_fao_code = ? AND pais = 'Argentina'
                    {q_year}""",
                [especie_fao_code] + params_year,
            ).fetchone()

            total_row = conn.execute(
                f"""SELECT captura_tn, year FROM fao_capturas
                    WHERE especie_fao_code = ? AND pais = 'Total'
                    {q_year}""",
                [especie_fao_code] + params_year,
            ).fetchone()

            status_row = conn.execute(
                """SELECT estado_stock, estado_stock_desc, tendencia,
                          year_evaluacion, notas, fuente_url
                   FROM fao_stock_status
                   WHERE especie_fao_code = ?
                   ORDER BY year_evaluacion DESC LIMIT 1""",
                [especie_fao_code],
            ).fetchone()

        captura_arg = arg_row["captura_tn"] if arg_row else None
        captura_total = total_row["captura_tn"] if total_row else None
        share_pct = (
            round(captura_arg / captura_total * 100, 1)
            if captura_arg and captura_total and captura_total > 0
            else None
        )

        return {
            "especie_fao_code": especie_fao_code,
            "year": arg_row["year"] if arg_row else None,
            "captura_argentina_tn": captura_arg,
            "captura_total_area41_tn": captura_total,
            "share_argentina_pct": share_pct,
            "estado_stock": status_row["estado_stock"] if status_row else None,
            "estado_stock_desc": status_row["estado_stock_desc"] if status_row else None,
            "tendencia": status_row["tendencia"] if status_row else None,
            "notas": status_row["notas"] if status_row else None,
        }
