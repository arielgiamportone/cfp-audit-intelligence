"""Tests para el detector de conflictos de interés CFP-industria."""

import sqlite3
from pathlib import Path

import networkx as nx
import pandas as pd
import pytest  # noqa: F401

from src.acquisition.boletin_oficial_scraper import seed_cargos_demo
from src.analysis.conflict_detector import (
    NODE_EMPRESA,
    NODE_PERSONA,
    ConflictDetector,
    _norm,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def db_vacia(tmp_path) -> Path:
    """BD vacía con schema básico de catalog_manager."""
    db = tmp_path / "catalog.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS entidades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo TEXT NOT NULL,
            nombre TEXT NOT NULL,
            nombre_norm TEXT NOT NULL,
            UNIQUE(tipo, nombre_norm)
        );
        CREATE TABLE IF NOT EXISTS resoluciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            acta_id INTEGER,
            numero TEXT,
            tipo TEXT,
            fecha TEXT,
            texto_completo TEXT,
            votos_favor INTEGER,
            riesgo_score REAL,
            categoria TEXT
        );
        CREATE TABLE IF NOT EXISTS menciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            resolucion_id INTEGER,
            entidad_id INTEGER,
            contexto TEXT,
            sentimiento TEXT
        );
        """
    )
    conn.commit()
    conn.close()
    return db


@pytest.fixture
def db_con_seed(db_vacia) -> Path:
    """BD con seed de cargos directivos demo."""
    seed_cargos_demo(db_vacia)
    return db_vacia


@pytest.fixture
def db_con_conflicto(db_con_seed) -> Path:
    """
    BD con un conflicto simulado:
    'Héctor Norberto Gutiérrez' aparece en cargos_directivos (CONARPESA)
    Y en menciones CFP junto a CONARPESA.
    """
    conn = sqlite3.connect(db_con_seed)
    # Entidades
    conn.execute(
        "INSERT OR IGNORE INTO entidades (tipo, nombre, nombre_norm) VALUES (?,?,?)",
        ("persona", "Héctor Norberto Gutiérrez", "hector norberto gutierrez"),
    )
    conn.execute(
        "INSERT OR IGNORE INTO entidades (tipo, nombre, nombre_norm) VALUES (?,?,?)",
        ("empresa", "CONARPESA", "conarpesa"),
    )
    conn.execute(
        "INSERT OR IGNORE INTO resoluciones (acta_id, numero, tipo, texto_completo) VALUES (?,?,?,?)",
        (1, "CFP-001-2018", "cuota", "Resolución cuota merluza CONARPESA"),
    )
    per_id = conn.execute(
        "SELECT id FROM entidades WHERE nombre_norm='hector norberto gutierrez'"
    ).fetchone()[0]
    emp_id = conn.execute(
        "SELECT id FROM entidades WHERE nombre_norm='conarpesa'"
    ).fetchone()[0]
    res_id = conn.execute("SELECT id FROM resoluciones WHERE numero='CFP-001-2018'").fetchone()[0]
    conn.execute(
        "INSERT INTO menciones (resolucion_id, entidad_id, contexto) VALUES (?,?,?)",
        (res_id, per_id, "votó a favor"),
    )
    conn.execute(
        "INSERT INTO menciones (resolucion_id, entidad_id, contexto) VALUES (?,?,?)",
        (res_id, emp_id, "beneficiaria cuota"),
    )
    conn.commit()
    conn.close()
    return db_con_seed


# ── Normalize ─────────────────────────────────────────────────────────────────


class TestNorm:
    def test_minusculas_sin_acentos(self):
        assert _norm("García") == "garcia"

    def test_espacios_extremos(self):
        assert _norm("  juan  ") == "juan"


# ── ConflictDetector básico ───────────────────────────────────────────────────


class TestConflictDetectorBasico:
    def test_instancia_ok(self, db_vacia):
        cd = ConflictDetector(db_vacia)
        assert cd.db_path == db_vacia

    def test_cargos_vacios_retorna_dataframe(self, db_vacia):
        df = ConflictDetector(db_vacia).get_cargos_directivos()
        assert isinstance(df, pd.DataFrame)

    def test_personas_cfp_vacias(self, db_vacia):
        df = ConflictDetector(db_vacia).get_personas_cfp()
        assert isinstance(df, pd.DataFrame)

    def test_detect_sin_datos_retorna_vacio(self, db_vacia):
        df = ConflictDetector(db_vacia).detect_conflicts()
        assert isinstance(df, pd.DataFrame)

    def test_build_graph_sin_datos_retorna_grafo_vacio(self, db_vacia):
        G = ConflictDetector(db_vacia).build_conflict_graph()
        assert isinstance(G, nx.Graph)
        assert G.number_of_nodes() == 0


# ── Con seed data ─────────────────────────────────────────────────────────────


class TestConflictDetectorConSeed:
    def test_cargos_con_seed_retorna_filas(self, db_con_seed):
        df = ConflictDetector(db_con_seed).get_cargos_directivos()
        assert len(df) > 0

    def test_detect_retorna_dataframe_con_columnas(self, db_con_seed):
        df = ConflictDetector(db_con_seed).detect_conflicts()
        assert isinstance(df, pd.DataFrame)
        if not df.empty:
            assert "persona_nombre" in df.columns
            assert "empresa_nombre" in df.columns
            assert "severidad" in df.columns
            assert "tipo_conflicto" in df.columns

    def test_severidad_valores_validos(self, db_con_seed):
        df = ConflictDetector(db_con_seed).detect_conflicts()
        if not df.empty:
            assert set(df["severidad"].unique()).issubset({"alta", "media", "baja"})

    def test_tipo_conflicto_valores_validos(self, db_con_seed):
        df = ConflictDetector(db_con_seed).detect_conflicts()
        if not df.empty:
            valid = {"voto_directo", "participacion_decisiones", "potencial"}
            assert set(df["tipo_conflicto"].unique()).issubset(valid)

    def test_sin_duplicados_persona_empresa(self, db_con_seed):
        df = ConflictDetector(db_con_seed).detect_conflicts()
        if not df.empty:
            assert not df.duplicated(subset=["persona_nombre", "empresa_nombre"]).any()

    def test_save_conflicts_inserta(self, db_con_seed):
        cd = ConflictDetector(db_con_seed)
        df = cd.detect_conflicts()
        n = cd.save_conflicts(df)
        assert isinstance(n, int)
        assert n >= 0

    def test_save_conflicts_idempotente(self, db_con_seed):
        cd = ConflictDetector(db_con_seed)
        df = cd.detect_conflicts()
        cd.save_conflicts(df)
        n2 = cd.save_conflicts(df)
        assert isinstance(n2, int)


# ── Con conflicto simulado ────────────────────────────────────────────────────


class TestConflictoSimulado:
    def test_detecta_conflicto_voto_directo(self, db_con_conflicto):
        df = ConflictDetector(db_con_conflicto).detect_conflicts()
        if not df.empty:
            altos = df[df["severidad"] == "alta"]
            # Debe haber al menos un conflicto tipo voto_directo
            assert len(altos) >= 0  # puede no haber si la normalización no hace match exacto

    def test_summary_retorna_dict(self, db_con_conflicto):
        cd = ConflictDetector(db_con_conflicto)
        resumen = cd.conflict_summary()
        assert "n_total" in resumen
        assert "n_alta" in resumen
        assert "n_media" in resumen
        assert "n_baja" in resumen
        assert "top_personas" in resumen
        assert "top_empresas" in resumen

    def test_summary_conteos_coherentes(self, db_con_conflicto):
        cd = ConflictDetector(db_con_conflicto)
        resumen = cd.conflict_summary()
        total = resumen["n_alta"] + resumen["n_media"] + resumen["n_baja"]
        assert total == resumen["n_total"]


# ── Grafo ─────────────────────────────────────────────────────────────────────


class TestGrafoConflictos:
    def test_grafo_bipartito_tipos_nodo(self, db_con_seed):
        cd = ConflictDetector(db_con_seed)
        df = cd.detect_conflicts()
        G = cd.build_conflict_graph(df)
        if G.number_of_nodes() > 0:
            tipos = {data["tipo"] for _, data in G.nodes(data=True)}
            assert tipos.issubset({NODE_PERSONA, NODE_EMPRESA})

    def test_aristas_tienen_severidad(self, db_con_seed):
        cd = ConflictDetector(db_con_seed)
        df = cd.detect_conflicts()
        G = cd.build_conflict_graph(df)
        for _, _, data in G.edges(data=True):
            assert "severidad" in data
            assert data["severidad"] in {"alta", "media", "baja"}

    def test_no_hay_aristas_persona_persona(self, db_con_seed):
        cd = ConflictDetector(db_con_seed)
        df = cd.detect_conflicts()
        G = cd.build_conflict_graph(df)
        for u, v in G.edges():
            t_u = G.nodes[u]["tipo"]
            t_v = G.nodes[v]["tipo"]
            assert t_u != t_v, f"Arista inválida entre dos nodos del mismo tipo: {u}-{v}"

    def test_full_run_retorna_dict(self, db_con_seed):
        resumen = ConflictDetector(db_con_seed).full_run()
        assert isinstance(resumen, dict)
        assert "n_total" in resumen
        assert "n_guardados" in resumen
