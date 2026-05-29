"""
NER pesquero especializado para el dominio CFP Argentina.

Combina el modelo estadístico de spaCy (es_core_news_sm) con un EntityRuler
de reglas para reconocer entidades específicas del sector pesquero:
  ESPECIE_PESCA   — especies marinas (merluza hubbsi, calamar illex, ...)
  EMPRESA_PESCA   — empresas pesqueras (ARGENOVA S.A., CONARPESA, ...)
  ZONA_PESCA      — zonas de pesca (Sur 41°S, Patagonia, GSJ, ...)
  CUOTA_PESCA     — cuotas y toneladas (300.000 tn, CBA 150.000 t, ...)
  NORMATIVA_CFP   — resoluciones y leyes (Res. CFP N° 5/2020, Ley 24.922, ...)
  BUQUE_PESCA     — embarcaciones pesqueras
"""

from dataclasses import dataclass, field
from functools import lru_cache

import spacy
from loguru import logger
from spacy.language import Language

# ── Etiquetas de entidad ───────────────────────────────────────────────────────

LABEL_ESPECIE = "ESPECIE_PESCA"
LABEL_EMPRESA = "EMPRESA_PESCA"
LABEL_ZONA = "ZONA_PESCA"
LABEL_CUOTA = "CUOTA_PESCA"
LABEL_NORMATIVA = "NORMATIVA_CFP"
LABEL_BUQUE = "BUQUE_PESCA"

ALL_LABELS = [LABEL_ESPECIE, LABEL_EMPRESA, LABEL_ZONA, LABEL_CUOTA, LABEL_NORMATIVA, LABEL_BUQUE]

LABEL_COLORS = {
    LABEL_ESPECIE: "#1976D2",
    LABEL_EMPRESA: "#E65100",
    LABEL_ZONA: "#388E3C",
    LABEL_CUOTA: "#7B1FA2",
    LABEL_NORMATIVA: "#F57C00",
    LABEL_BUQUE: "#0097A7",
}

# ── Patrones de species ────────────────────────────────────────────────────────

_ESPECIES = [
    # Merluza y variantes
    "merluza hubbsi",
    "merluza común",
    "merluza de cola",
    "merluza austral",
    "merluza negra",
    "merluza del sur",
    "merluza del norte",
    "merluccius hubbsi",
    "merluccius polylepis",
    "merluccius australis",
    "dissostichus eleginoides",
    "macruronus magellanicus",
    # Calamar
    "calamar illex",
    "calamar loligo",
    "illex argentinus",
    "loligo gahi",
    "loligo patagonica",
    # Langostino / crustáceos
    "langostino patagónico",
    "langostino",
    "pleoticus muelleri",
    "camarón",
    "camarón patagónico",
    "centolla",
    "centollón",
    "lithodes santolla",
    "paralomis granulosa",
    "cangrejo",
    "crustáceos patagónicos",
    # Peces demersales
    "abadejo",
    "genypterus blacodes",
    "genypterus brasiliensis",
    "polaca",
    "micromesistius australis",
    "pez espada",
    "xiphias gladius",
    "corvina rubia",
    "micropogonias furnieri",
    "corvina negra",
    "pogonias cromis",
    "pescadilla",
    "cynoscion guatucupa",
    "brótola",
    "urophycis brasiliensis",
    "lenguado",
    "paralichthys",
    "cazón",
    "squalus acanthias",
    "palometa",
    "seriolella punctata",
    # Pelágicos
    "anchoíta",
    "anchoita",
    "engraulis anchoita",
    "caballa",
    "scomber japonicus",
    "salmón de mar",
    "pseudopercis semifasciata",
    "pejerrey",
    "odontesthes",
    # Moluscos / equinodermos
    "vieira patagónica",
    "vieira",
    "zygochlamys patagonica",
    "mejillón",
    "mytilus chilensis",
    "pulpo",
    "octopus tehuelchus",
    "erizo de mar",
    # Genéricas
    "recursos pesqueros",
    "recursos demersales",
    "recursos pelágicos",
    "peces cartilaginosos",
    "condrictios",
    "elasmobranquios",
]

