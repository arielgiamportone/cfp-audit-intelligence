# CFP Audit Intelligence Platform

**Plataforma de Auditoría Inteligente del Consejo Federal Pesquero de Argentina**

> Extracción, procesamiento y análisis con IA de las actas públicas del CFP para auditar la toma de decisiones sobre los recursos pesqueros y acuícolas argentinos (1998–presente).

---

## Objetivo

Construir una **knowledge base** completa del Consejo Federal Pesquero y aplicar analítica avanzada + IA para:

1. **Auditar** la toma de decisiones históricas sobre recursos pesqueros
2. **Detectar patrones** que atenten contra la sostenibilidad de la pesca argentina
3. **Identificar** decisiones contrarias a normas o recomendaciones científicas (INIDEP)
4. **Generar evidencia** técnica reproducible y trazable para el debate público

---

## Estado actual (v0.2)

| Etapa | Estado |
|-------|--------|
| Descarga masiva de PDFs (cfp.gob.ar) | ✅ Funcional |
| Extracción de texto (PDF + OCR fallback) | ✅ Funcional |
| Parser de resoluciones y decisiones | ✅ Funcional |
| Knowledge base vectorial (ChromaDB) | ✅ Funcional |
| Dashboard Streamlit multipágina | ✅ Funcional |
| Auditoría IA (Claude API) | Requiere `ANTHROPIC_API_KEY` |

Probado con el año 2024: 32 actas → 215 resoluciones/decisiones indexadas.

---

## Arquitectura del pipeline

```
Etapa 1: Adquisición  →  Etapa 2: Procesamiento  →  Etapa 3: KB  →  Etapa 4: Auditoría
src/acquisition/          src/processing/             src/knowledge_base/  src/analysis/
  batch_scraper.py          pdf_extractor.py            vector_store.py      audit_engine.py
  catalog_manager.py        document_parser.py                               pattern_detector.py
       ↓                         ↓                          ↓
  data/raw/*.pdf         data/processed/text/        data/knowledge_base/
  catalog.db             data/processed/json/        (ChromaDB vectores)
```

El parser extrae dos tipos de contenido:
- **Resoluciones formales**: bloques con "Número de Registro CFP X/YYYY" y el proyecto previo
- **Decisiones del cuerpo**: frases "se decide [por unanimidad]..." con contexto circundante

---

## Instalación

```bash
git clone https://github.com/arielgiamportone/cfp-audit-intelligence.git
cd cfp-audit-intelligence
pip install -r requirements.txt
cp .env.example .env
# Editar .env — solo ANTHROPIC_API_KEY es necesaria para la etapa de auditoría
```

---

## Uso

```bash
# Pipeline completo (1998–2025)
python scripts/run_full_pipeline.py --years 1998-2025

# Por etapas
python scripts/run_full_pipeline.py --step download --years 2024
python scripts/run_full_pipeline.py --step process
python scripts/run_full_pipeline.py --step knowledge_base
python scripts/run_full_pipeline.py --step audit --limit 50   # requiere API key

# Dashboard
streamlit run src/dashboard/app.py

# Make targets
make download | make process | make build-kb | make audit | make dashboard | make pipeline
```

---

## Estructura de datos

### Catálogo SQLite (`data/processed/catalog.db`)
```
actas            — metadatos, estado en pipeline, hash del archivo
resoluciones     — resoluciones parseadas con score de riesgo
entidades        — especies, empresas, personas, lugares
menciones        — relaciones resolución↔entidad con contexto
analisis_sesiones — resultados de auditoría IA por acta
```

### Knowledge Base Vectorial (`data/knowledge_base/`)
Embeddings con `paraphrase-multilingual-MiniLM-L12-v2`. Búsqueda semántica con filtros por año, tipo de resolución y especie.

---

## Marco legal y ético

Trabaja exclusivamente con **documentos públicos** del Consejo Federal Pesquero, organismo creado por la **Ley Federal de Pesca N° 24.922**. Fuente: [cfp.gob.ar/actas-cfp](https://cfp.gob.ar/actas-cfp). El análisis es descriptivo y no constituye acusación legal.

---

## Roadmap

- [ ] Ampliar KB a todos los años disponibles (1998–2024)
- [ ] NER especializado para entidades pesqueras argentinas
- [ ] Comparador INIDEP: recomendaciones científicas vs. cuotas otorgadas
- [ ] Timeline interactivo por especie y año (Plotly)
- [ ] Reporte PDF ejecutivo (reportlab)
- [ ] API REST (FastAPI)

---

**Por la soberanía y sostenibilidad de los recursos pesqueros argentinos**
