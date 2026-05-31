"""
FisheriesAudit ALG — Motor de exportación científica.

Genera outputs publication-ready a partir del Triángulo de Auditoría
CBA (INIDEP) → CMP (CFP) → Captura real (SAGPyA/SIPA).

Salidas soportadas:
  - Figuras matplotlib 300 dpi (PNG + SVG)
  - Tablas LaTeX
  - CSV/Excel con metadatos FAIR
  - Tests estadísticos formales (scipy.stats)
  - Resúmenes de hallazgos estructurados
"""

from __future__ import annotations

import io
import textwrap
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import matplotlib
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd
from loguru import logger
from scipy import stats

matplotlib.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "font.size": 10,
        "axes.titlesize": 12,
        "axes.labelsize": 10,
        "xtick.labelsize": 9,
        "ytick.labelsize": 9,
        "legend.fontsize": 9,
        "figure.dpi": 150,
        "savefig.dpi": 300,
        "savefig.bbox": "tight",
        "axes.spines.top": False,
        "axes.spines.right": False,
    }
)

SERIES_NAME = "FisheriesAudit ALG"
SERIES_BRAND = "© Ariel L. Giamportone | FisheriesAudit ALG 2026"
COLOR_CBA = "#2196F3"
COLOR_CMP = "#FF5722"
COLOR_CAP = "#4CAF50"
COLOR_CRITICO = "#B71C1C"
COLOR_ROJO = "#E53935"
COLOR_AMARILLO = "#FFC107"
COLOR_VERDE = "#43A047"


@dataclass
class TestResult:
    """Resultado de un test estadístico formal."""

    nombre: str
    estadistico: float
    p_value: float
    interpretacion: str
    n: int
    alpha: float = 0.05

    @property
    def significativo(self) -> bool:
        return self.p_value < self.alpha

    def to_dict(self) -> dict:
        return {
            "test": self.nombre,
            "estadistico": round(self.estadistico, 4),
            "p_valor": round(self.p_value, 4),
            "n": self.n,
            "significativo": self.significativo,
            "interpretacion": self.interpretacion,
        }


@dataclass
class HallazgoPublicable:
    """Hallazgo estructurado listo para publicación."""

    titulo: str
    descripcion: str
    datos_clave: dict[str, Any]
    nivel_evidencia: str  # "alto" | "medio" | "exploratorio"
    especie: str | None = None
    years: list[int] = field(default_factory=list)
    tests: list[TestResult] = field(default_factory=list)
    fuentes: list[str] = field(default_factory=list)

    def resumen_ejecutivo(self) -> str:
        lines = [f"**{self.titulo}**", self.descripcion, ""]
        for k, v in self.datos_clave.items():
            lines.append(f"- {k}: {v}")
        if self.tests:
            lines.append("")
            for t in self.tests:
                sig = "p<0.05 ✓" if t.significativo else f"p={t.p_value:.3f}"
                lines.append(f"- {t.nombre}: {sig}")
        return "\n".join(lines)