_ZONAS = [
    "sur 41°s",
    "norte 41°s",
    "sur del paralelo 41",
    "norte del paralelo 41",
    "sur de 41°s",
    "norte de 41°s",
    "patagonia",
    "patagónico",
    "zona patagónica",
    "golfo san jorge",
    "gsj",
    "golfo nuevo",
    "golfo san matías",
    "zona austral",
    "aguas australes",
    "plataforma continental",
    "mar argentino",
    "zona económica exclusiva",
    "zee",
    "atlántico sudoccidental",
    "atlántico sur",
    "tierra del fuego",
    "canal beagle",
    "estrecho de magallanes",
    "islas malvinas",
    "georgias del sur",
    "sandwich del sur",
    "bahía san julián",
    "golfo de san jorge",
    "zona iii",
    "zona iv",
    "zona v",
    "subárea 41",
    "subárea 48",
]

_NORMATIVAS = [
    "ley 24.922",
    "ley 24922",
    "ley 25.290",
    "ley 25290",
    "decreto 748",
    "art. 9",
    "artículo 9",
    "art. 27",
    "artículo 27",
]

# ── Patrones empresa ───────────────────────────────────────────────────────────

_EMPRESAS_CONOCIDAS = [
    "argenova",
    "conarpesa",
    "arbumasa",
    "abadejero",
    "pesantar",
    "estremar",
    "prodesur",
    "glaciar pesquera",
    "altamare",
    "ardapez",
    "tinopesca",
    "illex fishing",
    "wanchese argentina",
    "wanchese arg",
    "shin yang ar",
    "shing yang ar",
    "continental de armadores",
    "continental armadores",
    "antonio baldino e hijos",
    "baldino e hijos",
    "pesquera latina",
    "pesquería del atlántico",
    "pesqueria del atlantico",
    "crustáceos patagónicos",
    "crustaceos patagonicos",
    "fonseca",
    "inidep",
    "cfp",
    "consejo federal pesquero",
    "harengus",
    "bariloche",
    "frigoríficos",
    "pesquería nacional",
    "nivia mar",
    "alpesca",
    "iberconsa",
    "novo mar",
]


