"""Tests para FisheriesAudit ALG — research_exporter y linkedin_formatter."""

import json
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd

from src.analysis.linkedin_formatter import LinkedInFormatter, LinkedInPost
from src.analysis.research_exporter import (
    HallazgoPublicable,
    ResearchExporter,
    TestResult,
)


# ─────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────

def _make_triangulo_df(n_especies: int = 2, n_years: int = 3) -> pd.DataFrame:
    import numpy as np

    rows = []
    species = [("merluza_comun", "Merluza común"), ("centolla", "Centolla")][:n_especies]
    for code, name in species:
        for yr in range(2022, 2022 + n_years):
            cba = 200_000 + yr * 100
            cmp = cba * 1.15
            cap = cba * 0.95
            rows.append(
                {
                    "especie": name,
                    "especie_code": code,
                    "zona": "Nacional",
                    "year": yr,
                    "cba_recomendada_tn": cba,
                    "cmp_aprobada_tn": cmp,
                    "captura_real_tn": cap,
                    "ratio_cmp_cba": round(cmp / cba, 3),
                    "ratio_captura_cba": round(cap / cba, 3),
                }
            )
    return pd.DataFrame(rows)


def _make_alertas_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"especie": "Merluza común", "year": 2022, "nivel_alerta": "critico"},
            {"especie": "Merluza común", "year": 2023, "nivel_alerta": "rojo"},
            {"especie": "Centolla", "year": 2022, "nivel_alerta": "amarillo"},
            {"especie": "Centolla", "year": 2023, "nivel_alerta": "verde"},
        ]
    )


def _make_comparator_mock(triangulo_df=None, alertas_df=None):
    comp = MagicMock()
    comp.get_triangulo_completo.return_value = triangulo_df if triangulo_df is not None else _make_triangulo_df()
    comp.get_alertas_activas.return_value = alertas_df if alertas_df is not None else _make_alertas_df()
    comp.get_inidep_data.return_value = pd.DataFrame(columns=["especie", "year", "cba_recomendada_tn"])
    comp.get_cfp_data.return_value = pd.DataFrame(columns=["especie", "year", "cmp_aprobada_tn"])
    comp.get_capturas_data.return_value = pd.DataFrame(columns=["especie", "year", "captura_tn"])
    comp.summary_report.return_value = {
        "total_comparaciones": 6,
        "n_sub_utilizacion": 1,
        "especies_monitoreadas": ["Merluza común", "Centolla"],
        "años_cubiertos": [2022, 2023, 2024],
        "por_nivel": {"critico": 1, "rojo": 2, "verde": 3},
    }
    return comp


# ─────────────────────────────────────────────────────────────────────
# TestResult
# ─────────────────────────────────────────────────────────────────────

class TestTestResult(unittest.TestCase):
    def test_significativo_true(self):
        t = TestResult("Wilcoxon", 2.5, 0.03, "sig", 10)
        self.assertTrue(t.significativo)

    def test_significativo_false(self):
        t = TestResult("Wilcoxon", 1.2, 0.2, "no sig", 10)
        self.assertFalse(t.significativo)

    def test_to_dict_keys(self):
        t = TestResult("Kendall", 0.5, 0.04, "tendencia", 8)
        d = t.to_dict()
        self.assertIn("test", d)
        self.assertIn("p_valor", d)
        self.assertIn("significativo", d)
        self.assertIn("n", d)

    def test_alpha_personalizable(self):
        t = TestResult("Test", 1.0, 0.06, "borderline", 5, alpha=0.1)
        self.assertTrue(t.significativo)


# ─────────────────────────────────────────────────────────────────────
# HallazgoPublicable
# ─────────────────────────────────────────────────────────────────────

class TestHallazgoPublicable(unittest.TestCase):
    def _make(self, nivel="alto"):
        return HallazgoPublicable(
            titulo="Sobreasignación sistémica",
            descripcion="El CFP aprueba cuotas sobre el 100% CBA.",
            datos_clave={"Mediana ratio": "1.15", "N": "10"},
            nivel_evidencia=nivel,
            fuentes=["INIDEP", "CFP"],
        )

    def test_resumen_ejecutivo_contiene_titulo(self):
        h = self._make()
        r = h.resumen_ejecutivo()
        self.assertIn("Sobreasignación sistémica", r)

    def test_resumen_ejecutivo_contiene_datos(self):
        h = self._make()
        r = h.resumen_ejecutivo()
        self.assertIn("Mediana ratio", r)

    def test_con_tests(self):
        h = self._make()
        h.tests = [TestResult("Wilcoxon", 3.5, 0.02, "sig", 10)]
        r = h.resumen_ejecutivo()
        self.assertIn("p<0.05", r)


