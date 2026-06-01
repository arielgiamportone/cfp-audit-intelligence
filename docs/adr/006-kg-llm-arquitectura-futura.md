# ADR-006: Arquitectura Híbrida KG+LLM — Trabajo Futuro

**Estado:** Diferido  
**Fecha:** 2026-06-01  
**Decidido por:** Ariel Giamportone

## Contexto

Colombo et al. (arXiv:2409.13252) proponen un enfoque híbrido que combina
Knowledge Graphs (KG) con Large Language Models para reducir alucinación en
documentos legislativos **por construcción** — en lugar de detectarla a posteriori.

La idea central: en lugar de darle al LLM el texto libre del acta y pedirle
que extraiga entidades y relaciones, se le da el subgrafo del KG correspondiente
al contexto (empresa → cuota → especie → año) y se restringe la generación
al vocabulario del grafo. Esto elimina alucinaciones sobre entidades porque el
LLM solo puede referirse a nodos que existen.

Resultado reportado: hallazgos 100% anclados en el KG, sin fabricación de
nombres de empresas, cuotas o años.

## Opciones evaluadas

| Arquitectura | Tasa de alucinación | Costo de implementación | Estado actual |
|-------------|--------------------|-----------------------|---------------|
| **LLM puro** (actual) | ~10-30% estimado | Cero | ✅ En producción |
| **LLM + groundedness** (ADR-005) | ~5-15% estimado | Bajo | ✅ Implementado |
| **KG+LLM híbrido** (esta ADR) | ~0-2% por construcción | Alto (3-4 sprints) | 🔜 Diferido |

## Decisión: Diferido

La arquitectura KG+LLM **no se implementa en Sprint 4** por las siguientes razones:

1. **Costo arquitectónico**: requiere rediseñar el grafo NetworkX de `graph_builder.py`
   como un grafo de entidades semánticas, no solo de relaciones textuales.
   Estimación: 3-4 sprints de desarrollo.

2. **Prerequisito de datos**: el KG pesquero necesita el corpus completo procesado
   (`--step process` sobre 1998-2025). Sin datos reales, el grafo de seed no
   tiene densidad suficiente para constrained generation.

3. **Alternativa suficiente**: el groundedness automático (ADR-005) reduce el riesgo
   de alucinación detectando hallazgos sin anclaje textual. Para Sprint 4,
   el balance riesgo/beneficio favorece la aproximación más simple.

## Ruta de migración (para Sprint 5+)

### Paso 1: KG de entidades pesqueras
```
NER pesquero (6 categorías) → GraphBuilder extendido:
  Nodo ESPECIE → Nodo EMPRESA → Nodo CUOTA (atributo: tn, año)
  Nodo ESPECIE → Nodo PERSONA_CFP → Nodo VOTO
  Nodo ZONA → Nodo BUQUE → Nodo EMPRESA
```

### Paso 2: Extracción de subgrafo por contexto
```python
def get_subgrafo_resolucion(resolucion_texto: str, kg: KGPesquero) -> nx.Graph:
    # Extraer entidades mencionadas en el texto (NER)
    entidades = ner.extract(resolucion_texto)
    # Obtener subgrafo de 2-hop alrededor de esas entidades
    return nx.ego_graph(kg, entidades, radius=2)
```

### Paso 3: Constrained generation
El prompt incluye el subgrafo serializado en lugar del texto libre:
```
ENTIDADES CONOCIDAS EN ESTA RESOLUCIÓN:
  ESPECIE: merluza_hubbsi [stock: plena_explotacion]
  EMPRESA: Pesquera_del_Plata_SA [cuota_hist: 42000tn, 2022]
  CBA_INIDEP: 319000tn [ITO: 36/2024]
  PERSONA: Juan_Perez [rol: vocal_prov_BS_AS]
  
Identifica hallazgos SOLO basándote en las entidades listadas.
```

### Paso 4: Validación de salida contra KG
Cada nombre de empresa, especie o persona en los hallazgos se verifica
contra el KG. Si no existe como nodo → rechazado.

## Consecuencias de diferir

- **Aceptada**: tasa de alucinación del sistema no puede garantizarse por construcción.
  Se mide a posteriori con groundedness (ADR-005).
- **Mitigación**: el framework de evaluación (ADR-005) cuantifica el error.
  La tasa observada se reporta en la metodología del paper.

## Referencias

- Colombo, P. et al. (2024). Improving LLM Reasoning via Knowledge Graph Integration
  for Legal and Legislative Documents. arXiv:2409.13252.
- Pan, S. et al. (2024). Unifying Large Language Models and Knowledge Graphs:
  A Roadmap. *IEEE TKDE*.
- Agrawal, A. et al. (2023). Do Large Language Models Know What They Don't Know?
  arXiv:2305.18153.
