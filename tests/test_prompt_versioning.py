"""Tests para versionado de prompts y reproducibilidad de analisis_sesiones."""

import sqlite3
from pathlib import Path

import pytest

from src.acquisition.catalog_manager import CatalogManager
from src.evaluation.groundedness import sha16 as _sha16


@pytest.fixture
def catalog(tmp_path) -> CatalogManager:
    return CatalogManager(tmp_path / "test.db")


class TestSha16:
    def test_mismo_input_mismo_hash(self):
        assert _sha16("texto de prueba") == _sha16("texto de prueba")

    def test_distinto_input_distinto_hash(self):
        assert _sha16("texto A") != _sha16("texto B")

    def test_longitud_16(self):
        assert len(_sha16("cualquier texto")) == 16

    def test_solo_hexadecimal(self):
        h = _sha16("texto")
        assert all(c in "0123456789abcdef" for c in h)

    def test_vacio(self):
        h = _sha16("")
        assert len(h) == 16


class TestAnalisisSesionesColumnas:
    def test_columnas_nuevas_existen(self, catalog):
        with sqlite3.connect(catalog.db_path) as conn:
            cols = [r[1] for r in conn.execute(
                "PRAGMA table_info(analisis_sesiones)"
            ).fetchall()]
        assert "prompt_hash" in cols
        assert "input_hash" in cols
        assert "temperatura" in cols

    def test_insert_analisis_con_hashes(self, catalog, tmp_path):
        acta_id = catalog.upsert_acta({
            "year": 2024, "nombre": "ACTA 1/2024",
            "url": "https://cfp.gob.ar/test1", "filename": "test1.pdf", "is_anexo": False,
        })
        prompt_hash = _sha16("system_prompt" + "user_prompt")
        input_hash = _sha16("texto fuente del acta")

        catalog.insert_analisis(
            acta_id=acta_id,
            tipo_analisis="resolucion",
            resultado='{"riesgo_score": 50}',
            modelo_ia="claude-sonnet-4-6",
            tokens_usados=1000,
            prompt_hash=prompt_hash,
            input_hash=input_hash,
            temperatura=0.1,
        )

        with sqlite3.connect(catalog.db_path) as conn:
            row = conn.execute(
                "SELECT prompt_hash, input_hash, temperatura FROM analisis_sesiones "
                "WHERE acta_id=?",
                (acta_id,),
            ).fetchone()

        assert row[0] == prompt_hash
        assert row[1] == input_hash
        assert abs(row[2] - 0.1) < 0.001

    def test_insert_sin_hashes_acepta_null(self, catalog):
        acta_id = catalog.upsert_acta({
            "year": 2024, "nombre": "ACTA 2/2024",
            "url": "https://cfp.gob.ar/test2", "filename": "test2.pdf", "is_anexo": False,
        })
        catalog.insert_analisis(
            acta_id=acta_id,
            tipo_analisis="resolucion",
            resultado="{}",
            modelo_ia="claude-sonnet-4-6",
        )
        with sqlite3.connect(catalog.db_path) as conn:
            row = conn.execute(
                "SELECT prompt_hash, input_hash FROM analisis_sesiones WHERE acta_id=?",
                (acta_id,),
            ).fetchone()
        assert row[0] is None
        assert row[1] is None


