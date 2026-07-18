"""
Página de Timeline interactivo: evolución histórica de CBA INIDEP y CMP CFP por especie.
"""

import sqlite3
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(ROOT))

st.title("📈 Timeline Histórico por Especie")
st.caption(
    "Evolución de las evaluaciones INIDEP y cuotas CFP desde 1992 hasta la actualidad. "
    "Fuente: marabierto.inidep.edu.ar — 492 ITOs scrapeados."
)

from src.config_loader import get_db_path
DB_PATH = get_db_path()

if not DB_PATH.exists():
    st.error(
        "Base de datos no encontrada. Ejecuta: `python scripts/scrape_inidep.py --mode metadata`"
    )
    st.stop()

@st.cache_data(ttl=300)
def load_data():
    conn = sqlite3.connect(DB_PATH)
    df_inidep = pd.read_sql_query(
        """
        SELECT especie, especie_code, zona, year,
               cba_recomendada_tn, estado_stock, numero_ito, notas
        FROM inidep_evaluaciones
        WHERE year BETWEEN 1990 AND 2030
        ORDER BY year, especie_code
        """,
        conn,
    )
    df_cfp = pd.read_sql_query(
        """
        SELECT especie, especie_code, zona, year,
               cmp_aprobada_tn, acta_referencia
        FROM cfp_cuotas
        ORDER BY year, especie_code
        """,
        conn,
    )
    conn.close()
    return df_inidep, df_cfp

df_inidep, df_cfp = load_data()

ESPECIE_LABELS = {
    "merluza_hubbsi": "Merluza común (M. hubbsi)",
    "calamar": "Calamar",
    "calamar_illex": "Calamar illex",
    "langostino": "Langostino",
    "centolla": "Centolla",
    "vieira": "Vieira patagónica",
    "anchoíta": "Anchoíta",
    "merluza_negra": "Merluza negra",
    "merluza_de_cola": "Merluza de cola",
    "polaca": "Polaca",
    "abadejo": "Abadejo",
}

ESTADO_COLOR = {
    "sobrexplotado": "#D32F2F",
    "en_recuperacion": "#388E3C",
    "saludable": "#1976D2",
    "precautorio": "#F57C00",
    "incierto": "#757575",
    None: "#9E9E9E",
}

# ── Sidebar ────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.header("Filtros")

    especies_disp = sorted(df_inidep["especie_code"].dropna().unique())
    especies_labels = [ESPECIE_LABELS.get(e, e.replace("_", " ").title()) for e in especies_disp]
    especie_sel = st.selectbox(
        "Especie",
        options=especies_disp,
        format_func=lambda e: ESPECIE_LABELS.get(e, e.replace("_", " ").title()),
        index=especies_disp.index("merluza_hubbsi") if "merluza_hubbsi" in especies_disp else 0,
    )

    year_min = int(df_inidep["year"].min())
    year_max = int(df_inidep["year"].max())
    year_range = st.slider("Período", year_min, year_max, (2010, year_max))

    mostrar_sin_cba = st.checkbox("Incluir ITOs sin CBA numérica", value=True)
    st.divider()
    st.caption(f"Total ITOs en BD: **{len(df_inidep)}**")
    st.caption(f"Especies: **{df_inidep['especie_code'].nunique()}**")
    st.caption(f"Con CBA numérica: **{df_inidep['cba_recomendada_tn'].notna().sum()}**")

# ── Filtrar datos ──────────────────────────────────────────────────────────────

mask = (
    (df_inidep["especie_code"] == especie_sel)
    & (df_inidep["year"] >= year_range[0])
    & (df_inidep["year"] <= year_range[1])
)
df_esp = df_inidep[mask].copy()
df_esp_cfp = df_cfp[
    (df_cfp["especie_code"] == especie_sel)
    & (df_cfp["year"] >= year_range[0])
    & (df_cfp["year"] <= year_range[1])
].copy()

especie_label = ESPECIE_LABELS.get(especie_sel, especie_sel.replace("_", " ").title())

# ── Métricas rápidas ───────────────────────────────────────────────────────────

col1, col2, col3, col4 = st.columns(4)
col1.metric("ITOs encontrados", len(df_esp))
col2.metric("Con CBA numérica", df_esp["cba_recomendada_tn"].notna().sum())
col3.metric(
    "Período cubierto",
    f"{int(df_esp['year'].min())}–{int(df_esp['year'].max())}" if len(df_esp) else "—",
)
col4.metric("Cuotas CFP registradas", len(df_esp_cfp))

st.divider()

# ── Tabs ───────────────────────────────────────────────────────────────────────

tab_timeline, tab_heatmap, tab_actividad, tab_datos = st.tabs(
    [
        "📊 Timeline CBA vs. CFP",
        "🗓️ Mapa de actividad",
        "🐠 Actividad por especie",
        "📋 Datos",
    ]
)

# ── Tab 1: Timeline CBA vs. CMP ───────────────────────────────────────────────

