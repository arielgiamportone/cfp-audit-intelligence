#!/usr/bin/env python3
"""
Fuente única de verdad para el conteo de tests en la documentación.

Corre `pytest --collect-only -q`, obtiene el número real de tests y estampa
ese valor en todas las referencias al TOTAL en README.md, CLAUDE.md, AGENTS.md
y TODO.md. Idempotente: correrlo dos veces no produce cambios la segunda vez.

Uso:
    python scripts/update_test_count.py          # actualiza in-place
    python scripts/update_test_count.py --check   # falla si hay drift (CI)
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Archivos de documentación con referencias al total de tests
DOC_FILES = ["README.md", "CLAUDE.md", "AGENTS.md", "TODO.md"]

# Patrones que matchean SOLO referencias al TOTAL de tests.
# Cada patrón captura el número en el grupo 1 y conserva el resto del texto.
# NO incluir `\d+ tests en` (conteos granulares por archivo en TODO.md).
TOTAL_PATTERNS: list[re.Pattern] = [
    re.compile(r"(?<=tests-)(\d+)(?=%20passing)"),  # badge shields.io
    re.compile(r"(?<=Tests: )(\d+)"),  # label del badge [![Tests: N]
    re.compile(r"(\d+)(?= tests, todos verdes)"),  # "N tests, todos verdes"
    re.compile(r"(\d+)(?= tests totales)"),  # "N tests totales"
    re.compile(r"(\d+)(?= tests pasando)"),  # "N tests pasando"
    re.compile(r"(\d+)(?= tests y ~50 módulos)"),  # AGENTS.md frase específica
    re.compile(r"(?<=\()(\d+)(?= actualmente\))"),  # "(N actualmente)"
]


def get_test_count() -> int:
    """Obtiene el número real de tests vía pytest --collect-only."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    output = result.stdout + result.stderr

    # Formato típico: "852 tests collected in 0.50s"
    m = re.search(r"(\d+) tests? collected", output)
    if m:
        return int(m.group(1))

    # Fallback: contar líneas que parecen IDs de test (contienen "::")
    n = sum(1 for line in output.splitlines() if "::" in line)
    if n == 0:
        raise RuntimeError(f"No se pudo determinar el conteo de tests.\n{output[-500:]}")
    return n


def update_text(text: str, count: int) -> str:
    """Reemplaza todas las referencias al total por `count`."""
    for pattern in TOTAL_PATTERNS:
        text = pattern.sub(str(count), text)
    return text


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="No escribe; retorna código 1 si hay drift (uso en CI).",
    )
    args = parser.parse_args()

    count = get_test_count()
    print(f"Conteo real de tests: {count}")

    drift_found = False
    for fname in DOC_FILES:
        path = REPO_ROOT / fname
        if not path.exists():
            continue
        original = path.read_text(encoding="utf-8")
        updated = update_text(original, count)
        if updated != original:
            drift_found = True
            if args.check:
                print(f"  DRIFT: {fname} tiene un conteo desactualizado")
            else:
                path.write_text(updated, encoding="utf-8")
                print(f"  Actualizado: {fname}")
        else:
            print(f"  OK: {fname}")

    if args.check and drift_found:
        print("\nDrift detectado. Correr: python scripts/update_test_count.py")
        return 1
    if not drift_found:
        print("\nSin cambios — documentación sincronizada.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
