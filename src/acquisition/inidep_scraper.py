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
from pathlib import Path
from typing import Optional

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
    "merluza negra", "merluza de cola", "merluza austral",
    "calamar illex", "calamar loligo",
    "merluza", "merluccius", "langostino", "pleoticus",
    "calamar", "illex", "centolla", "lithodes", "abadejo",
    "polaca", "vieira", "zygochlamys", "anchoíta", "anchoita",
    "dissostichus", "macruronus",
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
    uuid: Optional[str] = None
    año_publicacion: Optional[int] = None
    año_evaluacion: Optional[int] = None
    especie_raw: Optional[str] = None
    especie_norm: Optional[str] = None
    zona: Optional[str] = None
    cba_recomendada_tn: Optional[float] = None
    cmp_alternativa_tn: Optional[float] = None
    estado_stock: Optional[str] = None
    autores: list[str] = field(default_factory=list)
    numero_ito: Optional[str] = None
    pdf_url: Optional[str] = None
    abstract: Optional[str] = None
    fuente: str = "INIDEP Mar Abierto"


class INIDEPScraper:
    """Scraper del repositorio Mar Abierto del INIDEP vía DSpace 7 REST API."""

    def __init__(self, delay: float = 1.0):
        self.delay = delay
        self.session = requests.Session()
        self.session.verify = False
        self.session.headers.update({
            "User-Agent": "CFP-Audit-Research/1.0 (github.com/arielgiamportone/cfp-audit-intelligence)",
            "Accept": "application/json",
        })

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
    def _get_json(self, url: str, params: Optional[dict] = None) -> dict:
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
        return data.get("_embedded", {}).get("searchresults", {}).get("page", {}).get("totalElements", 0)

    def scrape_all_metadata(self, max_items: Optional[int] = None) -> list[ITORecord]:
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

            embedded = data.get("_embedded", {}).get("searchresults", {})
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

            logger.info(f"  Página {page + 1}/{total_pages}: {len(items)} items — total acumulado: {len(records)}")

            page += 1
            if page >= total_pages:
                break

        logger.success(f"Scraping completado: {len(records)} ITOs recuperados")
        return records

    def _parse_search_result(self, obj: dict) -> Optional[ITORecord]:
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

    def get_pdf_url(self, uuid: str) -> Optional[str]:
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

    def download_and_extract_pdf(self, rec: ITORecord) -> Optional[str]:
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

            embedded = data.get("_embedded", {}).get("searchresults", {})
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


# ── Extracción de campos ───────────────────────────────────────────────────────

def _first_value(metadata: dict, key: str) -> Optional[str]:
    vals = metadata.get(key, [])
    return vals[0].get("value") if vals else None


def _all_values(metadata: dict, key: str) -> list[str]:
    return [v.get("value", "") for v in metadata.get(key, [])]


def _parse_year(s: str) -> Optional[int]:
    m = _RE_YEAR.search(s or "")
    return int(m.group(1)) if m else None


def _extract_ito_number(text: str) -> Optional[str]:
    m = _RE_ITO_NUM.search(text or "")
    return m.group(1) if m else None


def _extract_eval_year(titulo: str) -> Optional[int]:
    """Extrae el año de evaluación del título (puede diferir del año de publicación)."""
    m = re.search(
        r"(?:temporada|evaluaci[oó]n|a[ñn]o|período)[^.]{0,40}?(20\d{2}|199\d)",
        titulo, re.IGNORECASE,
    )
    return int(m.group(1)) if m else None


def _extract_cba(text: str) -> Optional[float]:
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


def _extract_estado_stock(text: str) -> Optional[str]:
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


def _extract_especie(texto: str) -> Optional[str]:
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


def _extract_zona(titulo: str) -> Optional[str]:
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
    # MERLUZA COMÚN (Merluccius hubbsi) — ITO 36/2024, ITO 37/2024
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
        "notas": "Biomasa reproductiva ~720.000 t en 2022. Dos escenarios: 303k-336k tn.",
    },
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
        "notas": "Sobrepesca de reclutamiento. Biomasa reproductiva <150.000 t.",
    },
    # CENTOLLA (Lithodes santolla) — ITO 31/2025
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
        "notas": "Criterio precautorio. Zona S-I: 830 tn (<10% biomasa comercial).",
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
        "notas": "Sector S-I. ITO con criterio precautorio ante necesidad de margen.",
    },
    # ABADEJO — Res CFP N° 14/2024
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
        "notas": "CMP establecida en Res CFP N° 14/2024. INIDEP advirtió sobre superación.",
    },
    # POLACA — citado en Acta 34/2025
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
        "notas": "Recurso próximo al PBRO. CMP de 30.000 tn mantiene sustentabilidad.",
    },
    # LANGOSTINO — CBA pendiente
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
]
