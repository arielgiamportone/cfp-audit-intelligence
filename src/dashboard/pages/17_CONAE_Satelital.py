"""
Página 17 — CONAE Geoportal Marino: Esfuerzo Pesquero Satelital

Visualiza datos satelitales del geoportal marino de la CONAE (ADR-010):
  - Esfuerzo pesquero GFW AIS (proxy de actividad real)
  - SST y clorofila-a por zona de muestreo
  - Comparación de esfuerzo dentro vs. fuera de períodos de veda
    (4° vértice del triángulo de auditoría — evidencia independiente del corpus)

Fuente: CONAE Geoportal Marino (WMS GetFeatureInfo, datos públicos).
Esfuerzo: Global Fishing Watch AIS (Kroodsma et al. 2018, Science).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from src.acquisition.conae_marine_scraper import ZONAS_MUESTRA, CONAEMarineClient, get_esfuerzo_df
from src.analysis.geovisor_cross_validator import GeovisorCrossValidator

from src.config_loader import get_db_path
DB_PATH = get_db_path()
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

from src.dashboard._ui import page_header_raw
page_header_raw("🛰️ CONAE — Esfuerzo Pesquero Satelital", "Datos satelitales del geoportal marino de la CONAE. "
    "Verifica si el esfuerzo pesquero real (GFW AIS) disminuye durante períodos de veda "
    "— evidencia independiente del corpus de actas CFP (ADR-010).")

# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.header("Configuración")
    if st.button("📡 Muestrear datos CONAE (hoy)"):
        with st.spinner(
            "Consultando WMS geoservicios2.conae.gov.ar — puede tardar ~2 min..."
        ):
            try:
                client = CONAEMarineClient(delay=0.5)
                n = client.scrape_and_save(DB_PATH)
                st.cache_data.clear()
                if n > 0:
                    st.success(f"{n} nuevos registros satelitales guardados.")
                else:
                    st.info("No hay registros nuevos (ya muestreado hoy).")
            except Exception as exc:  # noqa: BLE001
                st.error(f"Error al consultar CONAE: {exc}")

    st.divider()
    st.info(
        "**Nota metodológica (ADR-010)**\n\n"
        "El WMS CONAE sirve composites recientes (~8 períodos rolling). "
        "La serie temporal se construye ejecutando el muestreo periódicamente.\n\n"
        "**Limitaciones:**\n"
        "- Muestreo puntual (centroides), no poligonal\n"
        "- GFW AIS no detecta flotas sin transponder\n"
        "- Sin consulta histórica directa"
    )
    st.markdown("**Fuente:** [CONAE Geoportal Marino](https://geoportal.conae.gov.ar)")

# ── Carga de datos ────────────────────────────────────────────────────────────

@st.cache_data(ttl=120)
def _cargar_datos() -> pd.DataFrame:
    return get_esfuerzo_df(DB_PATH) or pd.DataFrame()

df = _cargar_datos()

# ── Panel sin datos ───────────────────────────────────────────────────────────

if df.empty:
    st.info(
        "No hay datos satelitales disponibles aún. "
        'Usá el botón "📡 Muestrear datos CONAE (hoy)" en la barra lateral para '
        "consultar el geoportal CONAE y registrar el primer muestreo."
    )

    # Mostrar mapa de zonas de muestreo planificadas aunque no haya datos
    st.subheader("Zonas de muestreo planificadas")
    zonas_df = pd.DataFrame(ZONAS_MUESTRA)
    try:
        import plotly.express as px

        fig = px.scatter_geo(
            zonas_df,
            lat="lat",
            lon="lon",
            text="zona",
            color="especie_code",
            title="Centroides de zonas de muestreo CONAE (ZEE argentina)",
            scope="south america",
        )
        fig.update_traces(textposition="top center", marker_size=12)
        fig.update_layout(height=500)
        st.plotly_chart(fig, use_container_width=True)
    except ImportError:
        st.dataframe(zonas_df)
    st.stop()

# ── Tabs con datos ────────────────────────────────────────────────────────────

tab_mapa, tab_sst, tab_clorofila, tab_esfuerzo, tab_veda = st.tabs(
    ["🗺️ Mapa de zonas", "🌡️ SST", "🟢 Clorofila", "🚢 Esfuerzo GFW", "⚖️ Veda vs. Esfuerzo"]
)

# ── Tab 1: Mapa ───────────────────────────────────────────────────────────────

with tab_mapa:
    st.subheader("Zonas de muestreo con datos disponibles")
    ultimo_por_zona = df.sort_values("fecha").groupby("zona").last().reset_index()

    try:
        import plotly.express as px

        fig = px.scatter_geo(
            ultimo_por_zona,
            lat="lat",
            lon="lon",
            text="zona",
            color="especie_code",
            hover_data=["fecha", "esfuerzo_gfw", "sst", "clorofila"],
            title="Último muestreo por zona (geoportal CONAE)",
            scope="south america",
        )
        fig.update_traces(textposition="top center", marker_size=14)
        fig.update_layout(height=520)
        st.plotly_chart(fig, use_container_width=True)
    except ImportError:
        st.dataframe(ultimo_por_zona)

    n_zonas = df["zona"].nunique()
    n_fechas = df["fecha"].nunique()
    col1, col2, col3 = st.columns(3)
    col1.metric("Zonas muestreadas", n_zonas)
    col2.metric("Fechas de muestreo", n_fechas)
    col3.metric("Registros totales", len(df))

# ── Tab 2: SST ────────────────────────────────────────────────────────────────

with tab_sst:
    st.subheader("Temperatura superficial del mar (SST) — VIIRS/SNPP")
    df_sst = df[df["sst"].notna()].copy()

    if df_sst.empty:
        st.info("Sin datos SST disponibles todavía.")
    else:
        try:
            import plotly.express as px

            fig = px.line(
                df_sst.sort_values("fecha"),
                x="fecha",
                y="sst",
                color="zona",
                markers=True,
                labels={"sst": "SST diurna (°C)", "fecha": "Fecha"},
                title="Evolución de la SST diurna por zona de muestreo",
            )
            st.plotly_chart(fig, use_container_width=True)

            if df["sst_noche"].notna().any():
                fig2 = px.line(
                    df[df["sst_noche"].notna()].sort_values("fecha"),
                    x="fecha",
                    y="sst_noche",
                    color="zona",
                    markers=True,
                    labels={"sst_noche": "SST nocturna (°C)", "fecha": "Fecha"},
                    title="SST nocturna por zona",
                )
                st.plotly_chart(fig2, use_container_width=True)
        except ImportError:
            st.dataframe(df_sst[["zona", "fecha", "sst", "sst_noche"]])

# ── Tab 3: Clorofila ──────────────────────────────────────────────────────────

with tab_clorofila:
    st.subheader("Concentración de clorofila-a — VIIRS/SNPP")
    df_chla = df[df["clorofila"].notna() | df["clorofila_8d"].notna()].copy()

    if df_chla.empty:
        st.info("Sin datos de clorofila disponibles todavía.")
    else:
        try:
            import plotly.express as px

            col_usar = "clorofila_8d" if df_chla["clorofila_8d"].notna().sum() >= df_chla["clorofila"].notna().sum() else "clorofila"
            label_chla = "Chl-a 8d (mg/m³)" if col_usar == "clorofila_8d" else "Chl-a diaria (mg/m³)"

            fig = px.line(
                df_chla[df_chla[col_usar].notna()].sort_values("fecha"),
                x="fecha",
                y=col_usar,
                color="zona",
                markers=True,
                labels={col_usar: label_chla, "fecha": "Fecha"},
                title=f"Evolución de clorofila-a ({label_chla}) por zona",
            )
            st.plotly_chart(fig, use_container_width=True)
        except ImportError:
            st.dataframe(df_chla[["zona", "fecha", "clorofila", "clorofila_8d"]])

# ── Tab 4: Esfuerzo GFW ───────────────────────────────────────────────────────

with tab_esfuerzo:
    st.subheader("Esfuerzo pesquero GFW AIS — horas de pesca por km²")
    df_gfw = df[df["esfuerzo_gfw"].notna()].copy()

    if df_gfw.empty:
        st.info("Sin datos de esfuerzo GFW disponibles todavía.")
    else:
        try:
            import plotly.express as px

            fig = px.line(
                df_gfw.sort_values("fecha"),
                x="fecha",
                y="esfuerzo_gfw",
                color="zona",
                markers=True,
                labels={"esfuerzo_gfw": "Esfuerzo GFW (h/km²)", "fecha": "Fecha"},
                title="Esfuerzo pesquero GFW AIS por zona (Global Fishing Watch)",
            )
            st.plotly_chart(fig, use_container_width=True)

            st.caption(
                "Fuente: Global Fishing Watch — Kroodsma et al. (2018). "
                "Tracking the global footprint of fisheries. *Science* 359(6378), 904–908. "
                "Servido por el geoportal CONAE."
            )
        except ImportError:
            st.dataframe(df_gfw[["zona", "fecha", "esfuerzo_gfw"]])

        st.subheader("Esfuerzo promedio por zona (todos los muestreos)")
        resumen_zona = (
            df_gfw.groupby("zona")["esfuerzo_gfw"]
            .agg(["mean", "median", "count"])
            .reset_index()
            .rename(columns={"mean": "Promedio", "median": "Mediana", "count": "N muestreos"})
        )
        st.dataframe(resumen_zona, use_container_width=True)

# ── Tab 5: Veda vs. Esfuerzo ──────────────────────────────────────────────────

with tab_veda:
    st.subheader("Verificación satelital de cumplimiento de vedas")
    st.markdown(
        "Compara el esfuerzo GFW AIS durante períodos de veda activa (según "
        "`vedas_geoespaciales` del geovisor SERE/INIDEP) contra el esfuerzo fuera de veda. "
        "Una reducción significativa es evidencia de cumplimiento regulatorio."
    )

    try:
        validator = GeovisorCrossValidator(DB_PATH)
        resultado = validator.validar_cumplimiento_satelital()
    except Exception as exc:  # noqa: BLE001
        st.error(f"Error en validación: {exc}")
        st.stop()

    if "error" in resultado:
        st.warning(resultado["error"])
    else:
        col1, col2, col3 = st.columns(3)
        col1.metric(
            "Mediana esfuerzo DENTRO de veda",
            f"{resultado['mediana_esfuerzo_dentro']:.2f} h/km²"
            if resultado["mediana_esfuerzo_dentro"] is not None
            else "N/D",
        )
        col2.metric(
            "Mediana esfuerzo FUERA de veda",
            f"{resultado['mediana_esfuerzo_fuera']:.2f} h/km²"
            if resultado["mediana_esfuerzo_fuera"] is not None
            else "N/D",
        )
        ratio = resultado.get("ratio_reduccion")
        col3.metric(
            "Ratio dentro/fuera",
            f"{ratio:.2f}" if ratio is not None else "N/D",
            delta=f"{(ratio - 1) * 100:.0f}%" if ratio is not None else None,
            delta_color="inverse",
        )

        st.info(resultado["interpretacion"])

        if resultado.get("mannwhitney_pvalue") is not None:
            pval = resultado["mannwhitney_pvalue"]
            if pval < 0.05:
                st.success(f"Mann-Whitney U p={pval} — diferencia estadísticamente significativa.")
            else:
                st.warning(f"Mann-Whitney U p={pval} — diferencia no significativa (α=0.05).")

        col_n1, col_n2 = st.columns(2)
        col_n1.metric("Observaciones dentro de veda", resultado["n_dentro_veda"])
        col_n2.metric("Observaciones fuera de veda", resultado["n_fuera_veda"])

        if resultado["n_dentro_veda"] < 3 or resultado["n_fuera_veda"] < 3:
            st.caption(
                "⚠️ Pocos datos para análisis robusto. "
                "Ejecutar muestreo CONAE periódicamente para acumular serie temporal."
            )

        try:
            import plotly.express as px

            df_gfw_comp = df[df["esfuerzo_gfw"].notna()].copy()
            if not df_gfw_comp.empty:
                df_gfw_comp["periodo"] = "Sin datos de veda"
                st.subheader("Distribución del esfuerzo GFW por zona")
                fig = px.box(
                    df_gfw_comp,
                    x="zona",
                    y="esfuerzo_gfw",
                    color="especie_code",
                    title="Distribución del esfuerzo GFW por zona de muestreo",
                    labels={"esfuerzo_gfw": "Esfuerzo GFW (h/km²)", "zona": "Zona"},
                )
                fig.update_xaxes(tickangle=30)
                st.plotly_chart(fig, use_container_width=True)
        except ImportError:
            pass
