"""
Cliente WMS del geoportal marino CONAE — 4° vértice del triángulo de auditoría.

Consulta capas satelitales del Mar Argentino vía WMS GetFeatureInfo:
  - Esfuerzo pesquero GFW AIS   (Pesca:GFW_AIS_EPA_1..8)
  - SST diurna/nocturna VIIRS   (Pesca:SNPP_VIIRS_SST_1..8 / NSST)
  - Clorofila-a VIIRS           (Pesca:SNPP_VIIRS_CHLA_1..8 / CHLA8D)
  - Luces nocturnas VIIRS DNB   (Pesca:SNPP_VIIRS_LN_1..8)

Permite verificar si el esfuerzo pesquero real disminuye durante períodos de veda
— evidencia satelital independiente del pipeline de actas CFP (ADR-010).

Limitación: el WMS sirve composites recientes (rolling window de ~8 períodos).
La consulta histórica no está disponible. Ejecutar periódicamente para
acumular serie temporal.

WMS base: https://geoservicios2.conae.gov.ar/geoserver/AplicacionesMarinas/wms
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import requests
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

CONAE_WMS_BASE = "https://geoservicios2.conae.gov.ar/geoserver/AplicacionesMarinas/wms"

# Sub-tiles geográficos 1-8 que cubren la ZEE argentina
_N_TILES = 8

LAYER_GFW_AIS = "Pesca:GFW_AIS_EPA"
LAYER_SST = "Pesca:SNPP_VIIRS_SST"
LAYER_SST_NOCHE = "Pesca:SNPP_VIIRS_NSST"
LAYER_CHLA = "Pesca:SNPP_VIIRS_CHLA"
LAYER_CHLA_8D = "Pesca:SNPP_VIIRS_CHLA8D"
LAYER_LUCES = "Pesca:SNPP_VIIRS_LN"

# Zonas de muestreo: centroides representativos de las principales pesquerías.
# Elegidos por presencia documentada de vedas en vedas_geoespaciales y
# relevancia histórica (Bertolotti et al. 2001, INIDEP Informes Técnicos).
ZONAS_MUESTRA: list[dict] = [
    {
        "zona": "golfo_san_jorge_norte",
        "especie_code": "merluza_hubbsi",
        "lat": -44.5,
        "lon": -65.0,
    },
    {
        "zona": "plataforma_bonaerense",
        "especie_code": "merluza_hubbsi",
        "lat": -39.0,
        "lon": -57.0,
    },
    {
        "zona": "rawson_offshore",
        "especie_code": "langostino",
        "lat": -43.2,
        "lon": -63.5,
    },
    {
        "zona": "golfo_nuevo",
        "especie_code": "centolla",
        "lat": -42.7,
        "lon": -64.0,
    },
    {
        "zona": "sur_atlantico",
        "especie_code": "merluza_negra",
        "lat": -51.5,
        "lon": -60.0,
    },
    {
        "zona": "offshore_chubut",
        "especie_code": "vieira",
        "lat": -46.0,
        "lon": -62.0,
    },
]

# ── Schema ─────────────────────────────────────────────────────────────────────

SCHEMA_ESFUERZO_SATELITAL = """
CREATE TABLE IF NOT EXISTS esfuerzo_satelital (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    zona         TEXT NOT NULL,
    especie_code TEXT,
    fecha        TEXT NOT NULL,
    lon          REAL NOT NULL,
    lat          REAL NOT NULL,
    sst          REAL,
    sst_noche    REAL,
    clorofila    REAL,
    clorofila_8d REAL,
    esfuerzo_gfw REAL,
    luces_noche  REAL,
    fuente       TEXT DEFAULT 'CONAE geoportal (WMS GetFeatureInfo)',
    created_at   TEXT DEFAULT (datetime('now')),
    UNIQUE(zona, fecha)
);
CREATE INDEX IF NOT EXISTS idx_esfuerzo_zona_fecha
    ON esfuerzo_satelital(zona, fecha);
CREATE INDEX IF NOT EXISTS idx_esfuerzo_especie_fecha
    ON esfuerzo_satelital(especie_code, fecha);
