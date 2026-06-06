# CFP Audit Intelligence — Guía para Agentes IA

> Última actualización: 2026-05-30 | Versión: v0.4  
> Repositorio GitHub: `arielgiamportone/cfp-audit-intelligence`  
> Branch principal: `main`

---

## Qué es este proyecto

Plataforma de **auditoría inteligente** de las actas públicas del Consejo Federal Pesquero (CFP) de Argentina. Extrae, procesa y analiza con IA 25+ años de decisiones sobre recursos pesqueros para detectar patrones que atenten contra la sostenibilidad y los intereses nacionales.

- **Datos fuente**: PDFs públicos de sesiones CFP 1998–2025 + repositorios INIDEP, SIPA/SAGPyA, FAO FIRMS, CONICET
- **Objetivo principal**: Triángulo de auditoría — CBA (INIDEP) → CMP (CFP) → Captura real (SIPA)
- **Stack**: Python 3.11 · SQLite · ChromaDB · Claude API · Streamlit · FastAPI

---

## LEER PRIMERO antes de codificar

1. **Este archivo** — arquitectura, convenciones y estado actual
2. **`TODO.md`** — backlog priorizado; define qué construir ahora y qué está hecho
3. **`AGENTS.md`** — reglas por tipo de agente y flujo multi-entorno
4. **`docs/adr/`** — decisiones de arquitectura tomadas (no re-decidir sin ADR nuevo)

---

## Coordinación multi-entorno

Este proyecto se desarrolla en **dos entornos simultáneos**. Ambos trabajan sobre el mismo `main`:

| Entorno | Herramienta | Push git | Pull git |
|---------|------------|---------|----------|
| Web remoto | Claude Code en claude.ai/code | MCP `push_files` (proxy bloquea HTTP push) | `git fetch origin main` ✓ |
| Local | Claude Code en VS Code / terminal | `git push` directo ✓ | `git pull origin main` ✓ |

### Protocolo de sincronización

**Antes de empezar cualquier sesión:**
```bash
git fetch origin main
git reset --hard origin/main   # descarta commits locales no pusheados
```

**En el entorno web (claude.ai/code):**
- `git push` falla con HTTP 503 por proxy local en `127.0.0.1`
- Usar herramienta MCP `mcp__github__push_files` para subir archivos
- Después del push MCP: `git fetch origin main && git reset --hard origin/main`
- Nunca dejar commits locales sin pushear al terminar la sesión

**En VS Code / terminal local:**
- Push normal: `git push -u origin main` o `git push -u origin feat/nombre`
- Pull para sincronizar con cambios del entorno web: `git pull origin main`

**Fuente de verdad única:**
- `TODO.md` → estado de tareas (marcar `[x]` al completar)
- `main` en GitHub → código canónico
- Nunca hay "versión local" válida que no esté en GitHub

---

## Estructura del proyecto

