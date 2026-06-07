# Pipeline de Datos — Integridad, Trazabilidad y Tratamiento

> Versión: v0.4 | Última actualización: 2026-06-07  
> Documenta exactamente cómo cada dato entra, se transforma y se persiste.
> Ningún paso está basado en supuestos: cada contrato de datos está implementado en `src/`.

---

## Visión General del Pipeline

El pipeline tiene 5 etapas secuenciales más 3 etapas paralelas de fuentes externas. Cada
etapa produce un estado observable y verificable:

```
ETAPA 1: ADQUISICIÓN          → actas{download_status=ok, file_hash}
ETAPA 2: PROCESAMIENTO PDF    → .txt{method, char_count} + .json{Acta estructurada}
ETAPA 3: INDEXACIÓN KB        → ChromaDB{N resoluciones, cosine}
ETAPA 4: ANÁLISIS IA          → analisis_sesiones{prompt_hash, riesgo_score}
ETAPA 5: COMPARACIÓN TRIÁNGULO → comparacion_cfp_inidep{nivel_alerta}
  
PARALELAS:
  INIDEP    → inidep_evaluaciones{cba_recomendada_tn}
  GEOVISOR  → vedas_geoespaciales{resolucion_numero, resolucion_url}
  SAGPyA    → sipa_capturas{captura_tn}
```

**Comando CLI para cada etapa:**
```bash
python scripts/run_full_pipeline.py --step download   --years 1998-2025
python scripts/run_full_pipeline.py --step process
python scripts/run_full_pipeline.py --step knowledge_base
python scripts/run_full_pipeline.py --step audit      --limit 50
python scripts/run_full_pipeline.py --step inidep
python scripts/run_full_pipeline.py --step geovisor
```

---

## Etapa 1: Adquisición de Actas CFP

### Fuente y mecanismo de scraping

`CFPScraper.scrape_years(years)` itera sobre `https://cfp.gob.ar/actas-cfp?anio={year}`.
Para cada año, parsea el bloque HTML `<ul class="ListaPdf">` y extrae:

```python
@dataclass
class ActaMetadata:
    year: int
    nombre: str              # "Acta CFP N° 34/2025"
    url: str                 # URL completa al PDF
    filename: str            # "acta_cfp_34_2025.pdf"
    is_anexo: bool           # distingue actas de sus anexos
    local_path: Path | None
    download_status: str     # pending | ok | error | duplicate
    file_hash: str | None    # SHA256 del binario PDF
```

### Descarga con garantía de integridad

`CFPScraper.download_pdf()` descarga en streaming (chunks de 8.192 bytes) y calcula
el `SHA256` del contenido descargado antes de escribir al disco. El hash se persiste
en `actas.file_hash`.

**Implicaciones:**
- Si el mismo PDF se ofrece en dos URLs distintas, el hash detecta si el contenido es idéntico
- Si un PDF en el servidor cambia, el hash nuevo es diferente → re-descarga explícita
- Los PDFs nunca se re-descargan si `download_status=ok` → idempotencia

### Catálogo SQLite

`CatalogManager.upsert_acta()` usa `INSERT OR IGNORE` en `url` (UNIQUE) — jamás
duplica un acta. El estado del pipeline se persiste en flags binarios:

```
text_extracted → parsed → embedded → analyzed
```

`get_pending(stage)` filtra qué actas todavía no pasaron una etapa determinada.
Esto hace que el pipeline sea **reanudable** — se puede interrumpir y continuar
desde donde quedó.

---

## Etapa 2: Procesamiento de PDFs

### 2.1 Extracción de texto — Cascada de 3 niveles

El módulo `pdf_extractor.py` implementa una cascada con reportabilidad del método usado:

```
[nivel 1] pdfplumber
  → extrae texto nativo con tolerancias (x_tolerance=3, y_tolerance=3)
  → si len(texto) < 100 caracteres → intentar nivel 2

[nivel 2] PyMuPDF (fitz)
  → page.get_text("text")
  → mejor manejo de fuentes OTF/CFF embebidas
  → si len(texto) < 100 caracteres → intentar nivel 3

[nivel 3] Tesseract OCR
  → PyMuPDF renderiza páginas a 300 DPI → PIL Image
  → pytesseract.image_to_string(lang="spa")
  → para PDFs escaneados (imagen sin capa de texto)

[failed] si ningún nivel supera 100 chars → status="failed"
```

**Salida por PDF:**
```python
{
    "path": "data/processed/text/2025/acta_cfp_34_2025.txt",
    "text": "...",
    "method": "pdfplumber" | "pymupdf" | "ocr" | "failed",
    "page_count": 12,
    "char_count": 34521
}
```

El campo `method` queda registrado para diagnóstico: si muchos PDFs de un año
requieren OCR, indica que el CFP publicó esos PDFs como imágenes escaneadas.

