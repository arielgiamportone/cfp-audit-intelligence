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
