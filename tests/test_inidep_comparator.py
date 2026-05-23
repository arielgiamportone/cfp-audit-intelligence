"""
Tests del Comparador CFP vs. INIDEP.

Verifica la lógica de alertas, persistencia en SQLite y cálculo de ratios.
"""
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
        import sqlite3
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
        # El registro insertado tiene year=2025, zona="Sur 41°S"
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
        import sqlite3
        # Insertamos directamente para evitar depender del seed
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

    def test_alerta_verde(self, tmp_db):
        """CMP = CBA → verde."""
        comp = INIDEPComparator.__new__(INIDEPComparator)
        comp.db_path = tmp_db
        comp._init_schema()
        # Vaciar seed para test limpio
        import sqlite3
        with sqlite3.connect(tmp_db) as conn:
            conn.execute("DELETE FROM inidep_evaluaciones")
            conn.commit()
        self._setup_pair(comp, cba=100_000, cmp=100_000)
        alertas = comp.compute_comparisons()
        test_alertas = [a for a in alertas if a.especie == "test especie"]
        assert len(test_alertas) == 1
        assert test_alertas[0].nivel == ALERTA_VERDE
        assert test_alertas[0].ratio == pytest.approx(1.0)

    def test_alerta_verde_bajo_cba(self, tmp_db):
        """CMP < CBA → verde."""
        comp = INIDEPComparator.__new__(INIDEPComparator)
        comp.db_path = tmp_db
        comp._init_schema()
        import sqlite3
        with sqlite3.connect(tmp_db) as conn:
            conn.execute("DELETE FROM inidep_evaluaciones")
            conn.commit()
        self._setup_pair(comp, cba=100_000, cmp=90_000)
        alertas = comp.compute_comparisons()
        test_alertas = [a for a in alertas if a.especie == "test especie"]
        assert test_alertas[0].nivel == ALERTA_VERDE

    def test_alerta_amarilla(self, tmp_db):
        """CMP = 110% CBA → amarillo."""
        comp = INIDEPComparator.__new__(INIDEPComparator)
        comp.db_path = tmp_db
        comp._init_schema()
        import sqlite3
        with sqlite3.connect(tmp_db) as conn:
            conn.execute("DELETE FROM inidep_evaluaciones")
            conn.commit()
        self._setup_pair(comp, cba=100_000, cmp=110_000)
        alertas = comp.compute_comparisons()
        test_alertas = [a for a in alertas if a.especie == "test especie"]
        assert test_alertas[0].nivel == ALERTA_AMARILLA

    def test_alerta_roja(self, tmp_db):
        """CMP = 120% CBA → rojo."""
        comp = INIDEPComparator.__new__(INIDEPComparator)
        comp.db_path = tmp_db
        comp._init_schema()
        import sqlite3
        with sqlite3.connect(tmp_db) as conn:
            conn.execute("DELETE FROM inidep_evaluaciones")
            conn.commit()
        self._setup_pair(comp, cba=100_000, cmp=120_000)
        alertas = comp.compute_comparisons()
        test_alertas = [a for a in alertas if a.especie == "test especie"]
        assert test_alertas[0].nivel == ALERTA_ROJA

    def test_alerta_critica(self, tmp_db):
        """CMP = 150% CBA → crítico."""
        comp = INIDEPComparator.__new__(INIDEPComparator)
        comp.db_path = tmp_db
        comp._init_schema()
        import sqlite3
        with sqlite3.connect(tmp_db) as conn:
            conn.execute("DELETE FROM inidep_evaluaciones")
            conn.commit()
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
        comp = INIDEPComparator.__new__(INIDEPComparator)
        comp.db_path = tmp_db
        comp._init_schema()
        import sqlite3
        with sqlite3.connect(tmp_db) as conn:
            conn.execute("DELETE FROM inidep_evaluaciones")
            conn.commit()
        self._setup_pair(comp, cba=100_000, cmp=130_000)
        alertas = comp.compute_comparisons()
        test_alertas = [a for a in alertas if a.especie == "test especie"]
        assert test_alertas[0].diferencia_tn == pytest.approx(30_000.0)

    def test_persiste_en_tabla(self, tmp_db):
        """Los resultados se persisten en comparacion_cfp_inidep."""
        import sqlite3
        comp = INIDEPComparator.__new__(INIDEPComparator)
        comp.db_path = tmp_db
        comp._init_schema()
        with sqlite3.connect(tmp_db) as conn:
            conn.execute("DELETE FROM inidep_evaluaciones")
            conn.commit()
        self._setup_pair(comp, cba=100_000, cmp=110_000)
        comp.compute_comparisons()
        with sqlite3.connect(tmp_db) as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM comparacion_cfp_inidep"
            ).fetchone()[0]
        assert count > 0


# ── summary_report ────────────────────────────────────────────────────────────

class TestSummaryReport:
    def test_estructura_reporte(self, comp):
        report = comp.summary_report()
        assert "total_comparaciones" in report
        assert "por_nivel" in report
        assert "alertas_criticas" in report
        assert "alertas_rojas" in report
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
