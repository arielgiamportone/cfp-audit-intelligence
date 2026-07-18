"""
Dashboard de Evaluación y Validación del Sistema de Auditoría CFP.

Permite:
  - Anotar resoluciones manualmente (Tab 1)
  - Ver métricas P/R/F1/kappa del sistema vs. experto humano (Tab 2)
  - Exportar/importar anotaciones en CSV para trabajo offline (Tab 3)
  - Consultar el análisis de sensibilidad de umbrales (Tab 4)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import sqlite3

import pandas as pd
import streamlit as st

from src.config_loader import get_db_path
DB_PATH = get_db_path()

from src.dashboard._ui import page_header_raw
page_header_raw("🔬 Evaluación y Validación del Sistema de Auditoría")

st.info(
    "**Rigor metodológico**: este módulo permite validar el audit_engine contra anotaciones "
    "humanas de expertos del dominio pesquero. Sin este benchmark, los hallazgos del sistema "
    "valen tanto como una opinión bien presentada."
)

if not DB_PATH.exists():
    st.info(
        "📦 Esta página valida el motor contra el corpus de actas, que en la demo no "
        "está cargado. Reproduce el pipeline en local — ver `docs/TFM_DEPLOY.md`.",
        icon="ℹ️",
    )
    st.stop()

try:
    from src.analysis.sensitivity_analyzer import SensitivityAnalyzer
    from src.evaluation.annotation_protocol import seed_gold_set
    from src.evaluation.evaluator import GroundTruthEvaluator
except ImportError as e:
    st.error(f"Error importando módulos de evaluación: {e}")
    st.stop()

@st.cache_resource
def get_evaluator():
    return GroundTruthEvaluator(DB_PATH)

@st.cache_resource
def get_sensitivity():
    return SensitivityAnalyzer(DB_PATH)

evaluator = get_evaluator()
sensitivity = get_sensitivity()

tab1, tab2, tab3, tab4 = st.tabs([
    "📝 Anotar Resoluciones",
    "📊 Métricas del Sistema",
    "⬆️ Export / Import",
    "🎚️ Sensibilidad de Umbrales",
])

# ─── Tab 1: Anotar ───────────────────────────────────────────────────────────
with tab1:
    st.header("Anotación de Resoluciones")
    st.markdown(
        "Anote manualmente la categoría de riesgo de cada resolución. "
        "Sus anotaciones se compararán con las del sistema para calcular métricas."
    )

    anotador = st.text_input(
        "Su nombre/identificador como anotador:",
        value="experto_1",
        help="Use el mismo identificador en todas sus sesiones",
    )

    # Cargar resoluciones pendientes de anotación
    try:
        with sqlite3.connect(DB_PATH) as conn:
            df_res = pd.read_sql_query(
                """
                SELECT r.id, r.numero, r.tipo, r.fecha, r.riesgo_score,
                       r.categoria as categoria_ia,
                       substr(r.texto_completo, 1, 800) as texto_preview,
                       a.year as acta_year
                FROM resoluciones r
                JOIN actas a ON r.acta_id = a.id
                WHERE r.analisis_ia IS NOT NULL
                  AND r.id NOT IN (
                      SELECT resolucion_id FROM anotaciones_humanas
                      WHERE anotador = ?
                  )
                ORDER BY r.riesgo_score DESC NULLS LAST
                LIMIT 20
                """,
                conn,
                params=(anotador,),
            )
    except Exception:
        df_res = pd.DataFrame()

    if df_res.empty:
        gold_df = evaluator.get_gold_set()
        if not gold_df.empty:
            st.success("✅ No hay resoluciones del pipeline pendientes. Mostrando gold set sintético.")
            df_res = gold_df[["resolucion_id", "categoria_humana", "texto_completo"]].head(5).copy()
            df_res.columns = ["id", "categoria_ia", "texto_preview"]
            df_res["tipo"] = "gold_set"
            df_res["riesgo_score"] = None
        else:
            st.info("No hay resoluciones analizadas disponibles.")
            st.markdown("**Para generar resoluciones analizadas:**")
            st.code("python scripts/run_full_pipeline.py --step audit --limit 50")
            st.stop()

    st.markdown(f"**{len(df_res)} resoluciones pendientes de anotación por '{anotador}'**")

    idx = st.number_input("Resolución #", min_value=0, max_value=len(df_res) - 1, value=0)
    row = df_res.iloc[idx]

    with st.expander("📄 Texto de la resolución", expanded=True):
        st.text_area("Texto:", value=str(row.get("texto_preview", "")), height=200, disabled=True)

    col1, col2 = st.columns(2)
    with col1:
        st.metric("Score IA", f"{row.get('riesgo_score', 'N/D')}")
        st.metric("Categoría IA", str(row.get("categoria_ia", "N/D")))
    with col2:
        categoria_humana = st.selectbox(
            "Su evaluación:",
            ["bajo", "medio", "alto", "critico"],
            help="Categoría de riesgo según su criterio experto",
        )
        riesgo_humano = st.slider("Score de riesgo (0-100):", 0, 100, 50)

    notas = st.text_area("Notas / justificación (opcional):", height=80)
    confianza = st.slider("Confianza en su anotación (%):", 50, 100, 80)

    if st.button("💾 Guardar anotación", type="primary"):
        try:
            from src.acquisition.catalog_manager import CatalogManager
            cm = CatalogManager(DB_PATH)
            cm.upsert_anotacion(
                resolucion_id=int(row["id"]),
                anotador=anotador,
                categoria_ia=str(row.get("categoria_ia")) if row.get("categoria_ia") else None,
                categoria_humana=categoria_humana,
                riesgo_score_ia=float(row["riesgo_score"]) if row.get("riesgo_score") else None,
                riesgo_score_humano=riesgo_humano,
                notas=notas or None,
                confianza_pct=confianza,
            )
            st.success(f"✅ Anotación guardada para resolución #{int(row['id'])}")
            st.cache_resource.clear()
        except Exception as exc:
            st.error(f"Error guardando: {exc}")

# ─── Tab 2: Métricas ─────────────────────────────────────────────────────────
with tab2:
    st.header("Métricas de Evaluación")

    col_a, col_b = st.columns([2, 1])
    with col_b:
        if st.button("🔄 Recalcular métricas"):
            st.cache_resource.clear()
            st.rerun()

    metrics = evaluator.compute_metrics()

    if "error" in metrics:
        st.warning(f"⚠️ {metrics['error']}")
        st.markdown(
            "**Para calcular métricas:** anote al menos 10 resoluciones en la pestaña anterior "
            "y asegúrese de que el campo `categoria_ia` esté completado en la base de datos."
        )

        # Mostrar gold set como referencia
        gold_df = evaluator.get_gold_set()
        if not gold_df.empty:
            st.subheader("Gold set sintético (demo)")
            st.dataframe(
                gold_df[["categoria_humana", "riesgo_score_humano", "notas"]].head(10),
                width="stretch",
            )
    else:
        # KPIs principales
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("N pares anotados", metrics["n_pares"])
        c2.metric("Accuracy", f"{metrics['accuracy']:.1%}")
        c3.metric("Cohen's κ", f"{metrics['cohen_kappa']:.3f}")
        c4.metric("Macro F1", f"{metrics['macro_f1']:.3f}")

        st.markdown(f"**Interpretación kappa**: {metrics['kappa_interpretacion']}")

        # Métricas por categoría
        st.subheader("Precisión / Recall / F1 por categoría")
        tabla_cat = pd.DataFrame(metrics["por_categoria"]).T
        st.dataframe(tabla_cat.style.format("{:.3f}"), width="stretch")

        # Distribución
        st.subheader("Distribución de categorías")
        col_l, col_r = st.columns(2)
        with col_l:
            st.write("**Sistema (IA)**")
            st.write(pd.Series(metrics["distribucion_ia"]).rename("count").to_frame())
        with col_r:
            st.write("**Experto humano**")
            st.write(pd.Series(metrics["distribucion_humana"]).rename("count").to_frame())

# ─── Tab 3: Export/Import ─────────────────────────────────────────────────────
with tab3:
    st.header("Export / Import para Trabajo Offline")

    st.markdown(
        "Exporte una muestra de resoluciones a CSV, compártala con el especialista "
        "(INIDEP, ex-CFP), y reimporte sus anotaciones cuando las complete."
    )

    col_exp, col_imp = st.columns(2)

    with col_exp:
        st.subheader("⬇️ Exportar para experto")
        n_export = st.number_input("Cantidad de resoluciones a exportar:", 10, 100, 30)
        if st.button("📥 Generar CSV de anotación"):
            try:
                import io as io_mod
                buf = io_mod.BytesIO()
                n = evaluator.export_for_expert(
                    Path("data/reports/muestra_anotacion.csv"), n=n_export
                )
                with open("data/reports/muestra_anotacion.csv", "rb") as f:
                    csv_bytes = f.read()
                st.download_button(
                    label=f"Descargar muestra ({n} resoluciones)",
                    data=csv_bytes,
                    file_name="cfp_muestra_para_anotacion.csv",
                    mime="text/csv",
                )
            except Exception as exc:
                st.warning(f"No se pudo exportar: {exc}. Asegúrese de ejecutar --step audit primero.")

    with col_imp:
        st.subheader("⬆️ Importar anotaciones del experto")
        nombre_experto = st.text_input("Nombre del anotador:", value="experto_inidep")
        archivo = st.file_uploader("CSV con anotaciones:", type=["csv"])
        if archivo and st.button("📤 Importar anotaciones"):
            try:
                n = evaluator.import_from_expert(archivo, anotador=nombre_experto)
                st.success(f"✅ Importadas {n} anotaciones de '{nombre_experto}'")
                st.cache_resource.clear()
            except ValueError as exc:
                st.error(f"Error de formato: {exc}")
            except Exception as exc:
                st.error(f"Error importando: {exc}")

    # Gold set sintético
    st.divider()
    st.subheader("🧪 Gold set sintético")
    st.markdown(
        "El gold set contiene 30 resoluciones demo con etiquetas calibradas "
        "por el desarrollador. **Deben ser reemplazadas por anotaciones de un experto real** "
        "antes de cualquier publicación académica."
    )
    if st.button("Sembrar gold set sintético en BD"):
        n = seed_gold_set(DB_PATH)
        st.success(f"✅ {n} resoluciones del gold set insertadas")

    gold_df = evaluator.get_gold_set()
    if not gold_df.empty:
        st.dataframe(
            gold_df[["categoria_humana", "riesgo_score_humano", "notas"]].head(10),
            width="stretch",
        )

# ─── Tab 4: Sensibilidad de Umbrales ─────────────────────────────────────────
with tab4:
    st.header("Sensibilidad de Umbrales CMP/CBA")

    st.markdown(
        "Analiza cómo cambian las alertas cuando los umbrales varían. "
        "Responde a la crítica: *'los umbrales 100/115/130% son arbitrarios'*."
    )

    # Literatura de justificación
    with st.expander("📚 Justificación bibliográfica de los umbrales actuales"):
        st.markdown(
            """
