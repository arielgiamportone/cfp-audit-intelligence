"""
Catálogo SQLite de actas: registro de metadatos, estado de procesamiento y hash.

Provee trazabilidad completa del pipeline desde PDF hasta análisis.
"""
import hashlib
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Generator, Optional

from loguru import logger


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS actas (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    year        INTEGER NOT NULL,
    nombre      TEXT NOT NULL,
    url         TEXT NOT NULL UNIQUE,
    filename    TEXT NOT NULL,
    is_anexo    BOOLEAN DEFAULT FALSE,
    local_path  TEXT,
    file_hash   TEXT,
    file_size   INTEGER,
    download_status TEXT DEFAULT 'pending',
    text_extracted  BOOLEAN DEFAULT FALSE,
    text_path       TEXT,
    parsed          BOOLEAN DEFAULT FALSE,
    embedded        BOOLEAN DEFAULT FALSE,
    analyzed        BOOLEAN DEFAULT FALSE,
    scraped_at      TEXT,
    downloaded_at   TEXT,
    processed_at    TEXT,
    error_msg       TEXT
);

CREATE TABLE IF NOT EXISTS resoluciones (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    acta_id         INTEGER REFERENCES actas(id),
    numero          TEXT,
    tipo            TEXT,
    fecha           TEXT,
    texto_completo  TEXT,
    texto_resumen   TEXT,
    votos_favor     INTEGER,
    votos_contra    INTEGER,
    abstenciones    INTEGER,
    quorum          INTEGER,
    riesgo_score    REAL,
    categoria       TEXT,
    analisis_ia     TEXT,
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS entidades (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    tipo        TEXT NOT NULL,    -- especie | empresa | persona | lugar | normativa
    nombre      TEXT NOT NULL,
    nombre_norm TEXT NOT NULL,    -- normalizado (minúsculas, sin acentos)
    UNIQUE(tipo, nombre_norm)
);

CREATE TABLE IF NOT EXISTS menciones (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    resolucion_id   INTEGER REFERENCES resoluciones(id),
    entidad_id      INTEGER REFERENCES entidades(id),
    contexto        TEXT,
    sentimiento     TEXT    -- positivo | negativo | neutral
);

CREATE TABLE IF NOT EXISTS analisis_sesiones (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    acta_id         INTEGER REFERENCES actas(id),
    tipo_analisis   TEXT,
    resultado       TEXT,   -- JSON
    modelo_ia       TEXT,
    tokens_usados   INTEGER,
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_actas_year    ON actas(year);
CREATE INDEX IF NOT EXISTS idx_actas_status  ON actas(download_status);
CREATE INDEX IF NOT EXISTS idx_res_acta      ON resoluciones(acta_id);
CREATE INDEX IF NOT EXISTS idx_res_tipo      ON resoluciones(tipo);
CREATE INDEX IF NOT EXISTS idx_menciones_ent ON menciones(entidad_id);
"""


class CatalogManager:
    """Gestor del catálogo SQLite de actas y entidades del CFP."""

    def __init__(self, db_path: Path | str = "data/processed/catalog.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _conn(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.executescript(SCHEMA_SQL)
        logger.debug(f"Catálogo inicializado: {self.db_path}")

    # ── Actas ──────────────────────────────────────────────────────────────

    def upsert_acta(self, acta_data: dict[str, Any]) -> int:
        """Inserta o actualiza metadatos de un acta. Retorna id."""
        acta_data.setdefault("scraped_at", datetime.utcnow().isoformat())
        with self._conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO actas (year, nombre, url, filename, is_anexo, scraped_at)
                VALUES (:year, :nombre, :url, :filename, :is_anexo, :scraped_at)
                ON CONFLICT(url) DO UPDATE SET
                    nombre=excluded.nombre,
                    scraped_at=excluded.scraped_at
                RETURNING id
                """,
                acta_data,
            )
            row = cur.fetchone()
            return row[0]

    def mark_downloaded(self, url: str, local_path: Path) -> None:
        file_hash = self._hash_file(local_path)
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE actas SET
                    local_path=?, file_hash=?, file_size=?,
                    download_status='ok', downloaded_at=?
                WHERE url=?
                """,
                (
                    str(local_path),
                    file_hash,
                    local_path.stat().st_size,
                    datetime.utcnow().isoformat(),
                    url,
                ),
            )

    def mark_processed(self, acta_id: int, text_path: Path) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE actas SET
                    text_extracted=TRUE, text_path=?, processed_at=?
                WHERE id=?
                """,
                (str(text_path), datetime.utcnow().isoformat(), acta_id),
            )

    def mark_embedded(self, acta_id: int) -> None:
        with self._conn() as conn:
            conn.execute("UPDATE actas SET embedded=TRUE WHERE id=?", (acta_id,))

    def mark_analyzed(self, acta_id: int) -> None:
        with self._conn() as conn:
            conn.execute("UPDATE actas SET analyzed=TRUE WHERE id=?", (acta_id,))

    def get_pending(self, stage: str = "download") -> list[sqlite3.Row]:
        """Retorna actas pendientes para una etapa: download | process | embed | analyze."""
        filters = {
            "download": "download_status='pending'",
            "process": "download_status='ok' AND text_extracted=FALSE",
            "embed": "text_extracted=TRUE AND embedded=FALSE",
            "analyze": "embedded=TRUE AND analyzed=FALSE",
        }
        where = filters.get(stage, "download_status='pending'")
        with self._conn() as conn:
            return conn.execute(f"SELECT * FROM actas WHERE {where}").fetchall()

    def stats(self) -> dict[str, Any]:
        with self._conn() as conn:
            total = conn.execute("SELECT COUNT(*) FROM actas").fetchone()[0]
            downloaded = conn.execute(
                "SELECT COUNT(*) FROM actas WHERE download_status='ok'"
            ).fetchone()[0]
            processed = conn.execute(
                "SELECT COUNT(*) FROM actas WHERE text_extracted=TRUE"
            ).fetchone()[0]
            embedded = conn.execute(
                "SELECT COUNT(*) FROM actas WHERE embedded=TRUE"
            ).fetchone()[0]
            analyzed = conn.execute(
                "SELECT COUNT(*) FROM actas WHERE analyzed=TRUE"
            ).fetchone()[0]
            by_year = conn.execute(
                "SELECT year, COUNT(*) as n FROM actas GROUP BY year ORDER BY year"
            ).fetchall()
        return {
            "total": total,
            "downloaded": downloaded,
            "processed": processed,
            "embedded": embedded,
            "analyzed": analyzed,
            "by_year": {r["year"]: r["n"] for r in by_year},
        }

    # ── Resoluciones ──────────────────────────────────────────────────────

    def insert_resolucion(self, data: dict[str, Any]) -> int:
        with self._conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO resoluciones
                    (acta_id, numero, tipo, fecha, texto_completo, texto_resumen,
                     votos_favor, votos_contra, abstenciones, quorum, categoria)
                VALUES
                    (:acta_id, :numero, :tipo, :fecha, :texto_completo, :texto_resumen,
                     :votos_favor, :votos_contra, :abstenciones, :quorum, :categoria)
                """,
                data,
            )
            return cur.lastrowid

    def update_resolucion_analisis(
        self, resolucion_id: int, riesgo_score: float, analisis_ia: str
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE resoluciones SET riesgo_score=?, analisis_ia=? WHERE id=?",
                (riesgo_score, analisis_ia, resolucion_id),
            )

    # ── Entidades ─────────────────────────────────────────────────────────

    def upsert_entidad(self, tipo: str, nombre: str) -> int:
        nombre_norm = self._normalize(nombre)
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO entidades (tipo, nombre, nombre_norm)
                VALUES (?, ?, ?)
                ON CONFLICT(tipo, nombre_norm) DO NOTHING
                """,
                (tipo, nombre, nombre_norm),
            )
            row = conn.execute(
                "SELECT id FROM entidades WHERE tipo=? AND nombre_norm=?",
                (tipo, nombre_norm),
            ).fetchone()
            return row[0]

    def insert_mencion(
        self,
        resolucion_id: int,
        entidad_id: int,
        contexto: Optional[str] = None,
        sentimiento: Optional[str] = None,
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO menciones (resolucion_id, entidad_id, contexto, sentimiento) VALUES (?,?,?,?)",
                (resolucion_id, entidad_id, contexto, sentimiento),
            )

    # ── Análisis de sesiones ──────────────────────────────────────────────

    def insert_analisis(
        self,
        acta_id: int,
        tipo_analisis: str,
        resultado: str,
        modelo_ia: str,
        tokens_usados: int = 0,
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO analisis_sesiones
                    (acta_id, tipo_analisis, resultado, modelo_ia, tokens_usados)
                VALUES (?, ?, ?, ?, ?)
                """,
                (acta_id, tipo_analisis, resultado, modelo_ia, tokens_usados),
            )

    # ── Utilidades ────────────────────────────────────────────────────────

    @staticmethod
    def _hash_file(path: Path) -> str:
        h = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()

    @staticmethod
    def _normalize(text: str) -> str:
        import unicodedata
        nfkd = unicodedata.normalize("NFKD", text.lower())
        return "".join(c for c in nfkd if not unicodedata.combining(c)).strip()
