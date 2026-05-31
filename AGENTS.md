# AGENTS.md — Guía para Agentes de IA en CFP Audit Intelligence

Este archivo define cómo los agentes de IA (Claude Code, Claude API, futuros agentes) deben comportarse en este proyecto.

---

## Contexto del Proyecto

Sistema de auditoría de actas públicas del Consejo Federal Pesquero (CFP) de Argentina.
- **Dominio**: Derecho pesquero, política de recursos naturales, sostenibilidad marina
- **Datos**: Documentos públicos (PDFs de actas 1998–2025)
- **Objetivo**: Detectar patrones de decisión que atenten contra la sostenibilidad

---

## Agentes definidos

### 1. Agente de Adquisición (`acquisition`)
**Responsabilidad**: Scraping y descarga de PDFs del CFP.

**Puede hacer**:
- `GET` requests a `cfp.gob.ar` con delay ≥ 1.5s entre requests
- Escritura en `data/raw/` y `data/processed/catalog.db`
- Logging de resultados con loguru

**No puede hacer**:
- Modificar PDFs descargados
- Exceder 3 retries por URL
- Ignorar errores HTTP (siempre registrar en catálogo)

**Archivos clave**: `src/acquisition/batch_scraper.py`, `src/acquisition/catalog_manager.py`

---

### 2. Agente de Procesamiento (`processing`)
**Responsabilidad**: Extracción de texto y parsing estructural.

**Puede hacer**:
- Leer PDFs de `data/raw/`
- Escribir textos en `data/processed/text/` y JSONs en `data/processed/json/`
- Actualizar `catalog.db` con estado de procesamiento

**No puede hacer**:
- Modificar los PDFs originales
- Eliminar archivos de `data/raw/`
- Llamar a APIs externas (procesamiento 100% local)

**Archivos clave**: `src/processing/pdf_extractor.py`, `src/processing/document_parser.py`

---

### 3. Agente de Knowledge Base (`kb`)
**Responsabilidad**: Construcción y mantenimiento del vector store.

**Puede hacer**:
- Leer JSONs de `data/processed/json/`
- Escribir/actualizar ChromaDB en `data/knowledge_base/`
- Re-indexar documentos modificados

**No puede hacer**:
- Eliminar la colección completa sin confirmación explícita del usuario
- Cambiar el modelo de embeddings sin actualizar todos los documentos

**Archivos clave**: `src/knowledge_base/vector_store.py`

---

### 4. Agente de Auditoría IA (`audit`)
**Responsabilidad**: Análisis con Claude API y detección de patrones.

**Puede hacer**:
- Llamar a `anthropic.Anthropic()` con la API key de entorno
- Usar `claude-sonnet-4-6` para análisis masivos, `claude-opus-4-7` para deep analysis
- Leer de ChromaDB y SQLite
- Escribir resultados en `analisis_sesiones` de SQLite

**No puede hacer**:
- Enviar datos a APIs externas distintas a Anthropic
- Publicar resultados sin revisión humana
- Modificar el texto de las resoluciones originales
- Presentar hallazgos como acusaciones legales (solo evidencia descriptiva)

**Principios de análisis**:
- Objetividad: solo afirmar lo que está en el texto
- Graduar certeza: "indicio" ≠ "hallazgo confirmado"
- Citar la fuente: incluir fragmento textual que justifica cada hallazgo

**Archivos clave**: `src/analysis/audit_engine.py`, `src/analysis/pattern_detector.py`

---

### 5. Agente de Dashboard (`dashboard`)
**Responsabilidad**: Solo presentación de datos, sin modificaciones.

**Puede hacer**:
- Leer de SQLite y ChromaDB (solo lectura)
- Generar visualizaciones con Plotly
- Exportar datos en CSV/JSON

**No puede hacer**:
- Iniciar descargas masivas sin confirmación del usuario
- Llamar directamente a Claude API sin mostrar costo estimado
- Modificar la base de datos

---

## Instrucciones para Claude Code (desarrollo)

