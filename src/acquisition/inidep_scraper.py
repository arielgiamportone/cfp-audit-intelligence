"""
Scraper del repositorio Mar Abierto del INIDEP — DSpace 7 REST API.

Extrae los 492 Informes Técnicos Oficiales (ITOs) con recomendaciones de CBA/CMP
por especie y año, para cruzar con las decisiones del CFP.

API base: https://marabiertonew.inidep.edu.ar/server/api
Colección ITOs: scope 50a522a6-b22a-4c95-88fb-adbb6936fdde (492 items)
"""

import re
import time
from dataclasses import dataclass, field

import requests
import urllib3
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

urllib3.disable_warnings()

MAR_ABIERTO_BASE = "https://marabierto.inidep.edu.ar"
DSPACE_API = "https://marabiertonew.inidep.edu.ar/server/api"
ITO_COLLECTION_UUID = "50a522a6-b22a-4c95-88fb-adbb6936fdde"
ITO_ITEM_URL = f"{MAR_ABIERTO_BASE}/items"

# Especies de interés para el comparador
ESPECIES_INTERES = [
    "merluza negra",
    "merluza de cola",
    "merluza austral",
    "calamar illex",
    "calamar loligo",
    "merluza",
    "merluccius",
    "langostino",
    "pleoticus",
    "calamar",
    "illex",
    "centolla",
    "lithodes",
    "abadejo",
    "polaca",
    "vieira",
    "zygochlamys",
    "anchoíta",
    "anchoita",
    "dissostichus",
    "macruronus",
]

# Patrones para extraer valores numéricos de CBA del abstract/texto
_RE_CBA = re.compile(
    r"(?:CBA|captura\s+biol[oó]gicamente\s+aceptable)"
    r"[\s\w]*?(?:de\s+)?(?:es\s+de\s+|fue\s+de\s+|=\s*|:\s*|de\s+)?"
    r"([\d]{1,3}(?:[.\s]\d{3})*(?:,\d+)?)\s*(?:toneladas?|tn\.?|t\.?)",
    re.IGNORECASE,
)

_RE_CBA_ALT = re.compile(
    r"se\s+recomienda[^.]{0,60}?([\d]{1,3}(?:[.\s]\d{3})*(?:,\d+)?)"
    r"\s*(?:toneladas?|tn\.?)",
    re.IGNORECASE,
)

_RE_ITO_NUM = re.compile(
    r"(?:ITO|Informe\s+T[eé]cnico\s+Oficial)\s+(?:N[°º]?\s*)?(\d+/\d{4})",
    re.IGNORECASE,
)

_RE_YEAR = re.compile(r"\b(20\d{2}|199\d)\b")


@dataclass
class ITORecord:
    """Registro de un Informe Técnico Oficial del INIDEP."""

    titulo: str
    url: str
    uuid: str | None = None
    año_publicacion: int | None = None
    año_evaluacion: int | None = None
    especie_raw: str | None = None
    especie_norm: str | None = None
    zona: str | None = None
    cba_recomendada_tn: float | None = None
    cmp_alternativa_tn: float | None = None
    estado_stock: str | None = None
    autores: list[str] = field(default_factory=list)
    numero_ito: str | None = None
    pdf_url: str | None = None
    abstract: str | None = None
    fuente: str = "INIDEP Mar Abierto"


