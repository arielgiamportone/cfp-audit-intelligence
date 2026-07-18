"""
Puertos del dominio — patrón Hexagonal (Ports & Adapters) + Inversión de Dependencias.

Definimos los **contratos** (puertos) que el dominio necesita de servicios externos,
como `typing.Protocol` **estructural**: las implementaciones concretas (adaptadores)
los cumplen por *duck typing*, sin herencia ni cambios en el código existente.

Esto permite que el código de alto nivel dependa de **abstracciones** (DIP) y no de
tecnologías concretas (Anthropic, ChromaDB), y facilita **tests con dobles** (fakes).

Adaptadores actuales que satisfacen estos puertos:
- `VectorStorePort`  → `src/knowledge_base/vector_store.py::CFPVectorStore` (ChromaDB)
- `AuditorPort`      → `src/analysis/audit_engine.py::CFPAuditEngine` (Claude API)

Ver `docs/adr/012-puertos-hexagonal.md`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class VectorStorePort(Protocol):
    """Puerto de almacén vectorial para RAG (búsqueda semántica e indexación)."""

    def search(self, query: str, n_results: int = 10, **kwargs: Any) -> list[dict]:
        """Devuelve las resoluciones más similares a la consulta."""
        ...

    def add_resolucion(self, *args: Any, **kwargs: Any) -> Any:
        """Indexa una resolución individual."""
        ...

    def add_batch(self, *args: Any, **kwargs: Any) -> Any:
        """Indexa un lote de resoluciones."""
        ...

    def get_by_id(self, doc_id: str) -> dict | None:
        """Recupera un documento por su id (o None)."""
        ...

    def count(self) -> int:
        """Número de documentos indexados."""
        ...

    def index_from_json_dir(self, json_dir: Path, overwrite: bool = False) -> int:
        """Indexa desde un directorio de JSONs; devuelve cuántos se indexaron."""
        ...


@runtime_checkable
class AuditorPort(Protocol):
    """Puerto del motor de auditoría con IA sobre documentos públicos."""

    def analyze_resolucion(self, *args: Any, **kwargs: Any) -> Any:
        """Analiza una resolución y devuelve un resultado estructurado."""
        ...

    def summarize_acta(self, acta_texto: str, filename: str) -> dict[str, Any]:
        """Resume un acta completa."""
        ...

    def detect_patterns(self, resoluciones_texts: list[str]) -> dict[str, Any]:
        """Detecta patrones a partir de un conjunto de resoluciones."""
        ...

    def analyze_sustainability(self, *args: Any, **kwargs: Any) -> Any:
        """Analiza la sostenibilidad por especie."""
        ...
