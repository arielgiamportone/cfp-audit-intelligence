"""Página 11 — Publicaciones Científicas CONICET."""

from pathlib import Path

import streamlit as st

from src.acquisition.conicet_scraper import SEARCH_TERMS, CONICETScraper

from src.dashboard._ui import data_source, page_header_raw
page_header_raw("🔬 Publicaciones Científicas CONICET/INIDEP")
data_source("CONICET Digital / INIDEP (literatura verificada)", estado="verificado")
st.markdown(
    "Literatura científica verificada sobre las especies pesqueras analizadas por el CFP. "
    "Fuente: **CONICET Digital** y repositorios institucionales de INIDEP."
)

from src.config_loader import get_db_path
DB_PATH = get_db_path()

@st.cache_resource(show_spinner="Cargando publicaciones científicas...")
def get_scraper():
    s = CONICETScraper(db_path=DB_PATH)
    s.seed_data()
    return s

scraper = get_scraper()
df_pubs = scraper.get_publicaciones_df()
df_resumen = scraper.get_resumen_por_especie()

if df_pubs.empty:
    st.warning("No hay publicaciones disponibles.")
    st.stop()

# ── Métricas ──────────────────────────────────────────────────────────────────

c1, c2, c3, c4 = st.columns(4)
c1.metric("Total publicaciones", len(df_pubs))
c2.metric("Especies cubiertas", df_pubs["especie_code"].nunique())
c3.metric(
    "Rango temporal",
    f"{int(df_pubs['año_publicacion'].min())}–{int(df_pubs['año_publicacion'].max())}",
)
c4.metric("Con DOI", df_pubs["doi"].notna().sum())

st.divider()

# ── Tabs ──────────────────────────────────────────────────────────────────────

tab1, tab2, tab3 = st.tabs(
    [
        "📚 Por especie",
        "🔍 Buscar publicaciones",
        "📋 Tabla completa",
    ]
)

# ── Tab 1: Por especie ────────────────────────────────────────────────────────

with tab1:
    col_left, col_right = st.columns([1, 2])

    with col_left:
        st.subheader("Especies con literatura disponible")
        if not df_resumen.empty:
            for _, row in df_resumen.iterrows():
                especie = (row["especie_relacionada"] or row["especie_code"] or "—").title()
                st.markdown(
                    f"**{especie}** — {row['n_publicaciones']} pub. "
                    f"({row['año_min']}–{row['año_max']})"
                )

        st.divider()
        st.markdown("**Especies sin literatura en DB:**")
        especies_con_pubs = set(df_pubs["especie_code"].dropna())
        especies_all = set(SEARCH_TERMS.keys())
        sin_pubs = especies_all - especies_con_pubs
        for esp in sorted(sin_pubs):
            st.markdown(f"- {esp.replace('_', ' ')}")

    with col_right:
        st.subheader("Publicaciones por especie")
        especies_disp = sorted(df_pubs["especie_code"].dropna().unique())
        especie_sel = st.selectbox(
            "Seleccionar especie",
            options=["(todas)"] + list(especies_disp),
        )

        df_filtrado = (
            df_pubs if especie_sel == "(todas)" else df_pubs[df_pubs["especie_code"] == especie_sel]
        )

        for _, pub in df_filtrado.iterrows():
            tipo_icon = {"article": "📄", "report": "📊", "thesis": "🎓"}.get(
                pub.get("tipo_publicacion", ""), "📄"
            )
            with st.expander(
                f"{tipo_icon} {pub['titulo'][:90]}{'...' if len(pub['titulo']) > 90 else ''}"
            ):
                if pub.get("autores"):
                    st.markdown(f"**Autores:** {pub['autores']}")
                if pub.get("año_publicacion"):
                    st.markdown(f"**Año:** {int(pub['año_publicacion'])}")
                if pub.get("abstract"):
                    st.markdown(f"**Resumen:** {pub['abstract']}")
                if pub.get("keywords"):
                    st.markdown(f"**Palabras clave:** {pub['keywords']}")
                cols_link = st.columns(2)
                if pub.get("doi"):
                    cols_link[0].markdown(f"[DOI: {pub['doi']}](https://doi.org/{pub['doi']})")
                if pub.get("url"):
                    cols_link[1].markdown(f"[Ver en repositorio]({pub['url']})")

