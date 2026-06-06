"""
Cliente WFS del geovisor SERE del INIDEP — geoservicios públicos GeoServer.

SERE ("Visualizador de especies", sere.inidep.edu.ar) expone vía OGC WFS estándar
~195 capas de distribución de especies (ocurrencias georreferenciadas desde ~1982)
y capas de vedas geoespaciales que citan directamente número de resolución y link
al PDF oficial (CFP/CTMFM). Ver docs/adr/009-geovisor-sere-inidep.md para el diseño
completo y el estado de la integración.

WFS base: https://sere.inidep.edu.ar/geoserver/ows
"""

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

import requests
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

WFS_BASE = "https://sere.inidep.edu.ar/geoserver/ows"

# Capas de veda 2024 relevantes para las especies ya verificadas en el comparador
# (README: merluza, centolla, abadejo, polaca, langostino, calamar illex, merluza negra)
VEDAS_LAYERS: list[str] = [
    "vedas_2024:Merluza_Hubbsi_invierno",
    "vedas_2024:Merluza_Hubbsi_otonio",
    "vedas_2024:Merluza_Hubbsi_primavera",
    "vedas_2024:Merluza_Hubbsi_verano",
    "vedas_2024:merluza_hubbsi_veda_permanente",
    "vedas_2024:merluza_negra_veda",
    "vedas_2024:centolla",
    "vedas_2024:areas_centolla",
    "vedas_2024:langostino_veda_arrastre",
    "vedas_2024:Langostino_subareas",
    "vedas_2024:abadejo_pozos",
    "vedas_2024:Vieira_Vedas_Areas_cerradas_2024",
    "vedas_2024:Vieira_Unidad_Manejo",
    "vedas_2024:rincon_veda_demersales_costeros",
    "vedas_2024:Veda_arrastre_28m_eslora",
    "vedas_2024:Veda_arrastre_fondo_proteccion_de_condrictios",
]

# Mapeo a especie_code consistente con inidep_scraper._normalize_especie
_ESPECIE_CODE_MAP = {
    "merluza_hubbsi": "merluza_hubbsi",
    "merluza_negra": "merluza_negra",
    "centolla": "centolla",
    "langostino": "langostino",
    "abadejo": "abadejo",
    "vieira": "vieira",
}


@dataclass
class VedaGeoespacial:
    """Zona de veda georreferenciada citada por el geovisor SERE del INIDEP."""

    capa: str
    especie: str | None = None
    area: str | None = None
    fecha_inicio: str | None = None
    fecha_fin: str | None = None
    resolucion_numero: str | None = None
    resolucion_fuente: str | None = None
    resolucion_url: str | None = None
    notas: str | None = None
    geometry_type: str | None = None


def _clean_date(raw: str | None) -> str | None:
    """Normaliza '2024-07-01Z' → '2024-07-01'."""
    if not raw:
        return None
    return raw.rstrip("Z")


def _especie_code(especie: str | None) -> str | None:
    """Normaliza 'Merluza_Hubbsi' / 'Centolla' → especie_code consistente con inidep_scraper."""
    if not especie:
        return None
    key = especie.lower().strip()
    for needle, code in _ESPECIE_CODE_MAP.items():
        if needle.replace("_", " ") in key.replace("_", " "):
            return code
    return key.replace(" ", "_")


