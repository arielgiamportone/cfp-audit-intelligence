"""
Tests del cliente WFS del geovisor SERE (INIDEP) — ADR-009.

Cubre normalización, parseo de features GeoJSON y persistencia en
`vedas_geoespaciales`. No hace llamadas de red reales (mock de _get_features).
"""

import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from src.acquisition.inidep_geovisor_scraper import (
    SCHEMA_VEDAS_GEO,
    VEDAS_LAYERS,
    SEREGeovisorClient,
    VedaGeoespacial,
    _centroid,
    _clean_date,
    _especie_code,
    resoluciones_citadas,
    save_vedas_to_db,
)


class TestCentroid:
    """Punto representativo (centroide aproximado) de geometrías GeoJSON."""

    def test_point(self):
        assert _centroid({"type": "Point", "coordinates": [-60.0, -45.0]}) == (-45.0, -60.0)

    def test_polygon_promedia_vertices(self):
        poly = {
            "type": "Polygon",
            "coordinates": [[[-62, -46], [-58, -46], [-58, -44], [-62, -44]]],
        }
        lat, lon = _centroid(poly)
        assert lat == pytest.approx(-45.0)
        assert lon == pytest.approx(-60.0)

    def test_multipolygon(self):
        geom = {
            "type": "MultiPolygon",
            "coordinates": [[[[-62, -46], [-58, -46], [-58, -44], [-62, -44]]]],
        }
        lat, lon = _centroid(geom)
        assert lat == pytest.approx(-45.0)
        assert lon == pytest.approx(-60.0)

    def test_vacio_o_none(self):
        assert _centroid({}) == (None, None)
        assert _centroid(None) == (None, None)
        assert _centroid({"type": "Point", "coordinates": None}) == (None, None)


class TestPersistenciaCoordenadas:
    """El centroide (lat/lon) se persiste y se puede recuperar."""

    def test_guarda_y_lee_lat_lon(self, tmp_path):
        db = tmp_path / "vedas.db"
        rec = VedaGeoespacial(
            capa="test", especie="Merluza", area="Zona X",
            resolucion_numero="R1", lat=-45.5, lon=-61.0,
        )
        assert save_vedas_to_db([rec], db) == 1
        with sqlite3.connect(db) as conn:
            row = conn.execute("SELECT lat, lon FROM vedas_geoespaciales").fetchone()
        assert row == (-45.5, -61.0)

    def test_migracion_agrega_columnas(self, tmp_path):
        """Una BD sin columnas lat/lon se migra sin perder datos."""
        db = tmp_path / "old.db"
        with sqlite3.connect(db) as conn:
            conn.execute(
                "CREATE TABLE vedas_geoespaciales ("
                "id INTEGER PRIMARY KEY, capa TEXT, especie TEXT, especie_code TEXT, "
                "area TEXT, fecha_inicio TEXT, fecha_fin TEXT, resolucion_numero TEXT, "
                "resolucion_fuente TEXT, resolucion_url TEXT, notas TEXT, geometry_type TEXT)"
            )
        rec = VedaGeoespacial(capa="c", area="A", resolucion_numero="R", lat=-40.0, lon=-58.0)
        save_vedas_to_db([rec], db)  # debe migrar (ALTER TABLE) y no fallar
        with sqlite3.connect(db) as conn:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(vedas_geoespaciales)")}
        assert {"lat", "lon"} <= cols

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def db(tmp_path) -> Path:
    return tmp_path / "geovisor_test.db"


@pytest.fixture
def client() -> SEREGeovisorClient:
    return SEREGeovisorClient(delay=0.0)


