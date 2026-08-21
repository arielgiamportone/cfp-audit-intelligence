"""
Informe Ejecutivo — vista narrativa (scrollytelling) del hallazgo central del proyecto.

Cuenta, con los datos verificados, la cadena CIENCIA (CBA) → POLÍTICA (CMP) → REALIDAD
(captura), destaca las cifras clave y hace un foco por especie con texto autogenerado.
Pensada para leerse de arriba a abajo (y para grabar el vídeo del TFM).
"""

import sys
from collections import Counter
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(ROOT))

from src.dashboard._ui import col_ratio, col_tn, data_source, page_header_raw, tabla

page_header_raw(
    "📰 Informe Ejecutivo",
    "La historia en una página: ¿respeta la política pesquera lo que dice la ciencia?",
)
data_source("INIDEP (Mar Abierto) + SAGPyA/SIPA — datos semilla verificados", estado="verificado")

import plotly.graph_objects as go

from src.config_loader import get_db_path

DB_PATH = get_db_path()


@st.cache_resource(show_spinner="Preparando el informe...")
def _get_comparator():
    from src.analysis.inidep_comparator import INIDEPComparator

    return INIDEPComparator(DB_PATH)


try:
    comp = _get_comparator()
    df = comp.get_triangulo_completo()
    alertas = comp.compute_comparisons()
except Exception as exc:  # noqa: BLE001
    st.error(f"No se pudo preparar el informe: {exc}")
    st.stop()

if df.empty:
    st.info("Aún no hay datos suficientes para el informe. Visita el Comparador INIDEP.")
    st.page_link("pages/05_INIDEP_Comparador.py", label="🔬 Ir al Comparador INIDEP")
    st.stop()

# ── 1 · El problema en una frase ───────────────────────────────────────────────

st.markdown("---")
st.subheader("1 · El problema")
st.markdown(
    "Cada año la ciencia (**INIDEP**) fija un límite seguro de captura por especie "
    "—la **CBA**—. La política (**CFP**) aprueba una cuota —la **CMP**— y la flota "
    "desembarca una **captura real**. Este informe verifica, con datos públicos, si esa "
    "cadena respeta el límite científico."
)

st.markdown(
    """
```
CIENCIA (INIDEP) ──▶ CBA (límite seguro)
                      │
POLÍTICA (CFP)   ──▶ CMP (cuota aprobada)      ¿se respeta el límite?
                      │
REALIDAD (SIPA)  ──▶ Captura real desembarcada
```
"""
)

# ── 2 · Los números que importan ───────────────────────────────────────────────

st.markdown("---")
st.subheader("2 · Los números que importan")

cap = Counter(a.alerta_captura for a in alertas)
con_dato = sum(v for k, v in cap.items() if k not in (None, "sin_datos"))
excede = cap.get("critico", 0) + cap.get("rojo", 0) + cap.get("amarillo", 0)
criticos = cap.get("critico", 0)
pct_excede = (excede / con_dato * 100) if con_dato else 0

k1, k2, k3, k4 = st.columns(4)
k1.metric(
    "Comparaciones analizadas",
    con_dato,
    help="Casos especie/año con captura real y CBA disponibles.",
)
k2.metric(
    "Captura sobre el límite (CBA)",
    excede,
    help="Casos donde la captura real superó el límite recomendado por la ciencia.",
)
k3.metric(
    "% sobre el límite",
    f"{pct_excede:.0f}%",
    help="Proporción de casos analizados que superan la CBA.",
)
k4.metric("⚫ Casos críticos", criticos, help="Captura real superior al 130% de la CBA.")

st.caption(
    "Comparación **captura real vs. CBA**. Es **indicativa**: las capturas son totales "
    "nacionales y la CBA es por zona; el detalle está en el Comparador."
)

# ── 3 · Foco por especie ───────────────────────────────────────────────────────

st.markdown("---")
st.subheader("3 · Foco por especie")

df_cba = df.dropna(subset=["cba_recomendada_tn"]).copy()
# especies con más años de datos, ordenadas para elegir una "estrella" por defecto
orden_especies = (
    df_cba.groupby("especie")["ratio_captura_cba"]
    .apply(lambda s: s.notna().sum())
    .sort_values(ascending=False)
)
especies = list(orden_especies.index)
if not especies:
    st.info("No hay especies con CBA numérica para el foco.")
    st.stop()

especie_sel = st.selectbox(
    "Especie",
    especies,
    format_func=lambda e: str(e).title(),
    help="Elegida por defecto la especie con más años de datos.",
)

