"""
Scraper del Boletín Oficial de la República Argentina.

Extrae designaciones de autoridades y directores de empresas pesqueras
publicados en el Boletín Oficial (Sección 4 — Sociedades) para construir
la red de conflictos de interés CFP-industria.

URL base: https://www.boletinoficial.gob.ar
"""

from __future__ import annotations

import re
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

BO_BASE = "https://www.boletinoficial.gob.ar"
BO_SEARCH_URL = f"{BO_BASE}/busqueda/advanced"
BO_SECTION_SOCIEDADES = "4"

# Patrones para extraer roles de directores en textos del Boletín Oficial
_RE_CARGO = re.compile(
    r"\b(presidente|director\s+titular|director\s+suplente|vice\s*presidente|"
    r"secretar[io|ia]+|tesorero|síndico|socio\s+gerente|gerente\s+general|"
    r"apoderado|representante\s+legal|administrador)\b",
    re.IGNORECASE,
)

# ── Seed demo ──────────────────────────────────────────────────────────────────
# Datos demostrativos para desarrollo y tests.
# Fuente: "seed_demo" — no verificados contra registros reales.
# Un experto debe reemplazar con datos del Boletín Oficial / IGJ reales.
SEED_CARGOS_DEMO: list[dict] = [
    # empresas del alias map de graph_builder (datos demo)
    {
        "persona_nombre": "Carlos Eduardo Pérez",
        "empresa_nombre": "ARGENOVA S.A.",
        "cargo": "presidente",
        "desde_year": 2015,
        "hasta_year": None,
        "notas": "BO 30/11/2015 p.4 — demo",
    },
    {
        "persona_nombre": "Marta Alicia Rodríguez",
        "empresa_nombre": "ARGENOVA S.A.",
        "cargo": "director_titular",
        "desde_year": 2015,
        "hasta_year": 2021,
        "notas": "BO 30/11/2015 p.4 — demo",
    },
    {
        "persona_nombre": "Héctor Norberto Gutiérrez",
        "empresa_nombre": "CONARPESA",
        "cargo": "socio_gerente",
        "desde_year": 2010,
        "hasta_year": None,
        "notas": "BO 15/03/2010 p.4 — demo",
    },
    {
        "persona_nombre": "Silvia Beatriz Torres",
        "empresa_nombre": "CONARPESA",
        "cargo": "director_suplente",
        "desde_year": 2018,
        "hasta_year": None,
        "notas": "BO 02/08/2018 p.4 — demo",
    },
    {
        "persona_nombre": "Jorge Alberto Suárez",
        "empresa_nombre": "PRODESUR S.A.",
        "cargo": "presidente",
        "desde_year": 2012,
        "hasta_year": None,
        "notas": "BO 10/06/2012 p.4 — demo",
    },
    {
        "persona_nombre": "Roberto Daniel Méndez",
        "empresa_nombre": "PESANTAR S.A.",
        "cargo": "director_titular",
        "desde_year": 2008,
        "hasta_year": 2020,
        "notas": "BO 20/04/2008 p.4 — demo",
    },
    {
        "persona_nombre": "Ana Laura Vega",
        "empresa_nombre": "GLACIAR PESQUERA S.A.",
        "cargo": "gerente_general",
        "desde_year": 2016,
        "hasta_year": None,
        "notas": "BO 07/09/2016 p.4 — demo",
    },
    {
        "persona_nombre": "Luis Marcelo Soria",
        "empresa_nombre": "GLACIAR PESQUERA S.A.",
        "cargo": "presidente",
        "desde_year": 2014,
        "hasta_year": None,
        "notas": "BO 14/02/2014 p.4 — demo",
    },
    {
        "persona_nombre": "Patricia Noemí Flores",
        "empresa_nombre": "ALTAMARE S.A.",
        "cargo": "presidente",
        "desde_year": 2019,
        "hasta_year": None,
        "notas": "BO 22/05/2019 p.4 — demo",
    },
    {
        "persona_nombre": "Diego Hernán Castro",
        "empresa_nombre": "TINOPESCA S.A.",
        "cargo": "director_titular",
        "desde_year": 2014,
        "hasta_year": 2022,
        "notas": "BO 11/01/2014 p.4 — demo",
    },
    {
        "persona_nombre": "Nora Graciela Ibáñez",
        "empresa_nombre": "ARDAPEZ S.A.",
        "cargo": "presidente",
        "desde_year": 2013,
        "hasta_year": None,
        "notas": "BO 08/10/2013 p.4 — demo",
    },
    {
        "persona_nombre": "Martín Osvaldo Ruiz",
        "empresa_nombre": "ESTREMAR S.A.",
        "cargo": "socio_gerente",
        "desde_year": 2020,
        "hasta_year": None,
        "notas": "BO 17/11/2020 p.4 — demo",
    },
    {
        "persona_nombre": "Fernando Augusto López",
        "empresa_nombre": "ILLEX FISHING S.A.",
        "cargo": "presidente",
        "desde_year": 2017,
        "hasta_year": None,
        "notas": "BO 29/06/2017 p.4 — demo",
    },
    {
        "persona_nombre": "Graciela Susana Montoya",
        "empresa_nombre": "PRODESUR S.A.",
        "cargo": "director_suplente",
        "desde_year": 2012,
        "hasta_year": None,
        "notas": "BO 10/06/2012 p.4 — demo",
    },
    {
        "persona_nombre": "Oscar Alejandro Bravo",
        "empresa_nombre": "PESQ. DEL ATLÁNTICO S.A.",
        "cargo": "presidente",
        "desde_year": 2011,
        "hasta_year": None,
        "notas": "BO 03/03/2011 p.4 — demo",
    },
    {
        "persona_nombre": "Claudia Verónica Navarro",
        "empresa_nombre": "PESQ. DEL ATLÁNTICO S.A.",
        "cargo": "director_titular",
        "desde_year": 2017,
        "hasta_year": None,
        "notas": "BO 15/04/2017 p.4 — demo",
    },
    # personas que TAMBIÉN aparecen en menciones CFP (potencial conflicto de interés)
    {
        "persona_nombre": "Jorge Alberto Suárez",
        "empresa_nombre": "CONARPESA",
        "cargo": "accionista",
        "desde_year": 2010,
        "hasta_year": None,
        "notas": "BO 15/03/2010 p.4 — demo; también consta como delegado provincia",
    },
    {
        "persona_nombre": "Héctor Norberto Gutiérrez",
        "empresa_nombre": "ARGENOVA S.A.",
        "cargo": "director_suplente",
        "desde_year": 2008,
        "hasta_year": 2014,
        "notas": "BO 20/09/2008 p.4 — demo; registrado en actas CFP 2010-2014",
    },
    {
        "persona_nombre": "Luis Marcelo Soria",
        "empresa_nombre": "PESANTAR S.A.",
        "cargo": "accionista",
        "desde_year": 2014,
        "hasta_year": None,
        "notas": "BO 14/02/2014 p.4 — demo; aparece como consejero técnico CFP",
    },
    {
        "persona_nombre": "Roberto Daniel Méndez",
        "empresa_nombre": "ESTREMAR S.A.",
        "cargo": "director_suplente",
        "desde_year": 2015,
        "hasta_year": None,
        "notas": "BO 25/08/2015 p.4 — demo; consta en votos CFP 2016-2019",
    },
]

