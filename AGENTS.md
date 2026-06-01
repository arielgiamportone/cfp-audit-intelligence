# AGENTS.md — Reglas para agentes IA en CFP Audit Intelligence

> Para cualquier agente (Claude Code web, Claude Code VS Code, Claude API, otros) que trabaje en este repositorio.

---

## Contexto esencial

- **Proyecto**: Auditoría de actas CFP Argentina con IA
- **Datos**: Documentos públicos — PDFs de sesiones CFP 1998–2025 + INIDEP, FAO, CONICET
- **Análisis**: Descriptivo, no acusatorio. Solo evidencia de lo que está en los textos
- **Repo GitHub**: `arielgiamportone/cfp-audit-intelligence`
- **Branch principal**: `main` (todos los agentes trabajan sobre `main`)

---

## Coordinación entre entornos

Este proyecto se trabaja desde **dos entornos simultáneos**. Es crítico que ambos estén sincronizados.

### Regla 1: siempre partir del estado de GitHub

```bash
# En cualquier entorno, antes de empezar:
git fetch origin main
git reset --hard origin/main
```

Nunca asumir que el estado local está actualizado. Otro agente pudo haber pusheado cambios.

### Regla 2: entorno web (claude.ai/code) tiene restricción de push

El entorno web no puede hacer `git push` directo (proxy HTTP bloquea). Flujo:

```
1. Desarrollar y testear localmente en el contenedor
2. Pushear usando la herramienta MCP `mcp__github__push_files`
3. Luego sincronizar local: git fetch origin main && git reset --hard origin/main
```

No crear commits locales que no se vayan a pushear — el entorno remoto es efímero.

### Regla 3: entorno VS Code puede pushear directo

```bash
git add <archivos específicos>
git commit -m "feat(scope): descripción"
git push -u origin main    # o feat/nombre-rama
```

Nunca `git add -A` o `git add .` sin revisar qué archivos incluye.

### Regla 4: TODO.md es la fuente de verdad de tareas

- Antes de empezar: leer `TODO.md` sección "Prioridad Alta"
- Al completar: marcar `[ ]` → `[x]` y hacer commit del `TODO.md`
- No empezar una tarea que ya está marcada como completada

### Regla 5: no duplicar trabajo

Antes de implementar algo nuevo, buscar si ya existe:
```bash
grep -r "nombre_funcion\|concepto" src/ tests/
```

El proyecto tiene 609 tests y ~50 módulos. Es fácil re-implementar algo que ya existe.

---

## Agentes por módulo

### Adquisición (`src/acquisition/`)

**Responsabilidad**: Obtener datos de fuentes externas.

| Archivo | Fuente | Descripción |
|---------|--------|-------------|
| `batch_scraper.py` | cfp.gob.ar | Scrapea listado de actas CFP + descarga PDFs |
| `catalog_manager.py` | SQLite local | CRUD del catálogo de actas y estado del pipeline |
| `inidep_scraper.py` | marabiertonew.inidep.edu.ar | DSpace 7 REST API → 492 ITOs completos |
| `sipa_scraper.py` | SAGPyA/SIPA | Capturas reales por especie y año |
| `fao_firms_scraper.py` | FAO FIRMS | Capturas mundiales + estado de stocks globales |
| `conicet_scraper.py` | ri.conicet.gov.ar | Publicaciones científicas INIDEP/CONICET |

**Puede hacer**:
- GET requests con delay ≥ 1.5s entre requests
- Escritura en `data/raw/` y `data/processed/catalog.db`
- Retry con tenacity (máx 3 intentos, exponential backoff)

**No puede hacer**:
- Exceder 3 retries por URL
- Ignorar errores HTTP (siempre registrar en catálogo)
- Modificar o eliminar archivos descargados
- Hacer llamadas a APIs no listadas arriba

