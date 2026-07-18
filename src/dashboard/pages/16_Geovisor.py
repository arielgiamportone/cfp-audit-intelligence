"""
Página 16 — Geovisor SERE (INIDEP): Vedas Geoespaciales

Visualiza las zonas de veda georreferenciadas publicadas por el geovisor SERE
del INIDEP (sere.inidep.edu.ar), cada una con número de resolución, organismo
emisor (CFP/CTMFM) y link al PDF oficial — y cruza esas citas contra el corpus
de actas CFP ya cargado para medir cobertura del parser (ADR-009).

Fuente: servicio público WFS/GeoServer del INIDEP, sin autenticación.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from src.acquisition.inidep_geovisor_scraper import SEREGeovisorClient
from src.analysis.geovisor_cross_validator import GeovisorCrossValidator

from src.config_loader import get_db_path
DB_PATH = get_db_path()
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

from src.dashboard._ui import page_header_raw
page_header_raw("🗺️ Geovisor SERE (INIDEP) — Vedas Geoespaciales", "Cada zona de veda publicada por el geovisor cita directamente el número de "
    "resolución, el organismo emisor (CFP/CTMFM) y un link al PDF oficial — una "
    "fuente externa verificable para auditar la cobertura del parser de actas CFP.")

# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.header("Configuración")
    if st.button("📥 Descargar vedas del geovisor SERE"):
        with st.spinner("Consultando WFS sere.inidep.edu.ar (puede tardar ~1 min)..."):
            try:
                client = SEREGeovisorClient(delay=1.0)
                n = client.scrape_and_save_vedas(DB_PATH)
                st.cache_data.clear()
                st.success(f"{n} zonas de veda nuevas guardadas en la base.")
            except Exception as exc:  # noqa: BLE001
                st.error(f"No se pudo consultar el geovisor: {exc}")

    st.divider()
    st.info(
        "**Nota metodológica (ADR-009)**\n\n"
        "CFP y CTMFM numeran sus resoluciones de forma independiente: "
        '"Resolución N° 13/2024" puede existir en ambos organismos y referir a '
        "normas distintas. La cobertura solo compara citas de fuente **CFP** "
        "para evitar falsos positivos por colisión de numeración."
    )

# ── Carga de datos ────────────────────────────────────────────────────────────

@st.cache_data(ttl=120)
def cargar_vedas(db: str) -> pd.DataFrame:
    import sqlite3

    try:
        with sqlite3.connect(db) as conn:
            return pd.read_sql_query("SELECT * FROM vedas_geoespaciales", conn)
    except Exception:  # noqa: BLE001
        return pd.DataFrame()

@st.cache_data(ttl=120)
def cargar_cobertura(db: str) -> tuple[pd.DataFrame, dict]:
    validador = GeovisorCrossValidator(db)
    resultados = validador.validar_cobertura()
    resumen = validador.cobertura_summary(resultados)
    df = pd.DataFrame(
        [
            {
                "resolucion_numero": r.resolucion_numero,
                "especies": ", ".join(e for e in r.especies if e),
                "url": r.resolucion_url,
                "encontrada_en_corpus": "✅" if r.encontrada_en_corpus else "⏳ pendiente",
                "resolucion_ids_corpus": r.resolucion_ids_corpus,
            }
            for r in resultados
        ]
    )
    return df, resumen

df_vedas = cargar_vedas(str(DB_PATH))
df_cobertura, resumen_cobertura = cargar_cobertura(str(DB_PATH))

# ── KPIs ─────────────────────────────────────────────────────────────────────

col1, col2, col3, col4 = st.columns(4)
col1.metric("Zonas de veda cargadas", len(df_vedas))
col2.metric(
    "Resoluciones CFP citadas",
    resumen_cobertura.get("total_resoluciones_citadas_cfp", 0),
)
col3.metric("✅ Cubiertas por el corpus", resumen_cobertura.get("encontradas_en_corpus", 0))
col4.metric("% cobertura", f"{resumen_cobertura.get('pct_cobertura', 0.0)}%")

st.divider()

tab1, tab2, tab3, tab4 = st.tabs(
    ["🚫 Zonas de veda", "🔗 Cobertura del corpus", "🐟 Especies", "📖 Metodología"]
)

# ── Tab 1: Zonas de veda ──────────────────────────────────────────────────────

with tab1:
    if df_vedas.empty:
        st.info(
            "Sin datos cargados todavía. Usa **«Descargar vedas del geovisor SERE»** "
            "en la barra lateral para traerlos.",
            icon="ℹ️",
        )
    else:
        especies_disp = sorted(e for e in df_vedas["especie_code"].dropna().unique())
        especie_sel = st.multiselect("Filtrar por especie", especies_disp)
        df_show = df_vedas
        if especie_sel:
            df_show = df_show[df_show["especie_code"].isin(especie_sel)]

        cols = [
            "capa",
            "especie",
            "area",
            "fecha_inicio",
            "fecha_fin",
            "resolucion_numero",
            "resolucion_fuente",
            "resolucion_url",
        ]
        st.dataframe(
            df_show[cols].rename(
                columns={
                    "capa": "Capa",
                    "especie": "Especie",
                    "area": "Área",
                    "fecha_inicio": "Inicio",
                    "fecha_fin": "Fin",
                    "resolucion_numero": "Resolución",
                    "resolucion_fuente": "Organismo",
                    "resolucion_url": "PDF oficial",
                }
            ),
            width="stretch",
            height=420,
            column_config={
                "PDF oficial": st.column_config.LinkColumn("PDF oficial", display_text="Ver PDF")
            },
        )
        csv = df_show.to_csv(index=False).encode("utf-8")
        st.download_button("Descargar CSV", csv, "vedas_geoespaciales_sere.csv", "text/csv")

# ── Tab 2: Cobertura del corpus ───────────────────────────────────────────────

with tab2:
    st.markdown(f"**{resumen_cobertura.get('interpretacion', 'Sin datos.')}**")
    if df_cobertura.empty:
        st.info(
            "Sin resoluciones de veda fuente=CFP citadas por el geovisor en la base, "
            "o aún no se descargaron las vedas (ver barra lateral)."
        )
    else:
        st.dataframe(
            df_cobertura[["resolucion_numero", "especies", "url", "encontrada_en_corpus"]].rename(
                columns={
                    "resolucion_numero": "Resolución (CFP)",
                    "especies": "Especies",
                    "url": "PDF oficial",
                    "encontrada_en_corpus": "¿En el corpus?",
                }
            ),
            width="stretch",
            height=320,
            column_config={
                "PDF oficial": st.column_config.LinkColumn("PDF oficial", display_text="Ver PDF")
            },
        )
        st.caption(
            "Las resoluciones marcadas «⏳ pendiente» requieren que `--step process` cargue "
            "las actas de los años correspondientes para poder citarlas en el corpus (ver ADR-009)."
        )

# ── Tab 3: Especies ───────────────────────────────────────────────────────────

with tab3:
    if df_vedas.empty:
        st.info("Sin datos. Descargá las vedas desde la barra lateral.")
    else:
        conteo = (
            df_vedas.groupby("especie_code", dropna=True)
            .size()
            .reset_index(name="n_zonas_veda")
            .sort_values("n_zonas_veda", ascending=False)
        )
        st.bar_chart(conteo.set_index("especie_code"))
        st.dataframe(
            conteo.rename(columns={"especie_code": "Especie", "n_zonas_veda": "Zonas de veda"}),
            width="stretch",
        )

# ── Tab 4: Metodología ────────────────────────────────────────────────────────

with tab4:
    st.markdown(
        """
