"""
Parser de actas del CFP: extrae estructura real de las minutas de sesión.

Formato real del CFP:
  - Orden del Día numerado (1., 1.1., 1.1.1., ...)
  - Cada punto tiene: descripción del tema → contexto → DECISIÓN
  - Decisiones: "se decide por unanimidad...", "se aprueba...", "se acuerda..."
  - Referencias a Resoluciones CFP previas (N° X/YYYY)
  - CITC = Cuotas Individuales Transferibles de Captura
"""

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from loguru import logger

# ── Patrones regex ajustados al formato real del CFP ─────────────────────────

_MESES_PAT = (
    r"enero|febrero|marzo|abril|mayo|junio|julio|agosto|"
    r"septiembre|octubre|noviembre|diciembre"
)

RE_FECHA = re.compile(
    r"A los (\d{1,2}) días del mes de "
    rf"({_MESES_PAT}) de (\d{{4}})",
    re.IGNORECASE,
)

# Fecha inline dentro del cuerpo de un punto (ej: "Buenos Aires, 15 de marzo de 2025")
RE_FECHA_INLINE = re.compile(
    rf"(?:Buenos Aires,?\s+)?(?:con fecha\s+|del día\s+|el día\s+|el\s+)?"
    rf"(\d{{1,2}})\s+de\s+({_MESES_PAT})\s+de\s+(\d{{4}})",
    re.IGNORECASE,
)

# Votos en contra — extrae quién votó contra
RE_VOTO_CONTRA = re.compile(
    r"(?:con el voto en contra|votando en contra|vot[oó] en contra|"
    r"con la disidencia|en disidencia)\s+(?:de\s+(?:la?|los|las)\s+)?(.{5,120}?)(?=[,\.;\n]|\Z)",
    re.IGNORECASE,
)

# Votos explícitamente a favor
RE_VOTO_FAVOR = re.compile(
    r"(?:con\s+(?:(?:el|la|los?|las?|un)\s+)?voto[s]?\s+(?:afirmativo[s]?|favorable[s]?)|" 
    r"votando\s+a\s+favor|vot[oó]\s+a\s+favor|"
    r"a\s+favor(?:\s*:|\s+vot(?:aron|[oó]))\s*)"
    r"(?:\s+de\s+(?:la?s?\s+)?)?(.{5,150}?)(?=[,\.;\n]|\Z)",
    re.IGNORECASE,
)

# Abstenciones
RE_ABSTENCION = re.compile(
    r"(?:con la abstenci[oó]n|abstenién?dose|se abstienen?)\s+(?:de\s+(?:la?|los|las)\s+)?(.{5,120}?)(?=[,\.;\n]|\Z)",
    re.IGNORECASE,
)

# Mapa de normalización: fragmento en minúsculas → nombre canónico de institución CFP
_NORM_INSTITUCIONES: dict[str, str] = {
    "buenos aires": "Prov. Buenos Aires",
    "chubut": "Prov. Chubut",
    "santa cruz": "Prov. Santa Cruz",
    "río negro": "Prov. Río Negro",
    "rio negro": "Prov. Río Negro",
    "tierra del fuego": "Prov. Tierra del Fuego",
    "secretaría de pesca": "Sec. Pesca (Nación)",
    "secretaria de pesca": "Sec. Pesca (Nación)",
    "subsecretaría de pesca": "Sec. Pesca (Nación)",
    "subsecretaria de pesca": "Sec. Pesca (Nación)",
    "poder ejecutivo nacional": "P.E.N.",
    "inidep": "INIDEP",
    "armada": "Armada Argentina",
    "prefectura": "Prefectura Naval",
}

# Inicio de sesión
RE_INICIO_SESION = re.compile(
    r"(?:se\s+inicia\s+la\s+sesi[oó]n|dando\s+inicio\s+a\s+la\s+sesi[oó]n|"
    r"se\s+da\s+inicio\s+a\s+la\s+sesi[oó]n|se\s+retoma\s+la\s+sesi[oó]n|"
    r"continuando\s+con\s+la\s+sesi[oó]n)",
    re.IGNORECASE,
)

# Cierre de sesión
RE_CIERRE_SESION = re.compile(
    r"(?:se\s+levanta\s+la\s+sesi[oó]n|se\s+da\s+por\s+concluida|"
    r"sin\s+m[aá]s\s+temas?\s+(?:que\s+)?tratar|"
    r"se\s+da\s+por\s+finalizada\s+la\s+sesi[oó]n|"
    r"se\s+cierra\s+la\s+sesi[oó]n)",
    re.IGNORECASE,
)

# Receso dentro de la sesión
RE_RECESO = re.compile(
    r"(?:se\s+hace?\s+un?\s+receso|se\s+suspende\s+(?:brevemente|la\s+sesi[oó]n)|"
    r"cuarto\s+intermedio)",
    re.IGNORECASE,
)