**Patrones CBA en `inidep_scraper.py`**: hay 8 regexes en `_CBA_PATTERNS` para extraer
valores de CBA de abstracts. Están en orden de especificidad. No añadir patrones
sin actualizar los tests en `test_inidep_issue9.py`.

---

### Procesamiento (`src/processing/`)

**Responsabilidad**: Transformar PDFs en datos estructurados.

| Archivo | Descripción |
|---------|-------------|
| `pdf_extractor.py` | Cascada: pdfplumber → PyMuPDF → OCR Tesseract |
| `document_parser.py` | Parser actas CFP: resoluciones, votos, quórum, entidades |
| `ner_pesquero.py` | EntityRuler spaCy con 6 categorías pesqueras |

**Puede hacer**:
- Leer de `data/raw/`, escribir en `data/processed/text/` y `data/processed/json/`
- Actualizar `catalog.db` con estado de extracción
- Usar OCR solo cuando los dos métodos anteriores fallan

**No puede hacer**:
- Modificar los PDFs originales
- Eliminar archivos de `data/raw/`
- Llamar a APIs externas (todo procesamiento es local)

**Advertencia sobre el parser**: las actas CFP no tienen resoluciones numeradas en todos
los años. El parser maneja minutas narrativas y sesiones plenarias. Ver tests en
`test_document_parser.py` antes de modificar.

---

### Análisis (`src/analysis/`)

**Responsabilidad**: Generar inteligencia a partir de los datos procesados.

| Archivo | Descripción |
|---------|-------------|
| `audit_engine.py` | Claude API con prompt caching para análisis masivo |
| `pattern_detector.py` | HHI concentración, votaciones, reversiones estadísticas |
| `inidep_comparator.py` | CBA (INIDEP) vs CMP (CFP): 4 niveles de alerta |
| `alert_engine.py` | 4 tipos de alerta: cuota > CBA, empresa recurrente, veda revertida, quórum mínimo |
| `graph_builder.py` | NetworkX + pyvis: red empresas–resoluciones–miembros CFP |
| `report_generator.py` | Reporte PDF ejecutivo con reportlab |

**Puede hacer**:
- Llamar a `anthropic.Anthropic()` leyendo la API key solo de variables de entorno
- Usar `claude-sonnet-4-6` para análisis masivos
- Usar `claude-opus-4-8` para análisis profundo
- Leer de ChromaDB y SQLite
- Escribir resultados en `analisis_sesiones` de SQLite

**No puede hacer**:
- Hardcodear ninguna API key
- Enviar datos a APIs externas distintas a Anthropic
- Publicar resultados sin revisión humana
- Modificar el texto de las resoluciones originales
- Presentar hallazgos como acusaciones legales

**Principios de análisis**:
- Solo afirmar lo que está explícitamente en el texto
- Graduar certeza: "indicio" ≠ "hallazgo confirmado"
- Citar fragmento textual que justifica cada hallazgo
- Los resultados se marcan como "requieren verificación"

---

### Knowledge Base (`src/knowledge_base/`)

**Responsabilidad**: Indexado semántico para búsqueda y RAG.

| Archivo | Descripción |
|---------|-------------|
| `vector_store.py` | ChromaDB con embeddings `paraphrase-multilingual-MiniLM-L12-v2` |

**Puede hacer**:
- Leer JSONs de `data/processed/json/`
- Escribir y actualizar ChromaDB en `data/knowledge_base/`
- Re-indexar documentos modificados

**No puede hacer**:
- Eliminar la colección completa sin confirmación explícita del usuario
- Cambiar el modelo de embeddings sin re-indexar todos los documentos y actualizar ADR

---

### API REST (`src/api/`)

**Responsabilidad**: Exponer datos del sistema vía HTTP.

Endpoints actuales:
```
GET  /health
GET  /actas                  → listado con filtros
GET  /actas/{id}             → acta completa
GET  /resoluciones/{id}      → resolución con análisis
POST /search                 → búsqueda semántica en ChromaDB
POST /analyze                → análisis IA on-demand
GET  /alertas                → alertas activas
GET  /inidep/evaluaciones    → ITOs con CBA por especie
GET  /comparacion            → CBA vs CMP por especie/año
GET  /entidades              → empresas, personas, especies
```

