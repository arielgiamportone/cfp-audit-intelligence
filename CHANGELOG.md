# Changelog

Todos los cambios notables de este proyecto se documentan aquí.
Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/).

> Contexto: este repositorio es el **Trabajo Final del Máster en Desarrollo con IA**.
> Las mejoras se aplican **unidad a unidad** del máster (ver `docs/TFM_PLAN_MEJORAS.md`),
> citando el principio aplicado en cada entrada.

## [Sin publicar]

### Añadido
- **Entrega TFM:** `LICENSE` (MIT), sección TFM en el README (entregables, stack, estructura,
  escalabilidad), guiones de slides y vídeo (`docs/TFM_PRESENTACION.md`, `docs/TFM_GUION_VIDEO.md`)
  y runbook de despliegue (`docs/TFM_DEPLOY.md`).
- **Despliegue** en Streamlit Community Cloud (URL pública) + `.streamlit/config.toml`.
- **Plan de mejoras del TFM** (`docs/TFM_PLAN_MEJORAS.md`): aplicación de conceptos del máster.
- **ADR-011**: decisión de mantener **Streamlit como adaptador de entrega (UI)** sobre un
  dominio agnóstico y junto a la API REST (patrón hexagonal / Ports & Adapters), con
  evidencia de que el dominio no depende de la UI.
- **Unidad 2 (Análisis de Requisitos):** `docs/REQUISITOS.md` con fichas RF/RNF, historias
  de usuario (Given-When-Then), priorización MoSCoW y **trazabilidad requisito → módulo**.
- **Unidad 2 (Spec Driven Development):** `docs/specs/SPEC-001-export-comparador.md`,
  ejemplo Spec-First (la spec como fuente de verdad) para exportar la comparación CBA/CMP.
  Enlaces a REQUISITOS y specs añadidos a la Documentación Técnica del README.

### Cambiado
- **Narrativa TFM (autor):** se incorpora el arco personal **Data Science → DEV** en el guion
  de vídeo (`docs/TFM_GUION_VIDEO.md`) y una nota de motivación en el README.
- **UX (enfoque desarrollo):** home reescrito para público no experto (explicación en lenguaje
  llano, diagrama ciencia→política→realidad, leyenda de alertas, glosario, "empieza por aquí").
- **UX:** intros "¿cómo leer esta página?" en Comparador y Alertas; estados vacíos amigables
  ("modo demo") en Adquisición, Knowledge Base, Auditoría IA y Reportes.

### Añadido — Unidad 3 · Arquitectura (Hexagonal / DIP)
- **Puertos del dominio** (`src/ports.py`): `VectorStorePort` y `AuditorPort` como
  `typing.Protocol` estructural; los adaptadores actuales (ChromaDB, Claude) los cumplen
  sin cambios. Test de conformidad en `tests/test_ports.py`. Decisión en **ADR-012**.

### Refactorizado — Unidad 1 · Buenas Prácticas y Principios de Diseño
- **DRY + DIP (fuente única de verdad):** se añadieron `get_db_path()` y `get_kb_dir()` a
  `config_loader.py` y se refactorizaron las **18 páginas del dashboard + `app.py`** para
  consumir esas funciones en lugar de rutas hardcodeadas (antes duplicadas en 18 sitios y en
  dos formas distintas).
- **Bug latente corregido (KISS/robustez):** las rutas eran relativas al *cwd* en ~12 páginas
  (fallaban si el directorio de trabajo cambiaba). Ahora son **absolutas y ancladas a la raíz**
  del proyecto, con override opcional vía `settings.yaml → paths.{db_path,kb_dir}`.
