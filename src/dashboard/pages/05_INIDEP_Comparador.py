"""
Página del Comparador CFP vs. INIDEP: cuotas aprobadas vs. CBA recomendada.

Visualiza alertas cuando el CFP aprueba cuotas superiores a las recomendaciones
científicas del INIDEP (Ley 24.922, Art. 9).
"""

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(ROOT))

st.set_page_config(
    page_title="Comparador INIDEP | CFP Audit",
    page_icon="🔬",
    layout="wide",
)
st.title("🔬 Comparador CFP vs. INIDEP")
st.caption(
    "Cuotas aprobadas por el CFP vs. Captura Biológicamente Aceptable (CBA) "
    "recomendada por el INIDEP — Ley 24.922, Art. 9"
)

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

DB_PATH = ROOT / "data" / "processed" / "catalog.db"

# ── Inicializar comparador ─────────────────────────────────────────────────────


@st.cache_resource(show_spinner="Inicializando base de datos INIDEP...")
def get_comparator():
    from src.analysis.inidep_comparator import INIDEPComparator

    return INIDEPComparator(DB_PATH)


try:
    comp = get_comparator()
except Exception as exc:
    st.error(f"Error inicializando comparador: {exc}")
    st.stop()

# ── Sidebar — ingreso manual de cuota CFP ─────────────────────────────────────

with st.sidebar:
    st.header("➕ Registrar Cuota CFP")
    st.caption("Ingresa manualmente cuotas aprobadas por el CFP para cruzarlas con INIDEP.")

    with st.form("form_cuota"):
        especie_opts = {
            "Merluza común (Sur 41°S)": ("merluza común", "merluza_hubbsi"),
            "Merluza común (Norte 41°S)": ("merluza común", "merluza_hubbsi"),
            "Centolla": ("centolla", "centolla"),
            "Abadejo": ("abadejo", "abadejo"),
            "Polaca": ("polaca", "polaca"),
            "Langostino": ("langostino", "langostino"),
            "Otra": None,
        }
        especie_sel = st.selectbox("Especie", list(especie_opts.keys()))
        zona_input = st.text_input("Zona", placeholder="Sur 41°S / Norte 41°S / Nacional")
        year_input = st.number_input("Año", min_value=2000, max_value=2030, value=2025)
        cmp_input = st.number_input("CMP aprobada (tn)", min_value=0.0, step=100.0)
        acta_input = st.text_input("Acta / Resolución CFP", placeholder="Acta 34/2025")
        submit = st.form_submit_button("Registrar cuota")

    if submit and cmp_input > 0:
        mapping = especie_opts.get(especie_sel)
        if mapping:
            especie_n, especie_code = mapping
        else:
            especie_n = especie_sel.lower()
            especie_code = especie_sel.lower().replace(" ", "_")

        zona_val = zona_input.strip() or None
        comp.upsert_cfp_cuota(
            especie=especie_n,
            especie_code=especie_code,
            year=int(year_input),
            cmp_aprobada_tn=float(cmp_input),
            zona=zona_val,
            acta_referencia=acta_input.strip() or None,
        )
        st.success(f"Cuota registrada: {especie_n} {year_input} — {cmp_input:,.0f} tn")
        st.cache_resource.clear()
        st.rerun()

# ── Compute comparisons ───────────────────────────────────────────────────────

alertas = comp.compute_comparisons()

if not alertas:
    st.info("No hay datos de comparación disponibles. Ingresa cuotas CFP desde el panel lateral.")
    st.stop()

df = pd.DataFrame(
    [
        {
            "Especie": a.especie,
            "Zona": a.zona,
            "Año": a.year,
            "CBA INIDEP (tn)": a.cba_inidep_tn,
            "CMP CFP (tn)": a.cmp_cfp_tn,
            "Diferencia (tn)": a.diferencia_tn,
            "Ratio": a.ratio,
            "Nivel": a.nivel,
            "Descripción": a.descripcion,
            "ITO": a.numero_ito,
            "Acta CFP": a.acta_cfp,
        }
        for a in alertas
    ]
)

