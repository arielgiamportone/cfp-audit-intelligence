# Arquitectura del Sistema — CFP Audit Intelligence

> Versión: v0.4 | Última actualización: 2026-06-07  
> Este documento describe la arquitectura **real** del sistema tal como está implementada.
> Cada componente está respaldado por código en `src/`.

---

## 1. Visión General

El sistema es una plataforma de auditoría de documentos públicos que opera en seis capas:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      CFP AUDIT INTELLIGENCE v0.4                         │
├──────────────┬──────────────┬────────────────┬──────────────────────────┤
│  ADQUISICIÓN │ PROCESAMIENTO│  CONOCIMIENTO  │      ANÁLISIS + IA        │
│              │              │                │                            │
│ batch_scraper│ pdf_extractor│ vector_store   │ audit_engine (Claude API)  │
│ catalog_mgr  │ doc_parser   │ (ChromaDB)     │ inidep_comparator          │
│ inidep_scraper│ ner_pesquero│ catalog.db     │ pattern_detector           │
│ geovisor_scr │              │ (SQLite)       │ alert_engine               │
│ sipa_scraper │              │                │ conflict_detector          │
│ fao_scraper  │              │                │ graph_builder              │
│ conicet_scr  │              │                │ geovisor_cross_validator   │
│              │              │                │ sensitivity_analyzer       │
│              │              │                │ evaluator (ground truth)   │
├──────────────┴──────────────┴────────────────┴──────────────────────────┤
│                    PRESENTACIÓN Y ACCESO                                  │
│   Dashboard Streamlit (16 páginas)  │  API REST FastAPI (5 routers)       │
│   Notebooks de investigación (10)   │  Reporte PDF ejecutivo               │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Capas y Responsabilidades

### 2.1 Capa de Adquisición

| Módulo | Fuente | Responsabilidad | Salida |
|--------|--------|-----------------|--------|
| `batch_scraper.py` | `cfp.gob.ar/actas-cfp` | Scraping HTML + descarga PDFs. SSL bypass, retry ×3, rate limiting 1.5 s | `list[ActaMetadata]` + PDFs en `data/raw/` |
| `catalog_manager.py` | SQLite `catalog.db` | CRUD de todas las tablas, trazabilidad de pipeline, SHA256 de archivos | 7 tablas SQLite |
| `inidep_scraper.py` | DSpace 7 REST API (Mar Abierto) | Paginación API, extracción CBA con 8 patrones regex, normalización de especie/zona/stock | `list[ITORecord]` → `inidep_evaluaciones` |
| `inidep_geovisor_scraper.py` | WFS GeoServer SERE (`sere.inidep.edu.ar`) | WFS 2.0.0 GetFeature, 13 capas de vedas, deduplicación por `(capa, area, resolucion_numero)` | `vedas_geoespaciales` table |
| `sipa_scraper.py` | SAGPyA/datos.gob.ar | Capturas reales por especie y año | `sipa_capturas` table |
| `fao_firms_scraper.py` | FAO FIRMS | Capturas mundiales + estado de stocks globales | `fao_capturas`, `fao_stock_status` |
| `conicet_scraper.py` | CONICET/INIDEP | Publicaciones científicas por especie | `conicet_publicaciones` |

**Contrato de integridad en adquisición:**
- Cada PDF descargado recibe un hash `SHA256` → detecta duplicados y cambios en archivos
- `download_status` ∈ {`pending`, `ok`, `error`, `duplicate`} — no se re-descarga lo que ya está
- `tenacity` con `stop_after_attempt(3)` + `wait_exponential(min=2, max=30)` en todas las llamadas de red

---

### 2.2 Capa de Procesamiento

| Módulo | Entrada | Responsabilidad | Salida |
|--------|---------|-----------------|--------|
| `pdf_extractor.py` | PDF `local_path` | Cascada de extracción: pdfplumber → PyMuPDF → OCR Tesseract. Umbral mínimo 100 caracteres | `.txt` en `data/processed/text/` + stats `{ok, ocr, failed, skipped}` |
| `document_parser.py` | `.txt` de acta | Extracción estructural: fecha, quórum, miembros, decisiones, votos, asignaciones CITC, citas ITO | `Acta` (dataclass) → `.json` en `data/processed/json/` |
| `ner_pesquero.py` | Texto libre | spaCy EntityRuler con 500+ patrones: 6 categorías de entidades del dominio pesquero | `ResultadoNER` con listas deduplicadas por etiqueta |

