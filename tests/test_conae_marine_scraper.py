"""Tests para el cliente WMS del geoportal marino CONAE (ADR-010)."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.acquisition.conae_marine_scraper import (
    LAYER_GFW_AIS,
    ZONAS_MUESTRA,
    CONAEMarineClient,
    EsfuerzoSatelital,
    _bbox,
    _parse_raster_value,
    get_esfuerzo_df,
    save_esfuerzo_to_db,
)

# ── _parse_raster_value ───────────────────────────────────────────────────────


def test_parse_raster_value_gray_index():
    data = {"features": [{"properties": {"GRAY_INDEX": 18.5}}]}
    assert _parse_raster_value(data) == pytest.approx(18.5)


def test_parse_raster_value_fallback_keys():
    """Prueba claves alternativas que puede usar GeoServer."""
    for key in ("value", "Value", "DN", "band1"):
        data = {"features": [{"properties": {key: 7.2}}]}
        assert _parse_raster_value(data) == pytest.approx(7.2), f"Falla con clave '{key}'"


def test_parse_raster_value_nodata_returns_none():
    """Valores NoData (< -9000) se retornan como None."""
    data = {"features": [{"properties": {"GRAY_INDEX": -9999.0}}]}
    assert _parse_raster_value(data) is None


def test_parse_raster_value_empty_features():
    assert _parse_raster_value({"features": []}) is None


def test_parse_raster_value_no_features_key():
    assert _parse_raster_value({}) is None


def test_parse_raster_value_unknown_key_returns_none():
    data = {"features": [{"properties": {"unknown_key": 5.0}}]}
    assert _parse_raster_value(data) is None


# ── _bbox ─────────────────────────────────────────────────────────────────────


def test_bbox_format():
    result = _bbox(-65.0, -44.5)
    parts = result.split(",")
    assert len(parts) == 4
    lon_min, lat_min, lon_max, lat_max = map(float, parts)
    assert lon_min == pytest.approx(-65.1)
    assert lat_min == pytest.approx(-44.6)
    assert lon_max == pytest.approx(-64.9)
    assert lat_max == pytest.approx(-44.4)


def test_bbox_custom_delta():
    result = _bbox(-57.0, -39.0, delta=0.5)
    parts = list(map(float, result.split(",")))
    assert parts[0] == pytest.approx(-57.5)
    assert parts[2] == pytest.approx(-56.5)


# ── CONAEMarineClient._get_feature_info ───────────────────────────────────────


@pytest.fixture
def mock_response_value():
    """Respuesta WMS GetFeatureInfo con GRAY_INDEX = 42.3."""
    mock = MagicMock()
    mock.json.return_value = {"features": [{"properties": {"GRAY_INDEX": 42.3}}]}
    mock.raise_for_status = MagicMock()
    return mock


@pytest.fixture
def mock_response_nodata():
    """Respuesta WMS con features vacías (píxel fuera de cobertura)."""
    mock = MagicMock()
    mock.json.return_value = {"features": []}
    mock.raise_for_status = MagicMock()
    return mock


def test_get_feature_info_returns_value(mock_response_value):
    client = CONAEMarineClient(delay=0)
    with patch.object(client._session, "get", return_value=mock_response_value):
        val = client._get_feature_info("Pesca:GFW_AIS_EPA_1", -65.0, -44.5)
    assert val == pytest.approx(42.3)


def test_get_feature_info_correct_params(mock_response_value):
    """Verifica que los parámetros WMS enviados son correctos."""
    client = CONAEMarineClient(delay=0)
    with patch.object(client._session, "get", return_value=mock_response_value) as mock_get:
        client._get_feature_info("Pesca:GFW_AIS_EPA_1", -65.0, -44.5)

    call_kwargs = mock_get.call_args
    params = call_kwargs[1]["params"] if call_kwargs[1] else call_kwargs[0][1]
    assert params["SERVICE"] == "WMS"
    assert params["REQUEST"] == "GetFeatureInfo"
    assert params["LAYERS"] == "Pesca:GFW_AIS_EPA_1"
    assert params["X"] == 5
    assert params["Y"] == 5
    assert params["INFO_FORMAT"] == "application/json"
    assert params["SRS"] == "EPSG:4326"


def test_get_feature_info_nodata_returns_none(mock_response_nodata):
    client = CONAEMarineClient(delay=0)
    with patch.object(client._session, "get", return_value=mock_response_nodata):
        val = client._get_feature_info("Pesca:GFW_AIS_EPA_1", -65.0, -44.5)
    assert val is None


# ── CONAEMarineClient._sample_layer_group ─────────────────────────────────────


def test_sample_layer_group_uses_first_non_null():
    """Si tile _1 da None y tile _2 da un valor, retorna el valor de _2."""
    client = CONAEMarineClient(delay=0)

    side_effects = [None, 15.7]
    call_count = 0

    def fake_get_feature_info(layer, lon, lat):
        nonlocal call_count
        v = side_effects[min(call_count, len(side_effects) - 1)]
        call_count += 1
        return v

    with patch.object(client, "_get_feature_info", side_effect=fake_get_feature_info):
        val = client._sample_layer_group(LAYER_GFW_AIS, -65.0, -44.5)

    assert val == pytest.approx(15.7)
    assert call_count == 2


def test_sample_layer_group_all_none_returns_none():
    """Si todos los tiles dan None, retorna None."""
    client = CONAEMarineClient(delay=0)
    with patch.object(client, "_get_feature_info", return_value=None):
        val = client._sample_layer_group(LAYER_GFW_AIS, -65.0, -44.5)
    assert val is None


# ── CONAEMarineClient.sample_point ────────────────────────────────────────────


def test_sample_point_returns_dataclass():
    client = CONAEMarineClient(delay=0)

    def fake_sample(prefix, lon, lat):
        return {"Pesca:GFW_AIS_EPA": 5.2, "Pesca:SNPP_VIIRS_SST": 14.1}.get(prefix)

    with patch.object(client, "_sample_layer_group", side_effect=fake_sample):
        rec = client.sample_point(
            zona="golfo_san_jorge_norte",
            lon=-65.0,
            lat=-44.5,
            especie_code="merluza_hubbsi",
            fecha="2026-06-01",
        )

    assert isinstance(rec, EsfuerzoSatelital)
    assert rec.zona == "golfo_san_jorge_norte"
    assert rec.especie_code == "merluza_hubbsi"
    assert rec.fecha == "2026-06-01"
    assert rec.lon == pytest.approx(-65.0)
    assert rec.lat == pytest.approx(-44.5)


def test_sample_point_uses_today_if_no_fecha():
    from datetime import date

    client = CONAEMarineClient(delay=0)
    with patch.object(client, "_sample_layer_group", return_value=None):
        rec = client.sample_point(zona="test_zone", lon=-60.0, lat=-40.0)

    assert rec.fecha == date.today().isoformat()


# ── save_esfuerzo_to_db ───────────────────────────────────────────────────────


@pytest.fixture
def db_vacia(tmp_path) -> Path:
    return tmp_path / "catalog.db"


def _make_record(zona: str = "test_zona", fecha: str = "2026-01-01") -> EsfuerzoSatelital:
    return EsfuerzoSatelital(
        zona=zona,
        especie_code="merluza_hubbsi",
        fecha=fecha,
        lon=-65.0,
        lat=-44.5,
        sst=12.3,
        sst_noche=11.8,
        clorofila=0.42,
        clorofila_8d=0.38,
        esfuerzo_gfw=3.1,
        luces_noche=None,
    )


def test_save_esfuerzo_inserts_record(db_vacia):
    rec = _make_record()
    n = save_esfuerzo_to_db([rec], db_vacia)
    assert n == 1

    with sqlite3.connect(db_vacia) as conn:
        row = conn.execute("SELECT * FROM esfuerzo_satelital").fetchone()
    assert row is not None


def test_save_esfuerzo_idempotente(db_vacia):
    """Segunda inserción del mismo (zona, fecha) es ignorada."""
    rec = _make_record()
    save_esfuerzo_to_db([rec], db_vacia)
    n2 = save_esfuerzo_to_db([rec], db_vacia)
    assert n2 == 0


def test_save_esfuerzo_multiple_fechas(db_vacia):
    records = [_make_record(fecha=f"2026-0{i}-01") for i in range(1, 4)]
    n = save_esfuerzo_to_db(records, db_vacia)
    assert n == 3


def test_save_esfuerzo_creates_schema(tmp_path):
    db = tmp_path / "nuevo.db"
    save_esfuerzo_to_db([], db)
    with sqlite3.connect(db) as conn:
        tables = {
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
    assert "esfuerzo_satelital" in tables


def test_save_esfuerzo_null_values_allowed(db_vacia):
    """Permite insertar registros con todos los campos de variables como NULL."""
    rec = EsfuerzoSatelital(
        zona="zona_nula",
        especie_code=None,
        fecha="2026-06-10",
        lon=-60.0,
        lat=-40.0,
    )
    n = save_esfuerzo_to_db([rec], db_vacia)
    assert n == 1


# ── get_esfuerzo_df ───────────────────────────────────────────────────────────


def test_get_esfuerzo_df_empty_if_no_db(tmp_path):
    df = get_esfuerzo_df(tmp_path / "nonexistent.db")
    assert df is not None
    assert len(df) == 0


def test_get_esfuerzo_df_returns_data(db_vacia):
    save_esfuerzo_to_db([_make_record()], db_vacia)
    df = get_esfuerzo_df(db_vacia)
    assert len(df) == 1
    assert "esfuerzo_gfw" in df.columns


def test_get_esfuerzo_df_filtro_zona(db_vacia):
    save_esfuerzo_to_db(
        [_make_record("zona_a", "2026-01-01"), _make_record("zona_b", "2026-01-01")],
        db_vacia,
    )
    df = get_esfuerzo_df(db_vacia, zona="zona_a")
    assert len(df) == 1
    assert df["zona"].iloc[0] == "zona_a"


# ── ZONAS_MUESTRA ─────────────────────────────────────────────────────────────


def test_zonas_muestra_estructura():
    """Todas las zonas tienen los campos requeridos con coordenadas plausibles."""
    for z in ZONAS_MUESTRA:
        assert "zona" in z
        assert "especie_code" in z
        assert "lat" in z
        assert "lon" in z
        assert -65.0 <= z["lat"] <= -35.0, f"Latitud fuera de rango ZEE: {z}"
        assert -80.0 <= z["lon"] <= -40.0, f"Longitud fuera de rango ZEE: {z}"


def test_zonas_muestra_zonas_unicas():
    nombres = [z["zona"] for z in ZONAS_MUESTRA]
    assert len(nombres) == len(set(nombres))
