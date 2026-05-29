"""Router /inidep — evaluaciones científicas y comparaciones CFP vs. CBA."""

import sqlite3

from fastapi import APIRouter, HTTPException, Query

from src.api.deps import DB_PATH
from src.api.models import ComparacionListOut, ComparacionOut, INIDEPEvalOut

router = APIRouter(prefix="/inidep", tags=["inidep"])


def _conn():
    if not DB_PATH.exists():
        raise HTTPException(503, "Base de datos no disponible.")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@router.get("/evaluaciones", summary="Evaluaciones científicas INIDEP")
def list_evaluaciones(
    especie_code: str | None = Query(None),
    year: int | None = Query(None),
    estado_stock: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
):
    filters = []
    params: list = []
    if especie_code:
        filters.append("especie_code = ?")
        params.append(especie_code)
    if year:
        filters.append("year = ?")
        params.append(year)
    if estado_stock:
        filters.append("estado_stock = ?")
        params.append(estado_stock)

    where = ("WHERE " + " AND ".join(filters)) if filters else ""

    with _conn() as conn:
        try:
            rows = conn.execute(
                f"SELECT * FROM inidep_evaluaciones {where} ORDER BY year DESC, especie LIMIT ?",
                params + [limit],
            ).fetchall()
        except sqlite3.OperationalError:
            return {"total": 0, "items": []}

    items = [
        INIDEPEvalOut(
            id=r["id"],
            especie=r["especie"],
            especie_code=r["especie_code"],
            zona=r["zona"],
            year=r["year"],
            cba_recomendada_tn=r["cba_recomendada_tn"],
            estado_stock=r["estado_stock"],
            numero_ito=r["numero_ito"],
        )
        for r in rows
    ]
    return {"total": len(items), "items": items}


@router.get(
    "/comparaciones",
    response_model=ComparacionListOut,
    summary="Comparaciones CMP aprobada vs. CBA recomendada",
)
def list_comparaciones(
    especie_code: str | None = Query(None),
    nivel_alerta: str | None = Query(None, description="verde | amarillo | rojo | critico"),
    year_desde: int | None = Query(None),
    year_hasta: int | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    filters = []
    params: list = []

    if especie_code:
        filters.append("especie_code = ?")
        params.append(especie_code)
    if nivel_alerta:
        filters.append("nivel_alerta = ?")
        params.append(nivel_alerta)
    if year_desde:
        filters.append("year >= ?")
        params.append(year_desde)
    if year_hasta:
        filters.append("year <= ?")
        params.append(year_hasta)

    where = ("WHERE " + " AND ".join(filters)) if filters else ""
    offset = (page - 1) * page_size

    with _conn() as conn:
        try:
            total = conn.execute(
                f"SELECT COUNT(*) FROM comparacion_cfp_inidep {where}", params
            ).fetchone()[0]
            rows = conn.execute(
                f"""SELECT * FROM comparacion_cfp_inidep {where}
                    ORDER BY year DESC, ratio_sobreasignacion DESC
                    LIMIT ? OFFSET ?""",
                params + [page_size, offset],
            ).fetchall()
        except sqlite3.OperationalError:
            return ComparacionListOut(total=0, items=[], page=page, page_size=page_size)

    items = [
        ComparacionOut(
            id=r["id"],
            especie=r["especie"],
            especie_code=r["especie_code"],
            zona=r["zona"],
            year=r["year"],
            cba_inidep_tn=r["cba_inidep_tn"],
            cmp_cfp_tn=r["cmp_cfp_tn"],
            diferencia_tn=r["diferencia_tn"],
            ratio_sobreasignacion=r["ratio_sobreasignacion"],
            nivel_alerta=r["nivel_alerta"],
            descripcion_alerta=r["descripcion_alerta"],
        )
        for r in rows
    ]
    return ComparacionListOut(total=total, items=items, page=page, page_size=page_size)