```
src/
  acquisition/
    batch_scraper.py       → Scraper CFP con retry y rate limiting
    catalog_manager.py     → CRUD SQLite para actas y estado pipeline
    inidep_scraper.py      → DSpace 7 API → 492 ITOs de Mar Abierto
    sipa_scraper.py        → Capturas reales SAGPyA/SIPA por especie/año
    fao_firms_scraper.py   → Datos FAO: capturas Argentina + estado stocks
    conicet_scraper.py     → Publicaciones científicas INIDEP/CONICET
    inidep_geovisor_scraper.py → Geovisor SERE (WFS GeoServer): vedas geoespaciales + link al PDF oficial

  processing/
    pdf_extractor.py       → Cascada: pdfplumber → PyMuPDF → OCR Tesseract
    document_parser.py     → Parser actas CFP (resoluciones, votos, quórum)
    ner_pesquero.py        → EntityRuler spaCy: ESPECIE, EMPRESA, PERSONA_CFP…

  analysis/
    audit_engine.py        → Claude API + prompt caching, análisis de resoluciones
    pattern_detector.py    → HHI concentración, votaciones, reversiones estadísticas
    inidep_comparator.py   → CBA vs CMP: 4 niveles de alerta
    geovisor_cross_validator.py → Cruce vedas geovisor SERE vs. citas en corpus de actas (ground truth externo, ADR-009)
    alert_engine.py        → Alertas: cuota > CBA, empresa recurrente, veda revertida
    graph_builder.py       → NetworkX + pyvis: empresas–resoluciones–miembros
    report_generator.py    → Reportlab: reporte PDF ejecutivo

  knowledge_base/
    vector_store.py        → ChromaDB con embeddings paraphrase-multilingual-MiniLM-L12-v2

  api/
    main.py                → FastAPI app principal
    models.py              → Pydantic schemas
    deps.py                → Dependencias compartidas
    routers/
      actas.py             → GET /actas, GET /actas/{id}
      analysis.py          → POST /search, POST /analyze
      alertas.py           → GET /alertas
      inidep.py            → GET /inidep/evaluaciones, GET /comparacion
      entidades.py         → GET /entidades

  dashboard/
    app.py                 → Streamlit entry point
    pages/
      01_Adquisicion.py    → Estado pipeline, descarga
      02_Knowledge_Base.py → Estadísticas ChromaDB
      03_Auditoria.py      → Resultados análisis IA
      04_Reportes.py       → Exportar datos
      05_INIDEP_Comparador.py → CBA vs CMP con alertas
      06_Timeline.py       → Evolución histórica de cuotas por especie
      07_Grafo.py          → Red de relaciones interactiva
      08_Alertas.py        → Panel de alertas configurables
      09_Reporte.py        → Generación y descarga PDF ejecutivo
      10_FAO_FIRMS.py      → Capturas mundiales vs Argentina
      11_CONICET.py        → Publicaciones científicas por especie
      12_Capturas.py       → Capturas reales SIPA
      13_Investigacion.py  → Hub Serie FisheriesAudit ALG (figuras, exports, posts)
      14_Evaluacion.py     → Evaluación ground truth, groundedness, sensibilidad
      15_Conflictos.py     → Red de conflictos de interés CFP-industria
      16_Geovisor.py       → Vedas geoespaciales del geovisor SERE (INIDEP) + cobertura del corpus

scripts/
  run_full_pipeline.py     → Pipeline CLI completo
  scrape_inidep.py         → Script standalone INIDEP

tests/
  conftest.py              → Fixtures compartidas
  test_alert_engine.py
  test_api.py
  test_catalog_manager.py
  test_conicet_scraper.py
  test_document_parser.py
  test_fao_firms.py
  test_inidep_comparator.py
  test_inidep_issue9.py    → 44 tests flujo completo 492 ITOs
  test_inidep_scraper.py
  test_inidep_scraper_api.py
  test_inidep_scraper_persistence.py
  test_ner_pesquero.py
  test_report_generator.py
  test_sipa_scraper.py

data/                      → gitignored (solo .gitkeep)
  raw/                     → PDFs descargados
  processed/               → catalog.db + text/ + json/
  knowledge_base/          → ChromaDB persistente
  reports/                 → PDFs generados

config/settings.yaml       → Especies, modelos, umbrales
docs/adr/                  → ADR 001–004
Dockerfile                 → Multi-stage, non-root
docker-compose.yml         → api + dashboard con healthchecks
.github/workflows/ci.yml   → lint + test (3.10/3.11) + docker-build
```

---

## Pipeline CLI

```bash
# Pipeline completo (todas las etapas)
python scripts/run_full_pipeline.py --years 1998-2025

# Etapas individuales
python scripts/run_full_pipeline.py --step download --years 2020-2025
python scripts/run_full_pipeline.py --step process
python scripts/run_full_pipeline.py --step knowledge_base
python scripts/run_full_pipeline.py --step audit --limit 50
python scripts/run_full_pipeline.py --step inidep
python scripts/run_full_pipeline.py --step inidep --limit 20 --enrich-pdf
python scripts/run_full_pipeline.py --step geovisor

# Dashboard
streamlit run src/dashboard/app.py

# API REST
uvicorn src.api.main:app --reload

# Tests
pytest                          # todos (915 actualmente)
pytest tests/test_inidep_issue9.py -v
pytest -k "inidep" -v

# Via Make
make pipeline    # end-to-end
make dashboard
make test
make stats       # estadísticas del catálogo
```

---

## Instalación

```bash
pip install -r requirements.txt
python -m spacy download es_core_news_sm
cp .env.example .env          # completar ANTHROPIC_API_KEY
```

---

## Variables de entorno

Archivo `.env` (nunca commitear):

```env
ANTHROPIC_API_KEY=sk-ant-...      # Requerida para audit y report
CLAUDE_MODEL=claude-sonnet-4-6    # Análisis masivos
CLAUDE_AUDIT_MODEL=claude-opus-4-8  # Deep analysis (más lento, más profundo)
```

**Regla absoluta**: nunca hardcodear `ANTHROPIC_API_KEY` en ningún archivo del repo.

---

## Límites éticos

Marco completo y citable en **`docs/adr/007-limites-eticos.md`**: análisis descriptivo
no acusatorio, solo datos públicos, no difamación, hallazgos que requieren verificación,
conflictos de interés (`verificado=FALSE`) que exigen validación legal, salvaguarda de
groundedness, y recomendaciones de pre-registro OSF + firma GPG para publicación.

---

## Tecnologías

