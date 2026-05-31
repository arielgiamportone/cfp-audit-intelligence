# CFP Audit Intelligence Platform

**Plataforma de Auditoría Inteligente del Consejo Federal Pesquero de Argentina**

> Extrae, procesa y analiza con IA 25+ años de actas públicas del CFP para auditar decisiones sobre los recursos pesqueros argentinos y contrastarlas con las recomendaciones científicas del INIDEP.

[![Tests](https://github.com/arielgiamportone/cfp-audit-intelligence/actions/workflows/ci.yml/badge.svg)](https://github.com/arielgiamportone/cfp-audit-intelligence/actions)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Tests: 609](https://img.shields.io/badge/tests-609%20passing-brightgreen.svg)](#tests)

---

## Objetivo

Construir una **knowledge base** completa del CFP (1998–presente) y aplicar analítica + IA para:

1. **Auditar** 25 años de decisiones sobre recursos pesqueros y acuícolas
2. **Detectar patrones** que atenten contra la sostenibilidad de la pesca argentina
3. **Contrastar** cuotas CFP contra recomendaciones científicas del INIDEP (Ley 24.922, Art. 9)
4. **Generar evidencia** técnica reproducible para el debate público y la política pesquera

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
              │           DASHBOARD STREAMLIT (12 páginas)       │
              │  Adquisición │ KB │ Auditoría │ INIDEP │ FAO     │
              │  Timeline │ Grafo │ Alertas │ Reporte │ CONICET  │
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
pytest                    # 609 tests, todos verdes
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
- [x] Dashboard Streamlit de 12 páginas
- [x] **609 tests pasando**

### Pendiente

- [ ] Capturas SIPA integradas en el comparador
- [ ] Mejoras al parser (fecha exacta por resolución, votos disidentes por nombre)
- [ ] Deployment (Streamlit Cloud / HuggingFace / VPS)
- [ ] Dataset abierto en HuggingFace / Zenodo

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

---

**Por la soberanía y sostenibilidad de los recursos pesqueros argentinos**