# ─────────────────────────────────────────────────────────────────────
# ResearchExporter — tests estadísticos
# ─────────────────────────────────────────────────────────────────────

class TestResearchExporterStats(unittest.TestCase):
    def setUp(self):
        self.comp = _make_comparator_mock()
        self.exp = ResearchExporter(self.comp, output_dir="/tmp/test_fisheriesaudit_alg")

    def test_test_sobreasignacion_retorna_testresult(self):
        r = self.exp.test_sobreasignacion()
        self.assertIsInstance(r, TestResult)
        self.assertIn("Wilcoxon", r.nombre)

    def test_test_sobreasignacion_con_datos_sobre(self):
        """Con ratio > 1 en todos los datos, debe detectar sobreasignación."""
        r = self.exp.test_sobreasignacion()
        df = _make_triangulo_df()
        median = df["ratio_cmp_cba"].median()
        self.assertGreater(median, 1.0)

    def test_test_tendencia_temporal_retorna_testresult(self):
        r = self.exp.test_tendencia_temporal()
        self.assertIsInstance(r, TestResult)

    def test_test_tendencia_por_especie(self):
        r = self.exp.test_tendencia_temporal("merluza_comun")
        self.assertIn("merluza_comun", r.nombre)

    def test_test_kruskal(self):
        r = self.exp.test_diferencia_entre_especies()
        self.assertIsInstance(r, TestResult)
        self.assertIn("Kruskal", r.nombre)

    def test_test_spearman(self):
        r = self.exp.test_correlacion_captura_cba()
        self.assertIsInstance(r, TestResult)
        self.assertIn("Spearman", r.nombre)

    def test_ejecutar_todos_retorna_lista(self):
        tests = self.exp.ejecutar_todos_los_tests()
        self.assertIsInstance(tests, list)
        self.assertGreaterEqual(len(tests), 4)

    def test_todos_son_testresult(self):
        for t in self.exp.ejecutar_todos_los_tests():
            self.assertIsInstance(t, TestResult)

    def test_insuficientes_datos_no_falla(self):
        comp_empty = _make_comparator_mock(triangulo_df=pd.DataFrame())
        exp_empty = ResearchExporter(comp_empty, "/tmp/test_empty")
        r = exp_empty.test_sobreasignacion()
        self.assertIsInstance(r, TestResult)
        self.assertEqual(r.p_value, 1.0)


# ─────────────────────────────────────────────────────────────────────
# ResearchExporter — hallazgos
# ─────────────────────────────────────────────────────────────────────

class TestResearchExporterHallazgos(unittest.TestCase):
    def setUp(self):
        self.comp = _make_comparator_mock()
        self.exp = ResearchExporter(self.comp, "/tmp/test_fisheriesaudit_hallazgos")

    def test_generar_hallazgos_retorna_lista(self):
        h = self.exp.generar_hallazgos()
        self.assertIsInstance(h, list)

    def test_hallazgos_tienen_campos_requeridos(self):
        for h in self.exp.generar_hallazgos():
            self.assertIsInstance(h, HallazgoPublicable)
            self.assertTrue(h.titulo)
            self.assertTrue(h.descripcion)
            self.assertIn(h.nivel_evidencia, ["alto", "medio", "exploratorio"])

    def test_hallazgo_sobreasignacion_presente(self):
        h = self.exp.generar_hallazgos()
        titulos = [hh.titulo for hh in h]
        self.assertTrue(any("sobre" in t.lower() or "asignación" in t.lower() for t in titulos))

    def test_hallazgo_sub_utilizacion_presente(self):
        h = self.exp.generar_hallazgos()
        titulos = [hh.titulo for hh in h]
        self.assertTrue(any("sub" in t.lower() or "utiliz" in t.lower() for t in titulos))


# ─────────────────────────────────────────────────────────────────────
# ResearchExporter — exportaciones
# ─────────────────────────────────────────────────────────────────────

