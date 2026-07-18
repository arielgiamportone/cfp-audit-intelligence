"""Página 12 — Capturas Reales SIPA/SAGPyA."""

from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.acquisition.sipa_scraper import SIPAScraper

st.title("🐟 Capturas Reales — SIPA / SAGPyA")
st.markdown(
    "Cierre del triángulo de auditoría: **CBA (INIDEP)** → **CMP aprobada (CFP)** → "
    "**Captura real desembarcada (SAGPyA)**. "
    "Permite detectar cuotas sobre la recomendación científica y capturas que superan las cuotas."
)

from src.config_loader import get_db_path
DB_PATH = get_db_path()

ALERTA_COLORS = {
    "verde": "#2E7D32",
    "amarillo": "#F57F17",
    "rojo": "#C62828",
    "critico": "#880E4F",
    "sub_utilizacion": "#1565C0",
    "sin_datos": "#757575",
}

ALERTA_BG = {
    "verde": "#E8F5E9",
    "amarillo": "#FFF9C4",
    "rojo": "#FFEBEE",
    "critico": "#FCE4EC",
    "sub_utilizacion": "#E3F2FD",
    "sin_datos": "#F5F5F5",
}

ALERTA_LABELS = {
    "verde": "✅ Normal",
    "amarillo": "⚠️ Supera CBA",
    "rojo": "🔴 Exceso sobre CBA",
    "critico": "🚨 Crítico (>130% CBA)",
    "sub_utilizacion": "🔵 Sub-utilización",
    "sin_datos": "⬜ Sin datos",
}

@st.cache_resource(show_spinner="Cargando datos de capturas...")
def get_scraper():
    s = SIPAScraper(db_path=DB_PATH)
    s.seed_data()
    return s

scraper = get_scraper()
df_capturas = scraper.get_capturas_df()

if df_capturas.empty:
    st.warning("No hay datos de capturas disponibles.")
    st.stop()

triangulos = scraper.get_triangulo_auditoria()
alertas_activas = scraper.get_alertas_sobrexplotacion()

# ── Métricas globales ──────────────────────────────────────────────────────────

c1, c2, c3, c4 = st.columns(4)
c1.metric("Especies monitoreadas", df_capturas["especie_code"].nunique())
c2.metric("Años cubiertos", f"{int(df_capturas['year'].min())}–{int(df_capturas['year'].max())}")
c3.metric("Casos sobre CBA", len(alertas_activas))
c4.metric(
    "Total desembarcado (último año)",
    f"{df_capturas.sort_values('year').groupby('especie_code').last()['captura_tn'].sum() / 1e6:.2f} M tn",
)

st.divider()

# ── Tabs ──────────────────────────────────────────────────────────────────────

tab1, tab2, tab3, tab4 = st.tabs(
    [
        "📐 Triángulo CBA / CMP / Real",
        "📊 Series temporales",
        "🚨 Alertas de sostenibilidad",
        "📋 Datos completos",
    ]
)

# ── Tab 1: Triángulo ─────────────────────────────────────────────────────────

