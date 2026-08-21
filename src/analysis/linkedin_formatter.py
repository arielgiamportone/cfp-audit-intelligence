"""
FisheriesAudit ALG — Generador de contenido LinkedIn.

Transforma hallazgos científicos en posts estructurados para la
Serie FisheriesAudit ALG 2026 sobre gobernanza pesquera.

Cada post sigue la estructura: Hook → Contexto → Datos → Reflexión → CTA → Hashtags
Optimizado para dos perfiles: personal (Ariel Giamportone) y pesqueros en IA.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

HASHTAGS_PERSONAL = [
    "#GobernanzaPesquera",
    "#CienciaDeDatos",
    "#PoliticaPesquera",
    "#Sustentabilidad",
    "#FisheriesAuditALG",
    "#Argentina",
    "#RecursosPesqueros",
    "#DataScience",
    "#OpenData",
]

HASHTAGS_PESQUEROS_IA = [
    "#FisheriesAI",
    "#MarineScience",
    "#FisheryManagement",
    "#OpenData",
    "#FisheriesAuditALG",
    "#ArtificialIntelligence",
    "#FisheriesGovernance",
    "#MarinePolicy",
    "#DataDrivenFisheries",
]

SERIE_HEADER = "🐟 **FisheriesAudit ALG 2026 | Serie sobre Gobernanza Pesquera Argentina**"


@dataclass
class LinkedInPost:
    """Post LinkedIn estructurado."""

    numero_entrega: int
    titulo: str
    hook: str
    contexto: str
    datos_principales: list[str]
    reflexion: str
    cta: str
    hashtags: list[str]
    perfil: str = "personal"  # "personal" | "pesqueros_ia"
    emoji_tema: str = "📊"
    fuentes: list[str] = field(default_factory=list)

    def render(self) -> str:
        """Genera el texto completo del post."""
        entrega = f"Entrega #{self.numero_entrega:02d}"
        header = f"{SERIE_HEADER}\n{entrega} — {self.titulo}\n"
        separator = "─" * 40

        datos_block = "\n".join(f"  {self.emoji_tema} {d}" for d in self.datos_principales)

        fuentes_block = ""
        if self.fuentes:
            fuentes_block = "\n📎 Fuentes: " + " | ".join(self.fuentes) + "\n"

        hashtags_block = " ".join(self.hashtags[:10])

        return "\n".join(
            [
                header,
                self.hook,
                "",
                separator,
                "",
                self.contexto,
                "",
                datos_block,
                "",
                self.reflexion,
                "",
                f"👉 {self.cta}",
                "",
                fuentes_block,
                hashtags_block,
            ]
        )

    def render_corto(self, max_chars: int = 700) -> str:
        """Versión corta para comentarios o stories."""
        datos = " | ".join(self.datos_principales[:3])
        return (
            f"{self.hook}\n\n{datos}\n\n{self.reflexion[:200]}...\n\n{' '.join(self.hashtags[:5])}"
        )[:max_chars]


class LinkedInFormatter:
    """
    Genera posts LinkedIn a partir de hallazgos del ResearchExporter.

    Uso:
        formatter = LinkedInFormatter(hallazgos, numero_entrega=1)
        posts = formatter.generar_todos()
        for post in posts:
            print(post.render())
    """

    def __init__(self, hallazgos: list[Any], numero_entrega_inicial: int = 1) -> None:
        self.hallazgos = hallazgos
        self.base_numero = numero_entrega_inicial

    def post_triangulo_auditoria(self, datos_clave: dict, perfil: str = "personal") -> LinkedInPost:
        """Post sobre la metodología del Triángulo de Auditoría."""
        hashtags = HASHTAGS_PERSONAL if perfil == "personal" else HASHTAGS_PESQUEROS_IA

        median_ratio = datos_clave.get("Mediana ratio CMP/CBA", "N/A")
        pct_sobre = datos_clave.get("% casos sobre CBA", "N/A")
        n = datos_clave.get("N comparaciones", "N/A")
        especies = datos_clave.get("Especies", "N/A")

        return LinkedInPost(
            numero_entrega=self.base_numero,
            titulo="El Triángulo de Auditoría Pesquera",
            emoji_tema="🔺",
            hook=(
                "¿Cómo saber si una cuota pesquera es científicamente válida?\n"
                "Tres números lo dicen todo: CBA · CMP · Captura real."
            ),
            contexto=(
                "En Argentina, el INIDEP calcula anualmente la Captura Biológicamente Aceptable (CBA) "
                "para cada especie. El CFP fija la Captura Máxima Permisible (CMP). "
                "SAGPyA registra lo que realmente se captura.\n\n"
                "Cuando CMP > CBA → el CFP aprueba más de lo que la ciencia recomienda.\n"
                "Cuando Captura < CMP → las cuotas no se utilizan plenamente (¿especulación?).\n"
                "Este triángulo es el núcleo de la plataforma FisheriesAudit ALG."
            ),
            datos_principales=[
                f"Mediana CMP/CBA: {median_ratio} (>1.0 = sobreasignación)",
                f"Casos sobre CBA: {pct_sobre} de {n} comparaciones",
                f"Especies analizadas: {especies}",
                "Período: 2022–2025 (datos seed verificados con ITOs INIDEP)",
            ],
            reflexion=(
                "Los recursos pesqueros son patrimonio nacional (Ley 24.922). "
                "Cuando las cuotas superan sistemáticamente la recomendación científica, "
                "¿quién protege el stock para las próximas generaciones?\n\n"
                "La ciencia de datos nos da herramientas para hacer visible lo que "
                "los documentos públicos ya contienen."
            ),
            cta=(
                "¿Trabajás en gestión pesquera, política pública o periodismo de datos? "
                "Este análisis es abierto. Conectemos."
            ),
            hashtags=hashtags,
            perfil=perfil,
            fuentes=[
                "INIDEP Mar Abierto (marabierto.inidep.edu.ar)",
                "CFP Actas Públicas",
                "SAGPyA/SIPA",
            ],
        )

    def post_sobreasignacion(
        self, datos_clave: dict, test_result: Any | None = None, perfil: str = "personal"
    ) -> LinkedInPost:
        """Post sobre sobreasignación sistémica de cuotas."""
        hashtags = HASHTAGS_PERSONAL if perfil == "personal" else HASHTAGS_PESQUEROS_IA

        pct_sobre = datos_clave.get("% casos sobre CBA", "N/A")
        median_r = datos_clave.get("Mediana ratio CMP/CBA", "N/A")

        sig_text = ""
        if test_result and hasattr(test_result, "significativo"):
            sig_text = (
                f"p={test_result.p_value:.3f} (estadísticamente significativo)"
                if test_result.significativo
                else f"p={test_result.p_value:.3f} (no significativo con los datos disponibles)"
            )

        return LinkedInPost(
            numero_entrega=self.base_numero + 1,
            titulo="Sobreasignación sistémica de cuotas pesqueras",
            emoji_tema="⚠️",
            hook=(
                f"El CFP aprueba cuotas por encima del límite científico en {pct_sobre} de los casos.\n"
                "Esto no es una excepción. Es un patrón."
            ),
            contexto=(
                "25 años de actas del Consejo Federal Pesquero contienen las decisiones que "
                "determinaron el estado actual de los stocks pesqueros argentinos. "
                "Procesadas con IA, revelan un patrón sistemático: la Captura Máxima Permisible "
                "aprobada supera regularmente la recomendación científica del INIDEP."
            ),
            datos_principales=[
                f"Casos con CMP > CBA INIDEP: {pct_sobre}",
                f"Mediana de sobreasignación: {median_r}x la recomendación científica",
                f"Test estadístico (Wilcoxon): {sig_text}"
                if sig_text
                else "Análisis sobre datos seed 2022–2025",
                "Especies: merluza, centolla, abadejo, polaca, langostino",
            ],
            reflexion=(
                "No es que el INIDEP siempre tenga razón y el CFP siempre esté equivocado. "
                "La gestión adaptativa a veces justifica apartarse de la CBA. "
                "Pero cuando el patrón es sistemático y unidireccional, "
                "hay una pregunta legítima: ¿qué otros factores influyen en la decisión?"
            ),
            cta=(
                "El código y los datos son públicos. "
                "Si sos investigador o periodista y querés replicar este análisis, escribime."
            ),
            hashtags=hashtags,
            perfil=perfil,
            fuentes=["INIDEP ITOs 2022–2025", "CFP Actas Públicas 1998–2025"],
        )

    def post_sub_utilizacion(self, datos_clave: dict, perfil: str = "personal") -> LinkedInPost:
        """Post sobre sub-utilización de cuotas."""
        hashtags = HASHTAGS_PERSONAL if perfil == "personal" else HASHTAGS_PESQUEROS_IA
        n_sub = datos_clave.get("Casos sub-utilización (<70% CMP)", "N/A")
        pct_sub = datos_clave.get("% del total analizado", "N/A")

        return LinkedInPost(
            numero_entrega=self.base_numero + 2,
            titulo="Cuotas que no se usan: ¿especulación pesquera?",
            emoji_tema="📉",
            hook=(
                f"¿Qué pasa cuando una empresa tiene cuota pesquera y no la usa?\n"
                f"En {n_sub} casos ({pct_sub} del total), la captura fue inferior al 70% de la cuota aprobada."
            ),
            contexto=(
                "La sub-utilización de cuotas es el lado oscuro del sistema pesquero argentino. "
                "Una empresa puede tener cuota asignada, no pescar, y —dependiendo del régimen— "
                "mantenerla para el año siguiente o venderla. "
                "Mientras tanto, la especie sigue bajo presión por otras flotas."
            ),
            datos_principales=[
                f"Casos con captura < 70% CMP: {n_sub} ({pct_sub})",
                "Indicador posible: acaparamiento de cuotas o sobreestimación de capacidad",
                "Contrasta con sobreasignación: el CFP da más de lo recomendado, pero se captura menos de lo aprobado",
                "Fuente: SAGPyA/SIPA capturas declaradas vs CFP resoluciones",
            ],
            reflexion=(
                "El triángulo CBA → CMP → Captura muestra que el problema no es solo "
                "'pescar demasiado'. También es 'tener cuota sin pescar'. "
                "Ambos patrones merecen análisis de política pública."
            ),
            cta=(
                "¿Tenés acceso a datos SIPA más completos o al régimen de transferencia de cuotas? "
                "Este análisis mejora con más datos. Hablemos."
            ),
            hashtags=hashtags,
            perfil=perfil,
            fuentes=["SAGPyA/SIPA 2019–2024", "CFP Resoluciones"],
        )

    def post_metodologia_ia(self, perfil: str = "pesqueros_ia") -> LinkedInPost:
        """Post técnico sobre la metodología de IA utilizada."""
        hashtags = HASHTAGS_PESQUEROS_IA if perfil == "pesqueros_ia" else HASHTAGS_PERSONAL

        return LinkedInPost(
            numero_entrega=self.base_numero + 3,
            titulo="Cómo la IA audita 25 años de política pesquera",
            emoji_tema="🤖",
            hook=(
                "Más de 400 actas del CFP. 25 años de decisiones sobre recursos pesqueros argentinos. "
                "¿Cómo procesarlas? Con IA y datos abiertos."
            ),
            contexto=(
                "FisheriesAudit ALG es una plataforma open source que combina:\n"
                "• Web scraping + OCR para extraer actas CFP en PDF\n"
                "• NER pesquero especializado con spaCy (6 categorías de entidades)\n"
                "• Vector store ChromaDB con embeddings multilingües\n"
                "• Claude API (Anthropic) para análisis de riesgo con prompt caching\n"
                "• Comparador CFP vs INIDEP con alertas automáticas\n"
                "• Tests estadísticos formales (Wilcoxon, Kendall τ, Kruskal-Wallis)"
            ),
            datos_principales=[
                "25+ años de actas procesables (1998–2025)",
                "6 categorías NER: ESPECIE, EMPRESA_PESQUERA, PERSONA_CFP, NORMATIVA, ZONA_PESCA, BUQUE",
                "Triángulo de auditoría: CBA → CMP → Captura real",
                "588 tests automatizados, CI con GitHub Actions",
                "Stack: Python + Streamlit + SQLite + ChromaDB",
            ],
            reflexion=(
                "La IA no reemplaza al experto pesquero ni al analista de política pública. "
                "Lo que hace es escalar el análisis: pasar de 'puedo leer 10 actas' "
                "a 'puedo analizar patrones en 400 actas'. "
                "El juicio sigue siendo humano. Los datos, más completos."
            ),
            cta=(
                "El repositorio es público. Si querés usar esta metodología en otro sistema "
                "de gestión pesquera (Chile, Perú, UE), conversemos."
            ),
            hashtags=hashtags,
            perfil=perfil,
            fuentes=[
                "GitHub: arielgiamportone/cfp-audit-intelligence",
                "Claude API (Anthropic)",
                "spaCy NLP",
            ],
        )

    def generar_todos(self, hallazgos: list | None = None) -> dict[str, list[LinkedInPost]]:
        """
        Genera posts para ambos perfiles a partir de los hallazgos.

        Returns:
            Dict con claves "personal" y "pesqueros_ia", cada uno con lista de posts.
        """
        posts_personal: list[LinkedInPost] = []
        posts_ia: list[LinkedInPost] = []

        hallazgos = hallazgos or self.hallazgos

        datos_triangulo: dict = {}
        datos_sobreasignacion: dict = {}
        datos_sub: dict = {}
        test_sobre = None

        for h in hallazgos:
            titulo = h.titulo if hasattr(h, "titulo") else h.get("titulo", "")
            datos = h.datos_clave if hasattr(h, "datos_clave") else h.get("datos_clave", {})
            tests = h.tests if hasattr(h, "tests") else []

            if "sobreasignación" in titulo.lower():
                datos_sobreasignacion = datos
                test_sobre = tests[0] if tests else None
            elif "sub-utiliz" in titulo.lower():
                datos_sub = datos
            elif "triángulo" in titulo.lower() or "triangulo" in titulo.lower():
                datos_triangulo = datos

        if not datos_sobreasignacion:
            datos_sobreasignacion = {"% casos sobre CBA": "N/A", "Mediana ratio CMP/CBA": "N/A"}
        if not datos_sub:
            datos_sub = {"Casos sub-utilización (<70% CMP)": "N/A", "% del total analizado": "N/A"}

        posts_personal += [
            self.post_triangulo_auditoria(datos_triangulo or datos_sobreasignacion, "personal"),
            self.post_sobreasignacion(datos_sobreasignacion, test_sobre, "personal"),
            self.post_sub_utilizacion(datos_sub, "personal"),
            self.post_metodologia_ia("personal"),
        ]

        posts_ia += [
            self.post_triangulo_auditoria(datos_triangulo or datos_sobreasignacion, "pesqueros_ia"),
            self.post_metodologia_ia("pesqueros_ia"),
            self.post_sobreasignacion(datos_sobreasignacion, test_sobre, "pesqueros_ia"),
        ]

        return {"personal": posts_personal, "pesqueros_ia": posts_ia}
