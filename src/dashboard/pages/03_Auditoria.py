"""
Página de Auditoría IA: análisis con Claude API y detección de patrones.
"""

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(ROOT))

from src.dashboard._ui import page_header_raw

page_header_raw(
    "🧠 Auditoría con Inteligencia Artificial",
    "Análisis de resoluciones con Claude API y detección de patrones sistémicos",
)

with st.expander("🔍 IA responsable: cómo garantizamos transparencia", expanded=False):
    st.markdown(
        "- **Anclaje textual (groundedness):** cada hallazgo se contrasta con el texto fuente; "
        "si el anclaje es insuficiente se marca **`[BAJA_EVIDENCIA]`** y no se presenta como firme.\n"
        "- **Trazabilidad:** cada análisis se identifica por `prompt_hash` + `input_hash` + modelo + "
        "temperatura → es **reproducible y auditable**.\n"
        "- **Human-in-the-loop:** los resultados son **descriptivos** y **requieren verificación**; "
        "no constituyen prueba ni acusación.\n"
        "- Detalle completo en [`docs/IA_RESPONSABLE.md`](https://github.com/arielgiamportone/cfp-audit-intelligence/blob/main/docs/IA_RESPONSABLE.md) "
        "y en el marco ético (ADR-007)."
    )

# ── Verificar proveedor de LLM ─────────────────────────────────────────────────

from src.analysis.audit_engine import CFPAuditEngine
from src.analysis.pattern_detector import PatternDetector
from src.config_loader import get_kb_dir
from src.knowledge_base.vector_store import CFPVectorStore

try:
    # Valida que hay un proveedor configurado en .env (LLM_PROVIDER + su API key:
    # ANTHROPIC_API_KEY, o OPENAI_API_KEY/OPENAI_BASE_URL/LLM_MODEL). Agnóstico al proveedor.
    CFPAuditEngine()
except ValueError:
    st.info(
        "🧠 **Modo demo:** la Auditoría con IA requiere un proveedor de LLM configurado "
        "(`LLM_PROVIDER` + `ANTHROPIC_API_KEY` u `OPENAI_API_KEY`), no habilitado en esta demo "
        "pública. Esta función se muestra en el vídeo del proyecto y puede ejecutarse en local. "
        "Para ver resultados sin IA en vivo, visita **📊 Reportes**, **🔬 Comparador** y **🚨 Alertas**.",
        icon="ℹ️",
    )
    st.stop()

KB_DIR = get_kb_dir()
from src.config_loader import get_db_path

DB_PATH = get_db_path()

# ── Tabs ──────────────────────────────────────────────────────────────────────

tab_analisis, tab_patrones, tab_sostenibilidad, tab_busqueda_auditada = st.tabs(
    [
        "🔬 Analizar Resolución",
        "📊 Detección de Patrones",
        "🌊 Sostenibilidad por Especie",
        "🔍 Búsqueda + Auditoría",
    ]
)

# ── Tab 1: Analizar resolución individual ─────────────────────────────────────

with tab_analisis:
    st.subheader("Análisis de Resolución Individual")

    col_input, col_config = st.columns([3, 1])
    with col_input:
        texto_resolucion = st.text_area(
            "Texto de la resolución",
            height=300,
            placeholder=(
                "Pega aquí el texto de la resolución a analizar...\n\n"
                "Ej: RESOLUCIÓN N° 1/2024 – El CFP RESUELVE: Establecer la cuota "
                "de captura de Merluza hubbsi para el año 2024 en 500.000 toneladas..."
            ),
        )
        resolucion_id = st.text_input("ID de referencia (opcional)", value="manual_001")
        contexto = st.text_area(
            "Contexto del acta (opcional)",
            height=100,
            placeholder="Fecha, lugar, miembros presentes, quórum...",
        )

    with col_config:
        high_stakes = st.checkbox(
            "Análisis profundo (Opus)",
            help="Usa Claude Opus para análisis más detallado (mayor costo)",
        )
        st.caption("El análisis estándar usa Claude Sonnet.")

    if st.button("Analizar con IA", type="primary", disabled=not texto_resolucion):
        engine = CFPAuditEngine()
        with st.spinner("Analizando resolución con Claude..."):
            result = engine.analyze_resolucion(
                resolucion_id=resolucion_id,
                texto=texto_resolucion,
                acta_context=contexto or None,
                high_stakes=high_stakes,
            )

        # Score de riesgo
        risk_color = {
            "bajo": "green",
            "medio": "orange",
            "alto": "red",
            "critico": "darkred",
        }.get(result.categoria_riesgo, "gray")

        col_score, col_meta = st.columns([1, 3])
        with col_score:
            st.markdown(
                f"<h1 style='color:{risk_color};text-align:center'>"
                f"{result.riesgo_score:.0f}</h1>"
                f"<p style='text-align:center;color:{risk_color}'>"
                f"RIESGO {result.categoria_riesgo.upper()}</p>",
                unsafe_allow_html=True,
            )
        with col_meta:
            st.markdown(f"**Modelo usado:** {result.modelo_usado}")
            st.markdown(
                f"**Tokens:** {result.tokens_entrada} entrada / {result.tokens_salida} salida"
            )

        st.markdown("---")

        if result.hallazgos:
            st.markdown("**Hallazgos concretos:**")
            for h in result.hallazgos:
                st.error(f"⚠️ {h}")

        if result.indicios:
            st.markdown("**Indicios (requieren verificación adicional):**")
            for i in result.indicios:
                st.warning(f"🔍 {i}")

        if result.recomendaciones:
            st.markdown("**Recomendaciones:**")
            for r_item in result.recomendaciones:
                st.info(f"💡 {r_item}")

        cols = st.columns(3)
        if result.normativa_afectada:
            cols[0].markdown("**Normativa afectada:**")
            for n in result.normativa_afectada:
                cols[0].caption(f"• {n}")
        if result.entidades_beneficiadas:
            cols[1].markdown("**Entidades beneficiadas:**")
            for e in result.entidades_beneficiadas:
                cols[1].caption(f"• {e}")
        if result.especies_afectadas:
            cols[2].markdown("**Especies afectadas:**")
            for s in result.especies_afectadas:
                cols[2].caption(f"• {s}")

        with st.expander("Ver análisis completo (raw)"):
            st.text(result.analisis_completo)

