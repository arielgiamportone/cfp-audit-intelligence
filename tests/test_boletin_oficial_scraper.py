"""Tests para el scraper del Boletín Oficial."""

from unittest.mock import MagicMock, patch

import pytest

from src.acquisition.boletin_oficial_scraper import (
    SEED_CARGOS_DEMO,
    BoletinOficialScraper,
    CargoDirectivo,
    _extraer_nombre,
    _extraer_year,
    _normalize,
    seed_cargos_demo,
)

# ── Helpers ───────────────────────────────────────────────────────────────────


class TestNormalize:
    def test_minusculas(self):
        assert _normalize("ARGENOVA S.A.") == "argenova s.a."

    def test_remueve_acentos(self):
        assert _normalize("Pérez García") == "perez garcia"

    def test_cadena_vacia(self):
        assert _normalize("") == ""


class TestExtraerNombre:
    def test_nombre_simple(self):
        assert _extraer_nombre("Juan García Díaz") == "Juan García Díaz"

    def test_nombre_con_coma(self):
        resultado = _extraer_nombre("Carlos López, DNI 12345678")
        assert "Carlos" in resultado

    def test_fragmento_corto_retorna_none(self):
        assert _extraer_nombre("al") is None

    def test_fragmento_vacio(self):
        assert _extraer_nombre("") is None

    def test_no_capitalizado_retorna_vacio(self):
        # palabras en minúscula no se capturan
        resultado = _extraer_nombre("el gerente")
        assert resultado is None or len(resultado) <= 5


class TestExtraerYear:
    def test_year_presente(self):
        assert _extraer_year("Designado en 2019 por acta") == 2019

    def test_sin_year(self):
        assert _extraer_year("sin fecha") is None

    def test_year_formato_corto_ignorado(self):
        assert _extraer_year("acta 95/23") is None


# ── Scraper ───────────────────────────────────────────────────────────────────


class TestBoletinOficialScraper:
    @pytest.fixture
    def scraper(self):
        return BoletinOficialScraper(timeout=5, delay=0.0)

    def test_instancia_crea_session(self, scraper):
        assert scraper.session is not None

    def test_search_empresa_http_error_retorna_vacio(self, scraper):
        with patch.object(scraper, "_fetch", side_effect=Exception("timeout")):
            resultados = scraper.search_empresa("ARGENOVA S.A.")
        assert resultados == []

    def test_parse_search_results_html_vacio(self, scraper):
        resultados = scraper._parse_search_results("<html></html>", "TEST")
        assert isinstance(resultados, list)

    def test_extract_autoridades_encuentra_presidente(self, scraper):
        html = """
        <html><body>
        <p>Se designa Presidente: Roberto Fernández a partir del 01/01/2020.</p>
        </body></html>
        """
        cargos = scraper.extract_autoridades(html, "TEST S.A.")
        assert any("presidente" in c.cargo for c in cargos)

    def test_extract_autoridades_html_vacio(self, scraper):
        cargos = scraper.extract_autoridades("<html></html>", "TEST")
        assert cargos == []

    def test_extract_autoridades_retorna_lista_cargos(self, scraper):
        html = """
        <html><body>
        <p>Director Titular: María González. Director Suplente: Pedro López.</p>
        </body></html>
        """
        cargos = scraper.extract_autoridades(html, "EMPRESA S.A.")
        assert isinstance(cargos, list)
        assert all(isinstance(c, CargoDirectivo) for c in cargos)

    def test_fetch_cargos_empresa_red_ok(self, scraper, tmp_path):
        db = tmp_path / "test.db"
        mock_resp = MagicMock()
        mock_resp.text = """
        <html><body>
        <article class="resultado">
          <h3>ARGENOVA S.A. — Designación autoridades</h3>
          <time>15/06/2020</time>
          <a href="/norma/detalleAviso?id=123">Ver</a>
          <p>Presidente: Carlos Pérez</p>
        </article>
        </body></html>
        """
        mock_resp.raise_for_status = MagicMock()
        with patch.object(scraper, "_fetch", return_value=mock_resp):
            n = scraper.fetch_cargos_empresa("ARGENOVA S.A.", db)
        assert isinstance(n, int)


# ── Seed data ─────────────────────────────────────────────────────────────────


class TestSeedCargosDemos:
    def test_seed_inserta_registros(self, tmp_path):
        db = tmp_path / "test.db"
        n = seed_cargos_demo(db)
        assert n > 0

    def test_seed_idempotente(self, tmp_path):
        db = tmp_path / "test.db"
        n1 = seed_cargos_demo(db)
        n2 = seed_cargos_demo(db)
        assert n1 > 0
        assert n2 == 0  # segunda llamada no inserta duplicados

    def test_seed_crea_tabla(self, tmp_path):
        import sqlite3

        db = tmp_path / "test.db"
        seed_cargos_demo(db)
        conn = sqlite3.connect(db)
        tablas = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        assert "cargos_directivos" in tablas

    def test_seed_data_tiene_campos_requeridos(self):
        for item in SEED_CARGOS_DEMO:
            assert "persona_nombre" in item
            assert "empresa_nombre" in item
            assert "cargo" in item

    def test_seed_data_count(self):
        assert len(SEED_CARGOS_DEMO) >= 15

    def test_seed_fuente_es_demo(self, tmp_path):
        import sqlite3

        db = tmp_path / "test.db"
        seed_cargos_demo(db)
        conn = sqlite3.connect(db)
        fuentes = {r[0] for r in conn.execute("SELECT DISTINCT fuente FROM cargos_directivos").fetchall()}
        assert "seed_demo" in fuentes
