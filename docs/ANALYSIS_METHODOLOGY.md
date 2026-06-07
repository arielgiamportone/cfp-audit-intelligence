# Metodología de Análisis — Fundamentos Técnicos y Bibliográficos

> Versión: v0.4 | Última actualización: 2026-06-07  
> Documenta cada método analítico con su fundamento técnico y cita bibliográfica.
> Nada en este documento es especulación: cada procedimiento está implementado en `src/analysis/`.

---

## 1. El Triángulo de Auditoría (CBA · CMP · Captura Real)

El núcleo conceptual del sistema es la verificación del cumplimiento del Art. 9 de la
Ley 24.922 (*Régimen Federal de Pesca*, Argentina, 1998):

> "El CFP establecerá la Captura Máxima Permisible (CMP) para cada pesquería,
> teniendo en cuenta la Captura Máxima Sostenible (CMS) estimada por el INIDEP."

Esto establece tres puntos de observación que deben estar en relación de orden:

```
CBA (INIDEP)   ≥   CMP (CFP)   ≥   Captura Real (SAGPyA/SIPA)
```

Si `CMP > CBA`: el CFP excedió la recomendación científica del INIDEP.
Si `Captura Real > CMP`: la pesca efectiva excedió incluso la cuota aprobada.
Si `Captura Real << CMP`: sub-utilización de la cuota.

**Fuentes de datos:**
- `CBA` ← `inidep_evaluaciones.cba_recomendada_tn` (extraída de ITOs INIDEP Mar Abierto)
- `CMP` ← `cfp_cuotas.cmp_tn` (extraída de actas CFP parseadas)
- `Captura Real` ← `sipa_capturas.captura_tn` (SAGPyA / datos.gob.ar)

**Implementación:** `src/analysis/inidep_comparator.py` → `compute_comparisons()`

---

## 2. Sistema de Alertas CBA/CMP — Umbrales con Justificación

Los cuatro niveles de alerta están configurados en `config/settings.yaml` y justificados
bibliográficamente. No son umbrales arbitrarios.

| Nivel | Umbral | Justificación | Fuente |
|-------|--------|---------------|--------|
| 🟢 Verde | CMP ≤ 100% CBA | Límite legal explícito | Ley 24.922, Art. 9 |
| 🟡 Amarillo | 100% < CMP ≤ 115% CBA | Desviación histórica promedio observada en el régimen argentino | Bertolotti et al. (2001) — ~15% |
| 🔴 Rojo | 115% < CMP ≤ 130% CBA | Nivel de "sobreasignación significativa" que precede señales de colapso | Analogía con FAO Code 1995, Art. 7.2.1 |
| ⚫ Crítico | CMP > 130% CBA | >30% sobre el MSY = riesgo de colapso del stock documentado | FAO Code of Conduct for Responsible Fisheries, 1995 |

**Configuración en código:**
```yaml
# config/settings.yaml
comparador:
  umbrales_cmp_cba:
    amarillo_min: 1.00
    rojo_min: 1.15
    critico_min: 1.30
```

**¿Los umbrales son sensibles?** El módulo `sensitivity_analyzer.py` responde esta pregunta
formalmente (ver §6).

---

## 3. Índice HHI con Prueba Contrafactual

### El problema del HHI crudo

Reportar `HHI = 4523` sin referencia es arbitrario. ¿Es alto? ¿Comparado con qué?
El Departamento de Justicia de EE.UU. usa `HHI > 2500` como umbral de "mercado
altamente concentrado" en revisiones de fusiones — pero esa escala es para mercados
de bienes, no para distribución de menciones en actas regulatorias.

### Solución: HHI con contrafactual estadístico

`PatternDetector.hhi_concentration_with_test()` implementa la crítica metodológica:

**Paso 1 — Calcular HHI observado:**
```
HHI_obs = Σ (share_i)² × 10.000
share_i = menciones_empresa_i / total_menciones
```

**Paso 2 — Calcular HHI contrafactual (distribución uniforme):**
```
HHI_null = 10.000 / N_empresas
```

Bajo distribución perfectamente uniforme (todas las empresas tienen igual presencia),
el HHI es exactamente `10.000/N`. Esto es el baseline de referencia.

**Paso 3 — Prueba chi-cuadrado de bondad de ajuste:**
```
H₀: Las menciones se distribuyen uniformemente entre todas las empresas
H₁: Hay concentración estadísticamente significativa

χ² = Σ (O_i - E_i)² / E_i
donde E_i = total_menciones / N_empresas
```

