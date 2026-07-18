"""
Página 8 — Sistema de Alertas Configurables CFP.

Permite configurar reglas de alerta, evaluar el estado actual
y consultar el historial de alertas detectadas.
"""

from pathlib import Path

import pandas as pd
import streamlit as st

from src.analysis.alert_engine import (
    SEV_CRITICAL,
    SEV_INFO,
    SEV_WARNING,
    SEVERIDADES,
    SEVERITY_COLORS,
    SEVERITY_ICONS,
    TIPO_CBA_EXCESO,
    TIPO_QUORUM_MINIMO,
    TIPO_REVERSION,
    TIPO_STOCK_CRITICO,
    TIPOS_VALIDOS,
    AlertaRegla,
    AlertEngine,
)

from src.dashboard._ui import data_source, page_header_raw
page_header_raw("🚨 Sistema de Alertas Configurables", "Monitorea el cumplimiento de las decisiones del CFP respecto a las recomendaciones "
    "científicas del INIDEP y otros indicadores de riesgo pesquero.")
data_source("Motor de reglas sobre el corpus de actas CFP", estado="demo")

with st.expander("❓ ¿Cómo leer esta página?", expanded=False):
    st.markdown(
        "Una **alerta** salta cuando una decisión del CFP cruza un umbral de riesgo, por ejemplo:\n\n"
        "- aprobar una **cuota por encima del límite científico** (CBA),\n"
        "- un **stock en estado crítico**,\n"
        "- la **reversión de una veda**, o\n"
        "- decisiones tomadas con **quórum mínimo**.\n\n"
        "Abajo puedes ver las alertas activas, su **severidad** y configurar las reglas que las disparan."
    )

from src.config_loader import get_db_path
DB_PATH = get_db_path()

TIPO_LABELS = {
    TIPO_CBA_EXCESO: "Exceso de CBA",
    TIPO_STOCK_CRITICO: "Estado de stock",
    TIPO_QUORUM_MINIMO: "Quórum mínimo",
    TIPO_REVERSION: "Reversión de decisión",
}

SEV_LABELS = {
    SEV_INFO: "ℹ️ Info",
    SEV_WARNING: "⚠️ Advertencia",
    SEV_CRITICAL: "🔴 Crítica",
}

@st.cache_resource(show_spinner=False)
def get_engine():
    return AlertEngine(db_path=DB_PATH)

if not DB_PATH.exists():
    st.info(
        "📦 Esta vista necesita el corpus de actas, que en la demo pública no está "
        "cargado. Empieza por el **Comparador INIDEP** o reproduce el pipeline en "
        "local — ver `docs/TFM_DEPLOY.md`.",
        icon="ℹ️",
    )
    st.page_link("pages/05_INIDEP_Comparador.py", label="🔬 Ir al Comparador INIDEP")
    st.stop()

engine = get_engine()

# ── Métricas resumen ───────────────────────────────────────────────────────────

summary = engine.get_summary()

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("🔴 Críticas abiertas", summary["criticas"])
col2.metric("⚠️ Advertencias", summary["warnings"])
col3.metric("ℹ️ Informativas", summary["info"])
col4.metric("Total alertas", summary["total"])
col5.metric("Reglas activas", summary["n_reglas"])

if summary.get("ultima_evaluacion"):
    st.caption(f"Última evaluación: {summary['ultima_evaluacion']}")

st.divider()

# ── Tabs ───────────────────────────────────────────────────────────────────────

tab1, tab2, tab3 = st.tabs(
    [
        "🚨 Alertas activas",
        "⚙️ Reglas",
        "📋 Historial",
    ]
)

# ─── Tab 1: Alertas activas ────────────────────────────────────────────────────