# ── Tab 2: Detección de patrones ──────────────────────────────────────────────

with tab_patrones:
    st.subheader("Detección de Patrones Sistémicos")

    if not DB_PATH.exists():
        st.error(
            "Base de datos no encontrada. Ejecuta primero el pipeline de adquisición y procesamiento."
        )
    else:
        detector = PatternDetector(DB_PATH)

        col_hhi, col_voting = st.columns(2)

        with col_hhi:
            st.markdown("**Concentración de Beneficiarios (HHI)**")
            hhi = detector.hhi_concentration()
            hhi_val = hhi.get("hhi", 0)
            hhi_color = "red" if hhi_val > 2500 else "orange" if hhi_val > 1000 else "green"
            st.markdown(
                f"<h2 style='color:{hhi_color}'>{hhi_val:,.0f}</h2>",
                unsafe_allow_html=True,
            )
            st.caption(hhi.get("interpretation", ""))
            st.caption(f"Empresas analizadas: {hhi.get('empresas_analizadas', 0)}")

        with col_voting:
            st.markdown("**Patrones de Votación**")
            voting = detector.voting_patterns()
            if "error" not in voting:
                st.metric("Resoluciones unánimes", f"{voting.get('pct_unanimes', 0):.1f}%")
                st.metric("Con voto negativo", f"{voting.get('pct_con_disidencia', 0):.1f}%")
                st.metric("Con abstenciones", voting.get("abstenciones_registradas", 0))
            else:
                st.info("Sin datos de votaciones. Completa el pipeline de procesamiento.")

        st.markdown("---")

        # Reversiones
        st.markdown("**Reversiones Detectadas** (cuotas post-veda)")
        reversals = detector.reversals_detection()
        if reversals:
            import pandas as pd

            st.dataframe(pd.DataFrame(reversals), width="stretch")
        else:
            st.info("No se detectaron reversiones o no hay datos suficientes.")

        # Resoluciones de alto riesgo
        st.markdown("---")
        st.markdown("**Resoluciones de Alto Riesgo (score ≥ 70)**")
        threshold = st.slider("Umbral de riesgo", 50, 95, 70)
        high_risk = detector.high_risk_resolutions(threshold)
        if not high_risk.empty:
            st.dataframe(high_risk[["year", "numero", "tipo", "riesgo_score", "texto_preview"]])
        else:
            st.info("Sin resoluciones que superen el umbral (o análisis IA no ejecutado aún).")

        # Análisis de patrones con IA
        st.markdown("---")
        with st.expander("Analizar patrones con IA (requiere resoluciones en KB)"):
            if st.button("Detectar patrones con Claude"):
                vs = CFPVectorStore(KB_DIR)
                if vs.count() == 0:
                    st.error("Knowledge Base vacía.")
                else:
                    sample = vs.search("cuota captura sostenibilidad especie", n_results=20)
                    texts = [r["texto"] for r in sample]
                    engine = CFPAuditEngine()
                    with st.spinner("Analizando patrones con Claude Opus..."):
                        patterns = engine.detect_patterns(texts)
                    st.json(patterns)

# ── Tab 3: Sostenibilidad por especie ─────────────────────────────────────────

