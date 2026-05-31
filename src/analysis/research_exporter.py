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


# ──────────────────────────────────────────────────────────────────────────────
# PatternExporter — figuras y tests para PatternDetector (Entrega #02)
# ──────────────────────────────────────────────────────────────────────────────


class PatternExporter:
    """
    Genera outputs científicos a partir del PatternDetector.

    Uso:
        from src.analysis.pattern_detector import PatternDetector
        pd_det = PatternDetector(DB_PATH)
        pexp = PatternExporter(pd_det, output_dir="outputs/FisheriesAudit_ALG")
        pexp.figura_timeline_resoluciones()
        pexp.figura_hhi()
        pexp.figura_riesgo_temporal()
    """

    def __init__(self, detector, output_dir: str | Path = "outputs/FisheriesAudit_ALG") -> None:
        self.det = detector
        self.out = Path(output_dir)
        (self.out / "figuras").mkdir(parents=True, exist_ok=True)
        (self.out / "datos").mkdir(exist_ok=True)
        (self.out / "tablas_latex").mkdir(exist_ok=True)

    # ------------------------------------------------------------------
    # Figuras de patrones históricos
    # ------------------------------------------------------------------

    def figura_timeline_resoluciones(self, save: bool = True) -> plt.Figure:
        """Serie temporal de resoluciones CFP por año y tipo (1998–2025)."""
        df = self.det.resolution_timeline()

        if df.empty:
            fig, ax = plt.subplots(figsize=(10, 4))
            ax.text(0.5, 0.5, "Sin datos de resoluciones procesadas.\nEjecutá el pipeline primero.",
                    ha="center", va="center", transform=ax.transAxes, fontsize=11, color="gray")
            ax.set_title("Serie temporal de resoluciones CFP (sin datos)")
            fig.text(0.99, 0.01, SERIES_BRAND, ha="right", va="bottom", fontsize=7, color="gray")
            if save:
                fig.savefig(self.out / "figuras" / "timeline_resoluciones.png")
            return fig

        pivot = df.pivot_table(index="year", columns="tipo", values="cantidad", aggfunc="sum").fillna(0)

        fig, ax = plt.subplots(figsize=(12, 5))
        colors = plt.cm.Set2(np.linspace(0, 1, len(pivot.columns)))

        bottom = np.zeros(len(pivot))
        for col, color in zip(pivot.columns, colors):
            ax.bar(pivot.index, pivot[col], bottom=bottom, label=col, color=color, alpha=0.85)
            bottom += pivot[col].values

        ax.set_xlabel("Año")
        ax.set_ylabel("Número de resoluciones")
        ax.set_title("Resoluciones CFP por año y tipo (1998–2025)\nFuente: Actas Públicas CFP + FisheriesAudit ALG")
        ax.legend(loc="upper left", fontsize=8, ncol=2)
        fig.text(0.99, 0.01, SERIES_BRAND, ha="right", va="bottom", fontsize=7, color="gray")
        fig.tight_layout()

        if save:
            fig.savefig(self.out / "figuras" / "timeline_resoluciones.png")
            fig.savefig(self.out / "figuras" / "timeline_resoluciones.svg")
        return fig

    def figura_hhi(self, top_n: int = 15, save: bool = True) -> plt.Figure:
        """Concentración de beneficiarios (HHI) — top empresas por menciones."""
        df = self.det.top_beneficiaries(limit=top_n)

        if df.empty:
            fig, ax = plt.subplots(figsize=(9, 5))
            ax.text(0.5, 0.5, "Sin datos de entidades.\nEjecutá el pipeline primero.",
                    ha="center", va="center", transform=ax.transAxes, fontsize=11, color="gray")
            ax.set_title("Concentración de beneficiarios (sin datos)")
            fig.text(0.99, 0.01, SERIES_BRAND, ha="right", va="bottom", fontsize=7, color="gray")
            if save:
                fig.savefig(self.out / "figuras" / "hhi_beneficiarios.png")
            return fig

        hhi_data = self.det.hhi_concentration()
        hhi_val = hhi_data.get("hhi", 0)

        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5))

        # Barras horizontales — top empresas
        df_plot = df.sort_values("menciones", ascending=True).tail(top_n)
        ax1.barh(df_plot["nombre"], df_plot["menciones"], color=COLOR_CMP, alpha=0.8)
        ax1.set_xlabel("Menciones en resoluciones CFP")
        ax1.set_title(f"Top {top_n} actores por frecuencia en resoluciones")

        # Gauge HHI
        theta = np.linspace(0, np.pi, 200)
        ax2.set_aspect("equal")
        ax2.fill_between(np.cos(theta[:67]), np.sin(theta[:67]) * 0, np.sin(theta[:67]),
                         color=COLOR_VERDE, alpha=0.3)
        ax2.fill_between(np.cos(theta[67:134]), np.sin(theta[67:134]) * 0, np.sin(theta[67:134]),
                         color=COLOR_AMARILLO, alpha=0.3)
        ax2.fill_between(np.cos(theta[134:]), np.sin(theta[134:]) * 0, np.sin(theta[134:]),
                         color=COLOR_CRITICO, alpha=0.3)

        hhi_norm = min(hhi_val / 10000, 1.0)
        needle_angle = np.pi * (1 - hhi_norm)
        ax2.annotate("", xy=(np.cos(needle_angle) * 0.7, np.sin(needle_angle) * 0.7),
                     xytext=(0, 0),
                     arrowprops=dict(arrowstyle="->", color="black", lw=2.5))
        ax2.text(0, -0.25, f"HHI = {hhi_val:.0f}", ha="center", fontsize=14, fontweight="bold")
        ax2.text(-1, -0.4, "<1000\nBaja", ha="center", fontsize=8, color=COLOR_VERDE)
        ax2.text(0, -0.5, "1000–2500\nModerada", ha="center", fontsize=8, color=COLOR_AMARILLO)
        ax2.text(1, -0.4, ">2500\nAlta", ha="center", fontsize=8, color=COLOR_CRITICO)
        ax2.set_xlim(-1.2, 1.2)
        ax2.set_ylim(-0.6, 1.1)
        ax2.axis("off")
        ax2.set_title(f"Índice HHI de concentración\n{hhi_data.get('interpretation', '')}")

        fig.text(0.99, 0.01, SERIES_BRAND, ha="right", va="bottom", fontsize=7, color="gray")
        fig.tight_layout()

        if save:
            fig.savefig(self.out / "figuras" / "hhi_beneficiarios.png")
            fig.savefig(self.out / "figuras" / "hhi_beneficiarios.svg")
        return fig

    def figura_riesgo_temporal(self, save: bool = True) -> plt.Figure:
        """Evolución del score de riesgo promedio por año."""
        df = self.det.risk_evolution()

        if df.empty:
            fig, ax = plt.subplots(figsize=(10, 4))
            ax.text(0.5, 0.5, "Sin datos de riesgo.\nEjecutá el pipeline + auditoría IA primero.",
                    ha="center", va="center", transform=ax.transAxes, fontsize=11, color="gray")
            ax.set_title("Riesgo temporal (sin datos)")
            if save:
                fig.savefig(self.out / "figuras" / "riesgo_temporal.png")
            return fig

        fig, ax = plt.subplots(figsize=(10, 4))
        ax.fill_between(df["year"], df["riesgo_promedio"], alpha=0.2, color=COLOR_ROJO)
        ax.plot(df["year"], df["riesgo_promedio"], "o-", color=COLOR_ROJO,
                lw=2, ms=5, label="Riesgo promedio")
        ax.plot(df["year"], df["riesgo_maximo"], "--", color=COLOR_CRITICO,
                lw=1, alpha=0.6, label="Riesgo máximo")

        ax.axhline(70, color=COLOR_AMARILLO, lw=0.8, ls=":", label="Umbral alto (70)")
        ax.set_xlabel("Año")
        ax.set_ylabel("Score de riesgo (0–100)")
        ax.set_title("Evolución del riesgo en resoluciones CFP (1998–2025)\nAnálisis IA — FisheriesAudit ALG")
        ax.legend()
        ax.set_ylim(0, 105)
        fig.text(0.99, 0.01, SERIES_BRAND, ha="right", va="bottom", fontsize=7, color="gray")
        fig.tight_layout()

        if save:
            fig.savefig(self.out / "figuras" / "riesgo_temporal.png")
            fig.savefig(self.out / "figuras" / "riesgo_temporal.svg")
        return fig

    def figura_reversiones(self, save: bool = True) -> plt.Figure:
        """Visualiza reversiones de veda detectadas (veda → cuota en <2 años)."""
        reversiones = self.det.reversals_detection()

        fig, ax = plt.subplots(figsize=(10, max(3, len(reversiones) * 0.6 + 2)))

        if not reversiones:
            ax.text(0.5, 0.5,
                    "Sin reversiones detectadas en los datos disponibles.\n"
                    "Con el corpus completo (400+ actas) este análisis\nmuestra patrones de veda→cuota.",
                    ha="center", va="center", transform=ax.transAxes, fontsize=10, color="gray")
            ax.set_title("Detección de reversiones de veda (sin datos suficientes)")
            fig.text(0.99, 0.01, SERIES_BRAND, ha="right", va="bottom", fontsize=7, color="gray")
            if save:
                fig.savefig(self.out / "figuras" / "reversiones_veda.png")
            return fig

        especies = [r["especie"] for r in reversiones]
        anios_veda = [r["anio_veda"] for r in reversiones]
        anios_cuota = [r["anio_cuota_posterior"] for r in reversiones]
        delta = [c - v for v, c in zip(anios_veda, anios_cuota)]

        y_pos = range(len(reversiones))
        ax.barh(y_pos, delta, left=anios_veda, color=COLOR_AMARILLO, alpha=0.7, label="Período veda→cuota")
        ax.scatter(anios_veda, y_pos, color=COLOR_ROJO, zorder=3, s=60, label="Año veda")
        ax.scatter(anios_cuota, y_pos, color=COLOR_VERDE, zorder=3, s=60, marker="D", label="Año cuota posterior")

        ax.set_yticks(list(y_pos))
        ax.set_yticklabels(especies)
        ax.set_xlabel("Año")
        ax.set_title(f"Reversiones veda → cuota detectadas ({len(reversiones)} casos)\nFisheriesAudit ALG")
        ax.legend(loc="lower right")
        fig.text(0.99, 0.01, SERIES_BRAND, ha="right", va="bottom", fontsize=7, color="gray")
        fig.tight_layout()

        if save:
            fig.savefig(self.out / "figuras" / "reversiones_veda.png")
            fig.savefig(self.out / "figuras" / "reversiones_veda.svg")
        return fig

    # ------------------------------------------------------------------
    # Tests estadísticos de concentración
    # ------------------------------------------------------------------

    def test_concentracion_hhi(self) -> TestResult:
        """Evalúa si la concentración HHI supera el umbral de preocupación (2500)."""
        hhi_data = self.det.hhi_concentration()
        hhi = hhi_data.get("hhi", 0)
        n = hhi_data.get("empresas_analizadas", 0)
        if n < 2:
            return TestResult("HHI umbral", hhi, 1.0, "Datos insuficientes", n)

        # Comparar distribución de menciones contra distribución uniforme (chi-squared)
        df = self.det.top_beneficiaries(limit=100)
        if df.empty or len(df) < 2:
            return TestResult("HHI umbral", hhi, 1.0, "Datos insuficientes", 0)

        observed = df["menciones"].values
        expected = np.full_like(observed, observed.mean(), dtype=float)
        stat, p = stats.chisquare(observed, expected)
        interp = (
            f"Distribución de menciones significativamente concentrada (HHI={hhi:.0f})"
            if p < 0.05
            else f"Sin concentración estadísticamente significativa (HHI={hhi:.0f})"
        )
        return TestResult("Chi-cuadrado concentración beneficiarios", stat, p, interp, len(df))

    def test_tendencia_riesgo(self) -> TestResult:
        """Kendall tau: ¿el riesgo de las resoluciones aumenta con el tiempo?"""
        df = self.det.risk_evolution()
        if len(df) < 4:
            return TestResult("Kendall tau riesgo temporal", float("nan"), 1.0, "Datos insuficientes", len(df))
        tau, p = stats.kendalltau(df["year"], df["riesgo_promedio"])
        direccion = "creciente" if tau > 0 else "decreciente"
        interp = (
            f"Riesgo {direccion} a lo largo del tiempo (τ={tau:.3f})"
            if p < 0.05
            else f"Sin tendencia temporal en riesgo (τ={tau:.3f})"
        )
        return TestResult("Kendall tau riesgo temporal", tau, p, interp, len(df))

    def exportar_patrones_csv(self) -> Path:
        """Exporta CSV con datos de patrones históricos."""
        frames = {}
        try:
            frames["timeline"] = self.det.resolution_timeline()
        except Exception:
            frames["timeline"] = pd.DataFrame()
        try:
            frames["beneficiarios"] = self.det.top_beneficiaries(100)
        except Exception:
            frames["beneficiarios"] = pd.DataFrame()
        try:
            frames["riesgo"] = self.det.risk_evolution()
        except Exception:
            frames["riesgo"] = pd.DataFrame()

        out_path = self.out / "datos" / "patrones_historicos.csv"
        # Guardar la más completa como CSV principal
        for name, df in frames.items():
            if not df.empty:
                df["tabla_origen"] = name
                df["serie"] = SERIES_NAME
                df.to_csv(out_path, index=False, encoding="utf-8-sig")
                logger.info(f"CSV patrones guardado: {out_path} ({len(df)} filas de '{name}')")
                break
        else:
            pd.DataFrame().to_csv(out_path, index=False)

        return out_path

    def exportar_latex_beneficiarios(self, top_n: int = 10) -> str:
        """Tabla LaTeX de top beneficiarios."""
        df = self.det.top_beneficiaries(limit=top_n)
        if df.empty:
            return r"\begin{table}[ht]\centering\caption{Sin datos}\end{table}"

        cols_map = {
            "nombre": "Empresa / Actor",
            "menciones": "Menciones",
            "actas_distintas": "Actas",
            "primer_anio": "Desde",
            "ultimo_anio": "Hasta",
        }
        df_l = df[[c for c in cols_map if c in df.columns]].rename(columns=cols_map)

        rows = []
        for _, row in df_l.iterrows():
            rows.append(" & ".join(str(v) for v in row) + r" \\")

        header = " & ".join(df_l.columns) + r" \\"
        latex = textwrap.dedent(
            rf"""
            \begin{{table}}[ht]
            \centering
            \caption{{Top {top_n} actores más frecuentes en resoluciones CFP (1998–2025). Fuente: {SERIES_NAME}.}}
            \label{{tab:top_beneficiarios}}
            \begin{{tabular}}{{{'l' + 'r' * (len(df_l.columns) - 1)}}}
            \hline
            {header}
            \hline
            {chr(10).join(rows)}
            \hline
            \end{{tabular}}
            \end{{table}}
            """
        ).strip()

        out_path = self.out / "tablas_latex" / "tabla_beneficiarios.tex"
        out_path.write_text(latex, encoding="utf-8")
        return latex


