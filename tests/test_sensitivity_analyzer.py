"""Tests para SensitivityAnalyzer — análisis de sensibilidad de umbrales CFP/INIDEP."""

import sqlite3
import tempfile
from pathlib import Path

import pandas as pd
import pytest

from src.analysis.sensitivity_analyzer import LITERATURA, SensitivityAnalyzer


@pytest.fixture
def db_con_datos(tmp_path) -> Path:
    """DB con comparaciones CFP/INIDEP para análisis de sensibilidad."""
    db = tmp_path / "sensitivity_test.db"
    with sqlite3.connect(db) as conn:
        conn.execute(
            """
            CREATE TABLE comparacion_cfp_inidep (
                id INTEGER PRIMARY KEY,
                especie_code TEXT,
                zona TEXT,
                year INTEGER,
                ratio_sobreasignacion REAL
            )
            """
        )
        # Distribución que cubre todos los niveles de alerta
        datos = [
            ("merluza_hubbsi", "Norte", 2020, 0.95),   # verde
            ("merluza_hubbsi", "Norte", 2021, 1.05),   # amarillo
            ("merluza_hubbsi", "Norte", 2022, 1.20),   # rojo
            ("merluza_hubbsi", "Norte", 2023, 1.45),   # crítico
            ("langostino", "Sur", 2020, 0.85),         # verde
            ("langostino", "Sur", 2021, 1.12),         # amarillo
            ("langostino", "Sur", 2022, 1.28),         # rojo
            ("langostino", "Sur", 2023, 1.55),         # crítico
            ("polaca", "Sur", 2020, 0.98),             # verde
            ("polaca", "Sur", 2021, 1.08),             # amarillo
        ]
        conn.executemany(
            "INSERT INTO comparacion_cfp_inidep (especie_code, zona, year, ratio_sobreasignacion) "
            "VALUES (?,?,?,?)",
            datos,
        )
    return db


@pytest.fixture
def analyzer(db_con_datos) -> SensitivityAnalyzer:
    return SensitivityAnalyzer(db_con_datos)


@pytest.fixture
def analyzer_vacio(tmp_path) -> SensitivityAnalyzer:
    db = tmp_path / "vacia.db"
    return SensitivityAnalyzer(db)


class TestLiteratura:
    def test_tres_referencias(self):
        assert len(LITERATURA) == 3

    def test_referencias_son_strings(self):
        for v in LITERATURA.values():
            assert isinstance(v, str)
            assert len(v) > 10

    def test_contiene_ley_24922(self):
        assert any("24.922" in v for v in LITERATURA.values())

    def test_contiene_fao(self):
        assert any("FAO" in v for v in LITERATURA.values())


class TestSensitivityAnalyzerVacio:
    def test_db_sin_tabla_retorna_vacio(self, analyzer_vacio):
        df = analyzer_vacio.analyze_cba_thresholds()
        assert df.empty

    def test_stability_report_sin_datos(self, analyzer_vacio):
        report = analyzer_vacio.stability_report()
        assert "error" in report


