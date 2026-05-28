"""
Tests del scraper INIDEP vía DSpace 7 API.

No hacen llamadas de red — mockean las respuestas JSON de la API.
"""
import pytest
from unittest.mock import MagicMock, patch

from src.acquisition.inidep_scraper import (
    INIDEPScraper,
    ITORecord,
    _extract_cba,
    _extract_estado_stock,
    _extract_ito_number,
    _extract_eval_year,
    _first_value,
    _all_values,
    _parse_year,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_search_response():
    """Respuesta DSpace API simulada con 2 items."""
    return {
        "_embedded": {
            "searchResult": {
                "page": {
                    "totalElements": 492,
                    "totalPages": 10,
                    "size": 50,
                    "number": 0,
                },
                "_embedded": {
                    "objects": [
                        {
                            "_embedded": {
                                "indexableObject": {
                                    "uuid": "aaa-111",
                                    "handle": "123456789/100",
                                    "metadata": {
                                        "dc.title": [{"value": "Merluza hubbsi. Evaluación del stock sur 41°S. Temporada 2023"}],
                                        "dc.date.issued": [{"value": "2023"}],
                                        "dc.description.abstract": [{"value": "Se recomienda una CBA de 300.000 toneladas para la temporada 2023."}],
                                        "dc.contributor.author": [{"value": "García, Juan"}, {"value": "López, María"}],
                                        "dc.subject": [{"value": "merluza"}, {"value": "evaluación"}],
                                    },
                                }
                            }
                        },
                        {
                            "_embedded": {
                                "indexableObject": {
                                    "uuid": "bbb-222",
                                    "handle": "123456789/101",
                                    "metadata": {
                                        "dc.title": [{"value": "Calamar argentino. Temporada 2023"}],
                                        "dc.date.issued": [{"value": "2023-06-15"}],
                                        "dc.description.abstract": [{"value": "La CBA recomendada es de 150.000 toneladas."}],
                                        "dc.contributor.author": [{"value": "Rodríguez, Carlos"}],
                                        "dc.subject": [{"value": "calamar"}, {"value": "illex"}],
                                    },
                                }
                            }
                        },
                    ]
                },
            }
        }
    }


@pytest.fixture
def scraper():
    return INIDEPScraper(delay=0)


# ── _extract_cba ──────────────────────────────────────────────────────────────

class TestExtractCba:
    def test_patron_cba_simple(self):
        text = "Se recomienda una CBA de 300.000 toneladas para la temporada."
        assert _extract_cba(text) == pytest.approx(300000.0)

    def test_patron_cba_con_igualdad(self):
        text = "La CBA = 150.000 tn para el año 2024."
        assert _extract_cba(text) == pytest.approx(150000.0)

    def test_patron_captura_biologicamente(self):
        text = "La Captura Biológicamente Aceptable: 50.023 toneladas."
        assert _extract_cba(text) == pytest.approx(50023.0)

    def test_patron_se_recomienda(self):
        text = "El grupo de trabajo se recomienda 1.100 toneladas como límite."
        assert _extract_cba(text) == pytest.approx(1100.0)

    def test_sin_cba(self):
        assert _extract_cba("Informe sobre condiciones oceanográficas.") is None

    def test_valor_fuera_de_rango(self):
        assert _extract_cba("CBA de 5 toneladas") is None  # < 10

    def test_texto_vacio(self):
        assert _extract_cba("") is None

    def test_texto_none(self):
        assert _extract_cba(None) is None

    def test_miles_con_punto(self):
        text = "CBA recomendada de 1.200 toneladas métricas."
        val = _extract_cba(text)
        assert val == pytest.approx(1200.0)


# ── _extract_estado_stock ─────────────────────────────────────────────────────

class TestExtractEstadoStock:
    def test_sobrexplotado(self):
        assert _extract_estado_stock("El stock se encuentra sobrexplotado.") == "sobrexplotado"

    def test_sobrepesca(self):
        assert _extract_estado_stock("Existe sobrepesca de reclutamiento.") == "sobrexplotado"

    def test_en_recuperacion(self):
        assert _extract_estado_stock("El recurso está en recuperación.") == "en_recuperacion"

    def test_saludable(self):
        assert _extract_estado_stock("El stock se encuentra en buen estado.") == "saludable"

    def test_precautorio(self):
        assert _extract_estado_stock("Se aplica criterio precautorio.") == "precautorio"

    def test_incierto(self):
        assert _extract_estado_stock("Existe gran incertidumbre en los datos.") == "incierto"

    def test_sin_info(self):
        assert _extract_estado_stock("Informe técnico sin evaluación de estado.") is None

    def test_texto_vacio(self):
        assert _extract_estado_stock("") is None


# ── _extract_ito_number ───────────────────────────────────────────────────────

class TestExtractItoNumber:
    def test_ito_con_numero(self):
        assert _extract_ito_number("ITO N° 36/2024 - Merluza hubbsi") == "36/2024"

    def test_informe_tecnico_oficial(self):
        assert _extract_ito_number("Informe Técnico Oficial N° 12/2023") == "12/2023"

    def test_sin_numero(self):
        assert _extract_ito_number("Evaluación de merluza 2024") is None

    def test_ito_sin_grado(self):
        assert _extract_ito_number("ITO 05/2022 del INIDEP") == "05/2022"


# ── _extract_eval_year ────────────────────────────────────────────────────────

class TestExtractEvalYear:
    def test_temporada(self):
        assert _extract_eval_year("Merluza hubbsi. Temporada 2023") == 2023

    def test_evaluacion(self):
        assert _extract_eval_year("Evaluación del stock 2022") == 2022

    def test_sin_año_eval(self):
        assert _extract_eval_year("Informe técnico general") is None


# ── _first_value / _all_values ────────────────────────────────────────────────

class TestMetadataHelpers:
    def test_first_value(self):
        meta = {"dc.title": [{"value": "Mi título"}]}
        assert _first_value(meta, "dc.title") == "Mi título"

    def test_first_value_ausente(self):
        assert _first_value({}, "dc.title") is None

    def test_all_values(self):
        meta = {"dc.subject": [{"value": "merluza"}, {"value": "stock"}]}
        assert _all_values(meta, "dc.subject") == ["merluza", "stock"]

    def test_all_values_vacio(self):
        assert _all_values({}, "dc.subject") == []


# ── INIDEPScraper._parse_search_result ────────────────────────────────────────

class TestParseSearchResult:
    def test_parsea_item_merluza(self, scraper, mock_search_response):
        items = mock_search_response["_embedded"]["searchResult"]["_embedded"]["objects"]
        rec = scraper._parse_search_result(items[0])
        assert rec is not None
        assert rec.uuid == "aaa-111"
        assert rec.año_publicacion == 2023
        assert rec.año_evaluacion == 2023
        assert "merluza" in rec.especie_raw
        assert rec.zona == "Sur 41°S"
        assert rec.cba_recomendada_tn == pytest.approx(300000.0)
        assert len(rec.autores) == 2

    def test_parsea_item_calamar(self, scraper, mock_search_response):
        items = mock_search_response["_embedded"]["searchResult"]["_embedded"]["objects"]
        rec = scraper._parse_search_result(items[1])
        assert rec is not None
        assert rec.especie_norm == "calamar_illex"
        assert rec.cba_recomendada_tn == pytest.approx(150000.0)

    def test_item_vacio(self, scraper):
        assert scraper._parse_search_result({}) is None


# ── INIDEPScraper.scrape_all_metadata (mockeado) ──────────────────────────────

class TestScrapeAllMetadata:
    def test_scrape_paginado(self, scraper, mock_search_response):
        # Simular 2 páginas: primera con 2 items, segunda vacía (fin de paginación)
        empty_response = {
            "_embedded": {
                "searchResult": {
                    "page": {"totalElements": 2, "totalPages": 1, "size": 50, "number": 0},
                    "_embedded": {"objects": []},
                }
            }
        }

        with patch.object(scraper, "_get_json", return_value=mock_search_response):
            # Con totalPages=10 pero items vacíos después de la primera, solo la primera
            mock_search_response["_embedded"]["searchResult"]["page"]["totalPages"] = 1
            records = scraper.scrape_all_metadata()

        assert len(records) == 2

    def test_limite_max_items(self, scraper, mock_search_response):
        mock_search_response["_embedded"]["searchResult"]["page"]["totalPages"] = 1
        with patch.object(scraper, "_get_json", return_value=mock_search_response):
            records = scraper.scrape_all_metadata(max_items=1)
        assert len(records) == 1

    def test_get_total_itos(self, scraper, mock_search_response):
        single_item_resp = {
            "_embedded": {
                "searchResult": {
                    "page": {"totalElements": 492, "totalPages": 10},
                    "_embedded": {"objects": []},
                }
            }
        }
        with patch.object(scraper, "_get_json", return_value=single_item_resp):
            total = scraper.get_total_itos()
        assert total == 492
