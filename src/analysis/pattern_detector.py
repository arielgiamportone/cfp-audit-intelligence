"""
Detector de patrones estadísticos en las resoluciones del CFP.

Analiza:
  - Frecuencia de beneficiarios por empresa/actor
  - Evolución temporal de cuotas por especie
  - Distribución de tipos de resolución
  - Anomalías en patrones de votación
  - Concentración de beneficios (índice HHI)
  - Correlación entre composición del CFP y decisiones
"""
import json
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import pandas as pd
from loguru import logger


class PatternDetector:
    """Detecta patrones estadísticos en el corpus de resoluciones del CFP."""

    def __init__(self, db_path: Path | str = "data/processed/catalog.db"):
        self.db_path = Path(db_path)

    def _query(self, sql: str, params: tuple = ()) -> pd.DataFrame:
        with sqlite3.connect(self.db_path) as conn:
            return pd.read_sql_query(sql, conn, params=params)

    # ── Análisis de cuotas ────────────────────────────────────────────────

    def quota_evolution(self, especie: str) -> pd.DataFrame:
        """Evolución de cuotas (toneladas) por año para una especie."""
        df = self._query(
            """
            SELECT r.year AS anio, r.numero, r.tipo,
                   json_extract(r.texto_completo, '$') as texto
            FROM resoluciones r
            JOIN actas a ON r.acta_id = a.id
            WHERE r.tipo = 'cuota_captura'
              AND r.texto_completo LIKE ?
            ORDER BY r.year
            """,
            (f"%{especie}%",),
        )
        return df

    # ── Análisis de beneficiarios ─────────────────────────────────────────

    def top_beneficiaries(self, limit: int = 20) -> pd.DataFrame:
        """Empresas/actores más frecuentemente mencionados como beneficiarios."""
        return self._query(
            """
            SELECT e.nombre, e.tipo, COUNT(m.id) as menciones,
                   COUNT(DISTINCT r.acta_id) as actas_distintas,
                   MIN(a.year) as primer_anio,
                   MAX(a.year) as ultimo_anio
            FROM menciones m
            JOIN entidades e ON m.entidad_id = e.id
            JOIN resoluciones r ON m.resolucion_id = r.id
            JOIN actas a ON r.acta_id = a.id
            WHERE e.tipo = 'empresa'
            GROUP BY e.id
            ORDER BY menciones DESC
            LIMIT ?
            """,
            (limit,),
        )

    def hhi_concentration(self) -> dict[str, float]:
        """
        Índice de Herfindahl-Hirschman de concentración de menciones por empresa.
        HHI > 2500 indica alta concentración (potencial captura regulatoria).
        """
        df = self.top_beneficiaries(limit=100)
        if df.empty:
            return {"hhi": 0, "interpretation": "sin datos"}

        total = df["menciones"].sum()
        shares = df["menciones"] / total
        hhi = (shares ** 2).sum() * 10000

        return {
            "hhi": round(float(hhi), 2),
            "interpretation": (
                "Alta concentración (>2500): posible captura regulatoria"
                if hhi > 2500
                else "Concentración moderada (1000-2500): observar tendencia"
                if hhi > 1000
                else "Baja concentración (<1000): mercado diversificado"
            ),
            "empresas_analizadas": len(df),
        }

    # ── Análisis de votaciones ────────────────────────────────────────────

    def voting_patterns(self) -> dict[str, Any]:
        """Analiza patrones de votación: unanimidad, quórum mínimo, abstenciones."""
        df = self._query(
            """
            SELECT r.year, r.tipo, r.votos_favor, r.votos_contra,
                   r.abstenciones, r.quorum,
                   a.year as acta_year
            FROM resoluciones r
            JOIN actas a ON r.acta_id = a.id
            WHERE r.votos_favor IS NOT NULL
            """
        )

        if df.empty:
            return {"error": "No hay datos de votaciones"}

        total = len(df)
        unanimous = (df["votos_contra"].fillna(0) == 0) & (df["abstenciones"].fillna(0) == 0)
        with_dissent = df["votos_contra"].fillna(0) > 0

        return {
            "total_resoluciones_con_datos": total,
            "unanimes": int(unanimous.sum()),
            "pct_unanimes": round(float(unanimous.mean() * 100), 1),
            "con_voto_negativo": int(with_dissent.sum()),
            "pct_con_disidencia": round(float(with_dissent.mean() * 100), 1),
            "abstenciones_registradas": int((df["abstenciones"].fillna(0) > 0).sum()),
            "por_tipo": df.groupby("tipo")["votos_favor"].count().to_dict(),
        }

    # ── Análisis temporal ─────────────────────────────────────────────────

    def resolution_timeline(self) -> pd.DataFrame:
        """Serie temporal de resoluciones por año y tipo."""
        return self._query(
            """
            SELECT a.year, r.tipo, COUNT(*) as cantidad,
                   AVG(r.riesgo_score) as riesgo_promedio
            FROM resoluciones r
            JOIN actas a ON r.acta_id = a.id
            GROUP BY a.year, r.tipo
            ORDER BY a.year
            """
        )

    def risk_evolution(self) -> pd.DataFrame:
        """Evolución del score de riesgo promedio por año."""
        return self._query(
            """
            SELECT a.year, AVG(r.riesgo_score) as riesgo_promedio,
                   MAX(r.riesgo_score) as riesgo_maximo,
                   COUNT(*) as resoluciones
            FROM resoluciones r
            JOIN actas a ON r.acta_id = a.id
            WHERE r.riesgo_score IS NOT NULL
            GROUP BY a.year
            ORDER BY a.year
            """
        )

    # ── Detección de anomalías ────────────────────────────────────────────

    def high_risk_resolutions(self, threshold: float = 70.0) -> pd.DataFrame:
        """Resoluciones con score de riesgo superior al umbral."""
        return self._query(
            """
            SELECT r.id, a.year, r.numero, r.tipo, r.riesgo_score,
                   substr(r.texto_completo, 1, 300) as texto_preview,
                   r.analisis_ia
            FROM resoluciones r
            JOIN actas a ON r.acta_id = a.id
            WHERE r.riesgo_score >= ?
            ORDER BY r.riesgo_score DESC
            """,
            (threshold,),
        )

    def reversals_detection(self) -> list[dict]:
        """
        Detecta reversiones: resoluciones que contradicen vedas o restricciones previas.
        Heurística: resolución tipo 'cuota_captura' en especie que tuvo 'veda' el año anterior.
        """
        vedas = self._query(
            """
            SELECT a.year, m.entidad_id, e.nombre as especie
            FROM resoluciones r
            JOIN actas a ON r.acta_id = a.id
            JOIN menciones m ON m.resolucion_id = r.id
            JOIN entidades e ON e.id = m.entidad_id
            WHERE r.tipo = 'veda' AND e.tipo = 'especie'
            """
        )

        cuotas = self._query(
            """
            SELECT a.year, m.entidad_id, e.nombre as especie
            FROM resoluciones r
            JOIN actas a ON r.acta_id = a.id
            JOIN menciones m ON m.resolucion_id = r.id
            JOIN entidades e ON e.id = m.entidad_id
            WHERE r.tipo = 'cuota_captura' AND e.tipo = 'especie'
            """
        )

        if vedas.empty or cuotas.empty:
            return []

        reversals = []
        for _, veda_row in vedas.iterrows():
            # Buscar cuota otorgada en el año siguiente o el mismo año
            same_species_cuota = cuotas[
                (cuotas["entidad_id"] == veda_row["entidad_id"])
                & (cuotas["year"] >= veda_row["year"])
                & (cuotas["year"] <= veda_row["year"] + 2)
            ]
            if not same_species_cuota.empty:
                reversals.append({
                    "especie": veda_row["especie"],
                    "anio_veda": int(veda_row["year"]),
                    "anio_cuota_posterior": int(same_species_cuota["year"].min()),
                    "alerta": (
                        "Cuota otorgada poco después de una veda. "
                        "Requiere verificación de justificación técnica."
                    ),
                })

        return reversals

    # ── Reporte integral ──────────────────────────────────────────────────

    def full_report(self) -> dict[str, Any]:
        """Genera reporte completo de patrones detectados."""
        logger.info("Generando reporte de patrones...")
        return {
            "concentracion_beneficiarios": self.hhi_concentration(),
            "patrones_votacion": self.voting_patterns(),
            "reversiones_detectadas": self.reversals_detection(),
            "resoluciones_alto_riesgo": (
                self.high_risk_resolutions()
                .head(10)
                .to_dict(orient="records")
            ),
            "timeline_resolucion": (
                self.resolution_timeline()
                .to_dict(orient="records")
            ),
        }
