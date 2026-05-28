"""
Vector store ChromaDB para búsqueda semántica sobre las actas del CFP.

Permite:
  - Indexar resoluciones individuales con sus metadatos
  - Búsqueda semántica multilingüe (español)
  - Filtrado por año, tipo de resolución, especie
  - Recuperación por similitud para análisis RAG con Claude
"""
import json
from pathlib import Path
from typing import Any, Optional

from loguru import logger


COLLECTION_NAME = "cfp_resoluciones"
EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


class CFPVectorStore:
    """Wrapper sobre ChromaDB para el corpus de actas del CFP."""

    def __init__(
        self,
        persist_dir: Path | str = "data/knowledge_base",
        embedding_model: str = EMBEDDING_MODEL,
        collection_name: str = COLLECTION_NAME,
    ):
        self.persist_dir = Path(persist_dir)
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self.collection_name = collection_name
        self._client = None
        self._collection = None
        self._embed_fn = None
        self._embedding_model = embedding_model

    def _get_client(self):
        if self._client is None:
            import chromadb
            self._client = chromadb.PersistentClient(path=str(self.persist_dir))
        return self._client

    def _get_embed_fn(self):
        if self._embed_fn is None:
            from chromadb.utils import embedding_functions
            self._embed_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name=self._embedding_model
            )
        return self._embed_fn

    def _get_collection(self):
        if self._collection is None:
            client = self._get_client()
            self._collection = client.get_or_create_collection(
                name=self.collection_name,
                embedding_function=self._get_embed_fn(),
                metadata={"hnsw:space": "cosine"},
            )
        return self._collection

    # ── Indexación ────────────────────────────────────────────────────────

    def add_resolucion(
        self,
        doc_id: str,
        texto: str,
        metadata: dict[str, Any],
    ) -> None:
        """Indexa una resolución individual."""
        collection = self._get_collection()
        collection.upsert(
            ids=[doc_id],
            documents=[texto],
            metadatas=[_sanitize_metadata(metadata)],
        )

    def add_batch(
        self,
        ids: list[str],
        texts: list[str],
        metadatas: list[dict],
        batch_size: int = 32,
    ) -> int:
        """Indexa en lotes. Retorna número de documentos indexados."""
        collection = self._get_collection()
        total = 0
        for i in range(0, len(ids), batch_size):
            batch_ids = ids[i : i + batch_size]
            batch_docs = texts[i : i + batch_size]
            batch_meta = [_sanitize_metadata(m) for m in metadatas[i : i + batch_size]]
            collection.upsert(ids=batch_ids, documents=batch_docs, metadatas=batch_meta)
            total += len(batch_ids)
            logger.debug(f"  Indexados {total}/{len(ids)} documentos")
        return total

    # ── Búsqueda ─────────────────────────────────────────────────────────

    def search(
        self,
        query: str,
        n_results: int = 10,
        where: Optional[dict] = None,
        year_from: Optional[int] = None,
        year_to: Optional[int] = None,
        tipo: Optional[str] = None,
    ) -> list[dict]:
        """
        Búsqueda semántica. Retorna lista de resultados con texto y metadatos.

        Args:
            query: Consulta en lenguaje natural
            n_results: Número de resultados
            where: Filtro ChromaDB nativo
            year_from / year_to: Filtro temporal
            tipo: Filtro por tipo de resolución
        """
        collection = self._get_collection()

        # Construir filtro
        filters: list[dict] = []
        if where:
            filters.append(where)
        if year_from:
            filters.append({"year": {"$gte": year_from}})
        if year_to:
            filters.append({"year": {"$lte": year_to}})
        if tipo:
            filters.append({"tipo": {"$eq": tipo}})

        where_clause = None
        if len(filters) == 1:
            where_clause = filters[0]
        elif len(filters) > 1:
            where_clause = {"$and": filters}

        kwargs = {"query_texts": [query], "n_results": n_results}
        if where_clause:
            kwargs["where"] = where_clause

        results = collection.query(**kwargs)

        return [
            {
                "id": results["ids"][0][i],
                "texto": results["documents"][0][i],
                "metadata": results["metadatas"][0][i],
                "distance": results["distances"][0][i],
            }
            for i in range(len(results["ids"][0]))
        ]

    def get_by_id(self, doc_id: str) -> Optional[dict]:
        collection = self._get_collection()
        result = collection.get(ids=[doc_id], include=["documents", "metadatas"])
        if result["ids"]:
            return {
                "id": result["ids"][0],
                "texto": result["documents"][0],
                "metadata": result["metadatas"][0],
            }
        return None

    def count(self) -> int:
        return self._get_collection().count()

    def delete_collection(self) -> None:
        """Elimina y reinicia la colección (para reindexar desde cero)."""
        client = self._get_client()
        try:
            client.delete_collection(self.collection_name)
        except Exception:
            pass
        self._collection = None
        logger.warning(f"Colección '{self.collection_name}' eliminada")

    # ── Indexación desde JSON parseado ────────────────────────────────────

    def index_from_json_dir(self, json_dir: Path, overwrite: bool = False) -> int:
        """Indexa resoluciones desde directorio de JSONs parseados."""
        json_dir = Path(json_dir)
        if overwrite:
            self.delete_collection()

        ids, texts, metas = [], [], []
        seen_ids: set[str] = set()

        for json_path in sorted(json_dir.rglob("*.json")):
            try:
                data = json.loads(json_path.read_text(encoding="utf-8"))
                acta_filename = data.get("filename", json_path.stem)
                year = data.get("year", 0)

                # Path relativo al json_dir garantiza unicidad global (incluye año/subdir)
                rel = json_path.relative_to(json_dir)
                acta_key = str(rel.with_suffix("")).replace("\\", "/").replace(" ", "_")[:60]

                for i, res in enumerate(data.get("resoluciones", [])):
                    texto = res.get("texto", "").strip()
                    if not texto:
                        continue

                    base_id = f"{acta_key}_{res['numero']}"
                    # Resolver colisiones residuales con índice secuencial
                    doc_id = base_id
                    if doc_id in seen_ids:
                        doc_id = f"{base_id}_{i}"
                    seen_ids.add(doc_id)

                    ids.append(doc_id)
                    texts.append(texto)
                    metas.append({
                        "year": year,
                        "numero": res.get("numero", ""),
                        "tipo": res.get("tipo", "otro"),
                        "fecha_acta": res.get("fecha_acta") or "",
                        "acta_filename": acta_filename,
                        "especies": ", ".join(res.get("especies_mencionadas", [])),
                        "empresas": ", ".join(res.get("empresas_mencionadas", []))[:500],
                    })
            except Exception as exc:
                logger.error(f"Error indexando {json_path.name}: {exc}")

        if ids:
            count = self.add_batch(ids, texts, metas)
            logger.info(f"Knowledge base: {count} resoluciones indexadas")
            return count
        return 0


def _sanitize_metadata(meta: dict) -> dict:
    """ChromaDB solo acepta str, int, float, bool en metadatos."""
    sanitized = {}
    for k, v in meta.items():
        if isinstance(v, (str, int, float, bool)):
            sanitized[k] = v
        elif v is None:
            sanitized[k] = ""
        elif isinstance(v, list):
            sanitized[k] = ", ".join(str(x) for x in v)
        else:
            sanitized[k] = str(v)
    return sanitized