RE_QUORUM = re.compile(
    r"quórum\s+de\s+([A-ZÁÉÍÓÚÜÑ]+)\s*\((\d+)\)",
    re.IGNORECASE,
)

RE_DECISION = re.compile(
    r"se decide\s+(?:por\s+)?(?:unanimidad|mayoría)[,\s]*(.{10,600}?)(?=\n\n|\nA continuación|\nSe instruye|\Z)",
    re.IGNORECASE | re.DOTALL,
)

RE_APRUEBA = re.compile(
    r"se (?:aprueba|acuerda|resuelve|autoriza|instruye|establece)\s+(?:por unanimidad\s+)?(.{10,500}?)(?=\n\n|\Z)",
    re.IGNORECASE | re.DOTALL,
)

RE_AGENDA_ITEM = re.compile(
    r"^(\d+(?:\.\d+)*)\.\s+(.+?)(?=\n\d+(?:\.\d+)*\.|\Z)",
    re.MULTILINE | re.DOTALL,
)

RE_EMPRESA = re.compile(
    r"\b([A-ZÁÉÍÓÚÜÑ][A-ZÁÉÍÓÚÜÑa-záéíóúüñ\s\-\.]{2,50}?\s*(?:S\.A\.|S\.R\.L\.|SRL|SA|S\.A\.C\.I\.|LTDA\.|COOP\.))",
)

# Número de resolución que GENERA esta decisión (verbo dictar/emitir antes del número)
RE_NUMERO_RESOLUCION = re.compile(
    r"(?:dictar?|emitir?|se\s+dicta|se\s+emite)\s+(?:la\s+)?Resoluci[oó]n\s+"
    r"(?:CFP\s+|del\s+Consejo[^N]{0,40})?N[°º\.]\s*(\d+/\d{4})",
    re.IGNORECASE,
)

# Decisiones diferidas / postergadas
RE_DIFERIDA = re.compile(
    r"se\s+difiere?\s+(?:el\s+)?(?:tratamiento|consideraci[oó]n|an[aá]lisis)|"
    r"se\s+posterga|"
    r"queda\s+(?:en\s+suspenso|pendiente\s+de\s+tratamiento)|"
    r"cuarto\s+intermedio|"
    r"pasa\s+(?:al?\s+pr[oó]ximo|a\s+la\s+pr[oó]xima)\s+(?:orden|reuni[oó]n|sesi[oó]n)|"
    r"no\s+se\s+trata\s+en\s+esta\s+sesi[oó]n|"
    r"se\s+reserva\s+(?:su\s+)?tratamiento",
    re.IGNORECASE,
)

# Decisiones denegadas / rechazadas
RE_DENEGADA = re.compile(
    r"no\s+se\s+hace\s+lugar|"
    r"se\s+rechaza\b|"
    r"se\s+deniega\b|"
    r"no\s+prospera\b|"
    r"se\s+desestima\b|"
    r"no\s+se\s+(?:aprueba|autoriza|otorga)\b|"
    r"se\s+niega\s+(?:el\s+)?(?:pedido|solicitud|permiso)",
    re.IGNORECASE,
)

# Fundamentos científicos del INIDEP citados como base de la decisión
RE_FUNDAMENTO_INIDEP = re.compile(
    r"(?:"
    # "Informe [Técnico] [del] INIDEP" o "dictamen/evaluación/nota [del] INIDEP"
    r"(?:Informe|dictamen|evaluaci[oó]n|nota)\s+"
    r"(?:t[eé]cnic[oa]s?\s+|cient[ií]fico[as]?\s+|de\s+evaluaci[oó]n\s+|de\s+stock\s+)?"
    r"(?:del?\s+)?INIDEP"
    r"|"
    # "INIDEP Informe/dictamen [Técnico]"
    r"INIDEP\s+(?:Informe|dictamen|evaluaci[oó]n|nota)(?:\s+t[eé]cnico[as]?)?"
    r")"
    r"\s+N[°º\.ro]{0,4}\s*\d+/\d{4}",
    re.IGNORECASE,
)

