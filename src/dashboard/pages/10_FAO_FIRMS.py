"""Página 10 — Contexto Internacional FAO FIRMS."""

from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.acquisition.fao_firms_scraper import (
    ESPECIE_FAO_CODES,
    FAOFIRMSScraper,
    estado_stock_color,
)

st.set_page_config(page_title="FAO FIRMS — Contexto Internacional", page_icon="🌎", layout="wide")
st.title("🌎 Contexto Internacional FAO FIRMS")
st.markdown(
    "Capturas globales y estado de stocks en el **Área FAO 41 — Atlántico Sudoccidental**. "
    "Compara las cuotas CFP con la situación internacional de cada especie."
)

from src.config_loader import get_db_path
DB_PATH = get_db_path()

# ── Inicializar datos ─────────────────────────────────────────────────────────

@st.cache_resource(show_spinner="Cargando datos FAO FIRMS...")
def get_scraper():
    s = FAOFIRMSScraper(db_path=DB_PATH)
    s.seed_data()
    return s


scraper = get_scraper()
df_capturas = scraper.get_capturas_df()
df_status = scraper.get_stock_status_df()

if df_capturas.empty:
    st.warning("No hay datos FAO. Verifica la base de datos.")
    st.stop()

# ── Tabs ──────────────────────────────────────────────────────────────────────

tab1, tab2, tab3 = st.tabs([
    "📊 Capturas — Argentina vs. Mundo",
    "🚦 Estado de Stocks",
    "📋 Datos completos",
])

# ── Tab 1: Capturas ───────────────────────────────────────────────────────────

with tab1:
    st.subheader("Participación de Argentina en la Captura Total (Área FAO 41)")
    st.markdown(
        "Para la mayoría de las especies explotadas por el CFP, Argentina es el **productor "
        "dominante** en el Atlántico Sudoccidental. La comparación con el total del área "
        "permite evaluar la relevancia internacional de las decisiones del CFP."
    )

    # Share Argentina por especie
    df_arg = df_capturas[df_capturas["pais"] == "Argentina"].copy()
    df_total = df_capturas[df_capturas["pais"] == "Total"].copy()

    if not df_arg.empty and not df_total.empty:
        # Último año disponible por especie
        df_arg_last = df_arg.sort_values("year").groupby("especie").last().reset_index()
        df_total_last = df_total.sort_values("year").groupby("especie").last().reset_index()
        df_merge = df_arg_last.merge(
            df_total_last[["especie", "captura_tn"]],
            on="especie",
            suffixes=("_arg", "_total"),
        )
        df_merge["share_pct"] = (df_merge["captura_tn_arg"] / df_merge["captura_tn_total"] * 100).round(1)

        # Gráfico de barras stacked: Argentina vs Resto del mundo
        df_merge["resto_tn"] = df_merge["captura_tn_total"] - df_merge["captura_tn_arg"]

        fig = go.Figure()
        fig.add_trace(go.Bar(
            name="Argentina",
            x=df_merge["especie"],
            y=df_merge["captura_tn_arg"],
            marker_color="#1565C0",
            text=df_merge["captura_tn_arg"].apply(lambda x: f"{x:,.0f} tn"),
            textposition="inside",
        ))
        fig.add_trace(go.Bar(
            name="Resto del Área 41",
            x=df_merge["especie"],
            y=df_merge["resto_tn"],
            marker_color="#90CAF9",
            text=df_merge["resto_tn"].apply(lambda x: f"{x:,.0f} tn"),
            textposition="inside",
        ))
        fig.update_layout(
            barmode="stack",
            title="Captura Total Área FAO 41 — Último año disponible",
            yaxis_title="Toneladas",
            height=420,
            legend={"orientation": "h", "y": -0.15},
        )
        st.plotly_chart(fig, use_container_width=True)

        # Cards de share por especie
        st.markdown("**Participación de Argentina en Área FAO 41:**")
        cols = st.columns(min(len(df_merge), 4))
        for i, row in df_merge.iterrows():
            share = row["share_pct"]
            color = "🔵" if share > 80 else ("🟡" if share > 50 else "🟠")
            cols[i % 4].metric(
                label=row["especie"].title(),
                value=f"{share:.0f}%",
                help=f"Argentina: {row['captura_tn_arg']:,.0f} tn | Total: {row['captura_tn_total']:,.0f} tn",
            )
            cols[i % 4].caption(f"{color} {row['year']} | {row['captura_tn_arg']:,.0f} tn")

    st.divider()

    # Serie temporal por especie
    st.subheader("Serie temporal de capturas")
    especies_disp = df_arg["especie"].unique().tolist()
    especie_sel = st.selectbox("Especie", options=sorted(especies_disp))

    if especie_sel:
        df_esp_arg = df_arg[df_arg["especie"] == especie_sel]
        df_esp_total = df_total[df_total["especie"] == especie_sel]

        fig2 = go.Figure()
        if not df_esp_total.empty:
            fig2.add_trace(go.Bar(
                name="Total Área 41",
                x=df_esp_total["year"],
                y=df_esp_total["captura_tn"],
                marker_color="#E3F2FD",
                marker_line_color="#1565C0",
                marker_line_width=1,
            ))
        fig2.add_trace(go.Bar(
            name="Argentina",
            x=df_esp_arg["year"],
            y=df_esp_arg["captura_tn"],
            marker_color="#1565C0",
        ))

        # Overlay: línea de cuota CFP si hay datos
        if DB_PATH.exists():
            try:
                import sqlite3
                fao_code = next(
                    (v["fao_code"] for k, v in ESPECIE_FAO_CODES.items()
                     if especie_sel in k or k in especie_sel.lower().replace(" ", "_")),
                    None,
                )
                if fao_code:
                    conn = sqlite3.connect(DB_PATH)
                    df_cfp = pd.read_sql_query(
                        "SELECT year, cmp_aprobada_tn FROM cfp_cuotas WHERE especie_code LIKE ?",
                        conn,
                        params=[f"%{especie_sel.split()[0]}%"],
                    )
                    conn.close()
                    if not df_cfp.empty:
                        fig2.add_trace(go.Scatter(
                            name="CMP aprobada CFP",
                            x=df_cfp["year"],
                            y=df_cfp["cmp_aprobada_tn"],
                            mode="lines+markers",
                            line={"color": "#E65100", "width": 2, "dash": "dot"},
                        ))
            except Exception:
                pass

        fig2.update_layout(
            barmode="overlay",
            title=f"Capturas de {especie_sel.title()} — Área FAO 41",
            yaxis_title="Toneladas",
            height=380,
        )
        st.plotly_chart(fig2, use_container_width=True)


