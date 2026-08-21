"""
FisheriesAudit ALG — Hub de Investigación y Publicación.

Dashboard para generar outputs científicos publicables:
  - Figuras matplotlib 300 dpi
  - Tablas LaTeX
  - CSV/Excel estructurados (FAIR)
  - Tests estadísticos formales
  - Posts LinkedIn — Serie FisheriesAudit ALG 2026
"""

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from src.dashboard._ui import import_guard, page_header_raw

page_header_raw(
    "🧪 FisheriesAudit ALG — Hub de Investigación",
    "Serie FisheriesAudit ALG 2026 · Gobernanza Pesquera Argentina · "
    "Ariel L. Giamportone · Ing. Pesquero | Data Scientist",
)

with import_guard("El hub de investigación (figuras/exportación)"):
    from src.analysis.inidep_comparator import INIDEPComparator
    from src.analysis.linkedin_formatter import LinkedInFormatter
    from src.analysis.research_exporter import ResearchExporter

st.info(
    "Genera outputs científicos publicables directamente desde los datos de la plataforma: "
    "figuras publication-ready, tablas LaTeX, tests estadísticos, datasets FAIR y posts LinkedIn.",
    icon="ℹ️",
)

from src.config_loader import get_db_path

DB_PATH = get_db_path()
OUT_DIR = Path("outputs/FisheriesAudit_ALG")


@st.cache_resource
def get_comparator():
    comp = INIDEPComparator(DB_PATH)
    comp.compute_comparisons()
    return comp


@st.cache_resource
def get_exporter(_comp):
    return ResearchExporter(_comp, output_dir=OUT_DIR)


comp = get_comparator()
exp = get_exporter(comp)

tab_figs, tab_tests, tab_datos, tab_linkedin, tab_latex = st.tabs(
    ["📊 Figuras", "🧪 Tests estadísticos", "💾 Exportar datos", "💼 Posts LinkedIn", "📄 LaTeX"]
)

# ─────────────────────────────────────────────
# TAB 1 — FIGURAS
# ─────────────────────────────────────────────
with tab_figs:
    st.subheader("Figuras publication-ready (300 dpi PNG + SVG)")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("#### Triángulo de auditoría por especie")
        df_all = comp.get_triangulo_completo()
        especies_disponibles = (
            df_all["especie_code"].dropna().unique().tolist() if not df_all.empty else []
        )
        if especies_disponibles:
            especie_sel = st.selectbox("Seleccionar especie", especies_disponibles)
            if st.button("Generar figura triángulo", key="btn_triangulo"):
                with st.spinner("Generando figura..."):
                    try:
                        fig = exp.figura_triangulo_por_especie(especie_sel, save=True)
                        st.pyplot(fig)
                        png_path = OUT_DIR / "figuras" / f"triangulo_{especie_sel}.png"
                        if png_path.exists():
                            with open(png_path, "rb") as f:
                                st.download_button(
                                    "⬇ Descargar PNG (300 dpi)",
                                    f,
                                    file_name=png_path.name,
                                    mime="image/png",
                                )
                    except Exception as e:
                        st.error(f"Error: {e}")
        else:
            st.warning("Sin datos de triángulo disponibles.")

    with col2:
        st.markdown("#### Scatter diagnóstico — todas las especies")
        if st.button("Generar scatter multi-especie", key="btn_scatter"):
            with st.spinner("Generando figura..."):
                try:
                    fig = exp.figura_comparacion_todas_especies(save=True)
                    st.pyplot(fig)
                    png_path = OUT_DIR / "figuras" / "scatter_todas_especies.png"
                    if png_path.exists():
                        with open(png_path, "rb") as f:
                            st.download_button(
                                "⬇ Descargar PNG (300 dpi)",
                                f,
                                file_name=png_path.name,
                                mime="image/png",
                            )
                except Exception as e:
                    st.error(f"Error: {e}")

    st.markdown("---")
    st.markdown("#### Heatmap de alertas — especie × año")
    if st.button("Generar heatmap alertas", key="btn_heatmap"):
        with st.spinner("Generando figura..."):
            try:
                fig = exp.figura_alertas_heatmap(save=True)
                st.pyplot(fig)
                png_path = OUT_DIR / "figuras" / "heatmap_alertas.png"
                if png_path.exists():
                    with open(png_path, "rb") as f:
                        st.download_button(
                            "⬇ Descargar PNG (300 dpi)",
                            f,
                            file_name=png_path.name,
                            mime="image/png",
                        )
            except Exception as e:
                st.error(f"Error: {e}")

    st.markdown("---")
    if st.button("🔄 Generar TODAS las figuras y exportar", key="btn_all"):
        with st.spinner("Exportando todo..."):
            resultados = exp.exportar_todo()
            st.success(f"✅ Exportación completa en `{OUT_DIR}/`")
            for k, v in resultados.items():
                st.write(f"- **{k}**: `{v}`")

