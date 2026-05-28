"""
CLI para scraping del repositorio Mar Abierto del INIDEP.

Modos de uso:
  python scripts/scrape_inidep.py --mode metadata          # Solo metadatos (rápido)
  python scripts/scrape_inidep.py --mode full              # Metadatos + PDFs (lento)
  python scripts/scrape_inidep.py --mode species --query "merluza"
  python scripts/scrape_inidep.py --count                  # Ver total disponible
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import click
from loguru import logger

from src.acquisition.inidep_scraper import INIDEPScraper, ITORecord
from src.analysis.inidep_comparator import INIDEPComparator

DB_PATH = ROOT / "data" / "processed" / "catalog.db"


def _ito_to_evaluacion(rec: ITORecord) -> dict:
    """Convierte un ITORecord al formato que acepta inidep_evaluaciones."""
    year = rec.año_evaluacion or rec.año_publicacion
    if not year:
        return None
    especie = rec.especie_norm or rec.especie_raw
    if not especie:
        return None
    return {
        "especie": rec.especie_raw or especie,
        "especie_code": especie,
        "zona": rec.zona,
        "year": year,
        "cba_recomendada_tn": rec.cba_recomendada_tn,
        "cba_alternativa_tn": rec.cmp_alternativa_tn,
        "estado_stock": rec.estado_stock,
        "numero_ito": rec.numero_ito,
        "fuente_url": rec.url,
        "notas": (rec.abstract or "")[:300] if rec.abstract else rec.titulo[:200],
    }


@click.command()
@click.option("--mode", type=click.Choice(["metadata", "full", "species", "count"]),
              default="metadata", show_default=True,
              help="Modo de scraping: metadata (rápido), full (con PDFs), species, count")
@click.option("--query", default="", help="Query para búsqueda por especie (modo species)")
@click.option("--limit", default=None, type=int, help="Límite de ITOs a scrapear")
@click.option("--delay", default=1.0, type=float, show_default=True,
              help="Delay entre requests (segundos)")
@click.option("--db", default=str(DB_PATH), help="Path a catalog.db")
@click.option("--dry-run", is_flag=True, help="No guardar en BD, solo mostrar resultados")
def main(mode, query, limit, delay, db, dry_run):
    """Scrapea los ITOs del repositorio Mar Abierto del INIDEP y los guarda en catalog.db."""

    scraper = INIDEPScraper(delay=delay)
    db_path = Path(db)

    if mode == "count":
        total = scraper.get_total_itos()
        click.echo(f"Total ITOs disponibles en Mar Abierto: {total}")
        return

    if mode == "species":
        if not query:
            click.echo("Error: --query requerido en modo 'species'", err=True)
            sys.exit(1)
        click.echo(f"Buscando ITOs para: '{query}'")
        records = scraper.scrape_species(query, max_results=limit or 20)
    else:
        click.echo(f"Iniciando scraping en modo '{mode}' (delay={delay}s)...")
        records = scraper.scrape_all_metadata(max_items=limit)

        if mode == "full":
            click.echo(f"Enriqueciendo {len(records)} registros con PDFs...")
            enriched = []
            for i, rec in enumerate(records, 1):
                if rec.cba_recomendada_tn is None:
                    rec = scraper.enrich_with_pdf(rec)
                enriched.append(rec)
                if i % 10 == 0:
                    click.echo(f"  {i}/{len(records)} procesados")
            records = enriched

    # Estadísticas
    with_cba = sum(1 for r in records if r.cba_recomendada_tn is not None)
    with_especie = sum(1 for r in records if r.especie_raw)
    click.echo(f"\nResultados: {len(records)} ITOs")
    click.echo(f"  Con especie identificada: {with_especie} ({with_especie/len(records)*100:.0f}%)")
    click.echo(f"  Con CBA extraída:         {with_cba} ({with_cba/len(records)*100:.0f}%)")

    if dry_run:
        click.echo("\n[dry-run] Primeros 5 registros:")
        for rec in records[:5]:
            click.echo(f"  - {rec.titulo[:70]}")
            click.echo(f"    Especie: {rec.especie_norm} | Año: {rec.año_evaluacion} | CBA: {rec.cba_recomendada_tn}")
        return

    # Guardar en BD
    if not db_path.parent.exists():
        db_path.parent.mkdir(parents=True, exist_ok=True)

    comp = INIDEPComparator(db_path)
    saved = 0
    skipped = 0

    for rec in records:
        eva = _ito_to_evaluacion(rec)
        if not eva:
            skipped += 1
            continue
        try:
            comp.upsert_inidep_evaluacion(eva)
            saved += 1
        except Exception as exc:
            logger.warning(f"Error guardando '{rec.titulo[:50]}': {exc}")
            skipped += 1

    click.echo(f"\nGuardados en BD: {saved} | Omitidos (sin especie/año): {skipped}")
    click.echo(f"Base de datos: {db_path}")


if __name__ == "__main__":
    main()
