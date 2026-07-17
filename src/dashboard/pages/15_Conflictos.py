"""
Página 15 — Red de Conflictos de Interés

Visualiza la red de relaciones entre miembros/asesores del CFP
y empresas pesqueras de las que son directores o accionistas.

Fuentes: Boletín Oficial (Sección 4 — Sociedades) + menciones en actas CFP.
Los datos marcados como 'seed_demo' son demostrativos; deben ser verificados.
"""

from __future__ import annotations

from pathlib import Path

import networkx as nx
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.acquisition.boletin_oficial_scraper import seed_cargos_demo
from src.analysis.conflict_detector import ConflictDetector

st.set_page_config(page_title="Red de Conflictos de Interés", layout="wide")

from src.config_loader import get_db_path
DB_PATH = get_db_path()
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

st.title("Red de Conflictos de Interés — CFP vs. Industria Pesquera")
st.caption(
    "Cruce entre cargos directivos en empresas pesqueras (Boletín Oficial) "
    "y apariciones en actas del CFP. "
    "⚠️ Datos demo hasta verificación por experto legal."
)

# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.header("Configuración")
    mostrar_solo_alta = st.toggle("Solo conflictos de severidad alta", value=False)
    min_resoluciones = st.slider("Mín. co-apariciones en actas", 0, 20, 0)

    st.divider()
    if st.button("Cargar datos demo (seed)"):
        n = seed_cargos_demo(DB_PATH)
        if n > 0:
            st.success(f"{n} cargos demo cargados.")
        else:
            st.info("Datos demo ya cargados.")

    st.divider()
    st.info(
        "**Limitación metodológica**\n\n"
        "Los cargos directivos provienen del Boletín Oficial (datos públicos). "
        "El análisis es descriptivo y no constituye acusación legal. "
        "Requiere verificación por experto antes de publicación."
    )

# ── Carga de datos ────────────────────────────────────────────────────────────

@st.cache_data(ttl=120)
def cargar_conflictos(db: str, solo_alta: bool, min_res: int) -> tuple[pd.DataFrame, dict]:
    cd = ConflictDetector(db)
    df = cd.detect_conflicts()
    if df.empty:
        return df, {}
    if solo_alta:
        df = df[df["severidad"] == "alta"]
    if min_res > 0:
        df = df[df["n_resoluciones"] >= min_res]
    summary = cd.conflict_summary(df)
    return df, summary


df_conf, resumen = cargar_conflictos(str(DB_PATH), mostrar_solo_alta, min_resoluciones)

# ── KPIs ─────────────────────────────────────────────────────────────────────

col1, col2, col3, col4 = st.columns(4)
col1.metric("Total conflictos", resumen.get("n_total", 0))
col2.metric("🔴 Severidad alta", resumen.get("n_alta", 0))
col3.metric("🟡 Severidad media", resumen.get("n_media", 0))
col4.metric("🟢 Severidad baja", resumen.get("n_baja", 0))

st.divider()

tab1, tab2, tab3, tab4 = st.tabs(
    ["🕸️ Grafo interactivo", "📋 Tabla de conflictos", "🏢 Directores por empresa", "📖 Metodología"]
)

def _build_plotly_graph(G: nx.Graph) -> go.Figure:
    """Construye figura Plotly del grafo de conflictos."""
    if G.number_of_nodes() == 0:
        return go.Figure()

    pos = nx.spring_layout(G, seed=42, k=2.5)

    # Aristas
    edge_traces = []
    for u, v, data in G.edges(data=True):
        x0, y0 = pos[u]
        x1, y1 = pos[v]
        sev = data.get("severidad", "baja")
        color = {"alta": "#C62828", "media": "#F57F17", "baja": "#388E3C"}.get(sev, "#9E9E9E")
        width = {"alta": 3.5, "media": 2.0, "baja": 1.0}.get(sev, 1.0)
        edge_traces.append(
            go.Scatter(
                x=[x0, x1, None],
                y=[y0, y1, None],
                mode="lines",
                line={"width": width, "color": color},
                hoverinfo="none",
                showlegend=False,
            )
        )

    # Nodos
    node_x, node_y, node_text, node_color, node_size = [], [], [], [], []
    for node, data in G.nodes(data=True):
        x, y = pos[node]
        node_x.append(x)
        node_y.append(y)
        node_text.append(node)
        node_color.append(data.get("color", "#9E9E9E"))
        node_size.append(20 if data.get("tipo") == "persona" else 16)

    node_trace = go.Scatter(
        x=node_x,
        y=node_y,
        mode="markers+text",
        text=node_text,
        textposition="top center",
        textfont={"size": 9},
        marker={"color": node_color, "size": node_size, "line": {"width": 1, "color": "white"}},
        hovertext=node_text,
        hoverinfo="text",
        showlegend=False,
    )

    layout = go.Layout(
        xaxis={"showgrid": False, "zeroline": False, "showticklabels": False},
        yaxis={"showgrid": False, "zeroline": False, "showticklabels": False},
        margin={"l": 20, "r": 20, "t": 20, "b": 20},
        height=520,
        paper_bgcolor="#0E1117",
        plot_bgcolor="#0E1117",
        font={"color": "white"},
    )
    return go.Figure(data=edge_traces + [node_trace], layout=layout)