# ──────────────────────────────────────────────────────────────────────────────
# GraphExporter — figuras y tests para CFPGraphBuilder (Entrega #03)
# ──────────────────────────────────────────────────────────────────────────────


class GraphExporter:
    """
    Genera outputs científicos a partir del CFPGraphBuilder.

    Uso:
        from src.analysis.graph_builder import CFPGraphBuilder
        builder = CFPGraphBuilder(DB_PATH)
        gexp = GraphExporter(builder, output_dir="outputs/FisheriesAudit_ALG")
        G = builder.build_graph()
        gexp.figura_grafo_completo(G)
        gexp.figura_hhi_por_especie(builder.compute_stats(G))
    """

    COLOR_ESPECIE = "#2196F3"   # azul
    COLOR_EMPRESA = "#FF5722"   # naranja

    def __init__(
        self,
        builder,
        output_dir: str | Path = "outputs/FisheriesAudit_ALG",
    ) -> None:
        self.builder = builder
        self.out = Path(output_dir)
        (self.out / "figuras").mkdir(parents=True, exist_ok=True)
        (self.out / "datos").mkdir(exist_ok=True)
        (self.out / "tablas_latex").mkdir(exist_ok=True)

    # ------------------------------------------------------------------
    # Figuras
    # ------------------------------------------------------------------

    def figura_grafo_completo(
        self, G, save: bool = True
    ) -> plt.Figure:
        """
        Visualiza el grafo completo especie ↔ empresa con spring layout.

        Nodos azules = especies, nodos naranjas = empresas.
        Grosor de aristas proporcional al peso (co-menciones).
        Degrada graciosamente si el grafo está vacío.
        """
        import networkx as nx

        fig, ax = plt.subplots(figsize=(14, 10))

        if G is None or G.number_of_nodes() == 0:
            ax.text(
                0.5, 0.5,
                "Grafo vacío — ejecutá el pipeline primero.\n"
                "python scripts/run_full_pipeline.py --step process",
                ha="center", va="center", transform=ax.transAxes,
                fontsize=12, color="gray",
            )
            ax.set_title("Red de relaciones CFP (sin datos)", fontsize=13)
            ax.axis("off")
            fig.text(0.99, 0.01, SERIES_BRAND, ha="right", va="bottom", fontsize=7, color="gray")
            if save:
                fig.savefig(self.out / "figuras" / "grafo_completo.png")
            return fig

        pos = nx.spring_layout(G, seed=42, k=1.5 / (G.number_of_nodes() ** 0.5))

        node_colors = [
            self.COLOR_ESPECIE if d.get("tipo") == "especie" else self.COLOR_EMPRESA
            for _, d in G.nodes(data=True)
        ]
        node_sizes = [
            400 + G.degree(n) * 60
            for n in G.nodes()
        ]

        weights = [G[u][v].get("weight", 1) for u, v in G.edges()]
        max_w = max(weights) if weights else 1
        edge_widths = [0.5 + 3.5 * (w / max_w) for w in weights]
        edge_alphas = [0.3 + 0.6 * (w / max_w) for w in weights]

        # Dibujar aristas
        for (u, v), lw, alpha in zip(G.edges(), edge_widths, edge_alphas):
            ax.plot(
                [pos[u][0], pos[v][0]], [pos[u][1], pos[v][1]],
                color="#BDBDBD", lw=lw, alpha=alpha, zorder=1,
            )

        # Dibujar nodos
        nx.draw_networkx_nodes(
            G, pos, ax=ax,
            node_color=node_colors,
            node_size=node_sizes,
            alpha=0.9,
        )

        # Etiquetas solo para nodos con grado alto (top 20% o mínimo top 15)
        degree_threshold = sorted(
            [G.degree(n) for n in G.nodes()], reverse=True
        )[min(14, G.number_of_nodes() - 1)]
        labels = {n: n for n in G.nodes() if G.degree(n) >= degree_threshold}
        nx.draw_networkx_labels(G, pos, labels=labels, ax=ax, font_size=7.5, font_weight="bold")

        # Leyenda
        from matplotlib.patches import Patch
        legend_elements = [
            Patch(facecolor=self.COLOR_ESPECIE, label="Especie"),
            Patch(facecolor=self.COLOR_EMPRESA, label="Empresa"),
        ]
        ax.legend(handles=legend_elements, loc="upper left", fontsize=9)

        n_esp = sum(1 for _, d in G.nodes(data=True) if d.get("tipo") == "especie")
        n_emp = sum(1 for _, d in G.nodes(data=True) if d.get("tipo") == "empresa")
        ax.set_title(
            f"Red de co-menciones CFP — {G.number_of_nodes()} nodos "
            f"({n_esp} especies · {n_emp} empresas) · {G.number_of_edges()} conexiones\n"
            "Aristas ponderadas por frecuencia de co-mención en decisiones CFP",
            fontsize=11,
        )
        ax.axis("off")
        fig.text(0.99, 0.01, SERIES_BRAND, ha="right", va="bottom", fontsize=7, color="gray")
        fig.tight_layout()

        if save:
            fig.savefig(self.out / "figuras" / "grafo_completo.png")
            fig.savefig(self.out / "figuras" / "grafo_completo.svg")
            logger.info("Figura grafo_completo guardada")

        return fig

    def figura_ego_especie(
        self, G, especie: str, radio: int = 1, save: bool = True
    ) -> plt.Figure:
        """
        Ego graph centrado en una especie (radio 1 o 2).

        Muestra las empresas directamente conectadas a la especie seleccionada.
        Degrada graciosamente si el grafo está vacío o la especie no existe.
        """
        import networkx as nx

        fig, ax = plt.subplots(figsize=(10, 7))

        especie_lower = especie.lower()
        nodo_especie = None
        if G is not None and G.number_of_nodes() > 0:
            for n in G.nodes():
                if especie_lower in n.lower():
                    nodo_especie = n
                    break

        if G is None or G.number_of_nodes() == 0 or nodo_especie is None:
            ax.text(
                0.5, 0.5,
                f"Especie '{especie}' no encontrada en el grafo.\n"
                "Ejecutá el pipeline para poblar el corpus.",
                ha="center", va="center", transform=ax.transAxes,
                fontsize=11, color="gray",
            )
            ax.set_title(f"Ego graph — {especie} (sin datos)", fontsize=12)
            ax.axis("off")
            fig.text(0.99, 0.01, SERIES_BRAND, ha="right", va="bottom", fontsize=7, color="gray")
            if save:
                stem = f"ego_{especie.lower().replace(' ', '_')}"
                fig.savefig(self.out / "figuras" / f"{stem}.png")
            return fig

        ego = nx.ego_graph(G, nodo_especie, radius=radio)
        pos = nx.spring_layout(ego, seed=42, k=2.0 / max(ego.number_of_nodes() ** 0.5, 1))

        node_colors = [
            self.COLOR_ESPECIE if d.get("tipo") == "especie" else self.COLOR_EMPRESA
            for _, d in ego.nodes(data=True)
        ]
        node_sizes = [
            700 if n == nodo_especie else (300 + ego.degree(n) * 40)
            for n in ego.nodes()
        ]

        weights = [ego[u][v].get("weight", 1) for u, v in ego.edges()]
        max_w = max(weights) if weights else 1
        edge_widths = [0.8 + 4.0 * (w / max_w) for w in weights]

        nx.draw_networkx_nodes(ego, pos, ax=ax, node_color=node_colors,
                               node_size=node_sizes, alpha=0.9)
        nx.draw_networkx_edges(ego, pos, ax=ax, width=edge_widths,
                               edge_color="#78909C", alpha=0.7)
        nx.draw_networkx_labels(ego, pos, ax=ax, font_size=8,
                                font_weight="bold",
                                labels={n: n for n in ego.nodes()})

        # Anotaciones de peso en aristas
        edge_labels = {(u, v): str(ego[u][v].get("weight", "")) for u, v in ego.edges()}
        nx.draw_networkx_edge_labels(ego, pos, edge_labels=edge_labels, ax=ax,
                                     font_size=7, label_pos=0.35)

        n_emp = ego.number_of_nodes() - 1
        ax.set_title(
            f"Ego graph — {nodo_especie}\n"
            f"{n_emp} empresas conectadas (radio={radio}) | pesos = co-menciones en decisiones CFP",
            fontsize=11,
        )
        ax.axis("off")

        from matplotlib.patches import Patch
        ax.legend(
            handles=[
                Patch(facecolor=self.COLOR_ESPECIE, label="Especie"),
                Patch(facecolor=self.COLOR_EMPRESA, label="Empresa"),
            ],
            loc="upper left", fontsize=9,
        )
        fig.text(0.99, 0.01, SERIES_BRAND, ha="right", va="bottom", fontsize=7, color="gray")
        fig.tight_layout()

        if save:
            stem = f"ego_{especie.lower().replace(' ', '_')}"
            fig.savefig(self.out / "figuras" / f"{stem}.png")
            fig.savefig(self.out / "figuras" / f"{stem}.svg")
            logger.info(f"Figura ego_{especie} guardada")

        return fig

    def figura_hhi_por_especie(
        self, stats, save: bool = True
    ) -> plt.Figure:
        """
        Gráfico de barras del HHI de concentración por especie.

        Verde < 1000 (baja concentración), amarillo 1000–2500 (moderada),
        rojo > 2500 (alta concentración / posible captura regulatoria).
        Degrada graciosamente si stats.hhi_por_especie está vacío.
        """
        fig, ax = plt.subplots(figsize=(10, 5))

        hhi_data = getattr(stats, "hhi_por_especie", {}) if stats is not None else {}

        if not hhi_data:
            ax.text(
                0.5, 0.5,
                "Sin datos de HHI por especie.\n"
                "Ejecutá el pipeline para poblar el corpus.",
                ha="center", va="center", transform=ax.transAxes,
                fontsize=11, color="gray",
            )
            ax.set_title("HHI de concentración por especie (sin datos)", fontsize=12)
            fig.text(0.99, 0.01, SERIES_BRAND, ha="right", va="bottom", fontsize=7, color="gray")
            if save:
                fig.savefig(self.out / "figuras" / "hhi_por_especie.png")
            return fig

        especies = sorted(hhi_data.keys(), key=lambda e: hhi_data[e], reverse=True)
        valores = [hhi_data[e] for e in especies]

        colores = [
            COLOR_VERDE if v < 1000 else (COLOR_AMARILLO if v < 2500 else COLOR_ROJO)
            for v in valores
        ]

        bars = ax.bar(range(len(especies)), valores, color=colores, alpha=0.85, edgecolor="white")

        # Líneas de umbral
        ax.axhline(1000, color=COLOR_AMARILLO, lw=1.2, ls="--", label="Umbral moderado (1000)")
        ax.axhline(2500, color=COLOR_ROJO, lw=1.2, ls="--", label="Umbral alto (2500)")

        # Valores sobre barras
        for bar, val in zip(bars, valores):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 50,
                f"{val:.0f}",
                ha="center", va="bottom", fontsize=8.5, fontweight="bold",
            )

        ax.set_xticks(range(len(especies)))
        ax.set_xticklabels(especies, rotation=30, ha="right")
        ax.set_ylabel("HHI (0 – 10.000)")
        ax.set_title(
            "Concentración de empresas por especie — Índice HHI\n"
            "Verde=baja (<1000) · Amarillo=moderada (1000–2500) · Rojo=alta (>2500)",
            fontsize=11,
        )
        ax.legend(fontsize=8)
        ax.set_ylim(0, max(valores) * 1.15)
        fig.text(0.99, 0.01, SERIES_BRAND, ha="right", va="bottom", fontsize=7, color="gray")
        fig.tight_layout()

        if save:
            fig.savefig(self.out / "figuras" / "hhi_por_especie.png")
            fig.savefig(self.out / "figuras" / "hhi_por_especie.svg")
            logger.info("Figura hhi_por_especie guardada")

        return fig

    # ------------------------------------------------------------------
    # Tests estadísticos
    # ------------------------------------------------------------------

    def test_centralidad(self, G) -> TestResult:
        """
        Evalúa si la distribución de betweenness centrality es significativamente
        no-uniforme (concentración de intermediación en pocos nodos).

        Usa coeficiente de Gini sobre la distribución de centralidad y un
        test chi-cuadrado de bondad de ajuste contra distribución uniforme.

        Returns:
            TestResult con interpretación de la concentración de centralidad.
        """
        import networkx as nx

        if G is None or G.number_of_nodes() < 3:
            return TestResult(
                "Chi-cuadrado centralidad betweenness",
                float("nan"), 1.0,
                "Grafo insuficiente (n<3 nodos) — ejecutá el pipeline primero.",
                0,
            )

        bc = nx.betweenness_centrality(G)
        valores = np.array(list(bc.values()), dtype=float)
        n = len(valores)

        if valores.sum() == 0:
            return TestResult(
                "Chi-cuadrado centralidad betweenness",
                float("nan"), 1.0,
                "Centralidad uniforme: todos los nodos tienen betweenness = 0 (grafo sin intermediación).",
                n,
            )

        # Coeficiente de Gini
        sorted_vals = np.sort(valores)
        cum_vals = np.cumsum(sorted_vals)
        gini = 1 - 2 * cum_vals.sum() / (n * cum_vals[-1]) + 1 / n

        # Test chi-cuadrado contra distribución uniforme
        expected = np.full(n, valores.mean())
        # Evitar división por cero si expected es 0
        if expected[0] > 0:
            stat, p = stats.chisquare(valores, expected)
        else:
            stat, p = float("nan"), 1.0

        concentrada = gini > 0.5 or (not np.isnan(p) and p < 0.05)
        nivel = (
            "alta" if gini > 0.7 else
            "moderada" if gini > 0.4 else
            "baja"
        )

        interp = (
            f"Concentración {nivel} de intermediación (Gini={gini:.3f}): "
            + ("pocos nodos actúan como puentes críticos entre especies y empresas"
               if concentrada else
               "la intermediación está distribuida sin actores dominantes")
        )

        return TestResult(
            "Chi-cuadrado centralidad betweenness",
            float("nan") if np.isnan(stat) else stat,
            p,
            interp,
            n,
        )

    # ------------------------------------------------------------------
    # Exportación de datos
    # ------------------------------------------------------------------

    def exportar_grafo_csv(self, G) -> Path:
        """
        Exporta la lista de aristas del grafo como CSV con metadatos.

        Columnas: especie, empresa, co_menciones, serie, fecha_exportacion.

        Returns:
            Path al archivo CSV exportado.
        """
        df = self.builder.to_dataframe(G) if G is not None else pd.DataFrame()

        if df.empty:
            df = pd.DataFrame(columns=["especie", "empresa", "co_menciones"])

        df["serie"] = SERIES_NAME
        df["fecha_exportacion"] = datetime.now().strftime("%Y-%m-%d")

        out_path = self.out / "datos" / "grafo_relaciones.csv"
        df.to_csv(out_path, index=False, encoding="utf-8-sig")
        logger.info(f"CSV grafo exportado: {out_path} ({len(df)} aristas)")
        return out_path

    def exportar_latex_top_empresas(
        self, stats, top_n: int = 10
    ) -> str:
        """
        Genera tabla LaTeX de las top empresas por grado/conexiones en el grafo.

        Args:
            stats: GrafoStats con atributo hhi_por_especie y empresa_mas_conectada.
            top_n: número de empresas a incluir.

        Returns:
            String con el código LaTeX de la tabla.
        """
        # Construir tabla desde stats.hhi_por_especie y empresa_mas_conectada
        hhi_data = getattr(stats, "hhi_por_especie", {}) if stats is not None else {}

        if not hhi_data:
            return (
                r"\begin{table}[ht]\centering"
                r"\caption{Sin datos de grafo disponibles}"
                r"\end{table}"
            )

        rows_data = [
            {"especie": esp, "hhi": round(hhi, 0)}
            for esp, hhi in sorted(hhi_data.items(), key=lambda x: x[1], reverse=True)
        ][:top_n]

        df_l = pd.DataFrame(rows_data)
        df_l.columns = ["Especie", "HHI Concentración"]

        latex_rows = []
        for _, row in df_l.iterrows():
            latex_rows.append(
                f"{row['Especie']} & {row['HHI Concentración']:.0f}" + r" \\"
            )

        header = r"Especie & HHI Concentración \\"
        latex = textwrap.dedent(
            rf"""
            \begin{{table}}[ht]
            \centering
            \caption{{Top {top_n} especies por concentración HHI en red de relaciones CFP (1998–2025).
            HHI: Índice de Herfindahl-Hirschman. >2500 = alta concentración. Fuente: {SERIES_NAME}.}}
            \label{{tab:hhi_especies}}
            \begin{{tabular}}{{lr}}
            \hline
            {header}
            \hline
            {chr(10).join(latex_rows)}
            \hline
            \end{{tabular}}
            \end{{table}}
            """
        ).strip()

        out_path = self.out / "tablas_latex" / "tabla_hhi_especies.tex"
        out_path.write_text(latex, encoding="utf-8")
        logger.info(f"LaTeX HHI especies guardado: {out_path}")
        return latex