**Cascade de extracción PDF (orden de ejecución):**
```
PDF
 ├─→ [1] pdfplumber (texto nativo)  — fast, exact, funciona con PDFs vectoriales
 │       ↓ si char_count < 100
 ├─→ [2] PyMuPDF/fitz               — mejor manejo de fuentes embebidas
 │       ↓ si char_count < 100
 └─→ [3] Tesseract OCR               — para PDFs escaneados (300 DPI, lang=spa)
         method reportado en salida para trazabilidad
```

**Dataclasses clave del parser:**

```python
@dataclass
class Decision:
    texto: str              # hasta 800 caracteres
    tipo: str               # unanimidad | mayoria | aprobacion | otro
    agenda_punto: str       # "1.1.3"
    especies_mencionadas: list[str]
    empresas_mencionadas: list[str]
    toneladas: list[float]
    votos_favor: list[str]  # instituciones
    votos_en_contra: list[str]
    abstenciones: list[str]
    numero_resolucion: str | None   # "15/2025" si se dicta una resolución
    fundamento_inidep: list[str]    # ITOs citados: ["36/2024"]
    asignaciones: list[AsignacionCuota]  # empresa → toneladas
    zona_captura: list[str]
    periodo_vigencia_inicio: str    # ISO parcial: "2025" | "2025-03"
    periodo_vigencia_fin: str

@dataclass
class Acta:
    filename: str
    year: int
    numero: str | None              # "34"
    fecha: str                      # ISO "2025-03-15"
    quorum: int
    miembros_presentes: list[str]
    decisiones: list[Decision]
    es_multi_sesion: bool
    n_sesiones: int
```

**Entidades NER (6 categorías):**

| Label | Descripción | Colores dashboard |
|-------|-------------|-------------------|
| `ESPECIE_PESCA` | Merluza hubbsi, langostino, centolla, etc. | `#1976D2` (azul) |
| `EMPRESA_PESCA` | ARGENOVA S.A., CONARPESA, etc. | `#E65100` (naranja) |
| `ZONA_PESCA` | Sur 41°S, Patagonia, GSJ, ZEE | `#388E3C` (verde) |
| `CUOTA_PESCA` | 300.000 tn, CBA 150.000 t | `#7B1FA2` (violeta) |
| `NORMATIVA_CFP` | Ley 24.922, Res. CFP N° 5/2020, Art. 9 | `#F57C00` (ámbar) |
| `BUQUE_PESCA` | B/P nombres de buque | `#0097A7` (cyan) |

---

### 2.3 Capa de Conocimiento

**SQLite `catalog.db` — 7 tablas + tablas analíticas:**

```sql
-- Pipeline CFP (core)
actas(id, year, nombre, url UNIQUE, filename, is_anexo,
      local_path, file_hash, file_size, download_status,
      text_extracted, text_path, parsed, embedded, analyzed,
      scraped_at, downloaded_at, processed_at, error_msg)

resoluciones(id, acta_id FK, numero, tipo, fecha,
             texto_completo, texto_resumen,
             votos_favor, votos_contra, abstenciones, quorum,
             riesgo_score, categoria, analisis_ia, created_at)

entidades(id, tipo, nombre, nombre_norm, UNIQUE(tipo, nombre_norm))
menciones(id, resolucion_id FK, entidad_id FK, contexto, sentimiento)

-- Reproducibilidad IA
analisis_sesiones(id, acta_id FK, tipo_analisis, resultado JSON,
                  modelo_ia, tokens_usados,
                  prompt_hash, input_hash, temperatura, created_at)
prompt_registry(id, nombre UNIQUE, version, modelo,
                system_hash, user_template, user_hash,
                temperatura, tokens_max, notas, created_at)
anotaciones_humanas(id, resolucion_id FK, anotador,
                    categoria_ia, categoria_humana,
                    riesgo_score_ia, riesgo_score_humano,
                    coincide_categoria, notas, confianza_pct,
                    is_gold_set, timestamp,
                    UNIQUE(resolucion_id, anotador))

-- Triángulo de auditoría
inidep_evaluaciones(id, especie, especie_code, zona, year,
                    cba_recomendada_tn, cba_alternativa_tn,
                    estado_stock, numero_ito, fuente_url, notas, created_at)
cfp_cuotas(id, especie_code, zona, year, cmp_tn,
           resolucion_cfp, fecha_resolucion, fuente_url, notas)
comparacion_cfp_inidep(id, especie_code, zona, year,
                       cba_tn, cmp_tn, diferencia_tn, diferencia_pct,
                       nivel_alerta, created_at)

-- Motor de alertas
alertas_reglas(id, nombre, tipo, especie_code, zona,
               year_desde, year_hasta, umbral_pct, umbral_estado,
               severidad, activa)
alertas_historial(id, regla_id, tipo, especie, especie_code, zona, year,
                  valor_detectado, umbral, mensaje, severidad,
                  acta_referencia, resuelta, created_at)

-- Fuentes externas
fao_capturas, fao_stock_status, sipa_capturas, conicet_publicaciones

-- Geovisor SERE
vedas_geoespaciales(id, capa, especie, especie_code, area,
                    fecha_inicio, fecha_fin,
                    resolucion_numero, resolucion_fuente, resolucion_url,
                    notas, geometry_type,
                    fuente DEFAULT 'INIDEP SERE geovisor', created_at)

-- Conflictos de interés
cargos_directivos(persona_nombre, persona_norm, empresa_nombre,
                  cargo, desde_year, hasta_year, fuente, verificado)
```

