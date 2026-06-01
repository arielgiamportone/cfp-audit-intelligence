"""
Tests del Comparador CFP vs. INIDEP.

Verifica la lógica de alertas, persistencia en SQLite y cálculo de ratios.
Incluye tests del triángulo de auditoría (CBA · CMP · Captura Real).
"""
import sqlite3

import pytest

from src.analysis.inidep_comparator import (
    ALERTA_AMARILLA,
    ALERTA_CRITICA,
    ALERTA_ROJA,
    ALERTA_SIN_DATOS,
    ALERTA_VERDE,
    AlertaComparacion,
    INIDEPComparator,
)


@pytest.fixture
def comp(tmp_db):
    """Comparador inicializado con DB temporal (sin seed automático)."""
    c = INIDEPComparator(tmp_db)
    return c


# ── Inicialización y schema ────────────────────────────────────────────────────

class TestInit:
    def test_crea_tablas(self, tmp_db):
        INIDEPComparator(tmp_db)
        with sqlite3.connect(tmp_db) as conn:
            tables = [
                r[0] for r in
                conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            ]
        assert "inidep_evaluaciones" in tables
        assert "cfp_cuotas" in tables
        assert "comparacion_cfp_inidep" in tables
        assert "capturas_reales" in tables

    def test_seed_carga_datos(self, tmp_db):
        """El seed INIDEP se carga en la primera inicialización."""
        from src.acquisition.inidep_scraper import SEED_DATA
        comp = INIDEPComparator(tmp_db)
        df = comp.get_inidep_data()
        assert len(df) == len(SEED_DATA)

    def test_seed_no_duplica(self, tmp_db):
        """Doble inicialización no duplica el seed."""
        from src.acquisition.inidep_scraper import SEED_DATA
        INIDEPComparator(tmp_db)
        INIDEPComparator(tmp_db)
        comp = INIDEPComparator(tmp_db)
        df = comp.get_inidep_data()
        assert len(df) == len(SEED_DATA)

    def test_seed_capturas_carga(self, tmp_db):
        """El seed SAGPyA se carga en la primera inicialización."""
        from src.acquisition.sipa_scraper import SEED_DATA_CAPTURAS
        comp = INIDEPComparator(tmp_db)
        df = comp.get_capturas_data()
        assert len(df) == len(SEED_DATA_CAPTURAS)

    def test_seed_capturas_no_duplica(self, tmp_db):
        """Doble inicialización no duplica capturas_reales."""
        from src.acquisition.sipa_scraper import SEED_DATA_CAPTURAS
        INIDEPComparator(tmp_db)
        INIDEPComparator(tmp_db)
        comp = INIDEPComparator(tmp_db)
        df = comp.get_capturas_data()
        assert len(df) == len(SEED_DATA_CAPTURAS)

    def test_migrate_schema_idempotente(self, tmp_db):
        """La migración puede correr múltiples veces sin error."""
        comp = INIDEPComparator(tmp_db)
        comp._migrate_schema()
        comp._migrate_schema()  # no debe lanzar excepción

    def test_comparacion_tiene_columna_captura_real(self, tmp_db):
        """La tabla comparacion_cfp_inidep incluye captura_real_tn y alerta_captura."""
        INIDEPComparator(tmp_db)
        with sqlite3.connect(tmp_db) as conn:
            cols = [
                r[1] for r in conn.execute(
                    "PRAGMA table_info(comparacion_cfp_inidep)"
                ).fetchall()
            ]
        assert "captura_real_tn" in cols
        assert "alerta_captura" in cols


# ── upsert_inidep_evaluacion ──────────────────────────────────────────────────

class TestUpsertInidepEvaluacion:
    def test_inserta_evaluacion(self, comp, sample_inidep_record):
        count_before = len(comp.get_inidep_data())
        comp.upsert_inidep_evaluacion(sample_inidep_record)
        count_after = len(comp.get_inidep_data())
        assert count_after == count_before + 1

    def test_datos_correctos(self, comp, sample_inidep_record):
        count_before = len(comp.get_inidep_data())
        comp.upsert_inidep_evaluacion(sample_inidep_record)
        df = comp.get_inidep_data()
        assert len(df) == count_before + 1
        inserted = df[
            (df["especie_code"] == "merluza_hubbsi")
            & (df["year"] == 2025)
            & (df["zona"] == "Sur 41°S")
        ]
        assert len(inserted) >= 1
        assert inserted.iloc[-1]["cba_recomendada_tn"] == 319_000.0


# ── upsert_cfp_cuota ──────────────────────────────────────────────────────────