# Zonas y áreas de pesca del Mar Argentino y Antártico
RE_ZONA_CAPTURA = re.compile(
    r"(?:"
    # Áreas nombradas del CFP/SAGPyA
    r"[Áá]rea\s+(?:Norpatag[oó]nica|Patag[oó]nica|Bonaerense|Marina|"
    r"de\s+la\s+Convenci[oó]n\s+CCAMLR|Ant[áa]rtica)|"
    # Sub-áreas FAO/ICES (ej: subárea 41.3.1, 48.3)
    r"sub[áa]rea\s+\d+\.\d+(?:\.\d+)?|"
    # Área estadística FAO
    r"[áa]rea\s+estad[ií]stica\s+\d+|"
    # ZEE
    r"Zona\s+Econ[oó]mica\s+Exclusiva(?:\s+Argentina)?|ZEEA?\b|"
    # Plataforma/talud/litoral
    r"plataforma\s+continental|talud\s+continental|litoral\s+patag[oó]nico|"
    # Mar regional
    r"Mar\s+(?:Argentino|Austral|Patag[oó]nico)|"
    # Por paralelo de latitud
    r"(?:al\s+)?(?:norte|sur)\s+del\s+paralelo\s+\d+°?\s*[SsNn]|"
    # Aguas jurisdiccionales / franja costera
    r"aguas?\s+jurisdiccionales|franja\s+costera|"
    # Aguas de provincia costera
    r"aguas?\s+de\s+(?:Chubut|Santa\s+Cruz|Buenos\s+Aires|Tierra\s+del\s+Fuego|R[ií]o\s+Negro)"
    r")",
    re.IGNORECASE,
)

RE_ESPECIE = re.compile(
    r"\b(merluza(?:\s+(?:común|hubbsi|de cola|negra|austral))?|"
    r"langostino|calamar(?:\s+(?:illex|loligo))?|abadejo|polaca|"
    r"corvina(?:\s+(?:rubia|negra))?|anchoíta|anchoita|caballa|"
    r"salmón(?:\s+de\s+mar)?|salmon|pejerrey|centolla|vieira|"
    r"mariscos?|moluscos?|merluza hubbsi)\b",
    re.IGNORECASE,
)

RE_TONELADAS = re.compile(
    r"([\d\.]+(?:,\d+)?)\s*(?:toneladas?|tn\.?|t\.?)(?:\s*métricas?)?",
    re.IGNORECASE,
)

RE_CITC = re.compile(r"\bCITC\b")

RE_MIEMBRO = re.compile(
    r"(?:Representante|Presidente|Secretario|Director)\s+(?:del?|de la)?\s*"
    r"(?:CFP|Provincia|PODER EJECUTIVO|MINISTERIO|INIDEP|Autoridad).*?[,\n]"
)

MESES = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}

_SUF_LEGAL = r"(?:S\.A\.C\.I\.|S\.R\.L\.|LTDA\.|COOP\.|S\.A\.|SRL|SA)(?!\w)"
_NOMBRE_EMP = rf"[A-ZÁÉÍÓÚÜÑ][A-ZÁÉÍÓÚÜÑa-záéíóúüñ\s\-\.]{{0,55}}?{_SUF_LEGAL}"
_TN_VAL = r"[\d\.]+(?:,\d+)?"

# Asignación directa: "asignar/adjudicar/otorgar a EMPRESA N toneladas"
RE_ASIGNACION_DIRECTA = re.compile(
    r"(?:asigna[rn]?|asignando|adjudica[rn]?|adjudicando|otorga[rn]?|otorgando)\s+a\s+"
    rf"(?P<empresa>{_NOMBRE_EMP})\s+"
    r"(?:la\s+suma\s+de\s+|un\s+total\s+de\s+)?"
    rf"(?P<tn>{_TN_VAL})\s*(?:toneladas?|tn\.?)",
    re.IGNORECASE,
)

# Asignación inversa: "N toneladas a/para EMPRESA"
RE_ASIGNACION_INVERSA = re.compile(
    rf"(?P<tn>{_TN_VAL})\s*(?:toneladas?|tn\.?)\s+"
    r"(?:a|para|a\s+favor\s+de)\s+"
    rf"(?P<empresa>{_NOMBRE_EMP})",
    re.IGNORECASE,
)

# Formato tabla: "EMPRESA: N toneladas" — solo en contextos con CITC
RE_ASIGNACION_TABLA = re.compile(
    rf"(?P<empresa>{_NOMBRE_EMP})\s*[:\-]\s*"
    rf"(?P<tn>{_TN_VAL})\s*(?:toneladas?|tn\.?)",
    re.IGNORECASE,
)


@dataclass
class AsignacionCuota:
    """Par empresa → cuota en una distribución de CITC."""

    empresa: str
    toneladas_tn: float
    especie: str | None = None  # inferible de especies_mencionadas de la Decision


