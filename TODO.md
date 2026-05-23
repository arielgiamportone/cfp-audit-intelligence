# CFP Audit Intelligence — Backlog y Roadmap

> Estado: 2026-05-23 | Branch activo: `claude/cfp-fisheries-audit-project-lLMib`

---

## ✅ Completado (v0.2)

- [x] Scraper Streamlit básico (v0.1)
- [x] Scraper batch CLI con retry y rate limiting
- [x] Catálogo SQLite completo (actas, resoluciones, entidades, menciones)
- [x] Extracción PDF en cascada (pdfplumber → PyMuPDF → OCR)
- [x] Parser estructural de resoluciones (tipo, cuotas, especies, empresas)
- [x] Vector store ChromaDB con embeddings multilingües
- [x] Motor de auditoría con Claude API + prompt caching
- [x] Detector de patrones estadísticos (HHI, votaciones, reversiones)
- [x] Dashboard Streamlit multipágina (4 páginas)
- [x] Pipeline CLI end-to-end (`scripts/run_full_pipeline.py`)
- [x] Makefile con targets clave
- [x] ADRs (001–004), CLAUDE.md, AGENTS.md, TODO.md

---

## 🔴 Prioridad Alta (Fase 2 — Sprint 1)

### [FEAT] Tests del pipeline core
- [ ] `tests/test_batch_scraper.py` — mock de requests, parsing de años
- [ ] `tests/test_pdf_extractor.py` — fixture con PDF de ejemplo
- [ ] `tests/test_document_parser.py` — parsing de resoluciones conocidas
- [ ] `tests/test_catalog_manager.py` — CRUD SQLite
- [ ] `tests/test_vector_store.py` — upsert + search básico
- [ ] GitHub Actions CI: `pytest` en cada push

### [FEAT] Comparador INIDEP
- [ ] Scraper de publicaciones del INIDEP (informes de evaluación de stocks)
- [ ] Modelo de datos: `inidep_recomendaciones(especie, year, cms_recomendada_tn, fuente)`
- [ ] Comparador: cuota CFP vs CMS recomendada → ratio de sobrepesca
- [ ] Visualización: gráfico de barras CFP vs INIDEP por especie/año
- [ ] Alerta automática cuando cuota > 110% de la CMS recomendada
- [ ] Página de dashboard: `05_INIDEP_Comparador.py`

### [FEAT] NER pesquero especializado
- [ ] Corpus de entrenamiento: anotar ~500 resoluciones con spaCy
- [ ] Entidades objetivo: ESPECIE, EMPRESA_PESQUERA, PERSONA_CFP, NORMATIVA, ZONA_PESCA, BUQUE
- [ ] Fine-tuning de `es_core_news_sm` o uso de `spaCy-transformers`
- [ ] Integrar NER en `document_parser.py` para reemplazar heurísticas regex
- [ ] Validar recall sobre entidades conocidas (Merluza, CONARPESA, INIDEP, etc.)

---

## 🟡 Prioridad Media (Fase 3 — Sprint 2)

### [FEAT] Timeline interactivo por especie
- [ ] Dataset de cuotas históricas 1998–2025 extraídas del pipeline
- [ ] Visualización Plotly: línea de tiempo con eventos (vedas, reaperturas, picos)
- [ ] Overlay con data INIDEP (cuando esté disponible)
- [ ] Filtro por especie, zona, empresa
- [ ] Página de dashboard: `06_Timeline.py`

### [FEAT] Sistema de alertas configurables
- [ ] Modelo de alertas: `alertas(id, tipo, especie, empresa, umbral, activa)`
- [ ] Tipos: cuota_supera_cms | empresa_recurrente | veda_revertida | quorum_minimo
- [ ] Notificación por email (SMTP) o webhook cuando se detecta alerta
- [ ] UI de configuración en el dashboard

### [FEAT] Grafo de relaciones
- [ ] NetworkX para grafo: empresas — resoluciones — miembros CFP
- [ ] Visualización interactiva con pyvis
- [ ] Detección de comunidades (empresas con patrones de decisión compartidos)
- [ ] Página de dashboard: `07_Grafo.py`

### [IMPROVEMENT] Mejoras al parser
- [ ] Extraer fecha exacta de cada resolución (no solo del acta)
- [ ] Detectar miembros que votaron en contra (por nombre)
- [ ] Extraer números de expediente y referencias a resoluciones anteriores
- [ ] Manejo de actas multi-sesión (sesiones plenarias largas)

---

## 🟢 Prioridad Baja (Fase 4 — Sprint 3)

### [FEAT] API REST (FastAPI)
- [ ] `GET /actas?year=2024&tipo=cuota_captura` — búsqueda en catálogo
- [ ] `GET /resoluciones/{id}` — detalle de resolución
- [ ] `POST /search` — búsqueda semántica en KB
- [ ] `POST /analyze` — análisis IA de texto libre
- [ ] Autenticación básica (API key)
- [ ] Documentación OpenAPI auto-generada

### [FEAT] Reporte PDF ejecutivo
- [ ] Template reportlab con portada, índice, secciones
- [ ] Secciones: resumen ejecutivo, hallazgos por especie, patrones detectados, annexos
- [ ] Tablas de evidencia con citas textuales de las actas
- [ ] Gráficos embebidos (matplotlib/plotly → PNG)
- [ ] Generación desde el dashboard (botón "Generar Informe")

### [FEAT] Integración datos externos
- [ ] Capturas reales (SIPA/SAGPyA): validar cuotas vs capturas efectivas
- [ ] Exportaciones pesqueras (INDEC): correlación decisiones CFP con comercio exterior
- [ ] Noticias (RSS/scraping): contexto periodístico de decisiones polémicas

### [IMPROVEMENT] Infraestructura
- [ ] Docker + docker-compose para despliegue reproducible
- [ ] GitHub Actions: pipeline completo en CI con PDFs de prueba
- [ ] Configuración de logging estructurado (JSON) para análisis de ejecución
- [ ] Cache de embeddings para evitar re-computar en re-indexaciones

---

## 📌 Decisiones Pendientes

| Decisión | Opciones | Deadline |
|----------|---------|---------|
| ¿Dónde hospedar el dashboard? | Streamlit Cloud / HuggingFace Spaces / VPS | Sprint 2 |
| ¿Publicar datos procesados? | Dataset abierto en Hugging Face / Zenodo | Sprint 3 |
| ¿Framework de anotación NER? | Prodigy (pago) / Label Studio (libre) / Doccano | Sprint 2 |
| ¿Integrar datos INIDEP via API o scraping? | Investigar disponibilidad API oficial | Sprint 1 |

---

## 🐛 Bugs conocidos

- [ ] El parser puede fallar en actas con estructura atípica (sesiones extraordinarias cortas)
- [ ] `cfp_scraper.py` (legacy) y `src/dashboard/app.py` comparten nombre de página en Streamlit
- [ ] El delay de scraping hardcodeado en el dashboard no usa `config/settings.yaml`

---

## 💡 Ideas para investigación futura

- Análisis de sentimiento en declaraciones de miembros del CFP
- Modelo predictivo: ¿qué variables predicen una cuota por encima de la CMS?
- Red de conflictos de interés: directores de empresas pesqueras en cargos públicos
- Comparación internacional: decisiones CFP vs organismos equivalentes (Chile, Perú, UE)