# ── Tab 1: Grafo ──────────────────────────────────────────────────────────────

with tab1:
    if df_conf.empty:
        st.info(
            "No hay conflictos detectados. "
            "Cargá datos demo desde el sidebar o ejecutá el pipeline completo."
        )
    else:
        cd = ConflictDetector(DB_PATH)
        G = cd.build_conflict_graph(df_conf)
        fig = _build_plotly_graph(G)
        st.plotly_chart(fig, use_container_width=True)
        st.caption(
            "🟣 Personas con cargos en empresas pesqueras que aparecen en actas CFP  "
            "🟠 Empresas pesqueras  |  Grosor de arista = severidad del conflicto"
        )


# ── Tab 2: Tabla ──────────────────────────────────────────────────────────────

with tab2:
    if df_conf.empty:
        st.info("Sin datos. Cargá datos demo desde el sidebar.")
    else:
        sev_cols = {"alta": "🔴", "media": "🟡", "baja": "🟢"}
        df_display = df_conf.copy()
        df_display["Severidad"] = df_display["severidad"].map(sev_cols) + " " + df_display["severidad"]
        df_display = df_display.rename(
            columns={
                "persona_nombre": "Persona",
                "empresa_nombre": "Empresa",
                "cargo": "Cargo",
                "tipo_conflicto": "Tipo",
                "n_resoluciones": "Co-apariciones CFP",
            }
        )
        cols = ["Persona", "Empresa", "Cargo", "Tipo", "Severidad", "Co-apariciones CFP"]
        st.dataframe(df_display[cols], use_container_width=True, height=400)

        csv = df_conf.to_csv(index=False).encode("utf-8")
        st.download_button(
            "Descargar CSV",
            csv,
            "conflictos_interes.csv",
            "text/csv",
        )

# ── Tab 3: Directores por empresa ─────────────────────────────────────────────

with tab3:
    cd3 = ConflictDetector(DB_PATH)
    df_cargos = cd3.get_cargos_directivos()
    if df_cargos.empty:
        st.info("Sin datos de cargos. Cargá datos demo desde el sidebar.")
    else:
        empresas = sorted(df_cargos["empresa_nombre"].unique())
        empresa_sel = st.selectbox("Seleccionar empresa", empresas)
        df_emp = df_cargos[df_cargos["empresa_nombre"] == empresa_sel]
        st.dataframe(
            df_emp[["persona_nombre", "cargo", "desde_year", "hasta_year", "fuente", "verificado"]].rename(
                columns={
                    "persona_nombre": "Persona",
                    "cargo": "Cargo",
                    "desde_year": "Desde",
                    "hasta_year": "Hasta",
                    "fuente": "Fuente",
                    "verificado": "Verificado",
                }
            ),
            use_container_width=True,
        )
        st.caption(
            f"**Fuente:** Boletín Oficial Sección 4 / datos.gob.ar — "
            f"Verificado por experto: {'✅' if df_emp['verificado'].any() else '⚠️ pendiente'}"
        )

# ── Tab 4: Metodología ────────────────────────────────────────────────────────

with tab4:
    st.markdown(
        """
## Metodología — Red de Conflictos de Interés

### Fuentes de datos

| Fuente | Contenido | URL |
|--------|-----------|-----|
| Boletín Oficial (Sec. 4) | Designación de autoridades societarias | boletinoficial.gob.ar |
| Actas CFP 1998–2025 | Votaciones, resoluciones, miembros | cfp.gob.ar |
| IGJ (vía BO) | Estatutos y modificaciones societarias | *(vía Boletín Oficial)* |

### Definición de conflicto de interés

Un conflicto de interés se detecta cuando:

> Una misma persona figura como **director, presidente, socio o gerente** de una empresa
> pesquera beneficiaria de resoluciones CFP Y **aparece en las actas CFP** en el período
> correspondiente (como votante, asesor técnico o delegado).

### Niveles de severidad

| Nivel | Criterio |
|-------|---------|
| 🔴 **Alta** | Co-aparición directa: persona y empresa mencionadas en la misma resolución CFP |
| 🟡 **Media** | Persona en actas CFP durante período de directividad sin co-mención explícita |
| 🟢 **Baja** | Solo en registros societarios; sin aparición verificada en actas CFP |

### Limitaciones

- Los datos demo (`fuente = seed_demo`) son **sintéticos** y no verificados.
- Un mismo nombre puede corresponder a personas distintas (falsos positivos).
- La ausencia de conflicto detectado no implica ausencia real de conflicto.
- **No constituye acusación legal.** El análisis es descriptivo y requiere
  verificación por experto legal antes de cualquier publicación.

### Literatura de referencia

- OCDE (2003). *Managing Conflict of Interest in the Public Service: OECD Guidelines and Country Experiences.*
- Ley 25.188 de Ética Pública (Argentina) — Art. 13: incompatibilidades.
- FAO Code of Conduct for Responsible Fisheries (1995) — Art. 7.1.2: transparencia en la toma de decisiones.
        """
    )