**Limpieza del texto extraído (`_clean_text`):**
- CRLF → LF
- Caracteres de control eliminados (excepto LF y TAB)
- Colapso de espacios múltiples
- Máximo 2 saltos de línea consecutivos (evita bloques vacíos)

**Stats de lote (`batch_extract`):**
```python
{ok: int, ocr: int, failed: int, skipped: int}
```
`skipped` = el `.txt` ya existe y `overwrite=False` → idempotente.

### 2.2 Parseo estructural

`document_parser.parse_acta(text, filename)` extrae estructura semántica de
cada acta. El parser usa **3 estrategias complementarias** para extraer decisiones:

**Estrategia 1 — Bloques de decisión explícita:**
```
RE_DECISION: "se decide por (unanimidad|mayoría)…" → Decision{tipo=unanimidad, texto}
```

**Estrategia 2 — Puntos de agenda:**
```
RE_AGENDA_ITEM: "1.", "1.1.", "1.1.3." → segmenta por ítem, busca decisiones dentro
```

**Estrategia 3 — Diferidas/denegadas:**
```
RE_DIFERIDA: "queda diferido" | "se posterga"
RE_DENEGADA: "se deniega" | "no se aprueba"
```

**Extracción de citas INIDEP (`parse_fundamento_inidep`):**
```
RE_FUNDAMENTO_INIDEP: "Informe [Técnico] INIDEP N° 36/2024"
→ Decision.fundamento_inidep = ["36/2024"]
```

Esto es la base del ADR-008 (auditoría de citas): si el CFP cita un ITO y luego
aprueba una cuota que lo contradice, hay una contradicción explícita en el razonamiento.

**Extracción de asignaciones CITC (`parse_asignaciones_cuota`):**
3 patrones (directa, inversa, tabla) requieren sufijo legal (`S.A.`, `S.R.L.`, `S.C.A.`,
etc.) para evitar falsos positivos con cualquier número en el texto.

**Salida:** `.json` por acta en `data/processed/json/`, con la `Acta` dataclass completa.

### 2.3 NER pesquero

`FisheriesNER.process(text)` carga spaCy con `es_core_news_sm` y **antepone**
un `EntityRuler` (500+ patrones) que tiene precedencia sobre el NER estadístico.

```python
nlp.add_pipe("entity_ruler", before="ner", config={"overwrite_ents": True})
```

Los patrones cubren variantes ortográficas de cada especie (con/sin tilde, singular/plural)
y sufijos legales de empresas. El resultado se deduplicay se vincula a las tablas
`entidades` y `menciones` en SQLite vía `CatalogManager.upsert_entidad()`.

---

## Etapa 3: Indexación en Knowledge Base (ChromaDB)

`CFPVectorStore.index_from_json_dir(json_dir)` recorre todos los `.json` producidos
por `batch_parse` e indexa cada resolución individualmente:

```
Por cada resolución en el Acta:
  doc_id   = "{acta_key}_{numero_resolucion}"
  texto    = Decision.texto (hasta 800 chars)
  metadata = {year, numero, tipo, fecha_acta, acta_filename, especies[], empresas[]}
  → ChromaDB.upsert(doc_id, texto, metadata)
```

**Modelo de embedding:** `paraphrase-multilingual-MiniLM-L12-v2`
- 384 dimensiones, distancia coseno
- Multilingüe: entrenado en 50+ idiomas incluyendo español
- Los textos pesqueros en español rioplatense están dentro del dominio de entrenamiento

**Idempotencia:** `upsert` sobreescribe si el `doc_id` ya existe → re-indexar es seguro.

**Búsqueda semántica:**
```python
vs.search(query="cuota merluza supera CBA", n_results=10,
          where={"year": {"$gte": 2010}})
# → [{id, texto, metadata, distance}]  (distance = 1 - cosine_similarity)
```

---

## Etapa 4: Auditoría IA

### Diseño del prompt y versionado

`CFPAuditEngine` envía a Claude la resolución junto con un `system_prompt` que
establece el rol de experto en derecho pesquero argentino y el marco normativo.

**Reproducibilidad:** Cada análisis queda identificado por:
```python
prompt_hash = SHA256(system_prompt + user_template)[:16]
input_hash  = SHA256(texto_resolucion)[:16]
```
Ambos hashes se persisten en `analisis_sesiones`. Re-correr el análisis sobre el mismo texto
con el mismo prompt produce el mismo `(prompt_hash, input_hash)` — permite detectar si
el análisis se corrió antes y con qué versión del prompt.

El `prompt_registry` actúa como registro formal de versiones de prompts:
```sql
prompt_registry(nombre, version, system_hash, user_hash, temperatura, modelo, created_at)
```

