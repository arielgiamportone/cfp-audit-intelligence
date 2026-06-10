"""Tests para el validador cruzado geovisor SERE (INIDEP) vs. corpus de actas CFP."""

import sqlite3
from pathlib import Path

import pytest

from src.analysis.geovisor_cross_validator import (
    CoberturaResolucion,
    GeovisorCrossValidator,
    _normalizar_anio,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def db_vacia(tmp_path) -> Path:
    """BD vacía con el esquema mínimo de `resoluciones` (sin `vedas_geoespaciales`)."""
    db = tmp_path / "catalog.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS resoluciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            acta_id INTEGER,
            numero TEXT,
            tipo TEXT,
            texto_completo TEXT,
            texto_resumen TEXT
        );
        """
    )
    conn.commit()
    conn.close()
    return db


@pytest.fixture
def db_con_vedas(db_vacia) -> Path:
    """
    BD con `vedas_geoespaciales` poblada y resoluciones del corpus que permiten
    ejercitar los tres casos: cita CFP cubierta, cita CFP no cubierta, y la
    colisión CFP/CTMFM (mismo número/año, organismos distintos) que NO debe
    contarse como cobertura.
    """
    conn = sqlite3.connect(db_con_vedas := db_vacia)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS vedas_geoespaciales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            capa TEXT,
            especie TEXT,
            resolucion_numero TEXT,
            resolucion_fuente TEXT,
            resolucion_url TEXT
        );
        """
    )
    # Cita CFP "12/2018" — cubierta por el corpus (acta cita "Resolución CFP N° 12/2018")
    conn.execute(
        """INSERT INTO vedas_geoespaciales
           (capa, especie, resolucion_numero, resolucion_fuente, resolucion_url)
           VALUES (?,?,?,?,?)""",
        (
            "vedas_2024:centolla",
            "Centolla",
            "Res. 12/2018",
            "CFP",
            "https://cfp.gob.ar/resoluciones/Resolucion%2012%202018",
        ),
    )
    # Cita CFP "3/2024" — NO cubierta (no aparece en ninguna acta del corpus)
    conn.execute(
        """INSERT INTO vedas_geoespaciales
           (capa, especie, resolucion_numero, resolucion_fuente, resolucion_url)
           VALUES (?,?,?,?,?)""",
        (
            "vedas_2024:Merluza_Hubbsi_invierno",
            "Merluza_Hubbsi",
            "3/2024",
            "CFP",
            "https://cfp.gob.ar/resoluciones/Resolucion%203%202024",
        ),
    )
    # Cita CTMFM "13/2024" — colisión con "Resolución CFP N° 13/2024" en el corpus,
    # pero es un documento DISTINTO (otro organismo): no debe contar como cobertura.
    conn.execute(
        """INSERT INTO vedas_geoespaciales
           (capa, especie, resolucion_numero, resolucion_fuente, resolucion_url)
           VALUES (?,?,?,?,?)""",
        (
            "vedas_2024:Veda_arrastre_fondo_proteccion_de_condrictios",
            "Condrictios",
            "Res. 13/2024",
            "CTMFM",
            "https://ctmfm.org/resoluciones/Res%2013%202024",
        ),
    )
    # Resolución sin número (no debe entrar al cruce)
    conn.execute(
        """INSERT INTO vedas_geoespaciales (capa, especie, resolucion_numero, resolucion_fuente)
           VALUES (?,?,?,?)""",
        ("vedas_2024:abadejo_pozos", "Abadejo", None, "CFP"),
    )

    # Corpus de actas: cita "Resolución CFP N° 12/2018" (cubre la primera veda)
    conn.execute(
        """INSERT INTO resoluciones (acta_id, numero, tipo, texto_completo, texto_resumen)
           VALUES (?,?,?,?,?)""",
        (1, "1.1", "veda", "Se aprueba la Resolución CFP N° 12/2018 sobre veda de centolla.", ""),
    )
    # Corpus de actas: cita "Resolución CFP N° 13/2024" — colisiona en número/año con
    # la veda CTMFM, pero es una resolución CFP distinta (cuota merluza), no la veda.
    conn.execute(
        """INSERT INTO resoluciones (acta_id, numero, tipo, texto_completo, texto_resumen)
           VALUES (?,?,?,?,?)""",
        (2, "2.1", "cuota", "Resolución CFP N° 13/2024 — CMP de merluza común.", ""),
    )
    conn.commit()
    conn.close()
    return db_con_vedas


@pytest.fixture
def validator(db_con_vedas) -> GeovisorCrossValidator:
    return GeovisorCrossValidator(db_con_vedas)