**ChromaDB `data/knowledge_base/` — vector store:**
- Colección: `cfp_resoluciones`
- Modelo: `paraphrase-multilingual-MiniLM-L12-v2` (384 dimensiones, cosine)
- Documento ID: `{acta_key}_{numero_resolucion}`
- Metadatos indexados: `year`, `numero`, `tipo`, `fecha_acta`, `acta_filename`, `especies[]`, `empresas[]`
- Permite búsqueda semántica con filtros temporales, de tipo, y de especie vía `where` clause

---

### 2.4 Capa de Análisis

| Módulo | Entrada | Método | Salida |
|--------|---------|--------|--------|
| `audit_engine.py` | Texto resolución | Claude API (Sonnet/Opus) + prompt caching + groundedness (Jaccard) | `AuditResult` con `riesgo_score`, `hallazgos[]`, `groundedness_avg` |
| `inidep_comparator.py` | `inidep_evaluaciones` ⋈ `cfp_cuotas` ⋈ `sipa_capturas` | LEFT JOINs + clasificación por umbrales con cita bibliográfica | `list[AlertaComparacion]` con `nivel` ∈ {verde, amarillo, rojo, critico} |
| `pattern_detector.py` | `resoluciones` + `menciones` | HHI con chi-square contrafactual, análisis de votación, detección de reversiones | dict con `hhi_obs`, `p_valor_uniformidad`, `reversals[]` |
| `alert_engine.py` | Todas las tablas | 4 reglas configurables: exceso CBA, stock crítico, quórum mínimo, reversión de veda | `list[AlertaFired]` con severidad ∈ {info, warning, critical} |
| `conflict_detector.py` | `cargos_directivos` ⋈ `menciones` ⋈ `resoluciones` | Join persona-empresa-resolución, 3 tipos de severidad | `DataFrame` + `nx.Graph` bipartito |
| `graph_builder.py` | `menciones` ⋈ `resoluciones` | Red bipartita especie↔empresa, pesos = co-menciones, HHI por especie | `nx.Graph` + `GrafoStats` |
| `geovisor_cross_validator.py` | `vedas_geoespaciales` ⋈ `resoluciones` | Búsqueda de citas en corpus (RE_CITA_RESOLUCION_CFP), filtro `fuente=CFP` | `list[CoberturaResolucion]` con `pct_cobertura` |
| `sensitivity_analyzer.py` | `comparacion_cfp_inidep` | Grid search (amarillo_range, rojo_range), evaluación de estabilidad ±5% | `DataFrame` + heatmap + tabla LaTeX |
| `evaluator.py` | `anotaciones_humanas` (gold set) | Cohen's kappa, P/R/F1 por categoría | `{cohen_kappa, macro_f1, por_categoria{}}` |
| `report_generator.py` | Todas las tablas | reportlab: 6 secciones (portada, resumen, alertas, comparaciones, actores, metodología) | PDF binario |

---

### 2.5 Capa de Presentación — Dashboard Streamlit

16 páginas con responsabilidades diferenciadas:

| Página | Módulo backend | Qué muestra |
|--------|----------------|------------|
| 01 Adquisición | `CatalogManager.stats()` | KPIs pipeline: total/descargadas/procesadas/embebidas/analizadas |
| 02 Knowledge Base | `CFPVectorStore.count()` | Colección ChromaDB, búsqueda semántica |
| 03 Auditoría IA | `audit_engine` | Resultados `AuditResult` por resolución |
| 04 Reportes | `CatalogManager` | Exports CSV/JSON |
| 05 INIDEP Comparador | `INIDEPComparator` | Triángulo CBA·CMP·Captura, 5 tabs: alertas, triángulo, visualización, datos, metodología |
| 06 Timeline | SQLite `cfp_cuotas` | Evolución histórica de cuotas 1998–2025 |
| 07 Grafo | `CFPGraphBuilder` | Red especie↔empresa interactiva (pyvis) |
| 08 Alertas | `AlertEngine` | Panel configurable de alertas activas |
| 09 Reporte | `CFPReportGenerator` | Generación y descarga PDF ejecutivo |
| 10 FAO FIRMS | `fao_firms_scraper` | Capturas mundiales vs. Argentina |
| 11 CONICET | `conicet_scraper` | Publicaciones científicas por especie |
| 12 Capturas | `sipa_scraper` | Desembarques reales SAGPyA |
| 13 Investigación | notebooks | Hub Serie FisheriesAudit ALG |
| 14 Evaluación | `GroundTruthEvaluator` | Cohen's kappa, P/R/F1, gold set |
| 15 Conflictos | `ConflictDetector` | Red de conflictos de interés CFP-industria |
| 16 Geovisor | `GeovisorCrossValidator` | Vedas SERE INIDEP + cobertura del corpus |

---

### 2.6 Capa de API — FastAPI

**5 routers, base URL `http://0.0.0.0:8000`:**

| Router | Prefijo | Endpoints principales |
|--------|---------|----------------------|
| `actas.py` | `/actas` | `GET /actas` (paginado, filtro year/descargadas), `GET /actas/{id}`, `GET /actas/{id}/resoluciones` |
| `alertas.py` | `/alertas` | `GET /alertas` (filtros severidad/especie/year), `POST /alertas/evaluar`, `PATCH /alertas/{id}/resolver`, `GET /alertas/resumen` |
| `analysis.py` | `/analysis` | `POST /analysis/ner` (extracción entidades), `GET /analysis/stats` (KPIs globales) |
| `inidep.py` | `/inidep` | Comparaciones CBA/CMP, evaluaciones, triángulo completo |
| `entidades.py` | `/entidades` | Listado normalizado de species, empresas, personas |

**Health check:** `GET /health` → `{status: "ok", version: "0.3.0"}`  
**Documentación automática:** `/docs` (Swagger UI), `/redoc` (ReDoc)

---

## 3. Flujo de Datos End-to-End

```
cfp.gob.ar/actas-cfp
        │
        ▼
[1] batch_scraper.py
    → ActaMetadata{url, filename, year}
    → descarga PDF + SHA256 hash
        │
        ▼
[2] catalog_manager.py → actas{download_status=ok, file_hash}
        │
        ▼
[3] pdf_extractor.py
    → cascada: pdfplumber → PyMuPDF → Tesseract OCR
    → .txt (method reportado)
        │
        ▼
[4] document_parser.py
    → Acta{decisiones, votos, cuotas, fundamento_inidep}
    → .json estructurado
        │
        ├──→ ner_pesquero.py → ResultadoNER{especies, empresas, zonas}
        │       → entidades + menciones en SQLite
        │
        ├──→ vector_store.py → ChromaDB (384-dim embeddings, cosine)
        │
        └──→ audit_engine.py → AuditResult{riesgo_score, hallazgos, groundedness}
                 → analisis_sesiones en SQLite (prompt_hash + input_hash)

DSpace 7 INIDEP Mar Abierto
        │
        ▼
[5] inidep_scraper.py
    → ITORecord{cba_recomendada_tn, estado_stock, numero_ito}
    → inidep_evaluaciones en SQLite

SAGPyA / FAO / CONICET / GeoServer SERE
        │
        ▼
[6] scrapers externos → tablas de apoyo en SQLite

                    ┌──────────────────────┐
                    │  inidep_evaluaciones  │
                    │  cfp_cuotas           │ ──→ inidep_comparator.py
                    │  sipa_capturas        │         → AlertaComparacion
                    └──────────────────────┘         → nivel: verde/rojo/critico
                    
                    ┌──────────────────────┐
                    │  resoluciones         │
                    │  menciones            │ ──→ pattern_detector.py (HHI + chi²)
                    │  entidades            │ ──→ alert_engine.py (4 reglas)
                    └──────────────────────┘ ──→ graph_builder.py (red bipartita)
                    
                    ┌──────────────────────┐
                    │  vedas_geoespaciales  │
                    │  resoluciones         │ ──→ geovisor_cross_validator.py
                    └──────────────────────┘         → cobertura_summary %
```