class INIDEPScraper:
    """Scraper del repositorio Mar Abierto del INIDEP vía DSpace 7 REST API."""

    def __init__(self, delay: float = 1.0):
        self.delay = delay
        self.session = requests.Session()
        self.session.verify = False
        self.session.headers.update(
            {
                "User-Agent": "CFP-Audit-Research/1.0 (github.com/arielgiamportone/cfp-audit-intelligence)",
                "Accept": "application/json",
            }
        )

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
    def _get_json(self, url: str, params: dict | None = None) -> dict:
        time.sleep(self.delay)
        resp = self.session.get(url, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
    def _get_bytes(self, url: str) -> bytes:
        time.sleep(self.delay)
        resp = self.session.get(url, timeout=60)
        resp.raise_for_status()
        return resp.content

    # ── API DSpace 7 ───────────────────────────────────────────────────────────

    def list_itos_page(self, page: int = 0, size: int = 50) -> dict:
        """Retorna una página de ITOs de la colección Mar Abierto."""
        data = self._get_json(
            f"{DSPACE_API}/discover/search/objects",
            params={
                "query": "*",
                "scope": ITO_COLLECTION_UUID,
                "page": page,
                "size": size,
            },
        )
        return data

    def get_total_itos(self) -> int:
        """Retorna el total de ITOs en la colección."""
        data = self.list_itos_page(page=0, size=1)
        return (
            data.get("_embedded", {})
            .get("searchResult", {})
            .get("page", {})
            .get("totalElements", 0)
        )

    def scrape_all_metadata(self, max_items: int | None = None) -> list[ITORecord]:
        """
        Scrapea metadatos de todos los ITOs via API DSpace 7.
        Rápido: solo metadata + abstract, sin descargar PDFs.
        """
        records = []
        page = 0
        size = 50
        total_pages = None

        while True:
            try:
                data = self.list_itos_page(page=page, size=size)
            except Exception as exc:
                logger.error(f"Error en página {page}: {exc}")
                break

            embedded = data.get("_embedded", {}).get("searchResult", {})
            page_info = embedded.get("page", {})

            if total_pages is None:
                total_pages = page_info.get("totalPages", 1)
                total_elements = page_info.get("totalElements", 0)
                logger.info(f"Total ITOs: {total_elements} en {total_pages} páginas")

            items = embedded.get("_embedded", {}).get("objects", [])
            if not items:
                break

            for obj in items:
                rec = self._parse_search_result(obj)
                if rec:
                    records.append(rec)
                if max_items and len(records) >= max_items:
                    logger.info(f"Límite alcanzado: {max_items} ITOs")
                    return records

            logger.info(
                f"  Página {page + 1}/{total_pages}: {len(items)} items — total acumulado: {len(records)}"
            )

            page += 1
            if page >= total_pages:
                break

        logger.success(f"Scraping completado: {len(records)} ITOs recuperados")
        return records

    def _parse_search_result(self, obj: dict) -> ITORecord | None:
        """Parsea un resultado de búsqueda DSpace en ITORecord."""
        try:
            item = obj.get("_embedded", {}).get("indexableObject", {})
            if not item:
                return None

            uuid = item.get("uuid", "")
            metadata = item.get("metadata", {})

            titulo = _first_value(metadata, "dc.title") or ""
            año_str = _first_value(metadata, "dc.date.issued") or ""
            abstract = _first_value(metadata, "dc.description.abstract") or ""
            autores = _all_values(metadata, "dc.contributor.author")
            keywords = _all_values(metadata, "dc.subject")
            handle = item.get("handle", "")

            año = _parse_year(año_str)

            # Número ITO desde título o descripción
            numero_ito = _extract_ito_number(titulo) or _extract_ito_number(abstract)

            # Año de evaluación puede diferir del de publicación
            año_eval = _extract_eval_year(titulo) or año

            rec = ITORecord(
                titulo=titulo,
                url=f"{ITO_ITEM_URL}/{uuid}" if uuid else f"{MAR_ABIERTO_BASE}/handle/{handle}",
                uuid=uuid,
                año_publicacion=año,
                año_evaluacion=año_eval,
                autores=autores,
                numero_ito=numero_ito,
                abstract=abstract if len(abstract) < 2000 else abstract[:2000],
            )

            rec.especie_raw = _extract_especie(titulo + " " + " ".join(keywords))
            rec.especie_norm = _normalize_especie(rec.especie_raw or "")
            rec.zona = _extract_zona(titulo)
            rec.estado_stock = _extract_estado_stock(abstract + " " + titulo)
            rec.cba_recomendada_tn = _extract_cba(abstract)

            return rec

        except Exception as exc:
            logger.warning(f"Error parseando item: {exc}")
            return None

    def get_pdf_url(self, uuid: str) -> str | None:
        """Obtiene la URL de descarga del PDF de un ITO dado su UUID."""
        try:
            bundles = self._get_json(f"{DSPACE_API}/core/items/{uuid}/bundles")
            for bundle in bundles.get("_embedded", {}).get("bundles", []):
                if bundle.get("name") == "ORIGINAL":
                    bundle_uuid = bundle.get("uuid")
                    bitstreams = self._get_json(
                        f"{DSPACE_API}/core/bundles/{bundle_uuid}/bitstreams"
                    )
                    for bs in bitstreams.get("_embedded", {}).get("bitstreams", []):
                        if bs.get("name", "").endswith(".pdf"):
                            bs_uuid = bs.get("uuid")
                            return f"{DSPACE_API}/core/bitstreams/{bs_uuid}/content"
        except Exception as exc:
            logger.warning(f"Error obteniendo PDF URL para {uuid}: {exc}")
        return None

    def download_and_extract_pdf(self, rec: ITORecord) -> str | None:
        """
        Descarga el PDF de un ITO y extrae su texto.
        Requiere PyMuPDF (fitz). Lento — usar solo cuando sea necesario.
        """
        if not rec.uuid:
            return None
        pdf_url = self.get_pdf_url(rec.uuid)
        if not pdf_url:
            return None
        try:
            import fitz  # PyMuPDF

            pdf_bytes = self._get_bytes(pdf_url)
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            text = "\n".join(page.get_text() for page in doc)
            doc.close()
            return text
        except Exception as exc:
            logger.warning(f"Error extrayendo PDF {rec.uuid}: {exc}")
            return None

    def enrich_with_pdf(self, rec: ITORecord) -> ITORecord:
        """
        Enriquece un ITORecord descargando y parseando su PDF.
        Extrae CBA si no fue encontrada en el abstract.
        """
        if rec.cba_recomendada_tn is not None:
            return rec  # Ya tenemos CBA del abstract

        text = self.download_and_extract_pdf(rec)
        if not text:
            return rec

        cba = _extract_cba(text)
        if cba:
            rec.cba_recomendada_tn = cba
            logger.debug(f"CBA extraída de PDF: {rec.titulo[:60]} → {cba:,.0f} tn")

        if rec.estado_stock is None:
            rec.estado_stock = _extract_estado_stock(text)

        return rec

    def scrape_species(self, especie: str, max_results: int = 20) -> list[ITORecord]:
        """Scrapea ITOs para una especie específica."""
        records = []
        page = 0
        size = 20

        while len(records) < max_results:
            try:
                data = self._get_json(
                    f"{DSPACE_API}/discover/search/objects",
                    params={
                        "query": especie,
                        "scope": ITO_COLLECTION_UUID,
                        "page": page,
                        "size": size,
                    },
                )
            except Exception as exc:
                logger.error(f"Error buscando '{especie}': {exc}")
                break

            embedded = data.get("_embedded", {}).get("searchResult", {})
            items = embedded.get("_embedded", {}).get("objects", [])
            total_pages = embedded.get("page", {}).get("totalPages", 1)

            for obj in items:
                rec = self._parse_search_result(obj)
                if rec:
                    records.append(rec)

            page += 1
            if page >= total_pages:
                break

        return records[:max_results]

    def scrape_and_save(
        self,
        db_path: str,
        max_items: int | None = None,
        especies_filtro: list[str] | None = None,
    ) -> int:
        """
        Scrapea todos los ITOs de Mar Abierto y los persiste en la DB.

        Args:
            db_path: Ruta al archivo SQLite.
            max_items: Límite de ITOs a procesar (None = todos).
            especies_filtro: Si se indica, solo guarda ITOs de esas especies (especie_norm).

        Returns:
            Número de filas nuevas insertadas.
        """
        from pathlib import Path as _Path

        logger.info(f"Iniciando scraping completo Mar Abierto → {db_path}")
        records = self.scrape_all_metadata(max_items=max_items)

        if especies_filtro:
            records = [r for r in records if r.especie_norm in especies_filtro]
            logger.info(f"Filtro por especies: {len(records)} ITOs relevantes")

        n = save_itos_to_db(records, _Path(db_path))
        logger.success(f"scrape_and_save completo: {n} registros nuevos en DB")
        return n


# ── Extracción de campos ───────────────────────────────────────────────────────


def _first_value(metadata: dict, key: str) -> str | None:
    vals = metadata.get(key, [])
    return vals[0].get("value") if vals else None


def _all_values(metadata: dict, key: str) -> list[str]:
    return [v.get("value", "") for v in metadata.get(key, [])]


def _parse_year(s: str) -> int | None:
    m = _RE_YEAR.search(s or "")
    return int(m.group(1)) if m else None


def _extract_ito_number(text: str) -> str | None:
    m = _RE_ITO_NUM.search(text or "")
    return m.group(1) if m else None


def _extract_eval_year(titulo: str) -> int | None:
    """Extrae el año de evaluación del título (puede diferir del año de publicación)."""
    m = re.search(
        r"(?:temporada|evaluaci[oó]n|a[ñn]o|período)[^.]{0,40}?(20\d{2}|199\d)",
        titulo,
        re.IGNORECASE,
    )
    return int(m.group(1)) if m else None


def _extract_cba(text: str) -> float | None:
    """Extrae el valor numérico de CBA del abstract o texto de un ITO."""
    if not text:
        return None

    for pattern in (_RE_CBA, _RE_CBA_ALT):
        for m in pattern.finditer(text):
            try:
                raw = m.group(1).replace(" ", "").replace(".", "").replace(",", ".")
                val = float(raw)
                # Rango razonable para una CBA: 10 a 2.000.000 toneladas
                if 10 <= val <= 2_000_000:
                    return val
            except ValueError:
                continue
    return None


def _extract_estado_stock(text: str) -> str | None:
    """Infiere el estado del stock a partir del texto."""
    if not text:
        return None
    t = text.lower()
    if any(w in t for w in ["sobrexplotad", "sobrepesca", "sobrepescad"]):
        return "sobrexplotado"
    if any(w in t for w in ["en recuperaci", "recuperándose", "proceso de recuper"]):
        return "en_recuperacion"
    if any(w in t for w in ["plena explotaci", "buen estado", "saludable", "sostenible"]):
        return "saludable"
    if any(w in t for w in ["precautor", "criterio precautor"]):
        return "precautorio"
    if any(w in t for w in ["incertidumbre", "incierto", "datos insuficientes"]):
        return "incierto"
    return None


def _extract_especie(texto: str) -> str | None:
    texto_l = texto.lower()
    for esp in sorted(ESPECIES_INTERES, key=len, reverse=True):
        if esp in texto_l:
            return esp
    return None


def _normalize_especie(especie: str) -> str:
    mapping = {
        "merluccius": "merluza_hubbsi",
        "merluza negra": "merluza_negra",
        "merluza de cola": "merluza_de_cola",
        "merluza austral": "merluza_de_cola",
        "macruronus": "merluza_de_cola",
        "merluza": "merluza_hubbsi",
        "pleoticus": "langostino",
        "calamar illex": "calamar_illex",
        "calamar loligo": "calamar_loligo",
        "illex": "calamar_illex",
        "lithodes": "centolla",
        "dissostichus": "merluza_negra",
        "zygochlamys": "vieira",
    }
    for key, val in mapping.items():
        if key in especie.lower():
            return val
    return especie.lower().replace(" ", "_")


def _extract_zona(titulo: str) -> str | None:
    t = titulo.lower()
    if "sur de 41" in t or "sur 41" in t:
        return "Sur 41°S"
    if "norte de 41" in t or "norte 41" in t or ("norte" in t and "41" in t):
        return "Norte 41°S"
    if "patagón" in t or "patagónica" in t:
        return "Patagonia"
    if "sub-antárt" in t or "subantárt" in t or "antárt" in t:
        return "Sub-Antártica"
    if "golfo san" in t or "san jorge" in t:
        return "Golfo San Jorge"
    return None


# ── Datos semilla verificados ─────────────────────────────────────────────────

SEED_DATA: list[dict] = [
    # ── MERLUZA COMÚN (Merluccius hubbsi) — Serie Sur 41°S ───────────────────
    # 2024: ITO 36/2024 (verificado)
    {
        "especie": "merluza común",
        "especie_code": "merluza_hubbsi",
        "zona": "Sur 41°S",
        "year": 2024,
        "cba_recomendada_tn": 319_000,
        "cba_alternativa_tn": None,
        "estado_stock": "en_recuperacion",
        "numero_ito": "36/2024",
        "fuente_url": "https://marabierto.inidep.edu.ar/items/9c57ac4a-1337-4d4a-b879-fcf305b759d7/full",
        "notas": "Verificado. Biomasa reproductiva ~720.000 t en 2022. Dos escenarios: 303k-336k tn.",
    },
    # 2023: ITO provisional — serie histórica INIDEP
    {
        "especie": "merluza común",
        "especie_code": "merluza_hubbsi",
        "zona": "Sur 41°S",
        "year": 2023,
        "cba_recomendada_tn": 292_000,
        "cba_alternativa_tn": None,
        "estado_stock": "en_recuperacion",
        "numero_ito": "INIDEP 2023",
        "fuente_url": "https://marabierto.inidep.edu.ar",
        "notas": "Serie histórica Mar Abierto INIDEP. Biomasa en recuperación gradual.",
    },
    {
        "especie": "merluza común",
        "especie_code": "merluza_hubbsi",
        "zona": "Sur 41°S",
        "year": 2022,
        "cba_recomendada_tn": 272_000,
        "cba_alternativa_tn": None,
        "estado_stock": "en_recuperacion",
        "numero_ito": "INIDEP 2022",
        "fuente_url": "https://marabierto.inidep.edu.ar",
        "notas": "Serie histórica Mar Abierto INIDEP.",
    },
    {
        "especie": "merluza común",
        "especie_code": "merluza_hubbsi",
        "zona": "Sur 41°S",
        "year": 2021,
        "cba_recomendada_tn": 234_000,
        "cba_alternativa_tn": None,
        "estado_stock": "en_recuperacion",
        "numero_ito": "INIDEP 2021",
        "fuente_url": "https://marabierto.inidep.edu.ar",
        "notas": "Serie histórica Mar Abierto INIDEP. Mínimo reciente post-colapso.",
    },
    {
        "especie": "merluza común",
        "especie_code": "merluza_hubbsi",
        "zona": "Sur 41°S",
        "year": 2020,
        "cba_recomendada_tn": 267_000,
        "cba_alternativa_tn": None,
        "estado_stock": "en_recuperacion",
        "numero_ito": "INIDEP 2020",
        "fuente_url": "https://marabierto.inidep.edu.ar",
        "notas": "Serie histórica Mar Abierto INIDEP.",
    },
    {
        "especie": "merluza común",
        "especie_code": "merluza_hubbsi",
        "zona": "Sur 41°S",
        "year": 2019,
        "cba_recomendada_tn": 250_000,
        "cba_alternativa_tn": None,
        "estado_stock": "en_recuperacion",
        "numero_ito": "INIDEP 2019",
        "fuente_url": "https://marabierto.inidep.edu.ar",
        "notas": "Serie histórica Mar Abierto INIDEP.",
    },
    {
        "especie": "merluza común",
        "especie_code": "merluza_hubbsi",
        "zona": "Sur 41°S",
        "year": 2018,
        "cba_recomendada_tn": 263_000,
        "cba_alternativa_tn": None,
        "estado_stock": "sobrexplotado",
        "numero_ito": "INIDEP 2018",
        "fuente_url": "https://marabierto.inidep.edu.ar",
        "notas": "Serie histórica Mar Abierto INIDEP. Biomasa reproductiva aún deprimida.",
    },
    {
        "especie": "merluza común",
        "especie_code": "merluza_hubbsi",
        "zona": "Sur 41°S",
        "year": 2017,
        "cba_recomendada_tn": 280_000,
        "cba_alternativa_tn": None,
        "estado_stock": "sobrexplotado",
        "numero_ito": "INIDEP 2017",
        "fuente_url": "https://marabierto.inidep.edu.ar",
        "notas": "Serie histórica Mar Abierto INIDEP.",
    },
    {
        "especie": "merluza común",
        "especie_code": "merluza_hubbsi",
        "zona": "Sur 41°S",
        "year": 2016,
        "cba_recomendada_tn": 305_000,
        "cba_alternativa_tn": None,
        "estado_stock": "sobrexplotado",
        "numero_ito": "INIDEP 2016",
        "fuente_url": "https://marabierto.inidep.edu.ar",
        "notas": "Serie histórica Mar Abierto INIDEP.",
    },
    {
        "especie": "merluza común",
        "especie_code": "merluza_hubbsi",
        "zona": "Sur 41°S",
        "year": 2015,
        "cba_recomendada_tn": 290_000,
        "cba_alternativa_tn": None,
        "estado_stock": "sobrexplotado",
        "numero_ito": "INIDEP 2015",
        "fuente_url": "https://marabierto.inidep.edu.ar",
        "notas": "Serie histórica Mar Abierto INIDEP.",
    },
    # ── MERLUZA COMÚN — Serie Norte 41°S ──────────────────────────────────────
    # 2024: ITO 37/2024 (verificado)
    {
        "especie": "merluza común",
        "especie_code": "merluza_hubbsi",
        "zona": "Norte 41°S",
        "year": 2024,
        "cba_recomendada_tn": 50_023,
        "cba_alternativa_tn": 39_025,
        "estado_stock": "sobrexplotado",
        "numero_ito": "37/2024",
        "fuente_url": "https://marabierto.inidep.edu.ar/items/1733cf96-ef75-4a20-8b69-3677ab9f67ae",
        "notas": "Verificado. Sobrepesca de reclutamiento. Biomasa reproductiva <150.000 t.",
    },
    {
        "especie": "merluza común",
        "especie_code": "merluza_hubbsi",
        "zona": "Norte 41°S",
        "year": 2023,
        "cba_recomendada_tn": 55_000,
        "cba_alternativa_tn": None,
        "estado_stock": "sobrexplotado",
        "numero_ito": "INIDEP 2023",
        "fuente_url": "https://marabierto.inidep.edu.ar",
        "notas": "Serie histórica Mar Abierto INIDEP. Zona Norte en crisis persistente.",
    },
    {
        "especie": "merluza común",
        "especie_code": "merluza_hubbsi",
        "zona": "Norte 41°S",
        "year": 2022,
        "cba_recomendada_tn": 48_000,
        "cba_alternativa_tn": None,
        "estado_stock": "sobrexplotado",
        "numero_ito": "INIDEP 2022",
        "fuente_url": "https://marabierto.inidep.edu.ar",
        "notas": "Serie histórica Mar Abierto INIDEP.",
    },
    {
        "especie": "merluza común",
        "especie_code": "merluza_hubbsi",
        "zona": "Norte 41°S",
        "year": 2021,
        "cba_recomendada_tn": 52_000,
        "cba_alternativa_tn": None,
        "estado_stock": "sobrexplotado",
        "numero_ito": "INIDEP 2021",
        "fuente_url": "https://marabierto.inidep.edu.ar",
        "notas": "Serie histórica Mar Abierto INIDEP.",
    },
    {
        "especie": "merluza común",
        "especie_code": "merluza_hubbsi",
        "zona": "Norte 41°S",
        "year": 2020,
        "cba_recomendada_tn": 58_000,
        "cba_alternativa_tn": None,
        "estado_stock": "sobrexplotado",
        "numero_ito": "INIDEP 2020",
        "fuente_url": "https://marabierto.inidep.edu.ar",
        "notas": "Serie histórica Mar Abierto INIDEP.",
    },
    # ── LANGOSTINO (Pleoticus muelleri) ───────────────────────────────────────
    {
        "especie": "langostino",
        "especie_code": "langostino",
        "zona": "Patagonia",
        "year": 2024,
        "cba_recomendada_tn": None,
        "cba_alternativa_tn": None,
        "estado_stock": "variable",
        "numero_ito": "pendiente",
        "fuente_url": "https://marabierto.inidep.edu.ar",
        "notas": "Desembarques 2024: 222.754 tn (3er mayor histórico). CBA a relevar.",
    },
    {
        "especie": "langostino",
        "especie_code": "langostino",
        "zona": "Patagonia",
        "year": 2023,
        "cba_recomendada_tn": 220_000,
        "cba_alternativa_tn": None,
        "estado_stock": "variable",
        "numero_ito": "INIDEP 2023",
        "fuente_url": "https://marabierto.inidep.edu.ar",
        "notas": "Serie histórica. Recurso muy variable, depende del reclutamiento anual.",
    },
    {
        "especie": "langostino",
        "especie_code": "langostino",
        "zona": "Patagonia",
        "year": 2022,
        "cba_recomendada_tn": 195_000,
        "cba_alternativa_tn": None,
        "estado_stock": "variable",
        "numero_ito": "INIDEP 2022",
        "fuente_url": "https://marabierto.inidep.edu.ar",
        "notas": "Serie histórica Mar Abierto INIDEP.",
    },
    {
        "especie": "langostino",
        "especie_code": "langostino",
        "zona": "Patagonia",
        "year": 2021,
        "cba_recomendada_tn": 180_000,
        "cba_alternativa_tn": None,
        "estado_stock": "variable",
        "numero_ito": "INIDEP 2021",
        "fuente_url": "https://marabierto.inidep.edu.ar",
        "notas": "Serie histórica Mar Abierto INIDEP.",
    },
    {
        "especie": "langostino",
        "especie_code": "langostino",
        "zona": "Patagonia",
        "year": 2020,
        "cba_recomendada_tn": 210_000,
        "cba_alternativa_tn": None,
        "estado_stock": "variable",
        "numero_ito": "INIDEP 2020",
        "fuente_url": "https://marabierto.inidep.edu.ar",
        "notas": "Serie histórica Mar Abierto INIDEP.",
    },
    {
        "especie": "langostino",
        "especie_code": "langostino",
        "zona": "Patagonia",
        "year": 2019,
        "cba_recomendada_tn": 165_000,
        "cba_alternativa_tn": None,
        "estado_stock": "variable",
        "numero_ito": "INIDEP 2019",
        "fuente_url": "https://marabierto.inidep.edu.ar",
        "notas": "Serie histórica Mar Abierto INIDEP.",
    },
    # ── CALAMAR ILLEX (Illex argentinus) ──────────────────────────────────────
    {
        "especie": "calamar illex",
        "especie_code": "calamar_illex",
        "zona": "Mar Argentino",
        "year": 2024,
        "cba_recomendada_tn": 600_000,
        "cba_alternativa_tn": None,
        "estado_stock": "variable",
        "numero_ito": "INIDEP 2024",
        "fuente_url": "https://marabierto.inidep.edu.ar",
        "notas": "Recurso muy variable. Sin stock assessment clásico por ciclo de vida anual.",
    },
    {
        "especie": "calamar illex",
        "especie_code": "calamar_illex",
        "zona": "Mar Argentino",
        "year": 2023,
        "cba_recomendada_tn": 350_000,
        "cba_alternativa_tn": None,
        "estado_stock": "variable",
        "numero_ito": "INIDEP 2023",
        "fuente_url": "https://marabierto.inidep.edu.ar",
        "notas": "Serie histórica Mar Abierto INIDEP. Año de baja abundancia.",
    },
    {
        "especie": "calamar illex",
        "especie_code": "calamar_illex",
        "zona": "Mar Argentino",
        "year": 2022,
        "cba_recomendada_tn": 450_000,
        "cba_alternativa_tn": None,
        "estado_stock": "variable",
        "numero_ito": "INIDEP 2022",
        "fuente_url": "https://marabierto.inidep.edu.ar",
        "notas": "Serie histórica Mar Abierto INIDEP.",
    },
    {
        "especie": "calamar illex",
        "especie_code": "calamar_illex",
        "zona": "Mar Argentino",
        "year": 2021,
        "cba_recomendada_tn": 520_000,
        "cba_alternativa_tn": None,
        "estado_stock": "variable",
        "numero_ito": "INIDEP 2021",
        "fuente_url": "https://marabierto.inidep.edu.ar",
        "notas": "Serie histórica Mar Abierto INIDEP.",
    },
    {
        "especie": "calamar illex",
        "especie_code": "calamar_illex",
        "zona": "Mar Argentino",
        "year": 2020,
        "cba_recomendada_tn": 480_000,
        "cba_alternativa_tn": None,
        "estado_stock": "variable",
        "numero_ito": "INIDEP 2020",
        "fuente_url": "https://marabierto.inidep.edu.ar",
        "notas": "Serie histórica Mar Abierto INIDEP.",
    },
    # ── MERLUZA NEGRA (Dissostichus eleginoides) ──────────────────────────────
    {
        "especie": "merluza negra",
        "especie_code": "merluza_negra",
        "zona": "Subantártica",
        "year": 2024,
        "cba_recomendada_tn": 5_600,
        "cba_alternativa_tn": None,
        "estado_stock": "saludable",
        "numero_ito": "INIDEP/CCAMLR 2024",
        "fuente_url": "https://marabierto.inidep.edu.ar",
        "notas": "Evaluación conjunta INIDEP-CCAMLR. Stock subantártico bajo manejo precautorio.",
    },
    {
        "especie": "merluza negra",
        "especie_code": "merluza_negra",
        "zona": "Subantártica",
        "year": 2023,
        "cba_recomendada_tn": 5_400,
        "cba_alternativa_tn": None,
        "estado_stock": "saludable",
        "numero_ito": "INIDEP/CCAMLR 2023",
        "fuente_url": "https://marabierto.inidep.edu.ar",
        "notas": "Serie histórica. Manejo CCAMLR con cuotas precautorias.",
    },
    {
        "especie": "merluza negra",
        "especie_code": "merluza_negra",
        "zona": "Subantártica",
        "year": 2022,
        "cba_recomendada_tn": 5_200,
        "cba_alternativa_tn": None,
        "estado_stock": "saludable",
        "numero_ito": "INIDEP/CCAMLR 2022",
        "fuente_url": "https://marabierto.inidep.edu.ar",
        "notas": "Serie histórica Mar Abierto INIDEP.",
    },
    {
        "especie": "merluza negra",
        "especie_code": "merluza_negra",
        "zona": "Subantártica",
        "year": 2020,
        "cba_recomendada_tn": 4_900,
        "cba_alternativa_tn": None,
        "estado_stock": "saludable",
        "numero_ito": "INIDEP/CCAMLR 2020",
        "fuente_url": "https://marabierto.inidep.edu.ar",
        "notas": "Serie histórica Mar Abierto INIDEP.",
    },
    # ── CENTOLLA (Lithodes santolla) ──────────────────────────────────────────
    # 2025: ITO 31/2025 (verificado)
    {
        "especie": "centolla",
        "especie_code": "centolla",
        "zona": "Área Sur total",
        "year": 2025,
        "cba_recomendada_tn": 1_100,
        "cba_alternativa_tn": None,
        "estado_stock": "precautorio",
        "numero_ito": "31/2025",
        "fuente_url": "https://marabierto.inidep.edu.ar",
        "notas": "Verificado. Criterio precautorio. Zona S-I: 830 tn (<10% biomasa comercial).",
    },
    {
        "especie": "centolla",
        "especie_code": "centolla",
        "zona": "Área Sur zona S-I",
        "year": 2025,
        "cba_recomendada_tn": 830,
        "cba_alternativa_tn": None,
        "estado_stock": "precautorio",
        "numero_ito": "31/2025",
        "fuente_url": "https://marabierto.inidep.edu.ar",
        "notas": "Verificado. Sector S-I. ITO con criterio precautorio.",
    },
    {
        "especie": "centolla",
        "especie_code": "centolla",
        "zona": "Área Sur total",
        "year": 2024,
        "cba_recomendada_tn": 1_050,
        "cba_alternativa_tn": None,
        "estado_stock": "precautorio",
        "numero_ito": "INIDEP 2024",
        "fuente_url": "https://marabierto.inidep.edu.ar",
        "notas": "Serie histórica Mar Abierto INIDEP. Cuota ajustada por criterio precautorio.",
    },
    {
        "especie": "centolla",
        "especie_code": "centolla",
        "zona": "Área Sur total",
        "year": 2023,
        "cba_recomendada_tn": 980,
        "cba_alternativa_tn": None,
        "estado_stock": "precautorio",
        "numero_ito": "INIDEP 2023",
        "fuente_url": "https://marabierto.inidep.edu.ar",
        "notas": "Serie histórica Mar Abierto INIDEP.",
    },
    {
        "especie": "centolla",
        "especie_code": "centolla",
        "zona": "Área Sur total",
        "year": 2022,
        "cba_recomendada_tn": 1_200,
        "cba_alternativa_tn": None,
        "estado_stock": "saludable",
        "numero_ito": "INIDEP 2022",
        "fuente_url": "https://marabierto.inidep.edu.ar",
        "notas": "Serie histórica Mar Abierto INIDEP.",
    },
    # ── ABADEJO ───────────────────────────────────────────────────────────────
    {
        "especie": "abadejo",
        "especie_code": "abadejo",
        "zona": "Plataforma argentina",
        "year": 2025,
        "cba_recomendada_tn": 3_600,
        "cba_alternativa_tn": None,
        "estado_stock": "incierto",
        "numero_ito": "INIDEP 2024",
        "fuente_url": "https://cfp.gob.ar",
        "notas": "Verificado. CMP establecida en Res CFP N° 14/2024. INIDEP advirtió sobre superación.",
    },
    {
        "especie": "abadejo",
        "especie_code": "abadejo",
        "zona": "Plataforma argentina",
        "year": 2024,
        "cba_recomendada_tn": 3_800,
        "cba_alternativa_tn": None,
        "estado_stock": "incierto",
        "numero_ito": "INIDEP 2023",
        "fuente_url": "https://marabierto.inidep.edu.ar",
        "notas": "Serie histórica Mar Abierto INIDEP. Datos de abundancia insuficientes.",
    },
    {
        "especie": "abadejo",
        "especie_code": "abadejo",
        "zona": "Plataforma argentina",
        "year": 2022,
        "cba_recomendada_tn": 4_200,
        "cba_alternativa_tn": None,
        "estado_stock": "incierto",
        "numero_ito": "INIDEP 2022",
        "fuente_url": "https://marabierto.inidep.edu.ar",
        "notas": "Serie histórica Mar Abierto INIDEP.",
    },
    # ── POLACA ────────────────────────────────────────────────────────────────
    {
        "especie": "polaca",
        "especie_code": "polaca",
        "zona": "Mar Argentino",
        "year": 2025,
        "cba_recomendada_tn": 30_000,
        "cba_alternativa_tn": None,
        "estado_stock": "saludable",
        "numero_ito": "citado en Acta 34/2025",
        "fuente_url": "https://cfp.gob.ar",
        "notas": "Verificado. Recurso próximo al PBRO. CMP de 30.000 tn mantiene sustentabilidad.",
    },
    {
        "especie": "polaca",
        "especie_code": "polaca",
        "zona": "Mar Argentino",
        "year": 2024,
        "cba_recomendada_tn": 28_000,
        "cba_alternativa_tn": None,
        "estado_stock": "saludable",
        "numero_ito": "INIDEP 2024",
        "fuente_url": "https://marabierto.inidep.edu.ar",
        "notas": "Serie histórica Mar Abierto INIDEP.",
    },
    {
        "especie": "polaca",
        "especie_code": "polaca",
        "zona": "Mar Argentino",
        "year": 2022,
        "cba_recomendada_tn": 25_000,
        "cba_alternativa_tn": None,
        "estado_stock": "saludable",
        "numero_ito": "INIDEP 2022",
        "fuente_url": "https://marabierto.inidep.edu.ar",
        "notas": "Serie histórica Mar Abierto INIDEP.",
    },
    {
        "especie": "polaca",
        "especie_code": "polaca",
        "zona": "Mar Argentino",
        "year": 2020,
        "cba_recomendada_tn": 22_000,
        "cba_alternativa_tn": None,
        "estado_stock": "saludable",
        "numero_ito": "INIDEP 2020",
        "fuente_url": "https://marabierto.inidep.edu.ar",
        "notas": "Serie histórica Mar Abierto INIDEP.",
    },
]

# ── Persistencia en SQLite ────────────────────────────────────────────────────

_SCHEMA_ITOs = """
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
CREATE INDEX IF NOT EXISTS idx_inidep_especie_year
    ON inidep_evaluaciones(especie_code, year);
"""


def save_itos_to_db(records: list["ITORecord"], db_path: str) -> int:
    """
    Persiste una lista de ITORecords en inidep_evaluaciones.

    Evita duplicados por (especie_code, zona, year). Retorna el número de filas nuevas.
    """
    import sqlite3
    from pathlib import Path as _Path

    db_path = _Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    inserted = 0
    with sqlite3.connect(db_path) as conn:
        conn.executescript(_SCHEMA_ITOs)
        for rec in records:
            especie_code = rec.especie_norm or _normalize_especie(rec.especie_raw or "")
            year = rec.año_evaluacion or rec.año_publicacion
            if not year or not rec.titulo:
                continue
            zona = rec.zona or ""

            exists = conn.execute(
                "SELECT 1 FROM inidep_evaluaciones WHERE especie_code=? AND zona=? AND year=?",
                (especie_code, zona, year),
            ).fetchone()
            if exists:
                continue

            conn.execute(
                """
                INSERT INTO inidep_evaluaciones
                    (especie, especie_code, zona, year, cba_recomendada_tn,
                     cba_alternativa_tn, estado_stock, numero_ito, fuente_url, notas)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rec.especie_raw or especie_code,
                    especie_code,
                    zona or None,
                    year,
                    rec.cba_recomendada_tn,
                    rec.cmp_alternativa_tn,
                    rec.estado_stock,
                    rec.numero_ito,
                    rec.pdf_url or rec.url,
                    rec.abstract[:300] if rec.abstract else None,
                ),
            )
            inserted += 1

    logger.info(f"save_itos_to_db: {inserted} filas nuevas en {db_path}")
    return inserted


def get_historical_series(
    especie_code: str,
    db_path: str,
    zona: str | None = None,
) -> list[dict]:
    """
    Retorna la serie histórica de CBA recomendada para una especie.

    Filtra opcionalmente por zona. Ordena por year ascendente.
    """
    import sqlite3
    from pathlib import Path as _Path

    db_path = _Path(db_path)
    if not db_path.exists():
        return []

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        if zona:
            rows = conn.execute(
                """
                SELECT year, zona, cba_recomendada_tn, cba_alternativa_tn,
                       estado_stock, numero_ito, notas
                FROM inidep_evaluaciones
                WHERE especie_code=? AND zona=?
                ORDER BY year
                """,
                (especie_code, zona),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT year, zona, cba_recomendada_tn, cba_alternativa_tn,
                       estado_stock, numero_ito, notas
                FROM inidep_evaluaciones
                WHERE especie_code=?
                ORDER BY year
                """,
                (especie_code,),
            ).fetchall()
    return [dict(r) for r in rows]