# ── Métricas de resumen ───────────────────────────────────────────────────────

total = len(alertas)
criticos = sum(1 for a in alertas if a.nivel == "critico")
rojos = sum(1 for a in alertas if a.nivel == "rojo")
amarillos = sum(1 for a in alertas if a.nivel == "amarillo")
verdes = sum(1 for a in alertas if a.nivel == "verde")
sin_datos = sum(1 for a in alertas if a.nivel == "sin_datos")

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Total comparaciones", total)
col2.metric("🚨 Crítico (>130%)", criticos, delta=None)
col3.metric("⚠️ Rojo (116–130%)", rojos, delta=None)
col4.metric("🟡 Amarillo (101–115%)", amarillos, delta=None)
col5.metric("✅ Verde (≤100%)", verdes, delta=None)

st.divider()

# ── Tabs ──────────────────────────────────────────────────────────────────────

tab_alertas, tab_grafico, tab_inidep, tab_metodologia = st.tabs(
    [
        "🚨 Alertas Activas",
        "📊 Visualización",
        "📋 Datos INIDEP",
        "ℹ️ Metodología",
    ]
)

# ── Tab 1: Alertas activas ─────────────────────────────────────────────────────

with tab_alertas:
    NIVEL_COLOR = {
        "critico": "🚨",
        "rojo": "⚠️",
        "amarillo": "🟡",
        "verde": "✅",
        "sin_datos": "⬜",
    }
    NIVEL_LABEL = {
        "critico": "CRÍTICO",
        "rojo": "ROJO",
        "amarillo": "AMARILLO",
        "verde": "VERDE",
        "sin_datos": "SIN DATOS",
    }

    nivel_filtro = st.multiselect(
        "Filtrar por nivel de alerta",
        options=["critico", "rojo", "amarillo", "verde", "sin_datos"],
        default=["critico", "rojo", "amarillo"],
        format_func=lambda x: f"{NIVEL_COLOR[x]} {NIVEL_LABEL[x]}",
    )

    df_filtrado = df[df["Nivel"].isin(nivel_filtro)] if nivel_filtro else df

    if df_filtrado.empty:
        st.info("No hay alertas con los filtros seleccionados.")
    else:
        for _, row in df_filtrado.sort_values(
            ["Nivel", "Ratio"], ascending=[True, False]
        ).iterrows():
            icono = NIVEL_COLOR.get(row["Nivel"], "⬜")
            nivel_lbl = NIVEL_LABEL.get(row["Nivel"], row["Nivel"].upper())

            with st.expander(
                f"{icono} **{row['Especie'].title()}** — {row['Zona']} ({row['Año']}) "
                f"| {nivel_lbl}",
                expanded=(row["Nivel"] in ("critico", "rojo")),
            ):
                c1, c2, c3 = st.columns(3)
                c1.metric(
                    "CBA INIDEP",
                    f"{row['CBA INIDEP (tn)']:,.0f} tn" if row["CBA INIDEP (tn)"] else "N/D",
                )
                c2.metric(
                    "CMP CFP aprobada",
                    f"{row['CMP CFP (tn)']:,.0f} tn" if row["CMP CFP (tn)"] else "N/D",
                    delta=(
                        f"+{row['Diferencia (tn)']:,.0f} tn sobre CBA"
                        if row["Diferencia (tn)"] and row["Diferencia (tn)"] > 0
                        else (
                            f"{row['Diferencia (tn)']:,.0f} tn bajo CBA"
                            if row["Diferencia (tn)"]
                            else None
                        )
                    ),
                    delta_color="inverse" if (row["Diferencia (tn)"] or 0) > 0 else "normal",
                )
                c3.metric(
                    "Ratio sobreasignación",
                    f"{row['Ratio']:.2%}" if row["Ratio"] else "N/D",
                )
                st.markdown(f"**Descripción**: {row['Descripción']}")
                meta_cols = st.columns(2)
                if row["ITO"]:
                    meta_cols[0].caption(f"ITO INIDEP: {row['ITO']}")
                if row["Acta CFP"]:
                    meta_cols[1].caption(f"Acta CFP: {row['Acta CFP']}")

