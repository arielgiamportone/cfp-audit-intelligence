# 🐟 CFP Audit Intelligence Platform

**Plataforma de Auditoría Inteligente del Consejo Federal Pesquero de Argentina**

> I+D+I Pesquera de vanguardia: extracción, procesamiento y análisis con IA de las actas públicas del CFP para auditar la toma de decisiones sobre los recursos pesqueros y acuícolas argentinos.

---

## 🎯 Objetivo

Construir una **knowledge base** completa del Consejo Federal Pesquero (1998–presente) y aplicar analítica avanzada + IA para:

1. **Auditar** la toma de decisiones históricas sobre recursos pesqueros y acuícolas
2. **Detectar patrones** que atenten contra la sostenibilidad de la pesca argentina
3. **Identificar** decisiones subjetivas, contrarias a normas o intereses nacionales
4. **Generar evidencia** técnica reproducible y trazable para el debate público y la política pesquera

---

## 🏗️ Arquitectura del Sistema

```
┌─────────────────────────────────────────────────────────────────┐
│                    CFP AUDIT INTELLIGENCE                        │
├──────────────┬──────────────┬──────────────┬────────────────────┤
│  ADQUISICIÓN │ PROCESAMIENTO│  KNOWLEDGE   │     AUDITORÍA      │
│              │              │    BASE      │       + IA         │
│  • Scraper   │  • PDF→Text  │  • ChromaDB  │  • Claude API      │
│  • Bulk DL   │  • OCR       │  • SQLite    │  • Patrones        │
│  • Catálogo  │  • NER       │  • Grafo     │  • Sostenibilidad  │
│  • Versiones │  • Parsing   │  • Embeddings│  • Anomalías       │
└──────────────┴──────────────┴──────────────┴────────────────────┘
                                    │
                    ┌───────────────▼────────────────┐
                    │      DASHBOARD STREAMLIT        │
                    │  Adquisición │ KB │ Audit │ Reports│
                    └─────────────────────────────────┘
```

## 📦 Módulos Principales

| Módulo | Descripción |
|--------|-------------|
| `src/acquisition/` | Scraping masivo y descarga de PDFs del CFP |
| `src/processing/` | Extracción de texto, OCR, parsing estructurado y NER |
| `src/knowledge_base/` | Base vectorial, grafo de relaciones y catálogo SQLite |
| `src/analysis/` | Motor de auditoría con IA (Claude API), detección de patrones |
| `src/dashboard/` | Interfaz Streamlit multipágina |
| `scripts/` | Pipelines automatizados end-to-end |
| `notebooks/` | Análisis exploratorio y metodología |

---

## 🔬 Capacidades de Análisis

### Detección de Patrones
- **Cuotas vs. recomendaciones científicas**: ¿Se otorgaron cuotas superiores a lo recomendado?
- **Beneficiarios recurrentes**: Empresas o actores favorecidos sistemáticamente
- **Patrones de votación**: Decisiones unánimes vs. disenso, quórum mínimo
- **Evolución temporal**: Tendencias en las decisiones a lo largo de 25+ años
- **Especie bajo presión**: Merluza, langostino, calamar, abadejo y otras especies clave

### Auditoría de Sostenibilidad
- Comparación con capturas máximas sostenibles (CMS) históricas
- Detección de moratorias evadidas o incumplidas
- Análisis de vedas y áreas protegidas: ¿se respetan?
- Impacto de las decisiones en el stock pesquero

### Análisis con IA (Claude API)
- Resumen automático de cada acta
- Clasificación de resoluciones por categoría y urgencia
- Detección de lenguaje evasivo o ambiguo en resoluciones críticas
- Identificación de contradicciones con normativa vigente (Ley 24.922)
- Análisis de conflictos de interés potenciales

---

## 🚀 Inicio Rápido

### 1. Instalación

```bash
# Clonar y preparar entorno
git clone https://github.com/arielgiamportone/cfp-actas-scraper.git
cd cfp-actas-scraper
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate   # Windows

pip install -r requirements.txt
```