# ── _normalizar_anio ──────────────────────────────────────────────────────────


class TestNormalizarAnio:
    def test_anio_de_4_digitos_se_mantiene(self):
        assert _normalizar_anio("2024") == 2024

    def test_anio_de_2_digitos_se_expande_a_2000(self):
        assert _normalizar_anio("18") == 2018

    def test_anio_de_2_digitos_99_se_expande_a_2099(self):
        assert _normalizar_anio("99") == 2099


# ── _vedas_citadas / _citas_en_corpus ─────────────────────────────────────────


class TestVedasCitadas:
    def test_agrupa_unicas_y_excluye_sin_numero(self, validator):
        vedas = validator._vedas_citadas()
        assert len(vedas) == 3
        numeros = {v["resolucion_numero"] for v in vedas}
        assert numeros == {"Res. 12/2018", "3/2024", "Res. 13/2024"}

    def test_devuelve_lista_vacia_si_tabla_no_existe(self, db_vacia):
        v = GeovisorCrossValidator(db_vacia)
        assert v._vedas_citadas() == []


class TestCitasEnCorpus:
    def test_extrae_numero_y_anio_normalizado(self, validator):
        mapa = validator._citas_en_corpus()
        assert (12, 2018) in mapa
        assert (13, 2024) in mapa

    def test_mapea_a_ids_de_resolucion(self, validator):
        mapa = validator._citas_en_corpus()
        assert mapa[(12, 2018)] == [1]
        assert mapa[(13, 2024)] == [2]


# ── validar_cobertura ─────────────────────────────────────────────────────────


class TestValidarCobertura:
    def test_solo_compara_fuente_cfp(self, validator):
        resultados = validator.validar_cobertura()
        fuentes = {r.resolucion_fuente for r in resultados}
        assert "CTMFM" not in fuentes
        assert fuentes == {"CFP"}

    def test_excluye_colision_ctmfm_de_la_cobertura(self, validator):
        """
        El corpus SÍ contiene "Resolución CFP N° 13/2024" (otra norma, sobre cuota
        de merluza), pero la veda citada con ese mismo número/año es de CTMFM —
        no debe filtrarse en `validar_cobertura` (solo entran fuente=CFP) y por lo
        tanto tampoco aparecer como "encontrada" para ninguna entrada CFP.
        """
        resultados = validator.validar_cobertura()
        numeros_cfp = [r.resolucion_numero for r in resultados]
        assert "Res. 13/2024" not in numeros_cfp

    def test_marca_resolucion_cubierta_por_el_corpus(self, validator):
        resultados = validator.validar_cobertura()
        cubierta = next(r for r in resultados if r.resolucion_numero == "Res. 12/2018")
        assert cubierta.encontrada_en_corpus is True
        assert cubierta.numero_normalizado == (12, 2018)
        assert cubierta.resolucion_ids_corpus == [1]
        assert cubierta.especies == ["Centolla"]

    def test_marca_resolucion_no_cubierta(self, validator):
        resultados = validator.validar_cobertura()
        pendiente = next(r for r in resultados if r.resolucion_numero == "3/2024")
        assert pendiente.encontrada_en_corpus is False
        assert pendiente.resolucion_ids_corpus == []

    def test_ignora_resoluciones_sin_numero(self, validator):
        resultados = validator.validar_cobertura()
        assert all(r.resolucion_numero is not None for r in resultados)

    def test_devuelve_dataclass_cobertura_resolucion(self, validator):
        resultados = validator.validar_cobertura()
        assert all(isinstance(r, CoberturaResolucion) for r in resultados)


# ── cobertura_summary ─────────────────────────────────────────────────────────


class TestCoberturaSummary:
    def test_calcula_porcentaje_de_cobertura(self, validator):
        resumen = validator.cobertura_summary()
        assert resumen["total_resoluciones_citadas_cfp"] == 2
        assert resumen["encontradas_en_corpus"] == 1
        assert resumen["pendientes"] == 1
        assert resumen["pct_cobertura"] == 50.0

    def test_interpretacion_es_legible(self, validator):
        resumen = validator.cobertura_summary()
        assert "1/2" in resumen["interpretacion"]
        assert "50.0%" in resumen["interpretacion"]

    def test_acepta_resultados_precomputados(self, validator):
        resultados = validator.validar_cobertura()
        resumen = validator.cobertura_summary(resultados)
        assert resumen["total_resoluciones_citadas_cfp"] == len(resultados)

    def test_summary_sin_datos_no_falla(self, db_vacia):
        v = GeovisorCrossValidator(db_vacia)
        resumen = v.cobertura_summary()
        assert resumen["total_resoluciones_citadas_cfp"] == 0
        assert resumen["pct_cobertura"] == 0.0