---

## 4. Configuración Central (`config/settings.yaml`)

```yaml
cfp:
  base_url: "https://cfp.gob.ar"
  years_start: 1998

scraping:
  delay_seconds: 1.5
  max_retries: 3
  timeout: 30

processing:
  ocr_language: "spa"
  min_text_length: 100       # umbral de calidad extracción PDF

embeddings:
  model: "paraphrase-multilingual-MiniLM-L12-v2"
  batch_size: 32

comparador:
  umbrales_cmp_cba:
    amarillo_min: 1.00       # ≥ Ley 24.922 Art. 9
    rojo_min: 1.15           # Bertolotti et al. (2001)
    critico_min: 1.30        # FAO Code 1995 Art. 7.2.1

audit:
  risk_thresholds:
    low: 30                  # riesgo_score < 30 → bajo
    medium: 60
    high: 80
    critical: 90

evaluation:
  low_evidence_threshold: 0.15  # Jaccard < 0.15 → [BAJA_EVIDENCIA]

llm:
  default_model: "claude-sonnet-4-6"
  audit_model: "claude-opus-4-8"
  temperature: 0.1
  use_prompt_caching: true
```

---

## 5. Stack Tecnológico

| Capa | Tecnología | Versión mínima |
|------|-----------|----------------|
| Scraping | requests, beautifulsoup4, tenacity | ≥ 2.31, ≥ 4.12, ≥ 8.0 |
| PDF | pdfplumber, PyMuPDF (fitz), pytesseract | ≥ 0.10, ≥ 1.23, ≥ 0.3 |
| NLP | spacy (es_core_news_sm), sentence-transformers | ≥ 3.7, ≥ 2.7 |
| Vector DB | chromadb | ≥ 0.4 |
| LLM | anthropic SDK | ≥ 0.28 |
| Storage | sqlite3 (stdlib), pandas | ≥ 2.0 |
| UI | streamlit, plotly | ≥ 1.29, ≥ 5.16 |
| API | fastapi, uvicorn, pydantic | ≥ 0.104, ≥ 0.24, ≥ 2.0 |
| Análisis | networkx, scipy, scikit-learn, matplotlib | ≥ 3.2, ≥ 1.11, ≥ 1.3, ≥ 3.7 |
| Reportes | reportlab | ≥ 4.0 |
| Infra | Docker multi-stage, GitHub Actions CI | — |
| Tests | pytest, pytest-cov, ruff | ≥ 7.4 |

---

## 6. Despliegue

```bash
# Desarrollo local
pip install -r requirements.txt
python -m spacy download es_core_news_sm
cp .env.example .env

# Docker
docker-compose up --build
# api:       http://localhost:8000 (+ /docs)
# dashboard: http://localhost:8501

# Pipeline completo
python scripts/run_full_pipeline.py --years 1998-2025

# Tests
pytest tests/ -q   # 915 tests
```

**Variables de entorno requeridas:**
```env
ANTHROPIC_API_KEY=sk-ant-...         # solo para etapas audit y report
CLAUDE_MODEL=claude-sonnet-4-6
CLAUDE_AUDIT_MODEL=claude-opus-4-8
```

---

## 7. Repositorios de Datos (gitignored)

```
data/
  raw/               # PDFs originales descargados (por año)
  processed/
    catalog.db       # SQLite — fuente de verdad relacional
    text/            # .txt extraídos por pdf_extractor
    json/            # .json parseados por document_parser
  knowledge_base/    # ChromaDB persistente
  reports/           # PDFs generados por report_generator
```

Los directorios `data/` están en `.gitignore`. Solo se commitean `.gitkeep` y el código de generación. Esto garantiza que los datos se generan reproduciblemente desde las fuentes públicas, no se distribuyen como binarios.