### Prompt caching

El system prompt es largo y estable → se envía con `cache_control: {"type": "ephemeral"}`.
Anthropic lo cachea durante ~5 minutos, reduciendo el costo de análisis masivo por ~80%
en los tokens de contexto del sistema.

### Verificación de groundedness

`GroundednessChecker` calcula la similitud Jaccard token por token entre cada
`hallazgo` generado por el LLM y el `texto_resolucion` fuente:

```
Jaccard(hallazgo, texto) = |tokens_hallazgo ∩ tokens_texto| / |tokens_hallazgo ∪ tokens_texto|

Si Jaccard < 0.15 → hallazgo.texto = "[BAJA_EVIDENCIA] " + hallazgo.texto
```

El umbral `0.15` está configurado en `config/settings.yaml` bajo
`evaluation.low_evidence_threshold`. Esto filtra afirmaciones del LLM que no están
respaldadas por el texto del acta — la salvaguarda técnica contra alucinaciones
documentada en ADR-007.

`AuditResult.groundedness_avg` es el promedio de scores de todos los hallazgos.
Un análisis con `groundedness_avg < 0.15` indica que el LLM mayormente inventó
sus afirmaciones — señal para revisión humana.

### Selección de modelo

```python
# Análisis masivos (Sonnet): menor costo, más velocidad
engine.analyze_resolucion(id, texto, high_stakes=False)

# Análisis de alto impacto (Opus): más capacidad de razonamiento legal
engine.analyze_resolucion(id, texto, high_stakes=True)
```

El modelo concreto se configura vía `settings.yaml` y variables de entorno:
`CLAUDE_MODEL` / `CLAUDE_AUDIT_MODEL`.

---

## Etapa 5: Triángulo de Auditoría

### Fuentes del triángulo

```
INIDEP (CBA)         CFP (CMP)            SAGPyA/SIPA (captura real)
     │                    │                         │
     ▼                    ▼                         ▼
inidep_evaluaciones   cfp_cuotas           sipa_capturas
  .cba_recomendada_tn  .cmp_tn              .captura_tn
  .numero_ito          .resolucion_cfp      .año
  .estado_stock        .año                 .especie_code
```

### Algoritmo de comparación

`INIDEPComparator.compute_comparisons()` ejecuta un LEFT JOIN triple:

```sql
SELECT i.especie_code, i.zona, i.year,
       i.cba_recomendada_tn,
       c.cmp_tn,
       s.captura_tn
FROM inidep_evaluaciones i
LEFT JOIN cfp_cuotas c USING (especie_code, zona, year)
LEFT JOIN sipa_capturas s USING (especie_code, year)
```

Para cada fila:
1. Si `cmp_tn IS NULL` → `nivel = sin_datos`
2. Si `cba_tn IS NULL` → no se puede calcular ratio → `nivel = sin_datos`
3. `ratio = cmp_tn / cba_tn`
4. Clasificación por umbrales (ver Metodología de Análisis)
5. Clasificación de `captura_real` vs `cmp` → `alerta_captura`
6. Persistido en `comparacion_cfp_inidep`

### Estado actual de los datos

| Columna | Estado | Fuente |
|---------|--------|--------|
| `cba_recomendada_tn` | ✅ Poblado con SEED + scraping real | ITOs INIDEP Mar Abierto |
| `cmp_tn` | ⚠️ Vacío hasta correr `--step process` real | Actas CFP parseadas |
| `captura_tn` | ⚠️ Poblado con SEED_DATA_CAPTURAS | SIPA/SAGPyA |

El SEED_DATA en `inidep_scraper.py` contiene 50+ registros verificados de ITOs reales
(merluza, langostino, calamar illex, centolla, merluza negra, etc.) para que el sistema
sea demostrable sin necesitar el pipeline completo. Los datos SEED son explícitamente
marcados en el datasheet — no se presentan como resultado del scraping real.

---

## Mecanismos de Integridad de Datos

### 1. Hashing de archivos (SHA256)

Cada PDF descargado recibe un `file_hash = SHA256(contenido_binario)`.
- Detecta si el servidor cambia un PDF sin cambiar la URL
- Detecta duplicados entre diferentes URLs (si un acta aparece dos veces)
- Persiste en `actas.file_hash` para auditoría

### 2. Idempotencia de todas las escrituras

| Operación | Mecanismo |
|-----------|-----------|
| `upsert_acta()` | `INSERT OR IGNORE ON CONFLICT(url)` |
| `upsert_entidad()` | `INSERT OR IGNORE ON CONFLICT(tipo, nombre_norm)` |
| `upsert_anotacion()` | `INSERT OR REPLACE ON CONFLICT(resolucion_id, anotador)` |
| `add_resolucion()` en ChromaDB | `.upsert()` — sobrescribe si `doc_id` existe |
| `scrape_and_save_vedas()` | Verifica `(capa, area, resolucion_numero)` antes de insertar |
| `batch_extract()` | Omite `.txt` si ya existe (`overwrite=False` por defecto) |
| `index_from_json_dir()` | `overwrite=False` por defecto |