# ── Tab 2: Buscar ─────────────────────────────────────────────────────────────

with tab2:
    st.subheader("Buscar publicaciones en CONICET Digital")
    st.info(
        "La búsqueda online requiere conexión a CONICET Digital (ri.conicet.gov.ar). "
        "Los resultados se guardan en la base de datos local para uso offline."
    )

    col_q, col_btn = st.columns([3, 1])
    with col_q:
        query_input = st.text_input(
            "Término de búsqueda",
            placeholder="ej: Merluccius hubbsi stock assessment",
        )
    with col_btn:
        st.markdown("<br>", unsafe_allow_html=True)
        buscar = st.button("🔍 Buscar en CONICET", type="primary")

    if buscar and query_input:
        with st.spinner(f"Buscando '{query_input}' en CONICET Digital..."):
            resultados = scraper.search_conicet(query_input, limit=10)
            if resultados:
                n_nuevas = scraper.save_publicaciones(resultados)
                st.success(
                    f"Encontradas {len(resultados)} publicaciones ({n_nuevas} nuevas guardadas)"
                )
                for pub in resultados:
                    with st.expander(pub.titulo[:100]):
                        if pub.autores:
                            st.markdown(f"**Autores:** {pub.autores}")
                        if pub.año_publicacion:
                            st.markdown(f"**Año:** {pub.año_publicacion}")
                        if pub.abstract:
                            st.markdown(f"**Resumen:** {pub.abstract[:500]}")
            else:
                st.warning(
                    "No se encontraron resultados. Puede que CONICET Digital no esté disponible."
                )

    st.divider()
    st.subheader("Buscar automáticamente por especie")
    especie_auto = st.selectbox(
        "Especie",
        options=list(SEARCH_TERMS.keys()),
        format_func=lambda x: x.replace("_", " ").title(),
    )
    if st.button("📥 Descargar publicaciones de esta especie"):
        terms = SEARCH_TERMS.get(especie_auto, [])
        total_nuevas = 0
        with st.spinner(f"Buscando publicaciones sobre {especie_auto}..."):
            for term in terms:
                pubs = scraper.search_conicet(term, limit=10, especie_code=especie_auto)
                total_nuevas += scraper.save_publicaciones(pubs)
        st.success(f"{total_nuevas} publicaciones nuevas guardadas para {especie_auto}")

# ── Tab 3: Tabla completa ─────────────────────────────────────────────────────

with tab3:
    st.subheader("Todas las publicaciones")

    col_f1, col_f2 = st.columns(2)
    with col_f1:
        tipo_filtro = st.multiselect(
            "Tipo",
            options=df_pubs["tipo_publicacion"].dropna().unique().tolist(),
            default=[],
        )
    with col_f2:
        año_range = st.slider(
            "Rango de años",
            min_value=int(df_pubs["año_publicacion"].min()),
            max_value=int(df_pubs["año_publicacion"].max()),
            value=(
                int(df_pubs["año_publicacion"].min()),
                int(df_pubs["año_publicacion"].max()),
            ),
        )

    df_show = df_pubs.copy()
    if tipo_filtro:
        df_show = df_show[df_show["tipo_publicacion"].isin(tipo_filtro)]
    df_show = df_show[df_show["año_publicacion"].between(año_range[0], año_range[1])]

    cols_show = [
        c
        for c in [
            "titulo",
            "autores",
            "año_publicacion",
            "especie_relacionada",
            "tipo_publicacion",
            "doi",
            "repositorio",
        ]
        if c in df_show.columns
    ]
    st.dataframe(df_show[cols_show], width="stretch", hide_index=True)
    st.caption(f"{len(df_show)} publicaciones mostradas")

    csv = df_show.to_csv(index=False)
    st.download_button(
        "⬇️ Descargar CSV",
        data=csv,
        file_name="publicaciones_cientificas.csv",
        mime="text/csv",
    )