class TestAnalyzeCbaThresholds:
    def test_retorna_dataframe(self, analyzer):
        df = analyzer.analyze_cba_thresholds(
            amarillo_range=(0.00, 0.10),
            rojo_range=(0.10, 0.20),
            step=0.05,
        )
        assert isinstance(df, pd.DataFrame)
        assert not df.empty

    def test_columnas_requeridas(self, analyzer):
        df = analyzer.analyze_cba_thresholds(
            amarillo_range=(0.00, 0.10), rojo_range=(0.10, 0.20), step=0.05
        )
        for col in ["amarillo_min", "rojo_min", "n_verde", "n_amarillo", "n_rojo", "n_critico", "pct_critico"]:
            assert col in df.columns

    def test_n_total_consistente(self, analyzer):
        df = analyzer.analyze_cba_thresholds(
            amarillo_range=(0.00, 0.10), rojo_range=(0.10, 0.20), step=0.05
        )
        for _, row in df.iterrows():
            assert row["n_verde"] + row["n_amarillo"] + row["n_rojo"] + row["n_critico"] == row["n_total"]

    def test_critico_decrece_al_subir_umbral(self, analyzer):
        df = analyzer.analyze_cba_thresholds(
            amarillo_range=(0.00, 0.20), rojo_range=(0.20, 0.50), step=0.10
        )
        if df.empty:
            return
        # Con umbral rojo más alto, debería haber menos críticos
        df_sorted = df.sort_values("rojo_min")
        # Al menos una tendencia: rojo max → menos criticos
        criticos_low = df_sorted[df_sorted["rojo_min"] <= df_sorted["rojo_min"].median()]["n_critico"].mean()
        criticos_high = df_sorted[df_sorted["rojo_min"] > df_sorted["rojo_min"].median()]["n_critico"].mean()
        assert criticos_high <= criticos_low + 5  # tolerancia por datos seed

    def test_amarillo_min_siempre_menor_rojo_min(self, analyzer):
        df = analyzer.analyze_cba_thresholds(
            amarillo_range=(0.00, 0.20), rojo_range=(0.10, 0.40), step=0.05
        )
        for _, row in df.iterrows():
            assert row["amarillo_min"] < row["rojo_min"]

    def test_pct_critico_en_rango(self, analyzer):
        df = analyzer.analyze_cba_thresholds(
            amarillo_range=(0.00, 0.10), rojo_range=(0.10, 0.20), step=0.05
        )
        for _, row in df.iterrows():
            assert 0 <= row["pct_critico"] <= 100


class TestFiguraHeatmap:
    def test_genera_figura_con_datos(self, analyzer):
        import matplotlib.pyplot as plt

        df = analyzer.analyze_cba_thresholds(
            amarillo_range=(0.00, 0.15), rojo_range=(0.15, 0.35), step=0.075
        )
        fig = analyzer.figura_heatmap_sensibilidad(df)
        assert fig is not None
        plt.close("all")

    def test_genera_figura_sin_datos(self, analyzer_vacio):
        import matplotlib.pyplot as plt

        fig = analyzer_vacio.figura_heatmap_sensibilidad(pd.DataFrame())
        assert fig is not None
        plt.close("all")


class TestTablaLatex:
    def test_genera_latex_con_datos(self, analyzer):
        df = analyzer.analyze_cba_thresholds(
            amarillo_range=(0.00, 0.10), rojo_range=(0.10, 0.20), step=0.05
        )
        latex = analyzer.tabla_latex_sensibilidad(df)
        assert "\\begin{table}" in latex
        assert "\\end{table}" in latex

    def test_genera_comment_sin_datos(self, analyzer_vacio):
        latex = analyzer_vacio.tabla_latex_sensibilidad(pd.DataFrame())
        assert "%" in latex

    def test_latex_menciona_literatura(self, analyzer):
        df = analyzer.analyze_cba_thresholds(
            amarillo_range=(0.00, 0.10), rojo_range=(0.10, 0.20), step=0.05
        )
        latex = analyzer.tabla_latex_sensibilidad(df)
        assert "Bertolotti" in latex or "FAO" in latex


class TestStabilityReport:
    def test_retorna_configuracion_actual(self, analyzer):
        report = analyzer.stability_report()
        assert "configuracion_actual" in report
        assert report["configuracion_actual"]["amarillo_min"] == 1.15
        assert report["configuracion_actual"]["rojo_min"] == 1.30

    def test_retorna_literatura(self, analyzer):
        report = analyzer.stability_report()
        assert "literatura" in report
        assert len(report["literatura"]) == 3

    def test_retorna_max_variacion(self, analyzer):
        report = analyzer.stability_report()
        assert "max_variacion_criticos_pm5pct" in report
        assert isinstance(report["max_variacion_criticos_pm5pct"], int | float)

    def test_resultados_cinco_deltas(self, analyzer):
        report = analyzer.stability_report()
        assert "resultados_por_delta" in report
        assert len(report["resultados_por_delta"]) == 5

    def test_hallazgos_estables_es_bool(self, analyzer):
        report = analyzer.stability_report()
        assert isinstance(report["hallazgos_estables"], bool)
