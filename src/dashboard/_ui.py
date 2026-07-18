"""
Componentes de UI reutilizables para el dashboard (DRY + consistencia visual).

- `inject_base_css()`  → estilos sutiles (cards de métricas, nav, espaciado, expanders).
- `sidebar_brand()`    → logo/wordmark (arriba de la navegación) + enlaces en la barra lateral.
- `page_header()`      → cabecera consistente (icono + título + subtítulo).
- `setup_page()`       → atajo: inyecta CSS + marca de sidebar (llamar tras set_page_config).

Diseño: paleta marina definida en `.streamlit/config.toml`. El CSS es mínimo y usa
selectores `data-testid` estables para no depender de clases internas volátiles.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

REPO_URL = "https://github.com/arielgiamportone/cfp-audit-intelligence"
APP_URL = "https://cfp-audit-intelligence-um5xi4fkkiyq2gtuownvuz.streamlit.app"
LOGO_PATH = Path(__file__).parent / "assets" / "logo.svg"

_BASE_CSS = """
<style>
/* Franja de acento marino en la parte superior */
[data-testid="stHeader"] {
  background: linear-gradient(90deg, #0E7490 0%, #14303B 100%);
  height: 4px;
}

/* Ancho y aire de la página */
.block-container { padding-top: 2.4rem; padding-bottom: 3rem; max-width: 1200px; }

/* Métricas como tarjetas */
[data-testid="stMetric"] {
  background: #ECF3F6;
  border: 1px solid #D6E4EA;
  border-radius: 12px;
  padding: 14px 18px;
  box-shadow: 0 1px 2px rgba(20,48,59,.06);
}
[data-testid="stMetricLabel"] { opacity: .75; }

/* Navegación del sidebar: items tipo "pill" */
[data-testid="stSidebarNav"] ul { padding-top: .25rem; }
[data-testid="stSidebarNav"] a {
  border-radius: 8px;
  margin: 1px 6px;
  padding: 4px 10px;
}
[data-testid="stSidebarNav"] a:hover { background: rgba(14,116,144,.10); }
[data-testid="stSidebarNav"] a[aria-current="page"] {
  background: rgba(14,116,144,.16);
  font-weight: 600;
}

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
    """Logo/wordmark arriba de la navegación + enlaces en la barra lateral."""
    # `st.logo` (Streamlit >= 1.35) coloca la imagen ENCIMA de la navegación.
    try:
        if LOGO_PATH.exists():
            st.logo(str(LOGO_PATH), link=REPO_URL, icon_image=str(LOGO_PATH))
    except Exception:
        pass  # versiones antiguas de Streamlit: se usa solo el bloque de abajo
    with st.sidebar:
        st.caption("🐟 Auditoría pesquera con IA · **TFM**")
        st.markdown(f"[💻 Repositorio]({REPO_URL}) · [🚀 App]({APP_URL})")
        st.divider()


def page_header(icon: str, title: str, subtitle: str | None = None) -> None:
    """Cabecera consistente de página (icono + título + subtítulo)."""
    page_header_raw(f"{icon} {title}", subtitle)


def page_header_raw(title: str, subtitle: str | None = None) -> None:
    """Cabecera consistente cuando el título ya incluye el icono (o es una f-string).
    Punto único para dar formato al encabezado de cada página (DRY)."""
    st.title(title)
    if subtitle:
        st.caption(subtitle)


def setup_page() -> None:
    """Atajo estándar para cada página: CSS base + marca de sidebar."""
    inject_base_css()
    sidebar_brand()


# ── Paleta marina (coherente con .streamlit/config.toml) ───────────────────────
TEAL = "#0E7490"
SLATE = "#14303B"
CARD_BG = "#ECF3F6"
CARD_BORDER = "#D6E4EA"


def demo_banner(text: str | None = None) -> None:
    """Aviso estándar de 'modo demo' (unifica los 5 estilos que había dispersos)."""
    st.info(
        text
        or (
            "🎓 **Demo del TFM.** Esta vista requiere el corpus completo de actas "
            "(se genera con el pipeline). Su funcionamiento se muestra en el vídeo del "
            "proyecto y puede reproducirse en local — ver `docs/TFM_DEPLOY.md`."
        ),
        icon="ℹ️",
    )


def dev_note(text: str) -> None:
    """Encapsula instrucciones técnicas (comandos de terminal) para que no invadan
    la interfaz del usuario final, pero sigan disponibles para evaluadores."""
    with st.expander("🛠️ Detalle técnico (para desarrolladores)"):
        st.markdown(text)


def style_plotly(fig, height: int | None = None):
    """Aplica el tema claro marino a una figura Plotly (fondo transparente + texto
    slate) para que los gráficos hereden la paleta en lugar de forzar fondo oscuro."""
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font_color=SLATE,
        legend=dict(font=dict(color=SLATE)),
    )
    if height:
        fig.update_layout(height=height)
    return fig