with tab1:
    col_run, col_clear = st.columns([1, 4])
    with col_run:
        if st.button("▶️ Evaluar ahora", type="primary"):
            with st.spinner("Evaluando reglas..."):
                alertas = engine.evaluate(clear_previous=True)
            st.success(f"{len(alertas)} alertas generadas")
            summary = engine.get_summary()
            st.cache_resource.clear()
            st.rerun()
    with col_clear:
        if st.button("✅ Marcar todas como resueltas"):
            df_open = engine.get_historial(solo_abiertas=True, limit=1000)
            if not df_open.empty:
                for aid in df_open["id"]:
                    engine.resolve_alerta(int(aid))
                st.success("Todas las alertas marcadas como resueltas")
                st.rerun()

    # Filtros
    col_f1, col_f2, col_f3 = st.columns(3)
    with col_f1:
        sev_filtro = st.selectbox(
            "Severidad mínima",
            ["Todas"] + list(SEV_LABELS.values()),
            key="sev_filtro_activas",
        )
    with col_f2:
        tipo_filtro = st.multiselect(
            "Tipo de alerta",
            options=list(TIPO_LABELS.values()),
            key="tipo_filtro_activas",
        )
    with col_f3:
        year_filtro = st.slider("Rango de años", 2000, 2026, (2015, 2026), key="year_activas")

    sev_min_map = {
        "ℹ️ Info": SEV_INFO,
        "⚠️ Advertencia": SEV_WARNING,
        "🔴 Crítica": SEV_CRITICAL,
    }
    sev_min = sev_min_map.get(sev_filtro)
    tipo_rev_map = {v: k for k, v in TIPO_LABELS.items()}

    df = engine.get_historial(
        severidad_min=sev_min,
        solo_abiertas=True,
        year_desde=year_filtro[0],
        year_hasta=year_filtro[1],
    )

    if tipo_filtro:
        tipos_sel = [tipo_rev_map[t] for t in tipo_filtro if t in tipo_rev_map]
        if not df.empty and "tipo" in df.columns:
            df = df[df["tipo"].isin(tipos_sel)]

    if df.empty:
        st.info(
            "No hay alertas abiertas con los filtros seleccionados. "
            "Usa '▶️ Evaluar ahora' para ejecutar una evaluación."
        )
    else:
        # Cards de alertas por severidad
        for sev in [SEV_CRITICAL, SEV_WARNING, SEV_INFO]:
            df_sev = df[df["severidad"] == sev] if not df.empty else pd.DataFrame()
            if df_sev.empty:
                continue
            icon = SEVERITY_ICONS[sev]
            color = SEVERITY_COLORS[sev]
            with st.expander(
                f"{icon} {SEV_LABELS[sev]} ({len(df_sev)})",
                expanded=(sev == SEV_CRITICAL),
            ):
                for _, row in df_sev.iterrows():
                    col_msg, col_btn = st.columns([8, 1])
                    with col_msg:
                        tipo_label = TIPO_LABELS.get(row["tipo"], row["tipo"])
                        st.markdown(
                            f'<div style="border-left: 4px solid {color}; padding: 6px 12px; '
                            f'margin-bottom: 8px; background: #ECF3F6; border-radius: 6px">'
                            f"<small><b>{tipo_label}</b>"
                            + (f" · {row['year']}" if row.get("year") else "")
                            + (f" · {row['acta_referencia']}" if row.get("acta_referencia") else "")
                            + f"</small><br>{row['mensaje']}</div>",
                            unsafe_allow_html=True,
                        )
                    with col_btn:
                        if st.button("✓", key=f"res_{row['id']}", help="Marcar como resuelta"):
                            engine.resolve_alerta(int(row["id"]))
                            st.rerun()

# ─── Tab 2: Gestión de reglas ──────────────────────────────────────────────────

with tab2:
    st.subheader("Reglas de alerta configuradas")

    reglas = engine.get_reglas()

    if not reglas:
        st.info("No hay reglas configuradas.")
    else:
        for regla in reglas:
            icon = SEVERITY_ICONS.get(regla.severidad, "•")
            color = SEVERITY_COLORS.get(regla.severidad, "#888")
            with st.expander(
                f"{icon} [{TIPO_LABELS.get(regla.tipo, regla.tipo)}] {regla.nombre}"
                + (" ✓" if regla.activa else " (inactiva)"),
                expanded=False,
            ):
                col_r1, col_r2, col_r3 = st.columns([3, 2, 1])
                with col_r1:
                    st.write(f"**Descripción:** {regla.descripcion or '—'}")
                    st.write(f"**Especie:** {regla.especie_code or 'Todas'}")
                    st.write(f"**Zona:** {regla.zona or 'Todas'}")
                    st.write(f"**Años:** {regla.year_desde or '—'} → {regla.year_hasta or '—'}")
                with col_r2:
                    if regla.umbral_pct:
                        st.metric("Umbral (%)", f"{regla.umbral_pct:.0f}%")
                    if regla.umbral_estado:
                        st.write(f"**Estado stock:** `{regla.umbral_estado}`")
                    st.write(f"**Severidad:** {SEV_LABELS.get(regla.severidad, regla.severidad)}")
                with col_r3:
                    nuevo_estado = not regla.activa
                    btn_label = "✅ Activar" if not regla.activa else "⏸ Pausar"
                    if st.button(btn_label, key=f"toggle_{regla.id}"):
                        engine.toggle_regla(regla.id, nuevo_estado)
                        st.rerun()
                    if st.button("🗑 Eliminar", key=f"del_{regla.id}"):
                        engine.delete_regla(regla.id)
                        st.rerun()

    st.divider()
    st.subheader("➕ Nueva regla de alerta")

    with st.form("nueva_regla_form", clear_on_submit=True):
        col_n1, col_n2 = st.columns(2)
        with col_n1:
            nombre = st.text_input("Nombre de la regla *", placeholder="Ej: Exceso merluza norte")
            tipo = st.selectbox(
                "Tipo *",
                options=list(TIPOS_VALIDOS),
                format_func=lambda t: TIPO_LABELS.get(t, t),
            )
            descripcion = st.text_area("Descripción", height=80)
        with col_n2:
            severidad = st.selectbox(
                "Severidad *",
                options=SEVERIDADES,
                format_func=lambda s: SEV_LABELS.get(s, s),
                index=1,
            )
            especie_code = st.text_input(
                "Código especie (vacío = todas)",
                placeholder="ej: merluza_hubbsi",
            )
            zona = st.text_input("Zona (vacío = todas)", placeholder="ej: Sur 41°S")

        col_n3, col_n4, col_n5 = st.columns(3)
        with col_n3:
            year_desde = st.number_input("Año desde", value=2000, min_value=1990, max_value=2030)
        with col_n4:
            year_hasta = st.number_input("Año hasta", value=2030, min_value=1990, max_value=2030)
        with col_n5:
            umbral_pct = st.number_input(
                "Umbral % (para CBA exceso)",
                value=115.0,
                min_value=100.0,
                max_value=300.0,
                step=5.0,
                help="Solo para tipo 'cba_exceso'",
            )

        umbral_estado = st.selectbox(
            "Estado stock (para tipo 'stock_critico')",
            options=["", "sobrexplotado", "en_recuperacion", "precautorio", "incierto"],
        )

        submitted = st.form_submit_button("Guardar regla", type="primary")
        if submitted:
            if not nombre.strip():
                st.error("El nombre es obligatorio.")
            else:
                nueva = AlertaRegla(
                    nombre=nombre.strip(),
                    tipo=tipo,
                    severidad=severidad,
                    especie_code=especie_code.strip() or None,
                    zona=zona.strip() or None,
                    year_desde=int(year_desde),
                    year_hasta=int(year_hasta),
                    umbral_pct=float(umbral_pct) if tipo == TIPO_CBA_EXCESO else None,
                    umbral_estado=umbral_estado or None,
                    descripcion=descripcion.strip() or None,
                )
                engine.upsert_regla(nueva)
                st.success(f"Regla '{nombre}' guardada.")
                st.rerun()