foco = df_cba[df_cba["especie"] == especie_sel].sort_values("year").copy()
foco_ratio = foco.dropna(subset=["ratio_captura_cba"])

# Narrativa autogenerada a partir de los datos
nombre = str(especie_sel).title()
if not foco_ratio.empty:
    n_anios = foco_ratio["year"].nunique()
    n_exceso = int((foco_ratio["ratio_captura_cba"] > 1).sum())
    peor = foco_ratio.loc[foco_ratio["ratio_captura_cba"].idxmax()]
    peor_year = int(peor["year"])
    peor_ratio = float(peor["ratio_captura_cba"])
    rango = f"{int(foco_ratio['year'].min())}–{int(foco_ratio['year'].max())}"

    if n_exceso == 0:
        veredicto = f"la captura real se mantuvo **dentro** del límite científico en todos los años analizados ({rango})."
    else:
        veredicto = (
            f"la captura real **superó** el límite científico (CBA) en **{n_exceso} de {n_anios}** "
            f"años analizados ({rango}); el pico fue en **{peor_year}**, con una captura equivalente "
            f"al **{peor_ratio * 100:.0f}%** de la CBA."
        )
    st.markdown(f"**{nombre}:** {veredicto}")

# Gráfico de la cadena por año (CBA vs captura; CMP si existe)
fig = go.Figure()
fig.add_trace(
    go.Bar(
        name="CBA INIDEP (límite científico)",
        x=foco["year"],
        y=foco["cba_recomendada_tn"],
        marker_color="#2196F3",
        opacity=0.85,
    )
)
if foco["cmp_aprobada_tn"].notna().any():
    fig.add_trace(
        go.Bar(
            name="CMP CFP (cuota aprobada)",
            x=foco["year"],
            y=foco["cmp_aprobada_tn"],
            marker_color="#FF9800",
            opacity=0.85,
        )
    )
if foco["captura_real_tn"].notna().any():
    fig.add_trace(
        go.Bar(
            name="Captura real (SAGPyA)",
            x=foco["year"],
            y=foco["captura_real_tn"],
            marker_color="#4CAF50",
            opacity=0.85,
        )
    )
fig.update_layout(
    barmode="group",
    title=f"{nombre} — CBA vs. captura real por año",
    yaxis_title="Toneladas",
    xaxis_title="",
    legend=dict(orientation="h", yanchor="bottom", y=1.02),
    height=430,
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font_color="#14303B",
)
st.plotly_chart(fig, width="stretch")

# Tabla del foco con formato
cols = [
    c
    for c in ["year", "zona", "cba_recomendada_tn", "captura_real_tn", "ratio_captura_cba"]
    if c in foco.columns
]
tabla(
    foco[cols].rename(
        columns={
            "year": "Año",
            "zona": "Zona",
            "cba_recomendada_tn": "CBA (tn)",
            "captura_real_tn": "Captura real (tn)",
            "ratio_captura_cba": "Ratio Captura/CBA",
        }
    ),
    column_config={
        "Año": st.column_config.NumberColumn("Año", format="%d"),
        "CBA (tn)": col_tn("CBA (tn)", help="Límite recomendado por la ciencia."),
        "Captura real (tn)": col_tn("Captura real (tn)", help="Desembarque real (SAGPyA/SIPA)."),
        "Ratio Captura/CBA": col_ratio(
            "Ratio Captura/CBA",
            help="1.0 = límite científico. >1 = captura por encima.",
            max_value=3.0,
        ),
    },
)

# ── 4 · Cómo leerlo y limitaciones ─────────────────────────────────────────────

st.markdown("---")
st.subheader("4 · Cómo leerlo (y qué NO afirma)")
st.markdown(
    "- La comparación es **descriptiva**: señala dónde mirar, no constituye acusación ni "
    "conclusión jurídica.\n"
    "- Las capturas SAGPyA son **totales nacionales**; la CBA suele ser **por zona/stock**, "
    "por lo que algunos ratios altos reflejan esa diferencia de granularidad.\n"
    "- Los hallazgos deben verificarse contra los **textos originales** de las resoluciones.\n"
    "- La cuota **CMP** se ingresa manualmente en el Comparador; por eso aquí puede no aparecer."
)

st.page_link(
    "pages/05_INIDEP_Comparador.py", label="🔬 Explorar el análisis completo en el Comparador"
)
st.caption(
    "🇦🇷 Por la soberanía y sostenibilidad de los recursos pesqueros argentinos · "
    "Fuente: INIDEP · SAGPyA/SIPA · CFP"
)