| Capa | Tecnología |
|------|------------|
| Scraping | requests, beautifulsoup4, tenacity |
| PDF | pdfplumber, PyMuPDF (fitz), pytesseract + Tesseract |
| NLP | spacy (es_core_news_sm), sentence-transformers |
| Vector DB | ChromaDB + `paraphrase-multilingual-MiniLM-L12-v2` |
| LLM | anthropic SDK, claude-sonnet-4-6 / claude-opus-4-8 |
| Storage | SQLite (catálogo) + ChromaDB (vectores) |
| UI | Streamlit multipágina + Plotly |
| API | FastAPI + Pydantic |
| Infra | Docker multi-stage + GitHub Actions CI |

---

## Modelo de datos (SQLite `catalog.db`)

```sql
-- Pipeline CFP
actas(id, year, nombre, url, filename, is_anexo, local_path, file_hash,
      download_status, text_extracted, text_path, embedded, analyzed)

resoluciones(id, acta_id, numero, tipo, fecha, texto_completo, texto_resumen,
             votos_favor, votos_contra, abstenciones, quorum,
             riesgo_score, categoria, analisis_ia)

entidades(id, tipo, nombre, nombre_norm)
  -- tipo: especie | empresa | persona | lugar | normativa | buque

menciones(id, resolucion_id, entidad_id, contexto, sentimiento)
analisis_sesiones(id, acta_id, tipo_analisis, resultado_json, modelo_ia, tokens_usados)

-- Triángulo de auditoría
inidep_evaluaciones(id, especie, especie_code, zona, year,
                    cba_recomendada_tn, cba_alternativa_tn,
                    estado_stock, numero_ito, fuente_url, notas, created_at)

cfp_cuotas(id, especie_code, zona, year, cmp_tn, resolucion_cfp,
           fecha_resolucion, fuente_url, notas)

comparacion_cfp_inidep(id, especie_code, zona, year,
                       cba_tn, cmp_tn, diferencia_tn, diferencia_pct,
                       nivel_alerta, created_at)

-- Fuentes externas
fao_capturas(id, especie_code, year, pais, captura_tn, fuente, created_at)
fao_stock_status(id, especie_code, year, estado, descripcion, fuente, created_at)

conicet_publicaciones(id, titulo, autores, año, revista, doi,
                      especie_code, resumen, url, created_at)

sipa_capturas(id, especie_code, year, captura_tn, buques, fuente, created_at)

vedas_geoespaciales(id, capa, especie, especie_code, area, fecha_inicio, fecha_fin,
                    resolucion_numero, resolucion_fuente, resolucion_url, notas,
                    geometry_type, fuente, created_at)
```

---

## Convenciones de código

- **Logging**: `loguru` siempre, nunca `print()`
- **Retry de red**: `tenacity` con exponential backoff (≥ 3 reintentos)
- **Validación en boundaries**: Pydantic (entrada usuario, responses API)
- **Type hints**: obligatorios en todas las funciones públicas
- **Docstrings**: en español, una línea + Args/Returns si es complejo
- **Código**: variables y funciones en inglés; comentarios y docs en español
- **Comentarios**: solo cuando el WHY no es obvio; nunca describir el WHAT
- **Tests**: toda funcionalidad nueva en `tests/`; mocks para HTTP (sin llamadas reales)
- **Números argentinos**: `300.000,5` → miles con punto, decimal con coma

### Formato de commits
```
feat(scope): descripción breve en español
fix(scope): descripción
refactor(scope): descripción
test(scope): descripción
docs: descripción
chore: descripción
```

Ejemplos:
```
feat(inidep): agregar 8 patrones CBA + get_scrape_status
fix(parser): corregir idempotencia NULL vs "" en zona
test(api): tests de endpoints /inidep con mocks HTTP
```

---

## Estado actual (v0.4)

### Módulos completados
- Pipeline CFP: scraping, PDF, parsing, embeddings, auditoría IA
- Comparador INIDEP: CBA vs CMP con 4 niveles de alerta
- NER pesquero especializado (spaCy EntityRuler)
- Timeline interactivo de cuotas históricas
- Grafo de relaciones empresas–CFP–decisiones
- Sistema de alertas configurables (4 tipos)
- API REST FastAPI con 5 routers
- Reporte PDF ejecutivo (reportlab)
- Docker multi-stage + GitHub Actions CI
- Integración FAO FIRMS (capturas mundiales)
- Publicaciones CONICET/INIDEP
- Scraping completo 492 ITOs Mar Abierto (Issue #9)
- Geovisor SERE (INIDEP): vedas geoespaciales + cruce de cobertura del corpus (ADR-009)
- **915 tests pasando**

### Pendiente (ver TODO.md)
- Mejoras al parser (fecha exacta, miembros disidentes por nombre)
- Capturas SIPA integradas en comparador
- Deployment (Streamlit Cloud / HuggingFace / VPS)
- Dataset abierto (HuggingFace / Zenodo)
