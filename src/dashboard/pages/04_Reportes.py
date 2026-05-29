"""
Página de Reportes: visualizaciones, exportación y generación de informes.
"""

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(ROOT))

st.set_page_config(page_title="Reportes | CFP Audit", page_icon="📊", layout="wide")
st.title("📊 Reportes y Visualizaciones")
st.caption("Análisis estadístico y exportación de resultados de auditoría")

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

DB_PATH = ROOT / "data" / "processed" / "catalog.db"

if not DB_PATH.exists():
    st.error("Base de datos no encontrada. Ejecuta el pipeline de adquisición y procesamiento.")
    st.stop()

from src.acquisition.catalog_manager import CatalogManager
from src.analysis.pattern_detector import PatternDetector

catalog = CatalogManager(DB_PATH)
detector = PatternDetector(DB_PATH)
stats = catalog.stats()

# ── Tabs ──────────────────────────────────────────────────────────────────────

tab_overview, tab_species, tab_risk, tab_export = st.tabs(
    [
        "📈 Panorama General",
        "🐠 Por Especie",
        "⚠️ Riesgo y Anomalías",
        "💾 Exportar",
    ]
)

# ── Tab 1: Panorama general ───────────────────────────────────────────────────

with tab_overview:
    st.subheader("Distribución de Actas por Año")

    if stats["by_year"]:
        df_years = pd.DataFrame(
            list(stats["by_year"].items()), columns=["Año", "Actas"]
        ).sort_values("Año")

        fig = px.bar(
            df_years,
            x="Año",
            y="Actas",
            title="Actas del CFP por Año (1998–2025)",
            color="Actas",
            color_continuous_scale="Blues",
        )
        fig.update_layout(showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

        # Métricas de cobertura
        col1, col2, col3 = st.columns(3)
        col1.metric("Año con más actas", df_years.loc[df_years["Actas"].idxmax(), "Año"])
        col2.metric("Promedio anual", f"{df_years['Actas'].mean():.1f}")
        col3.metric("Total años cubiertos", len(df_years))
    else:
        st.info("Sin datos en el catálogo. Ejecuta el scraping de actas.")

    st.markdown("---")

    # Pipeline progress
    st.subheader("Progreso del Pipeline")
    stages = {
        "Catalogadas": stats["total"],
        "Descargadas": stats["downloaded"],
        "Procesadas": stats["processed"],
        "Indexadas (KB)": stats["embedded"],
        "Auditadas (IA)": stats["analyzed"],
    }
    max_val = max(stages.values()) if any(stages.values()) else 1
    for stage, val in stages.items():
        pct = val / max_val if max_val > 0 else 0
        st.progress(pct, text=f"{stage}: {val:,} ({pct * 100:.0f}%)")

# ── Tab 2: Por especie ────────────────────────────────────────────────────────

with tab_species:
    st.subheader("Análisis por Especie Pesquera")
    st.info(
        "Esta sección muestra estadísticas de menciones por especie en las resoluciones. "
        "Requiere que el pipeline de procesamiento y NER esté completo."
    )

    # Placeholder con datos de ejemplo para demostración
    especies_demo = {
        "merluza hubbsi": 450,
        "langostino": 320,
        "calamar illex": 280,
        "merluza de cola": 190,
        "abadejo": 145,
        "polaca": 120,
        "merluza negra": 98,
        "corvina rubia": 87,
        "anchoita": 65,
        "caballa": 43,
    }

    df_esp = pd.DataFrame(list(especies_demo.items()), columns=["Especie", "Menciones"])
    fig_esp = px.treemap(
        df_esp,
        path=["Especie"],
        values="Menciones",
        title="Menciones por Especie en Resoluciones del CFP",
        color="Menciones",
        color_continuous_scale="Teal",
    )
    st.plotly_chart(fig_esp, use_container_width=True)
    st.caption("Datos ilustrativos hasta completar el pipeline de NER")

    # Radar de sostenibilidad por especie (placeholder)
    categorias = [
        "Frecuencia decisiones",
        "Variabilidad cuotas",
        "Vedas registradas",
        "Alertas IA",
        "Índice presión",
    ]
    fig_radar = go.Figure()
    for especie, values in [
        ("Merluza hubbsi", [0.9, 0.7, 0.6, 0.75, 0.8]),
        ("Langostino", [0.7, 0.5, 0.3, 0.4, 0.55]),
        ("Calamar Illex", [0.6, 0.8, 0.2, 0.5, 0.65]),
    ]:
        fig_radar.add_trace(
            go.Scatterpolar(r=values, theta=categorias, fill="toself", name=especie)
        )
    fig_radar.update_layout(title="Perfil de Presión Pesquera (Ilustrativo)")
    st.plotly_chart(fig_radar, use_container_width=True)
    st.caption("Datos ilustrativos. Se poblará automáticamente con el análisis IA completo.")

# ── Tab 3: Riesgo y anomalías ─────────────────────────────────────────────────

with tab_risk:
    st.subheader("Mapa de Riesgo por Año y Tipo")

    risk_evo = detector.risk_evolution()
    if not risk_evo.empty:
        fig_risk = px.line(
            risk_evo,
            x="year",
            y="riesgo_promedio",
            title="Evolución del Score de Riesgo Promedio por Año",
            markers=True,
        )
        fig_risk.add_hline(
            y=60, line_dash="dash", line_color="orange", annotation_text="Riesgo medio"
        )
        fig_risk.add_hline(y=80, line_dash="dash", line_color="red", annotation_text="Riesgo alto")
        st.plotly_chart(fig_risk, use_container_width=True)
    else:
        st.info("Sin datos de riesgo. Ejecuta el análisis IA sobre las resoluciones.")

    st.markdown("---")

    # Reversiones detectadas
    st.subheader("Reversiones Detectadas")
    reversals = detector.reversals_detection()
    if reversals:
        df_rev = pd.DataFrame(reversals)
        st.dataframe(df_rev, use_container_width=True)
        st.warning(
            f"{len(reversals)} reversiones detectadas (cuotas otorgadas poco después de vedas). "
            "Cada caso requiere verificación de la justificación técnica subyacente."
        )
    else:
        st.success("No se detectaron reversiones estadísticas. Sin datos suficientes aún.")

    # HHI
    st.markdown("---")
    st.subheader("Concentración de Mercado (HHI)")
    hhi_data = detector.hhi_concentration()

    gauge_hhi = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=hhi_data.get("hhi", 0),
            domain={"x": [0, 1], "y": [0, 1]},
            title={"text": "Índice HHI de Concentración"},
            gauge={
                "axis": {"range": [0, 10000]},
                "bar": {"color": "darkblue"},
                "steps": [
                    {"range": [0, 1000], "color": "lightgreen"},
                    {"range": [1000, 2500], "color": "yellow"},
                    {"range": [2500, 10000], "color": "salmon"},
                ],
                "threshold": {
                    "line": {"color": "red", "width": 4},
                    "thickness": 0.75,
                    "value": 2500,
                },
            },
        )
    )
    gauge_hhi.update_layout(height=300)
    st.plotly_chart(gauge_hhi, use_container_width=True)
    st.caption(hhi_data.get("interpretation", "Sin datos"))

