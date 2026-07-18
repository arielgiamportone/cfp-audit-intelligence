"""
Componentes de UI reutilizables para el dashboard (DRY + consistencia visual).

- `inject_base_css()`  → estilos sutiles (cards de métricas, espaciado, expanders).
- `sidebar_brand()`    → bloque de marca + enlaces en la barra lateral.
- `page_header()`      → cabecera consistente (icono + título + subtítulo).
- `setup_page()`       → atajo: inyecta CSS + marca de sidebar (llamar tras set_page_config).

Diseño: paleta marina definida en `.streamlit/config.toml`. El CSS es mínimo y usa
selectores `data-testid` estables para no depender de clases internas volátiles.
"""

from __future__ import annotations

import streamlit as st

REPO_URL = "https://github.com/arielgiamportone/cfp-audit-intelligence"
APP_URL = "https://cfp-audit-intelligence-um5xi4fkkiyq2gtuownvuz.streamlit.app"

_BASE_CSS = """
<style>
/* Ancho y aire de la página */
.block-container { padding-top: 2.2rem; padding-bottom: 3rem; max-width: 1200px; }

/* Métricas como tarjetas */
[data-testid="stMetric"] {
  background: #ECF3F6;
  border: 1px solid #D6E4EA;
  border-radius: 12px;
  padding: 12px 16px;
}
[data-testid="stMetricLabel"] { opacity: .75; }

/* Expanders más suaves */
div[data-testid="stExpander"] details {
  border: 1px solid #D6E4EA;
  border-radius: 10px;
}

/* Botones de navegación (page_link) tipo "chip" */
[data-testid="stPageLink"] a { border-radius: 8px; }

/* Tipografía de títulos un poco más compacta */
h1, h2, h3 { letter-spacing: -0.01em; }

/* Ocultar el footer "Made with Streamlit" */
footer { visibility: hidden; }
</style>
"""


def inject_base_css() -> None:
    """Inyecta el CSS base (llamar una vez por página, tras `set_page_config`)."""
    st.markdown(_BASE_CSS, unsafe_allow_html=True)


def sidebar_brand() -> None:
    """Bloque de marca y enlaces en la barra lateral."""
    with st.sidebar:
        st.markdown("### 🐟 CFP Audit Intelligence")
        st.caption("Auditoría pesquera con IA · TFM")
        st.markdown(f"[💻 Repositorio]({REPO_URL}) · [🚀 App]({APP_URL})")
        st.divider()


def page_header(icon: str, title: str, subtitle: str | None = None) -> None:
    """Cabecera consistente de página."""
    st.title(f"{icon} {title}")
    if subtitle:
        st.caption(subtitle)


def setup_page() -> None:
    """Atajo estándar para cada página: CSS base + marca de sidebar."""
    inject_base_css()
    sidebar_brand()