with tab1:
    st.subheader("Comparación CBA / CMP / Captura real por especie y año")
    st.markdown(
        "El **triángulo de auditoría** muestra si la cuota CFP respeta la CBA del INIDEP "
        "y si la captura efectiva respeta esa cuota. "
        "Barras que superan la línea roja (CBA) indican presión insostenible sobre el recurso."
    )

    if not triangulos:
        st.info(
            "Sin datos para construir el triángulo. Verifique que la base de datos esté inicializada."
        )
    else:
        df_tri = pd.DataFrame(
            [
                {
                    "especie": t.especie.title(),
                    "especie_code": t.especie_code,
                    "year": t.year,
                    "CBA INIDEP": t.cba_inidep_tn,
                    "CMP CFP": t.cmp_cfp_tn,
                    "Captura real": t.captura_real_tn,
                    "ratio_cba": t.ratio_captura_cba,
                    "alerta": t.alerta_captura or "sin_datos",
                }
                for t in triangulos
            ]
        )

        especies_disp = sorted(df_tri["especie_code"].unique())
        especie_sel = st.selectbox(
            "Especie",
            options=especies_disp,
            format_func=lambda x: x.replace("_", " ").title(),
        )

        df_esp = df_tri[df_tri["especie_code"] == especie_sel].sort_values("year")

        if df_esp.empty:
            st.info("Sin datos para esta especie.")
        else:
            fig = go.Figure()

            # CBA — línea roja de límite científico
            if df_esp["CBA INIDEP"].notna().any():
                fig.add_trace(
                    go.Scatter(
                        name="CBA INIDEP",
                        x=df_esp["year"],
                        y=df_esp["CBA INIDEP"],
                        mode="lines+markers",
                        line={"color": "#C62828", "width": 3, "dash": "dash"},
                        marker={"size": 8},
                    )
                )

            # CMP — barras azules (cuota aprobada por CFP)
            if df_esp["CMP CFP"].notna().any():
                fig.add_trace(
                    go.Bar(
                        name="CMP CFP",
                        x=df_esp["year"],
                        y=df_esp["CMP CFP"],
                        marker_color="#90CAF9",
                        marker_line_color="#1565C0",
                        marker_line_width=1.5,
                        opacity=0.8,
                    )
                )

            # Captura real — barras superpuestas
            bar_colors = [ALERTA_COLORS.get(a, "#757575") for a in df_esp["alerta"]]
            fig.add_trace(
                go.Bar(
                    name="Captura real (SAGPyA)",
                    x=df_esp["year"],
                    y=df_esp["Captura real"],
                    marker_color=bar_colors,
                    opacity=0.9,
                )
            )

            fig.update_layout(
                barmode="overlay",
                title=f"Triángulo CBA / CMP / Captura — {especie_sel.replace('_', ' ').title()}",
                yaxis_title="Toneladas",
                height=420,
                legend={"orientation": "h", "y": -0.2},
                annotations=[
                    {
                        "x": 0.01,
                        "y": 0.98,
                        "xref": "paper",
                        "yref": "paper",
                        "text": "🔴 Línea roja = límite CBA (INIDEP)",
                        "showarrow": False,
                        "font": {"size": 11, "color": "#C62828"},
                    }
                ],
            )
            st.plotly_chart(fig, use_container_width=True)

            # Cards de ratios para el último año
            ultimo = df_esp.sort_values("year").iloc[-1]
            st.markdown(f"**Último año disponible: {int(ultimo['year'])}**")
            cols = st.columns(3)

            def _metric_card(col, label, ratio, invert=False):
                if ratio is None:
                    col.metric(label, "Sin datos")
                    return
                pct = f"{ratio:.1%}"
                icon = "🟢" if ratio <= 1.0 else ("🔴" if ratio > 1.15 else "🟡")
                col.metric(
                    label,
                    pct,
                    delta=f"{(ratio - 1):.1%}",
                    delta_color="inverse" if not invert else "normal",
                )
                col.caption(icon)

            _metric_card(cols[0], "Captura real / CBA", ultimo["ratio_cba"])
            if ultimo["CMP CFP"]:
                _metric_card(
                    cols[1],
                    "CMP / CBA",
                    ultimo["CMP CFP"] / ultimo["CBA INIDEP"] if ultimo["CBA INIDEP"] else None,
                )
            if ultimo["CMP CFP"] and ultimo["Captura real"]:
                _metric_card(
                    cols[2],
                    "Captura real / CMP",
                    ultimo["Captura real"] / ultimo["CMP CFP"],
                )

# ── Tab 2: Series temporales ──────────────────────────────────────────────────

with tab2:
    st.subheader("Evolución histórica de capturas por especie")

    especies_multi = st.multiselect(
        "Especies a comparar",
        options=sorted(df_capturas["especie_code"].unique()),
        default=["merluza_hubbsi", "langostino"],
        format_func=lambda x: x.replace("_", " ").title(),
    )

    if especies_multi:
        fig2 = go.Figure()
        for code in especies_multi:
            df_e = df_capturas[df_capturas["especie_code"] == code].sort_values("year")
            fig2.add_trace(
                go.Scatter(
                    name=code.replace("_", " ").title(),
                    x=df_e["year"],
                    y=df_e["captura_tn"],
                    mode="lines+markers",
                    marker={"size": 7},
                )
            )

        fig2.update_layout(
            title="Capturas reales por especie — Serie histórica",
            yaxis_title="Toneladas desembarcadas",
            height=400,
            legend={"orientation": "h", "y": -0.2},
        )
        st.plotly_chart(fig2, use_container_width=True)

    st.divider()
    st.subheader("Variación interanual")

    especie_var = st.selectbox(
        "Especie para variación",
        options=sorted(df_capturas["especie_code"].unique()),
        format_func=lambda x: x.replace("_", " ").title(),
        key="var_especie",
    )
    df_var = df_capturas[df_capturas["especie_code"] == especie_var].sort_values("year").copy()
    if len(df_var) >= 2:
        df_var["variacion_pct"] = df_var["captura_tn"].pct_change() * 100
        fig3 = go.Figure(
            go.Bar(
                x=df_var["year"],
                y=df_var["variacion_pct"],
                marker_color=[
                    "#2E7D32" if v >= 0 else "#C62828" for v in df_var["variacion_pct"].fillna(0)
                ],
            )
        )
        fig3.update_layout(
            title=f"Variación interanual — {especie_var.replace('_', ' ').title()}",
            yaxis_title="Variación %",
            height=300,
        )
        st.plotly_chart(fig3, use_container_width=True)

