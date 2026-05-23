# ADR-003: Almacenamiento de metadatos — SQLite

**Estado:** Aceptado  
**Fecha:** 2026-05-23  
**Decidido por:** Ariel Giamportone

## Contexto

Necesitamos persistir metadatos de actas, resoluciones, entidades y resultados de análisis con soporte para consultas relacionales complejas (JOIN, GROUP BY, filtros temporales).

## Opciones evaluadas

| Opción | Pros | Contras |
|--------|------|---------|
| **SQLite** | Sin servidor, portable, SQL completo, FTS5 | No concurrencia masiva de escritura |
| PostgreSQL | Robusto, escala, JSON nativo | Requiere servidor, overkill para investigación |
| DuckDB | OLAP nativo, Parquet support, rápido | Menor soporte transaccional, relativamente nuevo |
| MongoDB | Flexible schema | Sin SQL, difícil para reportes relacionales |

## Decisión

**SQLite** con schema relacional en `data/processed/catalog.db`.

## Justificación

- Proyecto de investigación: un solo usuario, sin concurrencia
- El corpus completo (1998–2025) cabe perfectamente en SQLite (<1GB)
- Portabilidad: el archivo `.db` es el artefacto completo de metadatos
- FTS5 para búsqueda full-text como complemento a ChromaDB
- Si escala a API multi-usuario, migrar a PostgreSQL es straightforward con SQLAlchemy

## Esquema de datos

```sql
actas → resoluciones → menciones → entidades
                    ↘ analisis_sesiones
```

## Consecuencias

- Un solo archivo `.db` como fuente de verdad de metadatos
- Backup trivial: copiar el archivo
- Limit: ~100GB de datos antes de considerarse migración (nunca lo alcanzaremos)