# ─────────────────────────────────────────────
# TAB 2 — TESTS ESTADÍSTICOS
# ─────────────────────────────────────────────
with tab_tests:
    st.subheader("Tests estadísticos formales")
    st.caption("Resultados para incluir en sección 'Resultados' de publicaciones científicas.")

    if st.button("Ejecutar batería de tests estadísticos", key="btn_tests"):
        with st.spinner("Corriendo tests..."):
            import pandas as pd

            tests = exp.ejecutar_todos_los_tests()
            rows = [t.to_dict() for t in tests]
            df_tests = pd.DataFrame(rows)

            def _color_sig(val):
                if val is True:
                    return "background-color: #c8e6c9"
                elif val is False:
                    return "background-color: #ffcdd2"
                return ""

            st.dataframe(
                df_tests.style.applymap(_color_sig, subset=["significativo"]),
                width="stretch",
                height=400,
            )

            st.markdown("---")
            st.subheader("Interpretación de hallazgos")
            hallazgos = exp.generar_hallazgos()
            for h in hallazgos:
                nivel_color = {
                    "alto": "🟢",
                    "medio": "🟡",
                    "exploratorio": "⚪",
                }.get(h.nivel_evidencia, "⚪")

                with st.expander(f"{nivel_color} {h.titulo} — evidencia {h.nivel_evidencia}"):
                    st.markdown(h.descripcion)
                    st.markdown("**Datos clave:**")
                    for k, v in h.datos_clave.items():
                        st.write(f"- {k}: **{v}**")
                    if h.tests:
                        st.markdown("**Tests:**")
                        for t in h.tests:
                            sig = "✅ p<0.05" if t.significativo else f"p={t.p_value:.4f}"
                            st.write(f"- {t.nombre}: {sig} — {t.interpretacion}")
                    if h.fuentes:
                        st.caption("Fuentes: " + " | ".join(h.fuentes))

