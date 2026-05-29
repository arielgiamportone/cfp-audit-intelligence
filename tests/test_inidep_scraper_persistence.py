"""
Tests de persistencia del scraper INIDEP — Issue #9.

Cubre save_itos_to_db, get_historical_series y scrape_and_save.
No hace llamadas de red reales.
"""

import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from src.acquisition.inidep_scraper import (
    SEED_DATA,
    INIDEPScraper,
    ITORecord,
    get_historical_series,
    save_itos_to_db,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def db(tmp_path) -> Path:
    return tmp_path / "test_inidep.db"


@pytest.fixture
def sample_records() -> list[ITORecord]:
    return [
        ITORecord(
            titulo="Merluza hubbsi. Evaluación del stock sur 41°S. Temporada 2023",
            url="https://marabierto.inidep.edu.ar/items/abc-123",
            uuid="abc-123",
            año_publicacion=2023,
            año_evaluacion=2023,
            especie_raw="merluza",
            especie_norm="merluza_hubbsi",
            zona="Sur 41°S",
            cba_recomendada_tn=292_000.0,
            estado_stock="en_recuperacion",
            autores=["García, J.", "López, M."],
            numero_ito="10/2023",
        ),
        ITORecord(
            titulo="Langostino patagónico. Informe 2023",
            url="https://marabierto.inidep.edu.ar/items/def-456",
            uuid="def-456",
            año_publicacion=2023,
            año_evaluacion=2023,
            especie_raw="langostino",
            especie_norm="langostino",
            zona="Patagonia",
            cba_recomendada_tn=220_000.0,
            estado_stock="variable",
        ),
        ITORecord(
            titulo="Centolla. Informe 2022",
            url="https://marabierto.inidep.edu.ar/items/ghi-789",
            uuid="ghi-789",
            año_publicacion=2022,
            año_evaluacion=2022,
            especie_raw="centolla",
            especie_norm="centolla",
            zona="Área Sur total",
            cba_recomendada_tn=1_200.0,
            estado_stock="saludable",
        ),
    ]


# ── SEED_DATA expandido ───────────────────────────────────────────────────────


class TestSeedDataExpandido:
    def test_minimo_30_registros(self):
        """La serie histórica debe cubrir al menos 30 evaluaciones."""
        assert len(SEED_DATA) >= 30

    def test_merluza_hubbsi_serie_sur(self):
        """Debe haber serie histórica de merluza Sur 41°S con múltiples años."""
        sur = [
            r
            for r in SEED_DATA
            if r["especie_code"] == "merluza_hubbsi" and r.get("zona") == "Sur 41°S"
        ]
        assert len(sur) >= 5, f"Solo {len(sur)} registros merluza Sur"

    def test_merluza_hubbsi_serie_norte(self):
        """Debe haber serie histórica de merluza Norte 41°S con múltiples años."""
        norte = [
            r
            for r in SEED_DATA
            if r["especie_code"] == "merluza_hubbsi" and r.get("zona") == "Norte 41°S"
        ]
        assert len(norte) >= 3

    def test_langostino_serie_historica(self):
        """Langostino debe tener serie de al menos 5 años."""
        lang = [r for r in SEED_DATA if r["especie_code"] == "langostino"]
        assert len(lang) >= 5

    def test_calamar_illex_presente(self):
        codes = {r["especie_code"] for r in SEED_DATA}
        assert "calamar_illex" in codes

    def test_merluza_negra_presente(self):
        codes = {r["especie_code"] for r in SEED_DATA}
        assert "merluza_negra" in codes

    def test_centolla_serie(self):
        centolla = [r for r in SEED_DATA if r["especie_code"] == "centolla"]
        assert len(centolla) >= 3

    def test_años_razonables(self):
        for rec in SEED_DATA:
            assert 2000 <= rec["year"] <= 2030, f"Año inválido: {rec['year']}"

    def test_cba_positiva_o_none(self):
        for rec in SEED_DATA:
            cba = rec.get("cba_recomendada_tn")
            if cba is not None:
                assert cba > 0, f"CBA no positiva: {rec}"

    def test_estado_stock_valido(self):
        estados_validos = {
            "saludable",
            "en_recuperacion",
            "sobrexplotado",
            "precautorio",
            "incierto",
            "variable",
            None,
        }
        for rec in SEED_DATA:
            assert rec.get("estado_stock") in estados_validos, (
                f"Estado inválido: {rec.get('estado_stock')}"
            )

    def test_fuente_url_presente(self):
        for rec in SEED_DATA:
            assert rec.get("fuente_url"), f"Sin fuente_url: {rec['especie_code']} {rec['year']}"

    def test_merluza_sur_2024_verificado(self):
        """El valor 2024 de merluza Sur debe coincidir con el ITO 36/2024."""
        r = next(
            (
                r
                for r in SEED_DATA
                if r["especie_code"] == "merluza_hubbsi"
                and r.get("zona") == "Sur 41°S"
                and r["year"] == 2024
            ),
            None,
        )
        assert r is not None
        assert r["cba_recomendada_tn"] == 319_000
        assert r["numero_ito"] == "36/2024"

    def test_merluza_norte_2024_verificado(self):
        """El valor 2024 de merluza Norte debe coincidir con el ITO 37/2024."""
        r = next(
            (
                r
                for r in SEED_DATA
                if r["especie_code"] == "merluza_hubbsi"
                and r.get("zona") == "Norte 41°S"
                and r["year"] == 2024
            ),
            None,
        )
        assert r is not None
        assert r["cba_recomendada_tn"] == pytest.approx(50_023)
        assert r["numero_ito"] == "37/2024"

    def test_especie_code_sin_espacios(self):
        for rec in SEED_DATA:
            assert " " not in rec["especie_code"]

    def test_no_años_duplicados_por_especie_zona(self):
        """No debe haber duplicados (especie_code, zona, year) en SEED_DATA."""
        seen = set()
        for rec in SEED_DATA:
            key = (rec["especie_code"], rec.get("zona"), rec["year"])
            assert key not in seen, f"Duplicado: {key}"
            seen.add(key)


# ── save_itos_to_db ───────────────────────────────────────────────────────────


class TestSaveItosToDB:
    def test_inserta_registros(self, db, sample_records):
        n = save_itos_to_db(sample_records, db)
        assert n == 3

    def test_crea_tabla(self, db, sample_records):
        save_itos_to_db(sample_records, db)
        conn = sqlite3.connect(db)
        tables = {
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        conn.close()
        assert "inidep_evaluaciones" in tables

    def test_datos_persistidos_correctamente(self, db, sample_records):
        save_itos_to_db(sample_records, db)
        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM inidep_evaluaciones ORDER BY especie_code").fetchall()
        conn.close()
        assert len(rows) == 3
        merluza = next(r for r in rows if r["especie_code"] == "merluza_hubbsi")
        assert merluza["year"] == 2023
        assert merluza["cba_recomendada_tn"] == pytest.approx(292_000)
        assert merluza["zona"] == "Sur 41°S"
        assert merluza["estado_stock"] == "en_recuperacion"

    def test_idempotente(self, db, sample_records):
        """Segunda inserción del mismo lote no agrega duplicados."""
        n1 = save_itos_to_db(sample_records, db)
        n2 = save_itos_to_db(sample_records, db)
        assert n1 == 3
        assert n2 == 0

    def test_solo_inserta_nuevos(self, db, sample_records):
        """Inserta primero 1, luego el lote completo — solo agrega los 2 nuevos."""
        save_itos_to_db(sample_records[:1], db)
        n = save_itos_to_db(sample_records, db)
        assert n == 2

    def test_omite_sin_year(self, db):
        """ITOs sin año válido se omiten silenciosamente."""
        rec = ITORecord(
            titulo="Sin año",
            url="https://marabierto.inidep.edu.ar/items/zzz",
            especie_raw="merluza",
            especie_norm="merluza_hubbsi",
        )
        n = save_itos_to_db([rec], db)
        assert n == 0

    def test_omite_sin_titulo(self, db):
        """ITOs con título vacío se omiten."""
        rec = ITORecord(
            titulo="",
            url="https://marabierto.inidep.edu.ar/items/zzz",
            año_evaluacion=2023,
            especie_norm="merluza_hubbsi",
        )
        n = save_itos_to_db([rec], db)
        assert n == 0

    def test_crea_directorio_si_no_existe(self, tmp_path):
        db_nuevo = tmp_path / "subdir" / "nuevo.db"
        rec = ITORecord(
            titulo="Test",
            url="https://x",
            año_evaluacion=2023,
            especie_norm="merluza_hubbsi",
            especie_raw="merluza",
        )
        n = save_itos_to_db([rec], db_nuevo)
        assert n == 1
        assert db_nuevo.exists()

    def test_abstract_truncado(self, db):
        """Abstracts largos se truncan al guardar."""
        rec = ITORecord(
            titulo="ITO Abstracto Largo 2022",
            url="https://marabierto.inidep.edu.ar/items/aaa",
            año_evaluacion=2022,
            especie_raw="calamar",
            especie_norm="calamar_illex",
            zona="Mar Argentino",
            abstract="x" * 5000,
        )
        n = save_itos_to_db([rec], db)
        assert n == 1
        conn = sqlite3.connect(db)
        row = conn.execute("SELECT notas FROM inidep_evaluaciones").fetchone()
        conn.close()
        assert len(row[0]) <= 300


# ── get_historical_series ─────────────────────────────────────────────────────


class TestGetHistoricalSeries:
    def test_retorna_lista(self, db, sample_records):
        save_itos_to_db(sample_records, db)
        series = get_historical_series("merluza_hubbsi", db)
        assert isinstance(series, list)
        assert len(series) >= 1

    def test_orden_ascendente_por_año(self, db, sample_records):
        # Agregar dos años diferentes
        recs = [
            ITORecord(
                titulo="M 2021",
                url="u",
                año_evaluacion=2021,
                especie_norm="merluza_hubbsi",
                especie_raw="merluza",
                zona="Sur 41°S",
                cba_recomendada_tn=234_000,
            ),
            ITORecord(
                titulo="M 2023",
                url="u2",
                año_evaluacion=2023,
                especie_norm="merluza_hubbsi",
                especie_raw="merluza",
                zona="Sur 41°S",
                cba_recomendada_tn=292_000,
            ),
        ]
        save_itos_to_db(recs, db)
        series = get_historical_series("merluza_hubbsi", db, zona="Sur 41°S")
        years = [r["year"] for r in series]
        assert years == sorted(years)

    def test_filtro_por_zona(self, db, sample_records):
        save_itos_to_db(sample_records, db)
        series = get_historical_series("merluza_hubbsi", db, zona="Sur 41°S")
        assert all(r["zona"] == "Sur 41°S" for r in series)

    def test_especie_inexistente_lista_vacia(self, db, sample_records):
        save_itos_to_db(sample_records, db)
        assert get_historical_series("vieira", db) == []

    def test_db_inexistente_lista_vacia(self, tmp_path):
        assert get_historical_series("merluza_hubbsi", tmp_path / "nodb.db") == []

    def test_campos_retornados(self, db, sample_records):
        save_itos_to_db(sample_records, db)
        series = get_historical_series("merluza_hubbsi", db)
        for row in series:
            assert "year" in row
            assert "cba_recomendada_tn" in row
            assert "zona" in row
            assert "estado_stock" in row


# ── INIDEPScraper.scrape_and_save (mockeado) ──────────────────────────────────


class TestScrapeAndSave:
    @pytest.fixture
    def mock_records(self, sample_records):
        return sample_records

    def test_llama_scrape_all_metadata(self, db, mock_records):
        s = INIDEPScraper(delay=0)
        with patch.object(s, "scrape_all_metadata", return_value=mock_records) as m:
            n = s.scrape_and_save(db)
        m.assert_called_once_with(max_items=None)
        assert n == 3

    def test_max_items_pasado(self, db, mock_records):
        s = INIDEPScraper(delay=0)
        with patch.object(s, "scrape_all_metadata", return_value=mock_records[:1]) as m:
            s.scrape_and_save(db, max_items=1)
        m.assert_called_once_with(max_items=1)

    def test_filtro_especies(self, db, mock_records):
        s = INIDEPScraper(delay=0)
        with patch.object(s, "scrape_all_metadata", return_value=mock_records):
            n = s.scrape_and_save(db, especies_filtro=["merluza_hubbsi"])
        assert n == 1  # solo 1 de los 3 es merluza_hubbsi

    def test_idempotente(self, db, mock_records):
        s = INIDEPScraper(delay=0)
        with patch.object(s, "scrape_all_metadata", return_value=mock_records):
            n1 = s.scrape_and_save(db)
            n2 = s.scrape_and_save(db)
        assert n1 == 3
        assert n2 == 0

    def test_retorna_int(self, db, mock_records):
        s = INIDEPScraper(delay=0)
        with patch.object(s, "scrape_all_metadata", return_value=[]):
            result = s.scrape_and_save(db)
        assert isinstance(result, int)
        assert result == 0

    def test_sin_records_no_falla(self, db):
        s = INIDEPScraper(delay=0)
        with patch.object(s, "scrape_all_metadata", return_value=[]):
            n = s.scrape_and_save(db)
        assert n == 0
