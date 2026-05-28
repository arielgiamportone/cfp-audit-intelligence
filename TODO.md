# CFP Audit Intelligence — Backlog y Roadmap

> Estado: 2026-05-28 | Repo: `arielgiamportone/cfp-audit-intelligence` | Branch: `claude/cfp-fisheries-audit-project-lLMib`

---

## ✅ Completado (v0.2 — Sprint 1)

### Infraestructura base
- [x] Scraper batch CLI con retry y rate limiting (tenacity, 1.5s delay)
- [x] Catálogo SQLite completo (`actas`, `resoluciones`, `entidades`, `menciones`, `analisis_sesiones`)
- [x] Extracción PDF en cascada (pdfplumber → PyMuPDF → OCR Tesseract)
- [x] Parser estructural de actas CFP (formato real: minutas narrativas, no resoluciones numeradas)
- [x] Vector store ChromaDB con embeddings multilingües (`paraphrase-multilingual-MiniLM-L12-v2`)
- [x] Motor de auditoría con Claude API + prompt caching
- [x] Detector de patrones estadísticos (HHI concentración, votaciones, reversiones)
- [x] Dashboard Streamlit multipágina (5 páginas activas)
- [x] Pipeline CLI end-to-end (`scripts/run_full_pipeline.py --step download|process|kb|audit`)
- [x] Makefile con targets clave
- [x] ADRs (001–004), CLAUDE.md, AGENTS.md

### Comparador CFP vs. INIDEP (Issue #4)
- [x] Scraper Mar Abierto INIDEP (`src/acquisition/inidep_scraper.py`)
- [x] Datos semilla verificados: merluza (ITO 36-37/2024), centolla (ITO 31/2025), abadejo, polaca, langostino
- [x] Schema SQLite: `inidep_evaluaciones`, `cfp_cuotas`, `comparacion_cfp_inidep`
- [x] Motor de comparación con 4 niveles de alerta (verde/amarillo/rojo/crítico)
- [x] Página dashboard `05_INIDEP_Comparador.py` con alertas, gráficos, formulario manual

### Tests y CI (Issue #3)
- [x] `tests/conftest.py` — fixtures compartidas
- [x] `tests/test_document_parser.py` — 43 tests del parser (fecha, quórum, decisiones, agenda)
- [x] `tests/test_catalog_manager.py` — 16 tests del catálogo SQLite
- [x] `tests/test_inidep_comparator.py` — 21 tests del comparador (alertas, ratios, persistencia)
- [x] `tests/test_inidep_scraper.py` — 34 tests (SEED_DATA, extracción especie/zona, normalización)
- [x] 114 tests totales, todos verdes
- [x] GitHub Actions CI (`.github/workflows/tests.yml`) — Python 3.10 y 3.11

### Repo y documentación
- [x] Repo renombrado: `cfp-actas-scraper` → `cfp-audit-intelligence`
- [x] Archivos legacy eliminados del root (`cfp_scraper.py`, HTMLs de prueba)
- [x] README reescrito con arquitectura, módulos, roadmap y marco legal

---

## 🔴 Prioridad Alta (Sprint 2)

### [FEAT] NER pesquero especializado (Issue #5)
- [ ] Corpus de entrenamiento: anotar ~500 resoluciones con spaCy
- [ ] Entidades: ESPECIE, EMPRESA_PESQUERA, PERSONA_CFP, NORMATIVA, ZONA_PESCA, BUQUE
- [ ] Fine-tuning de `es_core_news_sm` o `spaCy-transformers`
- [ ] Integrar NER en `document_parser.py` reemplazando heurísticas regex
- [ ] Validar recall sobre entidades conocidas (Merluza, CONARPESA, INIDEP, etc.)

### [FEAT] Timeline interactivo por especie (Issue #6)
- [ ] Dataset de cuotas históricas 1998–2025 extraídas del pipeline
- [ ] Visualización Plotly: línea temporal con eventos (vedas, reaperturas, picos de cuota)
- [ ] Overlay con recomendaciones INIDEP
- [ ] Filtro por especie, zona, empresa
- [ ] Página `06_Timeline.py`

### [FEAT] Grafo de relaciones (Issue #7)
- [ ] NetworkX: empresas — resoluciones — miembros CFP
- [ ] Visualización interactiva con pyvis
- [ ] Detección de comunidades (empresas con patrones compartidos)
- [ ] Página `07_Grafo.py`

### [FEAT] Scraping completo INIDEP Mar Abierto (Issue #9)
- [ ] Scraping de los 492 ITOs disponibles en marabierto.inidep.edu.ar
- [ ] Extracción automática de valores CBA desde texto de ITOs
- [ ] Enriquecer `inidep_evaluaciones` con series históricas por especie

---

## 🟡 Prioridad Media (Sprint 3)

### [FEAT] Sistema de alertas configurables (Issue #8)
- [ ] Modelo: `alertas(id, tipo, especie, empresa, umbral, activa)`
- [ ] Tipos: `cuota_supera_cba | empresa_recurrente | veda_revertida | quorum_minimo`
- [ ] Notificación email/webhook cuando se detecta alerta

### [FEAT] Integración fuentes externas
- [ ] FAO FIRMS: capturas globales por especie para contexto internacional (Issue #10)
- [ ] CONICET/UTN: publicaciones científicas para enriquecer KB (Issue #11)
- [ ] Capturas reales SIPA/SAGPyA: validar cuotas vs capturas efectivas

### [IMPROVEMENT] Mejoras al parser
- [ ] Extraer fecha exacta de cada resolución (no solo del acta)
- [ ] Detectar miembros que votaron en contra por nombre
- [ ] Manejo de actas multi-sesión (plenarios largos)

---

## 🟢 Prioridad Baja (Sprint 4)

### [FEAT] API REST FastAPI (Issue #13)
- [ ] `GET /actas`, `GET /resoluciones/{id}`, `POST /search`, `POST /analyze`
- [ ] Documentación OpenAPI auto-generada

### [FEAT] Reporte PDF ejecutivo (Issue #12)
- [ ] Template reportlab: portada, hallazgos, evidencia textual, gráficos
- [ ] Generación desde dashboard

### [IMPROVEMENT] Infraestructura (Issue #14)
- [ ] Docker + docker-compose
- [ ] GitHub Actions: pipeline completo con PDFs de prueba en CI

---

## 📌 Decisiones Pendientes

| Decisión | Opciones | Deadline |
|----------|---------|---------|
| ¿Dónde hospedar el dashboard? | Streamlit Cloud / HuggingFace Spaces / VPS | Sprint 3 |
| ¿Publicar datos procesados? | Dataset abierto en Hugging Face / Zenodo | Sprint 4 |
| ¿Framework de anotación NER? | Prodigy (pago) / Label Studio (libre) / Doccano | Sprint 2 |

---

## 🐛 Bugs conocidos

- [ ] El parser puede fallar en actas con estructura atípica (sesiones extraordinarias muy cortas)
- [ ] El delay de scraping hardcodeado en el dashboard no usa `config/settings.yaml`

---

## 💡 Ideas para investigación futura

- Análisis de sentimiento en declaraciones de miembros del CFP
- Modelo predictivo: ¿qué variables predicen una cuota por encima de la CBA?
- Red de conflictos de interés: directores de empresas pesqueras en cargos públicos
- Comparación internacional: decisiones CFP vs organismos equivalentes (Chile, Perú, UE)
- Publicación como dataset abierto en Hugging Face (actas procesadas 1998–2025)
