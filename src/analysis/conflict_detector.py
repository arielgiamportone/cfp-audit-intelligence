"""
Detector de conflictos de interés CFP — industria pesquera.

Cruza la tabla cargos_directivos (directores de empresas) con las menciones
de personas en resoluciones del CFP para detectar casos donde un miembro o
asesor del CFP también tiene vinculación directiva con empresas beneficiarias.

Produce:
- tabla conflictos_detectados (BD)
- grafo NetworkX bipartito persona ↔ empresa
- reporte estadístico con severidad
"""

from __future__ import annotations

import sqlite3
import unicodedata
from pathlib import Path

import networkx as nx
import pandas as pd
from loguru import logger

# Severidad del conflicto por tipo
_SEVERIDAD = {
    "voto_directo": "alta",         # votó cuotas de empresa que dirige
    "participacion_decisiones": "media",  # aparece en actas con empresa vinculada
    "potencial": "baja",            # comparte empresa pero sin actas cruzadas
}

NODE_PERSONA = "persona"
NODE_EMPRESA = "empresa"
NODE_COLORS = {
    NODE_PERSONA: "#7B1FA2",  # violeta
    NODE_EMPRESA: "#E65100",  # naranja (consistente con graph_builder)
}


def _norm(texto: str) -> str:
    t = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn").strip()