# ─── Tab 3: Historial ─────────────────────────────────────────────────────────

with tab3:
    st.subheader("Historial completo de alertas")

    col_h1, col_h2, col_h3 = st.columns(3)
    with col_h1:
        show_resueltas = st.checkbox("Incluir resueltas", value=False)
    with col_h2:
        sev_hist = st.selectbox(
            "Severidad mínima",
            ["Todas"] + list(SEV_LABELS.values()),
            key="sev_hist",
        )
    with col_h3:
        year_hist = st.slider("Rango años", 2000, 2026, (2000, 2026), key="year_hist")

    sev_hist_min = sev_min_map.get(sev_hist)

    df_hist = engine.get_historial(
        severidad_min=sev_hist_min,
        solo_abiertas=not show_resueltas,
        year_desde=year_hist[0],
        year_hasta=year_hist[1],
        limit=1000,
    )

    if df_hist.empty:
        st.info("No hay alertas en el historial con los filtros seleccionados.")
    else:
        # Estadísticas rápidas
        mc1, mc2, mc3 = st.columns(3)
        mc1.metric("Total en rango", len(df_hist))
        mc2.metric(
            "Críticas",
            len(df_hist[df_hist["severidad"] == SEV_CRITICAL]) if not df_hist.empty else 0,
        )
        mc3.metric(
            "Especies afectadas",
            df_hist["especie"].nunique() if "especie" in df_hist.columns else 0,
        )

        # Gráfico timeline
        try:
            import plotly.express as px

            df_chart = df_hist.dropna(subset=["year"]).copy()
            df_chart["year"] = df_chart["year"].astype(int)
            if not df_chart.empty:
                df_count = df_chart.groupby(["year", "severidad"]).size().reset_index(name="count")
                color_map = {SEV_CRITICAL: "#F44336", SEV_WARNING: "#FF9800", SEV_INFO: "#2196F3"}
                fig = px.bar(
                    df_count,
                    x="year",
                    y="count",
                    color="severidad",
                    color_discrete_map=color_map,
                    title="Alertas por año y severidad",
                    labels={"count": "Número de alertas", "year": "Año", "severidad": "Severidad"},
                    barmode="stack",
                )
                fig.update_layout(
                    plot_bgcolor="rgba(0,0,0,0)",
                    paper_bgcolor="rgba(0,0,0,0)",
                    font_color="#14303B",
                )
                st.plotly_chart(fig, use_container_width=True)
        except ImportError:
            pass

        # Tabla
        cols_show = [
            "severidad",
            "tipo",
            "especie",
            "year",
            "zona",
            "mensaje",
            "acta_referencia",
            "regla_nombre",
            "created_at",
        ]
        cols_present = [c for c in cols_show if c in df_hist.columns]

        df_display = df_hist[cols_present].copy()
        df_display["severidad"] = df_display["severidad"].map(
            lambda s: SEVERITY_ICONS.get(s, s) + " " + s
        )
        df_display["tipo"] = df_display["tipo"].map(lambda t: TIPO_LABELS.get(t, t))

        st.dataframe(df_display, use_container_width=True, hide_index=True)

        csv = df_hist.to_csv(index=False).encode("utf-8")
        st.download_button(
            "⬇️ Descargar historial CSV",
            data=csv,
            file_name="alertas_cfp_historial.csv",
            mime="text/csv",
        )
