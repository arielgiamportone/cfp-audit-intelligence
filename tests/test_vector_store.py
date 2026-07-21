"""
Tests del vector store (`CFPVectorStore`) — la capa RAG del proyecto.

No requiere ChromaDB ni sentence-transformers (imports perezosos): se inyecta una
colección simulada y se mockea `add_batch`. Cubre la sanitización de metadatos, la
construcción del filtro de búsqueda, el mapeo de resultados y la indexación desde JSON
(incluida la resolución de colisiones de IDs y el salto de textos vacíos).
"""

import json
from unittest.mock import MagicMock

from src.knowledge_base.vector_store import CFPVectorStore, _sanitize_metadata


class TestSanitizeMetadata:
    def test_tipos_escalares_se_conservan(self):
        out = _sanitize_metadata({"a": "x", "b": 1, "c": 1.5, "d": True})
        assert out == {"a": "x", "b": 1, "c": 1.5, "d": True}

    def test_none_se_convierte_en_cadena_vacia(self):
        assert _sanitize_metadata({"z": None}) == {"z": ""}

    def test_lista_se_une_con_comas(self):
        assert _sanitize_metadata({"esp": ["merluza", "centolla"]}) == {"esp": "merluza, centolla"}

    def test_otros_tipos_a_str(self):
        assert _sanitize_metadata({"o": {"k": 1}})["o"] == str({"k": 1})


def _store_with_collection(tmp_path, collection):
    vs = CFPVectorStore(persist_dir=tmp_path)
    vs._collection = collection  # inyecta colección simulada (evita ChromaDB)
    return vs


class TestSearch:
    def test_filtro_unico_y_mapeo_de_resultados(self, tmp_path):
        coll = MagicMock()
        coll.query.return_value = {
            "ids": [["a", "b"]],
            "documents": [["texto uno", "texto dos"]],
            "metadatas": [[{"year": 2024}, {"year": 2025}]],
            "distances": [[0.1, 0.2]],
        }
        vs = _store_with_collection(tmp_path, coll)
        out = vs.search("merluza", n_results=2, tipo="cuota_captura")

        assert len(out) == 2
        assert out[0] == {"id": "a", "texto": "texto uno", "metadata": {"year": 2024}, "distance": 0.1}
        # un solo filtro → se pasa directo (sin envolver en $and)
        assert coll.query.call_args.kwargs["where"] == {"tipo": {"$eq": "cuota_captura"}}

    def test_multiples_filtros_se_combinan_con_and(self, tmp_path):
        coll = MagicMock()
        coll.query.return_value = {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}
        vs = _store_with_collection(tmp_path, coll)
        vs.search("q", year_from=2000, year_to=2020)
        assert coll.query.call_args.kwargs["where"] == {
            "$and": [{"year": {"$gte": 2000}}, {"year": {"$lte": 2020}}]
        }

    def test_sin_filtros_no_pasa_where(self, tmp_path):
        coll = MagicMock()
        coll.query.return_value = {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}
        vs = _store_with_collection(tmp_path, coll)
        vs.search("q")
        assert "where" not in coll.query.call_args.kwargs


class TestIndexFromJsonDir:
    def test_indexa_resuelve_colisiones_y_salta_vacios(self, tmp_path, monkeypatch):
        json_dir = tmp_path / "json"
        json_dir.mkdir()
        (json_dir / "acta1.json").write_text(
            json.dumps(
                {
                    "filename": "acta1.pdf",
                    "year": 2024,
                    "resoluciones": [
                        {"numero": "1", "texto": "texto uno", "tipo": "cuota_captura",
                         "especies_mencionadas": ["merluza"]},
                        {"numero": "1", "texto": "texto dos"},  # colisión de número
                        {"numero": "2", "texto": "   "},        # vacío → se salta
                    ],
                }
            ),
            encoding="utf-8",
        )

        captured = {}
        vs = CFPVectorStore(persist_dir=tmp_path)

        def _fake_add_batch(ids, texts, metas, **kwargs):
            captured["ids"] = ids
            captured["texts"] = texts
            captured["metas"] = metas
            return len(ids)

        monkeypatch.setattr(vs, "add_batch", _fake_add_batch)

        n = vs.index_from_json_dir(json_dir)

        assert n == 2  # el de texto vacío se omite
        assert len(set(captured["ids"])) == 2  # IDs únicos (colisión resuelta)
        assert "merluza" in captured["metas"][0]["especies"]
        assert captured["metas"][0]["year"] == 2024
