"""
Página 7 — Grafo de Relaciones CFP.

Visualiza el grafo bipartito especie ↔ empresa basado en co-menciones
en las decisiones del Consejo Federal Pesquero.
"""

import tempfile
from pathlib import Path

import networkx as nx
import pandas as pd
import streamlit as st
from pyvis.network import Network

from src.analysis.graph_builder import NODE_COLORS, NODE_EMPRESA, NODE_ESPECIE, CFPGraphBuilder

st.set_page_config(
    page_title="Grafo CFP",
    page_icon="🕸️",
    layout="wide",
)

from src.dashboard._ui import setup_page
setup_page()

st.title("🕸️ Grafo de Relaciones CFP")
st.caption(
    "Red bipartita de co-menciones entre especies pesqueras y empresas "
    "en las decisiones del Consejo Federal Pesquero."
)

from src.config_loader import get_db_path
DB_PATH = get_db_path()


@st.cache_resource(show_spinner="Cargando grafo...")
def get_builder():
    return CFPGraphBuilder(db_path=DB_PATH)


@st.cache_data(show_spinner="Construyendo grafo...")
def build_cached_graph(min_coocurrencias: int):
    builder = CFPGraphBuilder(db_path=DB_PATH)
    G = builder.build_graph(min_coocurrencias=min_coocurrencias)
    stats = builder.compute_stats(G)
    return G, stats


def render_pyvis(G: nx.Graph, height: int = 700) -> str:
    """Renderiza el grafo NetworkX con pyvis y retorna HTML."""
    net = Network(
        height=f"{height}px",
        width="100%",
        bgcolor="#0e1117",
        font_color="white",
        notebook=False,
        directed=False,
    )
    net.barnes_hut(gravity=-8000, central_gravity=0.3, spring_length=120, spring_strength=0.05)

    for node, data in G.nodes(data=True):
        tipo = data.get("tipo", "")
        color = NODE_COLORS.get(tipo, "#888888")
        menciones = data.get("menciones", 0)
        n_res = data.get("n_resoluciones", 0)
        size = 10 + min(menciones * 0.8, 40)

        title = f"<b>{node}</b><br>Tipo: {tipo}<br>Menciones: {menciones}<br>Resoluciones: {n_res}"
        net.add_node(
            node,
            label=node,
            color=color,
            size=size,
            title=title,
            font={"size": 11, "color": "white"},
        )

    for n1, n2, data in G.edges(data=True):
        weight = data.get("weight", 1)
        width = min(weight * 1.2, 8)
        net.add_edge(
            n1,
            n2,
            width=width,
            title=f"Co-menciones: {weight}",
            color={"color": "#546e7a", "highlight": "#ffffff"},
        )

    net.set_options("""
    {
      "interaction": {
        "hover": true,
        "tooltipDelay": 100,
        "navigationButtons": true
      },
      "physics": {
        "enabled": true,
        "stabilization": {"iterations": 150}
      }
    }
    """)

    with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as f:
        net.save_graph(f.name)
        return Path(f.name).read_text(encoding="utf-8")


def render_ego_pyvis(G: nx.Graph, nodo: str, radio: int) -> str:
    builder = CFPGraphBuilder(db_path=DB_PATH)
    ego = builder.get_ego_graph(G, nodo, radio=radio)
    return render_pyvis(ego, height=500)


# ── Sidebar ────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.header("⚙️ Configuración")

    min_cooc = st.slider(
        "Mínimo co-menciones",
        min_value=1,
        max_value=10,
        value=1,
        help="Filtrar aristas con menos co-menciones que este umbral",
    )

    st.divider()
    st.subheader("🔍 Ego-grafo")
    ego_radio = st.slider("Radio ego-grafo", min_value=1, max_value=3, value=1)

    st.divider()
    st.subheader("📊 Vista")
    graph_height = st.slider("Altura grafo (px)", 400, 1000, 700, step=50)
    show_isolated = st.checkbox("Mostrar nodos aislados", value=False)

# ── Verificar BD ───────────────────────────────────────────────────────────────

if not DB_PATH.exists():
    st.warning(
        "⚠️ Base de datos no encontrada en `data/processed/catalog.db`. "
        "Ejecuta primero `make pipeline` o `python scripts/run_full_pipeline.py --step process`."
    )
    st.stop()

# ── Construir grafo ────────────────────────────────────────────────────────────

G, stats = build_cached_graph(min_coocurrencias=min_cooc)

if G.number_of_nodes() == 0:
    st.info(
        "El grafo está vacío. Es posible que las actas aún no hayan sido procesadas "
        "o que no haya co-menciones con el umbral seleccionado."
    )
    st.stop()

