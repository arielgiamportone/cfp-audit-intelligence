"""
Smoke test del dashboard (Streamlit).

Recorre el router `st.navigation` y **cada página** con `streamlit.testing.v1.AppTest`
y verifica que renderizan **sin excepciones no controladas**. Gracias al helper
`import_guard`, una dependencia ausente detiene la página con un aviso (no una excepción),
así que el test es válido tanto en el "camino feliz" (todas las deps instaladas) como en
entornos reducidos (deps opcionales ausentes).

Este test habría detectado regresiones reales ya corregidas:
  - `st.dataframe(height=None)` inválido en Streamlit ≥1.59 (helper `tabla`).
  - `get_esfuerzo_df(...) or pd.DataFrame()` → "truth value of a DataFrame is ambiguous" (CONAE).

Se omite automáticamente si Streamlit no está instalado.
"""

from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
APP = str(REPO / "src" / "dashboard" / "app.py")
PAGES = sorted((REPO / "src" / "dashboard" / "pages").glob("*.py"))


def _run(page_rel: str | None = None) -> AppTest:
    at = AppTest.from_file(APP, default_timeout=90)
    at.run()
    if page_rel:
        at.switch_page(page_rel).run()
    return at


def _first_exception(at: AppTest) -> str:
    if not at.exception:
        return ""
    exc = at.exception[0]
    return str(getattr(exc, "value", exc)).splitlines()[0]


def test_router_and_home_render():
    """El router de navegación construye y la página de inicio renderiza."""
    at = _run()
    assert not at.exception, f"home.py: {_first_exception(at)}"
    assert at.title, "El home debería renderizar un título"


@pytest.mark.parametrize(
    "page",
    [f"pages/{p.name}" for p in PAGES],
    ids=[p.stem for p in PAGES],
)
def test_page_renders_without_exception(page):
    """Cada página del dashboard renderiza sin excepción (guard o camino feliz)."""
    at = _run(page)
    assert not at.exception, f"{page}: {_first_exception(at)}"
