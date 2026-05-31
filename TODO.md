# CFP Audit Intelligence — Backlog y Roadmap

> Estado: 2026-05-31 | Repo: `arielgiamportone/cfp-audit-intelligence` | Branch: `main`

---

## ✅ Completado (v0.3 — Sprints 1–3)

### Infraestructura base
- [x] Scraper batch CLI con retry y rate limiting (tenacity, 1.5s delay)
- [x] Catálogo SQLite completo (`actas`, `resoluciones`, `entidades`, `menciones`, `analisis_sesiones`)
- [x] Extracción PDF en cascada (pdfplumber → PyMuPDF → OCR Tesseract)
- [x] Parser estructural de actas CFP (formato real: minutas narrativas, no resoluciones numeradas)
- [x] Vector store ChromaDB con embeddings multilingües (`paraphrase-multilingual-MiniLM-L12-v2`)
- [x] Motor de auditoría con Claude API + prompt caching
- [x] Detector de patrones estadísticos (HHI concentración, votaciones, reversiones)
- [x] Dashboard Streamlit multipágina (12 páginas activas)
- [x] Pipeline CLI end-to-end (`scripts/run_full_pipeline.py --step download|process|kb|audit|inidep`)
- [x] Makefile con targets clave
- [x] ADRs (001–004), CLAUDE.md, AGENTS.md

### Comparador CFP vs. INIDEP (Issue #4)
- [x] Scraper Mar Abierto INIDEP (`src/acquisition/inidep_scraper.py`)
- [x] Datos semilla verificados: merluza (ITO 36-37/2024), centolla (ITO 31/2025), abadejo, polaca, langostino
- [x] Schema SQLite: `inidep_evaluaciones`, `cfp_cuotas`, `comparacion_cfp_inidep`
- [x] Motor de comparación con 4 niveles de alerta (verde/amarillo/rojo/crítico)
- [x] Página dashboard `05_INIDEP_Comparador.py` con alertas, gráficos, formulario manual

### NER pesquero especializado (Issue #5)
- [x] EntityRuler spaCy con 6 categorías: ESPECIE, EMPRESA_PESQUERA, PERSONA_CFP, NORMATIVA, ZONA_PESCA, BUQUE
- [x] Integrado en `document_parser.py` reemplazando heurísticas regex
- [x] Tests en `test_ner_pesquero.py`

### Timeline interactivo por especie (Issue #6)
- [x] Dataset de cuotas históricas en `cfp_cuotas` SQLite
- [x] Página `06_Timeline.py` con Plotly y overlay INIDEP
- [x] Filtro por especie, zona, empresa

### Grafo de relaciones (Issue #7)
- [x] NetworkX + pyvis: empresas — resoluciones — miembros CFP
- [x] Detección de comunidades (`graph_builder.py`)
- [x] Página `07_Grafo.py` con visualización interactiva

### Sistema de alertas configurables (Issue #8)
- [x] Motor de alertas con 4 tipos: `cuota_supera_cba | empresa_recurrente | veda_revertida | quorum_minimo`
- [x] `test_alert_engine.py` con cobertura completa
- [x] Página `08_Alertas.py`

### API REST FastAPI (Issue #13)
- [x] `GET /actas`, `GET /resoluciones/{id}`, `POST /search`, `POST /analyze`
- [x] `/health` endpoint para Docker healthcheck
- [x] Documentación OpenAPI auto-generada
- [x] Tests en `test_api.py` y `test_inidep_scraper_api.py`

### Reporte PDF ejecutivo (Issue #12)
- [x] Template reportlab: portada, hallazgos, alertas, comparaciones CFP/INIDEP, top actores, metodología
- [x] `src/analysis/report_generator.py` con `CFPReportGenerator`
- [x] Página `09_Reporte.py` con generación y descarga PDF
- [x] 25 tests en `test_report_generator.py`

### Infraestructura Docker + CI (Issue #14)
- [x] Dockerfile multi-stage (builder → runtime, non-root user)
- [x] `docker-compose.yml` con api + dashboard, healthchecks, volumes
- [x] GitHub Actions CI 3 jobs: lint (ruff), test (matrix 3.10/3.11), docker-build
- [x] `.dockerignore` optimizado

### Integración FAO FIRMS (Issue #10)
- [x] `src/acquisition/fao_firms_scraper.py` con 8 especies, datos seed verificados
- [x] Schema: `fao_capturas` + `fao_stock_status`
- [x] Página `10_FAO_FIRMS.py`: capturas Argentina vs. Mundo, estado de stocks, alertas sobrexplotación
- [x] 39 tests en `test_fao_firms.py`

### Publicaciones científicas CONICET/INIDEP (Issue #11)
- [x] `src/acquisition/conicet_scraper.py` con DSpace REST API y 12 publicaciones seed
- [x] `normalizar_especie_from_titulo()` con detección científico/común
- [x] Página `11_CONICET.py`: 3 tabs (por especie, búsqueda live, tabla completa)
- [x] 40 tests en `test_conicet_scraper.py`