# ── Métricas resumen ───────────────────────────────────────────────────────────

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Nodos totales", stats.n_nodos)
col2.metric("Especies", stats.n_especies)
col3.metric("Empresas", stats.n_empresas)
col4.metric("Aristas", stats.n_aristas)
col5.metric("Densidad", f"{stats.densidad:.4f}")

st.divider()

# ── Tabs principales ───────────────────────────────────────────────────────────

tab1, tab2, tab3, tab4 = st.tabs(
    [
        "🌐 Grafo interactivo",
        "🔬 Ego-grafo",
        "📊 Análisis HHI",
        "📋 Datos",
    ]
)


# ─── Tab 1: Grafo completo ─────────────────────────────────────────────────────

with tab1:
    col_info, col_legend = st.columns([3, 1])

    with col_legend:
        st.markdown("**Leyenda**")
        st.markdown(
            f'<span style="color:{NODE_COLORS[NODE_ESPECIE]}">■</span> Especie pesquera',
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<span style="color:{NODE_COLORS[NODE_EMPRESA]}">■</span> Empresa pesquera',
            unsafe_allow_html=True,
        )
        st.markdown("*Grosor de arista = frecuencia de co-mención*")
        if stats.especie_mas_conectada:
            st.metric("Especie más conectada", stats.especie_mas_conectada)
        if stats.empresa_mas_conectada:
            st.metric("Empresa más conectada", stats.empresa_mas_conectada)
        st.metric("Componentes conexas", stats.componentes)

    with col_info:
        html_grafo = render_pyvis(G, height=graph_height)
        st.components.v1.html(html_grafo, height=graph_height + 20, scrolling=False)


# ─── Tab 2: Ego-grafo ─────────────────────────────────────────────────────────

with tab2:
    st.subheader("Red centrada en un nodo")

    all_nodes = sorted(G.nodes())
    especies = sorted([n for n, d in G.nodes(data=True) if d.get("tipo") == NODE_ESPECIE])
    empresas = sorted([n for n, d in G.nodes(data=True) if d.get("tipo") == NODE_EMPRESA])

    col_sel1, col_sel2 = st.columns(2)
    with col_sel1:
        tipo_ego = st.radio(
            "Tipo de nodo central", ["Especie", "Empresa", "Cualquiera"], horizontal=True
        )
    with col_sel2:
        if tipo_ego == "Especie":
            opciones = especies
        elif tipo_ego == "Empresa":
            opciones = empresas
        else:
            opciones = all_nodes

        nodo_ego = st.selectbox("Seleccionar nodo", opciones) if opciones else None

    if nodo_ego:
        builder_ego = CFPGraphBuilder(db_path=DB_PATH)
        ego_G = builder_ego.get_ego_graph(G, nodo_ego, radio=ego_radio)

        ego_col1, ego_col2 = st.columns([2, 1])

        with ego_col1:
            ego_html = render_pyvis(ego_G, height=500)
            st.components.v1.html(ego_html, height=520, scrolling=False)

        with ego_col2:
            st.subheader(f"Vecinos de '{nodo_ego}'")
            tipo_nodo = G.nodes[nodo_ego].get("tipo", "")

            if tipo_nodo == NODE_ESPECIE:
                builder_top = CFPGraphBuilder(db_path=DB_PATH)
                top = builder_top.top_empresas_por_especie(G, nodo_ego)
                if top:
                    df_top = pd.DataFrame(top)
                    df_top.columns = ["Empresa", "Co-menciones"]
                    st.dataframe(df_top, use_container_width=True, hide_index=True)
            elif tipo_nodo == NODE_EMPRESA:
                vecinos = [
                    {
                        "Especie": n,
                        "Co-menciones": G[nodo_ego][n]["weight"],
                    }
                    for n in G.neighbors(nodo_ego)
                    if G.nodes[n].get("tipo") == NODE_ESPECIE
                ]
                if vecinos:
                    df_vec = pd.DataFrame(
                        sorted(vecinos, key=lambda x: x["Co-menciones"], reverse=True)
                    )
                    st.dataframe(df_vec, use_container_width=True, hide_index=True)

            st.metric("Grado", G.degree(nodo_ego))
            st.metric("Menciones totales", G.nodes[nodo_ego].get("menciones", 0))
            st.metric("Resoluciones", G.nodes[nodo_ego].get("n_resoluciones", 0))


# ─── Tab 3: HHI ───────────────────────────────────────────────────────────────

