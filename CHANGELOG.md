# Changelog

Todos los cambios notables de este proyecto se documentan aquí.
Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/).

> Contexto: este repositorio es el **Trabajo Final del Máster en Desarrollo con IA**.
> Las mejoras se aplican **unidad a unidad** del máster (ver `docs/TFM_PLAN_MEJORAS.md`),
> citando el principio aplicado en cada entrada.

## [Sin publicar]

### Añadido
- **Entrega TFM:** `LICENSE` (MIT), sección TFM en el README (entregables, stack, estructura,
  escalabilidad), guiones de slides y vídeo (`docs/TFM_PRESENTACION.md`, `docs/TFM_GUION_VIDEO.md`)
  y runbook de despliegue (`docs/TFM_DEPLOY.md`).
- **Despliegue** en Streamlit Community Cloud (URL pública) + `.streamlit/config.toml`.
- **Plan de mejoras del TFM** (`docs/TFM_PLAN_MEJORAS.md`): aplicación de conceptos del máster.
- **ADR-011**: decisión de mantener **Streamlit como adaptador de entrega (UI)** sobre un
  dominio agnóstico y junto a la API REST (patrón hexagonal / Ports & Adapters), con
  evidencia de que el dominio no depende de la UI.
- **Unidad 2 (Análisis de Requisitos):** `docs/REQUISITOS.md` con fichas RF/RNF, historias
  de usuario (Given-When-Then), priorización MoSCoW y **trazabilidad requisito → módulo**.
- **Unidad 2 (Spec Driven Development):** `docs/specs/SPEC-001-export-comparador.md`,
  ejemplo Spec-First (la spec como fuente de verdad) para exportar la comparación CBA/CMP.
  Enlaces a REQUISITOS y specs añadidos a la Documentación Técnica del README.

### Cambiado
- **Narrativa TFM (autor):** se incorpora el arco personal **Data Science → DEV** en el guion
  de vídeo (`docs/TFM_GUION_VIDEO.md`) y una nota de motivación en el README.
- **UX (enfoque desarrollo):** home reescrito para público no experto (explicación en lenguaje
  llano, diagrama ciencia→política→realidad, leyenda de alertas, glosario, "empieza por aquí").
- **UX:** intros "¿cómo leer esta página?" en Comparador y Alertas; estados vacíos amigables
  ("modo demo") en Adquisición, Knowledge Base, Auditoría IA y Reportes.
- **UI (identidad visual y consistencia):** paleta marina en `.streamlit/config.toml` y componente
  reutilizable `src/dashboard/_ui.py` (`inject_base_css`, `sidebar_brand`, `page_header`, `setup_page`)
  aplicado a **home + las 17 páginas** (DRY): métricas como tarjetas, espaciado, expanders suaves,
  barra lateral de marca con enlaces al repo y a la app, y footer de Streamlit oculto.
- **UI · auditoría de usabilidad (tanda 1):** helpers `demo_banner()`, `dev_note()` y `style_plotly()`
  en `_ui.py`; `page_icon` añadido a las 4 páginas que no lo tenían (Evaluación, Conflictos, Geovisor,
  CONAE) y de-duplicación del icono 🔬 (CONICET→📚, Investigación→🧪) para una navegación coherente.

### Corregido — Blindaje de imports y dependencias (tanda 6)
- **Fin de los errores de importación:** helper `import_guard()` en `_ui.py` que envuelve los
  imports pesados/opcionales; si una dependencia no está instalada, la página muestra un aviso claro
  y un enlace al Comparador en vez de un *traceback*. Aplicado a Adquisición, Reportes, Grafo,
  Reporte PDF, Investigación, Conflictos y CONAE.
- **`requirements-deploy.txt` sincronizado:** añadidas `matplotlib`, `scipy`, `scikit-learn` y
  `openpyxl` (las usaban Reportes/Investigación/Evaluación/CONAE y faltaban en el perfil de deploy).
- **Bug real corregido (CONAE):** `get_esfuerzo_df(...) or pd.DataFrame()` lanzaba
  *"The truth value of a DataFrame is ambiguous"*; ahora se comprueba `is not None`.
- **Migración `use_container_width` → `width`:** 68 llamadas actualizadas a `width="stretch"`
  (la API antigua está deprecada), evitando que una futura versión de Streamlit rompa la app.
- **Validación:** smoke test con `AppTest` recorre **las 19 páginas** (router + navegación) sin
  excepciones, tanto con dependencias ausentes (guard) como presentes (camino feliz).

### Añadido — Informe Ejecutivo (tanda 5)
- **Nueva vista narrativa `Informe Ejecutivo`** (`pages/00_Informe_Ejecutivo.py`, sección *Inicio*):
  scrollytelling en 4 pasos (el problema → números clave → foco por especie con **texto
  autogenerado** a partir de los datos → cómo leerlo/limitaciones). Reutiliza `INIDEPComparator`,
  gráficos temáticos y el helper `tabla()`. Pensada para leerse de una sola pasada y para el vídeo.
- Acceso destacado al informe desde la portada.

### Corregido
- **`tabla()` con `height=None`:** Streamlit ≥1.59 rechaza `height=None` en `st.dataframe`
  (`StreamlitInvalidHeightError`); el helper ahora solo pasa `height` cuando tiene valor. Detectado
  con el smoke test de `AppTest` antes de publicar.

