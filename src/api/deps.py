"""
Dependencias compartidas para la API (DB path, instancias cacheadas).
"""

from functools import lru_cache
from pathlib import Path

from src.acquisition.catalog_manager import CatalogManager
from src.analysis.alert_engine import AlertEngine
from src.analysis.inidep_comparator import INIDEPComparator

DB_PATH = Path("data/processed/catalog.db")


@lru_cache(maxsize=1)
def get_catalog() -> CatalogManager:
    return CatalogManager(db_path=DB_PATH)


@lru_cache(maxsize=1)
def get_alert_engine() -> AlertEngine:
    return AlertEngine(db_path=DB_PATH)


@lru_cache(maxsize=1)
def get_comparator() -> INIDEPComparator:
    return INIDEPComparator(db_path=DB_PATH)
