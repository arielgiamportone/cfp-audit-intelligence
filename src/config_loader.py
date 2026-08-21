"""
Carga centralizada de la configuración del sistema (config/settings.yaml).

Provee acceso cacheado a settings.yaml con fallback a valores por defecto,
para evitar literales mágicos dispersos en el código (umbrales, modelos, etc.).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from loguru import logger

DEFAULT_SETTINGS_PATH = Path("config/settings.yaml")

# Umbrales por defecto si settings.yaml no está disponible.
# Justificación bibliográfica: ver config/settings.yaml y SensitivityAnalyzer.
DEFAULT_UMBRALES_CMP_CBA = {
    "amarillo_min": 1.00,  # Ley 24.922 Art. 9
    "rojo_min": 1.15,  # Bertolotti et al. 2001
    "critico_min": 1.30,  # FAO Code of Conduct 1995 Art. 7.2.1
}


@lru_cache(maxsize=4)
def load_settings(path: str | Path = DEFAULT_SETTINGS_PATH) -> dict[str, Any]:
    """Carga settings.yaml (cacheado). Retorna dict vacío si no existe."""
    path = Path(path)
    if not path.exists():
        logger.debug(f"settings.yaml no encontrado en {path}; usando defaults")
        return {}
    try:
        with path.open(encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception as exc:
        logger.warning(f"Error leyendo {path}: {exc}; usando defaults")
        return {}


def get_umbrales_cmp_cba(path: str | Path = DEFAULT_SETTINGS_PATH) -> dict[str, float]:
    """
    Retorna los umbrales CMP/CBA del comparador.

    Lee config/settings.yaml → comparador.umbrales_cmp_cba, con fallback a
    los valores por defecto justificados bibliográficamente.
    """
    settings = load_settings(path)
    umbrales = (
        settings.get("comparador", {}).get("umbrales_cmp_cba", {})
        if isinstance(settings, dict)
        else {}
    )
    return {
        "amarillo_min": float(
            umbrales.get("amarillo_min", DEFAULT_UMBRALES_CMP_CBA["amarillo_min"])
        ),
        "rojo_min": float(umbrales.get("rojo_min", DEFAULT_UMBRALES_CMP_CBA["rojo_min"])),
        "critico_min": float(umbrales.get("critico_min", DEFAULT_UMBRALES_CMP_CBA["critico_min"])),
    }


# ── Rutas del proyecto (fuente única de verdad: DRY + DIP) ─────────────────────
# Este archivo vive en src/config_loader.py, por lo que parent.parent es la raíz
# del repositorio. Anclar las rutas aquí evita rutas hardcodeadas y dependientes
# del directorio de trabajo (cwd) dispersas por las páginas del dashboard.

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _resolve_path(override: str | None, default_rel: str) -> Path:
    """Devuelve una ruta absoluta anclada a la raíz del proyecto.

    Si `override` es absoluto se respeta; si es relativo se ancla a PROJECT_ROOT;
    si es None se usa `default_rel` (relativo a la raíz).
    """
    rel = override or default_rel
    p = Path(rel)
    return p if p.is_absolute() else PROJECT_ROOT / p


def get_db_path(path: str | Path = DEFAULT_SETTINGS_PATH) -> Path:
    """Ruta absoluta y única de la base de datos SQLite del catálogo.

    Override opcional vía settings.yaml → `paths.db_path`.
    """
    settings = load_settings(path)
    override = settings.get("paths", {}).get("db_path") if isinstance(settings, dict) else None
    return _resolve_path(override, "data/processed/catalog.db")


def get_kb_dir(path: str | Path = DEFAULT_SETTINGS_PATH) -> Path:
    """Ruta absoluta del directorio de la Knowledge Base (ChromaDB).

    Override opcional vía settings.yaml → `paths.kb_dir`.
    """
    settings = load_settings(path)
    override = settings.get("paths", {}).get("kb_dir") if isinstance(settings, dict) else None
    return _resolve_path(override, "data/knowledge_base")
