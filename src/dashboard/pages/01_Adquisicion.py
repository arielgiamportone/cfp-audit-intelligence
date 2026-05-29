"""
Página de Adquisición: descarga masiva de actas del CFP.
"""

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(ROOT))

st.set_page_config(page_title="Adquisición | CFP Audit", page_icon="📥", layout="wide")
st.title("📥 Adquisición de Actas")
st.caption("Scraping y descarga masiva de PDFs del Consejo Federal Pesquero")

# ── Configuración ─────────────────────────────────────────────────────────────

from src.acquisition.batch_scraper import CFPScraper
from src.acquisition.catalog_manager import CatalogManager

RAW_DIR = ROOT / "data" / "raw"
DB_PATH = ROOT / "data" / "processed" / "catalog.db"

catalog = CatalogManager(DB_PATH)

# ── Estado actual ─────────────────────────────────────────────────────────────

st.subheader("Estado del Catálogo")
stats = catalog.stats()

cols = st.columns(4)
cols[0].metric("Total catalogadas", stats["total"])
cols[1].metric("Descargadas", stats["downloaded"])
cols[2].metric("Años con datos", len(stats["by_year"]))
cols[3].metric("Pendientes", stats["total"] - stats["downloaded"])

st.markdown("---")

# ── Panel de control ──────────────────────────────────────────────────────────

st.subheader("Panel de Descarga")

col_left, col_right = st.columns([1, 2])

with col_left:
    st.markdown("**Configuración**")
    year_from = st.number_input("Año desde", min_value=1998, max_value=2025, value=2020)
    year_to = st.number_input("Año hasta", min_value=1998, max_value=2025, value=2025)
    delay = st.slider("Delay entre requests (seg)", 0.5, 5.0, 1.5, step=0.5)
    only_list = st.checkbox("Solo listar (no descargar)", value=False)

with col_right:
    st.markdown("**Actas disponibles por año (según catálogo)**")
    if stats["by_year"]:
        import pandas as pd
        import plotly.express as px

        df_years = pd.DataFrame(
            list(stats["by_year"].items()), columns=["Año", "Cantidad"]
        ).sort_values("Año")
        fig = px.bar(df_years, x="Año", y="Cantidad", color_discrete_sequence=["#0068c9"])
        fig.update_layout(height=250, margin=dict(t=10, b=10))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Sin datos en el catálogo aún. Ejecuta el scraping para poblar.")

st.markdown("---")

if st.button("🚀 Iniciar Scraping y Descarga", type="primary"):
    years = list(range(year_from, year_to + 1))
    scraper = CFPScraper(delay=delay)

    with st.status(
        f"Procesando {len(years)} años ({year_from}–{year_to})...", expanded=True
    ) as status:
        st.write("Obteniendo listado de actas...")
        actas = scraper.scrape_years(years)
        st.write(f"Encontradas {len(actas)} actas en total")

        # Catalogar
        for acta in actas:
            catalog.upsert_acta(
                {
                    "year": acta.year,
                    "nombre": acta.nombre,
                    "url": acta.url,
                    "filename": acta.filename,
                    "is_anexo": acta.is_anexo,
                }
            )

        if not only_list:
            st.write("Descargando PDFs...")
            stats_dl = scraper.bulk_download(actas, RAW_DIR)

            # Marcar descargadas en catálogo
            for acta in actas:
                if acta.download_status == "ok" and acta.local_path:
                    catalog.mark_downloaded(acta.url, acta.local_path)

            status.update(
                label=(
                    f"Completado: {stats_dl['ok']} nuevos, "
                    f"{stats_dl['duplicate']} existentes, "
                    f"{stats_dl['error']} errores"
                ),
                state="complete",
            )
        else:
            status.update(
                label=f"Listado completado: {len(actas)} actas catalogadas", state="complete"
            )

    st.rerun()
