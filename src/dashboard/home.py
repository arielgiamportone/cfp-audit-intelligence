"""
CFP Audit Intelligence – Página de inicio (Home).

Pensada para que cualquier persona —también sin perfil técnico— entienda en 1 minuto
qué hace la plataforma y por dónde empezar. Se ejecuta como página dentro del router
de navegación (`app.py`), que ya fija `set_page_config` y el tema/marca.
"""

import sys
from pathlib import Path

import streamlit as st

# Robustez si se ejecutara de forma aislada (el router ya deja src en el path).
ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ── Hero ───────────────────────────────────────────────────────────────────────

st.title("🐟 CFP Audit Intelligence")
st.subheader("¿Se reparten las cuotas de pesca respetando lo que dice la ciencia?")
st.caption(
    "Plataforma que usa IA para auditar 25+ años de actas públicas del Consejo Federal "
    "Pesquero de Argentina y contrastarlas con la recomendación científica."
)

st.info(
    "🎓 **Demo del Trabajo Final de Máster.** Esta versión pública trae **datos verificados "
    "ya cargados** para que puedas explorar el sistema. El corpus histórico completo "
    "(cientos de actas) se construye con el pipeline — ver README del repositorio.",
    icon="ℹ️",
)

st.markdown("---")

# ── ¿Qué es esto? (lenguaje llano) ─────────────────────────────────────────────

col_left, col_right = st.columns([3, 2])

with col_left:
    st.subheader("¿Qué es esto, en simple?")
    st.markdown("""
    Cada año, un organismo del Estado (**el CFP**) decide **cuánto se puede pescar** de cada
    especie. Los científicos (**INIDEP**) recomiendan un límite seguro para no agotar el recurso.

    **La pregunta clave:** ¿la cantidad que autoriza la política (CFP) respeta ese límite
    científico? Revisar eso a mano en miles de páginas de actas es inviable.

    **Esta plataforma lo automatiza:** extrae las actas públicas, las analiza con IA y las
    compara con la ciencia y con la pesca realmente capturada, marcando con un **semáforo**
    cuándo se sobrepasan los límites.
    """)

with col_right:
    st.subheader("Cómo funciona")
    st.markdown("""
    ```
    CIENCIA (INIDEP)      →  límite recomendado (CBA)
          │
          ▼
    POLÍTICA (CFP)        →  cuota aprobada (CMP)
          │
          ▼
    REALIDAD (SIPA)       →  captura real
          │
          ▼
       🚦 SEMÁFORO DE ALERTA
    ```
    """)

# ── Leyenda de alertas ─────────────────────────────────────────────────────────

st.subheader("El semáforo de sostenibilidad")
a1, a2, a3, a4 = st.columns(4)
a1.success("🟢 **Verde**\n\nDentro del límite científico (≤100%)")
a2.warning("🟡 **Amarillo**\n\nA vigilar (101–115%)")
a3.error("🔴 **Rojo**\n\nSobreasignación (116–130%)")
a4.error("⚫ **Crítico**\n\nRiesgo alto (>130%)")

st.markdown("---")

# ── Empieza por aquí (páginas con datos listos para explorar) ───────────────────

st.subheader("👉 Empieza por aquí")
st.caption("Estas páginas ya tienen datos cargados y son el corazón del proyecto:")

s1, s2, s3 = st.columns(3)
with s1:
    st.page_link("pages/05_INIDEP_Comparador.py", label="🔬 Comparador CFP vs INIDEP",
                 help="El análisis estrella: ciencia vs política, con semáforo de alertas")
    st.page_link("pages/08_Alertas.py", label="🚨 Sistema de Alertas",
                 help="Alertas configurables sobre las decisiones del CFP")
with s2:
    st.page_link("pages/12_Capturas.py", label="🐟 Capturas reales (SIPA)",
                 help="Cuánto se pescó realmente por especie y año")
    st.page_link("pages/06_Timeline.py", label="📈 Timeline por especie",
                 help="Evolución histórica de cuotas")
with s3:
    st.page_link("pages/10_FAO_FIRMS.py", label="🌎 Contexto FAO",
                 help="Comparativa internacional de capturas y estado de stocks")
    st.page_link("pages/11_CONICET.py", label="📚 Ciencia CONICET",
                 help="Publicaciones científicas por especie")

# ── Estado del sistema (métricas del corpus) ───────────────────────────────────

st.markdown("---")
st.subheader("Estado del corpus de actas")

from src.config_loader import get_db_path
db_path = get_db_path()
loaded = False
if db_path.exists():
    try:
        from src.acquisition.catalog_manager import CatalogManager

        stats = CatalogManager(db_path).stats()
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Total actas", stats["total"])
        c2.metric("PDFs descargados", stats["downloaded"])
        c3.metric("Textos extraídos", stats["processed"])
        c4.metric("Indexadas (KB)", stats["embedded"])
        c5.metric("Analizadas con IA", stats["analyzed"])
        loaded = stats.get("total", 0) > 0
    except Exception:
        pass

if not loaded:
    st.caption(
        "📦 En esta demo el corpus completo de actas no está cargado (se genera con el "
        "pipeline). Las páginas de **Adquisición**, **Knowledge Base** y **Auditoría IA** "
        "requieren ese corpus; su funcionamiento se muestra en el vídeo del proyecto y "
        "puede reproducirse en local (ver `docs/TFM_DEPLOY.md`)."
    )

# ── Glosario para no expertos ──────────────────────────────────────────────────

with st.expander("📖 Glosario rápido (términos que verás en la app)"):
    st.markdown("""
    | Término | Qué significa |
    |---|---|
    | **CFP** | Consejo Federal Pesquero: el organismo que **decide** las cuotas de pesca (política). |
    | **INIDEP** | Instituto de investigación pesquera: **recomienda** los límites (ciencia). |
    | **CBA** | *Captura Biológicamente Aceptable*: el límite **seguro** que sugiere la ciencia. |
    | **CMP** | *Captura Máxima Permisible*: la cuota que **aprueba** el CFP. |
    | **SIPA** | Sistema de información de pesca: lo que **realmente** se capturó. |
    | **Cuota / Veda** | Cantidad autorizada a pescar / prohibición temporal de pesca. |
    | **Alerta** | Semáforo que indica si la cuota (CMP) supera el límite científico (CBA). |
    """)

# ── Para desarrolladores / evaluadores ─────────────────────────────────────────

with st.expander("🛠️ Para desarrolladores y evaluadores (arquitectura y calidad)"):
    st.markdown("""
    - **Arquitectura por capas:** adquisición → procesamiento → knowledge base → análisis+IA → dashboard/API.
    - **IA:** RAG con ChromaDB + embeddings multilingües y auditoría con Claude API (*prompt caching*).
    - **Calidad:** 945 tests, CI (ruff + pytest), Docker, y **ADRs 001–012** documentando cada decisión.
    - **IA responsable:** Model Card + Datasheet + marcado `[BAJA_EVIDENCIA]` para hallazgos sin anclaje textual.
    - **Repositorio:** [github.com/arielgiamportone/cfp-audit-intelligence](https://github.com/arielgiamportone/cfp-audit-intelligence)
    """)

st.markdown("---")
st.caption(
    "🇦🇷 Por la soberanía y sostenibilidad de los recursos pesqueros argentinos · "
    "Los hallazgos son descriptivos y requieren verificación · "
    "Fuente: [cfp.gob.ar](https://cfp.gob.ar)"
)