# Schema SQLite para la tabla de cargos directivos
SCHEMA_CONFLICTOS = """
CREATE TABLE IF NOT EXISTS cargos_directivos (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    persona_nombre  TEXT NOT NULL,
    persona_norm    TEXT NOT NULL,
    empresa_nombre  TEXT NOT NULL,
    empresa_norm    TEXT NOT NULL,
    cargo           TEXT,
    desde_year      INTEGER,
    hasta_year      INTEGER,
    fuente          TEXT DEFAULT 'boletin_oficial',
    url_fuente      TEXT,
    verificado      BOOLEAN DEFAULT FALSE,
    notas           TEXT,
    created_at      TEXT DEFAULT (datetime('now')),
    UNIQUE(persona_norm, empresa_norm, cargo)
);
CREATE TABLE IF NOT EXISTS conflictos_detectados (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    persona_nombre  TEXT NOT NULL,
    empresa_nombre  TEXT NOT NULL,
    tipo_conflicto  TEXT NOT NULL,
    severidad       TEXT NOT NULL,
    n_resoluciones  INTEGER DEFAULT 0,
    detalle         TEXT,
    verificado      BOOLEAN DEFAULT FALSE,
    created_at      TEXT DEFAULT (datetime('now')),
    UNIQUE(persona_nombre, empresa_nombre, tipo_conflicto)
);
CREATE INDEX IF NOT EXISTS idx_cargos_persona ON cargos_directivos(persona_norm);
CREATE INDEX IF NOT EXISTS idx_cargos_empresa ON cargos_directivos(empresa_norm);
CREATE INDEX IF NOT EXISTS idx_conflictos_persona ON conflictos_detectados(persona_nombre);
CREATE INDEX IF NOT EXISTS idx_conflictos_severidad ON conflictos_detectados(severidad);
"""


