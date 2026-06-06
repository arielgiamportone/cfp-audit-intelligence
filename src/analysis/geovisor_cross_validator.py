"""
Validador cruzado: vedas geoespaciales del geovisor SERE (INIDEP) vs. corpus de actas CFP.

Mide qué fracción de las resoluciones de veda citadas por el geovisor —cada una con
número, fuente (CFP/CTMFM) y link al PDF oficial verificable— aparece efectivamente
citada dentro del texto de las actas ya cargadas en `resoluciones`.

Es una métrica de cobertura *externa* del parser/corpus: a diferencia de ADR-008
(auditoría de citas, bloqueada por `cfp_cuotas` vacía), esta validación no depende
del pipeline real para producir un resultado — corre hoy sobre el corpus existente
y se vuelve más representativa a medida que el corpus crece.

Lección de diseño (verificada empíricamente, ver ADR-009): CFP y CTMFM numeran sus
resoluciones de forma independiente — "Resolución N° 13/2024" existe en ambos
organismos y refiere a normas distintas. La comparación filtra por `fuente` para
evitar falsos positivos por colisión de numeración.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from loguru import logger

# Citas "Resolución [CFP] N° X/YYYY" dentro del texto de actas/resoluciones CFP
RE_CITA_RESOLUCION_CFP = re.compile(
    r"[Rr]esoluci[oó]n\s*(?:CFP)?\s*N?[°ºoO]?\.?\s*(\d{1,3})\s*[/\-]\s*(\d{2,4})"
)

# Número de resolución tal como lo cita el geovisor: "Res. 12/2018", "06_2020", etc.
RE_NUMERO_GEOVISOR = re.compile(r"(\d{1,3})\s*[/_]\s*(\d{4})")


def _normalizar_anio(anio_str: str) -> int:
    anio = int(anio_str)
    return 2000 + anio if anio < 100 else anio


@dataclass
class CoberturaResolucion:
    """Resultado de validar si una resolución citada por el geovisor aparece en el corpus."""

    resolucion_numero: str
    resolucion_fuente: str | None
    resolucion_url: str | None
    especies: list[str] = field(default_factory=list)
    numero_normalizado: tuple[int, int] | None = None  # (numero, año)
    encontrada_en_corpus: bool = False
    resolucion_ids_corpus: list[int] = field(default_factory=list)


class GeovisorCrossValidator:
    """Cruza `vedas_geoespaciales` (geovisor SERE) contra `resoluciones` (corpus CFP)."""

    def __init__(self, db_path: Path | str = "data/processed/catalog.db"):
        self.db_path = Path(db_path)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _vedas_citadas(self) -> list[dict]:
        """Resoluciones únicas (número, fuente, url, especies) citadas por el geovisor."""
        with self._conn() as conn:
            try:
                rows = conn.execute(
                    """
                    SELECT resolucion_numero, resolucion_fuente, resolucion_url,
                           GROUP_CONCAT(DISTINCT especie) AS especies
                    FROM vedas_geoespaciales
                    WHERE resolucion_numero IS NOT NULL
                    GROUP BY resolucion_numero, resolucion_fuente, resolucion_url
                    ORDER BY resolucion_numero
                    """
                ).fetchall()
            except sqlite3.OperationalError:
                return []
        out = []
        for r in rows:
            d = dict(r)
            d["especies"] = (d.pop("especies") or "").split(",")
            out.append(d)
        return out

    def _citas_en_corpus(self) -> dict[tuple[int, int], list[int]]:
        """
        Mapa (numero, año) → [resolucion.id] de citas "Resolución [CFP] N° X/YYYY"
        encontradas en `texto_completo`/`texto_resumen` del corpus de actas.
        """
        mapa: dict[tuple[int, int], list[int]] = {}
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id, texto_completo, texto_resumen FROM resoluciones"
            ).fetchall()
        for row in rows:
            texto = (row["texto_completo"] or "") + " " + (row["texto_resumen"] or "")
            for m in RE_CITA_RESOLUCION_CFP.finditer(texto):
                clave = (int(m.group(1)), _normalizar_anio(m.group(2)))
                mapa.setdefault(clave, [])
                if row["id"] not in mapa[clave]:
                    mapa[clave].append(row["id"])
        return mapa

    def validar_cobertura(self) -> list[CoberturaResolucion]:
        """
        Por cada resolución de veda citada por el geovisor con `fuente=CFP`, comprueba
        si aparece citada en el corpus de actas ya cargado.

        Solo compara `fuente=CFP`: el corpus son actas del CFP, así que comparar contra
        resoluciones CTMFM produciría falsos positivos por colisión de numeración
        (ambos organismos publican, p. ej., una "Resolución N° 13/2024" propia y distinta).
        """
        citas_corpus = self._citas_en_corpus()
        resultados = []
        for veda in self._vedas_citadas():
            if (veda["resolucion_fuente"] or "").upper() != "CFP":
                continue

            m = RE_NUMERO_GEOVISOR.search(veda["resolucion_numero"] or "")
            clave = (int(m.group(1)), _normalizar_anio(m.group(2))) if m else None
            ids = citas_corpus.get(clave, []) if clave else []

            resultados.append(
                CoberturaResolucion(
                    resolucion_numero=veda["resolucion_numero"],
                    resolucion_fuente=veda["resolucion_fuente"],
                    resolucion_url=veda["resolucion_url"],
                    especies=veda["especies"],
                    numero_normalizado=clave,
                    encontrada_en_corpus=bool(ids),
                    resolucion_ids_corpus=ids,
                )
            )
        return resultados

    def cobertura_summary(self, resultados: list[CoberturaResolucion] | None = None) -> dict:
        """Resumen agregado: % de resoluciones de veda (fuente CFP) ya cubiertas por el corpus."""
        if resultados is None:
            resultados = self.validar_cobertura()

        total = len(resultados)
        encontradas = sum(1 for r in resultados if r.encontrada_en_corpus)
        pct = round(100 * encontradas / total, 1) if total else 0.0

        resumen = {
            "total_resoluciones_citadas_cfp": total,
            "encontradas_en_corpus": encontradas,
            "pendientes": total - encontradas,
            "pct_cobertura": pct,
            "interpretacion": (
                f"{encontradas}/{total} resoluciones de veda citadas por el geovisor "
                f"INIDEP (fuente CFP) aparecen ya citadas en el corpus de actas cargado "
                f"({pct}% cobertura). El resto requiere que `--step process` cargue las "
                f"actas de los años correspondientes (ver ADR-009, ruta de migración)."
            ),
        }
        logger.info(f"GeovisorCrossValidator.cobertura_summary: {resumen['interpretacion']}")
        return resumen
