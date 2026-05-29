"""
Constructor del grafo de relaciones CFP.

Construye un grafo NetworkX con nodos de especies, empresas y actas,
y aristas ponderadas por co-menciones en las decisiones del CFP.
"""

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

import networkx as nx
import pandas as pd
from loguru import logger

# ── Tipos de nodos ─────────────────────────────────────────────────────────────

NODE_ESPECIE = "especie"
NODE_EMPRESA = "empresa"
NODE_ACTA = "acta"

# Paleta de colores por tipo de nodo
NODE_COLORS = {
    NODE_ESPECIE: "#1976D2",  # azul
    NODE_EMPRESA: "#E65100",  # naranja
    NODE_ACTA: "#757575",  # gris
}

# Empresas conocidas con nombres duplicados/ruidosos — normalización manual
_ALIAS_EMPRESAS = {
    "abadejero s.a.": "ABADEJERO S.A.",
    "argenova s.a.": "ARGENOVA S.A.",
    "pesantar s.a.": "PESANTAR S.A.",
    "estremar s.a.": "ESTREMAR S.A.",
    "conarpesa": "CONARPESA",
    "arbumasa": "ARBUMASA",
    "prodesur s.a.": "PRODESUR S.A.",
    "fonseca s.a.": "FONSECA S.A.",
    "glaciar pesquera s.a.": "GLACIAR PESQUERA S.A.",
    "altamare s.a.": "ALTAMARE S.A.",
    "ardapez s.a.": "ARDAPEZ S.A.",
    "tinopesca s.a.": "TINOPESCA S.A.",
    "illex fishing s.a.": "ILLEX FISHING S.A.",
    "wanchese argentina s.r.l.": "WANCHESE ARG. S.R.L.",
    "wanchese arg. s.a.": "WANCHESE ARG. S.R.L.",
    "shin yang ar s.a.": "SHIN YANG AR S.A.",
    "shing yang ar s.a.": "SHIN YANG AR S.A.",
    "continental de armadores de pesca s.a.": "CONTINENTAL ARMADORES S.A.",
    "antonio baldino e hijos s.a.": "BALDINO E HIJOS S.A.",
    "pesquera latina s.a.": "PESQUERA LATINA S.A.",
    "pesquería del atlántico s.a.": "PESQ. DEL ATLÁNTICO S.A.",
    "pesqueria del atlantico s.a.": "PESQ. DEL ATLÁNTICO S.A.",
    "crustáceos patagónicos s.a.": "CRUSTÁCEOS PATAGÓNICOS S.A.",
    "crustaceos patagonicos s.a.": "CRUSTÁCEOS PATAGÓNICOS S.A.",
}

# Nombres de empresas que son ruido (extraídos mal por el parser)
_RUIDO_EMPRESAS = {
    "la sa",
    "u. y pesa",
    "pensa",
    "gdeba-ssa",
    "consejo de empresa",
    "consejo de \nempresa",
    "luca sa",
    "vieirasa",
    "viernes sa",
}


@dataclass
class GrafoStats:
    """Estadísticas básicas del grafo."""

    n_nodos: int = 0
    n_aristas: int = 0
    n_especies: int = 0
    n_empresas: int = 0
    n_actas: int = 0
    especie_mas_conectada: str | None = None
    empresa_mas_conectada: str | None = None
    densidad: float = 0.0
    componentes: int = 0
    hhi_por_especie: dict = field(default_factory=dict)