### Añadido — Valor de interfaz (tanda 4)
- **Home como *dashboard vivo*:** la portada muestra cifras reales de los datos verificados
  (comparaciones analizadas, casos con captura sobre la CBA, casos críticos y especie con más
  presión) reutilizando `INIDEPComparator`, con enlace al análisis completo. Antes la portada solo
  mostraba el estado del corpus (vacío en la demo).
- **Tablas legibles (`st.column_config`):** helper `tabla()` + columnas `col_tn` (toneladas con
  separador de miles) y `col_ratio` (barra de progreso, 1.0 = límite científico); aplicado a la
  tabla del triángulo del Comparador.
- **Sellos de procedencia y confianza:** componente `data_source(fuente, fecha, estado)` con estado
  🟢 verificado / 🟡 demo / 🔵 ilustrativo, añadido a Comparador, Timeline, Alertas, FAO, CONICET
  y Capturas.
- **Polish de accesibilidad:** tooltips `help=` en las métricas del Comparador y del home; helper
  `nivel_chip()` (icono + etiqueta, no depende solo del color); botones de acción ("Ir al
  Comparador") en los estados vacíos de Timeline, Grafo y Alertas.
- **Validación:** smoke test con `AppTest` confirma que el home renderiza métricas reales
  (35 comparaciones · 19 sobre el límite · 10 críticas · Merluza Común) sin excepciones.

### Cambiado — Consistencia de UI (tanda 2)
- **Cabecera unificada:** las 17 páginas usan ahora `page_header_raw()` de `_ui.py` (punto único de
  formato del encabezado) en lugar de `st.title`/`st.caption` sueltos → DRY.
- **Sin jerga de terminal para el usuario:** los estados vacíos de Timeline, Grafo, Alertas,
  Evaluación y Geovisor ya no muestran comandos (`--step process`, `make pipeline`, …); ahora guían
  al usuario ("empieza por el Comparador / reproduce el pipeline en local, ver `docs/TFM_DEPLOY.md`").
- **Selectores legibles:** el filtro "Tipo de resolución" (Knowledge Base) muestra etiquetas
  humanas (`Cuota de captura`, `Habilitación de buque`, …) vía `format_func` en vez de valores con
  guiones bajos; se añadió una explicación de qué significa la métrica de **similitud**.

### Cambiado — Navegación temática (st.navigation)
- **Menú lateral agrupado en 6 secciones** (Inicio · Núcleo/Triángulo · Análisis IA · Contexto
  externo · Gobernanza · Ingesta y rigor) en lugar de una lista plana de 17 páginas. `app.py` pasa
  a ser un **router** (`st.navigation` + `st.Page`, Streamlit ≥1.36) que fija `set_page_config` y el
  tema/marca **una sola vez**; el contenido del home se movió a `src/dashboard/home.py`.
- Se retiró `set_page_config`/`setup_page()` de las 17 páginas (ahora los aporta el router → DRY).
- **Validación:** smoke test headless con `streamlit.testing.v1.AppTest` (router + navegación +
  render del home sin excepciones). `requirements` sube a `streamlit>=1.36.0`.

### Corregido
- **Legibilidad en tema claro:** varios gráficos y tarjetas forzaban texto/fondo oscuro y quedaban
  ilegibles con el nuevo tema claro. Alertas (texto blanco invisible + tarjeta translúcida negra),
  Grafo y Conflictos (fondos `#0E1117` fijos) ahora usan fondo transparente y texto slate.
- **Manejo de errores en la UI:** la generación de PDF (`09_Reporte`) ya no vuelca el *traceback*
  crudo al usuario (`st.exception`); muestra un mensaje claro y esconde el detalle en un expander.
- **Honestidad de datos:** la pestaña "Por especie" de Reportes marca ahora de forma inequívoca
  que sus gráficos son **datos ILUSTRATIVOS (no reales)**, evitando que se tomen por hallazgos.

### Añadido — Unidad 4 · Fundamentos de la IA (IA responsable)
- **`docs/IA_RESPONSABLE.md`**: mapa de los 4 pilares (Fairness · Safety · Explainability ·
  Accountability) a la implementación real (groundedness, `[BAJA_EVIDENCIA]`, Model Card,
  Datasheet, trazabilidad `prompt_hash`, ADR-007).
- **Explainability en la UI**: expander de transparencia en la página de Auditoría.

### Añadido — Unidad 3 · Arquitectura (Hexagonal / DIP)
- **Puertos del dominio** (`src/ports.py`): `VectorStorePort` y `AuditorPort` como
  `typing.Protocol` estructural; los adaptadores actuales (ChromaDB, Claude) los cumplen
  sin cambios. Test de conformidad en `tests/test_ports.py`. Decisión en **ADR-012**.

### Refactorizado — Unidad 1 · Buenas Prácticas y Principios de Diseño
- **DRY + DIP (fuente única de verdad):** se añadieron `get_db_path()` y `get_kb_dir()` a
  `config_loader.py` y se refactorizaron las **18 páginas del dashboard + `app.py`** para
  consumir esas funciones en lugar de rutas hardcodeadas (antes duplicadas en 18 sitios y en
  dos formas distintas).
- **Bug latente corregido (KISS/robustez):** las rutas eran relativas al *cwd* en ~12 páginas
  (fallaban si el directorio de trabajo cambiaba). Ahora son **absolutas y ancladas a la raíz**
  del proyecto, con override opcional vía `settings.yaml → paths.{db_path,kb_dir}`.
