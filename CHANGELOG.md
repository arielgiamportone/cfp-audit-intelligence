# Changelog

Todos los cambios notables de este proyecto se documentan aquí.
Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y
[Versionado Semántico](https://semver.org/lang/es/).

## [0.5.0] — 2026-08

### Añadido
- **Corpus real 2024–25**: 68 actas del CFP y 754 resoluciones parseadas, versionadas y
  auditadas con IA (**474 análisis**), visibles en la app desplegada.
- **Motor de auditoría IA multi-proveedor** (patrón DIP, sin *vendor lock-in*): Anthropic (Claude)
  o cualquier API compatible con OpenAI —OpenAI, Groq, Gemini— configurable por `.env`.
- **Informe Ejecutivo**: vista narrativa del hallazgo central con texto generado a partir de los datos.
- **Home como dashboard vivo**: KPIs reales del corpus en la portada.
- **Navegación temática** con `st.navigation` (6 secciones) y **selector de especie global**
  sincronizado entre Comparador, Timeline y Capturas.
- **Mapa geoespacial de vedas** en el Geovisor (centroides desde el servicio WFS del INIDEP).
- **UX de datos**: tablas legibles (`st.column_config`), sellos de procedencia del dato
  (verificado / demo / ilustrativo), tooltips en métricas y semáforo accesible.
- **Calidad**: suite ampliada a **1003 tests**, incluyendo *smoke test* del dashboard
  (`streamlit.testing.AppTest`) y cobertura del núcleo (`audit_engine`, `vector_store`, `pdf_extractor`).
- **Documentación**: requisitos RF/RNF (Given-When-Then, MoSCoW, trazabilidad), especificaciones
  Spec-First, IA responsable (4 pilares) y ADRs de arquitectura hexagonal / puertos (ADR-011, ADR-012).

### Cambiado
- Identidad visual marina y **componentes de UI reutilizables** (DRY); cabecera de página unificada.
- **Rutas y configuración centralizadas** (`config_loader`); el pipeline escribe en las mismas rutas
  que lee la app, con un objetivo `make demo-corpus` para poblar una muestra reproducible.
- **Docker**: `streamlit>=1.36` y dependencias de visualización/ciencia en la imagen; `docker-compose`
  con servicios API y dashboard desacoplados.
- Migración de `use_container_width` a `width="stretch"` (API vigente de Streamlit).

### Corregido
- **Persistencia de resoluciones en SQLite** (las consumen la API y el dashboard), antes solo en JSON.
- **RAG**: clave de indexación de resoluciones; marcado de actas como `embedded` para habilitar la
  auditoría; auditoría **reintentable** ante fallos transitorios de la API.
- **Compatibilidad de proveedores**: soporte de `max_completion_tokens` y de `base_url` por defecto.
- **Legibilidad en tema claro**, manejo de errores en la UI (sin *tracebacks* al usuario),
  señalización inequívoca de datos ilustrativos y validación de `st.dataframe`.

## [0.4.0] y anteriores

Base del proyecto: pipeline de adquisición del CFP (scraping, extracción PDF en cascada, parser de
actas, NER pesquero con spaCy), Knowledge Base con ChromaDB, comparador **CBA vs CMP** con sistema de
alertas, 492 ITOs del INIDEP (Mar Abierto), timeline histórico, grafo de relaciones, sistema de
alertas configurables, API REST (FastAPI + OpenAPI), reporte PDF ejecutivo, integraciones FAO FIRMS /
CONICET / CONAE / geovisor SERE, e infraestructura Docker + GitHub Actions (CI).
