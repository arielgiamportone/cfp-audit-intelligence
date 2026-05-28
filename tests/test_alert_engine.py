"""
Tests del motor de alertas configurables.

Verifica CRUD de reglas, evaluación de condiciones y persistencia del historial.
"""
import sqlite3
import pytest
from pathlib import Path

from src.analysis.alert_engine import (
    AlertEngine,
    AlertaRegla,
    AlertaFired,
    TIPO_CBA_EXCESO,
    TIPO_STOCK_CRITICO,
    TIPO_QUORUM_MINIMO,
    SEV_INFO,
    SEV_WARNING,
    SEV_CRITICAL,
    DEFAULT_RULES,
)


@pytest.fixture
def engine(tmp_path):
    db = tmp_path / "test_alertas.db"
    return AlertEngine(db_path=db)


@pytest.fixture
def engine_con_datos(tmp_path):
    """Motor con datos de comparación y evaluaciones INIDEP precargados."""
    db = tmp_path / "test_datos.db"
    eng = AlertEngine(db_path=db)

    conn = sqlite3.connect(db)
    # Crear tablas necesarias
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS comparacion_cfp_inidep (
            id INTEGER PRIMARY KEY, especie TEXT, especie_code TEXT,
            zona TEXT, year INTEGER, cba_inidep_tn REAL, cmp_cfp_tn REAL,
            ratio_sobreasignacion REAL, acta_cfp TEXT, numero_ito TEXT,
            nivel_alerta TEXT, descripcion_alerta TEXT, created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS inidep_evaluaciones (
            id INTEGER PRIMARY KEY, especie TEXT, especie_code TEXT,
            zona TEXT, year INTEGER, cba_recomendada_tn REAL,
            cba_alternativa_tn REAL, estado_stock TEXT, numero_ito TEXT,
            fuente_url TEXT, notas TEXT, created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS cfp_cuotas (
            id INTEGER PRIMARY KEY, especie TEXT, especie_code TEXT,
            zona TEXT, year INTEGER, cmp_aprobada_tn REAL,
            tipo_decision TEXT, acta_referencia TEXT, resolucion_cfp TEXT,
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS resoluciones (
            id INTEGER PRIMARY KEY, acta_id INTEGER, numero TEXT,
            tipo TEXT, categoria TEXT, texto_resumen TEXT,
            votos_favor INTEGER, votos_contra INTEGER, quorum INTEGER,
            riesgo_score REAL, analisis_ia TEXT
        );
        CREATE TABLE IF NOT EXISTS actas (
            id INTEGER PRIMARY KEY, year INTEGER, nombre TEXT,
            url TEXT, filename TEXT
        );
    """)
    # Datos de comparación: merluza 2022 con 135% CBA → crítica
    conn.execute(
        """INSERT INTO comparacion_cfp_inidep
           (especie, especie_code, zona, year, cba_inidep_tn, cmp_cfp_tn,
            ratio_sobreasignacion, acta_cfp, nivel_alerta, descripcion_alerta)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        ("merluza hubbsi", "merluza_hubbsi", "Sur 41°S", 2022,
         300000, 405000, 1.35, "Acta 187/2022", "critico", "Exceso CBA"),
    )
    # Datos de comparación: langostino 2021 con 110% CBA → amarillo
    conn.execute(
        """INSERT INTO comparacion_cfp_inidep
           (especie, especie_code, zona, year, cba_inidep_tn, cmp_cfp_tn,
            ratio_sobreasignacion, acta_cfp, nivel_alerta, descripcion_alerta)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        ("langostino", "langostino", None, 2021,
         200000, 220000, 1.10, "Acta 175/2021", "amarillo", "Exceso leve"),
    )
    # INIDEP con stock sobrexplotado y cuota asignada
    conn.execute(
        """INSERT INTO inidep_evaluaciones
           (especie, especie_code, zona, year, cba_recomendada_tn, estado_stock, numero_ito)
           VALUES (?,?,?,?,?,?,?)""",
        ("merluza hubbsi", "merluza_hubbsi", "Norte 41°S", 2022, 50000, "sobrexplotado", "ITO 10/2022"),
    )
    conn.execute(
        """INSERT INTO cfp_cuotas
           (especie, especie_code, zona, year, cmp_aprobada_tn, tipo_decision)
           VALUES (?,?,?,?,?,?)""",
        ("merluza hubbsi", "merluza_hubbsi", "Norte 41°S", 2022, 75000, "cuota_captura"),
    )
    conn.commit()
    conn.close()
    return eng


# ── Schema y defaults ─────────────────────────────────────────────────────────

class TestSchema:
    def test_tablas_creadas(self, engine):
        with engine._conn() as conn:
            tables = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()}
        assert "alertas_reglas" in tables
        assert "alertas_historial" in tables

    def test_reglas_default_instaladas(self, engine):
        reglas = engine.get_reglas()
        assert len(reglas) == len(DEFAULT_RULES)

    def test_default_incluye_cba_critico(self, engine):
        reglas = engine.get_reglas()
        criticas = [r for r in reglas if r.severidad == SEV_CRITICAL]
        assert len(criticas) >= 1

    def test_default_incluye_stock_sobrexplotado(self, engine):
        reglas = engine.get_reglas()
        stock = [r for r in reglas if r.tipo == TIPO_STOCK_CRITICO]
        assert len(stock) >= 1


# ── CRUD reglas ───────────────────────────────────────────────────────────────

class TestCRUDReglas:
    def test_upsert_nueva_regla(self, engine):
        regla = AlertaRegla(
            nombre="Test rule",
            tipo=TIPO_CBA_EXCESO,
            severidad=SEV_WARNING,
            umbral_pct=120.0,
        )
        rid = engine.upsert_regla(regla)
        assert rid > 0

    def test_get_reglas_solo_activas(self, engine):
        # Desactivar todas las defaults
        for r in engine.get_reglas():
            engine.toggle_regla(r.id, False)
        activas = engine.get_reglas(solo_activas=True)
        assert activas == []

    def test_toggle_regla(self, engine):
        reglas = engine.get_reglas()
        regla = reglas[0]
        engine.toggle_regla(regla.id, False)
        reglas_updated = engine.get_reglas()
        regla_updated = next(r for r in reglas_updated if r.id == regla.id)
        assert regla_updated.activa is False

    def test_delete_regla(self, engine):
        n_before = len(engine.get_reglas())
        regla = engine.get_reglas()[0]
        engine.delete_regla(regla.id)
        assert len(engine.get_reglas()) == n_before - 1

    def test_upsert_actualiza_existente(self, engine):
        regla = engine.get_reglas()[0]
        regla.umbral_pct = 999.0
        engine.upsert_regla(regla)
        actualizada = next(r for r in engine.get_reglas() if r.id == regla.id)
        assert actualizada.umbral_pct == 999.0


# ── AlertaRegla.aplica_a ──────────────────────────────────────────────────────

class TestAplicaA:
    def test_sin_filtros_aplica_todo(self):
        r = AlertaRegla(nombre="x", tipo=TIPO_CBA_EXCESO)
        assert r.aplica_a("merluza_hubbsi", "Sur 41°S", 2022)

    def test_filtro_especie_match(self):
        r = AlertaRegla(nombre="x", tipo=TIPO_CBA_EXCESO, especie_code="merluza_hubbsi")
        assert r.aplica_a("merluza_hubbsi", None, 2022)

    def test_filtro_especie_no_match(self):
        r = AlertaRegla(nombre="x", tipo=TIPO_CBA_EXCESO, especie_code="langostino")
        assert not r.aplica_a("merluza_hubbsi", None, 2022)

    def test_filtro_year_fuera_rango(self):
        r = AlertaRegla(nombre="x", tipo=TIPO_CBA_EXCESO, year_desde=2020, year_hasta=2025)
        assert not r.aplica_a("merluza_hubbsi", None, 2019)
        assert r.aplica_a("merluza_hubbsi", None, 2022)
        assert not r.aplica_a("merluza_hubbsi", None, 2026)

    def test_filtro_zona_match(self):
        r = AlertaRegla(nombre="x", tipo=TIPO_CBA_EXCESO, zona="Sur 41°S")
        assert r.aplica_a("merluza_hubbsi", "Sur 41°S", 2022)
        assert not r.aplica_a("merluza_hubbsi", "Norte 41°S", 2022)


# ── Evaluación con datos ──────────────────────────────────────────────────────

class TestEvaluacion:
    def test_eval_genera_alertas_cba(self, engine_con_datos):
        alertas = engine_con_datos.evaluate()
        cba_alerts = [a for a in alertas if a.tipo == TIPO_CBA_EXCESO]
        assert len(cba_alerts) >= 1

    def test_eval_detecta_merluza_critica(self, engine_con_datos):
        alertas = engine_con_datos.evaluate()
        merluza_critica = [
            a for a in alertas
            if a.tipo == TIPO_CBA_EXCESO
            and a.especie_code == "merluza_hubbsi"
            and a.severidad == SEV_CRITICAL
        ]
        assert len(merluza_critica) >= 1

    def test_eval_detecta_stock_sobrexplotado(self, engine_con_datos):
        alertas = engine_con_datos.evaluate()
        stock_alerts = [a for a in alertas if a.tipo == TIPO_STOCK_CRITICO]
        assert len(stock_alerts) >= 1

    def test_eval_langostino_no_critica(self, engine_con_datos):
        """Langostino 110% no dispara alerta crítica (umbral 130%)."""
        alertas = engine_con_datos.evaluate()
        lang_critica = [
            a for a in alertas
            if a.tipo == TIPO_CBA_EXCESO
            and a.especie_code == "langostino"
            and a.severidad == SEV_CRITICAL
        ]
        assert len(lang_critica) == 0

    def test_eval_persiste_en_historial(self, engine_con_datos):
        engine_con_datos.evaluate(clear_previous=True)
        df = engine_con_datos.get_historial(solo_abiertas=True)
        assert len(df) > 0

    def test_clear_previous_limpia(self, engine_con_datos):
        engine_con_datos.evaluate()
        n1 = len(engine_con_datos.get_historial())
        engine_con_datos.evaluate(clear_previous=True)
        n2 = len(engine_con_datos.get_historial())
        assert n2 <= n1

    def test_resolve_alerta(self, engine_con_datos):
        engine_con_datos.evaluate()
        df = engine_con_datos.get_historial(solo_abiertas=True)
        if not df.empty:
            aid = int(df.iloc[0]["id"])
            engine_con_datos.resolve_alerta(aid)
            df2 = engine_con_datos.get_historial(solo_abiertas=True)
            assert aid not in df2["id"].tolist()


# ── get_historial filtros ─────────────────────────────────────────────────────

class TestHistorialFiltros:
    def test_filtro_severidad_min(self, engine_con_datos):
        engine_con_datos.evaluate()
        df_all = engine_con_datos.get_historial(severidad_min=SEV_INFO)
        df_crit = engine_con_datos.get_historial(severidad_min=SEV_CRITICAL)
        assert len(df_all) >= len(df_crit)

    def test_filtro_year(self, engine_con_datos):
        engine_con_datos.evaluate()
        df = engine_con_datos.get_historial(year_desde=2023, year_hasta=2023)
        # No hay datos de 2023 en el fixture
        assert df.empty or all(df["year"] == 2023)

    def test_filtro_especie_code(self, engine_con_datos):
        engine_con_datos.evaluate()
        df = engine_con_datos.get_historial(especie_code="merluza_hubbsi")
        if not df.empty:
            assert all(df["especie_code"] == "merluza_hubbsi")


# ── get_summary ───────────────────────────────────────────────────────────────

class TestSummary:
    def test_summary_vacio(self, engine):
        s = engine.get_summary()
        assert s["total"] == 0
        assert s["criticas"] == 0
        assert s["n_reglas"] == len(DEFAULT_RULES)

    def test_summary_despues_eval(self, engine_con_datos):
        engine_con_datos.evaluate()
        s = engine_con_datos.get_summary()
        assert s["total"] > 0
        assert s["criticas"] >= 0