class TestUpsertCfpCuota:
    def test_inserta_cuota(self, comp):
        comp.upsert_cfp_cuota(
            especie="merluza común",
            especie_code="merluza_hubbsi",
            year=2025,
            cmp_aprobada_tn=350_000.0,
            zona="Sur 41°S",
            acta_referencia="Acta 34/2025",
        )
        df = comp.get_cfp_data()
        assert len(df) == 1
        assert df.iloc[0]["cmp_aprobada_tn"] == 350_000.0

    def test_cuota_sin_zona(self, comp):
        comp.upsert_cfp_cuota(
            especie="polaca",
            especie_code="polaca",
            year=2025,
            cmp_aprobada_tn=30_000.0,
        )
        df = comp.get_cfp_data()
        assert len(df) == 1


# ── compute_comparisons — lógica de alertas ───────────────────────────────────

class TestComputeComparisons:

    def _setup_pair(self, comp, cba, cmp, zona="Sur 41°S"):
        """Helper: inserta un par CBA/CMP para testear el nivel de alerta."""
        with sqlite3.connect(comp.db_path) as conn:
            conn.execute(
                """INSERT INTO inidep_evaluaciones
                   (especie, especie_code, zona, year, cba_recomendada_tn,
                    estado_stock, numero_ito, fuente_url, notas)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                ("test especie", "test_especie", zona, 2025, cba,
                 "saludable", "ITO/test", "http://test", ""),
            )
            conn.execute(
                """INSERT INTO cfp_cuotas
                   (especie, especie_code, zona, year, cmp_aprobada_tn, tipo_decision)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                ("test especie", "test_especie", zona, 2025, cmp, "CMP"),
            )
            conn.commit()

    def _clean_comp(self, tmp_db):
        """Crea un comparador limpio (sin seed) para tests aislados."""
        comp = INIDEPComparator.__new__(INIDEPComparator)
        comp.db_path = tmp_db
        comp._init_schema()
        comp._migrate_schema()
        with sqlite3.connect(tmp_db) as conn:
            conn.execute("DELETE FROM inidep_evaluaciones")
            conn.execute("DELETE FROM capturas_reales")
            conn.commit()
        return comp

    def test_alerta_verde(self, tmp_db):
        """CMP = CBA → verde."""
        comp = self._clean_comp(tmp_db)
        self._setup_pair(comp, cba=100_000, cmp=100_000)
        alertas = comp.compute_comparisons()
        test_alertas = [a for a in alertas if a.especie == "test especie"]
        assert len(test_alertas) == 1
        assert test_alertas[0].nivel == ALERTA_VERDE
        assert test_alertas[0].ratio == pytest.approx(1.0)

    def test_alerta_verde_bajo_cba(self, tmp_db):
        """CMP < CBA → verde."""
        comp = self._clean_comp(tmp_db)
        self._setup_pair(comp, cba=100_000, cmp=90_000)
        alertas = comp.compute_comparisons()
        test_alertas = [a for a in alertas if a.especie == "test especie"]
        assert test_alertas[0].nivel == ALERTA_VERDE

    def test_alerta_amarilla(self, tmp_db):
        """CMP = 110% CBA → amarillo."""
        comp = self._clean_comp(tmp_db)
        self._setup_pair(comp, cba=100_000, cmp=110_000)
        alertas = comp.compute_comparisons()
        test_alertas = [a for a in alertas if a.especie == "test especie"]
        assert test_alertas[0].nivel == ALERTA_AMARILLA

    def test_alerta_roja(self, tmp_db):
        """CMP = 120% CBA → rojo."""
        comp = self._clean_comp(tmp_db)
        self._setup_pair(comp, cba=100_000, cmp=120_000)
        alertas = comp.compute_comparisons()
        test_alertas = [a for a in alertas if a.especie == "test especie"]
        assert test_alertas[0].nivel == ALERTA_ROJA

    def test_alerta_critica(self, tmp_db):
        """CMP = 150% CBA → crítico."""
        comp = self._clean_comp(tmp_db)
        self._setup_pair(comp, cba=100_000, cmp=150_000)
        alertas = comp.compute_comparisons()
        test_alertas = [a for a in alertas if a.especie == "test especie"]
        assert test_alertas[0].nivel == ALERTA_CRITICA

    def test_sin_cuota_cfp(self, comp):
        """INIDEP sin cuota CFP → sin_datos."""
        comp.upsert_inidep_evaluacion({
            "especie": "abadejo",
            "especie_code": "abadejo_test",
            "zona": "Plataforma",
            "year": 2025,
            "cba_recomendada_tn": 3_600.0,
            "cba_alternativa_tn": None,
            "estado_stock": "incierto",
            "numero_ito": "test",
            "fuente_url": "http://test",
            "notas": "",
        })
        alertas = comp.compute_comparisons()
        test_alertas = [a for a in alertas if a.especie == "abadejo"]
        assert any(a.nivel == ALERTA_SIN_DATOS for a in test_alertas)

    def test_calculo_diferencia(self, tmp_db):
        """La diferencia CMP - CBA se calcula correctamente."""
        comp = self._clean_comp(tmp_db)
        self._setup_pair(comp, cba=100_000, cmp=130_000)
        alertas = comp.compute_comparisons()
        test_alertas = [a for a in alertas if a.especie == "test especie"]
        assert test_alertas[0].diferencia_tn == pytest.approx(30_000.0)

    def test_persiste_en_tabla(self, tmp_db):
        """Los resultados se persisten en comparacion_cfp_inidep."""
        comp = self._clean_comp(tmp_db)
        self._setup_pair(comp, cba=100_000, cmp=110_000)
        comp.compute_comparisons()
        with sqlite3.connect(tmp_db) as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM comparacion_cfp_inidep"
            ).fetchone()[0]
        assert count > 0

    def test_captura_real_en_alerta(self, tmp_db):
        """Con captura_real disponible, alerta_captura se calcula."""
        comp = self._clean_comp(tmp_db)
        self._setup_pair(comp, cba=100_000, cmp=110_000)
        with sqlite3.connect(tmp_db) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO capturas_reales "
                "(especie, especie_code, year, captura_tn) VALUES (?, ?, ?, ?)",
                ("test especie", "test_especie", 2025, 95_000),
            )
            conn.commit()
        alertas = comp.compute_comparisons()
        test_alertas = [a for a in alertas if a.especie == "test especie"]
        assert test_alertas[0].captura_real_tn == 95_000
        assert test_alertas[0].alerta_captura is not None

    def test_alerta_captura_verde_bajo_cba(self, tmp_db):
        """Captura real ≤ CBA y ≥ 70% CMP → verde."""
        comp = self._clean_comp(tmp_db)
        self._setup_pair(comp, cba=100_000, cmp=100_000)
        with sqlite3.connect(tmp_db) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO capturas_reales "
                "(especie, especie_code, year, captura_tn) VALUES (?, ?, ?, ?)",
                ("test especie", "test_especie", 2025, 90_000),
            )
            conn.commit()
        alertas = comp.compute_comparisons()
        test_alertas = [a for a in alertas if a.especie == "test especie"]
        assert test_alertas[0].alerta_captura == "verde"

    def test_alerta_captura_sub_utilizacion(self, tmp_db):
        """Captura real < 70% CMP → sub_utilizacion."""
        comp = self._clean_comp(tmp_db)
        self._setup_pair(comp, cba=100_000, cmp=100_000)
        with sqlite3.connect(tmp_db) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO capturas_reales "
                "(especie, especie_code, year, captura_tn) VALUES (?, ?, ?, ?)",
                ("test especie", "test_especie", 2025, 60_000),
            )
            conn.commit()
        alertas = comp.compute_comparisons()
        test_alertas = [a for a in alertas if a.especie == "test especie"]
        assert test_alertas[0].alerta_captura == "sub_utilizacion"

    def test_alerta_captura_critico(self, tmp_db):
        """Captura real > 130% CBA → critico."""
        comp = self._clean_comp(tmp_db)
        self._setup_pair(comp, cba=100_000, cmp=140_000)
        with sqlite3.connect(tmp_db) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO capturas_reales "
                "(especie, especie_code, year, captura_tn) VALUES (?, ?, ?, ?)",
                ("test especie", "test_especie", 2025, 140_000),
            )
            conn.commit()
        alertas = comp.compute_comparisons()
        test_alertas = [a for a in alertas if a.especie == "test especie"]
        assert test_alertas[0].alerta_captura == "critico"

    def test_sin_captura_real_alerta_captura_sin_datos(self, tmp_db):
        """Sin captura_real disponible → alerta_captura = sin_datos."""
        comp = self._clean_comp(tmp_db)
        self._setup_pair(comp, cba=100_000, cmp=110_000)
        alertas = comp.compute_comparisons()
        test_alertas = [a for a in alertas if a.especie == "test especie"]
        assert test_alertas[0].captura_real_tn is None
        assert test_alertas[0].alerta_captura == "sin_datos"


