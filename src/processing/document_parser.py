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
from typing import Optional

from loguru import logger


# ── Patrones regex ajustados al formato real del CFP ─────────────────────────

RE_FECHA = re.compile(
    r"A los (\d{1,2}) días del mes de "
    r"(enero|febrero|marzo|abril|mayo|junio|julio|agosto|"
    r"septiembre|octubre|noviembre|diciembre) de (\d{4})",
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
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}


@dataclass
class Decision:
    """Una decisión tomada en la sesión del CFP."""
    texto: str
    tipo: str                               # unanimidad | mayoria | aprobacion | otro
    agenda_punto: Optional[str] = None      # "1.1.3" etc.
    tema: Optional[str] = None              # descripción del punto de agenda
    especies_mencionadas: list[str] = field(default_factory=list)
    empresas_mencionadas: list[str] = field(default_factory=list)
    toneladas: list[float] = field(default_factory=list)
    tiene_citc: bool = False
    referencias_res_cfp: list[str] = field(default_factory=list)


@dataclass
class Acta:
    filename: str
    year: int
    numero: Optional[str] = None           # "34" de "ACTA CFP N° 34/2025"
    fecha: Optional[str] = None
    lugar: Optional[str] = None
    quorum: Optional[int] = None
    texto_completo: str = ""
    miembros_presentes: list[str] = field(default_factory=list)
    decisiones: list[Decision] = field(default_factory=list)
    # Alias para compatibilidad con el resto del sistema
    resoluciones: list[Decision] = field(default_factory=list)


def parse_fecha(text: str) -> Optional[str]:
    m = RE_FECHA.search(text)
    if m:
        day, month_name, year = m.groups()
        month = MESES.get(month_name.lower())
        if month:
            return f"{year}-{month:02d}-{int(day):02d}"
    return None


def parse_numero_acta(text: str) -> Optional[str]:
    m = re.search(r"ACTA\s+CFP\s+N[°º]\s*(\d+)/(\d{4})", text[:500])
    if m:
        return m.group(1)
    return None


def parse_quorum(text: str) -> Optional[int]:
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


def classify_decision(texto: str) -> str:
    """Clasifica el tipo de decisión."""
    tl = texto.lower()
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
    return list(set(re.findall(
        r"(?:Resolución|Acta)\s+CFP\s+N[°º]\s*[\d/]+",
        text, re.IGNORECASE
    )))[:10]


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


def parse_decisions(text: str) -> list[Decision]:
    """Extrae todas las decisiones del texto de un acta."""
    decisions = []

    # Estrategia 1: buscar patrones "se decide por unanimidad"
    for m in RE_DECISION.finditer(text):
        texto = m.group(1).strip()[:800]
        especies = list({x.lower() for x in RE_ESPECIE.findall(texto)})
        empresas = list({e.strip() for e in RE_EMPRESA.findall(texto)})
        d = Decision(
            texto=texto,
            tipo="unanimidad",
            especies_mencionadas=especies,
            empresas_mencionadas=empresas,
            toneladas=extract_toneladas(texto),
            tiene_citc=bool(RE_CITC.search(texto)),
            referencias_res_cfp=extract_referencias_cfp(texto),
        )
        decisions.append(d)

    # Estrategia 2: buscar puntos de agenda con su decisión
    agenda_blocks = _split_by_agenda(text)
    for punto, tema, bloque in agenda_blocks:
        if not any(kw in bloque.lower() for kw in
                   ["unanimidad", "aprueba", "acuerda", "resuelve", "autoriza", "instruye"]):
            continue
        # Extraer la parte de la decisión (después del contexto)
        decisiones_en_bloque = re.findall(
            r"se (?:decide|aprueba|acuerda|resuelve|autoriza|establece|instruye)"
            r"(?:\s+por unanimidad)?[,\s]*(.{10,600}?)(?=\n\n|\nA continuación|\Z)",
            bloque, re.IGNORECASE | re.DOTALL
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
                especies_mencionadas=especies,
                empresas_mencionadas=empresas,
                toneladas=extract_toneladas(bloque),
                tiene_citc=bool(RE_CITC.search(bloque)),
                referencias_res_cfp=extract_referencias_cfp(bloque),
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

    decisiones = parse_decisions(text)

    acta = Acta(
        filename=filename,
        year=year,
        numero=parse_numero_acta(text),
        fecha=parse_fecha(text),
        texto_completo=text,
        quorum=parse_quorum(text),
        miembros_presentes=parse_miembros(text),
        decisiones=decisiones,
        resoluciones=decisiones,   # alias para compatibilidad
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