with tab_timeline:
    df_cba = df_esp[df_esp["cba_recomendada_tn"].notna()].copy()

    if df_cba.empty and df_esp_cfp.empty:
        st.info(
            f"No hay datos numéricos de CBA o CMP para **{especie_label}** "
            f"en el período {year_range[0]}–{year_range[1]}. "
            "Usa el modo `--mode full` del scraper para extraer CBA desde PDFs, "
            "o registra cuotas CFP en la página INIDEP Comparador."
        )
        if not df_esp.empty and mostrar_sin_cba:
            st.subheader("Evaluaciones INIDEP (sin CBA numérica)")
            st.dataframe(
                df_esp[["year", "zona", "numero_ito", "estado_stock", "notas"]].rename(
                    columns={
                        "year": "Año",
                        "zona": "Zona",
                        "numero_ito": "ITO",
                        "estado_stock": "Estado",
                        "notas": "Notas",
                    }
                ),
                use_container_width=True,
                hide_index=True,
            )
    else:
        fig = go.Figure()

        # CBA INIDEP — línea azul con marcadores de estado
        if not df_cba.empty:
            df_cba_sorted = df_cba.sort_values("year")
            # Agregar por año (promedio si hay varios registros)
            df_cba_agg = (
                df_cba_sorted.groupby("year")
                .agg(
                    cba=("cba_recomendada_tn", "mean"),
                    estado=("estado_stock", "first"),
                    ito=("numero_ito", "first"),
                )
                .reset_index()
            )

            fig.add_trace(
                go.Scatter(
                    x=df_cba_agg["year"],
                    y=df_cba_agg["cba"],
                    name="CBA INIDEP (recomendada)",
                    mode="lines+markers",
                    line=dict(color="#1976D2", width=2.5),
                    marker=dict(
                        size=10,
                        color=[ESTADO_COLOR.get(e, "#9E9E9E") for e in df_cba_agg["estado"]],
                        line=dict(color="white", width=1.5),
                    ),
                    customdata=df_cba_agg[["estado", "ito"]],
                    hovertemplate=(
                        "<b>%{x}</b><br>"
                        "CBA: %{y:,.0f} tn<br>"
                        "Estado: %{customdata[0]}<br>"
                        "ITO: %{customdata[1]}<extra></extra>"
                    ),
                )
            )

        # CMP CFP — barras rojas semitransparentes
        if not df_esp_cfp.empty:
            df_cfp_agg = (
                df_esp_cfp.groupby("year")
                .agg(
                    cmp=("cmp_aprobada_tn", "sum"),
                    acta=("acta_referencia", "first"),
                )
                .reset_index()
            )
            fig.add_trace(
                go.Bar(
                    x=df_cfp_agg["year"],
                    y=df_cfp_agg["cmp"],
                    name="CMP CFP (aprobada)",
                    marker_color="rgba(211, 47, 47, 0.55)",
                    customdata=df_cfp_agg[["acta"]],
                    hovertemplate=(
                        "<b>%{x}</b><br>"
                        "CMP aprobada: %{y:,.0f} tn<br>"
                        "Acta: %{customdata[0]}<extra></extra>"
                    ),
                )
            )

        # Leyenda de estados
        for estado, color in ESTADO_COLOR.items():
            if estado and not df_cba.empty and estado in df_cba["estado_stock"].values:
                fig.add_trace(
                    go.Scatter(
                        x=[None],
                        y=[None],
                        mode="markers",
                        marker=dict(size=8, color=color),
                        name=estado.replace("_", " ").title(),
                        showlegend=True,
                    )
                )

        fig.update_layout(
            title=f"{especie_label} — CBA INIDEP vs. CMP CFP ({year_range[0]}–{year_range[1]})",
            xaxis_title="Año",
            yaxis_title="Toneladas",
            barmode="overlay",
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
            height=480,
            hovermode="x unified",
        )
        st.plotly_chart(fig, use_container_width=True)

        # Tabla de referencia rápida
        if not df_cba.empty:
            with st.expander("Ver datos de CBA por año"):
                st.dataframe(
                    df_cba[
                        ["year", "zona", "cba_recomendada_tn", "estado_stock", "numero_ito"]
                    ].rename(
                        columns={
                            "year": "Año",
                            "zona": "Zona",
                            "cba_recomendada_tn": "CBA (tn)",
                            "estado_stock": "Estado stock",
                            "numero_ito": "ITO",
                        }
                    ),
                    use_container_width=True,
                    hide_index=True,
                )

# ── Tab 2: Mapa de actividad (heatmap especie × año) ──────────────────────────