class ResearchExporter:
    """
    Genera outputs científicos a partir del INIDEPComparator y PatternDetector.

    Uso:
        exp = ResearchExporter(comparator, output_dir="outputs/FisheriesAudit_ALG")
        fig = exp.figura_triangulo_por_especie("merluza_comun")
        exp.exportar_todo()
    """

    def __init__(
        self,
        comparator,
        output_dir: str | Path = "outputs/FisheriesAudit_ALG",
    ) -> None:
        self.comp = comparator
        self.out = Path(output_dir)
        self.out.mkdir(parents=True, exist_ok=True)
        (self.out / "figuras").mkdir(exist_ok=True)
        (self.out / "datos").mkdir(exist_ok=True)
        (self.out / "tablas_latex").mkdir(exist_ok=True)

    # ------------------------------------------------------------------
    # Figuras
    # ------------------------------------------------------------------

    def figura_triangulo_por_especie(
        self, especie_code: str, save: bool = True
    ) -> plt.Figure:
        """Gráfico de barras agrupadas CBA / CMP / Captura por año."""
        df = self.comp.get_triangulo_completo(especie_code)
        if df.empty:
            raise ValueError(f"Sin datos para especie_code={especie_code!r}")

        especie_label = df["especie"].iloc[0]
        years = sorted(df["year"].unique())
        x = np.arange(len(years))
        w = 0.25

        fig, ax = plt.subplots(figsize=(10, 5))

        def _vals(col: str) -> list[float]:
            return [
                df[df["year"] == y][col].mean() if col in df.columns else np.nan
                for y in years
            ]

        cba = _vals("cba_recomendada_tn")
        cmp_ = _vals("cmp_aprobada_tn")
        cap = _vals("captura_real_tn")

        ax.bar(x - w, cba, w, label="CBA INIDEP (recomendada)", color=COLOR_CBA, alpha=0.85)
        ax.bar(x, cmp_, w, label="CMP CFP (aprobada)", color=COLOR_CMP, alpha=0.85)
        ax.bar(x + w, cap, w, label="Captura real SAGPyA", color=COLOR_CAP, alpha=0.85)

        ax.set_xticks(x)
        ax.set_xticklabels([str(y) for y in years])
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v/1000:.0f}k"))
        ax.set_xlabel("Año")
        ax.set_ylabel("Toneladas (miles)")
        ax.set_title(
            f"Triángulo de Auditoría — {especie_label}\n"
            f"CBA (INIDEP) · CMP (CFP) · Captura real (SAGPyA)"
        )
        ax.legend(loc="upper right")
        fig.text(0.99, 0.01, SERIES_BRAND, ha="right", va="bottom", fontsize=7, color="gray")
        fig.tight_layout()

        if save:
            stem = f"triangulo_{especie_code}"
            fig.savefig(self.out / "figuras" / f"{stem}.png")
            fig.savefig(self.out / "figuras" / f"{stem}.svg")
            logger.info(f"Figura guardada: {stem}.png/.svg")

        return fig

    def figura_comparacion_todas_especies(self, save: bool = True) -> plt.Figure:
        """Scatter ratio CMP/CBA vs ratio Captura/CBA por especie y año."""
        df = self.comp.get_triangulo_completo()
        if df.empty:
            raise ValueError("Sin datos de triángulo completo.")

        fig, ax = plt.subplots(figsize=(8, 6))

        especies = df["especie"].unique()
        cmap = matplotlib.colormaps.get_cmap("tab10").resampled(len(especies))

        for i, esp in enumerate(sorted(especies)):
            sub = df[df["especie"] == esp].dropna(subset=["ratio_cmp_cba", "ratio_captura_cba"])
            if sub.empty:
                continue
            ax.scatter(
                sub["ratio_cmp_cba"],
                sub["ratio_captura_cba"],
                label=esp,
                color=cmap(i),
                s=60,
                alpha=0.8,
                zorder=3,
            )
            for _, row in sub.iterrows():
                ax.annotate(
                    str(int(row["year"])),
                    (row["ratio_cmp_cba"], row["ratio_captura_cba"]),
                    fontsize=7,
                    color="gray",
                    xytext=(3, 3),
                    textcoords="offset points",
                )

        ax.axhline(1.0, color="gray", lw=0.8, ls="--", label="CBA = 100%")
        ax.axvline(1.0, color="gray", lw=0.8, ls=":")

        ax.fill_between([1.0, ax.get_xlim()[1] if ax.get_xlim()[1] > 1 else 2], 1.0, 2.0,
                        alpha=0.05, color=COLOR_CRITICO, label="Zona crítica")

        ax.set_xlabel("Ratio CMP/CBA (cuota CFP / recomendación INIDEP)")
        ax.set_ylabel("Ratio Captura/CBA (captura real / recomendación INIDEP)")
        ax.set_title(
            "Diagnóstico de gobernanza pesquera — Todas las especies\n"
            "Cuadrante superior derecho = sobreasignación + sobrepesca"
        )
        ax.legend(loc="upper left", fontsize=8)
        fig.text(0.99, 0.01, SERIES_BRAND, ha="right", va="bottom", fontsize=7, color="gray")
        fig.tight_layout()

        if save:
            fig.savefig(self.out / "figuras" / "scatter_todas_especies.png")
            fig.savefig(self.out / "figuras" / "scatter_todas_especies.svg")

        return fig

    def figura_alertas_heatmap(self, save: bool = True) -> plt.Figure:
        """Heatmap especie × año con nivel de alerta."""
        df = self.comp.get_alertas_activas(nivel_minimo="verde")
        if df.empty:
            raise ValueError("Sin datos de alertas.")

        nivel_num = {"verde": 0, "amarillo": 1, "rojo": 2, "critico": 3, "sin_datos": -1}
        df["nivel_num"] = df["nivel_alerta"].map(nivel_num).fillna(-1)

        pivot = df.pivot_table(
            index="especie", columns="year", values="nivel_num", aggfunc="max"
        )

        fig, ax = plt.subplots(figsize=(max(8, len(pivot.columns) * 0.8), max(4, len(pivot) * 0.7)))

        cmap_custom = matplotlib.colors.ListedColormap(
            ["#BDBDBD", COLOR_VERDE, COLOR_AMARILLO, COLOR_ROJO, COLOR_CRITICO]
        )
        bounds = [-1.5, -0.5, 0.5, 1.5, 2.5, 3.5]
        norm = matplotlib.colors.BoundaryNorm(bounds, cmap_custom.N)

        im = ax.imshow(pivot.values, cmap=cmap_custom, norm=norm, aspect="auto")

        ax.set_xticks(range(len(pivot.columns)))
        ax.set_xticklabels([str(c) for c in pivot.columns], rotation=45, ha="right")
        ax.set_yticks(range(len(pivot.index)))
        ax.set_yticklabels(pivot.index)
        ax.set_title("Nivel de alerta por especie y año\n(gris=sin datos, verde, amarillo, rojo, crítico)")

        cbar = plt.colorbar(im, ax=ax, ticks=[-1, 0, 1, 2, 3])
        cbar.set_ticklabels(["sin datos", "verde", "amarillo", "rojo", "crítico"])
        fig.text(0.99, 0.01, SERIES_BRAND, ha="right", va="bottom", fontsize=7, color="gray")
        fig.tight_layout()

        if save:
            fig.savefig(self.out / "figuras" / "heatmap_alertas.png")
            fig.savefig(self.out / "figuras" / "heatmap_alertas.svg")

        return fig

    # ------------------------------------------------------------------
    # Tests estadísticos
    # ------------------------------------------------------------------

    def test_sobreasignacion(self) -> TestResult:
        """
        Wilcoxon signed-rank: H0: ratio CMP/CBA = 1 (CFP respeta recomendación INIDEP).
        Un p<0.05 indica que el CFP sistemáticamente se aparta de la recomendación.
        """
        raw = self.comp.get_triangulo_completo()
        df = raw.dropna(subset=["ratio_cmp_cba"]) if "ratio_cmp_cba" in raw.columns else raw.iloc[:0]
        if len(df) < 3:
            return TestResult(
                "Wilcoxon CMP/CBA",
                np.nan, 1.0, "Datos insuficientes (n<3)", len(df)
            )
        stat, p = stats.wilcoxon(df["ratio_cmp_cba"] - 1.0, alternative="two-sided")
        direccion = "sobreasignación" if df["ratio_cmp_cba"].median() > 1 else "subasignación"
        interp = (
            f"CFP aprueba cuotas sistémicamente superiores a CBA INIDEP ({direccion}), "
            f"mediana ratio={df['ratio_cmp_cba'].median():.2f}"
            if p < 0.05
            else f"No hay evidencia de desvío sistemático (mediana={df['ratio_cmp_cba'].median():.2f})"
        )
        return TestResult("Wilcoxon signed-rank CMP/CBA", stat, p, interp, len(df))

    def test_tendencia_temporal(self, especie_code: str | None = None) -> TestResult:
        """
        Kendall tau sobre ratio CMP/CBA a lo largo del tiempo.
        Detecta si la sobreasignación aumenta o disminuye año a año.
        """
        df = self.comp.get_triangulo_completo(especie_code).dropna(subset=["ratio_cmp_cba"])
        df = df.sort_values("year")
        if len(df) < 4:
            return TestResult("Kendall tau tendencia", np.nan, 1.0, "Datos insuficientes", len(df))
        tau, p = stats.kendalltau(df["year"], df["ratio_cmp_cba"])
        direccion = "creciente" if tau > 0 else "decreciente"
        interp = (
            f"Tendencia {direccion} en ratio CMP/CBA (τ={tau:.3f})"
            if p < 0.05
            else f"Sin tendencia temporal significativa (τ={tau:.3f})"
        )
        label = f"Kendall tau — {especie_code or 'todas las especies'}"
        return TestResult(label, tau, p, interp, len(df))

    def test_diferencia_entre_especies(self) -> TestResult:
        """
        Kruskal-Wallis: ¿difiere el nivel de sobreasignación entre especies?
        """
        df = self.comp.get_triangulo_completo().dropna(subset=["ratio_cmp_cba"])
        grupos = [g["ratio_cmp_cba"].values for _, g in df.groupby("especie") if len(g) >= 2]
        if len(grupos) < 2:
            return TestResult("Kruskal-Wallis especies", np.nan, 1.0, "Datos insuficientes", len(df))
        stat, p = stats.kruskal(*grupos)
        interp = (
            "Diferencias significativas entre especies en ratio CMP/CBA"
            if p < 0.05
            else "No hay diferencias significativas entre especies"
        )
        return TestResult("Kruskal-Wallis entre especies", stat, p, interp, len(df))

    def test_correlacion_captura_cba(self) -> TestResult:
        """
        Spearman: correlación entre ratio CMP/CBA y ratio Captura/CBA.
        Detecta si cuando el CFP aprueba más, también se captura más.
        """
        df = self.comp.get_triangulo_completo().dropna(
            subset=["ratio_cmp_cba", "ratio_captura_cba"]
        )
        if len(df) < 4:
            return TestResult("Spearman CMP-Captura", np.nan, 1.0, "Datos insuficientes", len(df))
        rho, p = stats.spearmanr(df["ratio_cmp_cba"], df["ratio_captura_cba"])
        interp = (
            f"Correlación positiva significativa (ρ={rho:.3f}): cuotas más altas → más captura"
            if (p < 0.05 and rho > 0)
            else f"Correlación negativa (ρ={rho:.3f}): cuotas altas no se traducen en más captura"
            if (p < 0.05 and rho < 0)
            else f"Sin correlación significativa (ρ={rho:.3f})"
        )
        return TestResult("Spearman CMP/CBA ↔ Captura/CBA", rho, p, interp, len(df))

    def ejecutar_todos_los_tests(self) -> list[TestResult]:
        """Corre toda la batería de tests estadísticos."""
        resultados = [
            self.test_sobreasignacion(),
            self.test_tendencia_temporal(),
            self.test_diferencia_entre_especies(),
            self.test_correlacion_captura_cba(),
        ]
        especies = self.comp.get_triangulo_completo()["especie_code"].dropna().unique()
        for esp in especies:
            resultados.append(self.test_tendencia_temporal(esp))
        return resultados

    # ------------------------------------------------------------------
    # Exportación de datos
    # ------------------------------------------------------------------

    def exportar_csv(self) -> Path:
        """CSV estructurado con metadatos FAIR del triángulo de auditoría."""
        df = self.comp.get_triangulo_completo()
        df["fuente_cba"] = "INIDEP Mar Abierto"
        df["fuente_cmp"] = "CFP Actas Públicas"
        df["fuente_captura"] = "SAGPyA/SIPA"
        df["serie"] = SERIES_NAME
        df["fecha_exportacion"] = datetime.now().strftime("%Y-%m-%d")

        out_path = self.out / "datos" / "triangulo_auditoria.csv"
        df.to_csv(out_path, index=False, encoding="utf-8-sig")
        logger.info(f"CSV exportado: {out_path} ({len(df)} registros)")
        return out_path

    def exportar_excel(self) -> Path:
        """Excel con múltiples hojas: triángulo, alertas, tests estadísticos."""
        out_path = self.out / "datos" / "FisheriesAudit_ALG_datos.xlsx"
        tests = self.ejecutar_todos_los_tests()

        with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
            self.comp.get_triangulo_completo().to_excel(
                writer, sheet_name="Triángulo_Auditoría", index=False
            )
            self.comp.get_alertas_activas("verde").to_excel(
                writer, sheet_name="Alertas", index=False
            )
            self.comp.get_inidep_data().to_excel(
                writer, sheet_name="INIDEP_evaluaciones", index=False
            )
            self.comp.get_cfp_data().to_excel(writer, sheet_name="CFP_cuotas", index=False)
            self.comp.get_capturas_data().to_excel(
                writer, sheet_name="Capturas_SAGPyA", index=False
            )
            pd.DataFrame([t.to_dict() for t in tests]).to_excel(
                writer, sheet_name="Tests_estadísticos", index=False
            )

        logger.info(f"Excel exportado: {out_path}")
        return out_path

    def exportar_tabla_latex(self, especie_code: str | None = None) -> str:
        """Genera tabla LaTeX del triángulo de auditoría."""
        df = self.comp.get_triangulo_completo(especie_code)
        df = df.dropna(subset=["cba_recomendada_tn"]).sort_values(["especie", "year"])

        cols = {
            "especie": "Especie",
            "year": "Año",
            "cba_recomendada_tn": "CBA (tn)",
            "cmp_aprobada_tn": "CMP (tn)",
            "captura_real_tn": "Captura (tn)",
            "ratio_cmp_cba": "CMP/CBA",
            "ratio_captura_cba": "Cap/CBA",
        }
        df_latex = df[[c for c in cols if c in df.columns]].rename(columns=cols)

        def _fmt(v):
            if pd.isna(v):
                return "---"
            if isinstance(v, float) and v > 100:
                return f"{v:,.0f}"
            if isinstance(v, float):
                return f"{v:.2f}"
            return str(v)

        latex_rows = []
        for _, row in df_latex.iterrows():
            latex_rows.append(" & ".join(_fmt(row[c]) for c in df_latex.columns) + r" \\")

        header = " & ".join(df_latex.columns) + r" \\"
        latex = textwrap.dedent(
            rf"""
            \begin{{table}}[ht]
            \centering
            \caption{{Triángulo de Auditoría Pesquera — CBA (INIDEP), CMP (CFP) y Captura Real (SAGPyA). Fuente: {SERIES_NAME}.}}
            \label{{tab:triangulo_auditoria}}
            \begin{{tabular}}{{{'l' + 'r' * (len(df_latex.columns) - 1)}}}
            \hline
            {header}
            \hline
            {chr(10).join(latex_rows)}
            \hline
            \end{{tabular}}
            \end{{table}}
            """
        ).strip()

        out_path = self.out / "tablas_latex" / "tabla_triangulo.tex"
        out_path.write_text(latex, encoding="utf-8")
        logger.info(f"LaTeX guardado: {out_path}")
        return latex

    # ------------------------------------------------------------------
    # Hallazgos publicables
    # ------------------------------------------------------------------

    def generar_hallazgos(self) -> list[HallazgoPublicable]:
        """Genera lista de hallazgos estructurados listos para publicación."""
        hallazgos: list[HallazgoPublicable] = []
        df = self.comp.get_triangulo_completo()
        summary = self.comp.summary_report()

        # Hallazgo 1: Sobreasignación sistémica
        t_sobre = self.test_sobreasignacion()
        df_ratio = df.dropna(subset=["ratio_cmp_cba"])
        if not df_ratio.empty:
            median_r = df_ratio["ratio_cmp_cba"].median()
            pct_sobre = (df_ratio["ratio_cmp_cba"] > 1.0).mean() * 100
            hallazgos.append(
                HallazgoPublicable(
                    titulo="Sobreasignación sistémica de cuotas pesqueras",
                    descripcion=(
                        f"El CFP aprueba cuotas superiores a la CBA recomendada por INIDEP "
                        f"en el {pct_sobre:.0f}% de los casos analizados, con una mediana "
                        f"de sobreasignación del {(median_r - 1)*100:.0f}%."
                    ),
                    datos_clave={
                        "Mediana ratio CMP/CBA": f"{median_r:.2f}",
                        "% casos sobre CBA": f"{pct_sobre:.0f}%",
                        "N comparaciones": len(df_ratio),
                        "Especies": ", ".join(sorted(df_ratio["especie"].unique())),
                    },
                    nivel_evidencia="alto" if t_sobre.significativo else "exploratorio",
                    tests=[t_sobre],
                    fuentes=["INIDEP ITOs", "CFP Actas Públicas"],
                )
            )

        # Hallazgo 2: Sub-utilización de cuotas
        n_sub = summary.get("n_sub_utilizacion", 0)
        df_sub = df.dropna(subset=["ratio_captura_cba"])
        if n_sub > 0:
            pct_sub = n_sub / max(len(df_sub), 1) * 100
            hallazgos.append(
                HallazgoPublicable(
                    titulo="Sub-utilización de cuotas aprobadas",
                    descripcion=(
                        f"En {n_sub} casos ({pct_sub:.0f}% del total), la captura real "
                        f"fue inferior al 70% de la CMP aprobada por el CFP, indicando "
                        f"posible especulación con cuotas pesqueras."
                    ),
                    datos_clave={
                        "Casos sub-utilización (<70% CMP)": n_sub,
                        "% del total analizado": f"{pct_sub:.0f}%",
                    },
                    nivel_evidencia="medio",
                    fuentes=["SAGPyA/SIPA capturas reales", "CFP Resoluciones"],
                )
            )

        # Hallazgo 3: Tendencia temporal
        t_tend = self.test_tendencia_temporal()
        hallazgos.append(
            HallazgoPublicable(
                titulo="Tendencia temporal en sobreasignación",
                descripcion=t_tend.interpretacion,
                datos_clave={
                    "Kendall τ": f"{t_tend.estadistico:.3f}" if not np.isnan(t_tend.estadistico) else "N/A",
                    "p-valor": f"{t_tend.p_value:.4f}",
                    "N observaciones": t_tend.n,
                },
                nivel_evidencia="alto" if t_tend.significativo else "exploratorio",
                tests=[t_tend],
                fuentes=["INIDEP ITOs", "CFP Actas Públicas"],
            )
        )

        # Hallazgo 4: Correlación cuota-captura
        t_corr = self.test_correlacion_captura_cba()
        hallazgos.append(
            HallazgoPublicable(
                titulo="Correlación entre cuotas CFP y capturas reales",
                descripcion=t_corr.interpretacion,
                datos_clave={
                    "Spearman ρ": f"{t_corr.estadistico:.3f}" if not np.isnan(t_corr.estadistico) else "N/A",
                    "p-valor": f"{t_corr.p_value:.4f}",
                    "N observaciones": t_corr.n,
                },
                nivel_evidencia="alto" if t_corr.significativo else "exploratorio",
                tests=[t_corr],
                fuentes=["SAGPyA/SIPA", "CFP Actas Públicas"],
            )
        )

        return hallazgos

    # ------------------------------------------------------------------
    # Exportar todo
    # ------------------------------------------------------------------

    def exportar_todo(self) -> dict[str, Path | str]:
        """Pipeline completo: figuras + datos + LaTeX + hallazgos."""
        logger.info(f"=== {SERIES_NAME} — Exportación completa ===")
        resultados: dict[str, Path | str] = {}

        try:
            df_all = self.comp.get_triangulo_completo()
            for esp_code in df_all["especie_code"].dropna().unique():
                try:
                    self.figura_triangulo_por_especie(esp_code)
                except Exception as e:
                    logger.warning(f"Figura triángulo {esp_code}: {e}")
        except Exception as e:
            logger.warning(f"Figuras por especie: {e}")

        try:
            self.figura_comparacion_todas_especies()
        except Exception as e:
            logger.warning(f"Scatter especies: {e}")

        try:
            self.figura_alertas_heatmap()
        except Exception as e:
            logger.warning(f"Heatmap alertas: {e}")

        resultados["csv"] = self.exportar_csv()
        resultados["excel"] = self.exportar_excel()
        resultados["latex"] = self.exportar_tabla_latex()

        hallazgos = self.generar_hallazgos()
        hallazgos_path = self.out / "datos" / "hallazgos.json"
        import json

        hallazgos_path.write_text(
            json.dumps(
                [
                    {
                        "titulo": h.titulo,
                        "descripcion": h.descripcion,
                        "datos_clave": h.datos_clave,
                        "nivel_evidencia": h.nivel_evidencia,
                        "tests": [t.to_dict() for t in h.tests],
                        "fuentes": h.fuentes,
                    }
                    for h in hallazgos
                ],
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        resultados["hallazgos"] = hallazgos_path

        logger.info(f"Exportación completada en {self.out}")
        logger.info(f"Hallazgos generados: {len(hallazgos)}")
        return resultados