# ── Tab 4: Exportar ───────────────────────────────────────────────────────────

with tab_export:
    st.subheader("Exportar Datos y Reportes")

    export_options = st.multiselect(
        "Selecciona qué exportar",
        [
            "Catálogo de actas (CSV)",
            "Resoluciones con score de riesgo (CSV)",
            "Reporte de patrones (JSON)",
            "Entidades mencionadas (CSV)",
        ],
        default=["Catálogo de actas (CSV)"],
    )

    if st.button("Generar Exportaciones", type="primary"):
        import json as json_lib
        import sqlite3

        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row

            if "Catálogo de actas (CSV)" in export_options:
                df_actas = pd.read_sql_query("SELECT * FROM actas", conn)
                csv_data = df_actas.to_csv(index=False).encode("utf-8")
                st.download_button(
                    "💾 Descargar catálogo de actas",
                    csv_data,
                    "cfp_actas_catalogo.csv",
                    "text/csv",
                )

            if "Resoluciones con score de riesgo (CSV)" in export_options:
                df_res = pd.read_sql_query(
                    "SELECT r.*, a.year FROM resoluciones r JOIN actas a ON r.acta_id=a.id "
                    "WHERE r.riesgo_score IS NOT NULL ORDER BY r.riesgo_score DESC",
                    conn,
                )
                st.download_button(
                    "💾 Descargar resoluciones con riesgo",
                    df_res.to_csv(index=False).encode("utf-8"),
                    "cfp_resoluciones_riesgo.csv",
                    "text/csv",
                )

            if "Reporte de patrones (JSON)" in export_options:
                report = detector.full_report()
                st.download_button(
                    "💾 Descargar reporte de patrones",
                    json_lib.dumps(report, ensure_ascii=False, indent=2).encode("utf-8"),
                    "cfp_patrones_report.json",
                    "application/json",
                )

        st.success("Exportaciones generadas.")

    st.markdown("---")
    st.info(
        "**Próximamente:** Generación de informes PDF con portada, "
        "tablas de evidencia y visualizaciones integradas (Fase 5 del roadmap)."
    )