def _build_ruler_patterns() -> list[dict]:
    """Construye los patrones para el EntityRuler."""
    patterns = []

    # ── Especies ──────────────────────────────────────────────────────────────
    for esp in _ESPECIES:
        patterns.append({"label": LABEL_ESPECIE, "pattern": esp})
        # Variante en mayúsculas
        patterns.append({"label": LABEL_ESPECIE, "pattern": esp.upper()})
        # Primera letra mayúscula
        patterns.append({"label": LABEL_ESPECIE, "pattern": esp.title()})

    # ── Zonas ─────────────────────────────────────────────────────────────────
    for zona in _ZONAS:
        patterns.append({"label": LABEL_ZONA, "pattern": zona})
        patterns.append({"label": LABEL_ZONA, "pattern": zona.upper()})
        patterns.append({"label": LABEL_ZONA, "pattern": zona.title()})

    # ── Empresas conocidas ────────────────────────────────────────────────────
    for emp in _EMPRESAS_CONOCIDAS:
        patterns.append({"label": LABEL_EMPRESA, "pattern": emp.upper()})
        patterns.append({"label": LABEL_EMPRESA, "pattern": emp})
        patterns.append({"label": LABEL_EMPRESA, "pattern": emp.title()})

    # ── Patrón genérico empresa: NOMBRE S.A. / S.R.L. / S.A.C.I. ─────────────
    for suffix in ["S.A.", "S.R.L.", "S.A.C.I.", "S.A.C.I.F.", "S.C.A.", "S.A.I.C."]:
        patterns.append(
            {
                "label": LABEL_EMPRESA,
                "pattern": [
                    {"IS_UPPER": True, "OP": "+"},
                    {"ORTH": suffix},
                ],
            }
        )

    # ── Zonas con patrón de token (Sur/Norte + número + ° + S/N) ─────────────
    for direccion in ["sur", "norte"]:
        for paralelo in ["41", "42", "47"]:
            # "Sur 41°S" — la S final puede tener punto (fin de frase)
            patterns.append(
                {
                    "label": LABEL_ZONA,
                    "pattern": [
                        {"LOWER": {"IN": [direccion, direccion.title()]}},
                        {"LOWER": paralelo},
                        {"ORTH": "°"},
                        {"TEXT": {"REGEX": r"[SsNn]\.?"}},
                    ],
                }
            )
            # "sur del paralelo 41°S"
            patterns.append(
                {
                    "label": LABEL_ZONA,
                    "pattern": [
                        {"LOWER": {"IN": [direccion, direccion.title()]}},
                        {"LOWER": {"IN": ["del", "de"]}},
                        {"LOWER": "paralelo"},
                        {"LOWER": paralelo},
                        {"ORTH": "°", "OP": "?"},
                        {"TEXT": {"REGEX": r"[SsNn]\.?"}, "OP": "?"},
                    ],
                }
            )

    # ── Normativas ────────────────────────────────────────────────────────────
    for norm in _NORMATIVAS:
        patterns.append({"label": LABEL_NORMATIVA, "pattern": norm})

    # Resolución CFP N° X/YYYY  — "N" y "°" son tokens separados
    patterns.append(
        {
            "label": LABEL_NORMATIVA,
            "pattern": [
                {"LOWER": {"IN": ["resolución", "resolucion", "res."]}},
                {"LOWER": {"IN": ["cfp"]}, "OP": "?"},
                {"LOWER": {"IN": ["n", "nro.", "núm.", "num."]}, "OP": "?"},
                {"ORTH": "°", "OP": "?"},
                {"TEXT": {"REGEX": r"\d{1,4}/\d{4}"}},
            ],
        }
    )

    # Resolución CFP (sin número)
    patterns.append(
        {
            "label": LABEL_NORMATIVA,
            "pattern": [
                {"LOWER": {"IN": ["resolución", "resolucion"]}},
                {"LOWER": "cfp"},
            ],
        }
    )

    # ── Cuotas: número + unidad ───────────────────────────────────────────────
    for unit in ["toneladas", "tn", "t.", "ton."]:
        # "300.000 toneladas"
        patterns.append(
            {
                "label": LABEL_CUOTA,
                "pattern": [{"LIKE_NUM": True}, {"LOWER": unit}],
            }
        )
        # "300.000 de toneladas"
        patterns.append(
            {
                "label": LABEL_CUOTA,
                "pattern": [{"LIKE_NUM": True}, {"LOWER": "de"}, {"LOWER": unit}],
            }
        )

    # CBA/CMP de X toneladas
    for keyword in ["cba", "cmp", "cuota"]:
        patterns.append(
            {
                "label": LABEL_CUOTA,
                "pattern": [
                    {"LOWER": keyword},
                    {"LOWER": {"IN": ["de", "=", ":"]}, "OP": "?"},
                    {"LIKE_NUM": True},
                    {"LOWER": {"IN": ["toneladas", "tn", "t."]}, "OP": "?"},
                ],
            }
        )

    # ── Buques: "B / P NOMBRE" — nombre en mayúsculas, máx 3 palabras ────────
    for stern in ["p", "m", "t", "r"]:
        patterns.append(
            {
                "label": LABEL_BUQUE,
                "pattern": [
                    {"LOWER": "b"},
                    {"ORTH": "/"},
                    {"LOWER": stern},
                    {"IS_UPPER": True},
                    {"IS_UPPER": True, "OP": "?"},
                    {"IS_UPPER": True, "OP": "?"},
                ],
            }
        )

    return patterns


@dataclass
class EntidadExtraida:
    texto: str
    etiqueta: str
    inicio: int
    fin: int
    contexto: str = ""


@dataclass
class ResultadoNER:
    texto_original: str
    entidades: list[EntidadExtraida] = field(default_factory=list)

    @property
    def especies(self) -> list[str]:
        return [e.texto for e in self.entidades if e.etiqueta == LABEL_ESPECIE]

    @property
    def empresas(self) -> list[str]:
        return [e.texto for e in self.entidades if e.etiqueta == LABEL_EMPRESA]

    @property
    def zonas(self) -> list[str]:
        return [e.texto for e in self.entidades if e.etiqueta == LABEL_ZONA]

    @property
    def cuotas(self) -> list[str]:
        return [e.texto for e in self.entidades if e.etiqueta == LABEL_CUOTA]

    @property
    def normativas(self) -> list[str]:
        return [e.texto for e in self.entidades if e.etiqueta == LABEL_NORMATIVA]

    @property
    def buques(self) -> list[str]:
        return [e.texto for e in self.entidades if e.etiqueta == LABEL_BUQUE]

    def by_label(self, label: str) -> list[str]:
        return [e.texto for e in self.entidades if e.etiqueta == label]

    def to_dict(self) -> dict:
        return {
            "especies": list(set(self.especies)),
            "empresas": list(set(self.empresas)),
            "zonas": list(set(self.zonas)),
            "cuotas": self.cuotas,
            "normativas": list(set(self.normativas)),
            "buques": list(set(self.buques)),
        }