class TestResearchExporterExport(unittest.TestCase):
    def setUp(self):
        self.comp = _make_comparator_mock()
        self.out = Path("/tmp/test_fisheriesaudit_export")
        self.exp = ResearchExporter(self.comp, self.out)

    def test_exportar_csv_crea_archivo(self):
        path = self.exp.exportar_csv()
        self.assertTrue(path.exists())
        df = pd.read_csv(path)
        self.assertGreater(len(df), 0)
        self.assertIn("serie", df.columns)

    def test_exportar_csv_tiene_columnas_fair(self):
        path = self.exp.exportar_csv()
        df = pd.read_csv(path)
        for col in ["fuente_cba", "fuente_cmp", "fuente_captura", "fecha_exportacion"]:
            self.assertIn(col, df.columns)

    def test_exportar_excel_crea_archivo(self):
        path = self.exp.exportar_excel()
        self.assertTrue(path.exists())
        self.assertEqual(path.suffix, ".xlsx")

    def test_exportar_latex_retorna_string(self):
        latex = self.exp.exportar_tabla_latex()
        self.assertIsInstance(latex, str)
        self.assertIn(r"\begin{table}", latex)
        self.assertIn(r"\end{table}", latex)
        self.assertIn("FisheriesAudit ALG", latex)

    def test_exportar_latex_crea_archivo(self):
        self.exp.exportar_tabla_latex()
        tex_path = self.out / "tablas_latex" / "tabla_triangulo.tex"
        self.assertTrue(tex_path.exists())


# ─────────────────────────────────────────────────────────────────────
# ResearchExporter — figuras
# ─────────────────────────────────────────────────────────────────────

class TestResearchExporterFiguras(unittest.TestCase):
    def setUp(self):
        self.comp = _make_comparator_mock()
        self.exp = ResearchExporter(self.comp, "/tmp/test_fisheriesaudit_figs")

    def test_figura_triangulo_retorna_figure(self):
        import matplotlib.pyplot as plt

        self.comp.get_triangulo_completo.return_value = _make_triangulo_df()
        fig = self.exp.figura_triangulo_por_especie("merluza_comun", save=False)
        self.assertIsInstance(fig, plt.Figure)
        plt.close(fig)

    def test_figura_triangulo_sin_datos_falla(self):
        self.comp.get_triangulo_completo.return_value = pd.DataFrame()
        with self.assertRaises(ValueError):
            self.exp.figura_triangulo_por_especie("especie_inexistente", save=False)

    def test_figura_scatter_retorna_figure(self):
        import matplotlib.pyplot as plt

        fig = self.exp.figura_comparacion_todas_especies(save=False)
        self.assertIsInstance(fig, plt.Figure)
        plt.close(fig)

    def test_figura_heatmap_retorna_figure(self):
        import matplotlib.pyplot as plt

        fig = self.exp.figura_alertas_heatmap(save=False)
        self.assertIsInstance(fig, plt.Figure)
        plt.close(fig)

    def test_figura_heatmap_sin_datos_falla(self):
        self.comp.get_alertas_activas.return_value = pd.DataFrame()
        with self.assertRaises(ValueError):
            self.exp.figura_alertas_heatmap(save=False)


# ─────────────────────────────────────────────────────────────────────
# LinkedInPost
# ─────────────────────────────────────────────────────────────────────

class TestLinkedInPost(unittest.TestCase):
    def _make_post(self, perfil="personal"):
        return LinkedInPost(
            numero_entrega=1,
            titulo="El Triángulo de Auditoría",
            hook="Hook del post.",
            contexto="Contexto del análisis.",
            datos_principales=["Dato 1", "Dato 2"],
            reflexion="Reflexión final.",
            cta="Llamada a la acción.",
            hashtags=["#FisheriesAuditALG", "#GobernanzaPesquera"],
            perfil=perfil,
        )

    def test_render_contiene_titulo(self):
        post = self._make_post()
        txt = post.render()
        self.assertIn("El Triángulo de Auditoría", txt)

    def test_render_contiene_serie(self):
        post = self._make_post()
        txt = post.render()
        self.assertIn("FisheriesAudit ALG 2026", txt)

    def test_render_contiene_hashtags(self):
        post = self._make_post()
        txt = post.render()
        self.assertIn("#FisheriesAuditALG", txt)

    def test_render_contiene_hook(self):
        post = self._make_post()
        self.assertIn("Hook del post.", post.render())

    def test_render_corto_es_mas_corto(self):
        post = self._make_post()
        self.assertLessEqual(len(post.render_corto()), 700)

    def test_render_corto_contiene_hook(self):
        post = self._make_post()
        self.assertIn("Hook del post.", post.render_corto())

    def test_numero_entrega_en_render(self):
        post = self._make_post()
        self.assertIn("#01", post.render())


# ─────────────────────────────────────────────────────────────────────
# LinkedInFormatter
# ─────────────────────────────────────────────────────────────────────

