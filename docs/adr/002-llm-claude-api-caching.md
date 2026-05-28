# ADR-002: LLM de auditoría — Claude API con prompt caching

**Estado:** Aceptado  
**Fecha:** 2026-05-23  
**Decidido por:** Ariel Giamportone

## Contexto

El motor de auditoría necesita analizar miles de resoluciones con un LLM. El costo y la latencia son factores críticos para un proyecto de investigación independiente.

## Opciones evaluadas

| Opción | Pros | Contras |
|--------|------|---------|
| **Claude API (Sonnet + Opus)** | Prompt caching, excelente razonamiento jurídico/técnico, output JSON confiable | Costo por token |
| GPT-4o | Buena calidad, amplio soporte | Sin prompt caching nativo, costo similar |
| Llama 3 (local) | Sin costo marginal | Hardware requerido, calidad inferior para razonamiento complejo |
| Gemini 1.5 Pro | Ventana de contexto enorme | Menor calidad en español técnico |

## Decisión

**Claude Sonnet 4-6** para análisis masivos + **Claude Opus 4-7** para análisis de alto riesgo o patrones sistémicos, ambos con **prompt caching** habilitado.

## Justificación

- El system prompt de auditoría (~500 tokens) se cachea: ahorra ~80% de costos en análisis masivos
- Claude tiene excelente comprensión del español legal/técnico argentino
- Output JSON consistente, crucial para pipelines automatizados
- Modelo de dos niveles: Sonnet para volumen, Opus para profundidad

## Esquema de costos (estimado)

```
10.000 resoluciones × 600 tokens entrada × $3/M = $18 (con caching: ~$4)
10.000 resoluciones × 400 tokens salida × $15/M = $60
Total estimado corpus completo: ~$65 (Sonnet)
```

## Consecuencias

- Requiere `ANTHROPIC_API_KEY` para las etapas 4+ del pipeline
- El análisis sin API key es posible (etapas 1-3 no requieren LLM)
- Los resultados de auditoría deben persistirse en SQLite para evitar re-análisis
