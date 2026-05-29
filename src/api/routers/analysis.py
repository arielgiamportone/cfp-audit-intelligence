"""Router /analysis — NER sobre texto y búsqueda semántica en la KB."""

import sqlite3

from fastapi import APIRouter, HTTPException

from src.api.deps import DB_PATH
from src.api.models import NEREntidadOut, NERRequest, NERResponse

router = APIRouter(prefix="/analysis", tags=["analysis"])


@router.post("/ner", response_model=NERResponse, summary="Extraer entidades pesqueras de texto")
def extract_ner(req: NERRequest):
    """
    Aplica el NER pesquero especializado al texto enviado.
    Detecta: ESPECIE_PESCA, EMPRESA_PESCA, ZONA_PESCA, CUOTA_PESCA,
    NORMATIVA_CFP, BUQUE_PESCA.
    """
    try:
        from src.processing.ner_pesquero import get_ner
    except ImportError:
        raise HTTPException(503, "spaCy no disponible en este entorno.")

    ner = get_ner()
    resultado = ner.process(req.texto)
    d = resultado.to_dict()

    return NERResponse(
        especies=d["especies"],
        empresas=d["empresas"],
        zonas=d["zonas"],
        cuotas=d["cuotas"],
        normativas=d["normativas"],
        buques=d["buques"],
        entidades_raw=[
            NEREntidadOut(
                texto=e.texto,
                etiqueta=e.etiqueta,
                inicio=e.inicio,
                fin=e.fin,
            )
            for e in resultado.entidades
        ],
    )


@router.get("/stats", summary="Estadísticas generales del catálogo")
def get_stats():
    """Retorna métricas globales del sistema."""
    if not DB_PATH.exists():
        return {
            "total_actas": 0,
            "actas_descargadas": 0,
            "actas_procesadas": 0,
            "actas_analizadas": 0,
            "total_resoluciones": 0,
            "total_entidades": 0,
            "total_menciones": 0,
            "años_cubiertos": [],
            "alertas_abiertas": 0,
            "alertas_criticas": 0,
        }

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    try:
        total_actas = conn.execute("SELECT COUNT(*) FROM actas").fetchone()[0]
        actas_desc = conn.execute(
            "SELECT COUNT(*) FROM actas WHERE download_status='downloaded'"
        ).fetchone()[0]
        actas_proc = conn.execute("SELECT COUNT(*) FROM actas WHERE text_extracted=1").fetchone()[0]
        actas_anal = conn.execute("SELECT COUNT(*) FROM actas WHERE analyzed=1").fetchone()[0]
    except sqlite3.OperationalError:
        total_actas = actas_desc = actas_proc = actas_anal = 0

    try:
        total_res = conn.execute("SELECT COUNT(*) FROM resoluciones").fetchone()[0]
    except sqlite3.OperationalError:
        total_res = 0

    try:
        total_ent = conn.execute("SELECT COUNT(*) FROM entidades").fetchone()[0]
        total_men = conn.execute("SELECT COUNT(*) FROM menciones").fetchone()[0]
    except sqlite3.OperationalError:
        total_ent = total_men = 0

    try:
        años = [
            r[0]
            for r in conn.execute(
                "SELECT DISTINCT year FROM actas WHERE year IS NOT NULL ORDER BY year"
            ).fetchall()
        ]
    except sqlite3.OperationalError:
        años = []

    conn.close()

    # Alertas
    alertas_abiertas = alertas_criticas = 0
    try:
        from src.analysis.alert_engine import AlertEngine

        engine = AlertEngine(db_path=DB_PATH)
        s = engine.get_summary()
        alertas_abiertas = s["total"]
        alertas_criticas = s["criticas"]
    except Exception:
        pass

    return {
        "total_actas": total_actas,
        "actas_descargadas": actas_desc,
        "actas_procesadas": actas_proc,
        "actas_analizadas": actas_anal,
        "total_resoluciones": total_res,
        "total_entidades": total_ent,
        "total_menciones": total_men,
        "años_cubiertos": años,
        "alertas_abiertas": alertas_abiertas,
        "alertas_criticas": alertas_criticas,
    }