class FisheriesNER:
    """
    NER especializado en el dominio pesquero del CFP Argentina.

    Combina el modelo estadístico es_core_news_sm con un EntityRuler
    de patrones de dominio para máxima cobertura.
    """

    def __init__(self, model: str = "es_core_news_sm"):
        self.model = model
        self._nlp: Language | None = None

    def _load(self) -> Language:
        if self._nlp is not None:
            return self._nlp

        try:
            nlp = spacy.load(self.model)
        except OSError:
            logger.warning(f"Modelo {self.model} no encontrado, usando modelo en blanco")
            nlp = spacy.blank("es")

        # Deshabilitar componentes no necesarios para velocidad
        disabled = [c for c in ["tagger", "parser", "lemmatizer"] if c in nlp.pipe_names]
        for comp in disabled:
            nlp.disable_pipe(comp)

        # Insertar EntityRuler ANTES del ner estadístico para que nuestras
        # reglas tengan prioridad (overwrite_ents=True en el ruler)
        ruler = nlp.add_pipe(
            "entity_ruler",
            before="ner" if "ner" in nlp.pipe_names else None,
            config={"overwrite_ents": True, "phrase_matcher_attr": "LOWER"},
        )
        patterns = _build_ruler_patterns()
        ruler.add_patterns(patterns)
        logger.debug(f"EntityRuler: {len(patterns)} patrones de dominio pesquero cargados")

        self._nlp = nlp
        return nlp

    def process(self, text: str, context_window: int = 80) -> ResultadoNER:
        """Extrae entidades pesqueras de un texto."""
        if not text or not text.strip():
            return ResultadoNER(texto_original=text)

        nlp = self._load()

        # Procesar en chunks si el texto es muy largo
        max_len = nlp.max_length
        if len(text) > max_len:
            text = text[:max_len]
            logger.debug(f"Texto truncado a {max_len} caracteres para NER")

        doc = nlp(text)

        entidades = []
        seen = set()
        for ent in doc.ents:
            if ent.label_ not in ALL_LABELS:
                continue
            key = (ent.text.strip().lower(), ent.label_)
            if key in seen:
                continue
            seen.add(key)

            ctx_start = max(0, ent.start_char - context_window)
            ctx_end = min(len(text), ent.end_char + context_window)
            contexto = text[ctx_start:ctx_end].replace("\n", " ").strip()

            texto = ent.text.strip().rstrip(".,;:")
            entidades.append(
                EntidadExtraida(
                    texto=texto,
                    etiqueta=ent.label_,
                    inicio=ent.start_char,
                    fin=ent.end_char,
                    contexto=contexto,
                )
            )

        return ResultadoNER(texto_original=text, entidades=entidades)

    def process_batch(self, texts: list[str], batch_size: int = 32) -> list[ResultadoNER]:
        """Procesa una lista de textos en batch."""
        nlp = self._load()
        resultados = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            for doc, text in zip(nlp.pipe(batch), batch):
                entidades = []
                seen = set()
                for ent in doc.ents:
                    if ent.label_ not in ALL_LABELS:
                        continue
                    key = (ent.text.strip().lower(), ent.label_)
                    if key in seen:
                        continue
                    seen.add(key)
                    entidades.append(
                        EntidadExtraida(
                            texto=ent.text.strip(),
                            etiqueta=ent.label_,
                            inicio=ent.start_char,
                            fin=ent.end_char,
                        )
                    )
                resultados.append(ResultadoNER(texto_original=text, entidades=entidades))

        return resultados

    def extract_from_acta(self, texto_acta: str) -> dict:
        """Extrae todas las entidades de una acta y las retorna como dict."""
        resultado = self.process(texto_acta)
        return resultado.to_dict()

    @staticmethod
    def visualize_html(text: str, ner: "FisheriesNER") -> str:
        """Retorna HTML con entidades resaltadas (para Streamlit)."""
        from spacy import displacy

        nlp = ner._load()
        doc = nlp(text[:5000])
        options = {
            "ents": ALL_LABELS,
            "colors": LABEL_COLORS,
        }
        return displacy.render(doc, style="ent", options=options, page=False)


@lru_cache(maxsize=1)
def get_ner() -> FisheriesNER:
    """Retorna instancia singleton del NER (cargada una sola vez)."""
    ner = FisheriesNER()
    ner._load()
    return ner