@pytest.fixture
def feature_collection_veda() -> dict:
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "MultiPolygon", "coordinates": []},
                "properties": {
                    "Especie": "Centolla",
                    "nam_area": "Zona C V",
                    "Resolucion": "Res. 12/2018",
                    "Fuente": "CFP",
                    "Link_res": "https://cfp.gob.ar/resoluciones/Resolucion%2012.pdf",
                    "Inicio": "2024-06-01Z",
                    "Fin": "2024-12-31Z",
                    "Notas": "Mismo periodo de veda todos los años",
                },
            },
            {
                "type": "Feature",
                "geometry": {"type": "MultiPolygon", "coordinates": []},
                "properties": {
                    "Especie": "Merluza_Negra",
                    "Id_area": "Provincial",
                    "No_Resol": "Res. CFP Nº 12/2019_Art5",
                    "Fuente": "CFP",
                    "Res_link": "https://cfp.gob.ar/resoluciones/Resolucion12_2019.pdf",
                    "Inicio": "2024-07-01Z",
                    "Fin": "2024-09-30Z",
                    "Nota": None,
                },
            },
        ],
    }


@pytest.fixture
def feature_collection_especie() -> dict:
    return {
        "type": "FeatureCollection",
        "totalFeatures": 1897,
        "features": [
            {
                "type": "Feature",
                "id": "Cynoscion_guatucupa.1",
                "geometry": {"type": "Point", "coordinates": [-53, -35.4166]},
                "properties": {
                    "especie": "Cynoscion guatucupa",
                    "nom_comun": "Pescadilla de red",
                    "anio": 1982,
                },
            }
        ],
    }


# ── Helpers de normalización ──────────────────────────────────────────────────


class TestCleanDate:
    def test_quita_sufijo_z(self):
        assert _clean_date("2024-07-01Z") == "2024-07-01"

    def test_sin_sufijo(self):
        assert _clean_date("2024-07-01") == "2024-07-01"

    def test_none(self):
        assert _clean_date(None) is None

    def test_vacio(self):
        assert _clean_date("") is None


class TestEspecieCode:
    def test_merluza_hubbsi(self):
        assert _especie_code("Merluza_Hubbsi") == "merluza_hubbsi"

    def test_centolla(self):
        assert _especie_code("Centolla") == "centolla"

    def test_merluza_negra(self):
        assert _especie_code("Merluza_Negra") == "merluza_negra"

    def test_desconocida_fallback(self):
        assert _especie_code("Especie Rara XYZ") == "especie_rara_xyz"

    def test_none(self):
        assert _especie_code(None) is None


# ── VEDAS_LAYERS ──────────────────────────────────────────────────────────────


class TestVedasLayers:
    def test_no_vacio(self):
        assert len(VEDAS_LAYERS) >= 10

    def test_todas_con_workspace(self):
        for layer in VEDAS_LAYERS:
            assert layer.startswith("vedas_2024:")

    def test_sin_duplicados(self):
        assert len(VEDAS_LAYERS) == len(set(VEDAS_LAYERS))

    def test_cubre_especies_verificadas(self):
        joined = " ".join(VEDAS_LAYERS).lower()
        for especie in ("merluza_hubbsi", "merluza_negra", "centolla", "langostino", "abadejo"):
            assert especie in joined


# ── SEREGeovisorClient.fetch_veda_layer ───────────────────────────────────────


class TestFetchVedaLayer:
    def test_normaliza_features(self, client, feature_collection_veda):
        with patch.object(client, "_get_features", return_value=feature_collection_veda):
            records = client.fetch_veda_layer("vedas_2024:centolla")

        assert len(records) == 2
        assert all(isinstance(r, VedaGeoespacial) for r in records)

    def test_extrae_resolucion_y_link_variante_a(self, client, feature_collection_veda):
        """Variante con Resolucion/Link_res (ej. centolla)."""
        with patch.object(client, "_get_features", return_value=feature_collection_veda):
            records = client.fetch_veda_layer("vedas_2024:centolla")

        r = records[0]
        assert r.especie == "Centolla"
        assert r.area == "Zona C V"
        assert r.resolucion_numero == "Res. 12/2018"
        assert r.resolucion_fuente == "CFP"
        assert r.resolucion_url.startswith("https://cfp.gob.ar/")
        assert r.fecha_inicio == "2024-06-01"
        assert r.fecha_fin == "2024-12-31"
        assert r.geometry_type == "MultiPolygon"

    def test_extrae_resolucion_y_link_variante_b(self, client, feature_collection_veda):
        """Variante con No_Resol/Res_link/Id_area (ej. merluza negra)."""
        with patch.object(client, "_get_features", return_value=feature_collection_veda):
            records = client.fetch_veda_layer("vedas_2024:merluza_negra_veda")

        r = records[1]
        assert r.especie == "Merluza_Negra"
        assert r.area == "Provincial"
        assert r.resolucion_numero == "Res. CFP Nº 12/2019_Art5"
        assert r.resolucion_url.endswith(".pdf")

    def test_capa_propagada(self, client, feature_collection_veda):
        with patch.object(client, "_get_features", return_value=feature_collection_veda):
            records = client.fetch_veda_layer("vedas_2024:centolla")
        assert all(r.capa == "vedas_2024:centolla" for r in records)

    def test_sin_features(self, client):
        with patch.object(client, "_get_features", return_value={"features": []}):
            records = client.fetch_veda_layer("vedas_2024:vacia")
        assert records == []