# ── validar_cumplimiento_satelital ────────────────────────────────────────────


@pytest.fixture
def db_con_satelital(tmp_path) -> Path:
    """BD con esfuerzo_satelital y vedas_geoespaciales para probar la validación."""
    db = tmp_path / "catalog.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS vedas_geoespaciales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            capa TEXT,
            especie TEXT,
            especie_code TEXT,
            resolucion_numero TEXT,
            resolucion_fuente TEXT,
            fecha_inicio TEXT,
            fecha_fin TEXT
        );
        CREATE TABLE IF NOT EXISTS esfuerzo_satelital (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            zona TEXT NOT NULL,
            especie_code TEXT,
            fecha TEXT NOT NULL,
            lon REAL,
            lat REAL,
            esfuerzo_gfw REAL,
            UNIQUE(zona, fecha)
        );
        """
    )
    # Veda activa para merluza_hubbsi en jun/2025
    conn.execute(
        "INSERT INTO vedas_geoespaciales (capa, especie_code, fecha_inicio, fecha_fin) "
        "VALUES (?,?,?,?)",
        ("vedas_2024:Merluza_Hubbsi_invierno", "merluza_hubbsi", "2025-06-01", "2025-08-31"),
    )
    # Esfuerzo DENTRO de veda (bajo: ~2.0)
    for d, v in [("2025-06-15", 1.8), ("2025-07-01", 2.2), ("2025-08-01", 1.5)]:
        conn.execute(
            "INSERT INTO esfuerzo_satelital (zona, especie_code, fecha, lon, lat, esfuerzo_gfw) "
            "VALUES (?,?,?,?,?,?)",
            ("golfo_san_jorge_norte", "merluza_hubbsi", d, -65.0, -44.5, v),
        )
    # Esfuerzo FUERA de veda (alto: ~6.0)
    for d, v in [("2025-03-01", 6.1), ("2025-04-01", 5.8), ("2025-10-01", 6.4)]:
        conn.execute(
            "INSERT INTO esfuerzo_satelital (zona, especie_code, fecha, lon, lat, esfuerzo_gfw) "
            "VALUES (?,?,?,?,?,?)",
            ("golfo_san_jorge_norte", "merluza_hubbsi", d, -65.0, -44.5, v),
        )
    conn.commit()
    conn.close()
    return db


class TestValidarCumplimientoSatelital:
    def test_detecta_reduccion_durante_veda(self, db_con_satelital):
        v = GeovisorCrossValidator(db_con_satelital)
        resultado = v.validar_cumplimiento_satelital()
        assert "error" not in resultado
        assert resultado["n_dentro_veda"] == 3
        assert resultado["n_fuera_veda"] == 3
        assert resultado["mediana_esfuerzo_dentro"] < resultado["mediana_esfuerzo_fuera"]
        assert resultado["ratio_reduccion"] < 1.0

    def test_interpretacion_indica_cumplimiento(self, db_con_satelital):
        v = GeovisorCrossValidator(db_con_satelital)
        resultado = v.validar_cumplimiento_satelital()
        assert "cumplimiento" in resultado["interpretacion"].lower()

    def test_error_si_tablas_no_existen(self, db_vacia):
        v = GeovisorCrossValidator(db_vacia)
        resultado = v.validar_cumplimiento_satelital()
        assert "error" in resultado

    def test_error_si_sin_datos_satelitales(self, tmp_path):
        db = tmp_path / "catalog.db"
        conn = sqlite3.connect(db)
        conn.executescript(
            """
            CREATE TABLE esfuerzo_satelital (
                id INTEGER PRIMARY KEY, zona TEXT, especie_code TEXT,
                fecha TEXT, esfuerzo_gfw REAL, UNIQUE(zona,fecha)
            );
            CREATE TABLE vedas_geoespaciales (
                id INTEGER PRIMARY KEY, especie_code TEXT,
                fecha_inicio TEXT, fecha_fin TEXT
            );
            """
        )
        conn.commit()
        conn.close()
        v = GeovisorCrossValidator(db)
        resultado = v.validar_cumplimiento_satelital()
        assert "error" in resultado

    def test_retorna_ratio_y_medianas(self, db_con_satelital):
        v = GeovisorCrossValidator(db_con_satelital)
        resultado = v.validar_cumplimiento_satelital()
        assert resultado["ratio_reduccion"] is not None
        assert resultado["mediana_esfuerzo_dentro"] is not None
        assert resultado["mediana_esfuerzo_fuera"] is not None
