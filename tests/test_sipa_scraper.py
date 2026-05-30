"""
Tests del módulo SIPA/SAGPyA — capturas reales.

Verifica seed data, schema, persistencia, triángulo de auditoría
y funciones auxiliares sin llamadas de red reales.
"""

import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from src.acquisition.sipa_scraper import (
    SEED_DATA_CAPTURAS,
    CapturaReal,
    SIPAScraper,
    TrianguloAuditoria,
    _clasificar_alerta_captura,
    resumen_por_especie,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def db(tmp_path) -> Path:
    return tmp_path / "sipa_test.db"


@pytest.fixture
def scraper(db) -> SIPAScraper:
    s = SIPAScraper(db_path=db)
    s.seed_data()
    return s


# ── SEED_DATA_CAPTURAS ────────────────────────────────────────────────────────


class TestSeedDataCapturas:
    def test_no_vacio(self):
        assert len(SEED_DATA_CAPTURAS) >= 20

    def test_campos_obligatorios(self):
        for rec in SEED_DATA_CAPTURAS:
            assert "especie_code" in rec
            assert "year" in rec
            assert "captura_tn" in rec

    def test_capturas_positivas(self):
        for rec in SEED_DATA_CAPTURAS:
            assert rec["captura_tn"] > 0, f"Captura no positiva: {rec}"

    def test_años_razonables(self):
        for rec in SEED_DATA_CAPTURAS:
            assert 2000 <= rec["year"] <= 2030

    def test_merluza_hubbsi_serie(self):
        merluza = [r for r in SEED_DATA_CAPTURAS if r["especie_code"] == "merluza_hubbsi"]
        assert len(merluza) >= 5

    def test_langostino_presente(self):
        codes = {r["especie_code"] for r in SEED_DATA_CAPTURAS}
        assert "langostino" in codes

    def test_calamar_illex_presente(self):
        codes = {r["especie_code"] for r in SEED_DATA_CAPTURAS}
        assert "calamar_illex" in codes

    def test_merluza_negra_presente(self):
        codes = {r["especie_code"] for r in SEED_DATA_CAPTURAS}
        assert "merluza_negra" in codes

    def test_langostino_2024_verificado(self):
        r = next(
            (
                r
                for r in SEED_DATA_CAPTURAS
                if r["especie_code"] == "langostino" and r["year"] == 2024
            ),
            None,
        )
        assert r is not None
        assert r["captura_tn"] == pytest.approx(222_754)

    def test_sin_duplicados(self):
        """No debe haber duplicados (especie_code, year)."""
        seen = set()
        for rec in SEED_DATA_CAPTURAS:
            key = (rec["especie_code"], rec["year"])
            assert key not in seen, f"Duplicado: {key}"
            seen.add(key)

    def test_especie_code_sin_espacios(self):
        for rec in SEED_DATA_CAPTURAS:
            assert " " not in rec["especie_code"]

    def test_fuente_presente(self):
        for rec in SEED_DATA_CAPTURAS:
            assert rec.get("fuente"), f"Sin fuente: {rec}"


# ── _clasificar_alerta_captura ────────────────────────────────────────────────


class TestClasificarAlertaCaptura:
    def test_verde(self):
        assert _clasificar_alerta_captura(0.90, 0.85) == "verde"

    def test_amarillo_supera_cba_leve(self):
        assert _clasificar_alerta_captura(1.05, 0.90) == "amarillo"

    def test_rojo_exceso_moderado(self):
        assert _clasificar_alerta_captura(1.20, 1.10) == "rojo"

    def test_critico_exceso_alto(self):
        assert _clasificar_alerta_captura(1.35, 1.30) == "critico"

    def test_sub_utilizacion(self):
        assert _clasificar_alerta_captura(0.60, 0.60) == "sub_utilizacion"

    def test_sin_datos(self):
        assert _clasificar_alerta_captura(None, None) == "sin_datos"

    def test_exactamente_en_cba(self):
        # ratio_cba=1.0 y no es sub-utilización → verde
        assert _clasificar_alerta_captura(1.00, 0.90) == "verde"


# ── TrianguloAuditoria ────────────────────────────────────────────────────────


class TestTrianguloAuditoria:
    def test_calcula_ratios(self):
        t = TrianguloAuditoria(
            especie="merluza común",
            especie_code="merluza_hubbsi",
            year=2023,
            cba_inidep_tn=350_000,
            cmp_cfp_tn=380_000,
            captura_real_tn=370_000,
        )
        assert t.ratio_cmp_cba == pytest.approx(380_000 / 350_000, rel=1e-3)
        assert t.ratio_captura_cba == pytest.approx(370_000 / 350_000, rel=1e-3)
        assert t.ratio_captura_cmp == pytest.approx(370_000 / 380_000, rel=1e-3)

    def test_alerta_critica_cuando_excede_130(self):
        t = TrianguloAuditoria(
            especie="merluza",
            especie_code="merluza_hubbsi",
            year=2020,
            cba_inidep_tn=200_000,
            cmp_cfp_tn=250_000,
            captura_real_tn=270_000,  # 135% de CBA
        )
        assert t.alerta_captura == "critico"

    def test_alerta_verde_cuando_dentro_cba(self):
        t = TrianguloAuditoria(
            especie="merluza",
            especie_code="merluza_hubbsi",
            year=2020,
            cba_inidep_tn=350_000,
            cmp_cfp_tn=370_000,
            captura_real_tn=330_000,  # 94% de CBA
        )
        assert t.alerta_captura == "verde"

    def test_sin_cba_sin_datos(self):
        t = TrianguloAuditoria(
            especie="langostino",
            especie_code="langostino",
            year=2024,
            cba_inidep_tn=None,
            cmp_cfp_tn=None,
            captura_real_tn=222_754,
        )
        assert t.ratio_captura_cba is None
        assert t.alerta_captura == "sin_datos"

    def test_ratios_none_sin_datos(self):
        t = TrianguloAuditoria(
            especie="x",
            especie_code="x",
            year=2023,
            cba_inidep_tn=None,
            cmp_cfp_tn=None,
            captura_real_tn=None,
        )
        assert t.ratio_cmp_cba is None
        assert t.ratio_captura_cmp is None
        assert t.ratio_captura_cba is None


# ── SIPAScraper ───────────────────────────────────────────────────────────────


class TestSIPAScraper:
    def test_seed_crea_tabla(self, db):
        s = SIPAScraper(db_path=db)
        s.seed_data()
        conn = sqlite3.connect(db)
        tables = {
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        conn.close()
        assert "capturas_reales" in tables

    def test_seed_inserta_registros(self, scraper):
        df = scraper.get_capturas_df()
        assert not df.empty
        assert len(df) == len(SEED_DATA_CAPTURAS)

    def test_seed_idempotente(self, db):
        s = SIPAScraper(db_path=db)
        n1 = s.seed_data()
        n2 = s.seed_data()
        assert n1 == len(SEED_DATA_CAPTURAS)
        assert n2 == 0

    def test_get_capturas_df_columnas(self, scraper):
        df = scraper.get_capturas_df()
        for col in ["especie_code", "year", "captura_tn", "fuente"]:
            assert col in df.columns

    def test_filtro_por_especie(self, scraper):
        df = scraper.get_capturas_df(especie_code="merluza_hubbsi")
        assert not df.empty
        assert all(df["especie_code"] == "merluza_hubbsi")

    def test_db_inexistente_df_vacio(self, tmp_path):
        s = SIPAScraper(db_path=tmp_path / "nodb.db")
        df = s.get_capturas_df()
        assert df.empty

    def test_save_capturas(self, db):
        s = SIPAScraper(db_path=db)
        s.seed_data()
        nueva = CapturaReal(
            especie="vieira",
            especie_code="vieira",
            year=2022,
            captura_tn=15_000,
            fuente="SAGPyA",
        )
        n = s.save_capturas([nueva])
        assert n == 1

    def test_save_capturas_idempotente(self, db):
        s = SIPAScraper(db_path=db)
        s.seed_data()
        nueva = CapturaReal(
            especie="vieira",
            especie_code="vieira",
            year=2021,
            captura_tn=14_500,
            fuente="SAGPyA",
        )
        n1 = s.save_capturas([nueva])
        n2 = s.save_capturas([nueva])
        assert n1 == 1
        assert n2 == 0

    def test_get_triangulo_sin_cfp_cuotas(self, db):
        """Sin tabla cfp_cuotas los ratios serán None pero no falla."""
        s = SIPAScraper(db_path=db)
        s.seed_data()
        triangulos = s.get_triangulo_auditoria()
        assert isinstance(triangulos, list)
        assert len(triangulos) > 0
        for t in triangulos:
            assert t.captura_real_tn is not None

    def test_get_triangulo_db_inexistente(self, tmp_path):
        s = SIPAScraper(db_path=tmp_path / "nodb.db")
        assert s.get_triangulo_auditoria() == []

    def test_get_alertas_sobrexplotacion_lista(self, db):
        s = SIPAScraper(db_path=db)
        s.seed_data()
        alertas = s.get_alertas_sobrexplotacion()
        assert isinstance(alertas, list)

    def test_get_triangulo_filtro_especie(self, db):
        s = SIPAScraper(db_path=db)
        s.seed_data()
        triangulos = s.get_triangulo_auditoria(especie_code="langostino")
        assert all(t.especie_code == "langostino" for t in triangulos)


# ── resumen_por_especie ────────────────────────────────────────────────────────


class TestResumenPorEspecie:
    def test_retorna_lista(self, db, scraper):
        resumen = resumen_por_especie(db)
        assert isinstance(resumen, list)
        assert len(resumen) > 0

    def test_campos_presentes(self, db, scraper):
        resumen = resumen_por_especie(db)
        for r in resumen:
            assert "especie_code" in r
            assert "n_años" in r
            assert "avg_captura" in r

    def test_db_inexistente(self, tmp_path):
        assert resumen_por_especie(tmp_path / "nodb.db") == []

    def test_merluza_tiene_mas_años(self, db, scraper):
        resumen = resumen_por_especie(db)
        merluza = next((r for r in resumen if r["especie_code"] == "merluza_hubbsi"), None)
        assert merluza is not None
        assert merluza["n_años"] >= 5

    def test_orden_por_captura_desc(self, db, scraper):
        resumen = resumen_por_especie(db)
        capturas = [r["avg_captura"] for r in resumen]
        assert capturas == sorted(capturas, reverse=True)


# ── fetch_datos_gob_ar (mockeado) ─────────────────────────────────────────────


class TestFetchDatosGobAr:
    def test_retorna_lista_vacia_si_falla(self, db):
        s = SIPAScraper(db_path=db)
        with patch.object(s._session, "get", side_effect=ConnectionError("offline")):
            result = s.fetch_datos_gob_ar("merluza_hubbsi")
        assert result == []

    def test_parsea_respuesta_correcta(self, db):
        s = SIPAScraper(db_path=db)
        mock_resp = {
            "result": {
                "records": [
                    {"año": "2020", "captura": "350000"},
                    {"año": "2021", "captura": "370000"},
                ]
            }
        }
        mock = patch.object(
            s._session,
            "get",
            return_value=type(
                "R",
                (),
                {
                    "status_code": 200,
                    "json": lambda self: mock_resp,
                },
            )(),
        )
        with mock:
            result = s.fetch_datos_gob_ar("merluza_hubbsi")
        assert len(result) == 2
        assert result[0].year == 2020
        assert result[0].captura_tn == pytest.approx(350_000)