# ── SEREGeovisorClient.fetch_especie_distribucion ─────────────────────────────


class TestFetchEspecieDistribucion:
    def test_extrae_ocurrencias(self, client, feature_collection_especie):
        with patch.object(client, "_get_features", return_value=feature_collection_especie):
            registros = client.fetch_especie_distribucion(
                "distribucion_especies_oseos:Cynoscion_guatucupa"
            )

        assert len(registros) == 1
        r = registros[0]
        assert r["especie"] == "Cynoscion guatucupa"
        assert r["nom_comun"] == "Pescadilla de red"
        assert r["anio"] == 1982
        assert r["lon"] == pytest.approx(-53)
        assert r["lat"] == pytest.approx(-35.4166)

    def test_sin_geometria(self, client):
        data = {"features": [{"properties": {"especie": "X", "anio": 2000}, "geometry": None}]}
        with patch.object(client, "_get_features", return_value=data):
            registros = client.fetch_especie_distribucion("capa:X")
        assert registros[0]["lon"] is None
        assert registros[0]["lat"] is None


# ── SEREGeovisorClient.scrape_all_vedas ───────────────────────────────────────


class TestScrapeAllVedas:
    def test_agrega_todas_las_capas(self, client):
        fake = [VedaGeoespacial(capa="x", especie="Centolla")]
        with patch.object(client, "fetch_veda_layer", return_value=fake) as m:
            out = client.scrape_all_vedas()

        assert m.call_count == len(VEDAS_LAYERS)
        assert len(out) == len(VEDAS_LAYERS)

    def test_tolera_capas_que_fallan(self, client):
        import requests

        def side_effect(layer):
            if "centolla" in layer:
                raise requests.RequestException("503")
            return [VedaGeoespacial(capa=layer)]

        with patch.object(client, "fetch_veda_layer", side_effect=side_effect):
            out = client.scrape_all_vedas()

        # Todas las capas menos las dos de centolla (centolla + areas_centolla)
        assert len(out) == len(VEDAS_LAYERS) - 2


class TestScrapeAndSaveVedas:
    def test_descarga_y_persiste(self, client, db):
        fake = [
            VedaGeoespacial(
                capa="vedas_2024:centolla",
                especie="Centolla",
                area="Zona C V",
                resolucion_numero="Res. 12/2018",
                resolucion_fuente="CFP",
            )
        ]
        with patch.object(client, "scrape_all_vedas", return_value=fake):
            n = client.scrape_and_save_vedas(db)

        assert n == 1
        with sqlite3.connect(db) as conn:
            row = conn.execute("SELECT COUNT(*) FROM vedas_geoespaciales").fetchone()
        assert row[0] == 1

    def test_es_idempotente(self, client, db):
        fake = [VedaGeoespacial(capa="vedas_2024:centolla", area="Zona C V")]
        with patch.object(client, "scrape_all_vedas", return_value=fake):
            client.scrape_and_save_vedas(db)
            n_segunda = client.scrape_and_save_vedas(db)

        assert n_segunda == 0