class SEREGeovisorClient:
    """Cliente de solo lectura para los servicios WFS del geovisor SERE (INIDEP/GeoServer)."""

    def __init__(self, delay: float = 0.5, timeout: int = 30):
        self.delay = delay
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "CFP-Audit-Research/1.0 (github.com/arielgiamportone/cfp-audit-intelligence)",
                "Accept": "application/json",
            }
        )

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
    def _get_features(self, type_name: str, count: int | None = None) -> dict:
        time.sleep(self.delay)
        params = {
            "service": "WFS",
            "version": "2.0.0",
            "request": "GetFeature",
            "typeName": type_name,
            "outputFormat": "application/json",
        }
        if count:
            params["count"] = count
        resp = self.session.get(WFS_BASE, params=params, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def fetch_veda_layer(self, type_name: str) -> list[VedaGeoespacial]:
        """Descarga y normaliza una capa de veda geoespacial a `VedaGeoespacial`."""
        data = self._get_features(type_name)
        out = []
        for feat in data.get("features", []):
            props = feat.get("properties", {}) or {}
            geom = feat.get("geometry") or {}
            out.append(
                VedaGeoespacial(
                    capa=type_name,
                    especie=props.get("Especie") or props.get("especie"),
                    area=props.get("nam_area") or props.get("Id_area") or props.get("area"),
                    fecha_inicio=_clean_date(props.get("Inicio")),
                    fecha_fin=_clean_date(props.get("Fin")),
                    resolucion_numero=props.get("Resolucion") or props.get("No_Resol"),
                    resolucion_fuente=props.get("Fuente"),
                    resolucion_url=props.get("Link_res") or props.get("Res_link"),
                    notas=props.get("Notas") or props.get("Nota"),
                    geometry_type=geom.get("type"),
                )
            )
        return out

    def fetch_especie_distribucion(
        self, type_name: str, max_features: int | None = None
    ) -> list[dict]:
        """Descarga ocurrencias georreferenciadas de una especie: especie, año, lat/lon."""
        data = self._get_features(type_name, count=max_features)
        out = []
        for feat in data.get("features", []):
            props = feat.get("properties", {}) or {}
            coords = (feat.get("geometry") or {}).get("coordinates") or [None, None]
            out.append(
                {
                    "especie": props.get("especie"),
                    "nom_comun": props.get("nom_comun"),
                    "anio": props.get("anio"),
                    "lon": coords[0],
                    "lat": coords[1],
                }
            )
        return out

    def scrape_all_vedas(self) -> list[VedaGeoespacial]:
        """Descarga todas las capas de veda 2024 relevantes (`VEDAS_LAYERS`)."""
        out: list[VedaGeoespacial] = []
        for layer in VEDAS_LAYERS:
            try:
                out.extend(self.fetch_veda_layer(layer))
            except requests.RequestException as exc:
                logger.warning(f"No se pudo descargar capa de veda {layer}: {exc}")
        logger.info(
            f"scrape_all_vedas: {len(out)} zonas de veda descargadas de {len(VEDAS_LAYERS)} capas"
        )
        return out

    def scrape_and_save_vedas(self, db_path: str | Path) -> int:
        """Descarga todas las capas de veda y las persiste en `vedas_geoespaciales`.

        Returns:
            Número de filas nuevas insertadas.
        """
        logger.info(f"Iniciando scraping de vedas geoespaciales SERE → {db_path}")
        records = self.scrape_all_vedas()
        n = save_vedas_to_db(records, db_path)
        logger.success(f"scrape_and_save_vedas completo: {n} registros nuevos en DB")
        return n


# ── Persistencia ──────────────────────────────────────────────────────────────

SCHEMA_VEDAS_GEO = """
CREATE TABLE IF NOT EXISTS vedas_geoespaciales (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    capa                TEXT NOT NULL,
    especie             TEXT,
    especie_code        TEXT,
    area                TEXT,
    fecha_inicio        TEXT,
    fecha_fin           TEXT,
    resolucion_numero   TEXT,
    resolucion_fuente   TEXT,
    resolucion_url      TEXT,
    notas               TEXT,
    geometry_type       TEXT,
    fuente              TEXT DEFAULT 'INIDEP SERE geovisor',
    created_at          TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_vedas_geo_especie     ON vedas_geoespaciales(especie_code);
CREATE INDEX IF NOT EXISTS idx_vedas_geo_resolucion  ON vedas_geoespaciales(resolucion_numero);
"""


def save_vedas_to_db(records: list[VedaGeoespacial], db_path: str | Path) -> int:
    """
    Persiste zonas de veda geoespaciales en `vedas_geoespaciales`.

    Evita duplicados por (capa, area, resolucion_numero). Retorna el número de filas nuevas.
    """
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    inserted = 0
    with sqlite3.connect(db_path) as conn:
        conn.executescript(SCHEMA_VEDAS_GEO)
        for rec in records:
            exists = conn.execute(
                """
                SELECT 1 FROM vedas_geoespaciales
                WHERE capa = ?
                  AND COALESCE(area, '') = COALESCE(?, '')
                  AND COALESCE(resolucion_numero, '') = COALESCE(?, '')
                """,
                (rec.capa, rec.area, rec.resolucion_numero),
            ).fetchone()
            if exists:
                continue

            conn.execute(
                """
                INSERT INTO vedas_geoespaciales
                    (capa, especie, especie_code, area, fecha_inicio, fecha_fin,
                     resolucion_numero, resolucion_fuente, resolucion_url, notas, geometry_type)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rec.capa,
                    rec.especie,
                    _especie_code(rec.especie),
                    rec.area,
                    rec.fecha_inicio,
                    rec.fecha_fin,
                    rec.resolucion_numero,
                    rec.resolucion_fuente,
                    rec.resolucion_url,
                    rec.notas,
                    rec.geometry_type,
                ),
            )
            inserted += 1

    logger.info(f"save_vedas_to_db: {inserted} filas nuevas en {db_path}")
    return inserted


def resoluciones_citadas(db_path: str | Path) -> list[dict]:
    """
    Lista única de (resolucion_numero, fuente, url) citados por el geovisor.

    Es el insumo de validación para `GeovisorCrossValidator` (ADR-009): cuando el
    pipeline real cargue las actas correspondientes, se podrá comprobar qué fracción
    de estas resoluciones aparece en `resoluciones.numero`.
    """
    db_path = Path(db_path)
    if not db_path.exists():
        return []
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT DISTINCT resolucion_numero, resolucion_fuente, resolucion_url
            FROM vedas_geoespaciales
            WHERE resolucion_numero IS NOT NULL
            ORDER BY resolucion_numero
            """
        ).fetchall()
        return [dict(r) for r in rows]
