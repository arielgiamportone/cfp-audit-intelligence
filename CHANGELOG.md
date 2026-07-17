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

### Cambiado
- **UX (enfoque desarrollo):** home reescrito para público no experto (explicación en lenguaje
  llano, diagrama ciencia→política→realidad, leyenda de alertas, glosario, "empieza por aquí").
- **UX:** intros "¿cómo leer esta página?" en Comparador y Alertas; estados vacíos amigables
  ("modo demo") en Adquisición, Knowledge Base, Auditoría IA y Reportes.

### Por hacer (Unidad 1 · Buenas Prácticas)
- Centralizar rutas en `config_loader.py` (`get_db_path`, `get_kb_dir`) aplicando **DRY + DIP**
  y corrigiendo el bug latente de rutas relativas al *cwd*.