class CFPGraphBuilder:
    """Construye y analiza el grafo de relaciones CFP."""

    def __init__(self, db_path: Path | str = "data/processed/catalog.db"):
        self.db_path = Path(db_path)

    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def load_data(self) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """Carga entidades, menciones y resoluciones de la BD."""
        with self._conn() as conn:
            df_ent = pd.read_sql_query("SELECT id, tipo, nombre, nombre_norm FROM entidades", conn)
            df_men = pd.read_sql_query(
                """
                SELECT m.resolucion_id, m.entidad_id, m.contexto,
                       r.acta_id, r.tipo as tipo_decision, r.categoria
                FROM menciones m
                JOIN resoluciones r ON m.resolucion_id = r.id
                """,
                conn,
            )
            df_res = pd.read_sql_query(
                """
                SELECT r.id, r.acta_id, r.tipo, r.categoria,
                       a.year, a.nombre as nombre_acta
                FROM resoluciones r
                JOIN actas a ON r.acta_id = a.id
                """,
                conn,
            )
        return df_ent, df_men, df_res

    def _clean_nombre(self, nombre_norm: str, tipo: str) -> str | None:
        """Normaliza y limpia nombre de entidad."""
        if not nombre_norm:
            return None
        n = nombre_norm.strip().replace("\n", " ").replace("  ", " ")

        if tipo == "empresa":
            if n in _RUIDO_EMPRESAS:
                return None
            # Filtrar nombres muy largos o con ruido evidente
            if len(n) > 60 or "presentaci" in n or "solicitud" in n or "citc de" in n:
                return None
            return _ALIAS_EMPRESAS.get(n, n.upper()[:40])

        if tipo == "especie":
            # Normalizar variantes de merluza
            if "merluza" in n and "negra" not in n and "cola" not in n:
                return "merluza común"
            return n.replace("\n", " ").strip()

        return n

    def build_graph(
        self,
        incluir_actas: bool = False,
        min_coocurrencias: int = 1,
    ) -> nx.Graph:
        """
        Construye el grafo de relaciones especie ↔ empresa.

        Nodos: especies (azul) y empresas pesqueras (naranja).
        Aristas: co-mención en la misma decisión del CFP, ponderada por frecuencia.
        """
        df_ent, df_men, df_res = self.load_data()

        G = nx.Graph()

        # ── Mapeo de entidad id → nombre limpio ────────────────────────────────
        ent_map = {}
        for _, row in df_ent.iterrows():
            nombre = self._clean_nombre(row["nombre_norm"], row["tipo"])
            if nombre:
                ent_map[row["id"]] = {"nombre": nombre, "tipo": row["tipo"]}

        # ── Añadir nodos ───────────────────────────────────────────────────────
        for eid, info in ent_map.items():
            G.add_node(
                info["nombre"],
                tipo=info["tipo"],
                color=NODE_COLORS[info["tipo"]],
                menciones=0,
                resoluciones=set(),
            )

        # ── Calcular co-menciones por resolución ───────────────────────────────
        # Agrupar entidades por resolución
        men_por_res: dict[int, list[str]] = {}
        for _, row in df_men.iterrows():
            eid = row["entidad_id"]
            rid = row["resolucion_id"]
            if eid in ent_map:
                nombre = ent_map[eid]["nombre"]
                men_por_res.setdefault(rid, []).append(nombre)
                if G.has_node(nombre):
                    G.nodes[nombre]["menciones"] = G.nodes[nombre].get("menciones", 0) + 1
                    G.nodes[nombre]["resoluciones"].add(rid)

        # ── Crear aristas entre co-mencionados en la misma resolución ─────────
        edge_counts: dict[tuple[str, str], int] = {}
        for rid, nombres in men_por_res.items():
            nombres_uniq = list(set(nombres))
            for i, n1 in enumerate(nombres_uniq):
                for n2 in nombres_uniq[i + 1 :]:
                    t1 = G.nodes.get(n1, {}).get("tipo", "")
                    t2 = G.nodes.get(n2, {}).get("tipo", "")
                    # Solo conectar especie ↔ empresa (no especie-especie ni empresa-empresa)
                    if {t1, t2} == {NODE_ESPECIE, NODE_EMPRESA}:
                        key = tuple(sorted([n1, n2]))
                        edge_counts[key] = edge_counts.get(key, 0) + 1

        for (n1, n2), count in edge_counts.items():
            if count >= min_coocurrencias:
                G.add_edge(n1, n2, weight=count, width=min(count * 1.5, 8))

        # Convertir sets a listas (no serializables en algunos formatos)
        for node in G.nodes:
            G.nodes[node]["n_resoluciones"] = len(G.nodes[node].get("resoluciones", set()))
            G.nodes[node]["resoluciones"] = list(G.nodes[node].get("resoluciones", set()))

        # Eliminar nodos aislados (sin aristas)
        isolated = [n for n in G.nodes if G.degree(n) == 0]
        G.remove_nodes_from(isolated)

        logger.info(f"Grafo construido: {G.number_of_nodes()} nodos, {G.number_of_edges()} aristas")
        return G

    def compute_stats(self, G: nx.Graph) -> GrafoStats:
        """Calcula estadísticas del grafo y HHI de concentración por especie."""
        if G.number_of_nodes() == 0:
            return GrafoStats()

        especies = [n for n, d in G.nodes(data=True) if d.get("tipo") == NODE_ESPECIE]
        empresas = [n for n, d in G.nodes(data=True) if d.get("tipo") == NODE_EMPRESA]

        # Empresa y especie más conectadas
        grados = dict(G.degree())
        esp_conectada = max(especies, key=lambda n: grados.get(n, 0)) if especies else None
        emp_conectada = max(empresas, key=lambda n: grados.get(n, 0)) if empresas else None

        # HHI por especie: concentración de menciones entre empresas vinculadas
        hhi = {}
        for esp in especies:
            neighbors = [
                (n, G[esp][n]["weight"])
                for n in G.neighbors(esp)
                if G.nodes[n]["tipo"] == NODE_EMPRESA
            ]
            if neighbors:
                total = sum(w for _, w in neighbors)
                shares = [w / total for _, w in neighbors]
                hhi[esp] = round(sum(s**2 for s in shares) * 10_000, 0)

        return GrafoStats(
            n_nodos=G.number_of_nodes(),
            n_aristas=G.number_of_edges(),
            n_especies=len(especies),
            n_empresas=len(empresas),
            especie_mas_conectada=esp_conectada,
            empresa_mas_conectada=emp_conectada,
            densidad=round(nx.density(G), 4),
            componentes=nx.number_connected_components(G),
            hhi_por_especie=hhi,
        )

    def get_ego_graph(self, G: nx.Graph, nodo: str, radio: int = 1) -> nx.Graph:
        """Retorna el subgrafo centrado en un nodo (ego network)."""
        if nodo not in G:
            return nx.Graph()
        return nx.ego_graph(G, nodo, radius=radio)

    def top_empresas_por_especie(self, G: nx.Graph, especie: str) -> list[dict]:
        """Retorna las empresas más mencionadas en decisiones sobre una especie."""
        if especie not in G:
            return []
        neighbors = [
            {
                "empresa": n,
                "co_menciones": G[especie][n]["weight"],
            }
            for n in G.neighbors(especie)
            if G.nodes[n]["tipo"] == NODE_EMPRESA
        ]
        return sorted(neighbors, key=lambda x: x["co_menciones"], reverse=True)

    def to_dataframe(self, G: nx.Graph) -> pd.DataFrame:
        """Convierte las aristas del grafo a DataFrame para exportar."""
        rows = []
        for n1, n2, data in G.edges(data=True):
            t1 = G.nodes[n1]["tipo"]
            especie = n1 if t1 == NODE_ESPECIE else n2
            empresa = n1 if t1 == NODE_EMPRESA else n2
            rows.append(
                {
                    "especie": especie,
                    "empresa": empresa,
                    "co_menciones": data["weight"],
                }
            )
        return pd.DataFrame(rows).sort_values("co_menciones", ascending=False)