# ── Tab 2: Estado de Stocks ───────────────────────────────────────────────────

with tab2:
    st.subheader("Estado de Stocks — Evaluación FAO FIRMS")
    st.markdown(
        "El estado de cada stock según la evaluación FAO FIRMS para el Área 41. "
        "Una especie clasificada como **Sobrexplotada (O)** por la FAO debería llevar "
        "a cuotas reducidas, no aumentadas, por parte del CFP."
    )

    if df_status.empty:
        st.info("No hay datos de estado de stock disponibles.")
    else:
        # Grid de tarjetas por especie
        status_colors_hex = {
            "verde": "#E8F5E9",
            "amarillo": "#FFF9C4",
            "rojo": "#FFEBEE",
            "critico": "#FCE4EC",
            "gris": "#F5F5F5",
        }
        status_border = {
            "verde": "#2E7D32",
            "amarillo": "#F57F17",
            "rojo": "#C62828",
            "critico": "#880E4F",
            "gris": "#757575",
        }

        cols = st.columns(3)
        for i, row in df_status.iterrows():
            color_key = estado_stock_color(row["estado_stock"])
            bg = status_colors_hex.get(color_key, "#F5F5F5")
            border = status_border.get(color_key, "#757575")
            with cols[i % 3]:
                st.markdown(
                    f"""<div style="background:{bg};border-left:4px solid {border};
                    padding:10px;border-radius:4px;margin-bottom:8px">
                    <b>{row['especie'].title()}</b> ({row['especie_fao_code']})<br>
                    <span style="font-size:1.2em"><b>{row['estado_stock_desc']}</b></span>
                    {f"<br>📈 Tendencia: {row['tendencia']}" if row.get('tendencia') else ""}
                    {f"<br><small>Evaluación: {row['year_evaluacion']}</small>" if row.get('year_evaluacion') else ""}
                    </div>""",
                    unsafe_allow_html=True,
                )

        st.divider()

        # Tabla detallada
        st.markdown("**Detalle de evaluaciones:**")
        cols_show = [
            c for c in ["especie", "estado_stock", "estado_stock_desc", "tendencia",
                        "year_evaluacion", "fuente", "notas"]
            if c in df_status.columns
        ]
        st.dataframe(df_status[cols_show], use_container_width=True, hide_index=True)

        st.info(
            "**Leyenda FAO FIRMS**: F = Plena explotación | O = Sobrexplotado | "
            "U = Subexplotado | R = En recuperación | D = Agotado"
        )

        # Alerta si alguna especie sobrexplotada tiene cuotas altas
        sobreexp = df_status[df_status["estado_stock"].isin(["O", "D"])]
        if not sobreexp.empty:
            st.warning(
                f"⚠️ **{len(sobreexp)} especie(s) clasificadas como Sobrexplotadas o Agotadas** "
                f"según FAO FIRMS: {', '.join(sobreexp['especie'].str.title())}. "
                "Las cuotas CFP para estas especies deberían revisarse con especial atención."
            )


# ── Tab 3: Datos completos ────────────────────────────────────────────────────

with tab3:
    st.subheader("Datos completos FAO")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Capturas (FAO FishStat)**")
        if not df_capturas.empty:
            st.dataframe(
                df_capturas.drop(columns=["id", "created_at"], errors="ignore"),
                use_container_width=True,
                hide_index=True,
            )
            csv_cap = df_capturas.to_csv(index=False)
            st.download_button(
                "⬇️ Descargar capturas CSV",
                data=csv_cap,
                file_name="fao_capturas.csv",
                mime="text/csv",
            )

    with col2:
        st.markdown("**Estado de stocks (FAO FIRMS)**")
        if not df_status.empty:
            st.dataframe(
                df_status.drop(columns=["id", "created_at"], errors="ignore"),
                use_container_width=True,
                hide_index=True,
            )
            csv_st = df_status.to_csv(index=False)
            st.download_button(
                "⬇️ Descargar estados CSV",
                data=csv_st,
                file_name="fao_stock_status.csv",
                mime="text/csv",
            )

    st.divider()
    st.markdown(
        "**Fuentes**: "
        "[FAO FishStat — Global Capture Production](https://www.fao.org/fishery/statistics/global-capture-production) | "
        "[FAO FIRMS](https://firms.fao.org) | "
        "[CCAMLR](https://www.ccamlr.org) para *D. eleginoides*"
    )
    st.caption(
        "Datos de captura: FAO FishStat J 2024. Área FAO 41 — Atlántico Sudoccidental. "
        "Los valores de Argentina incluyen flota de bandera argentina. "
        "El calamar Illex incluye capturas de flotas de pesca en alta mar (China, Corea del Sur, España)."
    )
