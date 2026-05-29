"""Router /entidades — especies, empresas y personas mencionadas."""
import sqlite3
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from src.api.models import EntidadOut, EntidadListOut
from src.api.deps import DB_PATH

router = APIRouter(prefix="/entidades", tags=["entidades"])


def _conn():
    if not DB_PATH.exists():
        raise HTTPException(503, "Base de datos no disponible.")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@router.get("", response_model=EntidadListOut, summary="Listar entidades detectadas")
def list_entidades(
    tipo: Optional[str] = Query(None, description="especie | empresa | persona | lugar | normativa | buque"),
    q: Optional[str] = Query(None, description="Búsqueda por nombre"),
    min_menciones: int = Query(1, ge=1),
    limit: int = Query(100, ge=1, le=500),
):
    having = ["COUNT(m.id) >= ?"]
    params: list = [min_menciones]

    if tipo:
        having.append("e.tipo = ?")
        params.append(tipo)
    if q:
        having.append("(e.nombre LIKE ? OR e.nombre_norm LIKE ?)")
        params += [f"%{q}%", f"%{q}%"]

    # SQLite no permite alias en HAVING directamente, usamos la expresión
    having_clause = "HAVING " + " AND ".join(having)

    with _conn() as conn:
        rows = conn.execute(
            f"""SELECT e.id, e.tipo, e.nombre, e.nombre_norm,
                       COUNT(m.id) as m_count
                FROM entidades e
                LEFT JOIN menciones m ON e.id = m.entidad_id
                GROUP BY e.id
                {having_clause}
                ORDER BY m_count DESC
                LIMIT ?""",
            params + [limit],
        ).fetchall()
        total = len(rows)  # sencillo: total = filas ya filtradas

    items = [
        EntidadOut(
            id=r["id"], tipo=r["tipo"], nombre=r["nombre"],
            nombre_norm=r["nombre_norm"], menciones=r["m_count"],
        )
        for r in rows
    ]
    return EntidadListOut(total=total, items=items)


@router.get("/{entidad_id}", response_model=EntidadOut, summary="Detalle de una entidad")
def get_entidad(entidad_id: int):
    with _conn() as conn:
        row = conn.execute(
            """SELECT e.*, COUNT(m.id) as m_count
               FROM entidades e
               LEFT JOIN menciones m ON e.id = m.entidad_id
               WHERE e.id = ?
               GROUP BY e.id""",
            (entidad_id,),
        ).fetchone()
    if not row:
        raise HTTPException(404, f"Entidad {entidad_id} no encontrada")
    return EntidadOut(
        id=row["id"], tipo=row["tipo"], nombre=row["nombre"],
        nombre_norm=row["nombre_norm"], menciones=row["m_count"],
    )
