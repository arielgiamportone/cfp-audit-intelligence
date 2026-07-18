"""
CFP Audit Intelligence – Router de navegación (entrypoint del dashboard).

Usa `st.navigation` (Streamlit ≥ 1.36) para agrupar las páginas en secciones temáticas
en lugar de una lista plana de 17 entradas. Fija `set_page_config` y el tema/marca una
sola vez; cada página deja de configurarse por su cuenta.
"""

import sys
from pathlib import Path

import streamlit as st

# Asegurar que `src` esté en el path para todas las páginas
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

st.set_page_config(
    page_title="CFP Audit Intelligence",
    page_icon="🐟",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        "About": (
            "**CFP Audit Intelligence Platform** v0.5\n\n"
            "Plataforma de auditoría inteligente del Consejo Federal Pesquero de Argentina.\n\n"
            "Datos fuente: [cfp.gob.ar](https://cfp.gob.ar/actas-cfp)"
        )
    },
)

from src.dashboard._ui import setup_page

# CSS base + logo/wordmark + marca de sidebar (una vez, para toda la app)
setup_page()

# ── Definición de páginas agrupadas por sección ────────────────────────────────
# Rutas relativas a este archivo (src/dashboard/). Títulos e iconos definen la nav.

inicio = st.Page("home.py", title="Inicio", icon="🏠", default=True)
informe = st.Page("pages/00_Informe_Ejecutivo.py", title="Informe ejecutivo", icon="📰")

nav = {
    "Inicio": [inicio, informe],
    "Núcleo · Triángulo de auditoría": [
        st.Page("pages/05_INIDEP_Comparador.py", title="Comparador INIDEP", icon="🔬"),
        st.Page("pages/06_Timeline.py", title="Timeline histórico", icon="📈"),
        st.Page("pages/12_Capturas.py", title="Capturas reales", icon="🐟"),
    ],
    "Análisis con IA": [
        st.Page("pages/03_Auditoria.py", title="Auditoría IA", icon="🧠"),
        st.Page("pages/04_Reportes.py", title="Reportes", icon="📊"),
        st.Page("pages/09_Reporte.py", title="Reporte PDF", icon="📄"),
    ],
    "Contexto externo": [
        st.Page("pages/10_FAO_FIRMS.py", title="Contexto FAO", icon="🌎"),
        st.Page("pages/11_CONICET.py", title="Ciencia CONICET", icon="📚"),
        st.Page("pages/16_Geovisor.py", title="Geovisor de vedas", icon="🗺️"),
        st.Page("pages/17_CONAE_Satelital.py", title="CONAE satelital", icon="🛰️"),
    ],
    "Gobernanza y alertas": [
        st.Page("pages/07_Grafo.py", title="Grafo de relaciones", icon="🕸️"),
        st.Page("pages/08_Alertas.py", title="Sistema de alertas", icon="🚨"),
        st.Page("pages/15_Conflictos.py", title="Conflictos de interés", icon="🕵️"),
    ],
    "Ingesta y rigor": [
        st.Page("pages/01_Adquisicion.py", title="Adquisición de actas", icon="📥"),
        st.Page("pages/02_Knowledge_Base.py", title="Knowledge Base", icon="🔍"),
        st.Page("pages/13_Investigacion.py", title="Hub de investigación", icon="🧪"),
        st.Page("pages/14_Evaluacion.py", title="Evaluación del sistema", icon="📐"),
    ],
}

pg = st.navigation(nav)
pg.run()
