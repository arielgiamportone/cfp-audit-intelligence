# CFP Audit Intelligence Platform

**Plataforma de Auditoría Inteligente del Consejo Federal Pesquero de Argentina**

> I+D+I Pesquera de vanguardia: extracción, procesamiento y análisis con IA de 25+ años de actas públicas del CFP para auditar la toma de decisiones sobre los recursos pesqueros y acuícolas argentinos.

[![Tests](https://github.com/arielgiamportone/cfp-audit-intelligence/actions/workflows/tests.yml/badge.svg)](https://github.com/arielgiamportone/cfp-audit-intelligence/actions/workflows/tests.yml)

---

## Objetivo

Construir una **knowledge base** completa del Consejo Federal Pesquero (1998–presente) y aplicar analítica avanzada + IA para:

1. **Auditar** la toma de decisiones históricas sobre recursos pesqueros y acuícolas
2. **Detectar patrones** que atenten contra la sostenibilidad de la pesca argentina
3. **Contrastar** cuotas aprobadas por el CFP con recomendaciones científicas del INIDEP (Ley 24.922, Art. 9)
4. **Generar evidencia** técnica reproducible y trazable para el debate público y la política pesquera

---

## Arquitectura

```
┌─────────────────────────────────────────────────────────────────┐
│                    CFP AUDIT INTELLIGENCE                        │
├──────────────┬──────────────┬──────────────┬────────────────────┤
│  ADQUISICIÓN │ PROCESAMIENTO│  KNOWLEDGE   │     AUDITORÍA      │
│              │              │    BASE      │       + IA         │
│  • Scraper   │  • PDF→Text  │  • ChromaDB  │  • Claude API      │
│  • Bulk DL   │  • OCR       │  • SQLite    │  • Patrones        │
│  • Catálogo  │  • NER       │  • Grafo     │  • Sostenibilidad  │
│  • INIDEP    │  • Parsing   │  • Embeddings│  • Anomalías       │
└──────────────┴──────────────┴──────────────┴────────────────────┘
                                    │
                    ┌───────────────▼────────────────┐
                    │      DASHBOARD STREAMLIT        │
                    │  Adquisición │ KB │ Audit │ INIDEP│
                    └─────────────────────────────────┘
```

---

## Módulos

| Módulo | Descripción |
|--------|-------------|
| `src/acquisition/batch_scraper.py` | Scraping masivo y descarga de PDFs del CFP |
| `src/acquisition/catalog_manager.py` | Catálogo SQLite con trazabilidad completa del pipeline |
| `src/acquisition/inidep_scraper.py` | Scraper del repositorio Mar Abierto del INIDEP |
| `src/processing/pdf_extractor.py` | Extracción en cascada: pdfplumber → PyMuPDF → OCR |
| `src/processing/document_parser.py` | Parser estructural de actas (decisiones, agenda, entidades) |
| `src/knowledge_base/vector_store.py` | ChromaDB con embeddings multilingües |
| `src/analysis/audit_engine.py` | Motor de auditoría con Claude API + prompt caching |
| `src/analysis/pattern_detector.py` | Detección estadística de patrones (HHI, votaciones, reversiones) |
| `src/analysis/inidep_comparator.py` | Comparador CFP vs. INIDEP: cuotas vs. CBA recomendada |
| `src/dashboard/` | Interfaz Streamlit multipágina (5 páginas) |
| `scripts/run_full_pipeline.py` | Pipeline CLI end-to-end |

---

## Inicio Rápido

### Instalación

```bash
git clone https://github.com/arielgiamportone/cfp-audit-intelligence.git
cd cfp-audit-intelligence
pip install -r requirements.txt
```

### Configuración

```bash
cp .env.example .env
# Completar ANTHROPIC_API_KEY en .env
```

### Pipeline

```bash
# End-to-end: descarga → procesa → KB → auditoría
python scripts/run_full_pipeline.py --years 1998-2025

# Pasos individuales
python scripts/run_full_pipeline.py --step download --years 2020-2025
python scripts/run_full_pipeline.py --step process
python scripts/run_full_pipeline.py --step knowledge_base
python scripts/run_full_pipeline.py --step audit --limit 50
```

### Dashboard

```bash
streamlit run src/dashboard/app.py
```

### Tests

```bash
make test
# o directamente:
python -m pytest tests/ -v --cov=src
```

---

## Comparador CFP vs. INIDEP

Módulo central de auditoría científica. Cruza las cuotas aprobadas por el CFP contra la Captura Biológicamente Aceptable (CBA) recomendada por el INIDEP, en cumplimiento de la **Ley 24.922, Art. 9**.

Sistema de alertas:

| Nivel | Criterio | Riesgo |
|-------|----------|--------|
| Verde | CMP ≤ 100% CBA | Dentro del límite científico |
| Amarillo | CMP 101–115% CBA | Monitorear |
| Rojo | CMP 116–130% CBA | Sobreasignación significativa |
| Crítico | CMP > 130% CBA | Riesgo crítico de sostenibilidad |

Datos semilla verificados disponibles para: merluza (ITO 36-37/2024), centolla (ITO 31/2025), abadejo, polaca, langostino.

---

## Modelo de Datos (SQLite `catalog.db`)

```sql
actas(id, year, nombre, url, filename, local_path, file_hash,
      download_status, text_extracted, text_path, embedded, analyzed)

resoluciones(id, acta_id, numero, tipo, fecha, texto_completo,
             votos_favor, votos_contra, quorum, riesgo_score, analisis_ia)

entidades(id, tipo, nombre, nombre_norm)
  -- tipo: especie | empresa | persona | lugar | normativa | buque

menciones(id, resolucion_id, entidad_id, contexto, sentimiento)

analisis_sesiones(id, acta_id, tipo_analisis, resultado_json, modelo_ia, tokens_usados)

inidep_evaluaciones(id, especie, especie_code, zona, year,
                    cba_recomendada_tn, estado_stock, numero_ito)

cfp_cuotas(id, especie, especie_code, zona, year, cmp_aprobada_tn, acta_referencia)

comparacion_cfp_inidep(id, especie, zona, year, cba_inidep_tn, cmp_cfp_tn,
                       diferencia_tn, ratio_sobreasignacion, nivel_alerta)
```

---

## Roadmap

### Sprint 1 — Core pipeline (completado)
- [x] Scraper batch con retry y catálogo SQLite
- [x] Extracción PDF en cascada (pdfplumber → PyMuPDF → OCR)
- [x] Parser estructural de actas (formato real CFP: minutas narrativas)
- [x] Knowledge base vectorial (ChromaDB + sentence-transformers)
- [x] Motor de auditoría IA (Claude API + prompt caching)
- [x] Detector de patrones estadísticos (HHI, votaciones)
- [x] Dashboard Streamlit 5 páginas
- [x] **Comparador CFP vs. INIDEP** — alertas por sobreasignación de cuotas
- [x] **Tests del pipeline core** — 114 tests, CI GitHub Actions

### Sprint 2 — Análisis avanzado (en curso)
- [ ] NER pesquero especializado (spaCy fine-tuning)
- [ ] Timeline interactivo por especie (1998–2025)
- [ ] Grafo de relaciones empresas–decisiones–miembros
- [ ] Sistema de alertas configurables
- [ ] Scraping completo de 492 ITOs INIDEP (Mar Abierto)

### Sprint 3 — Producción
- [ ] API REST (FastAPI)
- [ ] Reporte PDF ejecutivo automático
- [ ] Integración FAO FIRMS + CONICET
- [ ] Docker + CI/CD completo

---

## Marco Legal y Ético

Trabaja exclusivamente con **documentos públicos** del CFP, organismo colegiado creado por la **Ley Federal de Pesca N° 24.922**.

- Fuente primaria: [cfp.gob.ar/actas-cfp](https://cfp.gob.ar/actas-cfp)
- Fuente científica: [marabierto.inidep.edu.ar](https://marabierto.inidep.edu.ar)
- El análisis es **descriptivo** — no constituye acusación legal
- Metodología reproducible y código abierto

---

**Por la soberanía y sostenibilidad de los recursos pesqueros argentinos**
