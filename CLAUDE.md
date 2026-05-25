# CFP Audit Intelligence — Guía para Claude Code

## Descripción del Proyecto

Plataforma de **auditoría inteligente** de las actas públicas del Consejo Federal Pesquero (CFP) de Argentina. Extrae, procesa y analiza con IA 25+ años de decisiones sobre recursos pesqueros para detectar patrones que atenten contra la sostenibilidad y los intereses nacionales.

**Repositorio**: `arielgiamportone/cfp-audit-intelligence`  
**Branch de desarrollo**: `claude/cfp-fisheries-audit-project-lLMib`  
**Versión actual**: v0.2

---

## Leer antes de codificar

1. **`TODO.md`** — Backlog priorizado. La sección "Prioridad Alta" define qué construir ahora.
2. **`AGENTS.md`** — Permisos, restricciones y convenciones por tipo de agente.
3. **`docs/adr/`** — Decisiones de arquitectura ya tomadas (no re-decidir sin ADR nuevo).

---

## Estructura del Proyecto

```
src/
  acquisition/        → Scraping y descarga masiva (batch_scraper, catalog_manager)
  processing/         → Extracción PDF, OCR, parsing estructural
  knowledge_base/     → ChromaDB, embeddings multilingües
  analysis/           → Motor de auditoría (Claude API + prompt caching), patrones
  dashboard/          → Streamlit multipágina (4 páginas activas)
scripts/
  run_full_pipeline.py  → Pipeline CLI end-to-end (--step download|process|kb|audit)
data/
  raw/               → PDFs descargados (gitignored, solo .gitkeep)
  processed/         → catalog.db + text/ + json/ (gitignored)
  knowledge_base/    → ChromaDB persistente (gitignored)
  reports/           → Reportes generados (gitignored)
config/settings.yaml → Configuración del sistema (especies, modelos, umbrales)
docs/adr/            → Architecture Decision Records
TODO.md              → Backlog y roadmap priorizado
AGENTS.md            → Guía de agentes IA y restricciones
```

---

## Comandos Clave

```bash
# Instalar
pip install -r requirements.txt
python -m spacy download es_core_news_sm

# Pipeline completo
python scripts/run_full_pipeline.py --years 1998-2025

# Pasos individuales
python scripts/run_full_pipeline.py --step download --years 2020-2025
python scripts/run_full_pipeline.py --step process
python scripts/run_full_pipeline.py --step knowledge_base
python scripts/run_full_pipeline.py --step audit --limit 50

# Dashboard
streamlit run src/dashboard/app.py

# Via Make
make pipeline    # end-to-end
make dashboard   # lanzar UI
make stats       # ver estadísticas del catálogo
make test        # correr tests
```

---

## Variables de Entorno

Copiar `.env.example` a `.env` y completar:

- `ANTHROPIC_API_KEY`: Requerida para etapas 4+ (análisis IA)
- `CLAUDE_MODEL`: Default `claude-sonnet-4-6`
- `CLAUDE_AUDIT_MODEL`: Default `claude-opus-4-7` para análisis profundo

---

## Tecnologías Principales

| Capa | Tecnología |
|------|-----------|
| Scraping | requests, beautifulsoup4, tenacity |
| PDF | pdfplumber, PyMuPDF (fitz), pytesseract + Tesseract |
| NLP | spacy (es_core_news_sm), sentence-transformers |
| Vector DB | ChromaDB con embeddings `paraphrase-multilingual-MiniLM-L12-v2` |
| LLM | anthropic SDK, claude-sonnet-4-6 / claude-opus-4-7, prompt caching |
| Storage | SQLite (catálogo) + ChromaDB (vectores) |
| UI | Streamlit multipágina + Plotly |
| Pipeline | Click CLI + Makefile |

---

## Convenciones de Código

- **Logging**: `loguru` siempre, nunca `print()`
- **Retry de red**: `tenacity` con exponential backoff
- **Validación**: Pydantic para datos en boundaries (entrada de usuario, APIs)
- **Type hints**: en todas las funciones públicas
- **Docstrings**: en español, una línea de descripción + Args/Returns si es complejo
- **Código**: variables y funciones en inglés; comentarios y docs en español
- **Tests**: en `tests/` con fixtures en `tests/conftest.py`

---

## Modelo de Datos (SQLite `catalog.db`)

```sql
actas(id, year, nombre, url, filename, is_anexo, local_path, file_hash,
      download_status, text_extracted, text_path, embedded, analyzed)

resoluciones(id, acta_id, numero, tipo, fecha, texto_completo, texto_resumen,
             votos_favor, votos_contra, abstenciones, quorum,
             riesgo_score, categoria, analisis_ia)

entidades(id, tipo, nombre, nombre_norm)
  -- tipo: especie | empresa | persona | lugar | normativa | buque

menciones(id, resolucion_id, entidad_id, contexto, sentimiento)

analisis_sesiones(id, acta_id, tipo_analisis, resultado_json, modelo_ia, tokens_usados)
```

---

## Próximas Tareas (ver TODO.md para detalle completo)

### Sprint 1 (Prioridad Alta)
1. **Tests del pipeline core** — pytest para todos los módulos principales
2. **Comparador INIDEP** — cuotas CFP vs CMS recomendada por especie/año
3. **NER pesquero** — fine-tuning spaCy para entidades del sector

### Sprint 2 (Prioridad Media)
4. Timeline interactivo por especie
5. Sistema de alertas configurables
6. Grafo de relaciones empresas-decisiones-personas

### Sprint 3
7. API REST (FastAPI)
8. Reporte PDF ejecutivo
9. Docker + CI completo
