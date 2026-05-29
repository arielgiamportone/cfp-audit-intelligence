"""
Tests del módulo FAO FIRMS — capturas internacionales y estado de stocks.

Verifica seed data, schema, funciones auxiliares y el scraper,
sin hacer llamadas de red reales.
"""

import sqlite3

import pytest

from src.acquisition.fao_firms_scraper import (
    ESPECIE_FAO_CODES,
    SEED_DATA_CAPTURAS,
    SEED_STOCK_STATUS,
    FAOFIRMSScraper,
    calcular_share_argentina,
    estado_stock_color,
    estado_stock_label,
    get_fao_code,
)

# ── SEED_DATA_CAPTURAS ────────────────────────────────────────────────────────


class TestSeedDataCapturas:
    def test_no_vacio(self):
        assert len(SEED_DATA_CAPTURAS) > 0

    def test_campos_obligatorios(self):
        required = {"especie", "especie_fao_code", "year", "pais"}
        for rec in SEED_DATA_CAPTURAS:
            assert required.issubset(rec.keys()), f"Faltan campos en: {rec}"

    def test_años_razonables(self):
        for rec in SEED_DATA_CAPTURAS:
            assert 2000 <= rec["year"] <= 2030, f"Año inválido: {rec['year']}"

    def test_captura_positiva_o_none(self):
        for rec in SEED_DATA_CAPTURAS:
            cap = rec.get("captura_tn")
            if cap is not None:
                assert cap > 0, f"Captura no positiva: {rec}"

    def test_fao_code_tres_letras(self):
        for rec in SEED_DATA_CAPTURAS:
            code = rec["especie_fao_code"]
            assert len(code) == 3, f"FAO code debe tener 3 letras: {code}"
            assert code.isalpha(), f"FAO code debe ser alfabético: {code}"

    def test_pais_valido(self):
        paises_validos = {"Argentina", "Total"}
        for rec in SEED_DATA_CAPTURAS:
            assert rec["pais"] in paises_validos or len(rec["pais"]) > 0

    def test_merluza_hubbsi_presente(self):
        codes = {r["especie_fao_code"] for r in SEED_DATA_CAPTURAS}
        assert "HKP" in codes, "Debe haber datos de merluza hubbsi (HKP)"

    def test_langostino_presente(self):
        codes = {r["especie_fao_code"] for r in SEED_DATA_CAPTURAS}
        assert "SNA" in codes, "Debe haber datos de langostino (SNA)"

    def test_tiene_total_y_argentina(self):
        """Debe haber registros tanto para Argentina como para Total por especie."""
        arg_codes = {r["especie_fao_code"] for r in SEED_DATA_CAPTURAS if r["pais"] == "Argentina"}
        total_codes = {r["especie_fao_code"] for r in SEED_DATA_CAPTURAS if r["pais"] == "Total"}
        comunes = arg_codes & total_codes
        assert len(comunes) > 0, "Debe haber al menos una especie con Argentina + Total"

    def test_argentina_menor_o_igual_total(self):
        """Para el mismo año, la captura Argentina no puede superar el total."""
        from collections import defaultdict

        arg_by_key = defaultdict(float)
        total_by_key = defaultdict(float)
        for rec in SEED_DATA_CAPTURAS:
            key = (rec["especie_fao_code"], rec["year"])
            cap = rec.get("captura_tn") or 0
            if rec["pais"] == "Argentina":
                arg_by_key[key] = cap
            elif rec["pais"] == "Total":
                total_by_key[key] = cap

        for key in arg_by_key:
            if key in total_by_key and total_by_key[key] > 0:
                assert arg_by_key[key] <= total_by_key[key] + 1, (
                    f"Argentina ({arg_by_key[key]}) > Total ({total_by_key[key]}) para {key}"
                )


# ── SEED_STOCK_STATUS ─────────────────────────────────────────────────────────


class TestSeedStockStatus:
    def test_no_vacio(self):
        assert len(SEED_STOCK_STATUS) > 0

    def test_campos_obligatorios(self):
        required = {"especie", "especie_fao_code", "estado_stock", "estado_stock_desc"}
        for rec in SEED_STOCK_STATUS:
            assert required.issubset(rec.keys()), f"Faltan campos en: {rec}"

    def test_estados_validos(self):
        estados_validos = {"F", "O", "U", "R", "D"}
        for rec in SEED_STOCK_STATUS:
            assert rec["estado_stock"] in estados_validos, (
                f"Estado inválido: {rec['estado_stock']}"
            )

    def test_merluza_sobrexplotada(self):
        """FAO FIRMS clasifica merluza hubbsi como sobrexplotada."""
        merluza = [r for r in SEED_STOCK_STATUS if r["especie_fao_code"] == "HKP"]
        assert len(merluza) >= 1
        assert merluza[0]["estado_stock"] == "O"

    def test_tiene_fuente_url(self):
        for rec in SEED_STOCK_STATUS:
            assert rec.get("fuente_url"), f"Falta fuente_url en {rec['especie']}"

    def test_abadejo_sobrexplotado(self):
        abadejo = [r for r in SEED_STOCK_STATUS if r["especie_fao_code"] == "POA"]
        assert len(abadejo) >= 1
        assert abadejo[0]["estado_stock"] == "O"


# ── ESPECIE_FAO_CODES ─────────────────────────────────────────────────────────


