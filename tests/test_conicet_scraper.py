"""
Tests del módulo de scraping de publicaciones científicas CONICET.

Verifica seed data, schema, funciones auxiliares y el scraper,
sin hacer llamadas de red reales.
"""

import sqlite3

import pytest

from src.acquisition.conicet_scraper import (
    SEARCH_TERMS,
    SEED_DATA_PUBLICACIONES,
    CONICETScraper,
    Publicacion,
    _parse_dc_metadata,
    normalizar_especie_from_titulo,
)

# ── SEED_DATA_PUBLICACIONES ───────────────────────────────────────────────────


class TestSeedDataPublicaciones:
    def test_no_vacio(self):
        assert len(SEED_DATA_PUBLICACIONES) >= 5

    def test_campos_obligatorios(self):
        for rec in SEED_DATA_PUBLICACIONES:
            assert "titulo" in rec, f"Falta 'titulo' en: {rec}"
            assert rec["titulo"], "El título no puede estar vacío"

    def test_años_razonables(self):
        for rec in SEED_DATA_PUBLICACIONES:
            if rec.get("año_publicacion"):
                assert 1990 <= rec["año_publicacion"] <= 2030

    def test_repositorio_presente(self):
        for rec in SEED_DATA_PUBLICACIONES:
            assert rec.get("repositorio"), f"Falta repositorio en: {rec['titulo'][:40]}"

    def test_handle_unico(self):
        handles = [r.get("handle") for r in SEED_DATA_PUBLICACIONES if r.get("handle")]
        assert len(handles) == len(set(handles)), "Handles duplicados en SEED_DATA"

    def test_tiene_merluza(self):
        codes = {r.get("especie_code") for r in SEED_DATA_PUBLICACIONES}
        assert "merluza_hubbsi" in codes

    def test_tiene_langostino(self):
        codes = {r.get("especie_code") for r in SEED_DATA_PUBLICACIONES}
        assert "langostino" in codes

    def test_tiene_publicaciones_sin_especie(self):
        """Algunas publicaciones son sobre política pesquera general."""
        sin_especie = [r for r in SEED_DATA_PUBLICACIONES if not r.get("especie_code")]
        assert len(sin_especie) >= 1

    def test_tipos_validos(self):
        tipos_validos = {"article", "report", "thesis", None}
        for rec in SEED_DATA_PUBLICACIONES:
            assert rec.get("tipo_publicacion") in tipos_validos, (
                f"Tipo inválido: {rec.get('tipo_publicacion')}"
            )


# ── SEARCH_TERMS ──────────────────────────────────────────────────────────────


class TestSearchTerms:
    def test_no_vacio(self):
        assert len(SEARCH_TERMS) > 0

    def test_merluza_hubbsi(self):
        assert "merluza_hubbsi" in SEARCH_TERMS
        assert len(SEARCH_TERMS["merluza_hubbsi"]) > 0

    def test_terminos_son_strings(self):
        for code, terms in SEARCH_TERMS.items():
            assert isinstance(terms, list)
            for t in terms:
                assert isinstance(t, str), f"Término no string en {code}: {t}"

    def test_incluye_nombres_cientificos(self):
        # Al menos un término por especie debe tener nombre científico (genus + species)
        for code, terms in SEARCH_TERMS.items():
            has_scientific = any(" " in t and t[0].isupper() for t in terms)
            assert has_scientific, f"{code} no tiene nombre científico en SEARCH_TERMS"


# ── normalizar_especie_from_titulo ────────────────────────────────────────────


class TestNormalizarEspecie:
    def test_merluza_hubbsi_por_nombre_cientifico(self):
        nombre, code = normalizar_especie_from_titulo("Merluccius hubbsi stock assessment")
        assert code == "merluza_hubbsi"
        assert nombre == "merluza hubbsi"

    def test_merluza_hubbsi_por_nombre_comun(self):
        nombre, code = normalizar_especie_from_titulo("Evaluación del stock de merluza hubbsi 2024")
        assert code == "merluza_hubbsi"

    def test_langostino(self):
        nombre, code = normalizar_especie_from_titulo("Pleoticus muelleri population dynamics")
        assert code == "langostino"

    def test_illex(self):
        nombre, code = normalizar_especie_from_titulo(
            "Illex argentinus spatial distribution in the Southwest Atlantic"
        )
        assert code == "calamar_illex"

    def test_merluza_negra(self):
        nombre, code = normalizar_especie_from_titulo("Dissostichus eleginoides management")
        assert code == "merluza_negra"

    def test_centolla(self):
        nombre, code = normalizar_especie_from_titulo(
            "Southern king crab Lithodes santolla Beagle Channel"
        )
        assert code == "centolla"

    def test_texto_sin_especie(self):
        nombre, code = normalizar_especie_from_titulo("Política pesquera argentina 1990-2020")
        assert nombre is None
        assert code is None

    def test_usa_abstract(self):
        nombre, code = normalizar_especie_from_titulo(
            "Fisheries management review",
            abstract="This paper reviews merluza hubbsi stock dynamics.",
        )
        assert code == "merluza_hubbsi"


# ── _parse_dc_metadata ────────────────────────────────────────────────────────


