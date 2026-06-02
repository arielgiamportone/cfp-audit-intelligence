"""Tests para el script de sincronización del conteo de tests."""

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "update_test_count.py"

# Cargar el script como módulo (no es un paquete importable)
_spec = importlib.util.spec_from_file_location("update_test_count", SCRIPT_PATH)
update_test_count = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(update_test_count)

update_text = update_test_count.update_text


class TestUpdateText:
    def test_badge_shields(self):
        original = "[![Tests: 609](https://img.shields.io/badge/tests-609%20passing-brightgreen.svg)](#tests)"
        result = update_text(original, 852)
        assert "tests-852%20passing" in result
        assert "Tests: 852" in result
        assert "609" not in result

    def test_badge_no_se_rompe_url(self):
        # El segmento tests-N%20passing debe conservarse completo (regresión)
        original = "https://img.shields.io/badge/tests-609%20passing-brightgreen.svg"
        result = update_text(original, 852)
        assert result == "https://img.shields.io/badge/tests-852%20passing-brightgreen.svg"

    def test_tests_pasando(self):
        assert update_text("**609 tests pasando**", 852) == "**852 tests pasando**"

    def test_tests_totales(self):
        assert update_text("- [x] 763 tests totales, todos verdes", 852) == (
            "- [x] 852 tests totales, todos verdes"
        )

    def test_tests_todos_verdes(self):
        assert update_text("664 tests, todos verdes (pytest)", 852) == (
            "852 tests, todos verdes (pytest)"
        )

    def test_actualmente(self):
        assert update_text("pytest  # todos (609 actualmente)", 852) == (
            "pytest  # todos (852 actualmente)"
        )

    def test_modulos_frase(self):
        assert update_text("El proyecto tiene 609 tests y ~50 módulos.", 852) == (
            "El proyecto tiene 852 tests y ~50 módulos."
        )

    def test_no_toca_conteos_granulares(self):
        # Los conteos por archivo ("N tests en file") NO deben cambiar
        original = "- [x] 25 tests en `test_report_generator.py`"
        assert update_text(original, 852) == original

    def test_idempotente(self):
        original = "**609 tests pasando** y 763 tests totales"
        una_vez = update_text(original, 852)
        dos_veces = update_text(una_vez, 852)
        assert una_vez == dos_veces
        assert "609" not in una_vez
        assert "763" not in una_vez


class TestGetTestCount:
    def test_parsea_linea_collected(self, monkeypatch):
        class _Result:
            stdout = "tests/test_x.py::test_a\n852 tests collected in 0.50s\n"
            stderr = ""

        monkeypatch.setattr(
            update_test_count.subprocess, "run", lambda *a, **k: _Result()
        )
        assert update_test_count.get_test_count() == 852

    def test_fallback_cuenta_ids(self, monkeypatch):
        class _Result:
            stdout = "tests/test_x.py::test_a\ntests/test_x.py::test_b\n"
            stderr = ""

        monkeypatch.setattr(
            update_test_count.subprocess, "run", lambda *a, **k: _Result()
        )
        assert update_test_count.get_test_count() == 2

    def test_count_singular_plural(self, monkeypatch):
        class _Result:
            stdout = "1 test collected in 0.1s\n"
            stderr = ""

        monkeypatch.setattr(
            update_test_count.subprocess, "run", lambda *a, **k: _Result()
        )
        assert update_test_count.get_test_count() == 1