@dataclass
class Decision:
    """Una decisión tomada en la sesión del CFP."""

    texto: str
    tipo: str  # unanimidad | mayoria | aprobacion | otro
    agenda_punto: str | None = None  # "1.1.3" etc.
    tema: str | None = None  # descripción del punto de agenda
    fecha: str | None = None  # fecha específica de la resolución (ISO 8601)
    sesion_idx: int = 0  # índice de sesión (0 = primera, >0 = multi-sesión)
    especies_mencionadas: list[str] = field(default_factory=list)
    empresas_mencionadas: list[str] = field(default_factory=list)
    toneladas: list[float] = field(default_factory=list)
    tiene_citc: bool = False
    referencias_res_cfp: list[str] = field(default_factory=list)
    votos_favor: list[str] = field(default_factory=list)  # quiénes votaron a favor (explícito)
    votos_en_contra: list[str] = field(default_factory=list)  # quiénes votaron en contra
    abstenciones: list[str] = field(default_factory=list)  # quiénes se abstuvieron
    institucion_votos: dict[str, str] = field(
        default_factory=dict
    )  # institución → "favor"|"contra"|"abstencion"
    numero_resolucion: str | None = None  # "15/2025" — resolución CFP que genera esta decisión
    es_diferida: bool = False  # tratamiento postergado para próxima sesión
    es_denegada: bool = False  # solicitud rechazada/no aprobada
    fundamento_inidep: list[str] = field(default_factory=list)  # informes INIDEP citados
    zona_captura: list[str] = field(default_factory=list)  # zonas/áreas geográficas de pesca
    periodo_vigencia_inicio: str | None = (
        None  # inicio de vigencia ISO parcial: "YYYY", "YYYY-MM", "YYYY-MM-DD"
    )
    periodo_vigencia_fin: str | None = None  # fin de vigencia ISO parcial
    asignaciones: list[AsignacionCuota] = field(default_factory=list)  # empresa → tn en distribuciones CITC


@dataclass
class Acta:
    filename: str
    year: int
    numero: str | None = None  # "34" de "ACTA CFP N° 34/2025"
    fecha: str | None = None
    lugar: str | None = None
    quorum: int | None = None
    texto_completo: str = ""
    miembros_presentes: list[str] = field(default_factory=list)
    decisiones: list[Decision] = field(default_factory=list)
    # Alias para compatibilidad con el resto del sistema
    resoluciones: list[Decision] = field(default_factory=list)
    # Multi-sesión
    es_multi_sesion: bool = False
    n_sesiones: int = 1


def parse_fecha(text: str) -> str | None:
    m = RE_FECHA.search(text)
    if m:
        day, month_name, year = m.groups()
        month = MESES.get(month_name.lower())
        if month:
            return f"{year}-{month:02d}-{int(day):02d}"
    return None


def parse_numero_acta(text: str) -> str | None:
    m = re.search(r"ACTA\s+CFP\s+N[°º]\s*(\d+)/(\d{4})", text[:500])
    if m:
        return m.group(1)
    return None


def parse_quorum(text: str) -> int | None:
    m = RE_QUORUM.search(text[:2000])
    if m:
        return int(m.group(2))
    return None


def parse_miembros(text: str) -> list[str]:
    """Extrae miembros presentes del encabezado."""
    presentes_match = re.search(
        r"Se encuentran presentes:(.+?)(?:También se encuentran|Con un quórum|\Z)",
        text[:3000],
        re.DOTALL | re.IGNORECASE,
    )
    miembros = []
    if presentes_match:
        bloque = presentes_match.group(1)
        # Extraer nombres con cargo (patrones: "el Lic. Juan García," o "la Dra. María López,")
        for frag in re.split(r",\s*(?:el |la |los |las )", bloque):
            frag = frag.strip()
            if 10 < len(frag) < 120:
                miembros.append(frag)
    return miembros[:15]


def parse_fecha_inline(text: str) -> str | None:
    """
    Extrae fecha específica del cuerpo de una resolución.

    Detecta formatos como "15 de marzo de 2025" o "Buenos Aires, 15 de marzo de 2025".
    Retorna ISO 8601 (YYYY-MM-DD) o None.
    """
    m = RE_FECHA_INLINE.search(text or "")
    if m:
        day, month_name, year = m.groups()
        month = MESES.get(month_name.lower())
        if month:
            return f"{year}-{month:02d}-{int(day):02d}"
    return None


def parse_votos_en_contra(text: str) -> list[str]:
    """
    Extrae las representaciones o nombres que votaron en contra.

    Detecta: "con el voto en contra de la Provincia de Chubut",
    "con la disidencia del representante de la industria", etc.
    """
    resultados = []
    for m in RE_VOTO_CONTRA.finditer(text or ""):
        frag = m.group(1).strip().rstrip(".,;")
        if 3 < len(frag) < 120:
            resultados.append(frag)
    return resultados


def parse_abstenciones(text: str) -> list[str]:
    """Extrae abstenciones nombradas en el texto de una decisión."""
    resultados = []
    for m in RE_ABSTENCION.finditer(text or ""):
        frag = m.group(1).strip().rstrip(".,;")
        if 3 < len(frag) < 120:
            resultados.append(frag)
    return resultados


def parse_votos_favor(text: str) -> list[str]:
    """Extrae votos explícitamente a favor mencionados en el texto de una decisión."""
    resultados = []
    for m in RE_VOTO_FAVOR.finditer(text or ""):
        frag = m.group(1).strip().rstrip(".,;")
        if 3 < len(frag) < 150:
            resultados.append(frag)
    return resultados