# ─────────────────────────────────────────────
# TAB 3 — EXPORTAR DATOS
# ─────────────────────────────────────────────
with tab_datos:
    st.subheader("Exportar datasets (FAIR)")
    st.caption(
        "CSV y Excel estructurados con metadatos para depósito en Zenodo / Hugging Face Datasets."
    )

    col1, col2 = st.columns(2)

    with col1:
        if st.button("📥 Exportar CSV (triángulo de auditoría)", key="btn_csv"):
            with st.spinner("Generando CSV..."):
                path = exp.exportar_csv()
                with open(path, "rb") as f:
                    st.download_button(
                        "⬇ Descargar CSV",
                        f,
                        file_name="FisheriesAudit_ALG_triangulo.csv",
                        mime="text/csv",
                    )
                st.success(f"CSV generado: {len(comp.get_triangulo_completo())} registros")

    with col2:
        if st.button("📥 Exportar Excel (multi-hoja)", key="btn_excel"):
            with st.spinner("Generando Excel..."):
                path = exp.exportar_excel()
                with open(path, "rb") as f:
                    st.download_button(
                        "⬇ Descargar Excel",
                        f,
                        file_name="FisheriesAudit_ALG_datos.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )
                st.success(
                    "Excel generado: 6 hojas (triángulo, alertas, INIDEP, CFP, SAGPyA, tests)"
                )

    st.markdown("---")
    st.subheader("Vista previa del dataset")
    df_preview = comp.get_triangulo_completo()
    if not df_preview.empty:
        st.dataframe(df_preview, width="stretch", height=300)
        st.caption(
            f"{len(df_preview)} registros · "
            "Fuentes: INIDEP Mar Abierto + CFP Actas Públicas + SAGPyA/SIPA"
        )
    else:
        st.info("Sin datos disponibles. Ejecutá el pipeline primero.")

# ─────────────────────────────────────────────
# TAB 4 — POSTS LINKEDIN
# ─────────────────────────────────────────────
with tab_linkedin:
    st.subheader("Serie FisheriesAudit ALG 2026 — Posts LinkedIn")
    st.caption(
        "Posts estructurados para perfil personal (Ariel Giamportone) y comunidad Pesqueros en IA."
    )

    hallazgos = exp.generar_hallazgos()
    formatter = LinkedInFormatter(hallazgos, numero_entrega_inicial=1)
    todos_posts = formatter.generar_todos()

    perfil_sel = st.radio(
        "Perfil destino",
        ["personal", "pesqueros_ia"],
        format_func=lambda x: (
            "👤 Ariel Giamportone (personal)" if x == "personal" else "🐟 Pesqueros en IA"
        ),
        horizontal=True,
    )

    posts = todos_posts[perfil_sel]

    for i, post in enumerate(posts):
        with st.expander(
            f"📝 Entrega #{post.numero_entrega:02d} — {post.titulo}", expanded=(i == 0)
        ):
            col_preview, col_copy = st.columns([3, 1])
            with col_preview:
                texto = post.render()
                st.text_area(
                    "Texto del post",
                    value=texto,
                    height=400,
                    key=f"post_{perfil_sel}_{i}",
                    label_visibility="collapsed",
                )
            with col_copy:
                st.metric("Caracteres", len(texto))
                st.metric("Hashtags", len(post.hashtags))
                if len(texto) > 3000:
                    st.warning("⚠️ LinkedIn limita a ~3000 caracteres.")
                else:
                    st.success("✅ Longitud OK")
                st.caption(f"Nivel evidencia: {post.emoji_tema}")

                short = post.render_corto()
                st.text_area(
                    "Versión corta (comentarios)",
                    value=short,
                    height=150,
                    key=f"short_{perfil_sel}_{i}",
                )

# ─────────────────────────────────────────────
# TAB 5 — LATEX
# ─────────────────────────────────────────────
with tab_latex:
    st.subheader("Tablas LaTeX para publicaciones científicas")

    col1, col2 = st.columns([1, 3])
    with col1:
        df_all = comp.get_triangulo_completo()
        opciones_esp = ["Todas las especies"] + (
            df_all["especie_code"].dropna().unique().tolist() if not df_all.empty else []
        )
        esp_latex = st.selectbox("Filtrar por especie", opciones_esp, key="esp_latex")
        esp_code = None if esp_latex == "Todas las especies" else esp_latex

    with col2:
        if st.button("Generar tabla LaTeX", key="btn_latex"):
            try:
                latex = exp.exportar_tabla_latex(esp_code)
                st.code(latex, language="latex")
                st.download_button(
                    "⬇ Descargar .tex",
                    latex,
                    file_name="tabla_triangulo_auditoria.tex",
                    mime="text/plain",
                )
            except Exception as e:
                st.error(f"Error: {e}")

    st.markdown("---")
    st.markdown(
        """
**Instrucciones para incluir en manuscrito:**

```latex
\\usepackage{booktabs}   % en el preámbulo (opcional pero recomendado)
\\input{tabla_triangulo_auditoria.tex}
```

**Cita sugerida (APA):**
> Giamportone, A. L. (2026). *FisheriesAudit ALG: Plataforma de auditoría inteligente
> de actas del Consejo Federal Pesquero de Argentina (1998–2025)* [Software].
> GitHub. https://github.com/arielgiamportone/cfp-audit-intelligence
"""
    )

st.markdown("---")
st.caption(
    "FisheriesAudit ALG 2026 · Ariel L. Giamportone · "
    "Ingeniero Pesquero | Docente Investigador | Data Scientist · "
    "Datos: INIDEP, CFP, SAGPyA (fuentes públicas)"
)
