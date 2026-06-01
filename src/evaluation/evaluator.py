"""
GroundTruthEvaluator — framework de evaluación del audit_engine contra anotaciones humanas.

Responde a la crítica central: "nadie sabe si el sistema alucina o acierta".
Sin este benchmark, los hallazgos valen tanto como una opinión bien presentada.

Metodología:
  1. Gold set de 30+ resoluciones con etiquetas asignadas por experto(s)
  2. Métricas P/R/F1 por categoría (bajo/medio/alto/critico)
  3. Cohen's kappa inter-rater para medir acuerdo más allá del azar
  4. Export/Import CSV para que el experto trabaje offline

Referencias:
  Cohen, J. (1960). A coefficient of agreement for nominal scales.
    Educational and Psychological Measurement, 20(1), 37-46.
  Artstein, R. & Poesio, M. (2008). Inter-Coder Agreement for Computational Linguistics.
    Computational Linguistics, 34(4), 555-596.
"""

from __future__ import annotations

import csv
import io
import sqlite3
from pathlib import Path
from typing import Any

import pandas as pd
from loguru import logger

CATEGORIAS = ["bajo", "medio", "alto", "critico"]


def _cohen_kappa(labels_a: list[str], labels_b: list[str]) -> float:
    """Calcula Cohen's kappa entre dos listas de etiquetas."""
    if len(labels_a) != len(labels_b) or not labels_a:
        return float("nan")

    cats = sorted(set(labels_a) | set(labels_b))
    n = len(labels_a)
    observed_agree = sum(a == b for a, b in zip(labels_a, labels_b, strict=False)) / n

    counts_a = {c: labels_a.count(c) for c in cats}
    counts_b = {c: labels_b.count(c) for c in cats}
    expected = sum(counts_a.get(c, 0) * counts_b.get(c, 0) for c in cats) / (n * n)

    if expected >= 1.0:
        return 1.0
    return round((observed_agree - expected) / (1 - expected), 4)


def _precision_recall_f1(
    y_true: list[str], y_pred: list[str], categoria: str
) -> dict[str, float]:
    tp = sum(t == categoria and p == categoria for t, p in zip(y_true, y_pred, strict=False))
    fp = sum(t != categoria and p == categoria for t, p in zip(y_true, y_pred, strict=False))
    fn = sum(t == categoria and p != categoria for t, p in zip(y_true, y_pred, strict=False))
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (
        2 * precision * recall / (precision + recall)
        if (precision + recall) > 0
        else 0.0
    )
    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "support": tp + fn,
    }