def _normalize(texto: str) -> str:
    import unicodedata

    texto = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in texto if unicodedata.category(c) != "Mn").strip()


@dataclass
class CargoDirectivo:
    """Representa un cargo directivo de una persona en una empresa pesquera."""

    persona_nombre: str
    empresa_nombre: str
    cargo: str
    desde_year: int | None
    hasta_year: int | None
    fuente: str
    url_fuente: str | None
    verificado: bool = False
    notas: str | None = None


class BoletinOficialScraper:
    """Scraper del Boletín Oficial para designaciones de autoridades societarias."""

    def __init__(self, timeout: int = 30, delay: float = 2.0):
        self.timeout = timeout
        self.delay = delay
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "CFPAuditBot/1.0 (+https://github.com/arielgiamportone/cfp-audit-intelligence)"
            }
        )

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def _fetch(self, url: str, params: dict | None = None) -> requests.Response:
        """Realiza petición HTTP con retry y rate limiting."""
        time.sleep(self.delay)
        response = self.session.get(url, params=params, timeout=self.timeout, verify=False)
        response.raise_for_status()
        return response

    def search_empresa(self, nombre_empresa: str) -> list[dict]:
        """
        Busca publicaciones societarias de una empresa en el Boletín Oficial.

        Retorna lista de resultados con: titulo, fecha, url, extracto.
        """
        try:
            params = {
                "q": nombre_empresa,
                "s": BO_SECTION_SOCIEDADES,
                "d": "1",
                "cantPorPagina": "10",
            }
            response = self._fetch(BO_SEARCH_URL, params=params)
            return self._parse_search_results(response.text, nombre_empresa)
        except Exception as exc:
            logger.warning(f"Error buscando '{nombre_empresa}' en BO: {exc}")
            return []

    def _parse_search_results(self, html: str, query: str) -> list[dict]:
        """Extrae resultados de la página de búsqueda del Boletín Oficial."""
        soup = BeautifulSoup(html, "html.parser")
        resultados = []
        for item in soup.select(".resultado-buscador, .aviso-resultado, article.resultado"):
            titulo_el = item.select_one("h3, h4, .titulo-aviso")
            fecha_el = item.select_one(".fecha, time, .fecha-publicacion")
            link_el = item.select_one("a[href]")
            extracto_el = item.select_one("p, .extracto, .texto-aviso")
            resultados.append(
                {
                    "titulo": titulo_el.get_text(strip=True) if titulo_el else query,
                    "fecha": fecha_el.get_text(strip=True) if fecha_el else "",
                    "url": (
                        f"{BO_BASE}{link_el['href']}"
                        if link_el and link_el["href"].startswith("/")
                        else (link_el["href"] if link_el else "")
                    ),
                    "extracto": extracto_el.get_text(strip=True)[:300] if extracto_el else "",
                }
            )
        return resultados

    def extract_autoridades(self, html: str, empresa_nombre: str) -> list[CargoDirectivo]:
        """
        Extrae nombres y cargos de autoridades de un aviso societario del BO.

        Detecta patrones como: "Presidente: Juan García" o
        "se designa como director titular a María López".
        """
        soup = BeautifulSoup(html, "html.parser")
        texto = soup.get_text(" ")
        cargos_encontrados = []

        lineas = [ln.strip() for ln in texto.splitlines() if ln.strip()]
        for linea in lineas:
            match = _RE_CARGO.search(linea)
            if not match:
                continue
            cargo = match.group(0).lower().replace(" ", "_")
            # Buscar nombre después del cargo
            pos = match.end()
            fragmento = linea[pos : pos + 80].strip().lstrip(":").strip()
            nombre = _extraer_nombre(fragmento)
            if nombre:
                cargos_encontrados.append(
                    CargoDirectivo(
                        persona_nombre=nombre,
                        empresa_nombre=empresa_nombre,
                        cargo=cargo,
                        desde_year=_extraer_year(linea),
                        hasta_year=None,
                        fuente="boletin_oficial",
                        url_fuente=None,
                        verificado=False,
                    )
                )

        return cargos_encontrados

    def fetch_cargos_empresa(self, nombre_empresa: str, db_path: Path) -> int:
        """
        Busca y persiste directores de una empresa en la tabla cargos_directivos.

        Retorna cantidad de cargos nuevos insertados.
        """
        resultados = self.search_empresa(nombre_empresa)
        insertados = 0
        for resultado in resultados:
            if not resultado.get("url"):
                continue
            try:
                resp = self._fetch(resultado["url"])
                cargos = self.extract_autoridades(resp.text, nombre_empresa)
                for cargo in cargos:
                    cargo.url_fuente = resultado["url"]
                    if _insert_cargo(cargo, db_path):
                        insertados += 1
            except Exception as exc:
                logger.warning(f"Error procesando {resultado['url']}: {exc}")
        logger.info(f"{nombre_empresa}: {insertados} cargos nuevos insertados")
        return insertados


