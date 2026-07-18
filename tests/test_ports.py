"""Conformidad de adaptadores con los puertos del dominio (Hexagonal / DIP).

Verifica que las implementaciones concretas satisfacen el contrato de su puerto
(`src/ports.py`). Ver ADR-012. Los tests se saltan si faltan las dependencias
pesadas (chromadb / anthropic), para no bloquear entornos mínimos.
"""

import pytest

from src.ports import AuditorPort, VectorStorePort

VECTOR_STORE_METHODS = [
    "search",
    "add_resolucion",
    "add_batch",
    "get_by_id",
    "count",
    "index_from_json_dir",
]

AUDITOR_METHODS = [
    "analyze_resolucion",
    "summarize_acta",
    "detect_patterns",
    "analyze_sustainability",
]


def test_vector_store_port_declara_metodos():
    # El puerto declara el contrato esperado.
    assert set(VECTOR_STORE_METHODS) <= set(dir(VectorStorePort))


def test_auditor_port_declara_metodos():
    assert set(AUDITOR_METHODS) <= set(dir(AuditorPort))


def test_cfp_vector_store_cumple_puerto():
    pytest.importorskip("chromadb")
    from src.knowledge_base.vector_store import CFPVectorStore

    for m in VECTOR_STORE_METHODS:
        assert hasattr(CFPVectorStore, m), (
            f"CFPVectorStore no implementa '{m}' del VectorStorePort"
        )


def test_cfp_audit_engine_cumple_puerto():
    pytest.importorskip("anthropic")
    from src.analysis.audit_engine import CFPAuditEngine

    for m in AUDITOR_METHODS:
        assert hasattr(CFPAuditEngine, m), (
            f"CFPAuditEngine no implementa '{m}' del AuditorPort"
        )
