"""
Fixtures compartidas para todos los tests del proyecto CFP Audit.
"""
import sqlite3
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def tmp_dir(tmp_path):
    """Directorio temporal aislado para cada test."""
    return tmp_path


@pytest.fixture
def tmp_db(tmp_path) -> Path:
    """Base de datos SQLite vacía en directorio temporal."""
    return tmp_path / "test_catalog.db"


@pytest.fixture
def sample_acta_text() -> str:
    """Texto realista de un acta CFP para tests de parsing."""
    return """ACTA CFP N° 34/2025

En la ciudad de Buenos Aires, a los 15 días del mes de marzo de 2025, se reúne
el Consejo Federal Pesquero.

Se encuentran presentes: el Lic. Juan García, Representante del PODER EJECUTIVO
NACIONAL, la Dra. María López, Representante de la Provincia de Buenos Aires,
el Sr. Carlos Ruiz, Representante de la Provincia de Chubut.

Con un quórum de SIETE (7) miembros presentes, se pasa a tratar el Orden del Día.

1. MERLUZA COMÚN
CAPTURA MÁXIMA PERMISIBLE (CMP)

En el marco de la evaluación de los recursos pesqueros, el INIDEP presentó el
Informe Técnico N° 36/2024 con la Captura Biológicamente Aceptable recomendada.

Se decide por unanimidad aprobar la Captura Máxima Permisible de merluza hubbsi
para la zona Sur del paralelo 41°S en 350.000 toneladas para el año 2025, de
acuerdo con lo establecido en la Resolución CFP N° 5/2025.

1.1. CITC de merluza

Se aprueba por unanimidad la distribución de Cuotas Individuales Transferibles
de Captura (CITC) de merluza entre las empresas habilitadas.

2. CENTOLLA PATAGÓNICA

Se decide por unanimidad aprobar una captura de 1.200 toneladas de centolla
(Lithodes santolla) en el Área Sur para la temporada 2025, conforme al Acta
CFP N° 33/2025 y la Resolución CFP N° 12/2025.

3. LANGOSTINO PATAGÓNICO

La empresa PESQUERA DEL SUR S.A. solicitó ampliación de cuota.
Se acuerda por mayoría prorrogar el tratamiento del tema al próximo plenario.
"""


@pytest.fixture
def sample_inidep_record() -> dict:
    """Registro INIDEP de ejemplo para tests."""
    return {
        "especie": "merluza común",
        "especie_code": "merluza_hubbsi",
        "zona": "Sur 41°S",
        "year": 2025,
        "cba_recomendada_tn": 319_000.0,
        "cba_alternativa_tn": None,
        "estado_stock": "en_recuperacion",
        "numero_ito": "36/2024",
        "fuente_url": "https://marabierto.inidep.edu.ar",
        "notas": "Test fixture",
    }
