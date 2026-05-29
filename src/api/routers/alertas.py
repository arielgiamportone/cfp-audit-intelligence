"""Router /alertas — historial y reglas del sistema de alertas."""

from fastapi import APIRouter, HTTPException, Query

from src.api.deps import DB_PATH, get_alert_engine
from src.api.models import AlertaListOut, AlertaOut

router = APIRouter(prefix="/alertas", tags=["alertas"])


@router.get("", response_model=AlertaListOut, summary="Listar alertas")
def list_alertas(
    severidad: str | None = Query(None, description="info | warning | critical"),
    solo_abiertas: bool = Query(True),
    especie_code: str | None = Query(None),
    year_desde: int | None = Query(None),
    year_hasta: int | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
):
    """Retorna el historial de alertas con filtros opcionales."""
    if not DB_PATH.exists():
        raise HTTPException(503, "Base de datos no disponible.")

    engine = get_alert_engine()
    df = engine.get_historial(
        severidad_min=severidad,
        solo_abiertas=solo_abiertas,
        especie_code=especie_code,
        year_desde=year_desde,
        year_hasta=year_hasta,
        limit=limit,
    )

    if df.empty:
        return AlertaListOut(total=0, items=[])

    items = [
        AlertaOut(
            id=int(row["id"]),
            tipo=row["tipo"],
            especie=row.get("especie"),
            zona=row.get("zona"),
            year=int(row["year"]) if row.get("year") else None,
            valor_detectado=row.get("valor_detectado"),
            umbral=row.get("umbral"),
            mensaje=row["mensaje"],
            severidad=row["severidad"],
            acta_referencia=row.get("acta_referencia"),
            resuelta=bool(row.get("resuelta", False)),
            created_at=row.get("created_at"),
            regla_nombre=row.get("regla_nombre"),
        )
        for _, row in df.iterrows()
    ]
    return AlertaListOut(total=len(items), items=items)


@router.post("/evaluar", summary="Ejecutar evaluación de alertas")
def evaluar_alertas(limpiar_previas: bool = Query(False)):
    """Evalúa todas las reglas activas y genera nuevas alertas."""
    if not DB_PATH.exists():
        raise HTTPException(503, "Base de datos no disponible.")
    engine = get_alert_engine()
    alertas = engine.evaluate(clear_previous=limpiar_previas)
    summary = engine.get_summary()
    return {
        "alertas_generadas": len(alertas),
        "criticas": summary["criticas"],
        "warnings": summary["warnings"],
        "total_abiertas": summary["total"],
    }


@router.patch("/{alerta_id}/resolver", summary="Marcar alerta como resuelta")
def resolver_alerta(alerta_id: int):
    if not DB_PATH.exists():
        raise HTTPException(503, "Base de datos no disponible.")
    engine = get_alert_engine()
    engine.resolve_alerta(alerta_id)
    return {"ok": True, "alerta_id": alerta_id}


@router.get("/resumen", summary="Resumen del estado de alertas")
def resumen_alertas():
    if not DB_PATH.exists():
        return {"total": 0, "criticas": 0, "warnings": 0, "info": 0, "n_reglas": 0}
    engine = get_alert_engine()
    return engine.get_summary()