def seed_cargos_demo(db_path: Path) -> int:
    """
    Inserta datos demo de cargos directivos para desarrollo y tests.

    Los registros son ejemplos sintéticos (fuente='seed_demo', verificado=FALSE).
    Deben ser reemplazados por datos reales del Boletín Oficial / IGJ.
    """
    _init_schema(db_path)
    conn = sqlite3.connect(db_path)
    insertados = 0
    try:
        for item in SEED_CARGOS_DEMO:
            try:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO cargos_directivos
                        (persona_nombre, persona_norm, empresa_nombre, empresa_norm,
                         cargo, desde_year, hasta_year, fuente, verificado, notas)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'seed_demo', FALSE, ?)
                    """,
                    (
                        item["persona_nombre"],
                        _normalize(item["persona_nombre"]),
                        item["empresa_nombre"],
                        _normalize(item["empresa_nombre"]),
                        item["cargo"],
                        item.get("desde_year"),
                        item.get("hasta_year"),
                        item.get("notas"),
                    ),
                )
                insertados += conn.execute("SELECT changes()").fetchone()[0]
            except sqlite3.IntegrityError:
                pass
        conn.commit()
    finally:
        conn.close()
    logger.info(f"Seed cargos demo: {insertados} registros insertados en {db_path}")
    return insertados


def _init_schema(db_path: Path) -> None:
    """Crea tablas si no existen."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(SCHEMA_CONFLICTOS)
        conn.commit()
    finally:
        conn.close()


def _insert_cargo(cargo: CargoDirectivo, db_path: Path) -> bool:
    """Inserta un cargo en la BD. Retorna True si fue nuevo."""
    _init_schema(db_path)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            INSERT OR IGNORE INTO cargos_directivos
                (persona_nombre, persona_norm, empresa_nombre, empresa_norm,
                 cargo, desde_year, hasta_year, fuente, url_fuente, verificado, notas)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                cargo.persona_nombre,
                _normalize(cargo.persona_nombre),
                cargo.empresa_nombre,
                _normalize(cargo.empresa_nombre),
                cargo.cargo,
                cargo.desde_year,
                cargo.hasta_year,
                cargo.fuente,
                cargo.url_fuente,
                cargo.verificado,
                cargo.notas,
            ),
        )
        changes = conn.execute("SELECT changes()").fetchone()[0]
        conn.commit()
        return changes > 0
    finally:
        conn.close()


def _extraer_nombre(fragmento: str) -> str | None:
    """Intenta extraer un nombre propio del fragmento de texto."""
    # Tomar primeras palabras capitalizadas (máx 4 tokens)
    tokens = fragmento.split()[:6]
    nombre_tokens = []
    for t in tokens:
        limpio = re.sub(r"[,;:]", "", t)
        if limpio and limpio[0].isupper() and len(limpio) > 1:
            nombre_tokens.append(limpio)
        else:
            break
    nombre = " ".join(nombre_tokens[:4]).strip()
    return nombre if len(nombre) > 5 else None


def _extraer_year(texto: str) -> int | None:
    """Extrae el año de una cadena de texto."""
    match = re.search(r"\b(19|20)\d{2}\b", texto)
    return int(match.group(0)) if match else None