def normalizar_institucion(texto: str) -> str:
    """Normaliza un fragmento de texto al nombre canónico de institución CFP."""
    tl = texto.lower().strip()
    for key, canon in _NORM_INSTITUCIONES.items():
        if key in tl:
            return canon
    return texto.strip().title()


def build_institucion_votos(
    votos_favor: list[str],
    votos_contra: list[str],
    abstenciones: list[str],
) -> dict[str, str]:
    """
    Construye mapa institución → sentido de voto.

    El orden de prioridad en caso de solapamiento: contra > abstencion > favor.
    """
    result: dict[str, str] = {}
    for v in votos_favor:
        result[normalizar_institucion(v)] = "favor"
    for v in abstenciones:
        result[normalizar_institucion(v)] = "abstencion"
    for v in votos_contra:
        result[normalizar_institucion(v)] = "contra"
    return result


def parse_numero_resolucion(text: str) -> str | None:
    """
    Extrae el número de la Resolución CFP que genera esta decisión.

    Distingue entre la resolución que SE DICTA en este punto (verbo dictar/emitir)
    y las resoluciones pasadas que sólo se mencionan como antecedentes.
    Retorna "15/2025" o None si no se dicta ninguna resolución.
    """
    m = RE_NUMERO_RESOLUCION.search(text or "")
    return m.group(1) if m else None


def parse_es_diferida(text: str) -> bool:
    """Indica si el punto fue postergado/diferido para otra sesión."""
    return bool(RE_DIFERIDA.search(text or ""))


def parse_es_denegada(text: str) -> bool:
    """Indica si la solicitud fue rechazada o no aprobada."""
    return bool(RE_DENEGADA.search(text or ""))


def parse_fundamento_inidep(text: str) -> list[str]:
    """
    Extrae referencias a informes/dictámenes del INIDEP citados como fundamento.

    Retorna lista de strings completos tipo "Informe INIDEP N° 36/2024".
    Solo captura citas con número identificador (útiles para trazabilidad).
    """
    seen: set[str] = set()
    result = []
    for m in RE_FUNDAMENTO_INIDEP.finditer(text or ""):
        ref = m.group(0).strip()
        if ref not in seen:
            seen.add(ref)
            result.append(ref)
    return result


def parse_zona_captura(text: str) -> list[str]:
    """
    Extrae zonas/áreas de pesca mencionadas en el texto de una decisión.

    Cubre áreas nombradas del CFP (Norpatagónica, Patagónica), sub-áreas FAO
    (41.3.1, 48.3), ZEE Argentina, plataforma/talud continental y aguas provinciales.
    """
    seen: set[str] = set()
    result = []
    for m in RE_ZONA_CAPTURA.finditer(text or ""):
        zona = " ".join(m.group(0).split())  # normalizar espacios
        key = zona.lower()
        if key not in seen:
            seen.add(key)
            result.append(zona)
    return result


def parse_periodo_vigencia(text: str) -> tuple[str | None, str | None]:
    """
    Extrae el período de vigencia de una decisión.

    Retorna (inicio, fin) en formato ISO parcial: "YYYY", "YYYY-MM" o "YYYY-MM-DD".
    El primer patrón que hace match gana; el resto se ignora para evitar conflictos.
    """
    if not text:
        return None, None

    # "temporada 2024/2025" o "período 2024-2025"
    m = re.search(r"(?:temporada|per[ií]odo)\s+(\d{4})[-/](\d{4})", text, re.IGNORECASE)
    if m:
        return m.group(1), m.group(2)

    # "para el año 2025" / "por el ejercicio 2025"
    m = re.search(
        r"(?:para|por|durante|en)\s+el\s+(?:año|per[ií]odo|ejercicio)\s+(\d{4})\b",
        text,
        re.IGNORECASE,
    )
    if m:
        anio = m.group(1)
        return anio, anio

    # "primer semestre de 2025"
    m = re.search(r"primer\s+semestre\s+(?:del?\s+)?(\d{4})", text, re.IGNORECASE)
    if m:
        return f"{m.group(1)}-01", f"{m.group(1)}-06"

    # "segundo semestre de 2025"
    m = re.search(r"segundo\s+semestre\s+(?:del?\s+)?(\d{4})", text, re.IGNORECASE)
    if m:
        return f"{m.group(1)}-07", f"{m.group(1)}-12"

    # "enero a junio de 2025" / "enero-junio 2025"
    _m_pat = r"(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)"
    m = re.search(
        _m_pat + r"\s+(?:a|al?|hasta|-)\s+" + _m_pat + r"\s+(?:de\s+)?(\d{4})",
        text,
        re.IGNORECASE,
    )
    if m:
        mes_ini = MESES.get(m.group(1).lower())
        mes_fin = MESES.get(m.group(2).lower())
        anio = m.group(3)
        if mes_ini and mes_fin:
            return f"{anio}-{mes_ini:02d}", f"{anio}-{mes_fin:02d}"

    # "hasta el 31 de marzo de 2025"
    m = re.search(
        rf"(?:vigente\s+)?hasta\s+el\s+(\d{{1,2}})\s+de\s+({_MESES_PAT})\s+de\s+(\d{{4}})",
        text,
        re.IGNORECASE,
    )
    if m:
        mes = MESES.get(m.group(2).lower())
        if mes:
            return None, f"{m.group(3)}-{mes:02d}-{int(m.group(1)):02d}"

    # "a partir del 1 de enero de 2025"
    m = re.search(
        rf"a\s+partir\s+del?\s+(\d{{1,2}})°?\s+de\s+({_MESES_PAT})\s+de\s+(\d{{4}})",
        text,
        re.IGNORECASE,
    )
    if m:
        mes = MESES.get(m.group(2).lower())
        if mes:
            return f"{m.group(3)}-{mes:02d}-{int(m.group(1)):02d}", None

    return None, None


