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

    def validar_cumplimiento_satelital(self) -> dict:
        """
        Cruza esfuerzo_satelital (CONAE GFW AIS) con vedas_geoespaciales (INIDEP SERE).

        Para cada registro en `esfuerzo_satelital`, determina si la fecha cae dentro
        de alguna veda activa para la misma `especie_code`. Compara la mediana del
        esfuerzo GFW durante vedas vs. fuera de vedas y, si scipy está disponible,
        corre Mann-Whitney U para evaluar la significancia estadística.

        Returns:
            Diccionario con:
            - n_dentro_veda: observaciones durante períodos de veda activa
            - n_fuera_veda: observaciones fuera de veda
            - mediana_esfuerzo_dentro: mediana de esfuerzo_gfw durante veda
            - mediana_esfuerzo_fuera: mediana de esfuerzo_gfw fuera de veda
            - ratio_reduccion: mediana_dentro / mediana_fuera (< 1 → reducción)
            - mannwhitney_pvalue: p-valor Mann-Whitney U (None si scipy no disponible)
            - interpretacion: texto descriptivo del hallazgo
        """
        with self._conn() as conn:
            # Verifica que ambas tablas existen
            tablas = {
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            if "esfuerzo_satelital" not in tablas or "vedas_geoespaciales" not in tablas:
                return {
                    "error": "Tablas esfuerzo_satelital o vedas_geoespaciales no disponibles. "
                    "Ejecutar --step conae y --step geovisor primero."
                }

            # Esfuerzo GFW durante veda activa para la misma especie
            rows_dentro = conn.execute(
                """
                SELECT es.esfuerzo_gfw
                FROM esfuerzo_satelital es
                INNER JOIN vedas_geoespaciales vg
                    ON es.especie_code = vg.especie_code
                   AND es.fecha >= COALESCE(vg.fecha_inicio, '1900-01-01')
                   AND es.fecha <= COALESCE(vg.fecha_fin, '2099-12-31')
                WHERE es.esfuerzo_gfw IS NOT NULL
                """
            ).fetchall()

            # Esfuerzo GFW fuera de cualquier veda activa para la especie
            rows_fuera = conn.execute(
                """
                SELECT es.esfuerzo_gfw
                FROM esfuerzo_satelital es
                WHERE es.esfuerzo_gfw IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1 FROM vedas_geoespaciales vg
                      WHERE es.especie_code = vg.especie_code
                        AND es.fecha >= COALESCE(vg.fecha_inicio, '1900-01-01')
                        AND es.fecha <= COALESCE(vg.fecha_fin, '2099-12-31')
                  )
                """
            ).fetchall()

        dentro = [r[0] for r in rows_dentro]
        fuera = [r[0] for r in rows_fuera]

        if not dentro and not fuera:
            return {"error": "Sin datos de esfuerzo GFW. Ejecutar --step conae para muestrear."}

        def _mediana(vals: list[float]) -> float | None:
            if not vals:
                return None
            s = sorted(vals)
            n = len(s)
            return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2

        med_dentro = _mediana(dentro)
        med_fuera = _mediana(fuera)

        ratio = None
        if med_dentro is not None and med_fuera and med_fuera > 0:
            ratio = round(med_dentro / med_fuera, 3)

        pvalue = None
        try:
            from scipy.stats import mannwhitneyu

            if len(dentro) >= 3 and len(fuera) >= 3:
                _, pvalue = mannwhitneyu(dentro, fuera, alternative="less")
                pvalue = round(float(pvalue), 4)
        except ImportError:
            pass

        if ratio is None:
            interpretacion = "Datos insuficientes para comparar esfuerzo dentro/fuera de veda."
        elif ratio < 0.7:
            interpretacion = (
                f"El esfuerzo GFW dentro de vedas ({med_dentro:.2f}) es {(1 - ratio) * 100:.0f}% "
                f"menor que fuera de vedas ({med_fuera:.2f}) — consistente con cumplimiento."
            )
        elif ratio > 1.1:
            interpretacion = (
                f"El esfuerzo GFW dentro de vedas ({med_dentro:.2f}) es mayor que fuera "
                f"({med_fuera:.2f}) — posible incumplimiento satelitalmente documentado."
            )
        else:
            interpretacion = (
                f"Sin diferencia significativa en esfuerzo GFW dentro ({med_dentro:.2f}) "
                f"vs. fuera de vedas ({med_fuera:.2f})."
            )

        if pvalue is not None:
            interpretacion += f" Mann-Whitney U p={pvalue}."

        logger.info(f"validar_cumplimiento_satelital: {interpretacion}")
        return {
            "n_dentro_veda": len(dentro),
            "n_fuera_veda": len(fuera),
            "mediana_esfuerzo_dentro": med_dentro,
            "mediana_esfuerzo_fuera": med_fuera,
            "ratio_reduccion": ratio,
            "mannwhitney_pvalue": pvalue,
            "interpretacion": interpretacion,
        }