class TestPromptRegistry:
    def test_tabla_existe(self, catalog):
        with sqlite3.connect(catalog.db_path) as conn:
            tables = [r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()]
        assert "prompt_registry" in tables

    def test_upsert_retorna_id(self, catalog):
        rid = catalog.upsert_prompt_registro(
            nombre="audit_resolucion_v1",
            version="1.0.0",
            modelo="claude-sonnet-4-6",
            system_hash=_sha16("system_prompt"),
            user_template="Analiza la resolución: {texto}",
            user_hash=_sha16("Analiza la resolución: {texto}"),
            temperatura=0.1,
            tokens_max=4096,
            notas="Prompt inicial de auditoría",
        )
        assert isinstance(rid, int)
        assert rid > 0

    def test_upsert_idempotente(self, catalog):
        kwargs = dict(
            nombre="audit_resolucion_v2",
            version="2.0.0",
            modelo="claude-sonnet-4-6",
            system_hash=_sha16("system"),
            user_template="template",
            user_hash=_sha16("template"),
        )
        id1 = catalog.upsert_prompt_registro(**kwargs)
        id2 = catalog.upsert_prompt_registro(**kwargs)
        assert id1 == id2

    def test_upsert_actualiza_version(self, catalog):
        catalog.upsert_prompt_registro(
            nombre="audit_test",
            version="1.0",
            modelo="claude-sonnet-4-6",
            system_hash="abc",
            user_template="t",
            user_hash="def",
        )
        catalog.upsert_prompt_registro(
            nombre="audit_test",
            version="2.0",  # actualizado
            modelo="claude-opus-4-7",
            system_hash="xyz",
            user_template="t2",
            user_hash="uvw",
        )
        with sqlite3.connect(catalog.db_path) as conn:
            row = conn.execute(
                "SELECT version, modelo FROM prompt_registry WHERE nombre='audit_test'"
            ).fetchone()
        assert row[0] == "2.0"
        assert row[1] == "claude-opus-4-7"


class TestAnotacionesHumanas:
    def test_tabla_existe(self, catalog):
        with sqlite3.connect(catalog.db_path) as conn:
            tables = [r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()]
        assert "anotaciones_humanas" in tables

    def test_upsert_anotacion(self, catalog):
        acta_id = catalog.upsert_acta({
            "year": 2024, "nombre": "ACTA 3/2024",
            "url": "https://cfp.gob.ar/test3", "filename": "test3.pdf", "is_anexo": False,
        })
        res_id = catalog.insert_resolucion({
            "acta_id": acta_id, "numero": "001", "tipo": "cuota_captura",
            "fecha": "2024-01-01", "texto_completo": "texto de prueba",
            "texto_resumen": "", "votos_favor": 5, "votos_contra": 2,
            "abstenciones": 0, "quorum": 7, "categoria": "medio",
        })
        ann_id = catalog.upsert_anotacion(
            resolucion_id=res_id,
            anotador="experto_1",
            categoria_ia="medio",
            categoria_humana="alto",
            riesgo_score_ia=55.0,
            riesgo_score_humano=72,
            notas="El modelo subestimó el riesgo",
            confianza_pct=85,
            is_gold_set=True,
        )
        assert isinstance(ann_id, int)
        assert ann_id > 0

    def test_coincide_categoria_calculado(self, catalog):
        acta_id = catalog.upsert_acta({
            "year": 2024, "nombre": "ACTA 4/2024",
            "url": "https://cfp.gob.ar/test4", "filename": "test4.pdf", "is_anexo": False,
        })
        res_id = catalog.insert_resolucion({
            "acta_id": acta_id, "numero": "002", "tipo": "cuota_captura",
            "fecha": "2024-01-01", "texto_completo": "texto",
            "texto_resumen": "", "votos_favor": 5, "votos_contra": 0,
            "abstenciones": 0, "quorum": 5, "categoria": "bajo",
        })
        catalog.upsert_anotacion(
            res_id, "experto_1",
            categoria_ia="bajo", categoria_humana="bajo",
        )
        with sqlite3.connect(catalog.db_path) as conn:
            row = conn.execute(
                "SELECT coincide_categoria FROM anotaciones_humanas WHERE resolucion_id=?",
                (res_id,),
            ).fetchone()
        assert row[0] == 1  # True en SQLite

    def test_get_anotaciones_gold_set(self, catalog):
        # Crear una anotación gold
        acta_id = catalog.upsert_acta({
            "year": 2024, "nombre": "ACTA 5/2024",
            "url": "https://cfp.gob.ar/test5", "filename": "test5.pdf", "is_anexo": False,
        })
        res_id = catalog.insert_resolucion({
            "acta_id": acta_id, "numero": "003", "tipo": "cuota_captura",
            "fecha": "2024-01-01", "texto_completo": "texto gold",
            "texto_resumen": "", "votos_favor": 5, "votos_contra": 0,
            "abstenciones": 0, "quorum": 5, "categoria": "critico",
        })
        catalog.upsert_anotacion(res_id, "gold_sintetico", is_gold_set=True)
        rows = catalog.get_anotaciones(solo_gold=True)
        assert len(rows) >= 1
