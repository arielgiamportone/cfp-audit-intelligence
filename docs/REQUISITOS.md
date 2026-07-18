# Requisitos del sistema — CFP Audit Intelligence

> Documento de requisitos del proyecto (fuente única). Aplica el marco de la unidad
> *Análisis de Requisitos* del máster: fichas RF/RNF, historias de usuario con criterios
> **Given-When-Then**, priorización **MoSCoW** y **trazabilidad** requisito → implementación.
>
> Reglas de un buen requisito: claro · útil · comprobable · trazable · actualizado.

---

## 1. Requisitos funcionales (RF)

| ID | Descripción | Prioridad (MoSCoW) | Criterio de verificación | Implementado en |
|----|-------------|:---:|--------------------------|-----------------|
| RF01 | Descargar las actas públicas del CFP por rango de años | **M** | Los PDFs quedan catalogados con hash y estado de descarga | `acquisition/batch_scraper.py`, `catalog_manager.py`, pág. 01 |
| RF02 | Extraer el texto de los PDFs (cascada pdfplumber → PyMuPDF → OCR) | **M** | Cada acta descargada tiene texto extraído | `processing/pdf_extractor.py` |
| RF03 | Parsear resoluciones y reconocer entidades (especie, empresa, persona…) | **S** | Resoluciones y entidades persistidas por acta | `processing/document_parser.py`, `ner_pesquero.py` |
| RF04 | Búsqueda semántica (RAG) sobre el corpus de actas | **S** | Una consulta en lenguaje natural devuelve resoluciones relevantes | `knowledge_base/vector_store.py`, pág. 02 |
| RF05 | Auditar resoluciones con IA (Claude) con salvaguardas de groundedness | **M** | El análisis marca `[BAJA_EVIDENCIA]` cuando no hay anclaje textual | `analysis/audit_engine.py`, pág. 03 |
| RF06 | Comparar cuota aprobada (CMP·CFP) vs recomendación científica (CBA·INIDEP) y emitir nivel de alerta | **M** ⭐ | Dado especie/año con CMP > 1,15·CBA → alerta 🔴 (ver umbrales) | `analysis/inidep_comparator.py`, pág. 05 |
| RF07 | Sistema de alertas configurables (exceso CBA, stock crítico, reversión, quórum) | **S** | Las reglas activas generan alertas con severidad | `analysis/alert_engine.py`, pág. 08 |
| RF08 | Timeline histórico de cuotas por especie | **C** | Se visualiza la evolución por año y especie | pág. 06 |
| RF09 | Grafo de relaciones empresas–resoluciones–miembros | **C** | Se renderiza la red interactiva | `analysis/graph_builder.py`, pág. 07 |
| RF10 | Generar reporte PDF ejecutivo | **S** | Se descarga un PDF con hallazgos y metadatos | `analysis/report_generator.py`, pág. 09 |
| RF11 | Exponer una API REST (actas, search, alertas, inidep, entidades) | **S** | `/docs` OpenAPI responde y los endpoints devuelven datos | `api/` (5 routers) |
| RF12 | Integrar contexto externo (FAO FIRMS, CONICET, capturas SIPA) | **C** | Cada página muestra datos de su fuente | págs. 10/11/12 |
| RF13 | Verificación geoespacial/satelital (geovisor SERE, CONAE) | **C** | Se cruzan vedas y esfuerzo satelital con el corpus | págs. 16/17 (ADR-009/010) |

## 2. Requisitos no funcionales (RNF)

| ID | Categoría | Requisito | Criterio de verificación | Evidencia |
|----|-----------|-----------|--------------------------|-----------|
| RNF01 | Reproducibilidad | Pipeline idempotente (hash SHA256, *provenance chain*) | Re-ejecutar no duplica registros | `docs/DATA_PIPELINE.md` |
| RNF02 | Calidad | Suite de tests + CI (ruff + pytest 3.10/3.11) | CI en verde; 945 tests pasan | `.github/workflows/ci.yml`, `tests/` |
| RNF03 | IA responsable | Groundedness + marcado `[BAJA_EVIDENCIA]`; Model Card + Datasheet | Hallazgos sin anclaje quedan marcados | `docs/MODEL_CARD.md`, ADR-007 |
| RNF04 | Seguridad | Secretos (`ANTHROPIC_API_KEY`) nunca en el repo | No hay claves hardcodeadas | `.env.example`, `.streamlit/secrets` ignorado |
| RNF05 | Portabilidad / Despliegue | Ejecutable en local, Docker y Streamlit Cloud | `docker-compose up` levanta API+dashboard; URL pública viva | `Dockerfile`, `docs/TFM_DEPLOY.md` |
| RNF06 | Usabilidad | UI comprensible para público no experto | Home con glosario, semáforo y "empieza por aquí" | `dashboard/app.py` |
| RNF07 | Mantenibilidad | Arquitectura por capas + configuración centralizada | Dominio sin dependencias de UI; rutas en `config_loader` | ADR-011, `config_loader.py` |
| RNF08 | Soberanía del dato / Ética | Solo fuentes públicas; análisis descriptivo, no acusatorio | Hallazgos "requieren verificación" | ADR-007, `docs/adr/` |

## 3. Historias de usuario y criterios de aceptación (Given-When-Then)

**HU-01 — Detectar sobreasignación de cuotas** (RF06)
> Como **auditor/ciudadano interesado**, quiero **comparar la cuota aprobada con la recomendación científica por especie**, para **detectar cuándo se supera el límite sostenible**.
```
DADO    que existe una CBA (INIDEP) y una CMP (CFP) para una especie y año
CUANDO  abro el Comparador y selecciono esa especie
ENTONCES veo el % CMP/CBA y un nivel de alerta 🟢🟡🔴⚫ según los umbrales
```

**HU-02 — Buscar en las actas en lenguaje natural** (RF04)
> Como **investigador**, quiero **buscar por significado en el corpus de actas**, para **encontrar resoluciones relevantes sin conocer palabras exactas**.
```
DADO    que la Knowledge Base está indexada
CUANDO  escribo "vedas de langostino" y busco
ENTONCES obtengo resoluciones ordenadas por similitud semántica
```

**HU-03 — Integrar los datos desde otros sistemas** (RF11)
> Como **desarrollador/integrador**, quiero **una API REST documentada**, para **consumir actas, alertas y comparaciones desde otras aplicaciones**.
```
DADO    que la API está en marcha
CUANDO  hago GET /inidep/comparacion
ENTONCES recibo un JSON con las comparaciones CBA/CMP y su nivel de alerta
```

## 4. Restricciones
- **Tecnología:** Python 3.10+; el dominio no debe depender de la capa de UI (ADR-011).
- **Datos:** únicamente documentos y fuentes **públicas**.
- **Presupuesto de IA:** en modo demo el coste de tokens es ~0 (datos sembrados); la auditoría masiva requiere presupuesto de API.
- **Hosting demo:** Streamlit Community Cloud (~1 GB RAM) → la demo usa un subconjunto/seed.

## 5. Checklist de validación (por requisito)
- [ ] ¿Se entiende a la primera (sin ambigüedad)?
- [ ] ¿Es medible/comprobable y tiene criterio de aceptación?
- [ ] ¿Evita palabras vagas ("rápido", "fácil", "intuitivo")?
- [ ] ¿Está trazado a un módulo/página (columna "Implementado en")?

---
_Trazabilidad y decisiones relacionadas: ver `docs/adr/` (ADR-001…011) y `CHANGELOG.md`._