### Scraping completo INIDEP Mar Abierto (Issue #9)
- [x] Scraping de los 492 ITOs disponibles en marabierto.inidep.edu.ar (DSpace 7 REST API)
- [x] 8 patrones `_CBA_PATTERNS` + `_parse_tn_value()` para formato argentino
- [x] `get_scrape_status()` — estadísticas de cobertura desde DB
- [x] Fix idempotencia NULL vs "" en zona (SQLite)
- [x] `--step inidep` + `--enrich-pdf` en pipeline CLI
- [x] 44 tests con fixtures HTTP mockeadas (sin llamadas reales)

### Capturas reales SIPA integradas en comparador
- [x] `capturas_reales` table en `SCHEMA_INIDEP` de `inidep_comparator.py`
- [x] `_seed_capturas_data()` — seed SAGPyA (7 especies, ~40 registros)
- [x] `compute_comparisons()` actualizado: LEFT JOIN `capturas_reales` + `alerta_captura`
- [x] `get_triangulo_completo()` — DataFrame con CBA · CMP · Captura Real + ratios
- [x] `summary_report()` incluye `n_sub_utilizacion`
- [x] Dashboard `05_INIDEP_Comparador.py`: tab "🔺 Triángulo Completo" + 3ª barra en gráfico
- [x] 23 tests nuevos en `test_inidep_comparator.py` (triángulo, alerta_captura, sub-utilización)

### Tests y CI
- [x] 650 tests totales, todos verdes
- [x] GitHub Actions CI — Python 3.10 y 3.11 + Docker build

### FisheriesAudit ALG — Serie de investigación y divulgación (Issue #15)
- [x] `src/analysis/research_exporter.py` — motor de exportación científica (ResearchExporter, PatternExporter, GraphExporter, FAOExporter)
- [x] `src/analysis/linkedin_formatter.py` — generador Serie FisheriesAudit ALG 2026
- [x] `src/dashboard/pages/13_Investigacion.py` — hub de publicación (figuras, tests, exports, posts LinkedIn)
- [x] `notebooks/FisheriesAudit_ALG_01_triangulo_auditoria.ipynb` — Entrega #01: CBA · CMP · Captura real
- [x] `notebooks/FisheriesAudit_ALG_02_patrones_historicos.ipynb` — Entrega #02: HHI, riesgo temporal, reversiones de veda
- [x] `notebooks/FisheriesAudit_ALG_03_red_relaciones.ipynb` — Entrega #03: red de relaciones empresas-especies-CFP
- [x] `notebooks/FisheriesAudit_ALG_04_contexto_internacional.ipynb` — Entrega #04: FAO FIRMS, share Argentina, estado de stocks

---

## 🔴 Prioridad Alta

*(sin tareas pendientes de alta prioridad — ver Prioridad Media)*

---

## 🟡 Prioridad Media

### [IMPROVEMENT] Mejoras al parser
- [x] Extraer fecha exacta de cada resolución (no solo del acta)
- [x] Detectar miembros que votaron en contra por nombre
- [x] Manejo de actas multi-sesión (plenarios largos)
- [x] Extraer número de resolución CFP por decisión
- [x] Detectar decisiones diferidas y denegadas
- [x] Extraer fundamentos científicos INIDEP citados
- [x] Votos nominales por institución + normalización canónica
- [x] Extraer zonas y áreas geográficas de pesca
- [x] Extraer período de vigencia de cada decisión
- [x] Extraer asignaciones empresa→cuota

### [FEAT] Capturas reales SIPA/SAGPyA integradas
- [x] Validar cuotas CFP vs capturas efectivas por especie/año
- [x] Integrar en comparador para detectar sub-utilización de cuotas

---

## 🟢 Prioridad Baja

### [INFRA] Deployment
- [ ] Publicación en Streamlit Cloud o HuggingFace Spaces
- [ ] Dataset abierto en Hugging Face / Zenodo (actas procesadas 1998–2025)

### [ANALYSIS] Investigación futura
- [ ] Modelo predictivo: ¿qué variables predicen cuota > CBA?
- [ ] Red de conflictos de interés: directores de empresas pesqueras en cargos públicos
- [ ] Comparación internacional con Chile, Perú, UE

---

## 📌 Decisiones Pendientes

| Decisión | Opciones | Deadline |
|----------|---------|----------|
| ¿Dónde hospedar el dashboard? | Streamlit Cloud / HuggingFace Spaces / VPS | Sprint 4 |
| ¿Publicar datos procesados? | Dataset abierto en Hugging Face / Zenodo | Sprint 4 |
| ¿Framework de anotación NER? | Prodigy (pago) / Label Studio (libre) / Doccano | Sprint 4 |

---

## 🐛 Bugs conocidos

- [ ] El parser puede fallar en actas con estructura atípica (sesiones extraordinarias muy cortas)
- [ ] El delay de scraping hardcodeado en el dashboard no usa `config/settings.yaml`