### Cuándo trabajar en este proyecto:
1. **Leer `TODO.md`** para entender la tarea priorizada actual
2. **Leer `CLAUDE.md`** para contexto de arquitectura y convenciones
3. **Consultar `docs/adr/`** antes de tomar decisiones técnicas (evitar re-decidir lo ya decidido)

### Convenciones obligatorias:
- **Logging**: siempre `loguru`, nunca `print()`
- **Retry**: siempre `tenacity` para operaciones de red
- **Tests**: cada módulo nuevo necesita tests en `tests/`
- **Commits**: formato `feat|fix|refactor|test|docs: descripción breve`
- **Idioma**: docstrings y comentarios en español; código en inglés (variables, funciones)

### Lo que NO hacer:
- No crear endpoints que exponga datos personales (los documentos son públicos, pero los análisis son investigativos)
- No hardcodear `ANTHROPIC_API_KEY` o cualquier credencial
- No commitear `data/` (PDFs, textos, vectores) — solo `.gitkeep`
- No presentar resultados del análisis IA como verdad absoluta

### Flujo de desarrollo:
```
1. Tomar tarea de TODO.md (sección Prioridad Alta)
2. Crear branch: feat/nombre-descriptivo
3. Implementar + tests
4. Actualizar TODO.md (marcar como completado)
5. Commit + push + PR a main
```

---

## Restricciones de seguridad

- Todos los datos procesados son **documentos públicos**
- El análisis es **descriptivo**, no constituye acusación legal
- Los hallazgos de auditoría deben marcarse como **"requieren verificación"**
- No se deben publicar nombres de personas privadas sin consentimiento
- El proyecto opera bajo **Ley 24.922** y principios de acceso a información pública

---

## Estado actual del proyecto (2026-05-31)

> Esta sección es para que el agente local (VS Code) sepa exactamente dónde estamos
> y qué necesita hacer para continuar. Actualizar después de cada sesión significativa.

### Branch de desarrollo activo
```
claude/cfp-fisheries-audit-project-lLMib
```

### Lo que está completo y pusheado (NO re-implementar)

**Infraestructura y análisis:**
- Pipeline CLI end-to-end (`scripts/run_full_pipeline.py`)
- Comparador CFP vs INIDEP con Triángulo de Auditoría CBA·CMP·Captura
- PatternDetector (HHI, reversiones de veda, riesgo temporal)
- GraphBuilder (NetworkX, comunidades, centralidad)
- FAOFIRMSScraper (8 especies, seed data verificado)
- AlertEngine (4 tipos de alertas)
- AuditEngine (Claude API + prompt caching)
- NER pesquero (spaCy EntityRuler, 6 categorías)
- API REST FastAPI (17 endpoints)
- Dashboard Streamlit (13 páginas activas)
- Docker + GitHub Actions CI

**Serie FisheriesAudit ALG (I+D+I publicable):**
- `src/analysis/research_exporter.py` — 5 exporters: ResearchExporter, PatternExporter, GraphExporter, FAOExporter, ModelExporter
- `src/analysis/linkedin_formatter.py` — posts Serie FisheriesAudit ALG 2026
- `src/dashboard/pages/13_Investigacion.py` — hub de publicación
- `notebooks/FisheriesAudit_ALG_01_triangulo_auditoria.ipynb`
- `notebooks/FisheriesAudit_ALG_02_patrones_historicos.ipynb`
- `notebooks/FisheriesAudit_ALG_03_red_relaciones.ipynb`
- `notebooks/FisheriesAudit_ALG_04_contexto_internacional.ipynb`
- `notebooks/FisheriesAudit_ALG_05_modelo_predictivo.ipynb`

**Tests:** 664 tests, todos verdes (pytest)

---

## Instrucciones para sesión local en VS Code

### Paso 0 — Setup inicial (solo la primera vez)

```bash
# Clonar / actualizar desde el branch de desarrollo
git fetch origin
git checkout claude/cfp-fisheries-audit-project-lLMib
git pull

# Instalar dependencias Python
pip install -r requirements.txt

# Modelo spaCy en español
python -m spacy download es_core_news_sm

# Tesseract OCR (necesario para PDFs escaneados)
# Ubuntu/WSL:  sudo apt install tesseract-ocr tesseract-ocr-spa
# macOS:       brew install tesseract tesseract-lang
# Windows:     instalar desde github.com/UB-Mannheim/tesseract/wiki

# Variables de entorno
cp .env.example .env
# Editar .env:
#   ANTHROPIC_API_KEY=sk-ant-...   ← requerido para --step audit
#   CLAUDE_MODEL=claude-sonnet-4-6
```