# ── Tab 3: Alertas ─────────────────────────────────────────────────────────────

with tab3:
    st.subheader("Casos donde la captura real supera la CBA recomendada")
    st.markdown(
        "Estos son los casos más críticos para la sostenibilidad: la presión extractiva efectiva "
        "supera lo que el INIDEP considera biológicamente aceptable, independientemente de lo que "
        "el CFP haya aprobado como CMP."
    )

    if not alertas_activas:
        st.success(
            "✅ No se detectaron capturas que superen la CBA recomendada en los datos disponibles."
        )
    else:
        for t in alertas_activas:
            nivel = t.alerta_captura or "sin_datos"
            bg = ALERTA_BG.get(nivel, "#F5F5F5")
            border = ALERTA_COLORS.get(nivel, "#757575")
            label = ALERTA_LABELS.get(nivel, nivel)

            col1, col2 = st.columns([2, 3])
            with col1:
                st.markdown(
                    f"""<div style="background:{bg};border-left:5px solid {border};
                    padding:12px;border-radius:4px;margin-bottom:8px">
                    <b>{t.especie.title()}</b> — {t.year}<br>
                    <span style="font-size:1.1em">{label}</span>
                    </div>""",
                    unsafe_allow_html=True,
                )
            with col2:
                m1, m2, m3 = st.columns(3)
                m1.metric(
                    "Captura real",
                    f"{t.captura_real_tn:,.0f} tn" if t.captura_real_tn else "—",
                )
                m2.metric(
                    "CBA INIDEP",
                    f"{t.cba_inidep_tn:,.0f} tn" if t.cba_inidep_tn else "—",
                )
                if t.ratio_captura_cba:
                    exceso = (t.ratio_captura_cba - 1) * 100
                    m3.metric(
                        "Exceso sobre CBA",
                        f"{exceso:+.1f}%",
                        delta=f"{exceso:+.1f}%",
                        delta_color="inverse",
                    )

        st.divider()
        st.info(
            "**Metodología**: La alerta se activa cuando la captura real supera el 100% de la CBA "
            "recomendada por INIDEP. Niveles: ⚠️ 100-110% | 🔴 110-130% | 🚨 >130%."
        )

# ── Tab 4: Datos completos ────────────────────────────────────────────────────

with tab4:
    st.subheader("Datos completos de capturas")

    col_f1, col_f2 = st.columns(2)
    with col_f1:
        especies_filtro = st.multiselect(
            "Filtrar por especie",
            options=sorted(df_capturas["especie_code"].unique()),
            default=[],
            format_func=lambda x: x.replace("_", " ").title(),
        )
    with col_f2:
        año_range = st.slider(
            "Rango de años",
            min_value=int(df_capturas["year"].min()),
            max_value=int(df_capturas["year"].max()),
            value=(int(df_capturas["year"].min()), int(df_capturas["year"].max())),
        )

    df_show = df_capturas.copy()
    if especies_filtro:
        df_show = df_show[df_show["especie_code"].isin(especies_filtro)]
    df_show = df_show[df_show["year"].between(año_range[0], año_range[1])]

    cols_show = [
        c for c in ["especie", "year", "captura_tn", "fuente", "notas"] if c in df_show.columns
    ]
    st.dataframe(df_show[cols_show], use_container_width=True, hide_index=True)
    st.caption(f"{len(df_show)} registros mostrados")

    csv = df_show.to_csv(index=False)
    st.download_button(
        "⬇️ Descargar CSV",
        data=csv,
        file_name="capturas_reales_sagpya.csv",
        mime="text/csv",
    )

    st.divider()
    st.markdown(
        "**Fuentes**: "
        "[SAGPyA — Estadísticas pesqueras](https://www.magyp.gob.ar/sitio/areas/pesca_maritima/) | "
        "[datos.gob.ar](https://datos.gob.ar/dataset/agroindustria-pesca) | "
        "[CCAMLR](https://www.ccamlr.org) para *D. eleginoides*"
    )
    st.caption(
        "Datos de desembarque de la flota pesquera argentina. "
        "Series 2015–2024. Los valores provisionales pueden ajustarse al cierre del año estadístico."
    )