def _tn_str_to_float(s: str) -> float | None:
    """Convierte "12.345" o "12,5" a float; devuelve None si está fuera de rango."""
    try:
        val = float(s.replace(".", "").replace(",", "."))
        return val if 0 < val < 5_000_000 else None
    except ValueError:
        return None


def parse_asignaciones_cuota(text: str) -> list[AsignacionCuota]:
    """
    Extrae pares empresa → toneladas de distribuciones de CITC.

    Cubre tres patrones:
    - Directa: "asignar/adjudicar a EMPRESA N toneladas"
    - Inversa: "N toneladas a/para EMPRESA"
    - Tabla: "EMPRESA: N toneladas" (solo en bloques que contengan CITC)
    Requiere sufijo legal (S.A., S.R.L., etc.) para evitar falsos positivos.
    """
    if not text:
        return []

    seen: set[tuple[str, float]] = set()
    result: list[AsignacionCuota] = []

    def _add(empresa: str, tn_str: str) -> None:
        empresa = empresa.strip().rstrip(",;")
        tn = _tn_str_to_float(tn_str)
        if tn is None or not empresa:
            return
        key = (empresa[:30].lower(), tn)
        if key not in seen:
            seen.add(key)
            result.append(AsignacionCuota(empresa=empresa, toneladas_tn=tn))

    for m in RE_ASIGNACION_DIRECTA.finditer(text):
        _add(m.group("empresa"), m.group("tn"))

    for m in RE_ASIGNACION_INVERSA.finditer(text):
        _add(m.group("empresa"), m.group("tn"))

    if RE_CITC.search(text):
        for m in RE_ASIGNACION_TABLA.finditer(text):
            _add(m.group("empresa"), m.group("tn"))

    return result


def parse_sesiones(text: str) -> list[str]:
    """
    Divide el texto de un acta en bloques por sesión.

    Detecta marcadores de inicio/cierre de sesión para identificar plenarios
    que se extienden a múltiples jornadas o incluyen sesiones extraordinarias.
    Retorna lista de bloques de texto, uno por sesión.
    """
    # Buscar posiciones de inicio y cierre de sesión
    inicios = [m.start() for m in RE_INICIO_SESION.finditer(text)]
    cierres = [m.start() for m in RE_CIERRE_SESION.finditer(text)]

    if len(inicios) <= 1 and len(cierres) <= 1:
        return [text]  # Sesión única

    # Construir bloques entre inicio y cierre
    puntos_corte = sorted(set(inicios + cierres))
    if not puntos_corte:
        return [text]

    bloques = []
    prev = 0
    for corte in puntos_corte[1:]:
        bloque = text[prev:corte].strip()
        if len(bloque) > 100:
            bloques.append(bloque)
        prev = corte
    # Último bloque
    ultimo = text[prev:].strip()
    if len(ultimo) > 100:
        bloques.append(ultimo)

    return bloques if bloques else [text]


def classify_decision(texto: str) -> str:
    """Clasifica el tipo de decisión."""
    tl = texto.lower()
    if RE_DENEGADA.search(texto):
        return "denegada"
    if RE_DIFERIDA.search(texto):
        return "diferida"
    if "unanimidad" in tl:
        return "unanimidad"
    if "mayoría" in tl or "mayoria" in tl:
        return "mayoria"
    if "aprueba" in tl or "aprob" in tl:
        return "aprobacion"
    if "citc" in tl or "cuota" in tl or "captura máxima" in tl:
        return "cuota_captura"
    if "veda" in tl or "prohibi" in tl:
        return "veda"
    if "permiso" in tl or "habilitación" in tl or "buque" in tl:
        return "habilitacion_buque"
    return "otro"


def extract_referencias_cfp(text: str) -> list[str]:
    """Extrae referencias a Resoluciones/Actas CFP previas."""
    return list(
        set(re.findall(r"(?:Resolución|Acta)\s+CFP\s+N[°º]\s*[\d/]+", text, re.IGNORECASE))
    )[:10]