**No puede hacer**:
- Exponer datos personales privados
- Llamar directamente a Claude API sin control de costos
- Modificar la base de datos (solo lectura, excepto `POST /analyze`)

---

### Dashboard (`src/dashboard/`)

**Responsabilidad**: Visualización y exploración de datos.

**Puede hacer**:
- Leer de SQLite y ChromaDB (solo lectura)
- Generar visualizaciones con Plotly
- Exportar datos en CSV/JSON
- Llamar a la API REST local

**No puede hacer**:
- Iniciar descargas masivas sin confirmación del usuario
- Llamar directamente a Claude API sin mostrar costo estimado
- Modificar la base de datos directamente (ir por la API)

---

## Flujo de desarrollo estándar

```
1. git fetch origin main && git reset --hard origin/main
2. Leer TODO.md → elegir tarea de Prioridad Alta
3. Crear rama: feat/issue-N-descripcion  (o trabajar en main para fixes pequeños)
4. Implementar
5. Escribir tests (siempre) → pytest debe pasar en verde
6. Actualizar TODO.md (marcar tarea completada)
7. Commit con mensaje descriptivo
8. Push a GitHub
9. Si es rama: merge a main
```

---

## Convenciones obligatorias

### Código
- **Logging**: `loguru`, nunca `print()`
- **Retry**: `tenacity` para toda operación de red
- **Type hints**: en todas las funciones públicas
- **Docstrings**: español, una línea + Args/Returns si es complejo
- **Idioma**: variables/funciones en inglés; docs/comentarios en español

### Tests
- Cada módulo nuevo necesita tests en `tests/`
- HTTP siempre mockeado (no llamadas reales en tests)
- Usar fixtures de `tests/conftest.py`
- `pytest` debe correr en < 30 segundos

### Git
- Formato: `feat|fix|refactor|test|docs(scope): descripción`
- Nunca commitear `data/` ni `.env`
- Nunca commitear credenciales
- Un commit por cambio lógico (no mezclar refactor con feature)

---

## Restricciones de seguridad

| Restricción | Detalle |
|-------------|----------|
| API keys | Solo desde variables de entorno; nunca en código ni commits |
| Datos fuente | Todos son documentos públicos (actas CFP, repositorios INIDEP, FAO) |
| Análisis | Descriptivo; no constituye acusación legal |
| Hallazgos | Siempre marcados como "requieren verificación" |
| Personas privadas | No publicar nombres sin consentimiento |
| Marco legal | Ley 24.922 + principios de acceso a información pública Argentina |

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

## Cómo verificar el estado del proyecto

```bash
# Tests (deben ser todos verdes)
pytest --tb=short

# Estado del catálogo
make stats
# o:
python -c "
import sqlite3
conn = sqlite3.connect('data/processed/catalog.db')
print(conn.execute('SELECT COUNT(*) FROM actas').fetchone())
"

# Estado INIDEP
python -c "
from src.acquisition.inidep_scraper import get_scrape_status
print(get_scrape_status('data/processed/catalog.db'))
"

# Commits recientes (qué cambió)
git log --oneline -10
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

---

## Señales de alerta — cuándo preguntar antes de actuar

Un agente **debe consultar al usuario** antes de:

- Eliminar o sobrescribir datos de `data/` (aunque estén gitignoreados, pueden ser costosos de regenerar)
- Cambiar el modelo de embeddings en ChromaDB (requiere re-indexar todo)
- Modificar el schema de `catalog.db` (requiere migración)
- Cambiar los patrones NER o CBA si hay tests que dependen de ellos
- Pushear directamente a `main` un cambio de más de 300 líneas
- Hacer `git reset --hard` sin haber confirmado que los cambios no pusheados son descartables