class TestLinkedInFormatter(unittest.TestCase):
    def setUp(self):
        self.hallazgos = [
            HallazgoPublicable(
                titulo="Sobreasignación sistémica de cuotas pesqueras",
                descripcion="El CFP supera la CBA en el 80% de los casos.",
                datos_clave={"% casos sobre CBA": "80%", "Mediana ratio CMP/CBA": "1.15", "N comparaciones": 10},
                nivel_evidencia="alto",
                tests=[TestResult("Wilcoxon", 3.2, 0.02, "sig", 10)],
                fuentes=["INIDEP", "CFP"],
            ),
            HallazgoPublicable(
                titulo="Sub-utilización de cuotas aprobadas",
                descripcion="En 3 casos la captura fue <70% CMP.",
                datos_clave={"Casos sub-utilización (<70% CMP)": 3, "% del total analizado": "30%"},
                nivel_evidencia="medio",
                fuentes=["SAGPyA"],
            ),
        ]
        self.fmt = LinkedInFormatter(self.hallazgos, numero_entrega_inicial=1)

    def test_generar_todos_retorna_dict(self):
        r = self.fmt.generar_todos()
        self.assertIn("personal", r)
        self.assertIn("pesqueros_ia", r)

    def test_personal_tiene_posts(self):
        r = self.fmt.generar_todos()
        self.assertGreater(len(r["personal"]), 0)

    def test_pesqueros_ia_tiene_posts(self):
        r = self.fmt.generar_todos()
        self.assertGreater(len(r["pesqueros_ia"]), 0)

    def test_posts_son_linked_in_post(self):
        r = self.fmt.generar_todos()
        for post in r["personal"] + r["pesqueros_ia"]:
            self.assertIsInstance(post, LinkedInPost)

    def test_post_triangulo_usa_datos_hallazgo(self):
        post = self.fmt.post_triangulo_auditoria(
            {"% casos sobre CBA": "80%", "Mediana ratio CMP/CBA": "1.15", "N comparaciones": 10}
        )
        txt = post.render()
        self.assertIn("80%", txt)

    def test_post_sobreasignacion_con_test(self):
        t = TestResult("Wilcoxon", 3.2, 0.02, "sig", 10)
        post = self.fmt.post_sobreasignacion(
            {"% casos sobre CBA": "80%", "Mediana ratio CMP/CBA": "1.15"}, test_result=t
        )
        txt = post.render()
        self.assertIn("80%", txt)

    def test_post_sub_utilizacion_contiene_datos(self):
        post = self.fmt.post_sub_utilizacion(
            {"Casos sub-utilización (<70% CMP)": 3, "% del total analizado": "30%"}
        )
        txt = post.render()
        self.assertIn("3", txt)

    def test_post_metodologia_ia_perfil_pesqueros(self):
        post = self.fmt.post_metodologia_ia("pesqueros_ia")
        self.assertEqual(post.perfil, "pesqueros_ia")
        self.assertIn("#FisheriesAI", post.render())

    def test_hashtags_diferencian_perfiles(self):
        post_p = self.fmt.post_metodologia_ia("personal")
        post_ia = self.fmt.post_metodologia_ia("pesqueros_ia")
        self.assertIn("#DataScience", post_p.render())
        self.assertIn("#FisheriesAI", post_ia.render())

    def test_numeros_entrega_consecutivos(self):
        r = self.fmt.generar_todos()
        numeros = [p.numero_entrega for p in r["personal"]]
        self.assertEqual(numeros[0], 1)

    def test_render_corto_longitud_maxima(self):
        r = self.fmt.generar_todos()
        for post in r["personal"]:
            self.assertLessEqual(len(post.render_corto(700)), 700)


# ─────────────────────────────────────────────────────────────────────
# PatternExporter
# ─────────────────────────────────────────────────────────────────────