def extract_toneladas(texto: str) -> list[float]:
    result = []
    for m in RE_TONELADAS.finditer(texto):
        try:
            val = float(m.group(1).replace(".", "").replace(",", "."))
            if 0 < val < 5_000_000:
                result.append(val)
        except ValueError:
            pass
    return result


def parse_decisions(text: str, sesion_idx: int = 0) -> list[Decision]:
    """Extrae todas las decisiones del texto de un acta (o bloque de sesión)."""
    decisions = []

    # Estrategia 1: buscar patrones "se decide por unanimidad"
    for m in RE_DECISION.finditer(text):
        # Incluir contexto previo (200 chars) para capturar fecha y votos
        ctx_start = max(0, m.start() - 200)
        ctx = text[ctx_start : m.end()]
        texto = m.group(1).strip()[:800]
        especies = list({x.lower() for x in RE_ESPECIE.findall(texto)})
        empresas = list({e.strip() for e in RE_EMPRESA.findall(texto)})
        d = Decision(
            texto=texto,
            tipo="unanimidad",
            fecha=parse_fecha_inline(ctx),
            sesion_idx=sesion_idx,
            especies_mencionadas=especies,
            empresas_mencionadas=empresas,
            toneladas=extract_toneladas(texto),
            tiene_citc=bool(RE_CITC.search(texto)),
            referencias_res_cfp=extract_referencias_cfp(texto),
            votos_favor=parse_votos_favor(ctx),
            votos_en_contra=parse_votos_en_contra(texto),
            abstenciones=parse_abstenciones(texto),
            institucion_votos=build_institucion_votos(
                parse_votos_favor(ctx),
                parse_votos_en_contra(texto),
                parse_abstenciones(texto),
            ),
            numero_resolucion=parse_numero_resolucion(ctx),
            es_diferida=parse_es_diferida(texto),
            es_denegada=parse_es_denegada(texto),
            fundamento_inidep=parse_fundamento_inidep(ctx),
            zona_captura=parse_zona_captura(ctx),
            periodo_vigencia_inicio=parse_periodo_vigencia(ctx)[0],
            periodo_vigencia_fin=parse_periodo_vigencia(ctx)[1],
            asignaciones=parse_asignaciones_cuota(ctx),
        )
        decisions.append(d)

    # Estrategia 2: buscar puntos de agenda con su decisión
    agenda_blocks = _split_by_agenda(text)
    for punto, tema, bloque in agenda_blocks:
        if not any(
            kw in bloque.lower()
            for kw in ["unanimidad", "aprueba", "acuerda", "resuelve", "autoriza", "instruye"]
        ):
            continue
        decisiones_en_bloque = re.findall(
            r"se (?:decide|aprueba|acuerda|resuelve|autoriza|establece|instruye)"
            r"(?:\s+por unanimidad)?[,\s]*(.{10,600}?)(?=\n\n|\nA continuación|\Z)",
            bloque,
            re.IGNORECASE | re.DOTALL,
        )
        for texto_dec in decisiones_en_bloque:
            texto_dec = texto_dec.strip()[:800]
            if any(d.texto[:100] == texto_dec[:100] for d in decisions):
                continue  # Ya capturado
            especies = list({x.lower() for x in RE_ESPECIE.findall(bloque)})
            empresas = list({e.strip() for e in RE_EMPRESA.findall(bloque)})
            d = Decision(
                texto=texto_dec,
                tipo=classify_decision(texto_dec),
                agenda_punto=punto,
                tema=tema[:150] if tema else None,
                fecha=parse_fecha_inline(bloque),
                sesion_idx=sesion_idx,
                especies_mencionadas=especies,
                empresas_mencionadas=empresas,
                toneladas=extract_toneladas(bloque),
                tiene_citc=bool(RE_CITC.search(bloque)),
                referencias_res_cfp=extract_referencias_cfp(bloque),
                votos_favor=parse_votos_favor(bloque),
                votos_en_contra=parse_votos_en_contra(texto_dec),
                abstenciones=parse_abstenciones(texto_dec),
                institucion_votos=build_institucion_votos(
                    parse_votos_favor(bloque),
                    parse_votos_en_contra(texto_dec),
                    parse_abstenciones(texto_dec),
                ),
                numero_resolucion=parse_numero_resolucion(bloque),
                es_diferida=parse_es_diferida(texto_dec),
                es_denegada=parse_es_denegada(texto_dec),
                fundamento_inidep=parse_fundamento_inidep(bloque),
                zona_captura=parse_zona_captura(bloque),
                periodo_vigencia_inicio=parse_periodo_vigencia(bloque)[0],
                periodo_vigencia_fin=parse_periodo_vigencia(bloque)[1],
                asignaciones=parse_asignaciones_cuota(bloque),
            )
            decisions.append(d)

    # Estrategia 3: puntos de agenda diferidos o denegados (no capturados aún)
    for punto, tema, bloque in agenda_blocks:
        if any(d.agenda_punto == punto for d in decisions):
            continue  # ya capturado por estrategia 2
        if not (RE_DIFERIDA.search(bloque) or RE_DENEGADA.search(bloque)):
            continue
        especies = list({x.lower() for x in RE_ESPECIE.findall(bloque)})
        empresas = list({e.strip() for e in RE_EMPRESA.findall(bloque)})
        d = Decision(
            texto=bloque.strip()[:800],
            tipo=classify_decision(bloque),
            agenda_punto=punto,
            tema=tema[:150] if tema else None,
            fecha=parse_fecha_inline(bloque),
            sesion_idx=sesion_idx,
            especies_mencionadas=especies,
            empresas_mencionadas=empresas,
            toneladas=extract_toneladas(bloque),
            tiene_citc=bool(RE_CITC.search(bloque)),
            referencias_res_cfp=extract_referencias_cfp(bloque),
            votos_favor=parse_votos_favor(bloque),
            votos_en_contra=parse_votos_en_contra(bloque),
            abstenciones=parse_abstenciones(bloque),
            institucion_votos=build_institucion_votos(
                parse_votos_favor(bloque),
                parse_votos_en_contra(bloque),
                parse_abstenciones(bloque),
            ),
            numero_resolucion=parse_numero_resolucion(bloque),
            es_diferida=parse_es_diferida(bloque),
            es_denegada=parse_es_denegada(bloque),
            fundamento_inidep=parse_fundamento_inidep(bloque),
            zona_captura=parse_zona_captura(bloque),
            periodo_vigencia_inicio=parse_periodo_vigencia(bloque)[0],
            periodo_vigencia_fin=parse_periodo_vigencia(bloque)[1],
            asignaciones=parse_asignaciones_cuota(bloque),
        )
        decisions.append(d)

    return decisions