# ── Tab 2: Visualización ──────────────────────────────────────────────────────

with tab_grafico:
    df_con_datos = df[df["CBA INIDEP (tn)"].notna() & df["CMP CFP (tn)"].notna()].copy()

    if df_con_datos.empty:
        st.info(
            "No hay datos suficientes para graficar. "
            "Registra cuotas CFP desde el panel lateral para comparar."
        )
    else:
        st.subheader("CBA INIDEP vs. CMP CFP por especie")
        df_con_datos["Especie/Zona"] = (
            df_con_datos["Especie"].str.title()
            + " — "
            + df_con_datos["Zona"].fillna("Nacional")
            + " ("
            + df_con_datos["Año"].astype(str)
            + ")"
        )

        fig = go.Figure()
        fig.add_trace(
            go.Bar(
                name="CBA INIDEP (recomendada)",
                x=df_con_datos["Especie/Zona"],
                y=df_con_datos["CBA INIDEP (tn)"],
                marker_color="#2196F3",
                opacity=0.85,
            )
        )
        fig.add_trace(
            go.Bar(
                name="CMP CFP (aprobada)",
                x=df_con_datos["Especie/Zona"],
                y=df_con_datos["CMP CFP (tn)"],
                marker_color=df_con_datos["Nivel"].map(
                    {
                        "critico": "#D32F2F",
                        "rojo": "#F44336",
                        "amarillo": "#FFC107",
                        "verde": "#4CAF50",
                        "sin_datos": "#9E9E9E",
                    }
                ),
                opacity=0.85,
            )
        )
        fig.update_layout(
            barmode="group",
            title="Comparación CBA INIDEP vs. CMP CFP",
            yaxis_title="Toneladas",
            xaxis_title="",
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
            height=450,
        )
        st.plotly_chart(fig, use_container_width=True)

        # Gauge de ratio para alertas con datos
        st.subheader("Ratio de sobreasignación por especie/zona")
        fig_ratio = px.bar(
            df_con_datos.sort_values("Ratio", ascending=False),
            x="Especie/Zona",
            y="Ratio",
            color="Nivel",
            color_discrete_map={
                "critico": "#D32F2F",
                "rojo": "#F44336",
                "amarillo": "#FFC107",
                "verde": "#4CAF50",
            },
            title="Ratio CMP/CBA (1.0 = límite recomendado)",
            labels={"Ratio": "Ratio (CMP/CBA)", "Especie/Zona": ""},
        )
        fig_ratio.add_hline(
            y=1.0,
            line_dash="dash",
            line_color="gray",
            annotation_text="Límite CBA",
            annotation_position="top right",
        )
        fig_ratio.add_hline(
            y=1.15,
            line_dash="dot",
            line_color="#FFC107",
            annotation_text="Umbral amarillo",
            annotation_position="top right",
        )
        fig_ratio.add_hline(
            y=1.30,
            line_dash="dot",
            line_color="#F44336",
            annotation_text="Umbral rojo",
            annotation_position="top right",
        )
        fig_ratio.update_layout(height=400)
        st.plotly_chart(fig_ratio, use_container_width=True)

# ── Tab 3: Datos INIDEP ───────────────────────────────────────────────────────