with tab_heatmap:
    st.subheader("Intensidad de evaluaciones INIDEP por especie y año")

    pivot = df_inidep[
        (df_inidep["year"] >= year_range[0]) & (df_inidep["year"] <= year_range[1])
    ].pivot_table(
        index="especie_code",
        columns="year",
        values="cba_recomendada_tn",
        aggfunc="count",
        fill_value=0,
    )

    if pivot.empty:
        st.info("Sin datos en el período seleccionado.")
    else:
        pivot.index = [ESPECIE_LABELS.get(e, e) for e in pivot.index]

        fig_heat = px.imshow(
            pivot,
            labels=dict(x="Año", y="Especie", color="Nº ITOs"),
            color_continuous_scale="Blues",
            title="Número de ITOs por especie y año",
            aspect="auto",
        )
        fig_heat.update_layout(height=420)
        st.plotly_chart(fig_heat, use_container_width=True)

    # CBA disponibles por especie (barra horizontal)
    st.subheader("ITOs con CBA numérica disponible")
    cba_por_esp = (
        df_inidep[df_inidep["cba_recomendada_tn"].notna()]
        .groupby("especie_code")
        .size()
        .reset_index(name="count")
        .sort_values("count", ascending=True)
    )
    if not cba_por_esp.empty:
        cba_por_esp["especie_label"] = cba_por_esp["especie_code"].map(
            lambda e: ESPECIE_LABELS.get(e, e)
        )
        fig_bar = px.bar(
            cba_por_esp,
            x="count",
            y="especie_label",
            orientation="h",
            title="ITOs con valor de CBA extraído (abstract o PDF)",
            labels={"count": "Cantidad ITOs", "especie_label": ""},
            color="count",
            color_continuous_scale="Teal",
        )
        fig_bar.update_layout(height=350, showlegend=False)
        st.plotly_chart(fig_bar, use_container_width=True)

# ── Tab 3: Actividad total por especie ────────────────────────────────────────

with tab_actividad:
    st.subheader("Total de evaluaciones INIDEP por especie")

    df_act = df_inidep[
        (df_inidep["year"] >= year_range[0]) & (df_inidep["year"] <= year_range[1])
    ].copy()

    total_por_esp = (
        df_act.groupby("especie_code")
        .agg(
            total=("especie_code", "count"),
            con_cba=("cba_recomendada_tn", lambda x: x.notna().sum()),
            ultimo_año=("year", "max"),
            primer_año=("year", "min"),
        )
        .reset_index()
        .sort_values("total", ascending=False)
    )
    total_por_esp["especie_label"] = total_por_esp["especie_code"].map(
        lambda e: ESPECIE_LABELS.get(e, e)
    )
    total_por_esp["cobertura_cba"] = (
        total_por_esp["con_cba"] / total_por_esp["total"] * 100
    ).round(1)

    fig_donut = px.bar(
        total_por_esp,
        x="especie_label",
        y="total",
        color="cobertura_cba",
        color_continuous_scale="RdYlGn",
        range_color=(0, 100),
        title=f"ITOs por especie — color = % con CBA numérica ({year_range[0]}–{year_range[1]})",
        labels={"total": "Nº ITOs", "especie_label": "", "cobertura_cba": "% con CBA"},
        text="total",
    )
    fig_donut.update_traces(textposition="outside")
    fig_donut.update_layout(height=420)
    st.plotly_chart(fig_donut, use_container_width=True)

    # Tabla resumen
    st.dataframe(
        total_por_esp[
            ["especie_label", "total", "con_cba", "cobertura_cba", "primer_año", "ultimo_año"]
        ].rename(
            columns={
                "especie_label": "Especie",
                "total": "Total ITOs",
                "con_cba": "Con CBA",
                "cobertura_cba": "% CBA",
                "primer_año": "Primer año",
                "ultimo_año": "Último año",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )

    st.info(
        "La **cobertura de CBA baja** (~6%) se debe a que los valores numéricos están "
        "en el cuerpo de los PDFs, no en los abstracts. Ejecutar el scraper en modo "
        "`--mode full` mejora la cobertura extrayendo texto de cada PDF."
    )

# ── Tab 4: Datos crudos ───────────────────────────────────────────────────────

with tab_datos:
    st.subheader(f"Evaluaciones INIDEP — {especie_label}")

    df_show = df_esp.copy()
    if not mostrar_sin_cba:
        df_show = df_show[df_show["cba_recomendada_tn"].notna()]

    st.dataframe(
        df_show[
            ["year", "zona", "cba_recomendada_tn", "estado_stock", "numero_ito", "notas"]
        ].rename(
            columns={
                "year": "Año",
                "zona": "Zona",
                "cba_recomendada_tn": "CBA (tn)",
                "estado_stock": "Estado stock",
                "numero_ito": "ITO",
                "notas": "Notas",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )

    col_dl1, col_dl2 = st.columns(2)
    col_dl1.download_button(
        "⬇️ Descargar esta especie (CSV)",
        df_show.to_csv(index=False).encode("utf-8"),
        f"inidep_{especie_sel}.csv",
        "text/csv",
    )

    df_all = df_inidep[(df_inidep["year"] >= year_range[0]) & (df_inidep["year"] <= year_range[1])]
    col_dl2.download_button(
        "⬇️ Descargar todas las especies (CSV)",
        df_all.to_csv(index=False).encode("utf-8"),
        f"inidep_todas_{year_range[0]}_{year_range[1]}.csv",
        "text/csv",
    )
