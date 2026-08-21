"""Página 9 — Reporte PDF Ejecutivo."""

from datetime import datetime

import streamlit as st

from src.dashboard._ui import import_guard, page_header_raw

page_header_raw("📄 Reporte PDF Ejecutivo")
st.markdown("Genera un informe ejecutivo en PDF con todos los hallazgos de auditoría.")

st.info(
    "📄 **Modo demo:** el reporte se construye a partir del corpus y los análisis cargados. "
    "En esta demo pública el corpus completo no está poblado, por lo que el PDF puede salir con "
    "secciones limitadas; la versión completa se muestra en el vídeo (ver `docs/TFM_DEPLOY.md`).",
    icon="ℹ️",
)

with import_guard("La generación de PDF"):
    from src.analysis.report_generator import CFPReportGenerator

from src.config_loader import get_db_path

DB_PATH = get_db_path()

# ── Configuración del reporte ─────────────────────────────────────────────────

with st.expander("⚙️ Configuración del reporte", expanded=True):
    col1, col2 = st.columns(2)
    with col1:
        title = st.text_input(
            "Título del reporte",
            value="Auditoría CFP — Informe Ejecutivo",
        )
        author = st.text_input("Autor / Sistema", value="CFP Audit Intelligence")
    with col2:
        year_min = st.number_input(
            "Período desde (año)", value=1998, min_value=1990, max_value=2030
        )
        year_max = st.number_input(
            "Período hasta (año)",
            value=datetime.now().year,
            min_value=1990,
            max_value=2030,
        )

periodo = f"{year_min}–{year_max}"

# ── Secciones incluidas ───────────────────────────────────────────────────────

st.markdown("**Secciones incluidas en el reporte:**")
col_sec = st.columns(3)
sections = [
    "✅ Portada con metadata",
    "✅ Resumen ejecutivo + métricas",
    "✅ Alertas de sostenibilidad activas",
    "✅ Comparación CMP vs CBA (INIDEP)",
    "✅ Top empresas y especies",
    "✅ Metodología y fuentes",
]
for i, sec in enumerate(sections):
    col_sec[i % 3].markdown(sec)

st.divider()

# ── Generación ────────────────────────────────────────────────────────────────

if not DB_PATH.exists():
    st.warning("Base de datos no encontrada. Ejecuta el pipeline primero.")
    st.stop()

if st.button("📥 Generar y descargar PDF", type="primary", width="stretch"):
    with st.spinner("Generando reporte PDF..."):
        try:
            gen = CFPReportGenerator(db_path=DB_PATH)
            pdf_bytes = gen.generate(title=title, periodo=periodo, author=author)

            filename = f"cfp_reporte_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
            st.success(f"Reporte generado: {len(pdf_bytes):,} bytes")
            st.download_button(
                label="⬇️ Descargar PDF",
                data=pdf_bytes,
                file_name=filename,
                mime="application/pdf",
                width="stretch",
            )
        except Exception as e:
            st.error(
                "No se pudo generar el reporte. Verifica que el corpus esté cargado; "
                "si el problema persiste, revisa el detalle técnico.",
                icon="⚠️",
            )
            with st.expander("🛠️ Detalle técnico del error"):
                st.exception(e)

st.divider()

# ── Vista previa de secciones ─────────────────────────────────────────────────

st.subheader("📊 Vista previa de datos incluidos")

if DB_PATH.exists():
    gen = CFPReportGenerator(db_path=DB_PATH)
    stats = gen._get_stats()
    alertas = gen._get_alertas_criticas()
    comparaciones = gen._get_comparaciones()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Actas CFP", f"{stats['total_actas']:,}")
    c2.metric("Resoluciones", f"{stats['total_resoluciones']:,}")
    c3.metric("Alertas activas", len(alertas))
    c4.metric("Comparaciones CFP/INIDEP", len(comparaciones))

    if alertas:
        st.markdown("**Alertas que se incluirán:**")
        import pandas as pd

        df_alertas = pd.DataFrame([dict(a) for a in alertas[:10]])
        cols_show = [
            c
            for c in ["severidad", "tipo", "especie", "zona", "year", "mensaje"]
            if c in df_alertas.columns
        ]
        st.dataframe(df_alertas[cols_show], width="stretch", hide_index=True)

    if comparaciones:
        st.markdown("**Comparaciones CFP vs INIDEP que se incluirán:**")
        import pandas as pd

        df_comp = pd.DataFrame([dict(c) for c in comparaciones])
        cols_comp = [
            c
            for c in [
                "especie",
                "zona",
                "year",
                "cba_inidep_tn",
                "cmp_cfp_tn",
                "ratio_sobreasignacion",
                "nivel_alerta",
            ]
            if c in df_comp.columns
        ]
        st.dataframe(df_comp[cols_comp], width="stretch", hide_index=True)
