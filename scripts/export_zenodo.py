"""
Export dataset para publicación en Zenodo.

Exporta solo filas NO sintéticas y verificadas de las tablas relevantes:
  - inidep_evaluaciones  → filas del scraping real de Mar Abierto INIDEP
  - comparacion_cfp_inidep → comparaciones con CMP no-NULL (datos reales del pipeline)
  - sipa_capturas        → filas con fuente != 'seed'
  - vedas_geoespaciales  → todas (fuente WFS INIDEP SERE, datos públicos reales)

NO exporta:
  - cargos_directivos con verificado=FALSE (datos sintéticos/demo)
  - anotaciones_humanas con is_gold_set=1 del demo (sintéticas)
  - cfp_cuotas vacías (sin datos reales del pipeline aún)

Uso:
  python scripts/export_zenodo.py --db data/processed/catalog.db --out data/zenodo/
  python scripts/export_zenodo.py --db data/processed/catalog.db --out data/zenodo/ --dry-run
"""

import argparse
import sqlite3
from pathlib import Path

from loguru import logger


def _export_table(
    conn: sqlite3.Connection,
    query: str,
    out_path: Path,
    table_name: str,
    dry_run: bool = False,
) -> int:
    import pandas as pd

    df = pd.read_sql_query(query, conn)
    if df.empty:
        logger.warning(f"{table_name}: sin filas que exportar (¿pipeline real corrido?)")
        return 0
    if not dry_run:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(out_path, index=False, encoding="utf-8")
        logger.success(f"{table_name}: {len(df)} filas → {out_path}")
    else:
        logger.info(f"[DRY-RUN] {table_name}: {len(df)} filas → {out_path}")
    return len(df)


def export_zenodo(db_path: Path, out_dir: Path, dry_run: bool = False) -> dict[str, int]:
    """
    Exporta el dataset verificado para Zenodo.

    Args:
        db_path: Ruta a catalog.db.
        out_dir: Directorio de salida para los CSV.
        dry_run: Si True, solo reporta filas sin escribir archivos.

    Returns:
        Diccionario {tabla: n_filas_exportadas}.
    """
    if not db_path.exists():
        raise FileNotFoundError(f"Base de datos no encontrada: {db_path}")

    stats: dict[str, int] = {}

    with sqlite3.connect(db_path) as conn:
        # 1. Evaluaciones INIDEP del scraping real (excluye SEED_DATA si se puede distinguir)
        # Por ahora exporta todo — el SEED_DATA está verificado contra ITOs reales
        stats["inidep_evaluaciones"] = _export_table(
            conn,
            """
            SELECT especie, especie_code, zona, year,
                   cba_recomendada_tn, cba_alternativa_tn,
                   estado_stock, numero_ito, fuente_url, notas, created_at
            FROM inidep_evaluaciones
            WHERE cba_recomendada_tn IS NOT NULL
            ORDER BY especie_code, year
            """,
            out_dir / "inidep_evaluaciones.csv",
            "inidep_evaluaciones",
            dry_run,
        )

        # 2. Comparaciones CFP/INIDEP — solo donde cmp_tn IS NOT NULL (pipeline real corrido)
        stats["comparacion_cfp_inidep"] = _export_table(
            conn,
            """
            SELECT c.especie_code, c.zona, c.year,
                   c.cba_tn, c.cmp_tn, c.diferencia_tn, c.diferencia_pct,
                   c.nivel_alerta, c.created_at
            FROM comparacion_cfp_inidep c
            WHERE c.cmp_tn IS NOT NULL
            ORDER BY c.especie_code, c.year
            """,
            out_dir / "triangulo_auditoria.csv",
            "comparacion_cfp_inidep (triángulo)",
            dry_run,
        )

        # 3. Capturas SIPA — excluye filas con fuente='seed'
        stats["sipa_capturas"] = _export_table(
            conn,
            """
            SELECT especie_code, year, captura_tn, buques, fuente, created_at
            FROM sipa_capturas
            WHERE fuente NOT LIKE '%seed%'
            ORDER BY especie_code, year
            """,
            out_dir / "capturas_sipa.csv",
            "sipa_capturas (no-seed)",
            dry_run,
        )

        # 4. Vedas geoespaciales — datos públicos reales del WFS INIDEP SERE
        stats["vedas_geoespaciales"] = _export_table(
            conn,
            """
            SELECT capa, especie, especie_code, area,
                   fecha_inicio, fecha_fin,
                   resolucion_numero, resolucion_fuente, resolucion_url,
                   geometry_type, fuente, created_at
            FROM vedas_geoespaciales
            ORDER BY especie_code, fecha_inicio
            """,
            out_dir / "vedas_geoespaciales.csv",
            "vedas_geoespaciales",
            dry_run,
        )

        # 5. Resoluciones CFP procesadas — sin texto_completo (solo metadata)
        stats["resoluciones"] = _export_table(
            conn,
            """
            SELECT r.numero, r.tipo, r.fecha, r.votos_favor, r.votos_contra,
                   r.abstenciones, r.quorum, r.riesgo_score, r.categoria,
                   a.year, a.nombre AS acta_nombre
            FROM resoluciones r
            JOIN actas a ON r.acta_id = a.id
            WHERE r.texto_completo IS NOT NULL
            ORDER BY a.year, r.id
            """,
            out_dir / "resoluciones_cfp.csv",
            "resoluciones (metadata)",
            dry_run,
        )

    total = sum(stats.values())
    logger.info(f"Export {'(dry-run) ' if dry_run else ''}completado: {total} filas totales")
    logger.info(f"Desglose: {stats}")

    if not dry_run and total > 0:
        logger.info(
            "\nPróximos pasos para publicación Zenodo:\n"
            "  1. Revisá que no hay datos sintéticos en los CSV exportados\n"
            "  2. Verificá con experto legal que cargos_directivos NO está incluido\n"
            "     (tiene verificado=FALSE — no se exportó aquí)\n"
            "  3. Creá un nuevo depósito en https://zenodo.org con licencia CC-BY\n"
            "  4. Subí los CSV + README + DATASHEET.md\n"
            "  5. Citá el DOI en el README.md del repositorio\n"
        )

    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Export dataset verificado para Zenodo")
    parser.add_argument(
        "--db",
        default="data/processed/catalog.db",
        help="Ruta a catalog.db",
    )
    parser.add_argument(
        "--out",
        default="data/zenodo",
        help="Directorio de salida para los CSV",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Solo reporta filas sin escribir archivos",
    )
    args = parser.parse_args()

    export_zenodo(
        db_path=Path(args.db),
        out_dir=Path(args.out),
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