## Metodología — Geovisor SERE (INIDEP)

### Fuente de datos

[SERE — Visualizador de Especies](https://sere.inidep.edu.ar) es un geovisor del INIDEP
que corre sobre **GeoServer** y expone capas vía servicios OGC estándar (WFS 2.0.0),
**públicos y sin autenticación** (`https://sere.inidep.edu.ar/geoserver/ows`).

Cada polígono de veda geoespacial trae el **número de resolución, el organismo emisor
(CFP o CTMFM) y un link directo al PDF oficial** — una fuente independiente del parser
propio del proyecto, útil como ground truth externo.

### ¿Qué mide la cobertura?

Por cada resolución de veda citada por el geovisor con `fuente = CFP`, se comprueba si
su número (`N°/AAAA`) aparece citado dentro del texto de alguna acta ya cargada en
`resoluciones` (vía regex `Resolución [CFP] N° X/YYYY`, igual patrón que
`document_parser.parse_fundamento_inidep`).

### Por qué se filtra por organismo (lección de ADR-009)

CFP y CTMFM (Comisión Técnica Mixta del Frente Marítimo, organismo binacional
Argentina–Uruguay) **numeran sus resoluciones de forma independiente**. Se verificó
empíricamente que "Res. 13/2024" del geovisor es una veda de condrictios de **CTMFM**
(`ctmfm.org`), mientras que "Resolución CFP N° 13/2024" en el corpus es una norma
de **CFP** sobre cuota de merluza común — documentos distintos con igual número y año.
Comparar sin filtrar por `fuente` produciría falsos positivos de cobertura.

### Limitaciones

- La cobertura depende de que `--step process` cargue las actas de los años citados
  por el geovisor (2018, 2019, 2024, …) — mismo bloqueante que ADR-008.
- El geovisor solo publica capas de veda **2024**; años anteriores no están expuestos.
- Coincidencia por `(número, año)`: no valida que la fecha de vigencia (`fecha_inicio`/
  `fecha_fin`) coincida con la fecha real de la resolución citada en el acta.

### Referencias

- `docs/adr/009-geovisor-sere-inidep.md` — diseño, hallazgos verificados y ruta de migración.
- `src/acquisition/inidep_geovisor_scraper.py` — cliente WFS y persistencia.
- `src/analysis/geovisor_cross_validator.py` — cruce de cobertura.
        """
    )
