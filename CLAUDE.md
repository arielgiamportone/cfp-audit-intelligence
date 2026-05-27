# CFP Audit Intelligence – Guía para Claude Code

## Descripción del Proyecto

Plataforma de **auditoría inteligente** de las actas públicas del Consejo Federal Pesquero (CFP) de Argentina. Extrae, procesa y analiza con IA 25+ años de decisiones sobre recursos pesqueros para detectar patrones que atenten contra la sostenibilidad y los intereses nacionales.

## Estructura del Proyecto

```
src/
  acquisition/        → Scraping y descarga masiva
  processing/         → Extracción PDF, OCR, parsing
  knowledge_base/     → ChromaDB, embeddings
  analysis/           → Motor de auditoría (Claude API), detección de patrones
  dashboard/          → Streamlit multipágina
scripts/
  run_full_pipeline.py  → Pipeline end-to-end
data/
  raw/               → PDFs descargados
  processed/         → Textos, JSONs, catálogo SQLite
  knowledge_base/    → Vector store ChromaDB
config/settings.yaml → Configuración del sistema
```

## Comandos Clave

```bash
# Instalar dependencias
pip install -r requirements.txt

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
make pipeline
make dashboard
make stats
```

## Variables de Entorno Requeridas

- `ANTHROPIC_API_KEY`: Para análisis con Claude API (etapa 4 y dashboard auditoría)
- Copiar `.env.example` a `.env` y completar

## Tecnologías Principales

- **Scraping**: requests, beautifulsoup4, tenacity (retry)
- **PDF**: pdfplumber, PyMuPDF (fitz), pytesseract (OCR)
- **NLP**: spacy (es_core_news_sm), sentence-transformers
- **Vector DB**: ChromaDB con embeddings multilingües
- **LLM**: anthropic SDK con prompt caching (claude-sonnet-4-6 / claude-opus-4-7)
- **UI**: Streamlit multipágina + Plotly
- **Storage**: SQLite (catálogo) + ChromaDB (vectores)

## Convenciones de Código

- Módulos con docstrings claros en español
- Logging con `loguru` (no `print`)
- Retry con `tenacity` para operaciones de red
- Pydantic para validación de datos donde aplica
- Type hints en todas las funciones públicas

## Modelo de Datos (SQLite)

```
actas(id, year, nombre, url, filename, download_status, text_extracted, embedded, analyzed)
resoluciones(id, acta_id, numero, tipo, texto, riesgo_score, analisis_ia)
entidades(id, tipo, nombre, nombre_norm)
menciones(id, resolucion_id, entidad_id, contexto)
analisis_sesiones(id, acta_id, tipo_analisis, resultado, modelo_ia)
```

## Notas de implementación

- El parser (`document_parser.py`) extrae dos tipos: resoluciones formales (patrón "Número de Registro CFP X/YYYY") y decisiones del cuerpo (patrón "se decide [por unanimidad]..."). Las decisiones informales usan numeración `D1`, `D2`, etc.
- Los IDs en ChromaDB usan `{acta_stem}_{numero}` para evitar colisiones entre actas del mismo año.
- Streamlit se ejecuta con Python 3.10 (`C:\Users\Ariel\AppData\Local\Programs\Python\Python310\`). Instalar dependencias con ese Python: `"C:/Users/Ariel/AppData/Local/Programs/Python/Python310/python.exe" -m pip install ...`
- `catalog.db` está en `.gitignore` — no se versiona.
- El notebook `notebooks/eda_kb.ipynb` requiere `pio.renderers.default = 'notebook'` para renderizar gráficos Plotly inline en VS Code sin abrir el browser. Si los gráficos no aparecen, reiniciar el kernel (la caché de módulos puede tener `nbformat=None` de un arranque previo).
