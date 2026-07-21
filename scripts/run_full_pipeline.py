"""
Pipeline end-to-end del CFP Audit Intelligence.

Etapas:
  1. download      → Scrape y descarga todos los PDFs
  2. process       → Extrae texto y parsea resoluciones
  3. knowledge_base → Construye el vector store
  4. audit         → Corre análisis IA sobre resoluciones
  5. inidep        → Scrapea ITOs de INIDEP Mar Abierto (492 ITOs)
  6. geovisor      → Descarga vedas geoespaciales SERE (INIDEP)
  7. conae         → Muestrea esfuerzo satelital GFW + SST + Clorofila (CONAE)

Uso:
  python scripts/run_full_pipeline.py --years 1998-2025
  python scripts/run_full_pipeline.py --step download --years 2020-2025
  python scripts/run_full_pipeline.py --step audit --limit 100
  python scripts/run_full_pipeline.py --step conae
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
from loguru import logger

load_dotenv(ROOT / ".env")


def step_download(years: list[int], raw_dir: Path, db_path: Path, limit: int = 0) -> None:
    from src.acquisition.batch_scraper import CFPScraper
    from src.acquisition.catalog_manager import CatalogManager

    logger.info(f"=== ETAPA 1: DESCARGA ({years[0]}–{years[-1]}) ===")
    catalog = CatalogManager(db_path)
    scraper = CFPScraper(delay=1.5)

    actas = scraper.scrape_years(years)
    if limit:
        actas = actas[:limit]
        logger.info(f"Límite aplicado: se descargarán {len(actas)} actas (muestra)")
    for acta in actas:
        catalog.upsert_acta(
            {
                "year": acta.year,
                "nombre": acta.nombre,
                "url": acta.url,
                "filename": acta.filename,
                "is_anexo": acta.is_anexo,
            }
        )

    stats = scraper.bulk_download(actas, raw_dir)
    for acta in actas:
        if acta.download_status == "ok" and acta.local_path:
            catalog.mark_downloaded(acta.url, acta.local_path)

    logger.success(f"Descarga completada: {stats}")


def step_process(raw_dir: Path, processed_dir: Path, db_path: Path) -> None:
    from src.acquisition.catalog_manager import CatalogManager
    from src.processing.document_parser import batch_parse
    from src.processing.pdf_extractor import batch_extract

    logger.info("=== ETAPA 2: PROCESAMIENTO ===")
    catalog = CatalogManager(db_path)

    text_dir = processed_dir / "text"
    json_dir = processed_dir / "json"

    # Extracción de texto
    logger.info("Extrayendo texto de PDFs...")
    stats_extract = batch_extract(raw_dir, text_dir)
    logger.info(f"Extracción: {stats_extract}")

    # Parseo estructural
    logger.info("Parseando estructura de documentos...")
    count = batch_parse(text_dir, json_dir)
    logger.success(f"Parseados {count} documentos")

    # Marcar procesados en catálogo
    marked = 0
    for acta in catalog.get_pending("process"):
        acta_id = acta["id"]
        local_path = Path(acta["local_path"])
        try:
            rel = local_path.relative_to(raw_dir)
            text_path = text_dir / rel.with_suffix(".txt")
            if text_path.exists():
                catalog.mark_processed(acta_id, text_path)
                marked += 1
        except (ValueError, Exception):
            pass
    logger.info(f"Marcadas {marked} actas como procesadas en catálogo")

    logger.success("Procesamiento completado")


def step_knowledge_base(processed_dir: Path, kb_dir: Path) -> None:
    from src.knowledge_base.vector_store import CFPVectorStore

    logger.info("=== ETAPA 3: KNOWLEDGE BASE ===")
    json_dir = processed_dir / "json"

    if not json_dir.exists():
        logger.error(f"Directorio {json_dir} no encontrado. Ejecuta primero el procesamiento.")
        return

    vs = CFPVectorStore(persist_dir=kb_dir)
    count = vs.index_from_json_dir(json_dir, overwrite=False)
    logger.success(f"Knowledge Base construida: {count:,} resoluciones indexadas")


def step_inidep(db_path: Path, max_items: int | None = None, enrich_pdf: bool = False) -> None:
    """Scrapea los ITOs de INIDEP Mar Abierto y los persiste en inidep_evaluaciones."""
    from src.acquisition.inidep_scraper import INIDEPScraper, get_scrape_status

    logger.info("=== ETAPA INIDEP: SCRAPING MAR ABIERTO (492 ITOs) ===")
    scraper = INIDEPScraper(delay=1.5)

    if enrich_pdf:
        logger.info("Modo enrichment PDF activado (más lento, mayor cobertura CBA)")

    n = scraper.scrape_and_save(str(db_path), max_items=max_items)
    status = get_scrape_status(db_path)

    logger.success(
        f"INIDEP completado: {n} ITOs nuevos | "
        f"Total en DB: {status['n_total']} | "
        f"Con CBA: {status['n_con_cba']} | "
        f"Especies: {len(status['especies_cubiertas'])}"
    )


def step_geovisor(db_path: Path) -> None:
    """Descarga vedas geoespaciales del geovisor SERE (INIDEP) y las cruza contra el corpus."""
    from src.acquisition.inidep_geovisor_scraper import SEREGeovisorClient
    from src.analysis.geovisor_cross_validator import GeovisorCrossValidator

    logger.info("=== ETAPA GEOVISOR: VEDAS GEOESPACIALES SERE (INIDEP) ===")
    client = SEREGeovisorClient(delay=1.0)
    n = client.scrape_and_save_vedas(db_path)

    validador = GeovisorCrossValidator(db_path)
    resumen = validador.cobertura_summary()

    logger.success(
        f"Geovisor completado: {n} zonas de veda nuevas | "
        f"Cobertura corpus (fuente CFP): {resumen['encontradas_en_corpus']}/"
        f"{resumen['total_resoluciones_citadas_cfp']} ({resumen['pct_cobertura']}%)"
    )


def step_conae(db_path: Path) -> None:
    """Muestrea capas satelitales del geoportal marino CONAE y cruza con vedas (ADR-010)."""
    from src.acquisition.conae_marine_scraper import CONAEMarineClient
    from src.analysis.geovisor_cross_validator import GeovisorCrossValidator

    logger.info("=== ETAPA CONAE: ESFUERZO PESQUERO SATELITAL (GFW AIS + SST + Clorofila) ===")
    client = CONAEMarineClient(delay=0.5)
    n = client.scrape_and_save(db_path)

    validador = GeovisorCrossValidator(db_path)
    resultado = validador.validar_cumplimiento_satelital()

    if "error" not in resultado:
        logger.success(
            f"CONAE completado: {n} registros nuevos | "
            f"Esfuerzo dentro/fuera veda: "
            f"{resultado['mediana_esfuerzo_dentro']:.2f}/{resultado['mediana_esfuerzo_fuera']:.2f} "
            f"(ratio={resultado['ratio_reduccion']})"
        )
    else:
        logger.success(f"CONAE completado: {n} registros nuevos | {resultado['error']}")


def step_audit(db_path: Path, kb_dir: Path, limit: int = 0) -> None:
    import json
    import os

    from src.acquisition.catalog_manager import CatalogManager
    from src.analysis.audit_engine import CFPAuditEngine
    from src.knowledge_base.vector_store import CFPVectorStore

    logger.info(f"=== ETAPA 4: AUDITORÍA IA (límite: {limit or 'sin límite'}) ===")

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.error("ANTHROPIC_API_KEY no configurada. Omitiendo etapa de auditoría.")
        return

    catalog = CatalogManager(db_path)
    engine = CFPAuditEngine(api_key=api_key)
    vs = CFPVectorStore(kb_dir)

    if vs.count() == 0:
        logger.error("Knowledge Base vacía. Ejecuta primero la etapa knowledge_base.")
        return

    # Obtener actas pendientes de análisis
    pending = catalog.get_pending("analyze")
    if limit:
        pending = pending[:limit]

    logger.info(f"Actas pendientes de análisis: {len(pending)}")

    for row in pending:
        acta_id = row["id"]
        filename = row["filename"]

        # Buscar resoluciones en KB para esta acta
        results = vs.search(filename, n_results=10, where={"acta_filename": {"$eq": filename}})

        if not results:
            catalog.mark_analyzed(acta_id)
            continue

        # Analizar cada resolución
        analisis_results = []
        for r in results:
            audit = engine.analyze_resolucion(r["id"], r["texto"])
            analisis_results.append(
                {
                    "id": r["id"],
                    "riesgo_score": audit.riesgo_score,
                    "categoria": audit.categoria_riesgo,
                    "hallazgos": audit.hallazgos,
                }
            )

            # Guardar en catálogo
            catalog.insert_analisis(
                acta_id=acta_id,
                tipo_analisis="resolucion",
                resultado=json.dumps(
                    {"riesgo_score": audit.riesgo_score, "hallazgos": audit.hallazgos},
                    ensure_ascii=False,
                ),
                modelo_ia=audit.modelo_usado,
                tokens_usados=audit.tokens_entrada + audit.tokens_salida,
            )

        catalog.mark_analyzed(acta_id)
        max_risk = max((a["riesgo_score"] for a in analisis_results), default=0)
        logger.info(
            f"  {filename}: {len(analisis_results)} resoluciones, riesgo máx: {max_risk:.0f}"
        )

    logger.success("Auditoría completada")


def main():
    parser = argparse.ArgumentParser(description="CFP Audit Intelligence Pipeline")
    parser.add_argument(
        "--step",
        choices=["download", "process", "knowledge_base", "audit", "inidep", "geovisor", "conae", "all"],
        default="all",
        help="Etapa del pipeline a ejecutar",
    )
    parser.add_argument(
        "--enrich-pdf",
        action="store_true",
        help="[--step inidep] Descargar PDFs para enriquecer CBA cuando no está en abstract",
    )
    parser.add_argument("--years", default="1998-2025", help="Rango de años (ej: 2020-2025)")
    parser.add_argument("--limit", type=int, default=0, help="Límite de documentos a procesar")
    parser.add_argument(
        "--data-dir",
        default=None,
        help="Directorio base de datos (por defecto: rutas del proyecto, iguales a las del dashboard)",
    )
    args = parser.parse_args()

    # Rutas: por defecto se usan las MISMAS que consume el dashboard (config_loader),
    # de modo que el corpus poblado por el pipeline sea el que la app muestra —
    # independientemente del directorio de trabajo (cwd). Ver ADR-001/DRY (Unidad 1).
    from src.config_loader import get_db_path, get_kb_dir

    if args.data_dir:
        data_dir = Path(args.data_dir).resolve()
        processed_dir = data_dir / "processed"
        db_path = processed_dir / "catalog.db"
        kb_dir = data_dir / "knowledge_base"
    else:
        db_path = get_db_path()
        kb_dir = get_kb_dir()
        processed_dir = db_path.parent
        data_dir = processed_dir.parent
    raw_dir = data_dir / "raw"
    logger.info(f"Rutas → db={db_path} | kb={kb_dir} | raw={raw_dir}")

    # Parsear años
    if "-" in args.years:
        start, end = map(int, args.years.split("-", 1))
        years = list(range(start, end + 1))
    else:
        years = [int(args.years)]

    steps = (
        ["download", "process", "knowledge_base", "audit"] if args.step == "all" else [args.step]
    )

    logger.info(f"Pipeline CFP Audit Intelligence | Pasos: {steps}")

    if "download" in steps:
        step_download(years, raw_dir, db_path, limit=args.limit)
    if "process" in steps:
        step_process(raw_dir, processed_dir, db_path)
    if "knowledge_base" in steps:
        step_knowledge_base(processed_dir, kb_dir)
    if "audit" in steps:
        step_audit(db_path, kb_dir, limit=args.limit)
    if "inidep" in steps:
        step_inidep(
            db_path,
            max_items=args.limit or None,
            enrich_pdf=args.enrich_pdf,
        )
    if "geovisor" in steps:
        step_geovisor(db_path)
    if "conae" in steps:
        step_conae(db_path)

    logger.success("Pipeline completado.")


if __name__ == "__main__":
    main()