class TestPatternExporter(unittest.TestCase):
    def setUp(self):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        self.det = MagicMock()
        self.det.resolution_timeline.return_value = pd.DataFrame()
        self.det.top_beneficiaries.return_value = pd.DataFrame()
        self.det.hhi_concentration.return_value = {"hhi": 0, "interpretation": "sin datos", "empresas_analizadas": 0}
        self.det.risk_evolution.return_value = pd.DataFrame()
        self.det.reversals_detection.return_value = []
        self.det.high_risk_resolutions.return_value = pd.DataFrame()
        self.det.voting_patterns.return_value = {}
        self.out = Path("/tmp/test_pattern_exporter")
        self.pexp = PatternExporter(self.det, self.out)
        self.plt = plt

    def tearDown(self):
        self.plt.close("all")

    def test_figura_timeline_vacia_no_falla(self):
        fig = self.pexp.figura_timeline_resoluciones(save=False)
        self.assertIsInstance(fig, self.plt.Figure)

    def test_figura_hhi_vacia_no_falla(self):
        fig = self.pexp.figura_hhi(save=False)
        self.assertIsInstance(fig, self.plt.Figure)

    def test_figura_riesgo_vacia_no_falla(self):
        fig = self.pexp.figura_riesgo_temporal(save=False)
        self.assertIsInstance(fig, self.plt.Figure)

    def test_figura_reversiones_vacias_no_falla(self):
        fig = self.pexp.figura_reversiones(save=False)
        self.assertIsInstance(fig, self.plt.Figure)

    def test_figura_timeline_con_datos(self):
        self.det.resolution_timeline.return_value = pd.DataFrame({
            "year": [2020, 2020, 2021, 2021],
            "tipo": ["cuota_captura", "veda", "cuota_captura", "veda"],
            "cantidad": [5, 2, 7, 1],
            "riesgo_promedio": [50.0, 60.0, 55.0, 70.0],
        })
        fig = self.pexp.figura_timeline_resoluciones(save=False)
        self.assertIsInstance(fig, self.plt.Figure)

    def test_figura_hhi_con_datos(self):
        self.det.top_beneficiaries.return_value = pd.DataFrame({
            "nombre": ["Empresa A", "Empresa B", "Empresa C"],
            "menciones": [50, 30, 20],
            "actas_distintas": [10, 8, 5],
            "primer_anio": [2010, 2015, 2018],
            "ultimo_anio": [2024, 2024, 2024],
        })
        self.det.hhi_concentration.return_value = {
            "hhi": 3800.0,
            "interpretation": "Alta concentración",
            "empresas_analizadas": 3,
        }
        fig = self.pexp.figura_hhi(save=False)
        self.assertIsInstance(fig, self.plt.Figure)

    def test_figura_reversiones_con_datos(self):
        self.det.reversals_detection.return_value = [
            {"especie": "Merluza", "anio_veda": 2015, "anio_cuota_posterior": 2016, "alerta": "Revisar"}
        ]
        fig = self.pexp.figura_reversiones(save=False)
        self.assertIsInstance(fig, self.plt.Figure)

    def test_test_concentracion_sin_datos(self):
        t = self.pexp.test_concentracion_hhi()
        self.assertIsInstance(t, TestResult)
        self.assertEqual(t.p_value, 1.0)

    def test_test_concentracion_con_datos(self):
        self.det.top_beneficiaries.return_value = pd.DataFrame({
            "nombre": [f"Empresa {i}" for i in range(5)],
            "menciones": [100, 10, 5, 3, 2],
            "actas_distintas": [20, 5, 3, 2, 1],
            "primer_anio": [2000]*5,
            "ultimo_anio": [2024]*5,
        })
        self.det.hhi_concentration.return_value = {"hhi": 8200.0, "empresas_analizadas": 5}
        t = self.pexp.test_concentracion_hhi()
        self.assertIsInstance(t, TestResult)
        self.assertIn("Chi", t.nombre)

    def test_test_tendencia_riesgo_sin_datos(self):
        t = self.pexp.test_tendencia_riesgo()
        self.assertIsInstance(t, TestResult)
        self.assertEqual(t.p_value, 1.0)

    def test_test_tendencia_riesgo_con_datos(self):
        self.det.risk_evolution.return_value = pd.DataFrame({
            "year": [2018, 2019, 2020, 2021, 2022],
            "riesgo_promedio": [40.0, 45.0, 55.0, 62.0, 70.0],
            "riesgo_maximo": [70.0, 75.0, 80.0, 85.0, 90.0],
            "resoluciones": [10, 12, 11, 13, 14],
        })
        t = self.pexp.test_tendencia_riesgo()
        self.assertIsInstance(t, TestResult)
        self.assertIn("Kendall", t.nombre)

    def test_exportar_patrones_csv_crea_archivo(self):
        path = self.pexp.exportar_patrones_csv()
        self.assertIsInstance(path, Path)
        self.assertTrue(path.parent.exists())

    def test_exportar_latex_beneficiarios_sin_datos(self):
        latex = self.pexp.exportar_latex_beneficiarios()
        self.assertIsInstance(latex, str)
        self.assertIn(r"\begin{table}", latex)

    def test_exportar_latex_beneficiarios_con_datos(self):
        self.det.top_beneficiaries.return_value = pd.DataFrame({
            "nombre": ["Empresa A", "Empresa B"],
            "menciones": [50, 30],
            "actas_distintas": [10, 8],
            "primer_anio": [2010, 2015],
            "ultimo_anio": [2024, 2024],
        })
        latex = self.pexp.exportar_latex_beneficiarios(top_n=2)
        self.assertIn("FisheriesAudit ALG", latex)
        self.assertIn("Empresa A", latex)


# necesario para importar PatternExporter en los tests
from src.analysis.research_exporter import PatternExporter