class GroundTruthEvaluator:
    """Evalúa el sistema de auditoría contra anotaciones humanas."""

    def __init__(self, db_path: Path | str = "data/processed/catalog.db"):
        self.db_path = Path(db_path)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def get_gold_set(self) -> pd.DataFrame:
        """Retorna el gold set (is_gold_set=TRUE) como DataFrame."""
        with self._conn() as conn:
            try:
                return pd.read_sql_query(
                    """
                    SELECT a.*, r.texto_completo, r.categoria as categoria_pipeline,
                           r.riesgo_score as riesgo_score_pipeline
                    FROM anotaciones_humanas a
                    LEFT JOIN resoluciones r ON r.id = a.resolucion_id
                    WHERE a.is_gold_set = 1
                    ORDER BY a.id
                    """,
                    conn,
                )
            except Exception as exc:
                logger.warning(f"Gold set no disponible: {exc}")
                return pd.DataFrame()

    def get_all_annotations(self, anotador: str | None = None) -> pd.DataFrame:
        """Retorna todas las anotaciones, opcionalmente filtradas por anotador."""
        where = "WHERE a.anotador = ?" if anotador else ""
        params = (anotador,) if anotador else ()
        with self._conn() as conn:
            try:
                return pd.read_sql_query(
                    f"""
                    SELECT a.*, r.texto_completo, r.riesgo_score as riesgo_score_pipeline
                    FROM anotaciones_humanas a
                    LEFT JOIN resoluciones r ON r.id = a.resolucion_id
                    {where}
                    ORDER BY a.id
                    """,
                    conn,
                    params=params,
                )
            except Exception as exc:
                logger.warning(f"Error cargando anotaciones: {exc}")
                return pd.DataFrame()

    def compute_metrics(self) -> dict[str, Any]:
        """
        Calcula métricas de evaluación sobre pares (categoria_ia, categoria_humana).

        Requiere al menos algunas anotaciones con ambos campos no nulos.

        Returns:
            Dict con: kappa, precision/recall/F1 por categoría, accuracy, n_pares.
        """
        df = self.get_all_annotations()
        if df.empty:
            return {"error": "Sin anotaciones disponibles"}

        paired = df.dropna(subset=["categoria_ia", "categoria_humana"])
        if paired.empty:
            return {"error": "Sin pares (categoria_ia, categoria_humana) completos"}

        y_ia = paired["categoria_ia"].str.lower().tolist()
        y_hum = paired["categoria_humana"].str.lower().tolist()

        kappa = _cohen_kappa(y_ia, y_hum)
        accuracy = sum(a == b for a, b in zip(y_ia, y_hum, strict=False)) / len(y_ia)

        metricas_por_cat = {
            cat: _precision_recall_f1(y_hum, y_ia, cat) for cat in CATEGORIAS
        }

        macro_f1 = sum(m["f1"] for m in metricas_por_cat.values()) / len(CATEGORIAS)

        return {
            "n_pares": len(paired),
            "n_anotadores": paired["anotador"].nunique(),
            "accuracy": round(accuracy, 4),
            "cohen_kappa": kappa,
            "kappa_interpretacion": _interpretar_kappa(kappa),
            "macro_f1": round(macro_f1, 4),
            "por_categoria": metricas_por_cat,
            "distribucion_ia": pd.Series(y_ia).value_counts().to_dict(),
            "distribucion_humana": pd.Series(y_hum).value_counts().to_dict(),
        }

    def export_for_expert(self, output_path: Path, n: int = 30) -> int:
        """
        Exporta resoluciones para anotación offline.

        Selecciona `n` resoluciones priorizando las que el sistema marcó
        como de alto/crítico riesgo (las más importantes de validar).

        Returns:
            Número de filas exportadas.
        """
        with self._conn() as conn:
            try:
                df = pd.read_sql_query(
                    f"""
                    SELECT r.id as resolucion_id, r.numero, r.tipo, r.fecha,
                           r.riesgo_score, r.categoria, r.analisis_ia,
                           substr(r.texto_completo, 1, 1000) as texto_preview,
                           a.year as acta_year
                    FROM resoluciones r
                    JOIN actas a ON r.acta_id = a.id
                    WHERE r.analisis_ia IS NOT NULL
                    ORDER BY r.riesgo_score DESC NULLS LAST
                    LIMIT {n}
                    """,
                    conn,
                )
            except Exception:
                df = pd.DataFrame()

        if df.empty:
            df = pd.DataFrame(
                columns=[
                    "resolucion_id", "numero", "tipo", "fecha", "riesgo_score",
                    "categoria", "texto_preview", "acta_year",
                    "categoria_humana", "riesgo_score_humano", "notas", "confianza_pct",
                ]
            )

        df["categoria_humana"] = ""
        df["riesgo_score_humano"] = ""
        df["notas"] = ""
        df["confianza_pct"] = ""

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(output_path, index=False, quoting=csv.QUOTE_ALL)
        logger.info(f"Exportadas {len(df)} resoluciones para anotación: {output_path}")
        return len(df)

    def import_from_expert(
        self,
        csv_path: Path | str | io.IOBase,
        anotador: str,
    ) -> int:
        """
        Importa CSV de anotación experta a la tabla anotaciones_humanas.

        El CSV debe tener columnas: resolucion_id, categoria_humana,
        riesgo_score_humano, notas, confianza_pct.

        Returns:
            Número de filas importadas.
        """
        if isinstance(csv_path, (str, Path)):
            df = pd.read_csv(csv_path, dtype=str)
        else:
            df = pd.read_csv(csv_path, dtype=str)

        required = {"resolucion_id", "categoria_humana"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"CSV falta columnas requeridas: {missing}")

        df = df[df["categoria_humana"].notna() & (df["categoria_humana"] != "")]
        if df.empty:
            logger.warning("CSV importado no tiene categorías humanas completadas")
            return 0

        with sqlite3.connect(self.db_path) as conn:
            count = 0
            for _, row in df.iterrows():
                try:
                    conn.execute(
                        """
                        INSERT INTO anotaciones_humanas
                            (resolucion_id, anotador, categoria_ia, categoria_humana,
                             riesgo_score_ia, riesgo_score_humano, notas, confianza_pct)
                        VALUES (?,?,?,?,?,?,?,?)
                        ON CONFLICT(resolucion_id, anotador) DO UPDATE SET
                            categoria_humana=excluded.categoria_humana,
                            riesgo_score_humano=excluded.riesgo_score_humano,
                            notas=excluded.notas,
                            confianza_pct=excluded.confianza_pct,
                            timestamp=datetime('now')
                        """,
                        (
                            int(row["resolucion_id"]),
                            anotador,
                            row.get("categoria"),
                            row["categoria_humana"].lower().strip(),
                            float(row["riesgo_score"]) if row.get("riesgo_score") else None,
                            int(row["riesgo_score_humano"]) if row.get("riesgo_score_humano") else None,
                            row.get("notas"),
                            int(row["confianza_pct"]) if row.get("confianza_pct") else None,
                        ),
                    )
                    count += 1
                except Exception as exc:
                    logger.warning(f"Error importando fila {row.get('resolucion_id')}: {exc}")
            conn.commit()

        logger.info(f"Importadas {count} anotaciones de '{anotador}'")
        return count

    def generate_report(self) -> dict[str, Any]:
        """Reporte completo: métricas + ejemplos de acuerdos/desacuerdos."""
        metrics = self.compute_metrics()
        if "error" in metrics:
            return metrics

        df = self.get_all_annotations()
        paired = df.dropna(subset=["categoria_ia", "categoria_humana"])

        acuerdos = paired[
            paired["categoria_ia"].str.lower() == paired["categoria_humana"].str.lower()
        ].head(3)
        desacuerdos = paired[
            paired["categoria_ia"].str.lower() != paired["categoria_humana"].str.lower()
        ].head(3)

        return {
            "metricas": metrics,
            "ejemplos_acuerdo": acuerdos[
                ["resolucion_id", "categoria_ia", "categoria_humana", "notas"]
            ].to_dict("records"),
            "ejemplos_desacuerdo": desacuerdos[
                ["resolucion_id", "categoria_ia", "categoria_humana", "notas"]
            ].to_dict("records"),
            "recomendacion": _recomendar(metrics.get("cohen_kappa", float("nan"))),
        }


def _interpretar_kappa(kappa: float) -> str:
    if kappa != kappa:  # nan
        return "No calculable (datos insuficientes)"
    if kappa < 0:
        return "Peor que el azar — revisar protocolo de anotación"
    if kappa < 0.2:
        return "Acuerdo leve (< 0.20) — anotaciones inconsistentes"
    if kappa < 0.4:
        return "Acuerdo moderado (0.20–0.40)"
    if kappa < 0.6:
        return "Acuerdo moderado-alto (0.40–0.60)"
    if kappa < 0.8:
        return "Acuerdo sustancial (0.60–0.80) — publicable"
    return "Acuerdo casi perfecto (> 0.80) — resultado robusto"


def _recomendar(kappa: float) -> str:
    if kappa != kappa:
        return "Completar anotaciones humanas antes de publicar"
    if kappa < 0.4:
        return "Revisar y reconciliar criterios de anotación con el experto"
    if kappa < 0.6:
        return "Resultados publicables con caveat; ampliar muestra a 50+ resoluciones"
    return "Sistema validado; documentar métricas en la sección de metodología"
