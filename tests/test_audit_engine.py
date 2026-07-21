"""
Tests del motor de auditoría IA (`CFPAuditEngine`).

Cubre el parseo de la respuesta del LLM, la construcción del resultado y el manejo
de errores **sin llamadas reales a la API** (se mockea `_call_claude`). Es la pieza
central del pipeline y hasta ahora no tenía test dedicado.

Se omite si el SDK `anthropic` no está instalado.
"""

from unittest.mock import MagicMock

import pytest

pytest.importorskip("anthropic")

from src.analysis.audit_engine import CFPAuditEngine, _extract_json  # noqa: E402


def _fake_response(text: str, model: str = "claude-sonnet-4-6", ti: int = 100, to: int = 50):
    resp = MagicMock()
    resp.content = [MagicMock(text=text)]
    resp.model = model
    resp.usage = MagicMock(input_tokens=ti, output_tokens=to)
    return resp


class TestExtractJson:
    def test_json_puro(self):
        assert _extract_json('{"a": 1}') == {"a": 1}

    def test_json_embebido_en_prosa(self):
        assert _extract_json('Aquí tienes: {"a": 1, "b": "x"} — fin')["b"] == "x"

    def test_sin_json_marca_error(self):
        out = _extract_json("no hay json aquí")
        assert out["parse_error"] is True
        assert "raw_response" in out


class TestInit:
    def test_sin_api_key_lanza(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        with pytest.raises(ValueError):
            CFPAuditEngine(api_key=None)

    def test_con_api_key(self):
        eng = CFPAuditEngine(api_key="sk-test-123")
        assert eng.api_key == "sk-test-123"
        assert eng.client is not None


class TestAnalyzeResolucion:
    def _engine(self):
        return CFPAuditEngine(api_key="sk-test-123")

    def test_happy_path_parsea_y_construye_resultado(self):
        eng = self._engine()
        payload = (
            '{"riesgo_score": 75, "categoria_riesgo": "alto", '
            '"hallazgos": ["La CMP aprobada de merluza supera la CBA recomendada"], '
            '"indicios": ["posible presión de flota"], "recomendaciones": ["verificar acta"], '
            '"normativa_afectada": ["Ley 24.922 Art. 9"], "entidades_beneficiadas": [], '
            '"especies_afectadas": ["merluza"]}'
        )
        # Mockea la llamada al LLM (evita red y el retry de tenacity)
        eng._call_claude = MagicMock(return_value=_fake_response(payload))

        texto = (
            "Se aprueba la CMP de merluza común en 350.000 toneladas para 2025, "
            "superando la CBA recomendada por el INIDEP."
        )
        res = eng.analyze_resolucion("2025_1", texto)

        assert res.riesgo_score == 75.0
        assert res.categoria_riesgo == "alto"
        assert res.especies_afectadas == ["merluza"]
        assert res.tokens_entrada == 100
        assert res.tokens_salida == 50
        assert res.modelo_usado == "claude-sonnet-4-6"
        # Reproducibilidad
        assert res.prompt_hash and len(res.prompt_hash) == 16
        assert res.input_hash and len(res.input_hash) == 16
        # Groundedness calculada sobre los hallazgos
        assert isinstance(res.hallazgos, list) and len(res.hallazgos) == 1
        assert isinstance(res.groundedness_scores, list)

    def test_prompt_hash_determinista(self):
        eng = self._engine()
        eng._call_claude = MagicMock(return_value=_fake_response('{"riesgo_score": 0}'))
        r1 = eng.analyze_resolucion("id", "mismo texto")
        r2 = eng.analyze_resolucion("id", "mismo texto")
        assert r1.input_hash == r2.input_hash
        assert r1.prompt_hash == r2.prompt_hash

    def test_error_en_llm_devuelve_categoria_error(self):
        eng = self._engine()
        eng._call_claude = MagicMock(side_effect=RuntimeError("fallo de red"))
        res = eng.analyze_resolucion("x", "texto de prueba")
        assert res.categoria_riesgo == "error"
        assert res.riesgo_score == 0
        assert "ERROR" in res.analisis_completo