Correr cualquier etapa dos veces produce el mismo estado final. Ningún paso crea
duplicados por re-ejecución.

### 3. Versionado de prompts IA

El `prompt_registry` registra cada versión del system prompt con su hash.
`analisis_sesiones.prompt_hash` vincula cada análisis con la versión del prompt
que lo generó. Si el prompt cambia, los análisis existentes siguen siendo
reproducibles — se puede ver qué versión del prompt produjo qué resultado.

### 4. Normalización de entidades

`CatalogManager._normalize(texto)`:
- Minúsculas
- Remoción de tildes y diacríticos (NFD → ASCII)
- Strip de espacios

Garantiza que `"ARGENOVA S.A."` y `"Argenova S.A."` y `"argenova s.a."` se almacenen
como el mismo `nombre_norm = "argenova s.a."`, con una única entrada en `entidades`.

### 5. Calidad del texto extraído

El umbral `min_text_length = 100` en `settings.yaml` actúa como gate de calidad:
si la extracción de un PDF produce menos de 100 caracteres, el sistema lo registra como
`method=failed` y el acta queda marcada para revisión en `error_msg`.
Los PDFs corruptos o con protección de copia no pasan silenciosamente — se reportan.

### 6. Filtro de fuente en geovisor (ADR-009)

`GeovisorCrossValidator` filtra a `fuente = 'CFP'` al buscar resoluciones en el corpus.
Esto previene falsos positivos de resoluciones CTMFM (Comisión Técnica Mixta del
Frente Marítimo) que comparten el mismo formato de numeración — una misma resolución
"N° 5/2024" puede pertenecer a dos organismos distintos. Solo se cruzan las de fuente CFP.

---

## Cadena de Proveniencia (Provenance Chain)

```
Fuente original → mecanismo de adquisición → identificador estable → transformación → destino

cfp.gob.ar/actas-cfp/{año}
  └─→ batch_scraper (HTTP GET, SHA256)
       └─→ actas.url (UNIQUE) + actas.file_hash
            └─→ pdf_extractor (cascade pdfplumber→PyMuPDF→OCR)
                 └─→ processed/text/{año}/{filename}.txt + method
                      └─→ document_parser (regex multi-estrategia)
                           └─→ processed/json/{filename}.json + Acta{decisiones}
                                ├─→ ner_pesquero → entidades/menciones SQLite
                                ├─→ vector_store → ChromaDB (doc_id, metadata)
                                └─→ audit_engine → analisis_sesiones{prompt_hash, input_hash}

marabierto.inidep.edu.ar (DSpace 7 API)
  └─→ inidep_scraper (pagination, 8 CBA regex patterns)
       └─→ inidep_evaluaciones.numero_ito + cba_recomendada_tn

sere.inidep.edu.ar/geoserver (WFS 2.0.0)
  └─→ inidep_geovisor_scraper (13 capas × GetFeature)
       └─→ vedas_geoespaciales{capa, especie_code, resolucion_numero, resolucion_url}
            └─→ geovisor_cross_validator
                 └─→ cobertura_summary{pct_cobertura} (ground truth externo)
```

Cada paso es auditable: la URL de origen, el hash del archivo, el método de extracción,
el hash del prompt y el texto fuente quedan persistidos. Un revisor externo puede
reconstruir cualquier resultado.

---

## SEED Data vs. Datos Reales

El sistema distingue explícitamente entre:

| Tipo | Descripción | Dónde se usa | Estado |
|------|-------------|-------------|--------|
| **SEED_DATA INIDEP** | 50+ ITOs verificados manualmente contra documentos originales | `inidep_evaluaciones` bootstrap | ✅ Verificado |
| **SEED_DATA_CAPTURAS** | Capturas SAGPyA de referencia | `sipa_capturas` | ✅ Verificado |
| **cfp_cuotas** | CMP real de actas CFP parseadas | Vacío hasta pipeline completo | ⏳ Requiere `--step process` real |
| **Gold set evaluación** | 30 resoluciones con categorías anotadas | `anotaciones_humanas.is_gold_set=1` | ⚠️ Demo/sintético hasta anotación experta |
| **cargos_directivos** | Directores empresas vs. miembros CFP | `cargos_directivos.verificado=FALSE` | ⚠️ Demo hasta validación Boletín Oficial |

Esta distinción está documentada en `docs/DATASHEET.md` y es obligatoria para cualquier
publicación académica de resultados (ver `docs/adr/007-limites-eticos.md`).
