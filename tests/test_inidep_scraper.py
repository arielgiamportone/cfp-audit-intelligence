"""
Tests del módulo de scraping del INIDEP.

Verifica el SEED_DATA, funciones de extracción y normalización de especies,
sin hacer llamadas de red reales.
"""
import pytest

from src.acquisition.inidep_scraper import (
    SEED_DATA,
    ESPECIES_INTERES,
    ITORecord,
    _extract_especie,
    _extract_zona,
    _normalize_especie,
)


# ── SEED_DATA ─────────────────────────────────────────────────────────────────

class TestSeedData:
    def test_no_vacio(self):
        assert len(SEED_DATA) > 0

    def test_campos_obligatorios(self):
        required = {"especie", "especie_code", "year"}
        for rec in SEED_DATA:
            assert required.issubset(rec.keys()), f"Faltan campos en: {rec}"

    def test_años_razonables(self):
        for rec in SEED_DATA:
            assert 2000 <= rec["year"] <= 2030, f"Año inválido: {rec['year']}"

    def test_cba_positiva_o_none(self):
        for rec in SEED_DATA:
            cba = rec.get("cba_recomendada_tn")
            if cba is not None:
                assert cba > 0, f"CBA no positiva: {rec}"

    def test_especie_code_sin_espacios(self):
        for rec in SEED_DATA:
            assert " " not in rec["especie_code"], \
                f"especie_code tiene espacios: {rec['especie_code']}"

    def test_merluza_hubbsi_presente(self):
        codes = {r["especie_code"] for r in SEED_DATA}
        assert "merluza_hubbsi" in codes

    def test_merluza_sur_cba_conocida(self):
        """Merluza Sur 41°S 2024 debe tener CBA del ITO 36/2024."""
        merluza_sur = [
            r for r in SEED_DATA
            if r["especie_code"] == "merluza_hubbsi"
            and r.get("zona") == "Sur 41°S"
            and r["year"] == 2024
        ]
        assert len(merluza_sur) == 1
        assert merluza_sur[0]["cba_recomendada_tn"] == 319_000

    def test_merluza_norte_sobrexplotado(self):
        """Merluza Norte 41°S debe indicar estado sobrexplotado."""
        merluza_norte = [
            r for r in SEED_DATA
            if r["especie_code"] == "merluza_hubbsi"
            and r.get("zona") == "Norte 41°S"
        ]
        assert len(merluza_norte) >= 1
        assert merluza_norte[0]["estado_stock"] == "sobrexplotado"


# ── _extract_especie ──────────────────────────────────────────────────────────

class TestExtractEspecie:
    def test_merluza(self):
        assert _extract_especie("Evaluación de merluza hubbsi 2024") == "merluza"

    def test_langostino(self):
        assert _extract_especie("Informe sobre langostino patagónico") == "langostino"

    def test_calamar(self):
        assert _extract_especie("Pesquería de calamar illex en el Mar Argentino") == "calamar"

    def test_centolla(self):
        assert _extract_especie("Evaluación de centolla en la zona austral") == "centolla"

    def test_vieira(self):
        assert _extract_especie("Recurso vieira en plataforma patagónica") == "vieira"

    def test_merluza_negra(self):
        assert _extract_especie("Informe de merluza negra sub-antártica") == "merluza negra"

    def test_sin_especie(self):
        assert _extract_especie("Informe sobre condiciones oceanográficas") is None

    def test_case_insensitive(self):
        assert _extract_especie("EVALUACIÓN DE MERLUZA AUSTRAL") is not None


# ── _normalize_especie ────────────────────────────────────────────────────────

class TestNormalizeEspecie:
    def test_merluccius(self):
        assert _normalize_especie("merluccius hubbsi") == "merluza_hubbsi"

    def test_merluza(self):
        assert _normalize_especie("merluza") == "merluza_hubbsi"

    def test_pleoticus(self):
        assert _normalize_especie("pleoticus muelleri") == "langostino"

    def test_illex(self):
        assert _normalize_especie("illex argentinus") == "calamar_illex"

    def test_lithodes(self):
        assert _normalize_especie("lithodes santolla") == "centolla"

    def test_dissostichus(self):
        assert _normalize_especie("dissostichus eleginoides") == "merluza_negra"

    def test_macruronus(self):
        assert _normalize_especie("macruronus magellanicus") == "merluza_de_cola"

    def test_zygochlamys(self):
        assert _normalize_especie("zygochlamys patagonica") == "vieira"

    def test_especie_sin_mapeo(self):
        result = _normalize_especie("anchoíta")
        assert result == "anchoíta"

    def test_reemplaza_espacios(self):
        result = _normalize_especie("especie nueva")
        assert " " not in result


# ── _extract_zona ─────────────────────────────────────────────────────────────

class TestExtractZona:
    def test_sur_41(self):
        assert _extract_zona("Evaluación de merluza sur de 41°S") == "Sur 41°S"

    def test_norte_41(self):
        assert _extract_zona("Stock norte del paralelo 41°S") == "Norte 41°S"

    def test_norte_41_variante(self):
        assert _extract_zona("Merluza norte 41 grados") == "Norte 41°S"

    def test_patagonia(self):
        assert _extract_zona("Recursos pesqueros patagónicos") == "Patagonia"

    def test_sin_zona(self):
        assert _extract_zona("Informe técnico general de recursos") is None


# ── ITORecord ─────────────────────────────────────────────────────────────────

class TestITORecord:
    def test_creacion_minima(self):
        rec = ITORecord(titulo="Evaluación merluza 2024", url="https://test.com/item")
        assert rec.titulo == "Evaluación merluza 2024"
        assert rec.fuente == "INIDEP Mar Abierto"
        assert rec.autores == []

    def test_campos_opcionales_none(self):
        rec = ITORecord(titulo="test", url="http://test")
        assert rec.año_publicacion is None
        assert rec.cba_recomendada_tn is None
        assert rec.estado_stock is None


# ── ESPECIES_INTERES ──────────────────────────────────────────────────────────

class TestEspeciesInteres:
    def test_contiene_merluza(self):
        assert "merluza" in ESPECIES_INTERES

    def test_contiene_langostino(self):
        assert "langostino" in ESPECIES_INTERES

    def test_no_vacia(self):
        assert len(ESPECIES_INTERES) > 5