### Paso 1 — Pipeline: descarga de actas CFP

```bash
# Recomendado: empezar con 5 años para validar
python scripts/run_full_pipeline.py --step download --years 2020-2025

# Cuando funcione bien, escalar al corpus completo
python scripts/run_full_pipeline.py --step download --years 1998-2025
```

**Resultado esperado:** ~400 PDFs en `data/raw/` (~1-2 GB)

### Paso 2 — Pipeline: extracción y parsing

```bash
python scripts/run_full_pipeline.py --step process
```

**Resultado esperado:** textos en `data/processed/text/`, JSONs en `data/processed/json/`,
tabla `resoluciones` + `entidades` + `menciones` populadas en `catalog.db`.
Esto llena `cmp_aprobada_tn` en `cfp_cuotas` — **dato clave para el modelo predictivo**.

### Paso 3 — Pipeline: INIDEP (gratuito)

```bash
python scripts/run_full_pipeline.py --step inidep
# Opcional: enriquecer con PDFs de ITOs
python scripts/run_full_pipeline.py --step inidep --enrich-pdf
```

### Paso 4 — Pipeline: auditoría IA (tiene costo de API)

```bash
# Prueba barata ($2-5): solo 50 actas
python scripts/run_full_pipeline.py --step audit --limit 50

# Corpus parcial ($15-30): 200 actas
python scripts/run_full_pipeline.py --step audit --limit 200

# Corpus completo ($50-80): todas las actas
python scripts/run_full_pipeline.py --step audit --limit 500
```

### Paso 5 — Re-ejecutar notebooks con datos reales

Una vez que el pipeline completó, abrir los notebooks en orden:

```bash
jupyter notebook
# Abrir en este orden:
# 1. FisheriesAudit_ALG_01_triangulo_auditoria.ipynb  ← triángulo con datos reales
# 2. FisheriesAudit_ALG_02_patrones_historicos.ipynb  ← HHI real, riesgo real
# 3. FisheriesAudit_ALG_03_red_relaciones.ipynb       ← grafo real de empresas
# 4. FisheriesAudit_ALG_04_contexto_internacional.ipynb
# 5. FisheriesAudit_ALG_05_modelo_predictivo.ipynb    ← modelo con target REAL
```

**El notebook #05 es el más importante con datos reales:** el target `CMP/CBA > 1`
se calculará desde `cfp_cuotas` (populada en Paso 2) y el modelo tendrá poder
predictivo real en lugar de target sintético.

### Paso 6 — Dashboard completo

```bash
streamlit run src/dashboard/app.py
# Navegar a http://localhost:8501
# Página 13_Investigacion.py — hub de publicación con exports
```

### Verificación rápida de estado del corpus

```bash
python scripts/run_full_pipeline.py --stats
# O desde Python:
python -c "
from src.acquisition.catalog_manager import CatalogManager
cm = CatalogManager('data/processed/catalog.db')
print(cm.stats())
"
```

---

## Próximas tareas para implementar (en VS Code local)

Ver `TODO.md` para detalle completo. En orden de prioridad:

1. **Re-entrenamiento modelo con datos reales** — una vez que `--step process` completó,
   re-ejecutar notebook #05. Si AUC-ROC > 0.75 → es publicable como artículo.

2. **Entrega #06 — Análisis de red de conflictos de interés** — grafo directores
   de empresas pesqueras en cargos públicos (requiere datos externos: Registro
   Público de Comercio, Boletín Oficial Nacional).

3. **Deployment HuggingFace Spaces** — publicar el dashboard con datos seed
   para acceso público. Ver `TODO.md` sección Deployment.

4. **Dataset abierto en Zenodo** — exportar `triangulo_auditoria.csv` y
   `patrones_historicos.csv` con DOI para citabilidad académica.
