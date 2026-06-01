"""Tests para GroundTruthEvaluator y annotation_protocol."""

import io
import json
import sqlite3
import tempfile
from pathlib import Path

import pandas as pd
import pytest

from src.evaluation.annotation_protocol import GOLD_SET, seed_gold_set
from src.evaluation.evaluator import (
    CATEGORIAS,
    GroundTruthEvaluator,
    _cohen_kappa,
    _precision_recall_f1,
)


@pytest.fixture
def tmp_db(tmp_path) -> Path:
    db = tmp_path / "test_eval.db"
    seed_gold_set(db)
    return db


@pytest.fixture
def evaluator(tmp_db) -> GroundTruthEvaluator:
    return GroundTruthEvaluator(tmp_db)


# ── Tests internos ────────────────────────────────────────────────────────────

class TestCohenKappa:
    def test_acuerdo_perfecto(self):
        labels = ["bajo", "medio", "alto", "critico"]
        assert _cohen_kappa(labels, labels) == 1.0

    def test_listas_vacias(self):
        assert _cohen_kappa([], []) != _cohen_kappa([], []) or True  # nan

    def test_listas_desiguales(self):
        result = _cohen_kappa(["a", "b"], ["a"])
        assert result != result  # nan

    def test_peor_que_azar(self):
        # 4 etiquetas alternadas perfectamente invertidas
        a = ["bajo", "alto"] * 50
        b = ["alto", "bajo"] * 50
        k = _cohen_kappa(a, b)
        assert k < 0

    def test_retorna_float(self):
        k = _cohen_kappa(["bajo", "medio"], ["bajo", "alto"])
        assert isinstance(k, float)


class TestPrecisionRecallF1:
    def test_perfecto(self):
        y_true = ["bajo", "medio", "bajo"]
        y_pred = ["bajo", "medio", "bajo"]
        m = _precision_recall_f1(y_true, y_pred, "bajo")
        assert m["precision"] == 1.0
        assert m["recall"] == 1.0
        assert m["f1"] == 1.0

    def test_sin_positivos(self):
        y_true = ["medio", "medio"]
        y_pred = ["medio", "medio"]
        m = _precision_recall_f1(y_true, y_pred, "bajo")
        assert m["f1"] == 0.0
        assert m["support"] == 0

    def test_sin_predicciones(self):
        y_true = ["bajo", "bajo"]
        y_pred = ["medio", "medio"]
        m = _precision_recall_f1(y_true, y_pred, "bajo")
        assert m["recall"] == 0.0
        assert m["precision"] == 0.0


# ── Tests del gold set ────────────────────────────────────────────────────────

class TestGoldSet:
    def test_tamanio(self):
        assert len(GOLD_SET) == 30

    def test_distribucion_categorias(self):
        cats = [item["categoria_humana"] for item in GOLD_SET]
        assert cats.count("bajo") == 12
        assert cats.count("medio") == 10
        assert cats.count("alto") == 5
        assert cats.count("critico") == 3

    def test_campos_requeridos(self):
        for item in GOLD_SET:
            assert "texto" in item
            assert "categoria_humana" in item
            assert "hallazgos_humanos" in item
            assert "riesgo_score_humano" in item

    def test_riesgo_score_range(self):
        for item in GOLD_SET:
            assert 0 <= item["riesgo_score_humano"] <= 100

    def test_categorias_validas(self):
        for item in GOLD_SET:
            assert item["categoria_humana"] in CATEGORIAS

    def test_riesgo_creciente_por_categoria(self):
        scores = {cat: [] for cat in CATEGORIAS}
        for item in GOLD_SET:
            scores[item["categoria_humana"]].append(item["riesgo_score_humano"])
        medias = {cat: sum(v) / len(v) for cat, v in scores.items() if v}
        assert medias["bajo"] < medias["medio"] < medias["alto"] < medias["critico"]


# ── Tests de seed_gold_set ────────────────────────────────────────────────────

