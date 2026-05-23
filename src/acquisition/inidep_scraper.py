"""
Scraper del repositorio Mar Abierto del INIDEP.

Extrae Informes Técnicos Oficiales (ITOs) con recomendaciones de CBA/CMP
por especie y año, para cruzar con las decisiones del CFP.

Repositorio: https://marabierto.inidep.edu.ar
Colección ITOs: /collections/50a522a6-b22a-4c95-88fb-adbb6936fdde
"""
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import requests
import urllib3
from bs4 import BeautifulSoup
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

urllib3.disable_warnings()

MAR_ABIERTO_BASE = "https://marabierto.inidep.edu.ar"
ITO_COLLECTION = f"{MAR_ABIERTO_BASE}/collections/50a522a6-b22a-4c95-88fb-adbb6936fdde"
MAR_ABIERTO_API = "https://marabiertonew.inidep.edu.ar/server/api"

# Especies de interés para el comparador
ESPECIES_INTERES = [
    "merluza", "merluccius", "langostino", "pleoticus",
    "calamar", "illex", "centolla", "lithodes", "abadejo",
    "polaca", "vieira", "zygochlamys", "anchoíta", "anchoita",
    "merluza negra", "dissostichus", "merluza de cola",
    "macruronus", "merluza austral",
]


@dataclass
class ITORecord:
    """Registro de un Informe Técnico Oficial del INIDEP."""
    titulo: str
    url: str
    año_publicacion: Optional[int] = None
    año_evaluacion: Optional[int] = None
    especie_raw: Optional[str] = None
    especie_norm: Optional[str] = None
    zona: Optional[str] = None
    cba_recomendada_tn: Optional[float] = None
    cmp_alternativa_tn: Optional[float] = None
    estado_stock: Optional[str] = None      # saludable | sobrexplotado | en_recuperacion | incierto
    autores: list[str] = field(default_factory=list)
    numero_ito: Optional[str] = None
    pdf_url: Optional[str] = None
    fuente: str = "INIDEP Mar Abierto"


class INIDEPScraper:
    """Scraper del repositorio Mar Abierto del INIDEP."""

    def __init__(self, delay: float = 1.5):
        self.delay = delay
        self.session = requests.Session()
        self.session.verify = False
        self.session.headers["User-Agent"] = "CFP-Audit-Research/1.0"

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
    def _get(self, url: str) -> requests.Response:
        resp = self.session.get(url, timeout=20)
        resp.raise_for_status()
        return resp

    def search_itos(
        self,
        query: str = "",
        page: int = 1,
        per_page: int = 20,
    ) -> list[dict]:
        """Busca ITOs en Mar Abierto por query string."""
        time.sleep(self.delay)
        params = {
            "scope": "50a522a6-b22a-4c95-88fb-adbb6936fdde",
            "query": query,
            "page": page,
            "rpp": per_page,
        }
        try:
            url = f"{MAR_ABIERTO_BASE}/discover"
            resp = self._get(f"{url}?{'&'.join(f'{k}={v}' for k,v in params.items())}")
            soup = BeautifulSoup(resp.content, "lxml")
            items = []
            for article in soup.find_all("div", class_=re.compile("artifact-description|item-summary")):
                link = article.find("a", href=re.compile(r"/items/|/handle/"))
                if not link:
                    continue
                item_url = MAR_ABIERTO_BASE + link["href"] if link["href"].startswith("/") else link["href"]
                items.append({
                    "titulo": link.get_text(strip=True),
                    "url": item_url,
                })
            return items
        except Exception as exc:
            logger.error(f"Error buscando '{query}': {exc}")
            return []

    def scrape_ito_detail(self, url: str) -> Optional[ITORecord]:
        """Extrae metadatos de un ITO individual."""
        time.sleep(self.delay)
        try:
            resp = self._get(url)
            soup = BeautifulSoup(resp.content, "lxml")

            titulo = ""
            h_tags = soup.find(["h1", "h2", "h3"])
            if h_tags:
                titulo = h_tags.get_text(strip=True)

            # Buscar año
            año = None
            for tag in soup.find_all(string=re.compile(r"\b(20\d{2})\b")):
                m = re.search(r"\b(20\d{2})\b", tag)
                if m:
                    año = int(m.group(1))
                    break

            # Buscar PDF link
            pdf_url = None
            for a in soup.find_all("a", href=re.compile(r"\.pdf|/download|/content")):
                href = a.get("href", "")
                pdf_url = href if href.startswith("http") else MAR_ABIERTO_BASE + href
                break

            record = ITORecord(
                titulo=titulo,
                url=url,
                año_publicacion=año,
                pdf_url=pdf_url,
            )

            # Inferir especie del título
            record.especie_raw = _extract_especie(titulo)
            record.especie_norm = _normalize_especie(record.especie_raw or "")
            record.zona = _extract_zona(titulo)

            return record

        except Exception as exc:
            logger.error(f"Error scrapeando {url}: {exc}")
            return None

    def scrape_all_especies(self, output_path: Path) -> list[ITORecord]:
        """Scrapea ITOs para todas las especies de interés."""
        all_records = []
        queries = [
            "merluza hubbsi evaluación CBA",
            "merluza hubbsi estimación captura",
            "langostino evaluación abundancia",
            "calamar illex pesquería",
            "centolla evaluación",
            "abadejo evaluación",
            "polaca evaluación",
            "vieira patagónica evaluación",
            "merluza negra evaluación",
        ]

        for query in queries:
            logger.info(f"Buscando: '{query}'")
            items = self.search_itos(query=query, per_page=20)
            logger.info(f"  → {len(items)} resultados")
            for item in items[:10]:
                rec = self.scrape_ito_detail(item["url"])
                if rec:
                    all_records.append(rec)

        logger.success(f"Total ITOs scrapeados: {len(all_records)}")
        return all_records