# ── Persistencia ──────────────────────────────────────────────────────────────


class TestSaveVedasToDb:
    def test_crea_schema_e_inserta(self, db):
        records = [
            VedaGeoespacial(
                capa="vedas_2024:centolla",
                especie="Centolla",
                area="Zona C V",
                fecha_inicio="2024-06-01",
                fecha_fin="2024-12-31",
                resolucion_numero="Res. 12/2018",
                resolucion_fuente="CFP",
                resolucion_url="https://cfp.gob.ar/r12.pdf",
                geometry_type="MultiPolygon",
            )
        ]
        n = save_vedas_to_db(records, db)
        assert n == 1

        with sqlite3.connect(db) as conn:
            row = conn.execute(
                "SELECT especie, especie_code, resolucion_numero FROM vedas_geoespaciales"
            ).fetchone()
        assert row == ("Centolla", "centolla", "Res. 12/2018")

    def test_idempotente_evita_duplicados(self, db):
        records = [VedaGeoespacial(capa="vedas_2024:centolla", especie="Centolla", area="Zona C V")]
        n1 = save_vedas_to_db(records, db)
        n2 = save_vedas_to_db(records, db)
        assert n1 == 1
        assert n2 == 0

        with sqlite3.connect(db) as conn:
            total = conn.execute("SELECT COUNT(*) FROM vedas_geoespaciales").fetchone()[0]
        assert total == 1

    def test_distingue_por_area(self, db):
        records = [
            VedaGeoespacial(capa="vedas_2024:centolla", especie="Centolla", area="Zona C II"),
            VedaGeoespacial(capa="vedas_2024:centolla", especie="Centolla", area="Zona C V"),
        ]
        n = save_vedas_to_db(records, db)
        assert n == 2

    def test_crea_directorio_padre(self, tmp_path):
        nested = tmp_path / "nested" / "dir" / "geo.db"
        n = save_vedas_to_db([VedaGeoespacial(capa="x")], nested)
        assert n == 1
        assert nested.exists()


class TestSchemaVedasGeo:
    def test_schema_ejecutable(self, db):
        with sqlite3.connect(db) as conn:
            conn.executescript(SCHEMA_VEDAS_GEO)
            tables = {
                r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
        assert "vedas_geoespaciales" in tables


# ── resoluciones_citadas ──────────────────────────────────────────────────────


class TestResolucionesCitadas:
    def test_db_inexistente(self, tmp_path):
        assert resoluciones_citadas(tmp_path / "no_existe.db") == []

    def test_lista_unicas(self, db):
        records = [
            VedaGeoespacial(
                capa="vedas_2024:centolla",
                area="Zona C II",
                resolucion_numero="Res. 12/2018",
                resolucion_fuente="CFP",
                resolucion_url="https://cfp.gob.ar/r12.pdf",
            ),
            VedaGeoespacial(
                capa="vedas_2024:centolla",
                area="Zona C V",
                resolucion_numero="Res. 12/2018",
                resolucion_fuente="CFP",
                resolucion_url="https://cfp.gob.ar/r12.pdf",
            ),
            VedaGeoespacial(
                capa="vedas_2024:merluza_negra_veda",
                area="Provincial",
                resolucion_numero="Res. CFP Nº 12/2019_Art5",
                resolucion_fuente="CFP",
                resolucion_url="https://cfp.gob.ar/r12_2019.pdf",
            ),
        ]
        save_vedas_to_db(records, db)

        citadas = resoluciones_citadas(db)
        numeros = [c["resolucion_numero"] for c in citadas]
        assert "Res. 12/2018" in numeros
        assert "Res. CFP Nº 12/2019_Art5" in numeros
        assert len(numeros) == len(set(numeros)), "no debe haber duplicados"

    def test_excluye_sin_numero(self, db):
        save_vedas_to_db([VedaGeoespacial(capa="x", area="Y", resolucion_numero=None)], db)
        assert resoluciones_citadas(db) == []
