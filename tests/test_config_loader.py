"""Tests para el loader centralizado de configuración (settings.yaml)."""

import textwrap

import pytest

from src.config_loader import (
    DEFAULT_UMBRALES_CMP_CBA,
    get_umbrales_cmp_cba,
    load_settings,
)


@pytest.fixture(autouse=True)
def _clear_cache():
    """Limpia el cache LRU antes de cada test para aislar."""
    load_settings.cache_clear()
    yield
    load_settings.cache_clear()


class TestLoadSettings:
    def test_archivo_inexistente_retorna_vacio(self, tmp_path):
        assert load_settings(tmp_path / "no_existe.yaml") == {}

    def test_carga_yaml_valido(self, tmp_path):
        p = tmp_path / "settings.yaml"
        p.write_text("comparador:\n  umbrales_cmp_cba:\n    amarillo_min: 1.05\n")
        settings = load_settings(p)
        assert settings["comparador"]["umbrales_cmp_cba"]["amarillo_min"] == 1.05

    def test_yaml_malformado_retorna_vacio(self, tmp_path):
        p = tmp_path / "bad.yaml"
        p.write_text("comparador:\n  - : : malformado : :\n   bad indent")
        # No debe lanzar excepción
        result = load_settings(p)
        assert isinstance(result, dict)


class TestGetUmbralesCmpCba:
    def test_defaults_cuando_no_hay_archivo(self, tmp_path):
        umbrales = get_umbrales_cmp_cba(tmp_path / "no_existe.yaml")
        assert umbrales == DEFAULT_UMBRALES_CMP_CBA

    def test_lee_valores_custom(self, tmp_path):
        p = tmp_path / "settings.yaml"
        p.write_text(
            textwrap.dedent(
                """
                comparador:
                  umbrales_cmp_cba:
                    amarillo_min: 1.02
                    rojo_min: 1.20
                    critico_min: 1.40
                """
            )
        )
        umbrales = get_umbrales_cmp_cba(p)
        assert umbrales["amarillo_min"] == 1.02
        assert umbrales["rojo_min"] == 1.20
        assert umbrales["critico_min"] == 1.40

    def test_fallback_parcial(self, tmp_path):
        # Solo define amarillo_min; rojo y critico usan default
        p = tmp_path / "settings.yaml"
        p.write_text("comparador:\n  umbrales_cmp_cba:\n    amarillo_min: 1.03\n")
        umbrales = get_umbrales_cmp_cba(p)
        assert umbrales["amarillo_min"] == 1.03
        assert umbrales["rojo_min"] == DEFAULT_UMBRALES_CMP_CBA["rojo_min"]
        assert umbrales["critico_min"] == DEFAULT_UMBRALES_CMP_CBA["critico_min"]

    def test_orden_umbrales_coherente(self, tmp_path):
        umbrales = get_umbrales_cmp_cba(tmp_path / "no_existe.yaml")
        assert umbrales["amarillo_min"] < umbrales["rojo_min"] < umbrales["critico_min"]

    def test_retorna_floats(self, tmp_path):
        umbrales = get_umbrales_cmp_cba(tmp_path / "no_existe.yaml")
        for v in umbrales.values():
            assert isinstance(v, float)

    def test_settings_real_del_repo(self):
        # El settings.yaml del repo debe tener los umbrales documentados
        umbrales = get_umbrales_cmp_cba()
        assert umbrales["amarillo_min"] == 1.00
        assert umbrales["rojo_min"] == 1.15
        assert umbrales["critico_min"] == 1.30