with tab3:
    st.subheader("Índice de Herfindahl-Hirschman (HHI) por especie")
    st.markdown(
        """
        El **HHI** mide la concentración de la actividad pesquera por especie.
        - **< 1.500**: Mercado competitivo
        - **1.500 – 2.500**: Concentración moderada
        - **> 2.500**: Alta concentración (oligopolio/monopolio)

        *Calculado como suma de cuadrados de participaciones de co-menciones × 10.000*
        """
    )

    if stats.hhi_por_especie:
        df_hhi = pd.DataFrame(
            [
                {
                    "Especie": esp,
                    "HHI": hhi,
                    "Nivel": (
                        "🟢 Competitivo"
                        if hhi < 1500
                        else "🟡 Moderado"
                        if hhi < 2500
                        else "🔴 Alta concentración"
                    ),
                }
                for esp, hhi in sorted(
                    stats.hhi_por_especie.items(), key=lambda x: x[1], reverse=True
                )
            ]
        )

        try:
            import plotly.express as px

            fig_hhi = px.bar(
                df_hhi,
                x="Especie",
                y="HHI",
                color="HHI",
                color_continuous_scale=["#4caf50", "#ffeb3b", "#f44336"],
                range_color=[0, 10000],
                title="HHI de concentración empresarial por especie",
                labels={"HHI": "Índice HHI"},
                text="HHI",
            )
            fig_hhi.add_hline(
                y=1500,
                line_dash="dash",
                line_color="#ffeb3b",
                annotation_text="Umbral moderado (1.500)",
            )
            fig_hhi.add_hline(
                y=2500,
                line_dash="dash",
                line_color="#f44336",
                annotation_text="Umbral alta concentración (2.500)",
            )
            fig_hhi.update_traces(texttemplate="%{text:.0f}", textposition="outside")
            fig_hhi.update_layout(
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                font_color="white",
                showlegend=False,
            )
            st.plotly_chart(fig_hhi, use_container_width=True)
        except ImportError:
            pass

        st.dataframe(df_hhi, use_container_width=True, hide_index=True)

        st.subheader("Top empresas por especie")
        esp_sel = st.selectbox(
            "Especie",
            sorted(stats.hhi_por_especie.keys()),
            key="hhi_esp_sel",
        )
        if esp_sel:
            builder_hhi = CFPGraphBuilder(db_path=DB_PATH)
            top_emp = builder_hhi.top_empresas_por_especie(G, esp_sel)
            if top_emp:
                df_top_emp = pd.DataFrame(top_emp)
                total_co = df_top_emp["co_menciones"].sum()
                df_top_emp["participación_%"] = (df_top_emp["co_menciones"] / total_co * 100).round(
                    1
                )
                df_top_emp.columns = ["Empresa", "Co-menciones", "Participación %"]
                st.dataframe(df_top_emp, use_container_width=True, hide_index=True)
    else:
        st.info("No hay datos HHI disponibles. Verifica que las actas estén procesadas.")


# ─── Tab 4: Datos ─────────────────────────────────────────────────────────────

with tab4:
    st.subheader("Aristas del grafo")

    builder_df = CFPGraphBuilder(db_path=DB_PATH)
    df_edges = builder_df.to_dataframe(G)

    col_f1, col_f2, col_f3 = st.columns(3)
    with col_f1:
        esp_filtro = st.multiselect(
            "Filtrar por especie",
            sorted(df_edges["especie"].unique()),
        )
    with col_f2:
        emp_filtro = st.multiselect(
            "Filtrar por empresa",
            sorted(df_edges["empresa"].unique()),
        )
    with col_f3:
        min_co_filtro = st.number_input("Mínimo co-menciones", min_value=1, value=1)

    df_show = df_edges.copy()
    if esp_filtro:
        df_show = df_show[df_show["especie"].isin(esp_filtro)]
    if emp_filtro:
        df_show = df_show[df_show["empresa"].isin(emp_filtro)]
    df_show = df_show[df_show["co_menciones"] >= min_co_filtro]

    st.dataframe(
        df_show.rename(columns={"co_menciones": "Co-menciones"}),
        use_container_width=True,
        hide_index=True,
    )
    st.caption(f"Mostrando {len(df_show)} aristas de {len(df_edges)} totales.")

    csv_data = df_show.to_csv(index=False).encode("utf-8")
    st.download_button(
        "⬇️ Descargar CSV",
        data=csv_data,
        file_name="grafo_cfp_aristas.csv",
        mime="text/csv",
    )

    st.divider()
    st.subheader("Nodos del grafo")
    df_nodes = pd.DataFrame(
        [
            {
                "Nodo": n,
                "Tipo": d.get("tipo", ""),
                "Menciones": d.get("menciones", 0),
                "Resoluciones": d.get("n_resoluciones", 0),
                "Grado": G.degree(n),
            }
            for n, d in G.nodes(data=True)
        ]
    ).sort_values("Grado", ascending=False)

    st.dataframe(df_nodes, use_container_width=True, hide_index=True)