# ── AlertaComparacion dataclass ───────────────────────────────────────────────

class TestAlertaComparacionDataclass:
    def test_tiene_campos_triangulo(self):
        """AlertaComparacion incluye captura_real_tn y alerta_captura."""
        import dataclasses
        fields = {f.name for f in dataclasses.fields(AlertaComparacion)}
        assert "captura_real_tn" in fields
        assert "alerta_captura" in fields

    def test_campos_triangulo_opcionales(self):
        """captura_real_tn y alerta_captura tienen default=None."""
        a = AlertaComparacion(
            especie="merluza", zona="Sur", year=2025,
            cba_inidep_tn=100_000, cmp_cfp_tn=110_000,
            diferencia_tn=10_000, ratio=1.1,
            nivel="amarillo", descripcion="test",
            numero_ito=None, acta_cfp=None,
        )
        assert a.captura_real_tn is None
        assert a.alerta_captura is None


# ── get_triangulo_completo ────────────────────────────────────────────────────

class TestGetTrianguloCompleto:

    def test_retorna_dataframe(self, comp):
        df = comp.get_triangulo_completo()
        import pandas as pd
        assert isinstance(df, pd.DataFrame)

    def test_columnas_presentes(self, comp):
        df = comp.get_triangulo_completo()
        for col in ["especie", "year", "cba_recomendada_tn", "ratio_cmp_cba", "ratio_captura_cba"]:
            assert col in df.columns

    def test_filtro_especie(self, comp):
        df_all = comp.get_triangulo_completo()
        if df_all.empty:
            pytest.skip("Sin datos en DB de test")
        especie = df_all["especie_code"].iloc[0]
        df_filtrado = comp.get_triangulo_completo(especie_code=especie)
        assert all(df_filtrado["especie_code"] == especie)

    def test_ratio_cmp_cba_calculado(self, tmp_db):
        """ratio_cmp_cba = cmp / cba en la tabla."""
        comp = INIDEPComparator.__new__(INIDEPComparator)
        comp.db_path = tmp_db
        comp._init_schema()
        comp._migrate_schema()
        with sqlite3.connect(tmp_db) as conn:
            conn.execute("DELETE FROM inidep_evaluaciones")
            conn.execute(
                "INSERT INTO inidep_evaluaciones "
                "(especie, especie_code, zona, year, cba_recomendada_tn, numero_ito, fuente_url, notas) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                ("merluza", "merluza_test", "Sur", 2023, 100_000, "ITO/1", "http://x", ""),
            )
            conn.execute(
                "INSERT INTO cfp_cuotas "
                "(especie, especie_code, zona, year, cmp_aprobada_tn, tipo_decision) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                ("merluza", "merluza_test", "Sur", 2023, 120_000, "CMP"),
            )
            conn.commit()
        df = comp.get_triangulo_completo(especie_code="merluza_test")
        assert not df.empty
        assert df.iloc[0]["ratio_cmp_cba"] == pytest.approx(1.2)


