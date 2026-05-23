# ADR-001: Base de datos vectorial — ChromaDB

**Estado:** Aceptado  
**Fecha:** 2026-05-23  
**Decidido por:** Ariel Giamportone

## Contexto

Necesitamos un vector store para indexar ~5.000–15.000 resoluciones del CFP (embeddings de ~384 dimensiones) y permitir búsqueda semántica en español.

## Opciones evaluadas

| Opción | Pros | Contras |
|--------|------|---------|
| **ChromaDB** | Embebido, sin servidor, persistente, API simple | Escalabilidad limitada en millones de docs |
| FAISS | Ultra-rápido, battle-tested | Sin metadatos nativos, sin persistencia directa |
| Pinecone | Cloud, escala infinita | Costo, dependencia externa, latencia |
| Weaviate | GraphQL + vectores, robusto | Complejo de operar, requiere Docker |
| pgvector | SQL familiar, transaccional | Requiere PostgreSQL, configuración pesada |

## Decisión

**ChromaDB** con persistencia local en `data/knowledge_base/`.

## Justificación

- El corpus es acotado (<50K documentos): ChromaDB es más que suficiente
- Investigación independiente, sin infraestructura cloud requerida
- API simple para filtros por metadatos (año, tipo, especie)
- Integración directa con sentence-transformers
- Si el proyecto escala a producción, migrar a Weaviate es straightforward

## Consecuencias

- Límite práctico: ~200K documentos antes de necesitar migración
- No soporta búsqueda full-text nativa (se complementa con SQLite FTS)
- Requiere regenerar índice si cambia el modelo de embeddings
