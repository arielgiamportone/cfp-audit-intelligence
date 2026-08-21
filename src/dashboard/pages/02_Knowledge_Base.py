"""
Página de Knowledge Base: búsqueda semántica y procesamiento de documentos.
"""

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(ROOT))

from src.dashboard._ui import page_header_raw

page_header_raw(
    "🔍 Knowledge Base Semántica", "Búsqueda inteligente sobre el corpus completo de actas del CFP"
)

from src.config_loader import get_kb_dir
from src.knowledge_base.vector_store import CFPVectorStore

KB_DIR = get_kb_dir()
PROCESSED_DIR = ROOT / "data" / "processed"

# ── Estado de la KB ───────────────────────────────────────────────────────────


@st.cache_resource
def get_vector_store():
    return CFPVectorStore(persist_dir=KB_DIR)


try:
    vs = get_vector_store()
    count = vs.count()
except Exception:
    count = 0

if count == 0:
    st.info(
        "🔎 **Modo demo:** la búsqueda semántica requiere el corpus de actas indexado en la "
        "Knowledge Base (embeddings), que se construye con el pipeline. Esta función se muestra "
        "en el vídeo del proyecto y puede reproducirse en local (ver `docs/TFM_DEPLOY.md`). "
        "Mientras tanto, explora **🔬 Comparador CFP vs INIDEP**, que ya tiene datos cargados.",
        icon="ℹ️",
    )
    st.stop()

st.success(f"Knowledge Base activa: **{count:,}** resoluciones indexadas")

st.markdown("---")

# ── Búsqueda semántica ────────────────────────────────────────────────────────

st.subheader("Búsqueda Semántica")

col_q, col_filters = st.columns([3, 1])

with col_q:
    query = st.text_input(
        "Consulta en lenguaje natural",
        placeholder="Ej: cuota de merluza 2018, vedas langostino, habilitación buque congelador...",
    )

with col_filters:
    n_results = st.slider("Resultados", 5, 20, 10)
    year_from_f = st.number_input("Desde año", 1998, 2025, 1998, key="kb_year_from")
    year_to_f = st.number_input("Hasta año", 1998, 2025, 2025, key="kb_year_to")
    _TIPO_LABELS = {
        "Todos": "Todos",
        "cuota_captura": "Cuota de captura",
        "veda": "Veda",
        "habilitacion_buque": "Habilitación de buque",
        "area_protegida": "Área protegida",
        "convenio_internacional": "Convenio internacional",
        "investigacion": "Investigación",
        "sancion": "Sanción",
    }
    tipo_filter = st.selectbox(
        "Tipo de resolución",
        list(_TIPO_LABELS.keys()),
        format_func=lambda x: _TIPO_LABELS.get(x, x.replace("_", " ").capitalize()),
    )

if query and count > 0:
    with st.spinner("Buscando..."):
        results = vs.search(
            query=query,
            n_results=n_results,
            year_from=year_from_f if year_from_f > 1998 else None,
            year_to=year_to_f if year_to_f < 2025 else None,
            tipo=tipo_filter if tipo_filter != "Todos" else None,
        )

    st.success(f"{len(results)} resultados encontrados")
    st.caption(
        "La **similitud** mide cuánto se parece cada resolución a tu consulta "
        "(100% = coincidencia máxima; se calcula sobre el significado, no las palabras exactas)."
    )
    st.markdown("---")

    for i, r in enumerate(results, 1):
        meta = r["metadata"]
        similarity = 1 - r["distance"]

        with st.expander(
            f"**[{i}]** Res. N° {meta.get('numero', '?')} / {meta.get('year', '?')} "
            f"— {meta.get('tipo', 'sin tipo').replace('_', ' ').title()} "
            f"| Similitud: {similarity:.0%}",
            expanded=i <= 3,
        ):
            col_meta, col_text = st.columns([1, 3])
            with col_meta:
                st.markdown(f"**Año:** {meta.get('year', 'N/D')}")
                st.markdown(f"**Tipo:** {meta.get('tipo', 'N/D')}")
                if meta.get("especies"):
                    st.markdown(f"**Especies:** {meta['especies']}")
                if meta.get("empresas"):
                    st.markdown(f"**Empresas:** {meta['empresas'][:100]}")
                st.markdown(f"**Archivo:** `{meta.get('acta_filename', 'N/D')}`")
            with col_text:
                st.markdown(r["texto"][:800] + ("..." if len(r["texto"]) > 800 else ""))

elif query and count == 0:
    st.error("La Knowledge Base está vacía. Ejecuta primero el pipeline de procesamiento.")

st.markdown("---")

# ── Construcción de KB ────────────────────────────────────────────────────────

with st.expander("Construir / Reconstruir Knowledge Base"):
    st.warning(
        "Esta operación procesa los JSONs de resoluciones y genera embeddings. "
        "Puede tomar varios minutos."
    )
    json_dir = PROCESSED_DIR / "json"

    if json_dir.exists():
        json_count = len(list(json_dir.rglob("*.json")))
        st.info(f"JSONs disponibles para indexar: {json_count}")
    else:
        st.error(f"Directorio {json_dir} no existe. Ejecuta primero el procesamiento de PDFs.")
        json_count = 0

    overwrite = st.checkbox("Reindexar desde cero (eliminar índice existente)", value=False)

    if st.button("Construir Knowledge Base", disabled=json_count == 0):
        with st.spinner("Generando embeddings e indexando..."):
            indexed = vs.index_from_json_dir(json_dir, overwrite=overwrite)
        st.success(f"Knowledge Base construida: {indexed:,} resoluciones indexadas")
        st.rerun()