# ── summary_report ────────────────────────────────────────────────────────────

class TestSummaryReport:
    def test_estructura_reporte(self, comp):
        report = comp.summary_report()
        assert "total_comparaciones" in report
        assert "por_nivel" in report
        assert "alertas_criticas" in report
        assert "alertas_rojas" in report
        assert "n_sub_utilizacion" in report
        assert "especies_monitoreadas" in report
        assert "años_cubiertos" in report

    def test_total_correcto(self, comp):
        """El total debe coincidir con la suma de niveles."""
        report = comp.summary_report()
        suma_niveles = sum(report["por_nivel"].values())
        assert report["total_comparaciones"] == suma_niveles

    def test_especies_monitoreadas_son_unicas(self, comp):
        report = comp.summary_report()
        especies = report["especies_monitoreadas"]
        assert len(especies) == len(set(especies))

    def test_n_sub_utilizacion_es_entero(self, comp):
        report = comp.summary_report()
        assert isinstance(report["n_sub_utilizacion"], int)
        assert report["n_sub_utilizacion"] >= 0


# ── _clasificar_alerta_captura ────────────────────────────────────────────────

class TestClasificarAlertaCaptura:
    """Verifica la función auxiliar importada de sipa_scraper."""

    def _clf(self, ratio_cba, ratio_cmp=None):
        from src.acquisition.sipa_scraper import _clasificar_alerta_captura
        return _clasificar_alerta_captura(ratio_cba, ratio_cmp)

    def test_sin_datos(self):
        assert self._clf(None) == "sin_datos"

    def test_critico(self):
        assert self._clf(1.35) == "critico"

    def test_rojo(self):
        assert self._clf(1.15) == "rojo"

    def test_amarillo(self):
        assert self._clf(1.05) == "amarillo"

    def test_sub_utilizacion(self):
        assert self._clf(0.60, ratio_cmp=0.60) == "sub_utilizacion"

    def test_verde(self):
        assert self._clf(0.95, ratio_cmp=0.90) == "verde"

    def test_limite_exacto_cba(self):
        """Captura = exactamente CBA → verde (no supera)."""
        assert self._clf(1.0, ratio_cmp=1.0) == "verde"