**100% (verde → amarillo)**
> Ley 24.922 Art. 9: la cuota de captura máxima permisible (CMP) no puede superar
> la captura máxima sostenible (CMS) recomendada por el INIDEP. Exceder el 100% es
> técnicamente una violación del principio precautorio del Artículo 9.

**115% (amarillo → rojo)**
> Bertolotti, M.I. et al. (2001). *Impacto económico de la actividad pesquera*.
> INIDEP Informe Técnico 47. Los autores documentaron que el desvío histórico
> promedio entre CMP aprobada por CFP y CBA recomendada por INIDEP fue ~15%.
> Este umbral identifica decisiones fuera de la tendencia histórica "normal".

**130% (rojo → crítico)**
> FAO (1995). *Code of Conduct for Responsible Fisheries*, Art. 7.2.1.
> La FAO establece que sobrepasar el MSY en más de un 30% constituye
> riesgo de colapso del stock. Este umbral se usa en gestión pesquera
> internacional como límite precautorio.
            """
        )

    stability = sensitivity.stability_report()

    if "error" in stability:
        st.warning(
            f"⚠️ {stability['error']}. Ejecutar el pipeline para generar datos de comparaciones."
        )
    else:
        config = stability["configuracion_actual"]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Umbral amarillo", f"{config['amarillo_min']:.0%}")
        c2.metric("Umbral rojo", f"{config['rojo_min']:.0%}")
        c3.metric("Umbral crítico", f"{config['critico_min']:.0%}")
        c4.metric("Variación máx ±5%", stability["max_variacion_criticos_pm5pct"])

        estable = stability["hallazgos_estables"]
        if estable:
            st.success("✅ Hallazgos estables: la variación ±5% de umbrales cambia ≤2 alertas críticas")
        else:
            st.warning("⚠️ Hallazgos sensibles a los umbrales: documentar en la sección de limitaciones")

        # Tabla de resultados por delta
        st.subheader("Variación de críticos según ±5% en umbrales")
        rows = []
        for k, v in stability["resultados_por_delta"].items():
            rows.append({
                "Delta": k,
                "Umbral amarillo": f"{v['amarillo_min']:.3f}",
                "Umbral rojo": f"{v['rojo_min']:.3f}",
                "Críticos": v.get("n_critico", 0),
                "Rojos": v.get("n_rojo", 0),
            })
        st.dataframe(pd.DataFrame(rows), width="stretch")

    # Grilla completa de sensibilidad
    st.subheader("Grilla de sensibilidad (grilla completa)")
    if st.button("🔄 Calcular grilla de sensibilidad"):
        with st.spinner("Calculando..."):
            df_grid = sensitivity.analyze_cba_thresholds(
                amarillo_range=(0.00, 0.20),
                rojo_range=(0.10, 0.40),
                step=0.05,
            )
        if not df_grid.empty:
            st.dataframe(df_grid.style.background_gradient(subset=["pct_critico"], cmap="YlOrRd"))
            fig = sensitivity.figura_heatmap_sensibilidad(df_grid)
            st.pyplot(fig)

            latex = sensitivity.tabla_latex_sensibilidad(df_grid, n_filas=8)
            with st.expander("Tabla LaTeX para paper"):
                st.code(latex, language="latex")
        else:
            st.info("Sin datos de comparaciones CFP/INIDEP para la grilla.")