# ── Datos semilla (ya verificados con fuentes oficiales) ──────────────────────

SEED_DATA: list[dict] = [
    # MERLUZA COMÚN (Merluccius hubbsi) — fuente: ITO 36/2024, ITO 37/2024
    {
        "especie": "merluza común",
        "especie_code": "merluza_hubbsi",
        "zona": "Sur 41°S",
        "year": 2024,
        "cba_recomendada_tn": 319_000,
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
    # CENTOLLA (Lithodes santolla) — fuente: ITO 31/2025 mencionado en Acta 32/2025
    {
        "especie": "centolla",
        "especie_code": "centolla",
        "zona": "Área Sur total",
        "year": 2025,
        "cba_recomendada_tn": 1_100,
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
        "estado_stock": "precautorio",
        "numero_ito": "31/2025",
        "fuente_url": "https://marabierto.inidep.edu.ar",
        "notas": "Sector S-I. ITO con criterio precautorio ante necesidad de margen.",
    },
    # ABADEJO — fuente: Acta 31/2025 referencia Res CFP N° 14/2024
    {
        "especie": "abadejo",
        "especie_code": "abadejo",
        "zona": "Plataforma argentina",
        "year": 2025,
        "cba_recomendada_tn": 3_600,
        "estado_stock": "incierto",
        "numero_ito": "INIDEP 2024",
        "fuente_url": "https://cfp.gob.ar",
        "notas": "CMP establecida en Res CFP N° 14/2024. INIDEP advirtió sobre superación.",
    },
    # POLACA — fuente: ITO citado en Acta 34/2025
    {
        "especie": "polaca",
        "especie_code": "polaca",
        "zona": "Mar Argentino",
        "year": 2025,
        "cba_recomendada_tn": 30_000,
        "estado_stock": "saludable",
        "numero_ito": "citado en Acta 34/2025",
        "fuente_url": "https://cfp.gob.ar",
        "notas": "Recurso próximo al PBRO. CMP de 30.000 tn mantiene sustentabilidad.",
    },
    # LANGOSTINO — fuente: búsqueda INIDEP Mar Abierto
    {
        "especie": "langostino",
        "especie_code": "langostino",
        "zona": "Patagonia",
        "year": 2024,
        "cba_recomendada_tn": None,   # A completar con scraping
        "estado_stock": "variable",
        "numero_ito": "pendiente",
        "fuente_url": "https://marabierto.inidep.edu.ar",
        "notas": "Desembarques 2024: 222.754 tn (3er mayor histórico). CBA a relevar.",
    },
]


def _extract_especie(titulo: str) -> Optional[str]:
    titulo_l = titulo.lower()
    # Ordenar de mayor a menor longitud para que "merluza negra" gane sobre "merluza"
    for esp in sorted(ESPECIES_INTERES, key=len, reverse=True):
        if esp in titulo_l:
            return esp
    return None


def _normalize_especie(especie: str) -> str:
    mapping = {
        "merluccius": "merluza_hubbsi",
        "merluza": "merluza_hubbsi",
        "pleoticus": "langostino",
        "illex": "calamar_illex",
        "lithodes": "centolla",
        "dissostichus": "merluza_negra",
        "macruronus": "merluza_de_cola",
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
    if "patagón" in t:
        return "Patagonia"
    return None