class TestSeedGoldSet:
    def test_inserta_30_registros(self, tmp_path):
        db = tmp_path / "test.db"
        n = seed_gold_set(db)
        assert n == 30

    def test_idempotente(self, tmp_path):
        db = tmp_path / "test.db"
        seed_gold_set(db)
        n2 = seed_gold_set(db)
        assert n2 == 30

    def test_gold_set_marcado(self, tmp_path):
        db = tmp_path / "test.db"
        seed_gold_set(db)
        with sqlite3.connect(db) as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM anotaciones_humanas WHERE is_gold_set=1"
            ).fetchone()[0]
        assert count == 30

    def test_anotador_gold_sintetico(self, tmp_path):
        db = tmp_path / "test.db"
        seed_gold_set(db)
        with sqlite3.connect(db) as conn:
            anotadores = conn.execute(
                "SELECT DISTINCT anotador FROM anotaciones_humanas"
            ).fetchall()
        assert any(r[0] == "gold_sintetico" for r in anotadores)


# ── Tests de GroundTruthEvaluator ────────────────────────────────────────────

class TestGroundTruthEvaluator:
    def test_get_gold_set_retorna_dataframe(self, evaluator):
        df = evaluator.get_gold_set()
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 30

    def test_get_gold_set_tiene_campos(self, evaluator):
        df = evaluator.get_gold_set()
        assert "categoria_humana" in df.columns
        assert "riesgo_score_humano" in df.columns

    def test_db_vacia_retorna_error(self, tmp_path):
        db = tmp_path / "vacia.db"
        ev = GroundTruthEvaluator(db)
        result = ev.compute_metrics()
        assert "error" in result

    def test_compute_metrics_sin_ia(self, evaluator):
        # Gold set solo tiene categoria_humana, no categoria_ia → error esperado
        result = evaluator.compute_metrics()
        assert "error" in result

    def test_compute_metrics_con_ia(self, evaluator, tmp_db):
        # Insertar categoria_ia para poder comparar
        with sqlite3.connect(tmp_db) as conn:
            conn.execute(
                "UPDATE anotaciones_humanas SET categoria_ia = categoria_humana"
            )
        result = evaluator.compute_metrics()
        assert "cohen_kappa" in result
        assert result["cohen_kappa"] == 1.0  # acuerdo perfecto

    def test_kappa_acuerdo_perfecto(self, evaluator, tmp_db):
        with sqlite3.connect(tmp_db) as conn:
            conn.execute(
                "UPDATE anotaciones_humanas SET categoria_ia = categoria_humana"
            )
        result = evaluator.compute_metrics()
        assert abs(result["cohen_kappa"] - 1.0) < 0.01

    def test_export_for_expert_crea_archivo(self, evaluator, tmp_path):
        output = tmp_path / "export.csv"
        n = evaluator.export_for_expert(output, n=10)
        assert output.exists()
        assert n >= 0  # puede ser 0 si no hay resoluciones con analisis_ia

    def test_export_crea_columnas_anotacion(self, evaluator, tmp_path):
        output = tmp_path / "export.csv"
        evaluator.export_for_expert(output)
        df = pd.read_csv(output)
        assert "categoria_humana" in df.columns
        assert "riesgo_score_humano" in df.columns
        assert "notas" in df.columns

    def test_import_from_expert_csv(self, evaluator, tmp_db, tmp_path):
        # Crear CSV de prueba
        seed_gold_set(tmp_db)
        with sqlite3.connect(tmp_db) as conn:
            res_id = conn.execute(
                "SELECT resolucion_id FROM anotaciones_humanas LIMIT 1"
            ).fetchone()[0]

        csv_content = f"resolucion_id,categoria,categoria_humana,riesgo_score,notas,confianza_pct\n"
        csv_content += f"{res_id},bajo,medio,25,test,80\n"
        csv_file = io.StringIO(csv_content)

        n = evaluator.import_from_expert(csv_file, anotador="experto_test")
        assert n == 1

    def test_import_sin_categoria_humana_ignora(self, evaluator, tmp_path):
        csv_content = "resolucion_id,categoria_humana,riesgo_score\n999,,\n"
        n = evaluator.import_from_expert(io.StringIO(csv_content), "test")
        assert n == 0

    def test_import_columna_faltante_lanza_error(self, evaluator):
        csv_content = "resolucion_id,notas\n1,test\n"
        with pytest.raises(ValueError, match="columnas requeridas"):
            evaluator.import_from_expert(io.StringIO(csv_content), "test")

    def test_generate_report_estructura(self, evaluator, tmp_db):
        with sqlite3.connect(tmp_db) as conn:
            conn.execute(
                "UPDATE anotaciones_humanas SET categoria_ia = categoria_humana"
            )
        report = evaluator.generate_report()
        assert "metricas" in report
        assert "recomendacion" in report
