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
    "rojo_min": 1.15,      # Bertolotti et al. 2001
    "critico_min": 1.30,   # FAO Code of Conduct 1995 Art. 7.2.1
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
        "amarillo_min": float(umbrales.get("amarillo_min", DEFAULT_UMBRALES_CMP_CBA["amarillo_min"])),
        "rojo_min": float(umbrales.get("rojo_min", DEFAULT_UMBRALES_CMP_CBA["rojo_min"])),
        "critico_min": float(umbrales.get("critico_min", DEFAULT_UMBRALES_CMP_CBA["critico_min"])),
    }