class TestParseDcMetadata:
    def test_extrae_titulo(self):
        item = {"metadata": [{"key": "dc.title", "value": "Test Paper on Hake"}]}
        meta = _parse_dc_metadata(item)
        assert meta["titulo"] == "Test Paper on Hake"

    def test_extrae_autores(self):
        item = {
            "metadata": [
                {"key": "dc.contributor.author", "value": "García, S."},
                {"key": "dc.contributor.author", "value": "López, M."},
            ]
        }
        meta = _parse_dc_metadata(item)
        assert "García, S." in meta["autores"]
        assert "López, M." in meta["autores"]

    def test_extrae_año(self):
        item = {"metadata": [{"key": "dc.date.issued", "value": "2022-03-15"}]}
        meta = _parse_dc_metadata(item)
        assert meta["año"] == 2022

    def test_extrae_abstract(self):
        item = {"metadata": [{"key": "dc.description.abstract", "value": "This is the abstract."}]}
        meta = _parse_dc_metadata(item)
        assert meta["abstract"] == "This is the abstract."

    def test_item_vacio(self):
        meta = _parse_dc_metadata({})
        assert meta == {}

    def test_keywords_concatenados(self):
        item = {
            "metadata": [
                {"key": "dc.subject", "value": "hake"},
                {"key": "dc.subject", "value": "Argentina"},
            ]
        }
        meta = _parse_dc_metadata(item)
        assert "hake" in meta["keywords"]
        assert "Argentina" in meta["keywords"]


# ── CONICETScraper ────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def conicet_db(tmp_path_factory):
    db = tmp_path_factory.mktemp("conicet_db") / "catalog.db"
    s = CONICETScraper(db_path=db)
    s.seed_data()
    return db


@pytest.fixture(scope="module")
def scraper(conicet_db):
    return CONICETScraper(db_path=conicet_db)


class TestCONICETScraper:
    def test_seed_crea_tabla(self, conicet_db):
        conn = sqlite3.connect(conicet_db)
        tables = {
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        conn.close()
        assert "publicaciones_cientificas" in tables

    def test_seed_inserta_registros(self, scraper):
        df = scraper.get_publicaciones_df()
        assert not df.empty
        assert len(df) == len(SEED_DATA_PUBLICACIONES)

    def test_seed_idempotente(self, conicet_db):
        s = CONICETScraper(db_path=conicet_db)
        n = s.seed_data()
        assert n == 0  # ya existían, no inserta duplicados
        df = s.get_publicaciones_df()
        assert len(df) == len(SEED_DATA_PUBLICACIONES)

    def test_get_publicaciones_df_columnas(self, scraper):
        df = scraper.get_publicaciones_df()
        for col in ["titulo", "autores", "año_publicacion", "especie_code"]:
            assert col in df.columns

    def test_filtro_por_especie(self, scraper):
        df = scraper.get_publicaciones_df(especie_code="merluza_hubbsi")
        assert not df.empty
        assert all(df["especie_code"] == "merluza_hubbsi")

    def test_get_resumen_por_especie(self, scraper):
        df = scraper.get_resumen_por_especie()
        assert not df.empty
        assert "n_publicaciones" in df.columns
        assert "especie_code" in df.columns

    def test_resumen_merluza_tiene_pubs(self, scraper):
        df = scraper.get_resumen_por_especie()
        merluza = df[df["especie_code"] == "merluza_hubbsi"]
        assert not merluza.empty
        assert merluza.iloc[0]["n_publicaciones"] >= 1

    def test_get_publicaciones_by_especie(self, scraper):
        pubs = scraper.get_publicaciones_by_especie("langostino")
        assert isinstance(pubs, list)
        assert len(pubs) >= 1
        assert "titulo" in pubs[0]

    def test_save_publicaciones(self, conicet_db):
        s = CONICETScraper(db_path=conicet_db)
        pub = Publicacion(
            titulo="Test publication for save_publicaciones",
            repositorio="Test",
            handle="test_handle_unique_123",
        )
        n = s.save_publicaciones([pub])
        assert n >= 1
        df = s.get_publicaciones_df()
        assert any(df["titulo"] == pub.titulo)

    def test_save_publicaciones_sin_duplicados(self, conicet_db):
        s = CONICETScraper(db_path=conicet_db)
        pub = Publicacion(
            titulo="Duplicate test pub",
            repositorio="Test",
            handle="test_handle_unique_456",
        )
        n1 = s.save_publicaciones([pub])
        n2 = s.save_publicaciones([pub])
        assert n1 >= 1
        assert n2 == 0  # INSERT OR IGNORE

    def test_no_db_empty_df(self, tmp_path):
        s = CONICETScraper(db_path=tmp_path / "nodb.db")
        df = s.get_publicaciones_df()
        assert df.empty

    def test_no_db_empty_resumen(self, tmp_path):
        s = CONICETScraper(db_path=tmp_path / "nodb.db")
        df = s.get_resumen_por_especie()
        assert df.empty

    def test_no_db_empty_by_especie(self, tmp_path):
        s = CONICETScraper(db_path=tmp_path / "nodb.db")
        pubs = s.get_publicaciones_by_especie("merluza_hubbsi")
        assert pubs == []