class ConflictDetector:
    """Detecta conflictos de interés entre miembros CFP y empresas pesqueras."""

    def __init__(self, db_path: Path | str = "data/processed/catalog.db"):
        self.db_path = Path(db_path)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # ── Fuentes de datos ──────────────────────────────────────────────────────

    def get_cargos_directivos(self) -> pd.DataFrame:
        """Retorna todos los cargos directivos registrados."""
        with self._conn() as conn:
            try:
                return pd.read_sql_query(
                    "SELECT * FROM cargos_directivos ORDER BY empresa_nombre, cargo",
                    conn,
                )
            except Exception:
                return pd.DataFrame(
                    columns=[
                        "id", "persona_nombre", "persona_norm", "empresa_nombre",
                        "empresa_norm", "cargo", "desde_year", "hasta_year",
                        "fuente", "verificado",
                    ]
                )

    def get_personas_cfp(self) -> pd.DataFrame:
        """
        Retorna personas que aparecen en menciones de resoluciones CFP.

        Incluye conteo de resoluciones y empresas con las que co-aparecen.
        """
        with self._conn() as conn:
            try:
                return pd.read_sql_query(
                    """
                    SELECT
                        e.nombre           AS persona_nombre,
                        e.nombre_norm      AS persona_norm,
                        COUNT(DISTINCT m.resolucion_id) AS n_resoluciones,
                        COUNT(DISTINCT m2.entidad_id)   AS n_empresas_coaparecen
                    FROM entidades e
                    JOIN menciones m ON e.id = m.entidad_id
                    LEFT JOIN menciones m2
                        ON m2.resolucion_id = m.resolucion_id
                        AND m2.entidad_id != e.id
                    WHERE e.tipo = 'persona'
                    GROUP BY e.id
                    ORDER BY n_resoluciones DESC
                    """,
                    conn,
                )
            except Exception:
                return pd.DataFrame(
                    columns=["persona_nombre", "persona_norm", "n_resoluciones", "n_empresas_coaparecen"]
                )

    def get_empresas_cfp(self) -> pd.DataFrame:
        """Retorna empresas mencionadas en resoluciones CFP."""
        with self._conn() as conn:
            try:
                return pd.read_sql_query(
                    """
                    SELECT
                        e.nombre       AS empresa_nombre,
                        e.nombre_norm  AS empresa_norm,
                        COUNT(DISTINCT m.resolucion_id) AS n_resoluciones
                    FROM entidades e
                    JOIN menciones m ON e.id = m.entidad_id
                    WHERE e.tipo = 'empresa'
                    GROUP BY e.id
                    ORDER BY n_resoluciones DESC
                    """,
                    conn,
                )
            except Exception:
                return pd.DataFrame(
                    columns=["empresa_nombre", "empresa_norm", "n_resoluciones"]
                )

    # ── Detección de conflictos ───────────────────────────────────────────────

    def detect_conflicts(self) -> pd.DataFrame:
        """
        Cruza cargos_directivos con menciones CFP.

        Para cada (persona, empresa) en cargos_directivos:
        - tipo 'voto_directo': persona aparece en resoluciones que mencionan
          la empresa que dirige
        - tipo 'participacion_decisiones': persona en actas donde empresa aparece
        - tipo 'potencial': solo en cargos_directivos, sin cruce en menciones
        """
        cargos = self.get_cargos_directivos()
        if cargos.empty:
            return pd.DataFrame()

        personas_cfp = self.get_personas_cfp()
        empresas_cfp = self.get_empresas_cfp()

        conflictos: list[dict] = []

        for _, cargo in cargos.iterrows():
            persona_norm = cargo["persona_norm"]
            empresa_norm = cargo["empresa_norm"]

            # ¿Aparece esta persona en actas CFP?
            en_cfp = not personas_cfp.empty and persona_norm in personas_cfp["persona_norm"].values

            # ¿Aparece esta empresa en actas CFP?
            empresa_en_cfp = not empresas_cfp.empty and (
                empresa_norm in empresas_cfp["empresa_norm"].values
                or any(empresa_norm in n for n in empresas_cfp["empresa_norm"].values)
            )

            n_res = 0
            tipo = "potencial"

            if en_cfp and empresa_en_cfp:
                # Verificar si co-aparecen en las MISMAS resoluciones
                n_res = _count_coapariciones(
                    cargo["persona_nombre"],
                    cargo["empresa_nombre"],
                    self.db_path,
                )
                tipo = "voto_directo" if n_res > 0 else "participacion_decisiones"
            elif en_cfp:
                tipo = "participacion_decisiones"

            conflictos.append(
                {
                    "persona_nombre": cargo["persona_nombre"],
                    "empresa_nombre": cargo["empresa_nombre"],
                    "cargo": cargo["cargo"],
                    "tipo_conflicto": tipo,
                    "severidad": _SEVERIDAD[tipo],
                    "n_resoluciones": n_res,
                    "fuente_cargo": cargo.get("fuente", ""),
                    "verificado": bool(cargo.get("verificado", False)),
                }
            )

        df = pd.DataFrame(conflictos)
        if df.empty:
            return df

        # Deduplicar: si hay varios cargos en la misma empresa, tomar el de mayor severidad
        sev_order = {"alta": 0, "media": 1, "baja": 2}
        df["_sev_ord"] = df["severidad"].map(sev_order)
        df = (
            df.sort_values("_sev_ord")
            .drop_duplicates(subset=["persona_nombre", "empresa_nombre"])
            .drop(columns=["_sev_ord"])
            .reset_index(drop=True)
        )
        return df

    def save_conflicts(self, conflicts: pd.DataFrame) -> int:
        """Persiste conflictos detectados en la BD. Retorna cantidad insertada."""
        if conflicts.empty:
            return 0
        _ensure_tables(self.db_path)
        conn = sqlite3.connect(self.db_path)
        insertados = 0
        try:
            for _, row in conflicts.iterrows():
                conn.execute(
                    """
                    INSERT OR REPLACE INTO conflictos_detectados
                        (persona_nombre, empresa_nombre, tipo_conflicto, severidad,
                         n_resoluciones, verificado)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row["persona_nombre"],
                        row["empresa_nombre"],
                        row["tipo_conflicto"],
                        row["severidad"],
                        int(row.get("n_resoluciones", 0)),
                        bool(row.get("verificado", False)),
                    ),
                )
                insertados += conn.execute("SELECT changes()").fetchone()[0]
            conn.commit()
        finally:
            conn.close()
        logger.info(f"{insertados} conflictos guardados en {self.db_path}")
        return insertados

    # ── Grafo ─────────────────────────────────────────────────────────────────

    def build_conflict_graph(self, conflicts: pd.DataFrame | None = None) -> nx.Graph:
        """
        Construye grafo bipartito persona ↔ empresa.

        Nodos:
          - persona: violeta, atributo n_resoluciones
          - empresa: naranja (consistente con graph_builder)

        Aristas:
          - peso = n_resoluciones de co-aparición
          - severidad = "alta" | "media" | "baja"
          - tipo_conflicto
        """
        if conflicts is None:
            conflicts = self.detect_conflicts()

        G = nx.Graph()

        if conflicts.empty:
            return G

        cargos = self.get_cargos_directivos()
        personas_cfp = self.get_personas_cfp()

        # Nodos persona
        for persona in conflicts["persona_nombre"].unique():
            n_res = 0
            if not personas_cfp.empty:
                row = personas_cfp[personas_cfp["persona_nombre"] == persona]
                n_res = int(row["n_resoluciones"].iloc[0]) if not row.empty else 0
            G.add_node(
                persona,
                tipo=NODE_PERSONA,
                color=NODE_COLORS[NODE_PERSONA],
                n_resoluciones_cfp=n_res,
            )

        # Nodos empresa
        for empresa in conflicts["empresa_nombre"].unique():
            cargos_emp = (
                cargos[cargos["empresa_nombre"] == empresa]["cargo"].tolist()
                if not cargos.empty
                else []
            )
            G.add_node(
                empresa,
                tipo=NODE_EMPRESA,
                color=NODE_COLORS[NODE_EMPRESA],
                cargos=cargos_emp,
            )

        # Aristas
        for _, row in conflicts.iterrows():
            G.add_edge(
                row["persona_nombre"],
                row["empresa_nombre"],
                severidad=row["severidad"],
                tipo_conflicto=row["tipo_conflicto"],
                n_resoluciones=int(row.get("n_resoluciones", 0)),
                cargo=row.get("cargo", ""),
                weight={"alta": 3, "media": 2, "baja": 1}.get(row["severidad"], 1),
            )

        logger.info(
            f"Grafo conflictos: {G.number_of_nodes()} nodos, {G.number_of_edges()} aristas"
        )
        return G

    # ── Reporte ───────────────────────────────────────────────────────────────

    def conflict_summary(self, conflicts: pd.DataFrame | None = None) -> dict:
        """
        Reporte estadístico de conflictos.

        Retorna: totales por severidad, top personas, top empresas,
        lista de conflictos de alta severidad.
        """
        if conflicts is None:
            conflicts = self.detect_conflicts()

        if conflicts.empty:
            return {
                "n_total": 0,
                "n_alta": 0,
                "n_media": 0,
                "n_baja": 0,
                "top_personas": [],
                "top_empresas": [],
                "conflictos_alta": [],
            }

        sev_counts = conflicts["severidad"].value_counts().to_dict()
        top_personas = (
            conflicts.groupby("persona_nombre")
            .agg(n_empresas=("empresa_nombre", "count"), max_sev=("severidad", "first"))
            .sort_values("n_empresas", ascending=False)
            .head(10)
            .reset_index()
            .to_dict("records")
        )
        top_empresas = (
            conflicts.groupby("empresa_nombre")
            .agg(n_personas=("persona_nombre", "count"), max_sev=("severidad", "first"))
            .sort_values("n_personas", ascending=False)
            .head(10)
            .reset_index()
            .to_dict("records")
        )
        alta = conflicts[conflicts["severidad"] == "alta"][
            ["persona_nombre", "empresa_nombre", "cargo", "n_resoluciones"]
        ].to_dict("records")

        return {
            "n_total": len(conflicts),
            "n_alta": sev_counts.get("alta", 0),
            "n_media": sev_counts.get("media", 0),
            "n_baja": sev_counts.get("baja", 0),
            "top_personas": top_personas,
            "top_empresas": top_empresas,
            "conflictos_alta": alta,
        }

    def full_run(self) -> dict:
        """Pipeline completo: detectar → guardar → resumen."""
        _ensure_tables(self.db_path)
        conflicts = self.detect_conflicts()
        n_saved = self.save_conflicts(conflicts)
        summary = self.conflict_summary(conflicts)
        summary["n_guardados"] = n_saved
        return summary


# ── Helpers ────────────────────────────────────────────────────────────────────

def _count_coapariciones(persona: str, empresa: str, db_path: Path) -> int:
    """Cuenta resoluciones donde persona y empresa co-aparecen."""
    try:
        conn = sqlite3.connect(db_path)
        persona_norm = _norm(persona)
        empresa_norm = _norm(empresa)
        row = conn.execute(
            """
            SELECT COUNT(DISTINCT m1.resolucion_id)
            FROM menciones m1
            JOIN entidades e1 ON m1.entidad_id = e1.id
            JOIN menciones m2 ON m1.resolucion_id = m2.resolucion_id
            JOIN entidades e2 ON m2.entidad_id = e2.id
            WHERE e1.nombre_norm = ?
              AND e2.nombre_norm LIKE ?
              AND e1.tipo = 'persona'
              AND e2.tipo = 'empresa'
            """,
            (persona_norm, f"%{empresa_norm[:12]}%"),
        ).fetchone()
        conn.close()
        return int(row[0]) if row else 0
    except Exception:
        return 0


def _ensure_tables(db_path: Path) -> None:
    """Crea tablas de conflictos si no existen (idempotente)."""
    from src.acquisition.boletin_oficial_scraper import _init_schema

    _init_schema(db_path)