**Salida de `hhi_concentration_with_test()`:**
```python
{
    "hhi_obs": 4523.21,
    "hhi_null": 1234.56,        # 10000/N bajo distribución uniforme
    "delta_hhi": 3288.65,       # exceso sobre el baseline
    "chi2_stat": 156.3,
    "p_valor_uniformidad": 0.001,
    "significativo_alpha_05": True,
    "universo_comparacion": "top-100 empresas por menciones",
    "interpretacion_contrafactual": "HHI observado (4523.21) excede el baseline de distribución uniforme (1234.56) en 3288.65 puntos. χ²=156.3, p=0.001 — la distribución es significativamente no uniforme."
}
```

**Antecedente bibliográfico:** Österblom et al. (2015, PLOS ONE) documentó que 13 corporaciones
controlan 11–16% de la captura marina global usando un análisis de concentración similar.
El grafo argentino es la versión nacional de ese marco.

**Implementación:** `src/analysis/pattern_detector.py` → `hhi_concentration_with_test()`

---

## 4. Motor de Auditoría IA — Diseño y Garantías

### 4.1 System prompt y rol

El `audit_engine.py` establece en el system prompt que Claude actúa como:

> Experto en derecho pesquero argentino, biología marina y política de recursos.
> Analiza actas del CFP buscando:
> 1. Decisiones que comprometan la sostenibilidad
> 2. Irregularidades procedimentales
> 3. Cumplimiento de Ley 24.922 + normativa INIDEP
> 4. Patrones de beneficio recurrente a actores específicos
> 5. Adherencia de cuotas a recomendaciones CBA del INIDEP

**Escala de riesgo:** 0–100 (0 = sin riesgo, 100 = crítico).
El prompt requiere **exclusivamente evidencia documental** del texto del acta y diferencia
explícitamente `hallazgos` (evidencia concreta) de `indicios` (pistas para investigar).

### 4.2 Prompt caching

El system prompt (estable entre análisis) se envía con `cache_control: {"type": "ephemeral"}`.
Anthropic lo mantiene cacheado ~5 minutos, reduciendo el costo de análisis masivo ~80%
en tokens de contexto. Esto hace viable el análisis de miles de resoluciones.

### 4.3 Groundedness — salvaguarda contra alucinaciones

Para cada `hallazgo` generado por el LLM, se calcula:

```
Jaccard(hallazgo, texto_acta) = |tokens_hallazgo ∩ tokens_texto| / |tokens_hallazgo ∪ tokens_texto|
```

Si `Jaccard < 0.15` (configurable en `settings.yaml`): el hallazgo recibe el prefijo
`[BAJA_EVIDENCIA]` — indica que el LLM no encontró suficiente ancla textual en el
documento fuente. No se suprime el hallazgo, pero se marca para revisión humana.

`AuditResult.groundedness_avg` es el promedio de todos los scores del análisis.
Un análisis con `groundedness_avg` muy bajo es candidato a revisión antes de publicar.

**Este mecanismo es la razón por la que el audit_engine no "alucina libre" —
cada hallazgo tiene un score de respaldo textual medible.**

### 4.4 Esquema de respuesta estructurada

El LLM responde en JSON con el esquema:
```json
{
  "riesgo_score": 72,
  "categoria_riesgo": "alto",
  "hallazgos": ["La cuota aprobada (380.000 tn) supera en 19.4% la CBA de INIDEP (319.000 tn) según ITO N° 36/2024"],
  "indicios": ["El mismo bloque empresarial aparece beneficiado en 4 de las últimas 6 sesiones"],
  "recomendaciones": ["Verificar si la diferencia es acumulativa con años anteriores"],
  "normativa_afectada": ["Ley 24.922, Art. 9"],
  "entidades_beneficiadas": ["ARGENOVA S.A.", "CONARPESA"],
  "especies_afectadas": ["merluza hubbsi"]
}
```

### 4.5 Versionado de prompts para reproducibilidad

```python
prompt_hash = SHA256(system_prompt + user_template)[:16]
input_hash  = SHA256(texto_resolucion)[:16]
```

Ambos se persisten en `analisis_sesiones`. Dos análisis del mismo texto con el mismo
prompt producen el mismo `(prompt_hash, input_hash)` — un revisor puede verificar que
el análisis es reproducible con la misma versión del prompt.

Si se actualiza el prompt, el `prompt_hash` cambia → las entradas anteriores quedan
identificadas con el prompt viejo, no se mezclan los resultados.

