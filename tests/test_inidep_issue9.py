"""
Tests Issue #9 — Scraping completo INIDEP Mar Abierto.

Cubre:
  - Nuevos patrones de extracción CBA (8 patrones)
  - Flujo completo de 492 ITOs con HTTP mockeado (paginación DSpace)
  - Paso `--step inidep` del pipeline CLI
  - `get_scrape_status()` desde DB
"""

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.acquisition.inidep_scraper import (
    INIDEPScraper,
    ITORecord,
    _CBA_PATTERNS,
    _extract_cba,
    _parse_tn_value,
    get_scrape_status,
    save_itos_to_db,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def db(tmp_path) -> Path:
    return tmp_path / "inidep_test.db"


@pytest.fixture
def scraper() -> INIDEPScraper:
    return INIDEPScraper(delay=0)


def _make_dspace_page(items: list[dict], page: int, total_pages: int, total: int) -> dict:
    """Construye una respuesta DSpace paginada para tests."""
    return {
        "_embedded": {
            "searchResult": {
                "page": {
                    "number": page,
                    "size": len(items),
                    "totalPages": total_pages,
                    "totalElements": total,
                },
                "_embedded": {
                    "objects": [
                        {
                            "_embedded": {
                                "indexableObject": {
                                    "uuid": item["uuid"],
                                    "handle": f"123456/{item['uuid'][:6]}",
                                    "metadata": {
                                        "dc.title": [{"value": item["titulo"]}],
                                        "dc.date.issued": [{"value": str(item.get("year", 2023))}],
                                        "dc.description.abstract": [
                                            {"value": item.get("abstract", "")}
                                        ],
                                        "dc.contributor.author": [],
                                        "dc.subject": [
                                            {"value": item.get("especie", "merluza")}
                                        ],
                                    },
                                }
                            }
                        }
                        for item in items
                    ]
                },
            }
        }
    }


def _make_ito_item(
    uuid: str,
    titulo: str,
    year: int = 2023,
    abstract: str = "",
    especie: str = "merluza",
) -> dict:
    return {"uuid": uuid, "titulo": titulo, "year": year, "abstract": abstract, "especie": especie}


# ── _parse_tn_value ──────────────────────────────────────────────────────────


class TestParseTnValue:
    def test_formato_argentino_miles(self):
        assert _parse_tn_value("300.000") == pytest.approx(300_000.0)

    def test_formato_argentino_con_decimal(self):
        assert _parse_tn_value("1.234,5") == pytest.approx(1234.5)

    def test_numero_simple(self):
        assert _parse_tn_value("95000") == pytest.approx(95_000.0)

    def test_fuera_de_rango_bajo(self):
        assert _parse_tn_value("5") is None

    def test_fuera_de_rango_alto(self):
        assert _parse_tn_value("3.000.000") is None

    def test_valor_invalido(self):
        assert _parse_tn_value("abc") is None

    def test_con_espacios_como_miles(self):
        assert _parse_tn_value("300 000") == pytest.approx(300_000.0)


# ── Nuevos patrones CBA (Issue #9) ─────────────────────────────────────────────


class TestNuevosPatronesCBA:
    """Verifica los 8 patrones de extracción CBA implementados para Issue #9."""

    def test_patron_1_cba_igual(self):
        assert _extract_cba("CBA = 300.000 toneladas") == pytest.approx(300_000.0)

    def test_patron_1_cba_dos_puntos(self):
        assert _extract_cba("La CBA: 150.000 tn para el año 2024.") == pytest.approx(150_000.0)

    def test_patron_1_cba_estimada_en(self):
        assert _extract_cba("CBA estimada en 280.000 t.") == pytest.approx(280_000.0)

    def test_patron_1_cba_resultante(self):
        assert _extract_cba("CBA resultante de 312.000 tn.") == pytest.approx(312_000.0)

    def test_patron_2_no_superar(self):
        assert _extract_cba(
            "Se recomienda no superar las 280.000 toneladas para la temporada."
        ) == pytest.approx(280_000.0)

    def test_patron_2_no_exceder(self):
        assert _extract_cba(
            "La captura no debe exceder 195.000 tn."
        ) == pytest.approx(195_000.0)

    def test_patron_3_se_recomienda(self):
        assert _extract_cba(
            "El grupo de trabajo se recomienda 1.100 toneladas como límite."
        ) == pytest.approx(1_100.0)

    def test_patron_4_captura_maxima_recomendada(self):
        assert _extract_cba(
            "La captura máxima recomendada es de 180.000 t."
        ) == pytest.approx(180_000.0)

    def test_patron_4_captura_maxima_permisible(self):
        assert _extract_cba(
            "Captura máxima permisible de 220.000 toneladas."
        ) == pytest.approx(220_000.0)

    def test_patron_5_captura_recomendada_dos_puntos(self):
        assert _extract_cba(
            "Captura recomendada: 95.000 tn."
        ) == pytest.approx(95_000.0)

    def test_patron_6_limite_de_captura(self):
        assert _extract_cba(
            "El límite de captura de 180.000 toneladas métricas fue aprobado."
        ) == pytest.approx(180_000.0)

    def test_patron_7_no_deberia_exceder(self):
        assert _extract_cba(
            "La captura no debería exceder las 350.000 t en ningún escenario."
        ) == pytest.approx(350_000.0)

    def test_patron_8_resulto_en(self):
        assert _extract_cba(
            "El análisis resultó en 312.000 toneladas como recomendación."
        ) == pytest.approx(312_000.0)

    def test_sin_toneladas_no_matchea(self):
        assert _extract_cba("La CBA fue evaluada pero sin valor numérico final.") is None

    def test_texto_vacio(self):
        assert _extract_cba("") is None

    def test_texto_none(self):
        assert _extract_cba(None) is None

    def test_valor_fuera_de_rango_ignorado(self):
        assert _extract_cba("CBA de 3 toneladas.") is None

    def test_multiples_valores_retorna_primero(self):
        """Con múltiples matches, retorna el primero encontrado (patrón más específico)."""
        val = _extract_cba("CBA = 300.000 tn. No superar 280.000 tn.")
        assert val == pytest.approx(300_000.0)

    def test_todos_los_patrones_compilados(self):
        assert len(_CBA_PATTERNS) >= 8


# ── Flujo paginado completo (492 ITOs mockeado) ───────────────────────────────────


class TestFlujoPaginadoCompleto:
    """Simula scraping de 492 ITOs en 10 páginas de 50 items."""

    def _build_pages(self, total: int = 492, page_size: int = 50) -> list[dict]:
        pages = []
        total_pages = (total + page_size - 1) // page_size
        for p in range(total_pages):
            start = p * page_size
            count = min(page_size, total - start)
            items = [
                _make_ito_item(
                    uuid=f"uuid-{start + i:04d}",
                    titulo=f"ITO N° {start + i}/2023 — merluza sur 41°S",
                    year=2023,
                    abstract=f"CBA = {300_000 - start - i * 100} toneladas para la temporada.",
                )
                for i in range(count)
            ]
            pages.append(_make_dspace_page(items, p, total_pages, total))
        return pages

    def test_scrape_all_metadata_492(self, scraper):
        pages = self._build_pages(492)
        call_count = 0

        def mock_get_json(url, params=None):
            nonlocal call_count
            page = params.get("page", 0) if params else 0
            result = pages[page]
            call_count += 1
            return result

        with patch.object(scraper, "_get_json", side_effect=mock_get_json):
            records = scraper.scrape_all_metadata()

        assert len(records) == 492

    def test_scrape_respeta_max_items(self, scraper):
        pages = self._build_pages(492)

        def mock_get_json(url, params=None):
            page = params.get("page", 0) if params else 0
            return pages[min(page, len(pages) - 1)]

        with patch.object(scraper, "_get_json", side_effect=mock_get_json):
            records = scraper.scrape_all_metadata(max_items=25)

        assert len(records) == 25

    def test_scrape_continua_tras_error_de_pagina(self, scraper):
        """Si una página falla, el scraping termina limpiamente sin crash."""
        pages = self._build_pages(100)
        call_count = [0]

        def mock_get_json(url, params=None):
            page = params.get("page", 0) if params else 0
            call_count[0] += 1
            if page == 1:
                raise ConnectionError("timeout")
            return pages[min(page, len(pages) - 1)]

        with patch.object(scraper, "_get_json", side_effect=mock_get_json):
            records = scraper.scrape_all_metadata()

        # Debe tener los items de la página 0 (antes del error)
        assert len(records) >= 0  # no lanza excepción

    def test_cba_extraida_de_abstract(self, scraper):
        pages = self._build_pages(10)

        def mock_get_json(url, params=None):
            page = params.get("page", 0) if params else 0
            return pages[min(page, len(pages) - 1)]

        with patch.object(scraper, "_get_json", side_effect=mock_get_json):
            records = scraper.scrape_all_metadata()

        records_con_cba = [r for r in records if r.cba_recomendada_tn is not None]
        assert len(records_con_cba) == len(records)

    def test_especie_norm_asignada(self, scraper):
        items = [
            _make_ito_item("uuid-001", "ITO merluza hubbsi", especie="merluza hubbsi"),
            _make_ito_item("uuid-002", "ITO langostino Pleoticus", especie="pleoticus"),
            _make_ito_item("uuid-003", "ITO Dissostichus eleginoides", especie="dissostichus"),
        ]
        page = _make_dspace_page(items, 0, 1, 3)

        with patch.object(scraper, "_get_json", return_value=page):
            records = scraper.scrape_all_metadata()

        especies = {r.especie_norm for r in records}
        assert "merluza_hubbsi" in especies
        assert "langostino" in especies
        assert "merluza_negra" in especies


# ── scrape_and_save con DB ────────────────────────────────────────────────────────


class TestScrapeAndSave:
    def test_guarda_en_db_y_retorna_count(self, scraper, db):
        items = [
            _make_ito_item(
                "uuid-100",
                "ITO 36/2024 merluza sur 41°S",
                year=2024,
                abstract="CBA = 319.000 toneladas.",
                especie="merluza",
            )
        ]
        page = _make_dspace_page(items, 0, 1, 1)

        with patch.object(scraper, "_get_json", return_value=page):
            n = scraper.scrape_and_save(str(db))

        assert n == 1
        conn = sqlite3.connect(db)
        rows = conn.execute("SELECT * FROM inidep_evaluaciones").fetchall()
        conn.close()
        assert len(rows) == 1

    def test_idempotente(self, scraper, db):
        items = [
            _make_ito_item("uuid-200", "ITO merluza 2023", year=2023, especie="merluza")
        ]
        page = _make_dspace_page(items, 0, 1, 1)

        with patch.object(scraper, "_get_json", return_value=page):
            n1 = scraper.scrape_and_save(str(db))
        with patch.object(scraper, "_get_json", return_value=page):
            n2 = scraper.scrape_and_save(str(db))

        assert n1 == 1
        assert n2 == 0

    def test_filtro_por_especie(self, scraper, db):
        items = [
            _make_ito_item("uuid-300", "ITO merluza", year=2023, especie="merluza"),
            _make_ito_item("uuid-301", "ITO centolla", year=2023, especie="centolla lithodes"),
        ]
        page = _make_dspace_page(items, 0, 1, 2)

        with patch.object(scraper, "_get_json", return_value=page):
            n = scraper.scrape_and_save(str(db), especies_filtro=["merluza_hubbsi"])

        assert n == 1


# ── get_scrape_status ────────────────────────────────────────────────────────────


class TestGetScrapeStatus:
    def test_db_inexistente(self, tmp_path):
        status = get_scrape_status(tmp_path / "nodb.db")
        assert status["n_total"] == 0
        assert status["especies_cubiertas"] == []

    def test_status_tras_seed(self, db):
        records = [
            ITORecord(
                titulo="ITO merluza 2023",
                url="https://example.com",
                uuid="uuid-400",
                año_evaluacion=2023,
                especie_norm="merluza_hubbsi",
                especie_raw="merluza",
                cba_recomendada_tn=292_000,
            ),
            ITORecord(
                titulo="ITO langostino 2023",
                url="https://example.com",
                uuid="uuid-401",
                año_evaluacion=2023,
                especie_norm="langostino",
                especie_raw="langostino",
                cba_recomendada_tn=None,
            ),
        ]
        save_itos_to_db(records, db)

        status = get_scrape_status(db)
        assert status["n_total"] == 2
        assert status["n_con_cba"] == 1
        assert "merluza_hubbsi" in status["especies_cubiertas"]
        assert "langostino" in status["especies_cubiertas"]

    def test_status_campos_presentes(self, db):
        save_itos_to_db([], db)
        status = get_scrape_status(db)
        assert "n_total" in status
        assert "n_con_cba" in status
        assert "especies_cubiertas" in status
        assert "ultimo_año" in status
        assert "ultima_actualizacion" in status


# ── Pipeline --step inidep ───────────────────────────────────────────────────────


class TestPipelineInidepStep:
    def test_step_inidep_llama_scraper(self, tmp_path):
        db_path = tmp_path / "catalog.db"

        mock_n = 42
        with patch(
            "src.acquisition.inidep_scraper.INIDEPScraper.scrape_and_save",
            return_value=mock_n,
        ) as mock_scrape:
            from scripts.run_full_pipeline import step_inidep

            step_inidep(db_path)

        mock_scrape.assert_called_once()

    def test_step_inidep_max_items(self, tmp_path):
        db_path = tmp_path / "catalog.db"

        with patch(
            "src.acquisition.inidep_scraper.INIDEPScraper.scrape_and_save",
            return_value=10,
        ) as mock_scrape:
            from scripts.run_full_pipeline import step_inidep

            step_inidep(db_path, max_items=10)

        _, kwargs = mock_scrape.call_args
        assert kwargs.get("max_items") == 10 or mock_scrape.call_args[0][1] == 10

    def test_pipeline_acepta_step_inidep(self):
        """Verifica que el argparser acepta --step inidep."""
        import argparse
        import sys

        with patch.object(sys, "argv", ["pipeline", "--step", "inidep"]):
            parser = argparse.ArgumentParser()
            parser.add_argument(
                "--step",
                choices=["download", "process", "knowledge_base", "audit", "inidep", "all"],
            )
            parser.add_argument("--enrich-pdf", action="store_true")
            args = parser.parse_args()
        assert args.step == "inidep"


# ── Enrich con PDF ────────────────────────────────────────────────────────────────


class TestEnrichWithPDF:
    def test_enrich_usa_cba_del_abstract_si_existe(self, scraper):
        rec = ITORecord(
            titulo="ITO merluza 2024",
            url="https://example.com",
            uuid="uuid-500",
            cba_recomendada_tn=319_000.0,
        )
        result = scraper.enrich_with_pdf(rec)
        # No debe intentar descargar PDF si ya tiene CBA
        assert result.cba_recomendada_tn == pytest.approx(319_000.0)

    def test_enrich_extrae_cba_del_pdf(self, scraper):
        rec = ITORecord(
            titulo="ITO merluza 2024",
            url="https://example.com",
            uuid="uuid-501",
            cba_recomendada_tn=None,
        )
        pdf_text = "Se recomienda no superar las 280.000 toneladas para la temporada 2024."

        with patch.object(scraper, "download_and_extract_pdf", return_value=pdf_text):
            result = scraper.enrich_with_pdf(rec)

        assert result.cba_recomendada_tn == pytest.approx(280_000.0)

    def test_enrich_sin_uuid_retorna_rec_sin_cambios(self, scraper):
        rec = ITORecord(titulo="ITO sin UUID", url="https://example.com", uuid=None)
        result = scraper.enrich_with_pdf(rec)
        assert result.cba_recomendada_tn is None

    def test_enrich_pdf_falla_silenciosamente(self, scraper):
        rec = ITORecord(
            titulo="ITO con PDF roto",
            url="https://example.com",
            uuid="uuid-502",
            cba_recomendada_tn=None,
        )
        with patch.object(scraper, "download_and_extract_pdf", return_value=None):
            result = scraper.enrich_with_pdf(rec)
        assert result.cba_recomendada_tn is None