"""


# ── Modelo de datos ───────────────────────────────────────────────────────────


@dataclass
class EsfuerzoSatelital:
    """Observación satelital puntual para una zona y fecha."""

    zona: str
    especie_code: str | None
    fecha: str
    lon: float
    lat: float
    sst: float | None = None
    sst_noche: float | None = None
    clorofila: float | None = None
    clorofila_8d: float | None = None
    esfuerzo_gfw: float | None = None
    luces_noche: float | None = None


# ── Helpers ───────────────────────────────────────────────────────────────────


def _parse_raster_value(data: dict) -> float | None:
    """Extrae el valor numérico del JSON de GetFeatureInfo de GeoServer."""
    features = data.get("features", [])
    if not features:
        return None
    props = features[0].get("properties") or {}
    for key in ("GRAY_INDEX", "gray_index", "value", "Value", "DN", "dn", "band1", "Band1"):
        val = props.get(key)
        if val is not None:
            try:
                f = float(val)
                if f < -9000:  # NoData típico en rasters GeoServer
                    return None
                return f
            except (ValueError, TypeError):
                pass
    return None


def _bbox(lon: float, lat: float, delta: float = 0.1) -> str:
    """BBOX de 0.2° × 0.2° centrado en (lon, lat) para WMS 1.1.1."""
    return f"{lon - delta},{lat - delta},{lon + delta},{lat + delta}"


# ── Cliente WMS ───────────────────────────────────────────────────────────────


class CONAEMarineClient:
    """Cliente de solo lectura para el WMS de aplicaciones marinas del geoportal CONAE."""

    def __init__(
        self,
        base_url: str = CONAE_WMS_BASE,
        delay: float = 0.5,
        timeout: int = 30,
    ) -> None:
        self.base_url = base_url
        self.delay = delay
        self.timeout = timeout
        self._session = requests.Session()
        self._session.headers.update(
            {
                "User-Agent": (
                    "CFP-Audit-Research/1.0 (github.com/arielgiamportone/cfp-audit-intelligence)"
                )
            }
        )

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
    def _get_feature_info(self, layer_name: str, lon: float, lat: float) -> float | None:
        """
        GetFeatureInfo para un punto geográfico sobre una capa WMS.

        Crea un BBOX de 0.2°×0.2° alrededor del punto y consulta el píxel central.
        Retorna `None` si el píxel es NoData o la capa no cubre el punto.
        """
        time.sleep(self.delay)
        params = {
            "SERVICE": "WMS",
            "VERSION": "1.1.1",
            "REQUEST": "GetFeatureInfo",
            "LAYERS": layer_name,
            "QUERY_LAYERS": layer_name,
            "STYLES": "",
            "BBOX": _bbox(lon, lat),
            "WIDTH": 11,
            "HEIGHT": 11,
            "SRS": "EPSG:4326",
            "X": 5,
            "Y": 5,
            "INFO_FORMAT": "application/json",
            "FEATURE_COUNT": 1,
        }
        resp = self._session.get(self.base_url, params=params, timeout=self.timeout)
        resp.raise_for_status()
        return _parse_raster_value(resp.json())

    def _sample_layer_group(self, layer_prefix: str, lon: float, lat: float) -> float | None:
        """
        Prueba sub-tiles _1..8 en orden hasta obtener un valor no nulo.

        El geoportal CONAE divide la ZEE en 8 sub-tiles geográficos. No se conoce
        la asignación exacta de tile a área, por lo que se intentan todos.
        """
        for i in range(1, _N_TILES + 1):
            layer = f"{layer_prefix}_{i}"
            try:
                val = self._get_feature_info(layer, lon, lat)
                if val is not None:
                    return val
            except Exception as exc:
                logger.debug(f"Tile {layer} en ({lon},{lat}) no disponible: {exc}")
        return None

    def sample_point(
        self,
        zona: str,
        lon: float,
        lat: float,
        especie_code: str | None = None,
        fecha: str | None = None,
    ) -> EsfuerzoSatelital:
        """
        Muestrea todas las capas CONAE en un punto geográfico.

        Args:
            zona: Nombre de la zona (ej. 'golfo_san_jorge_norte').
            lon: Longitud decimal (negativo = Oeste).
            lat: Latitud decimal (negativo = Sur).
            especie_code: Código de especie asociado a la zona.
            fecha: Fecha de muestreo (ISO YYYY-MM-DD). Por defecto: hoy.

        Returns:
            EsfuerzoSatelital con todos los campos disponibles.
        """
        if fecha is None:
            fecha = date.today().isoformat()

        logger.info(f"Muestreando CONAE: zona={zona} ({lat},{lon}) fecha={fecha}")

        return EsfuerzoSatelital(
            zona=zona,
            especie_code=especie_code,
            fecha=fecha,
            lon=lon,
            lat=lat,
            sst=self._sample_layer_group(LAYER_SST, lon, lat),
            sst_noche=self._sample_layer_group(LAYER_SST_NOCHE, lon, lat),
            clorofila=self._sample_layer_group(LAYER_CHLA, lon, lat),
            clorofila_8d=self._sample_layer_group(LAYER_CHLA_8D, lon, lat),
            esfuerzo_gfw=self._sample_layer_group(LAYER_GFW_AIS, lon, lat),
            luces_noche=self._sample_layer_group(LAYER_LUCES, lon, lat),
        )

    def scrape_and_save(self, db_path: Path | str) -> int:
        """
        Muestrea todas las zonas de ZONAS_MUESTRA con la fecha de hoy y persiste en DB.

        Diseñado para ejecución periódica (semanal/mensual) que acumula serie temporal.

        Returns:
            Número de filas nuevas insertadas.
        """
        db_path = Path(db_path)
        records: list[EsfuerzoSatelital] = []
        hoy = date.today().isoformat()

        for zona_info in ZONAS_MUESTRA:
            try:
                rec = self.sample_point(
                    zona=zona_info["zona"],
                    lon=zona_info["lon"],
                    lat=zona_info["lat"],
                    especie_code=zona_info.get("especie_code"),
                    fecha=hoy,
                )
                records.append(rec)
            except Exception as exc:
                logger.warning(f"Error muestreando zona {zona_info['zona']}: {exc}")

        n = save_esfuerzo_to_db(records, db_path)
        logger.success(f"CONAE scrape completado: {n} registros nuevos en {db_path}")
        return n


# ── Persistencia ──────────────────────────────────────────────────────────────


def save_esfuerzo_to_db(records: list[EsfuerzoSatelital], db_path: Path | str) -> int:
    """
    Persiste observaciones satelitales CONAE en `esfuerzo_satelital`.

    Idempotente: usa INSERT OR IGNORE sobre (zona, fecha). Retorna filas nuevas.
    """
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    inserted = 0
    with sqlite3.connect(db_path) as conn:
        conn.executescript(SCHEMA_ESFUERZO_SATELITAL)
        for rec in records:
            conn.execute(
                """
                INSERT OR IGNORE INTO esfuerzo_satelital
                    (zona, especie_code, fecha, lon, lat,
                     sst, sst_noche, clorofila, clorofila_8d,
                     esfuerzo_gfw, luces_noche)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rec.zona,
                    rec.especie_code,
                    rec.fecha,
                    rec.lon,
                    rec.lat,
                    rec.sst,
                    rec.sst_noche,
                    rec.clorofila,
                    rec.clorofila_8d,
                    rec.esfuerzo_gfw,
                    rec.luces_noche,
                ),
            )
            if conn.execute("SELECT changes()").fetchone()[0]:
                inserted += 1

    logger.info(f"save_esfuerzo_to_db: {inserted} filas nuevas en {db_path}")
    return inserted


def get_esfuerzo_df(db_path: Path | str, zona: str | None = None):  # -> pd.DataFrame
    """Retorna DataFrame de observaciones satelitales. Vacío si no hay datos."""
    try:
        import pandas as pd
    except ImportError:
        return None  # type: ignore[return-value]

    db_path = Path(db_path)
    if not db_path.exists():
        return pd.DataFrame()

    with sqlite3.connect(db_path) as conn:
        try:
            conn.executescript(SCHEMA_ESFUERZO_SATELITAL)
        except Exception:
            pass
        query = "SELECT * FROM esfuerzo_satelital"
        params: tuple = ()
        if zona:
            query += " WHERE zona = ?"
            params = (zona,)
        query += " ORDER BY zona, fecha"
        try:
            import pandas as pd

            return pd.read_sql_query(query, conn, params=params)
        except Exception:
            return pd.DataFrame()