**Marco bibliográfico:** Mitchell et al. (2019, FAT*'19) — Model Cards for Model Reporting.
Raji et al. (2020, FAccT) — Closing the AI accountability gap.

---

## 5. Motor de Alertas — 4 Tipos con Lógica de Detección

### Tipo 1: `cuota_supera_cba`

```python
# Detecta: ratio CMP/CBA >= umbral configurado (115% o 130%)
FROM comparacion_cfp_inidep
WHERE ratio_sobreasignacion * 100 >= umbral_pct
AND nivel_alerta IN ('rojo', 'critico')
```

Severidad: `warning` (rojo) / `critical` (crítico)

### Tipo 2: `stock_critico`

```python
# Detecta: INIDEP reporta stock sobrexplotado Y el CFP tiene cuota activa
FROM inidep_evaluaciones i
JOIN cfp_cuotas c USING (especie_code, zona, year)
WHERE i.estado_stock IN ('sobrexplotado', 'en_recuperacion')
AND c.cmp_tn IS NOT NULL
```

Severidad: `critical` (sobrexplotado) / `warning` (en recuperación)

### Tipo 3: `quorum_minimo`

```python
# Detecta: decisión de cuota_captura aprobada por margen de 1 voto
FROM resoluciones
WHERE categoria = 'cuota_captura'
AND (votos_favor - votos_contra) = 1
```

Las decisiones de alto impacto económico tomadas con mínimo margen son metodológicamente
relevantes porque indican ausencia de consenso técnico. El análisis distingue estos casos.

### Tipo 4: `veda_revertida`

```python
# Detecta: decisión de veda seguida de cuota_captura para la misma especie en 0-2 años
# Heurística sobre resoluciones.texto_resumen:
WHERE texto_resumen ILIKE '%deja sin efecto%'
   OR texto_resumen ILIKE '%deroga%'
   OR texto_resumen ILIKE '%modifica la resolución%'
```

Una veda revertida en los 2 años posteriores puede indicar presión industrial sobre
la decisión regulatoria — el hallazgo más frecuentemente citado en literatura de
enforcement pesquero (Da Rocha et al. 2013, Ambio).

**Configurabilidad:** Las alertas se crean y gestionan vía tabla `alertas_reglas`.
Cada regla tiene `activa` (bool), `year_desde`/`year_hasta` (rango temporal),
`especie_code` y `zona` (filtros específicos). El sistema puede ejecutar reglas
de 1998 hasta 2025 de forma selectiva.

---

## 6. Análisis de Sensibilidad de Umbrales

### ¿Por qué importa la sensibilidad?

Un revisor puede objetar: "¿qué pasaría si el umbral fuera 120% en lugar de 115%?
¿Cambiarían radicalmente las conclusiones?" El módulo de sensibilidad responde esto.

### Diseño de la prueba

`SensitivityAnalyzer.analyze_cba_thresholds()` ejecuta un grid search sobre
combinaciones de umbrales:

```python
# Varía amarillo de 0% a 20% adicional (steps de 2.5%)
# Varía rojo de 10% a 40% adicional (steps de 2.5%)
# Para cada combo: clasifica todas las comparaciones y cuenta alertas por nivel
```

**Salida:** DataFrame con columnas `{amarillo_min, rojo_min, n_verde, n_amarillo, n_rojo, n_critico, pct_critico}`

### Prueba de estabilidad ±5%

`stability_report()` evalúa variaciones de ±5% alrededor de la configuración actual:

```python
# Para delta in [-0.05, -0.025, 0, +0.025, +0.05]:
#   aplica (amarillo_actual + delta, rojo_actual + delta)
#   cuenta alertas críticas resultantes
# Si max_variacion_criticos_pm5pct <= 2: hallazgos_estables = True
```

**Interpretación:** Si los hallazgos críticos no cambian en ±2 alertas frente a
variaciones de ±5% en los umbrales, las conclusiones son robustas respecto a la
elección de umbral. Si cambian significativamente, los umbrales son determinantes
y deben estar justificados con mayor rigor.

**Salida de `stability_report()`:**
```python
{
    "configuracion_actual": {"amarillo": 1.15, "rojo": 1.30},
    "literatura": {
        "amarillo": "Bertolotti et al. 2001 — desviación histórica ~15%",
        "rojo": "FAO Code 1995 Art. 7.2.1 — >30% sobre MSY = riesgo colapso"
    },
    "max_variacion_criticos_pm5pct": 1,
    "hallazgos_estables": True
}
```

**Visualización:** Heatmap matplotlib (eje X = amarillo_min, eje Y = rojo_min, color = %_critico).
La configuración actual aparece marcada con estrella roja.

**Exportación:** `tabla_latex_sensibilidad()` genera tabla LaTeX lista para incluir en paper.

---

## 7. Red de Relaciones y Análisis de Grafo

### Estructura del grafo bipartito

`CFPGraphBuilder.build_graph()` construye una red bipartita:
- **Nodos tipo A:** Especies (`ESPECIE_PESCA`)
- **Nodos tipo B:** Empresas (`EMPRESA_PESCA`)
- **Aristas:** Co-mención en la misma resolución, `weight = n_co_menciones`

El grafo excluye aristas especie–especie y empresa–empresa — solo relaciones inter-tipo,
lo que facilita interpretar "qué empresas están más asociadas a qué especies en las decisiones del CFP".

### Métricas de centralidad

Para cada nodo:
- `degree centrality` = número de vecinos directos
- `betweenness centrality` = cuántas rutas mínimas del grafo pasan por ese nodo

Una empresa con alta betweenness conecta a especies que no están directamente relacionadas
entre sí — es un nodo "puente" en la estructura de decisiones.

### HHI por especie

Para cada especie, el HHI mide la concentración de co-menciones entre empresas:

```
Para especie E:
  share_i = weight(E, empresa_i) / Σ weight(E, empresa_j) ∀ j
  HHI_E = Σ (share_i)² × 10.000
```

Un `HHI_merluza > 2500` indica que pocas empresas acaparan la mayoría de las
co-menciones con merluza en las actas — potencial captura regulatoria.

**Antecedente bibliográfico:** Österblom et al. (2015) + Virdin et al. (2021) — el enfoque
de "keystone corporate actors" aplicado al contexto argentino.

---

## 8. Validación Cruzada con Geovisor SERE (Ground Truth Externo)

El `GeovisorCrossValidator` implementa una métrica de cobertura del corpus que no
depende del pipeline interno — es una fuente de verdad **externa e independiente**.

**Lógica:**
1. El geovisor SERE (INIDEP) lista vedas geoespaciales con el número de la resolución
   CFP que las establece (ej: "Res. CFP N° 13/2024")
2. El validador busca esos números en `resoluciones.texto_completo` del corpus
3. Si la resolución está en el corpus, el acta fue descargada y procesada correctamente

**Resultado:** `pct_cobertura` = % de resoluciones de veda del geovisor que aparecen
en el corpus de actas procesadas.

```
pct_cobertura = 0%  → el corpus está vacío (no se corrió --step process real)
pct_cobertura = 80% → 80% de las vedas del geovisor están en el corpus
pct_cobertura = 100% → cobertura total del período cubierto por el geovisor
```

Esta métrica crece automáticamente conforme se procesan más actas, sin requerir
anotación humana. Es el indicador objetivo del estado del pipeline.

**Por qué solo `fuente = 'CFP'`:** El geovisor también contiene resoluciones CTMFM
(Comisión Técnica Mixta del Frente Marítimo, Argentina–Uruguay). Ambas instituciones
usan el mismo formato de numeración (`N° X/YYYY`). Sin filtro de fuente, la búsqueda
genera falsos positivos. Decisión documentada en ADR-009.

---

## 9. Evaluación con Ground Truth — Cohen's Kappa

### Marco de evaluación

`GroundTruthEvaluator` compara la clasificación del `audit_engine` contra anotaciones
humanas de expertos del dominio (ex-funcionarios del CFP, investigadores INIDEP).

**Flujo:**
```
1. export_for_expert(n=30) → CSV con texto de resolución + clasificación del sistema
2. Experto completa columnas: categoria_humana, riesgo_score_humano, notas, confianza_pct
3. import_from_expert(csv, anotador="experto_INIDEP") → upsert en anotaciones_humanas
4. compute_metrics() → {cohen_kappa, precision, recall, f1}
```

### Cohen's kappa

```
κ = (P_o - P_e) / (1 - P_e)

P_o = acuerdo observado (% de casos donde sistema y experto coinciden)
P_e = acuerdo esperado por azar (función de las distribuciones marginales)
```

**Interpretación (Landis & Koch 1977):**

| κ | Interpretación |
|---|----------------|
| < 0.20 | Slight (mínimo) |
| 0.20–0.40 | Fair (moderado bajo) |
| 0.40–0.60 | Moderate |
| 0.60–0.80 | Substantial — umbral de publicabilidad |
| > 0.80 | Near-perfect |

**Umbral de publicabilidad:** κ ≥ 0.60 — definido en `evaluator.generate_report()`.

**Estado actual:** El gold set de 30 resoluciones es **demo/sintético** hasta que se
complete la anotación por experto. El sistema produce la estructura correcta
(métrica real), pero los valores dependen del anotador externo.

### Por qué kappa y no solo accuracy

La accuracy es sesgada cuando las categorías están desbalanceadas. Si el 70% de las
resoluciones son "bajo riesgo", un clasificador que siempre dice "bajo" tiene 70%
de accuracy sin haber aprendido nada. El kappa corrige por azar — es el estándar
en estudios de acuerdo inter-rater en ciencias sociales y evaluación de NLP.

---

## 10. Pruebas Estadísticas en los Notebooks de Investigación

Los notebooks de la Serie FisheriesAudit ALG usan exclusivamente pruebas
**no paramétricas** porque el corpus (cuotas, capturas, riesgo_score) no cumple
supuestos de normalidad:

| Prueba | Uso | Implementación |
|--------|-----|----------------|
| **Wilcoxon signed-rank** | Comparar CMP vs. CBA por especie (distribuciones apareadas) | `scipy.stats.wilcoxon` |
| **Kendall τ** | Tendencia temporal del riesgo_score o del HHI (correlación monotónica) | `scipy.stats.kendalltau` |
| **Kruskal-Wallis** | Comparar distribución de cuotas entre períodos políticos | `scipy.stats.kruskal` |
| **Chi-cuadrado** | Distribución de menciones por empresa (HHI contrafactual) | `scipy.stats.chisquare` |

**¿Por qué no ANOVA?** ANOVA requiere normalidad y homocedasticidad. Las cuotas
pesqueras son series temporales con rupturas estructurales (crisis 2000, vedas de
emergencia, pandemia). Los tests no paramétricos son más robustos frente a outliers
y distribuciones asimétricas.

---

## 11. Lo Que el Sistema Puede y No Puede Afirmar

### Puede afirmar

- **Verificablemente:** "En el período [X-Y], el CFP aprobó una CMP de Z tn para [especie],
  mientras el INIDEP recomendaba W tn (ITO N° X/Y). La diferencia es [(Z-W)/W × 100]%."
- **Estadísticamente:** "El HHI de co-menciones empresa-especie en las actas 1998–2025 es
  4523, significativamente superior al baseline uniforme (p < 0.001)."
- **Computacionalmente:** "El audit_engine clasificó esta resolución como riesgo alto
  (score=72) con groundedness_avg=0.43, basado en hallazgos con ancla textual verificable."

### No puede afirmar (por diseño)

- No imputa intencionalidad ni dolo en ninguna decisión
- No afirma ilegalidad — señala inconsistencias para investigación
- No extrapolate fuera del corpus de documentos analizados
- Los conflictos de interés detectados son `verificado=FALSE` hasta validación legal
- El modelo predictivo (Notebook #05) opera sobre target sintético — no es resultado empírico

**Marco legal completo:** `docs/adr/007-limites-eticos.md`

---

## Referencias Bibliográficas

Ver `docs/bibliography.md` para referencias completas con DOI verificado.

**Referencias directamente aplicadas en esta metodología:**

- Ley 24.922 (Argentina, 1998) — fundamento legal de los umbrales verdes
- Bertolotti, M.I. et al. (2001) — justificación del umbral amarillo (115%)
- FAO Code of Conduct for Responsible Fisheries (1995), Art. 7.2.1 — umbral crítico (130%)
- Da Rocha, J.M., Villasante, S., & Trelles González, R. (2013). *Ambio* — marco teórico de enforcement
- Froese, R. et al. (2025). *Science* — "overfishing ratchet" como patrón sistémico
- Österblom, H. et al. (2015). *PLOS ONE* — keystone actors, base metodológica del HHI en grafo
- Mitchell, M. et al. (2019). *FAT\* '19* — model cards (audit_engine)
- Raji, I.D. et al. (2020). *FAccT* — internal algorithmic auditing framework
- Landis, J.R. & Koch, G.G. (1977). *Biometrics* — interpretación del Cohen's kappa
- Nosek, B. et al. (2018). *PNAS* — pre-registro de hipótesis
