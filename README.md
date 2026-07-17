# CFP Audit Intelligence Platform

**Plataforma de Auditoría Inteligente del Consejo Federal Pesquero de Argentina**

> Extrae, procesa y analiza con IA 25+ años de actas públicas del CFP para auditar decisiones sobre los recursos pesqueros argentinos y contrastarlas con las recomendaciones científicas del INIDEP.

[![Tests](https://github.com/arielgiamportone/cfp-audit-intelligence/actions/workflows/ci.yml/badge.svg)](https://github.com/arielgiamportone/cfp-audit-intelligence/actions)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Tests: 945](https://img.shields.io/badge/tests-945%20passing-brightgreen.svg)](#tests)

---

## 🎓 Trabajo Final de Máster (TFM)

Este proyecto se presenta como **Trabajo Final del _Máster en Desarrollo con IA_** (campus.thebigschool.com).

> **Proyecto de largo recorrido:** `cfp-audit-intelligence` es una iniciativa personal iniciada **antes** del máster y que ha ido **evolucionando durante el mismo**, aplicando de forma directa lo aprendido: **arquitectura de software** (capas + ADRs 001–010), **buenas prácticas y testing** (945 tests, CI/CD), **IA generativa y RAG** (Claude API + ChromaDB), **MLOps** e **IA responsable** (Model Card, Datasheet, límites éticos). El TFM es, por tanto, la consolidación de ese recorrido con los estándares del máster.

🔗 **App en vivo:** https://cfp-audit-intelligence-um5xi4fkkiyq2gtuownvuz.streamlit.app

### Entregables

| # | Entregable | Enlace |
|---|-----------|--------|
| 1 | Código fuente (repo público GitHub) | https://github.com/arielgiamportone/cfp-audit-intelligence |
| 2 | Documentación (este README + `docs/`) | [`docs/`](docs/) |
| 3 | Despliegue en funcionamiento (URL) | **[App en vivo ↗](https://cfp-audit-intelligence-um5xi4fkkiyq2gtuownvuz.streamlit.app)** |
| 4 | Slides de presentación | ⏳ _pendiente de publicar_ |
| 5 | Vídeo explicativo (captura de pantalla) | ⏳ _pendiente de publicar_ |

**Acceso a la aplicación:** la app es de acceso **público y no requiere login** (no hay usuario/contraseña de prueba). Las funciones de auditoría con IA requieren configurar `ANTHROPIC_API_KEY` como secreto de despliegue (ver [Variables de Entorno](#variables-de-entorno)).

### Dónde está cada punto de la documentación exigida
1. **Descripción general** → [Objetivo](#objetivo)
2. **Stack tecnológico** → [Stack tecnológico](#stack-tecnológico)
3. **Instalación y ejecución** → [Inicio Rápido](#inicio-rápido)
4. **Estructura del proyecto** → [Estructura del proyecto](#estructura-del-proyecto)
5. **Funcionalidades principales** → [Módulos](#módulos) y [Estado del Proyecto](#estado-del-proyecto-v04)
6. **Credenciales de prueba** → no aplica (aplicación sin login, ver arriba)

---

## Stack tecnológico

| Capa | Tecnologías |
|------|-------------|
| Lenguaje | Python 3.10+ |
| Interfaz | Streamlit (dashboard 17 páginas) |
| API | FastAPI + OpenAPI |
| IA / LLM | Claude API (Anthropic) con prompt caching |
| RAG / Vector store | ChromaDB + embeddings `paraphrase-multilingual-MiniLM-L12-v2` |
| NLP | spaCy (NER pesquero: EntityRuler) |
| Extracción PDF/OCR | pdfplumber · PyMuPDF · Tesseract |
| Análisis / grafos | NetworkX · pyvis · pandas · scikit-learn |
| Reportes | reportlab (PDF ejecutivo) |
| Persistencia | SQLite (catálogo + modelo de datos) |
| Infra / calidad | Docker · docker-compose · GitHub Actions (CI) · pytest (945 tests) · ruff |

---

## Estructura del proyecto

```
cfp-audit-intelligence/
├── src/
│   ├── acquisition/     # Scrapers: CFP, INIDEP, SIPA, FAO, CONICET, geovisor, CONAE
│   ├── processing/      # Extracción PDF (cascada), parser de actas, NER pesquero
│   ├── knowledge_base/  # ChromaDB + embeddings multilingües
│   ├── analysis/        # audit_engine (Claude), comparador CBA/CMP, alertas, grafos, reportes
│   ├── api/             # FastAPI (5 routers + OpenAPI)
│   ├── dashboard/       # App Streamlit (17 páginas) — punto de entrada: app.py
│   └── evaluation/      # Métricas y evaluación
├── scripts/             # run_full_pipeline.py, scrapers, utilidades
├── docs/                # ARCHITECTURE, DATA_PIPELINE, MODEL_CARD, DATASHEET, ADRs 001–010, bibliografía
├── notebooks/           # Exploración y análisis
├── tests/               # 945 tests (pytest)
├── data/                # Datos del pipeline (SQLite, PDFs, artefactos)
├── config/              # Configuración
├── Dockerfile · docker-compose.yml · Makefile
├── requirements.txt · requirements-deploy.txt · pyproject.toml
└── README.md
```

---

## Objetivo

Construir una **knowledge base** completa del CFP (1998–presente) y aplicar analítica + IA para:

1. **Auditar** 25 años de decisiones sobre recursos pesqueros y acuícolas
2. **Detectar patrones** que atenten contra la sostenibilidad de la pesca argentina
3. **Contrastar** cuotas CFP contra recomendaciones científicas del INIDEP (Ley 24.922, Art. 9)
4. **Generar evidencia** técnica reproducible para el debate público y la política pesquera

---

## Documentación Técnica

| Documento | Contenido |
|-----------|-----------|
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Arquitectura completa: capas, módulos, contratos de datos, flujo end-to-end, stack tecnológico |
| [`docs/DATA_PIPELINE.md`](docs/DATA_PIPELINE.md) | Tratamiento e integridad de datos: cascade PDF, parseo estructural, hashing SHA256, idempotencia, provenance chain |
| [`docs/ANALYSIS_METHODOLOGY.md`](docs/ANALYSIS_METHODOLOGY.md) | Fundamentos técnicos: triángulo CBA·CMP·Captura, umbrales con citas, HHI+chi², groundedness, kappa, sensibilidad |
| [`docs/MODEL_CARD.md`](docs/MODEL_CARD.md) | Model Card (Mitchell 2019): audit_engine + modelo predictivo |
| [`docs/DATASHEET.md`](docs/DATASHEET.md) | Datasheet for Datasets (Gebru 2021): composición, procesamiento, limitaciones |
| [`docs/bibliography.md`](docs/bibliography.md) | Bibliografía académica verificada (30+ refs con DOI) |
| [`docs/adr/`](docs/adr/) | ADR 001–010: decisiones de arquitectura con contexto y justificación |

---

## Arquitectura

```
┌─────────────────────────────────────────────────────────────────────┐
│                      CFP AUDIT INTELLIGENCE v0.4                     │
├────────────┬───────────────┬──────────────┬──────────────────────────┤
│ ADQUISICIÓN│ PROCESAMIENTO │  KNOWLEDGE   │       ANÁLISIS + IA      │
│            │               │    BASE      │                          │
│ • CFP PDFs │ • pdfplumber  │ • ChromaDB   │ • Claude API             │
│ • INIDEP   │ • PyMuPDF     │ • SQLite     │ • Comparador CBA vs CMP  │
│   492 ITOs │ • OCR Tess.   │ • Embeddings │ • Alertas (4 niveles)    │
│ • SIPA     │ • NER spaCy   │   multilíng. │ • Grafo de relaciones    │
│ • FAO FIRMS│ • Parser CFP  │              │ • Reporte PDF ejecutivo  │
│ • CONICET  │               │              │ • Detector patrones HHI  │
└────────────┴───────────────┴──────────────┴──────────────────────────┘
                                    │
              ┌─────────────────────▼─────────────────────────┐
              │           DASHBOARD STREAMLIT (17 páginas)       │
              │  Adquisición │ KB │ Auditoría │ INIDEP │ FAO     │
              │  Timeline │ Grafo │ Alertas │ Reporte │ CONICET  │
              │  Capturas │ Investigación │ Evaluación │ Conflictos│
              │  Geovisor SERE │ CONAE Satelital                  │
              └──────────────────────────────────────────────────┘
                                    │
              ┌─────────────────────▼─────────────────────────┐
              │              API REST FastAPI                     │
              │  /actas  /resoluciones  /search  /alertas        │
              │  /inidep/evaluaciones  /comparacion  /entidades  │
              └──────────────────────────────────────────────────┘
```

---

## Módulos

### Adquisición

| Módulo | Fuente | Descripción |
|--------|--------|-------------|
| `src/acquisition/batch_scraper.py` | cfp.gob.ar | Scraping masivo + descarga PDFs con retry |
| `src/acquisition/catalog_manager.py` | SQLite | Catálogo con trazabilidad completa del pipeline |
| `src/acquisition/inidep_scraper.py` | INIDEP Mar Abierto | DSpace 7 API → 492 ITOs, extracción CBA |
| `src/acquisition/sipa_scraper.py` | SAGPyA/SIPA | Capturas reales por especie y año |
| `src/acquisition/fao_firms_scraper.py` | FAO FIRMS | Capturas mundiales + estado de stocks globales |
| `src/acquisition/conicet_scraper.py` | CONICET/INIDEP | Publicaciones científicas por especie |
| `src/acquisition/inidep_geovisor_scraper.py` | Geovisor SERE (INIDEP) | Vedas geoespaciales: número de resolución + link al PDF oficial (WFS GeoServer) |
| `src/acquisition/conae_marine_scraper.py` | CONAE Geoportal Marino | Esfuerzo pesquero GFW AIS + SST + Clorofila-a (WMS GetFeatureInfo) — 4° vértice |

### Procesamiento

| Módulo | Descripción |
|--------|-------------|
| `src/processing/pdf_extractor.py` | Cascada: pdfplumber → PyMuPDF → OCR Tesseract |
| `src/processing/document_parser.py` | Parser actas CFP: resoluciones, votos, quórum |
| `src/processing/ner_pesquero.py` | EntityRuler spaCy: ESPECIE, EMPRESA, PERSONA_CFP, ZONA, BUQUE |

### Análisis

| Módulo | Descripción |
|--------|-------------|
| `src/analysis/audit_engine.py` | Claude API con prompt caching para análisis masivo |
| `src/analysis/pattern_detector.py` | HHI concentración, votaciones, reversiones estadísticas |
| `src/analysis/inidep_comparator.py` | CBA (INIDEP) vs CMP (CFP): 4 niveles de alerta |
| `src/analysis/geovisor_cross_validator.py` | Cruce de vedas del geovisor SERE vs. citas en el corpus (ADR-009) + verificación satelital de cumplimiento vía CONAE GFW AIS (ADR-010) |
| `src/analysis/alert_engine.py` | 4 tipos de alerta configurables |
| `src/analysis/graph_builder.py` | NetworkX + pyvis: red empresas–resoluciones–miembros |
| `src/analysis/report_generator.py` | Reporte PDF ejecutivo con reportlab |

### Knowledge Base y API

| Módulo | Descripción |
|--------|-------------|
| `src/knowledge_base/vector_store.py` | ChromaDB + `paraphrase-multilingual-MiniLM-L12-v2` |
| `src/api/` | FastAPI con 5 routers + documentación OpenAPI |

---

## Inicio Rápido

### Instalación

```bash
git clone https://github.com/arielgiamportone/cfp-audit-intelligence.git
cd cfp-audit-intelligence
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m spacy download es_core_news_sm
cp .env.example .env   # completar ANTHROPIC_API_KEY
```

### Pipeline

```bash
# End-to-end completo
python scripts/run_full_pipeline.py --years 1998-2025

# Etapas individuales
python scripts/run_full_pipeline.py --step download --years 2020-2025
python scripts/run_full_pipeline.py --step process
python scripts/run_full_pipeline.py --step knowledge_base
python scripts/run_full_pipeline.py --step audit --limit 50
python scripts/run_full_pipeline.py --step inidep          # scraping 492 ITOs INIDEP
python scripts/run_full_pipeline.py --step inidep --enrich-pdf  # + extracción desde PDFs
python scripts/run_full_pipeline.py --step geovisor        # vedas geoespaciales SERE (INIDEP)
python scripts/run_full_pipeline.py --step conae           # esfuerzo satelital GFW + SST + Clorofila
```

### Dashboard

```bash
streamlit run src/dashboard/app.py
```

### API REST

```bash
uvicorn src.api.main:app --reload
# Documentación: http://localhost:8000/docs
```

### Docker

```bash
docker-compose up --build
# api: http://localhost:8000 | dashboard: http://localhost:8501
```

---

## Tests

```bash
pytest                    # 945 tests, todos verdes
pytest -k "inidep" -v     # subset INIDEP
make test                 # via Makefile
```

CI en GitHub Actions corre lint (ruff) + tests (Python 3.10 y 3.11) + docker build.

---

## Triángulo de Auditoría

El módulo central cruza tres fuentes para detectar sobreasignación de cuotas:

```
INIDEP (CBA científica)
        │
        ▼
   ¿CFP aprueba más?  →  SIPA (captura real)
        │                       │
        └──── nivel de alerta ──┘
```

### Sistema de alertas (Comparador CFP vs. INIDEP)

| Nivel | Criterio | Acción sugerida |
|-------|----------|-----------------|
| 🟢 Verde | CMP ≤ 100% CBA | Dentro del límite científico |
| 🟡 Amarillo | CMP 101–115% CBA | Monitorear de cerca |
| 🔴 Rojo | CMP 116–130% CBA | Sobreasignación significativa |
| ⚫ Crítico | CMP > 130% CBA | Riesgo crítico de sostenibilidad |

Datos verificados disponibles para: **merluza** (ITO 36-37/2024), **centolla** (ITO 31/2025), **abadejo**, **polaca**, **langostino**, **calamar illex**, **merluza negra**.

### Alertas del motor de análisis

- `cuota_supera_cba` — CFP aprobó más del límite científico
- `empresa_recurrente` — misma empresa beneficiada en múltiples resoluciones
- `veda_revertida` — decisión de veda revertida en sesión posterior
- `quorum_minimo` — decisiones tomadas con quórum mínimo

---

## Modelo de Datos

```sql
-- Pipeline CFP
actas(id, year, nombre, url, filename, is_anexo, local_path, file_hash,
      download_status, text_extracted, text_path, embedded, analyzed)

resoluciones(id, acta_id, numero, tipo, fecha, texto_completo, texto_resumen,
             votos_favor, votos_contra, abstenciones, quorum,
             riesgo_score, categoria, analisis_ia)

entidades(id, tipo, nombre, nombre_norm)
menciones(id, resolucion_id, entidad_id, contexto, sentimiento)
analisis_sesiones(id, acta_id, tipo_analisis, resultado_json, modelo_ia, tokens_usados)

-- Triángulo de auditoría
inidep_evaluaciones(id, especie, especie_code, zona, year,
                    cba_recomendada_tn, cba_alternativa_tn,
                    estado_stock, numero_ito, fuente_url, notas, created_at)

cfp_cuotas(id, especie_code, zona, year, cmp_tn, resolucion_cfp, fecha_resolucion)

comparacion_cfp_inidep(id, especie_code, zona, year,
                       cba_tn, cmp_tn, diferencia_tn, diferencia_pct,
                       nivel_alerta, created_at)

-- Fuentes externas
fao_capturas(id, especie_code, year, pais, captura_tn, fuente, created_at)
fao_stock_status(id, especie_code, year, estado, descripcion, fuente, created_at)
conicet_publicaciones(id, titulo, autores, año, revista, doi, especie_code, resumen)
sipa_capturas(id, especie_code, year, captura_tn, buques, fuente, created_at)

vedas_geoespaciales(id, capa, especie, especie_code, area, fecha_inicio, fecha_fin,
                    resolucion_numero, resolucion_fuente, resolucion_url,
                    geometry_type, fuente, created_at)

-- 4° vértice: verificación satelital independiente (CONAE, ADR-010)
esfuerzo_satelital(id, zona, especie_code, fecha, lon, lat,
                   sst, sst_noche, clorofila, clorofila_8d,
                   esfuerzo_gfw, luces_noche, fuente, created_at)
```

---

## Estado del Proyecto (v0.4)

### Completado

- [x] Pipeline CFP: scraping, PDF, parsing, embeddings, auditoría IA
- [x] NER pesquero especializado — 6 categorías de entidades (spaCy)
- [x] Comparador CBA vs CMP con 4 niveles de alerta
- [x] Scraping completo 492 ITOs INIDEP Mar Abierto (DSpace 7 API)
- [x] Timeline interactivo de cuotas históricas 1998–2025
- [x] Grafo de relaciones empresas–CFP–decisiones (NetworkX + pyvis)
- [x] Sistema de alertas configurables (4 tipos)
- [x] API REST FastAPI con 5 routers y documentación OpenAPI
- [x] Reporte PDF ejecutivo automático (reportlab)
- [x] Docker multi-stage + GitHub Actions CI (Python 3.10/3.11)
- [x] Integración FAO FIRMS (capturas mundiales, estado de stocks)
- [x] Publicaciones científicas CONICET/INIDEP por especie
- [x] Dashboard Streamlit de 17 páginas
- [x] Integración CONAE Geoportal Marino — 4° vértice satelital (GFW AIS + SST + Clorofila, ADR-010)
- [x] **945 tests pasando**

### Pendiente

- [x] Capturas SIPA en comparador (seed SAGPyA verificado; pull real de SIPA pendiente cuando el pipeline produzca `cfp_cuotas` con datos reales)
- [ ] Mejoras al parser (fecha exacta por resolución, votos disidentes por nombre)
- [ ] Deployment (Streamlit Cloud / HuggingFace / VPS)
- [ ] Dataset abierto en HuggingFace / Zenodo

---

## Escalabilidad y trabajo futuro

El proyecto está diseñado para escalar del **modo demo** (entrega TFM) al **modo productivo** sin cambiar la arquitectura:

| Dimensión | Modo demo (actual, coste ~0) | Modo productivo (futuro) |
|-----------|------------------------------|--------------------------|
| **Datos** | Comparador CBA/CMP y contexto (FAO, CONICET, capturas) **auto-sembrados** + subconjunto de actas | Corpus completo 1998–2025 (cientos de actas + 492 ITOs INIDEP) |
| **Auditoría IA** | Muestra acotada (`--step audit --limit`) para demostrar el flujo | Auditoría masiva con Claude API + *prompt caching* sobre todo el corpus |
| **Hosting** | Streamlit Community Cloud (gratuito, solo lectura sobre SQLite) | VPS / contenedor dedicado (Docker ya provisto) con más RAM/CPU |
| **Vector store** | ChromaDB local | ChromaDB persistente / servicio gestionado para RAG a escala |
| **Coste** | Sin coste de tokens (datos sembrados) | Presupuesto de API dimensionado al volumen del corpus |

La arquitectura por capas, los contratos de datos, el pipeline idempotente (hashing SHA256, *provenance chain*) y el `docker-compose` permiten esta transición **sin reescritura**: basta con proveer infraestructura y presupuesto de API. El diseño demo↔producción es deliberado y forma parte de la estrategia del proyecto.

---

## Variables de Entorno

```env
ANTHROPIC_API_KEY=sk-ant-...      # Requerida para audit y reportes
CLAUDE_MODEL=claude-sonnet-4-6    # Análisis masivos
CLAUDE_AUDIT_MODEL=claude-opus-4-8  # Análisis profundo
```

---

## Marco Legal y Ético

Trabaja exclusivamente con **documentos públicos** del CFP, organismo colegiado creado por la **Ley Federal de Pesca N° 24.922**.

- Fuente primaria: [cfp.gob.ar/actas-cfp](https://cfp.gob.ar/actas-cfp)
- Fuente científica: [marabierto.inidep.edu.ar](https://marabierto.inidep.edu.ar)
- El análisis es **descriptivo** — los hallazgos no constituyen acusación legal
- Todos los resultados están marcados como "requieren verificación"
- Metodología reproducible y código abierto
- Marco ético completo y citable: [`docs/adr/007-limites-eticos.md`](docs/adr/007-limites-eticos.md)

---

## Bases bibliográficas

La bibliografía académica verificada del proyecto (gobernanza pesquera argentina, brecha
ciencia-política, NLP regulatorio, concentración corporativa e IA responsable) está en
[`docs/bibliography.md`](docs/bibliography.md).

Referencias mínimas indispensables:

| Referencia | Relevancia |
|-----------|-----------|
| Da Rocha, Villasante & Trelles González (2013) — *Ambio* | Marco teórico brecha CBA→CMP |
| Froese et al. (2025) — *Science* | "Overfishing ratchet" europeo; equivalente del hallazgo central |
| Gualdoni, Pagani & Bertolotti (2014) — *FACES* | Análisis institucional del CITC argentino |
| Bertolotti et al. (2015) — UNMdP | Desempeño empírico CITC (hipótesis a validar 2010–2025) |
| Villasante et al. (2015) — *Sea Around Us* | Reconstrucción IUU Argentina 55% sub-reportado |
| Österblom et al. (2015) — *PLOS ONE* | Keystone actors; base metodológica del análisis de grafo |
| Coglianese & Lehr (2017) — *Georgetown Law Journal* | IA en regulación administrativa |
| Mitchell et al. (2019) — *FAT\* '19* | Model Cards (`docs/MODEL_CARD.md`) |
| Gebru et al. (2021) — *CACM* | Datasheets for Datasets (`docs/DATASHEET.md`) |
| INIDEP ITOs 32/2024 y 34/2024 | Fuente primaria CBA actual |


---

## Autoría y Declaración de Asistencia IA

**Autor:** Ariel L. Giamportone (Ingeniero Pesquero | Data Scientist)

**Contribuciones humanas:** El diseño metodológico, la elección y justificación de umbrales
(115%/130% CBA), la selección de fuentes bibliográficas, la interpretación de los hallazgos,
todas las decisiones de arquitectura (documentadas en `docs/adr/`), y la supervisión del
desarrollo son responsabilidad del autor. El autor operó el pipeline, validó los resultados
contra documentos primarios (ITOs INIDEP, actas CFP públicas) y tomó todas las decisiones
de diseño relevantes para la validez científica.

**Asistencia IA:** Se utilizó Claude (Anthropic) como herramienta de asistencia en la
implementación de código, redacción de documentación técnica y revisión de tests, bajo
supervisión y dirección continua del autor. Todas las decisiones metodológicas y de
interpretación son humanas. El audit_engine usa Claude como herramienta analítica sobre
documentos públicos, con salvaguardas de groundedness y marcado `[BAJA_EVIDENCIA]` para
hallazgos sin anclaje textual suficiente (ver `docs/adr/007-limites-eticos.md`).

**Recomendación OSF:** Pre-registrar el plan analítico de cada entrega ALG en el Open
Science Framework *antes* de re-correr con datos reales del pipeline, para prevenir
críticas de ajuste post-hoc (ver ADR-007).

**GPG:** Los commits significativos deben firmarse con la identidad GPG del autor para
atribución verificable en revisión por pares.

---

**Por la soberanía y sostenibilidad de los recursos pesqueros argentinos**