with tab_sostenibilidad:
    st.subheader("Análisis de Sostenibilidad por Especie")

    ESPECIES = [
        "merluza hubbsi",
        "merluza de cola",
        "merluza negra",
        "langostino",
        "calamar illex",
        "abadejo",
        "polaca",
        "corvina rubia",
        "anchoita",
        "caballa",
    ]

    col_esp, col_config_sust = st.columns([2, 1])
    with col_esp:
        especie_sel = st.selectbox("Selecciona especie", ESPECIES)
    with col_config_sust:
        years_range = st.slider("Rango de años", 1998, 2025, (2000, 2025))

    if st.button("Analizar sostenibilidad con IA", type="primary"):
        vs = CFPVectorStore(KB_DIR)
        if vs.count() == 0:
            st.error("Knowledge Base vacía. Construye la KB primero.")
        else:
            # Recuperar resoluciones relevantes por año
            resoluciones_por_anio = {}
            for year in range(years_range[0], years_range[1] + 1):
                results = vs.search(
                    especie_sel,
                    n_results=5,
                    year_from=year,
                    year_to=year,
                )
                if results:
                    resoluciones_por_anio[year] = [r["texto"] for r in results]

            if not resoluciones_por_anio:
                st.warning(f"No se encontraron resoluciones sobre {especie_sel} en el período.")
            else:
                st.info(
                    f"Analizando {sum(len(v) for v in resoluciones_por_anio.values())} resoluciones sobre {especie_sel}..."
                )
                engine = CFPAuditEngine()
                with st.spinner("Analizando con Claude Opus..."):
                    result = engine.analyze_sustainability(especie_sel, resoluciones_por_anio)

                risk_sust = result.get("riesgo_sostenibilidad", 0)
                st.metric(
                    "Riesgo de Sostenibilidad",
                    f"{risk_sust}/100",
                    delta=f"Tendencia: {result.get('tendencia_cuotas', 'N/D')}",
                    delta_color="inverse",
                )

                if result.get("señales_sobrexplotacion"):
                    st.markdown("**Señales de sobrexplotación:**")
                    for s in result["señales_sobrexplotacion"]:
                        st.warning(f"⚠️ {s}")

                if result.get("decisiones_cuestionables"):
                    st.markdown("**Decisiones cuestionables:**")
                    import pandas as pd

                    st.dataframe(pd.DataFrame(result["decisiones_cuestionables"]))

                st.info(f"**Conclusión:** {result.get('conclusion', 'N/D')}")
                with st.expander("Ver análisis completo"):
                    st.json(result)

# ── Tab 4: Búsqueda + auditoría combinada ─────────────────────────────────────

with tab_busqueda_auditada:
    st.subheader("Búsqueda Semántica + Auditoría Automática")
    st.caption("Busca resoluciones relevantes y analízalas con IA en un solo flujo")

    query_audit = st.text_input(
        "Consulta",
        placeholder="Ej: cuotas de langostino otorgadas sin informe técnico...",
    )
    n_audit = st.slider("Cantidad a auditar", 1, 10, 5, key="n_audit")

    if st.button("Buscar y Auditar", type="primary", disabled=not query_audit):
        vs = CFPVectorStore(KB_DIR)
        if vs.count() == 0:
            st.error("Knowledge Base vacía.")
        else:
            with st.spinner("Buscando resoluciones relevantes..."):
                results = vs.search(query_audit, n_results=n_audit)

            engine = CFPAuditEngine()
            st.markdown(f"**{len(results)} resoluciones encontradas. Auditando...**")

            for i, r in enumerate(results, 1):
                meta = r["metadata"]
                with st.expander(
                    f"[{i}] Res. {meta.get('numero', '?')} / {meta.get('year', '?')} "
                    f"— {meta.get('tipo', 'otro').replace('_', ' ').title()}"
                ):
                    with st.spinner(f"Auditando resolución {i}/{len(results)}..."):
                        audit = engine.analyze_resolucion(
                            resolucion_id=r["id"],
                            texto=r["texto"],
                        )

                    risk_color = {
                        "bajo": "🟢",
                        "medio": "🟡",
                        "alto": "🔴",
                        "critico": "🚨",
                    }.get(audit.categoria_riesgo, "⚪")

                    st.markdown(
                        f"{risk_color} **Riesgo:** {audit.riesgo_score:.0f}/100 "
                        f"({audit.categoria_riesgo.upper()})"
                    )

                    if audit.hallazgos:
                        for h in audit.hallazgos:
                            st.error(f"⚠️ {h}")
                    if audit.indicios:
                        for ind in audit.indicios:
                            st.warning(f"🔍 {ind}")
                    if not audit.hallazgos and not audit.indicios:
                        st.success("Sin alertas significativas")
