"""
Scraper batch para descarga masiva de todas las actas del CFP (1998–presente).

Uso:
    python -m src.acquisition.batch_scraper --years 1998-2025
    python -m src.acquisition.batch_scraper --year 2024
"""
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests
import urllib3
from bs4 import BeautifulSoup
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


BASE_URL = "https://cfp.gob.ar"
ACTAS_URL = f"{BASE_URL}/actas-cfp"


@dataclass
class ActaMetadata:
    year: int
    nombre: str
    url: str
    filename: str
    is_anexo: bool
    scraped_at: datetime = field(default_factory=datetime.utcnow)
    local_path: Optional[Path] = None
    download_status: str = "pending"   # pending | ok | error | duplicate
    error_msg: Optional[str] = None


class CFPScraper:
    """Scraper del sitio oficial del CFP con manejo de SSL y rate limiting."""

    def __init__(
        self,
        delay: float = 1.5,
        timeout: int = 30,
        max_retries: int = 3,
        ssl_verify: bool = False,
    ):
        self.delay = delay
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = requests.Session()
        self.session.verify = ssl_verify
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (compatible; CFP-Audit-Bot/1.0; "
                "Investigacion publica datos abiertos)"
            )
        })

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    def _get(self, url: str) -> requests.Response:
        response = self.session.get(url, timeout=self.timeout)
        response.raise_for_status()
        return response

    def get_available_years(self) -> list[int]:
        """Obtiene lista de años con actas publicadas."""
        try:
            resp = self._get(ACTAS_URL)
            soup = BeautifulSoup(resp.content, "lxml")
            year_links = soup.find_all("a", href=re.compile(r"actas-cfp\?anio=\d{4}"))
            years = sorted(
                {int(re.search(r"anio=(\d{4})", a["href"]).group(1)) for a in year_links},
                reverse=True,
            )
            if not years:
                logger.warning("No se encontraron años en la página; usando rango por defecto")
                years = list(range(datetime.now().year, 1997, -1))
            logger.info(f"Años disponibles: {years[0]}–{years[-1]} ({len(years)} años)")
            return years
        except Exception as exc:
            logger.error(f"Error obteniendo años: {exc}")
            return list(range(datetime.now().year, 1997, -1))

    def get_actas_for_year(self, year: int) -> list[ActaMetadata]:
        """Extrae metadatos de todas las actas de un año dado."""
        time.sleep(self.delay)
        url = f"{ACTAS_URL}?anio={year}"
        try:
            resp = self._get(url)
            soup = BeautifulSoup(resp.content, "lxml")

            pdf_list = soup.find("ul", class_="ListaPdf")
            actas: list[ActaMetadata] = []

            if not pdf_list:
                logger.warning(f"  [{year}] No se encontró lista de PDFs")
                return actas

            for li in pdf_list.find_all("li"):
                link = li.find("a")
                if not link or not link.get("href"):
                    continue

                href = link["href"]
                pdf_url = BASE_URL + href if href.startswith("/") else href
                filename = Path(href).name
                is_anexo = li.find("span", class_="ListaPdfActAnexo") is not None
                nombre = link.get_text(strip=True)

                actas.append(
                    ActaMetadata(
                        year=year,
                        nombre=nombre,
                        url=pdf_url,
                        filename=filename,
                        is_anexo=is_anexo,
                    )
                )

            logger.info(f"  [{year}] {len(actas)} actas encontradas")
            return actas

        except Exception as exc:
            logger.error(f"  [{year}] Error: {exc}")
            return []

    def scrape_years(self, years: list[int]) -> list[ActaMetadata]:
        """Scrape metadatos para múltiples años."""
        all_actas: list[ActaMetadata] = []
        for year in years:
            actas = self.get_actas_for_year(year)
            all_actas.extend(actas)
        logger.info(f"Total actas descubiertas: {len(all_actas)}")
        return all_actas

    def download_pdf(self, acta: ActaMetadata, dest_dir: Path) -> ActaMetadata:
        """Descarga un PDF y actualiza el estado de la acta."""
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / str(acta.year) / acta.filename

        if dest_path.exists():
            logger.debug(f"  Ya existe: {dest_path.name}")
            acta.local_path = dest_path
            acta.download_status = "duplicate"
            return acta

        dest_path.parent.mkdir(parents=True, exist_ok=True)
        time.sleep(self.delay)

        try:
            resp = self.session.get(acta.url, stream=True, timeout=self.timeout)
            resp.raise_for_status()

            with dest_path.open("wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

            acta.local_path = dest_path
            acta.download_status = "ok"
            logger.debug(f"  ✓ {dest_path.name} ({dest_path.stat().st_size // 1024} KB)")

        except Exception as exc:
            acta.download_status = "error"
            acta.error_msg = str(exc)
            logger.warning(f"  ✗ {acta.filename}: {exc}")

        return acta

    def bulk_download(
        self,
        actas: list[ActaMetadata],
        dest_dir: Path,
    ) -> dict[str, int]:
        """Descarga masiva de PDFs. Devuelve conteo de resultados."""
        stats = {"ok": 0, "duplicate": 0, "error": 0}
        total = len(actas)

        logger.info(f"Iniciando descarga masiva: {total} archivos → {dest_dir}")
        for i, acta in enumerate(actas, 1):
            logger.info(f"[{i}/{total}] {acta.year}/{acta.filename}")
            self.download_pdf(acta, dest_dir)
            stats[acta.download_status] = stats.get(acta.download_status, 0) + 1

        logger.success(
            f"Descarga completada: {stats['ok']} nuevos, "
            f"{stats['duplicate']} ya existían, {stats['error']} errores"
        )
        return stats


def parse_year_range(spec: str) -> list[int]:
    """Parsea '1998-2025' o '2024' en una lista de años."""
    if "-" in spec and not spec.startswith("-"):
        start, end = map(int, spec.split("-", 1))
        return list(range(start, end + 1))
    return [int(spec)]


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Scraper batch de actas del CFP")
    parser.add_argument("--years", default="1998-2025", help="Rango '1998-2025' o año único '2024'")
    parser.add_argument("--output", default="./data/raw", help="Directorio de destino")
    parser.add_argument("--delay", type=float, default=1.5, help="Delay entre requests (segundos)")
    parser.add_argument("--no-download", action="store_true", help="Solo listar, no descargar")
    args = parser.parse_args()

    years = parse_year_range(args.years)
    scraper = CFPScraper(delay=args.delay)

    logger.info(f"Scraping años {years[0]}–{years[-1]}")
    all_actas = scraper.scrape_years(years)

    if not args.no_download:
        scraper.bulk_download(all_actas, Path(args.output))
    else:
        for a in all_actas:
            print(f"{a.year} | {a.nombre} | {a.url}")
