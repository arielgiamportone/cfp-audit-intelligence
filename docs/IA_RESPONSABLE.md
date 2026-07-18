# IA Responsable — CFP Audit Intelligence

> Mapa de los **cuatro pilares de la IA responsable** (Fairness · Safety · Explainability ·
> Accountability) aplicados a este proyecto, con evidencia en el código y la documentación.
> Consolida lo ya implementado; no sustituye a `MODEL_CARD.md`, `DATASHEET.md` ni al marco
> ético `docs/adr/007-limites-eticos.md`, sino que los referencia.

---

## Resumen por pilar

| Pilar | Qué hacemos | Evidencia |
|-------|-------------|-----------|
| **Fairness** (evitar sesgos) | NER pesquero especializado para no depender solo del sesgo del modelo base; trabajo solo con **fuentes públicas**; limitaciones de sesgo declaradas | `processing/ner_pesquero.py`, `MODEL_CARD.md` (Factors), `DATASHEET.md` |
| **Safety** (fiabilidad) | Análisis **descriptivo** (no acusatorio), **human-in-the-loop**, hallazgos marcados "requieren verificación", umbral de publicabilidad (kappa ≥ 0.60) | `docs/adr/007-limites-eticos.md`, `MODEL_CARD.md` (Metrics) |
| **Explainability** (XAI) | **Groundedness** (solape textual) por hallazgo + marcado **`[BAJA_EVIDENCIA]`**; **trazabilidad** por `prompt_hash`/`input_hash`/modelo/temperatura | `evaluation/groundedness.py`, `analysis/audit_engine.py`, ADR-005 |
| **Accountability** (responsabilidad) | Modelo **SaaS/API** (Claude) con responsabilidad en cascada declarada; **Model Card** + **Datasheet**; autoría y declaración de asistencia IA | `MODEL_CARD.md`, `DATASHEET.md`, README (Autoría) |

---

## Detalle

### 1. Fairness — sesgos
- El corpus son **documentos públicos** del CFP; no hay datos personales sensibles.
- Se mitiga la dependencia del sesgo del modelo base (español rioplatense, jerga pesquera)
  con un **NER de dominio** (`EntityRuler` spaCy) que ancla especies, empresas y personas.
- **Limitación declarada** (no se oculta): el modelo base puede arrastrar sesgos; el *gold set*
  de evaluación es aún sintético/demo hasta anotación por experto (ver `MODEL_CARD.md`).

### 2. Safety — fiabilidad y control humano
- El sistema es de **apoyo**, no de decisión: sus salidas **no constituyen prueba ni acusación**
  (marco ético `ADR-007`).
- **Human-in-the-loop**: todo hallazgo se marca como *requiere verificación*.
- **Umbral de publicabilidad**: kappa ≥ 0.60 (Landis & Koch 1977) antes de comunicar resultados.

### 3. Explainability — por qué la IA "dice lo que dice"
En este proyecto la explicabilidad **no** es SHAP/Saliency (no es un modelo tabular ni de visión),
sino **anclaje textual + trazabilidad**, que es la forma adecuada para un LLM sobre documentos:
- **Groundedness**: cada hallazgo se contrasta contra el texto fuente (solape de tokens); si el
  anclaje es insuficiente se marca **`[BAJA_EVIDENCIA]`** y no se presenta como afirmación firme.
- **Trazabilidad/reproducibilidad**: cada análisis queda identificado por `prompt_hash`,
  `input_hash`, modelo y temperatura (ADR-005) → se puede **reproducir y auditar** una salida.
- **Cita a la fuente**: los resultados remiten a la resolución/acta pública de origen.

### 4. Accountability — responsabilidad
- **Cadena de responsabilidad**: el LLM es un servicio de terceros (Anthropic); el diseño,
  los umbrales, la interpretación y la supervisión son responsabilidad del autor (README, Autoría).
- **Documentos de transparencia**: `MODEL_CARD.md` (Mitchell 2019) y `DATASHEET.md` (Gebru 2021).
- **Secretos y datos**: `ANTHROPIC_API_KEY` fuera del repo; solo fuentes públicas (soberanía del dato).

---

## Privacidad y marco legal
- Solo **documentos públicos** del CFP (Ley 24.922) y fuentes científicas públicas (INIDEP, CONICET, FAO).
- Análisis descriptivo y reproducible; límites completos en `docs/adr/007-limites-eticos.md`.

## Trabajo futuro
- Anotación del *gold set* por experto del dominio para validar métricas (kappa real).
- Panel de "explicabilidad" en el dashboard que muestre groundedness y cita por hallazgo.