### 2. Configuración

```bash
cp .env.example .env
# Editar .env con tu ANTHROPIC_API_KEY
```

### 3. Pipeline completo (recomendado)

```bash
# Descargar todas las actas, procesar y construir KB
python scripts/run_full_pipeline.py --years 1998-2025

# Solo descargar PDFs
python scripts/run_full_pipeline.py --step download

# Solo procesar PDFs ya descargados
python scripts/run_full_pipeline.py --step process

# Solo construir knowledge base
python scripts/run_full_pipeline.py --step knowledge_base

# Solo correr análisis de auditoría
python scripts/run_full_pipeline.py --step audit
```

### 4. Dashboard interactivo

```bash
streamlit run src/dashboard/app.py
```

### 5. Make targets

```bash
make download      # Descargar todas las actas
make process       # Procesar PDFs
make build-kb      # Construir knowledge base
make audit         # Correr auditoría completa
make dashboard     # Lanzar dashboard
make pipeline      # Pipeline end-to-end
```

---

## 📊 Estructura de Datos

### Catálogo SQLite (`data/processed/catalog.db`)
```sql
actas(id, year, numero, fecha, url, pdf_path, text_path, processed, hash)
resoluciones(id, acta_id, numero, tipo, texto, votos_favor, votos_contra, abstenciones)
entidades(id, tipo, nombre, normalized)  -- empresas, especies, personas, lugares
menciones(resolucion_id, entidad_id, contexto)
```

### Knowledge Base Vectorial (`data/knowledge_base/`)
- Embeddings de resoluciones individuales
- Embeddings de actas completas
- Índice semántico para búsqueda por similitud

---

## 🧭 Roadmap

### Fase 1: Adquisición (Semanas 1-2) ✅
- [x] Scraper base (Streamlit)
- [ ] Scraper batch CLI para todas las actas
- [ ] Descarga masiva con retry y deduplicación
- [ ] Catálogo SQLite de metadatos

### Fase 2: Procesamiento (Semanas 3-4)
- [ ] Extracción de texto PDF (pdfplumber + PyMuPDF)
- [ ] OCR para PDFs escaneados (Tesseract)
- [ ] Parser de estructura: actas → resoluciones
- [ ] NER: especies, empresas, personas, normativa

### Fase 3: Knowledge Base (Semanas 5-6)
- [ ] Embeddings con sentence-transformers
- [ ] Vector store ChromaDB
- [ ] Grafo de relaciones (NetworkX → Neo4j)
- [ ] API de búsqueda semántica

### Fase 4: Análisis IA (Semanas 7-9)
- [ ] Integración Claude API con prompt caching
- [ ] Clasificador de resoluciones
- [ ] Detector de patrones anómalos
- [ ] Análisis de sostenibilidad por especie/año

### Fase 5: Dashboard y Reportes (Semanas 10-12)
- [ ] Dashboard multipágina Streamlit
- [ ] Visualizaciones interactivas (Plotly)
- [ ] Generador de reportes PDF
- [ ] Sistema de alertas configurables

---

## ⚖️ Marco Legal y Ético

Este proyecto trabaja exclusivamente con **documentos públicos** del Consejo Federal Pesquero, organismo colegiado creado por la **Ley Federal de Pesca N° 24.922**. Su objetivo es fortalecer la transparencia y el control ciudadano sobre el manejo de un recurso natural estratégico de Argentina.

- Fuente: [cfp.gob.ar](https://cfp.gob.ar/actas-cfp)
- Todos los documentos son de acceso público
- El análisis es descriptivo y no constituye acusación legal
- Metodología reproducible y código abierto

---

## 🤝 Contribuciones

Este es un proyecto de **I+D+I pesquera abierta**. Contribuciones bienvenidas:
- Mejoras al pipeline de procesamiento
- Algoritmos de detección de patrones
- Visualizaciones de datos
- Validación de resultados por expertos pesqueros

---

**🇦🇷 Por la soberanía y sostenibilidad de los recursos pesqueros argentinos**