def _split_by_agenda(text: str) -> list[tuple[str, str, str]]:
    """Divide el texto en bloques por punto de agenda."""
    # Buscar encabezados de agenda: "1.\nTITULO" o "1.2. Titulo"
    pattern = re.compile(r"^(\d+(?:\.\d+)*)\.\s*\n?([^\n]{3,100})\n", re.MULTILINE)
    matches = list(pattern.finditer(text))
    blocks = []
    for i, m in enumerate(matches):
        punto = m.group(1)
        tema = m.group(2).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        bloque = text[start:end]
        if len(bloque) > 50:
            blocks.append((punto, tema, bloque))
    return blocks


def parse_acta(text: str, filename: str) -> Acta:
    """Parsea el texto completo de un acta y retorna estructura Acta."""
    year_match = re.search(r"(\d{4})", filename)
    year = int(year_match.group(1)) if year_match else 0

    # Detectar multi-sesión antes de parsear decisiones
    bloques_sesion = parse_sesiones(text)
    inicios_count = len(RE_INICIO_SESION.findall(text))
    cierres_count = len(RE_CIERRE_SESION.findall(text))
    es_multi = len(bloques_sesion) > 1 or inicios_count > 1 or cierres_count > 1
    n_sesiones = max(len(bloques_sesion), inicios_count if inicios_count > 1 else 1)

    # Parsear decisiones por bloque de sesión para etiquetar sesion_idx
    decisiones: list[Decision] = []
    for idx, bloque in enumerate(bloques_sesion):
        decisiones.extend(parse_decisions(bloque, sesion_idx=idx))

    acta = Acta(
        filename=filename,
        year=year,
        numero=parse_numero_acta(text),
        fecha=parse_fecha(text),
        texto_completo=text,
        quorum=parse_quorum(text),
        miembros_presentes=parse_miembros(text),
        decisiones=decisiones,
        resoluciones=decisiones,  # alias para compatibilidad
        es_multi_sesion=es_multi,
        n_sesiones=n_sesiones,
    )

    return acta


def batch_parse(text_dir: Path, output_dir: Path) -> int:
    """Parsea todos los .txt en text_dir y guarda JSON estructurado en output_dir."""
    text_dir = Path(text_dir)
    output_dir = Path(output_dir)
    count = 0

    for txt_path in sorted(text_dir.rglob("*.txt")):
        try:
            text = txt_path.read_text(encoding="utf-8")
            acta = parse_acta(text, txt_path.name)

            rel = txt_path.relative_to(text_dir)
            out_path = output_dir / rel.with_suffix(".json")
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(
                json.dumps(asdict(acta), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            count += 1
            logger.debug(f"  {txt_path.name}: {len(acta.decisiones)} decisiones")
        except Exception as exc:
            logger.error(f"Error parseando {txt_path.name}: {exc}")

    logger.info(f"Parseados {count} documentos")
    return count
