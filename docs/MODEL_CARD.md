# Model Card — CFP Audit Intelligence

> Estructura basada en Mitchell et al. (2019), *Model Cards for Model Reporting* (FAT\* '19).
> Última actualización: 2026-06-02

Este sistema usa **dos modelos** con propósitos distintos. Se documentan por separado.

---

## Modelo A — Audit Engine (clasificación de resoluciones)

### Model Details
- **Desarrollado por:** Ariel Giamportone (proyecto CFP Audit Intelligence).
- **Tipo:** clasificación + extracción asistida por LLM, sin fine-tuning.
- **Modelo base:** Claude (`claude-sonnet-4-6` para análisis masivos;
  `claude-opus-4-8` para deep analysis). Acceso vía Anthropic API con prompt caching.
- **Entrada:** texto de una resolución/acta del CFP.
- **Salida:** categoría de riesgo (bajo/medio/alto/crítico), `riesgo_score`,
  lista de hallazgos, e `indicios`. Persistido en `analisis_sesiones`.
- **Versionado:** cada análisis se identifica por `(prompt_hash, input_hash,
  modelo_ia, temperatura, created_at)` — ver ADR-005.

### Intended Use
- **Uso previsto:** auditoría **descriptiva** de patrones en decisiones públicas,
  como apoyo a investigación periodística y académica.
- **Usuarios:** investigadores, periodistas de datos, organismos de control.
- **Fuera de alcance:** NO es una herramienta de decisión legal ni de imputación
  penal. Sus salidas no constituyen prueba ni acusación (ver ADR-007).

### Factors
- Variabilidad por especie, año, tipo de decisión y longitud del acta.
- Sesgo potencial del modelo base hacia el español rioplatense y la terminología
  pesquera; mitigado parcialmente con NER pesquero especializado.

### Metrics
- **Precisión / Recall / F1** por categoría y **Macro-F1** (`GroundTruthEvaluator`).
- **Cohen's kappa** inter-rater contra anotaciones de experto.
- **Groundedness** (Jaccard token-overlap) por hallazgo; `[BAJA_EVIDENCIA]` si < 0.15.
- **Umbral de publicabilidad:** kappa ≥ 0.60 (Landis & Koch 1977).

### Evaluation Data
- Gold set de 30 resoluciones (12 bajo / 10 medio / 5 alto / 3 crítico),
  `src/evaluation/annotation_protocol.py`. **Actualmente sintético/demo** hasta
  anotación por experto del dominio (INIDEP / ex-CFP).

### Training Data
- Ninguna (no hay fine-tuning). El comportamiento proviene del modelo base +
  prompt versionado en `prompt_registry`.

### Ethical Considerations
- Ver **`docs/adr/007-limites-eticos.md`**. Análisis descriptivo, solo datos
  públicos, hallazgos marcados como "requieren verificación".

### Caveats and Recommendations
- Los resultados de kappa con datos reales (no el gold set demo) son los que
  importan para publicación.
- El groundedness por token-overlap puede penalizar paráfrasis correctas.

---

## Modelo B — Modelo predictivo de sobreasignación (Notebook #05)

> ⚠️ **ADVERTENCIA PRINCIPAL: TARGET SINTÉTICO.**
> En la versión actual, el target `CMP/CBA > 1` es **sintético**, calibrado sobre
> la tasa histórica de la literatura (Bertolotti et al. 2001, ~65% de
> sobreasignación). **El modelo aprende la función generadora del target, no el
> dominio real.** NO usar para predicción real ni publicar como hallazgo empírico
> hasta que `cfp_cuotas.cmp_aprobada_tn` esté poblado con datos reales del pipeline.

### Model Details
- **Tipo:** clasificación binaria (Random Forest + Logistic Regression), con SHAP
  para interpretabilidad. `notebooks/FisheriesAudit_ALG_05_modelo_predictivo.ipynb`.
- **Entrada:** features por especie/año (estado de stock, histórico de cuotas, etc.).
- **Salida:** probabilidad de sobreasignación (CMP > CBA).

### Intended Use
- **Uso previsto (futuro):** una vez con datos reales, anticipar qué decisiones
  tienen mayor riesgo de superar la recomendación científica.
- **Fuera de alcance (actual):** cualquier inferencia sobre el dominio real —
  el target no proviene de datos observados.

### Metrics
- AUC-ROC, precision/recall. **Umbral de interés:** AUC-ROC > 0.75 con datos
  reales sería candidato a publicación (Marine Policy / Fisheries Research).

### Caveats and Recommendations
- Hasta el reemplazo del target sintético, el notebook es una **demostración
  metodológica**, no un resultado.
- Se recomienda **pre-registro OSF** del plan analítico antes de correr con datos
  reales, para blindar contra cherry-picking (ver ADR-007).
- No publicar como post de la Serie ALG sin el disclaimer de target sintético al frente.

---

## Referencias

Ver [`docs/bibliography.md`](bibliography.md) para la bibliografía completa verificada del proyecto.

Referencias específicas de este documento:
- Mitchell, M. et al. (2019). Model Cards for Model Reporting. *FAT\* '19*. https://doi.org/10.1145/3287560.3287596
- Gebru, T. et al. (2021). Datasheets for Datasets. *CACM*, 64(12). https://doi.org/10.1145/3458723
- Landis, J.R. & Koch, G.G. (1977). *Biometrics*, 33(1), 159–174.
- Raji, I.D. et al. (2020). Closing the AI accountability gap. *FAccT '20*. https://doi.org/10.1145/3351095.3372873
- Bertolotti, M.I. et al. (2015). Cuotas Individuales Transferibles de Captura en Argentina. UNMdP/FCEyS. https://nulan.mdp.edu.ar/3113/
- ADR-005 (evaluación y reproducibilidad), ADR-007 (límites éticos).
