# ADR-005: Framework de Evaluación y Reproducibilidad

**Estado:** Aceptado  
**Fecha:** 2026-06-01  
**Decidido por:** Ariel Giamportone

## Contexto

Sin un benchmark de evaluación contra criterio humano experto, los hallazgos
del sistema tienen el mismo peso metodológico que "una opinión bien presentada".
Cualquier revisor académico exigirá:

1. **Ground truth**: ¿existe una muestra de referencia anotada por expertos?
2. **Métricas cuantitativas**: precisión, recall, F1 por categoría; Cohen's kappa inter-rater.
3. **Groundedness**: ¿los hallazgos del LLM están anclados en el texto fuente?
4. **Reproducibilidad**: si el prompt cambia, ¿qué resultados quedan invalidados?

La referencia del paper de Harvard sobre LLMs en rulemaking federal
(Nay et al. 2023) y de Colombo et al. (arXiv:2409.13252) sobre KG+LLM en
legislación subrayan que la tasa de error del sistema debe ser cuantificada,
no solo disclaimeada.

## Decisión

Implementar cuatro mecanismos complementarios:

### 1. Gold set y `anotaciones_humanas`

Nueva tabla SQLite `anotaciones_humanas` con campos:
`(resolucion_id, anotador, categoria_ia, categoria_humana, hallazgos_ia,
hallazgos_humanos, riesgo_score_ia, riesgo_score_humano, coincide_categoria,
notas, confianza_pct, is_gold_set)`.

Gold set sintético de 30 resoluciones (12 bajo, 10 medio, 5 alto, 3 crítico)
en `src/evaluation/annotation_protocol.py` como demo funcional hasta que un
experto del dominio (INIDEP, ex-CFP) realice las anotaciones definitivas.

### 2. `GroundTruthEvaluator` (`src/evaluation/evaluator.py`)

Calcula:
- **Cohen's kappa** (Cohen 1960) para acuerdo inter-rater más allá del azar.
- **Precisión/Recall/F1** por categoría (bajo/medio/alto/crítico).
- **Macro F1** para evaluación global.

Umbral de publicabilidad: kappa ≥ 0.60 (acuerdo sustancial, Landis & Koch 1977).

Export/Import CSV para trabajo offline del experto.

### 3. Groundedness automático (`src/evaluation/groundedness.py`)

Para cada hallazgo devuelto por `audit_engine.py`, calcula un score de anclaje
textual (0–1) usando token-overlap (Jaccard) sobre ventana deslizante de 100
palabras sobre el texto fuente del acta.

- **Score < 0.15**: hallazgo marcado con `[BAJA_EVIDENCIA]` — posible alucinación.
- Integrado en `AuditResult` con campos `groundedness_scores` y `groundedness_avg`.
- La arquitectura híbrida KG+LLM (Colombo et al. 2409.13252) que garantiza
  non-hallucination por construcción está documentada en ADR-006 como trabajo futuro.

### 4. Versionado de prompts

- Columnas `prompt_hash`, `input_hash`, `temperatura` en `analisis_sesiones`.
- Nueva tabla `prompt_registry` con versiones del system prompt y user template.
- `prompt_hash = sha256[:16](system_prompt + user_prompt)`.
- `input_hash = sha256[:16](texto_resolucion)`.

Un análisis queda identificado por `(prompt_hash, input_hash, modelo_ia, created_at)`.

## Justificación

| Opción | Pros | Contras | Decisión |
|--------|------|---------|----------|
| **Ground truth + métricas** (elegida) | Publicable, cuantitativo, experto externo independiente | Requiere tiempo de experto | ✅ Implementado |
| Solo disclaimer "requiere verificación" | Costo cero | No cuantifica el error | ❌ Insuficiente para publicación |
| Fine-tuning del modelo | Máxima precisión con datos suficientes | Requiere corpus anotado grande | 🔜 Fase futura |

## Consecuencias

- **Positivas**: 
  - Hallazgos publicables con métricas de validación reportadas.
  - Reproducibilidad: cualquier análisis puede re-ejecutarse con el mismo prompt.
  - Groundedness filtra posibles alucinaciones automáticamente.
  
- **Negativas / limitaciones**:
  - El gold set sintético es demo — los resultados de kappa con datos reales
    son los que importan para publicación.
  - Groundedness por token-overlap es una aproximación; un parafraseo correcto
    puede recibir score bajo.

## Referencias

- Cohen, J. (1960). A coefficient of agreement for nominal scales.
  *Educational and Psychological Measurement*, 20(1), 37–46.
- Landis, J.R. & Koch, G.G. (1977). The measurement of observer agreement
  for categorical data. *Biometrics*, 33(1), 159–174.
- Nay, J.J. et al. (2023). Large Language Models as Proxies for Human
  Judgment in AI Rulemaking. *Harvard Journal on Legislation* (preprint).
- Colombo et al. (2024). Knowledge Graph-LLM Hybrid for Legislative Documents.
  arXiv:2409.13252.
