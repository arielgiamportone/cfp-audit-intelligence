"""Router /actas — listado, detalle y búsqueda de actas CFP."""
import sqlite3
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from src.api.models import ActaOut, ActaListOut, ResolucionOut, ResolucionListOut
from src.api.deps import DB_PATH

router = APIRouter(prefix="/actas", tags=["actas"])


def _conn():
    if not DB_PATH.exists():
        raise HTTPException(503, "Base de datos no disponible. Ejecuta el pipeline primero.")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@router.get("", response_model=ActaListOut, summary="Listar actas del CFP")
def list_actas(
    year: Optional[int] = Query(None, description="Filtrar por año"),
    descargadas: Optional[bool] = Query(None, description="Solo actas descargadas"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    """Retorna el catálogo de actas del CFP con paginación."""
    filters = []
    params: list = []

    if year is not None:
        filters.append("year = ?")
        params.append(year)
    if descargadas is not None:
        filters.append("download_status = ?")
        params.append("downloaded" if descargadas else "pending")

    where = ("WHERE " + " AND ".join(filters)) if filters else ""
    offset = (page - 1) * page_size

    with _conn() as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM actas {where}", params).fetchone()[0]
        rows = conn.execute(
            f"SELECT * FROM actas {where} ORDER BY year DESC, nombre LIMIT ? OFFSET ?",
            params + [page_size, offset],
        ).fetchall()

    items = [
        ActaOut(
            id=r["id"],
            year=r["year"],
            nombre=r["nombre"],
            url=r["url"],
            filename=r["filename"],
            download_status=r["download_status"],
            text_extracted=bool(r["text_extracted"]),
            embedded=bool(r["embedded"]),
            analyzed=bool(r["analyzed"]),
        )
        for r in rows
    ]
    return ActaListOut(total=total, items=items, page=page, page_size=page_size)


@router.get("/{acta_id}", response_model=ActaOut, summary="Detalle de un acta")
def get_acta(acta_id: int):
    with _conn() as conn:
        row = conn.execute("SELECT * FROM actas WHERE id = ?", (acta_id,)).fetchone()
    if not row:
        raise HTTPException(404, f"Acta {acta_id} no encontrada")
    return ActaOut(
        id=row["id"], year=row["year"], nombre=row["nombre"],
        url=row["url"], filename=row["filename"],
        download_status=row["download_status"],
        text_extracted=bool(row["text_extracted"]),
        embedded=bool(row["embedded"]),
        analyzed=bool(row["analyzed"]),
    )


@router.get("/{acta_id}/resoluciones", response_model=ResolucionListOut,
            summary="Resoluciones de un acta")
def get_resoluciones(
    acta_id: int,
    categoria: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    with _conn() as conn:
        # Verificar que el acta existe
        acta = conn.execute("SELECT id, year FROM actas WHERE id = ?", (acta_id,)).fetchone()
        if not acta:
            raise HTTPException(404, f"Acta {acta_id} no encontrada")

        filters = ["r.acta_id = ?"]
        params: list = [acta_id]
        if categoria:
            filters.append("r.categoria = ?")
            params.append(categoria)

        where = "WHERE " + " AND ".join(filters)
        offset = (page - 1) * page_size

        total = conn.execute(
            f"SELECT COUNT(*) FROM resoluciones r {where}", params
        ).fetchone()[0]
        rows = conn.execute(
            f"""SELECT r.*, a.year FROM resoluciones r
                JOIN actas a ON r.acta_id = a.id
                {where} ORDER BY r.id LIMIT ? OFFSET ?""",
            params + [page_size, offset],
        ).fetchall()

    items = [
        ResolucionOut(
            id=r["id"], acta_id=r["acta_id"], numero=r["numero"],
            tipo=r["tipo"], categoria=r["categoria"],
            texto_resumen=r["texto_resumen"],
            votos_favor=r["votos_favor"], votos_contra=r["votos_contra"],
            quorum=r["quorum"], riesgo_score=r["riesgo_score"],
            year=r["year"],
        )
        for r in rows
    ]
    return ResolucionListOut(total=total, items=items, page=page, page_size=page_size)