class TestEspecieFaoCodes:
    def test_no_vacio(self):
        assert len(ESPECIE_FAO_CODES) > 0

    def test_estructura(self):
        for code, info in ESPECIE_FAO_CODES.items():
            assert "fao_code" in info
            assert "nombre_fao" in info
            assert "nombre_cientifico" in info

    def test_merluza_hubbsi(self):
        assert "merluza_hubbsi" in ESPECIE_FAO_CODES
        assert ESPECIE_FAO_CODES["merluza_hubbsi"]["fao_code"] == "HKP"

    def test_langostino(self):
        assert "langostino" in ESPECIE_FAO_CODES
        assert ESPECIE_FAO_CODES["langostino"]["fao_code"] == "SNA"

    def test_calamar_illex(self):
        assert "calamar_illex" in ESPECIE_FAO_CODES
        assert ESPECIE_FAO_CODES["calamar_illex"]["fao_code"] == "SQA"


# ── Funciones auxiliares ──────────────────────────────────────────────────────


class TestFuncionesAuxiliares:
    def test_get_fao_code_existente(self):
        assert get_fao_code("merluza_hubbsi") == "HKP"
        assert get_fao_code("langostino") == "SNA"

    def test_get_fao_code_inexistente(self):
        assert get_fao_code("especie_inexistente") is None

    def test_estado_stock_label_conocidos(self):
        assert estado_stock_label("F") == "Plena explotación"
        assert estado_stock_label("O") == "Sobrexplotado"
        assert estado_stock_label("U") == "Subexplotado"
        assert estado_stock_label("R") == "En recuperación"
        assert estado_stock_label("D") == "Agotado"

    def test_estado_stock_label_desconocido(self):
        assert estado_stock_label("X") == "X"

    def test_estado_stock_color(self):
        assert estado_stock_color("F") == "amarillo"
        assert estado_stock_color("O") == "rojo"
        assert estado_stock_color("U") == "verde"
        assert estado_stock_color("D") == "critico"

    def test_calcular_share_argentina(self):
        import pandas as pd

        df = pd.DataFrame([
            {"especie": "merluza hubbsi", "especie_fao_code": "HKP", "year": 2022,
             "pais": "Argentina", "captura_tn": 345_000},
            {"especie": "merluza hubbsi", "especie_fao_code": "HKP", "year": 2022,
             "pais": "Total", "captura_tn": 365_000},
        ])
        result = calcular_share_argentina(df)
        assert not result.empty
        assert "share_arg_pct" in result.columns
        share = result.iloc[0]["share_arg_pct"]
        assert 90 < share < 100, f"Share esperado ~94.5%, obtenido {share}"

    def test_calcular_share_sin_total(self):
        import pandas as pd

        df = pd.DataFrame([
            {"especie": "merluza hubbsi", "especie_fao_code": "HKP", "year": 2022,
             "pais": "Argentina", "captura_tn": 345_000},
        ])
        result = calcular_share_argentina(df)
        assert result.iloc[0]["share_arg_pct"] is None


# ── FAOFIRMSScraper ───────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def fao_db(tmp_path_factory):
    """BD SQLite temporal con datos FAO."""
    db = tmp_path_factory.mktemp("fao_db") / "catalog.db"
    scraper = FAOFIRMSScraper(db_path=db)
    scraper.seed_data()
    return db


@pytest.fixture(scope="module")
def fao_scraper(fao_db):
    return FAOFIRMSScraper(db_path=fao_db)


class TestFAOFIRMSScraper:
    def test_seed_crea_tablas(self, fao_db):
        conn = sqlite3.connect(fao_db)
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        conn.close()
        assert "fao_capturas" in tables
        assert "fao_stock_status" in tables

    def test_seed_inserta_capturas(self, fao_scraper):
        df = fao_scraper.get_capturas_df()
        assert not df.empty
        assert len(df) == len(SEED_DATA_CAPTURAS)

    def test_seed_inserta_status(self, fao_scraper):
        df = fao_scraper.get_stock_status_df()
        assert not df.empty
        assert len(df) == len(SEED_STOCK_STATUS)

    def test_seed_idempotente(self, fao_db):
        """Llamar seed dos veces no duplica datos."""
        s = FAOFIRMSScraper(db_path=fao_db)
        s.seed_data()
        s.seed_data()
        df = s.get_capturas_df()
        assert len(df) == len(SEED_DATA_CAPTURAS)

    def test_get_capturas_df_columnas(self, fao_scraper):
        df = fao_scraper.get_capturas_df()
        for col in ["especie", "especie_fao_code", "pais", "year", "captura_tn"]:
            assert col in df.columns

    def test_get_stock_status_df_columnas(self, fao_scraper):
        df = fao_scraper.get_stock_status_df()
        for col in ["especie", "especie_fao_code", "estado_stock", "estado_stock_desc"]:
            assert col in df.columns

    def test_get_contexto_especie_hkp(self, fao_scraper):
        ctx = fao_scraper.get_contexto_especie("HKP", year=2022)
        assert ctx["captura_argentina_tn"] == 345_000
        assert ctx["captura_total_area41_tn"] == 365_000
        assert ctx["share_argentina_pct"] is not None
        assert 90 < ctx["share_argentina_pct"] < 100

    def test_get_contexto_especie_estado_stock(self, fao_scraper):
        ctx = fao_scraper.get_contexto_especie("HKP")
        assert ctx["estado_stock"] == "O"
        assert ctx["estado_stock_desc"] == "Sobrexplotado"

    def test_get_contexto_especie_inexistente(self, fao_scraper):
        ctx = fao_scraper.get_contexto_especie("XXX")
        assert ctx == {} or ctx.get("captura_argentina_tn") is None

    def test_no_db_capturas_empty(self, tmp_path):
        s = FAOFIRMSScraper(db_path=tmp_path / "nodb.db")
        df = s.get_capturas_df()
        assert df.empty

    def test_no_db_status_empty(self, tmp_path):
        s = FAOFIRMSScraper(db_path=tmp_path / "nodb.db")
        df = s.get_stock_status_df()
        assert df.empty