with tab_inidep:
    st.subheader("Evaluaciones INIDEP cargadas")
    df_inidep = comp.get_inidep_data()
    if df_inidep.empty:
        st.info("No hay evaluaciones INIDEP registradas.")
    else:
        st.dataframe(
            df_inidep[
                [
                    "especie",
                    "zona",
                    "year",
                    "cba_recomendada_tn",
                    "estado_stock",
                    "numero_ito",
                    "notas",
                ]
            ].rename(
                columns={
                    "especie": "Especie",
                    "zona": "Zona",
                    "year": "Año",
                    "cba_recomendada_tn": "CBA (tn)",
                    "estado_stock": "Estado stock",
                    "numero_ito": "ITO",
                    "notas": "Notas",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )

    st.divider()
    st.subheader("Cuotas CFP registradas")
    df_cfp = comp.get_cfp_data()
    if df_cfp.empty:
        st.info("No hay cuotas CFP registradas. Usa el formulario del panel lateral.")
    else:
        st.dataframe(
            df_cfp[
                [
                    "especie",
                    "zona",
                    "year",
                    "cmp_aprobada_tn",
                    "tipo_decision",
                    "acta_referencia",
                    "resolucion_cfp",
                ]
            ].rename(
                columns={
                    "especie": "Especie",
                    "zona": "Zona",
                    "year": "Año",
                    "cmp_aprobada_tn": "CMP aprobada (tn)",
                    "tipo_decision": "Tipo",
                    "acta_referencia": "Acta referencia",
                    "resolucion_cfp": "Resolución CFP",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )

    col_dl1, col_dl2 = st.columns(2)
    if not df_inidep.empty:
        col_dl1.download_button(
            "⬇️ Descargar datos INIDEP (CSV)",
            df_inidep.to_csv(index=False).encode("utf-8"),
            "inidep_evaluaciones.csv",
            "text/csv",
        )
    if not df_cfp.empty:
        col_dl2.download_button(
            "⬇️ Descargar cuotas CFP (CSV)",
            df_cfp.to_csv(index=False).encode("utf-8"),
            "cfp_cuotas.csv",
            "text/csv",
        )

# ── Tab 4: Metodología ────────────────────────────────────────────────────────

with tab_metodologia:
    st.subheader("Marco metodológico")
    st.markdown("""
### Base legal
**Ley 24.922 — Ley Federal de Pesca, Art. 9:**
> El Consejo Federal Pesquero deberá establecer la Captura Máxima Permisible (CMP)
> sobre la base de las recomendaciones del INIDEP.

### Definiciones

| Término | Definición |
|---------|-----------|
| **CBA** | Captura Biológicamente Aceptable — umbral máximo recomendado por el INIDEP para no comprometer la reproducción de la especie |
| **CMP** | Captura Máxima Permisible — cuota aprobada por el CFP para la temporada |
| **ITO** | Informe Técnico Oficial — documento científico del INIDEP con la evaluación del stock |
| **Ratio CMP/CBA** | Relación entre lo aprobado y lo recomendado. Ratio >1.0 indica sobreasignación |

### Sistema de alertas

| Nivel | Criterio | Implicancia |
|-------|----------|-------------|
| ✅ **Verde** | CMP ≤ 100% CBA | Dentro del límite recomendado |
| 🟡 **Amarillo** | CMP 101–115% CBA | Supera leve/moderadamente la CBA. Monitorear. |
| ⚠️ **Rojo** | CMP 116–130% CBA | Sobreasignación significativa. Riesgo de sobrepesca. |
| 🚨 **Crítico** | CMP > 130% CBA | Riesgo crítico de sostenibilidad. Posible violación Art. 9 Ley 24.922. |

### Fuentes de datos INIDEP
- **Mar Abierto** (`marabierto.inidep.edu.ar`): repositorio institucional con 492+ ITOs
- Los datos semilla están verificados con fuentes oficiales publicadas
- Los ITOs son documentos de acceso público

### Limitaciones
- Los datos CFP se ingresan manualmente hasta completar el scraping completo de resoluciones
- Algunos ITOs no publican valores numéricos de CBA (solo rangos o criterios cualitativos)
- La comparación es descriptiva — no constituye acusación legal ni conclusión jurídica
- Los hallazgos deben ser verificados con los textos originales de las resoluciones

### Próximas mejoras
- Scraping automatizado de 492 ITOs del repositorio Mar Abierto
- Extracción automática de CBA desde texto de resoluciones CFP scrapeadas
- Series históricas 1998–2025 por especie
    """)
