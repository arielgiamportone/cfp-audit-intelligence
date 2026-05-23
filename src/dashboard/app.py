"""
CFP Audit Intelligence – Dashboard Principal

Navegación multipágina:
  1. Inicio      → Estado del sistema y métricas globales
  2. Adquisición → Descarga de actas
  3. Knowledge Base → Búsqueda semántica
  4. Auditoría   → Análisis con IA y patrones
  5. Reportes    → Exportación y visualización
"""
import os
import sys
from pathlib import Path

import streamlit as st

# Asegurar que src esté en el path
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

st.set_page_config(
    page_title="CFP Audit Intelligence",
    page_icon="🐟",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        "About": (
            "**CFP Audit Intelligence Platform** v0.2\n\n"
            "Plataforma de auditoría inteligente del Consejo Federal Pesquero de Argentina.\n\n"
            "Datos fuente: [cfp.gob.ar](https://cfp.gob.ar/actas-cfp)"
        )
    },
)

# ── Header ────────────────────────────────────────────────────────────────────

st.title("🐟 CFP Audit Intelligence Platform")
st.caption(
    "Auditoría inteligente de las actas del Consejo Federal Pesquero de Argentina (1998–presente)"
)
st.markdown("---")

# ── Métricas de estado del sistema ────────────────────────────────────────────

col1, col2, col3, col4, col5 = st.columns(5)

db_path = ROOT / "data" / "processed" / "catalog.db"

if db_path.exists():
    try:
        from src.acquisition.catalog_manager import CatalogManager
        catalog = CatalogManager(db_path)
        stats = catalog.stats()

        with col1:
            st.metric("Total Actas", stats["total"])
        with col2:
            st.metric("PDFs Descargados", stats["downloaded"])
        with col3:
            st.metric("Textos Extraídos", stats["processed"])
        with col4:
            st.metric("Indexadas en KB", stats["embedded"])
        with col5:
            st.metric("Analizadas con IA", stats["analyzed"])
    except Exception as e:
        with col1:
            st.metric("Catálogo", "No inicializado")
else:
    with col1:
        st.info("Catálogo no inicializado. Ejecuta el pipeline de adquisición.")

st.markdown("---")

# ── Descripción del proyecto ──────────────────────────────────────────────────

col_left, col_right = st.columns([2, 1])

with col_left:
    st.subheader("Objetivo del Proyecto")
    st.markdown("""
    Esta plataforma aplica **Inteligencia Artificial y Ciencia de Datos** al análisis de las
    actas públicas del **Consejo Federal Pesquero (CFP)** para:

    - **Auditar** la toma de decisiones sobre cuotas de captura, permisos y vedas
    - **Detectar patrones** que atenten contra la sostenibilidad de la pesca argentina
    - **Identificar** decisiones subjetivas o contrarias a la normativa (Ley 24.922)
    - **Generar evidencia técnica** reproducible para el debate público y la política pesquera

    > **Marco legal**: Todas las actas son documentos públicos del CFP, organismo creado por
    > la Ley Federal de Pesca N° 24.922.
    """)

with col_right:
    st.subheader("Pipeline de Procesamiento")
    st.markdown("""
    ```
    1. ADQUISICIÓN
       Scraping CFP → PDFs

    2. PROCESAMIENTO
       PDF → Texto → Estructura

    3. KNOWLEDGE BASE
       Embeddings + Vector DB

    4. AUDITORÍA IA
       Claude API + Patrones

    5. REPORTES
       Dashboard + Exportación
    ```
    """)

st.markdown("---")

# ── Acceso rápido ─────────────────────────────────────────────────────────────

st.subheader("Acceso Rápido")

quick_cols = st.columns(4)
with quick_cols[0]:
    st.page_link(
        "pages/01_Adquisicion.py",
        label="📥 Descargar Actas",
        help="Scraping y descarga masiva de PDFs del CFP",
    )
with quick_cols[1]:
    st.page_link(
        "pages/02_Knowledge_Base.py",
        label="🔍 Buscar en Actas",
        help="Búsqueda semántica sobre todas las actas",
    )
with quick_cols[2]:
    st.page_link(
        "pages/03_Auditoria.py",
        label="🧠 Auditoría IA",
        help="Análisis con Claude API y detección de patrones",
    )
with quick_cols[3]:
    st.page_link(
        "pages/04_Reportes.py",
        label="📊 Reportes",
        help="Visualizaciones y exportación de resultados",
    )

# ── Noticias / Últimas actualizaciones ────────────────────────────────────────

st.markdown("---")
st.subheader("Estado del Pipeline")

pipeline_status = {
    "Scraper batch": ("✅ Listo", "Descarga masiva con retry y deduplicación"),
    "Catálogo SQLite": ("✅ Listo", "Trazabilidad completa del pipeline"),
    "Extracción PDF": ("✅ Listo", "pdfplumber + PyMuPDF + OCR Tesseract"),
    "Parser estructural": ("✅ Listo", "Extracción de resoluciones, entidades, cuotas"),
    "Vector Store": ("✅ Listo", "ChromaDB con embeddings multilingües"),
    "Motor de Auditoría IA": ("✅ Listo", "Claude API con prompt caching"),
    "Detector de Patrones": ("✅ Listo", "HHI, votaciones, reversiones"),
    "Dashboard multipágina": ("🔄 En progreso", "Páginas de KB y Auditoría en desarrollo"),
    "Reportes PDF": ("📅 Planificado", "Fase 5 del roadmap"),
}

for component, (status, desc) in pipeline_status.items():
    col_s, col_c, col_d = st.columns([1, 2, 5])
    with col_s:
        st.write(status)
    with col_c:
        st.write(f"**{component}**")
    with col_d:
        st.caption(desc)

st.markdown("---")
st.caption(
    "🇦🇷 Por la soberanía y sostenibilidad de los recursos pesqueros argentinos | "
    "Fuente: [cfp.gob.ar](https://cfp.gob.ar)"
)
