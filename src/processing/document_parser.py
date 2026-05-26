"""
Parser de documentos del CFP: extrae estructura de actas en resoluciones individuales.

Las actas del CFP tienen formato semi-estructurado:
  - Encabezado: fecha, lugar, miembros presentes, quórum
  - Cuerpo: resoluciones formales ("Número de Registro CFP X/YYYY") y
            decisiones del cuerpo ("se decide por unanimidad...")
  - Pie: firma de los miembros

Estrategia de extracción:
  1. Resoluciones formales: buscar "Número de Registro CFP X/YYYY" y extraer
     el proyecto de resolución previo (hasta 3000 chars atrás).
  2. Decisiones del cuerpo: buscar "se decide [por unanimidad]" y extraer
     el contexto circundante como unidad de conocimiento.
"""
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from loguru import logger


# ── Patrones regex para parsing ───────────────────────────────────────────────

# Resoluciones formales con número de registro oficial
RE_NUMERO_REGISTRO = re.compile(
    r"[Nn]úmero\s+de\s+[Rr]egistro\s+CFP\s+(\d+)/(\d{4})",
)

# Inicio de proyecto de resolución formal
RE_INICIO_PROYECTO = re.compile(
    r"(?:se\s+da\s+tratamiento\s+a\s+un\s+proyecto|"
    r"trat[aó]\s+(?:el\s+)?proyecto\s+de\s+resolución|"
    r"proyecto\s+de\s+resolución\s+a\s+través)",
    re.IGNORECASE,
)

# Decisiones del cuerpo del acta (sin número formal)
RE_SE_DECIDE = re.compile(
    r"(?:se\s+decide|Se\s+decide)(?:\s+por\s+unanimidad|\s+instruir|\s+requerir|\s+comunicar)?",
    re.IGNORECASE,
)

RE_FECHA = re.compile(
    r"(\d{1,2})\s+de\s+(enero|febrero|marzo|abril|mayo|junio|julio|agosto|"
    r"septiembre|octubre|noviembre|diciembre)\s+de\s+(\d{4})",
    re.IGNORECASE,
)

RE_QUORUM = re.compile(r"qu[oó]rum\s*(?:de)?\s*(\d+)", re.IGNORECASE)

RE_VOTOS = re.compile(
    r"(\d+)\s+voto[s]?\s+(?:a\s+favor|en\s+favor|afirmativo[s]?)"
    r"(?:.*?(\d+)\s+(?:en\s+contra|negativo[s]?))?",
    re.IGNORECASE,
)

RE_ESPECIE = re.compile(
    r"\b(merluza(?:\s+(?:hubbsi|de\s+cola|negra))?|langostino|calamar"
    r"|abadejo|polaca|corvina|anchoita|caballa|salmon|pejerrey|centolla"
    r"|vieira|mariscos?|moluscos?)\b",
    re.IGNORECASE,
)

RE_CUOTA = re.compile(
    r"(\d[\d\.,]*)\s*(?:toneladas?|tn\.?|t\.?)(?:\s*métricas?)?",
    re.IGNORECASE,
)

MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}


@dataclass
class Resolucion:
    numero: str
    year: int
    texto: str
    fecha_acta: Optional[str] = None
    tipo: Optional[str] = None
    votos_favor: Optional[int] = None
    votos_contra: Optional[int] = None
    abstenciones: Optional[int] = None
    quorum: Optional[int] = None
    especies_mencionadas: list[str] = field(default_factory=list)
    cuotas_toneladas: list[float] = field(default_factory=list)
    empresas_mencionadas: list[str] = field(default_factory=list)


@dataclass
class Acta:
    filename: str
    year: int
    fecha: Optional[str] = None
    lugar: Optional[str] = None
    quorum: Optional[int] = None
    texto_completo: str = ""
    resoluciones: list[Resolucion] = field(default_factory=list)
    miembros_presentes: list[str] = field(default_factory=list)


def parse_fecha(text: str) -> Optional[str]:
    m = RE_FECHA.search(text)
    if m:
        day, month_name, year = m.groups()
        month = MESES.get(month_name.lower())
        if month:
            return f"{year}-{month:02d}-{int(day):02d}"
    return None


def classify_resolucion(texto: str) -> str:
    """Clasifica el tipo de resolución según palabras clave."""
    texto_l = texto.lower()
    if any(k in texto_l for k in ["cuota", "captura máxima", "tonelada"]):
        return "cuota_captura"
    if any(k in texto_l for k in ["veda", "suspender", "suspensión"]):
        return "veda"
    if any(k in texto_l for k in ["habilitación", "permiso de pesca", "matricula"]):
        return "habilitacion_buque"
    if any(k in texto_l for k in ["área protegida", "zona de veda", "reserva"]):
        return "area_protegida"
    if any(k in texto_l for k in ["convenio", "acuerdo internacional", "tratado"]):
        return "convenio_internacional"
    if any(k in texto_l for k in ["investigación", "inidep", "científic"]):
        return "investigacion"
    if any(k in texto_l for k in ["sanción", "infracción", "multa"]):
        return "sancion"
    if any(k in texto_l for k in ["reglamento", "reglamentación", "resolución conjunta"]):
        return "reglamento"
    return "otro"


def extract_empresas(texto: str) -> list[str]:
    """Extrae nombres de empresas (heurística basada en patrones comunes del sector)."""
    empresas = []
    # S.A., S.R.L., S.A.C.I., Ltda., etc.
    pattern = re.compile(
        r"\b([A-ZÁÉÍÓÚÜÑ][a-záéíóúüñA-ZÁÉÍÓÚÜÑ\s\-\.]{2,40}?"
        r"(?:S\.A\.|S\.R\.L\.|S\.A\.C\.I\.|Ltda\.|SRL|SA))\b"
    )
    for m in pattern.finditer(texto):
        name = m.group(1).strip()
        if len(name) > 5:
            empresas.append(name)
    return list(set(empresas))


def parse_acta(text: str, filename: str) -> Acta:
    """Parsea el texto completo de un acta y retorna estructura Acta.

    Extrae dos tipos de contenido:
    - Resoluciones formales: bloques con "Número de Registro CFP X/YYYY"
    - Decisiones del cuerpo: frases "se decide [por unanimidad]..."
    """
    year_match = re.search(r"(\d{4})", filename)
    year = int(year_match.group(1)) if year_match else 0

    acta = Acta(
        filename=filename,
        year=year,
        fecha=parse_fecha(text),
        texto_completo=text,
        quorum=_extract_quorum(text),
        miembros_presentes=_extract_miembros(text),
    )

    # ── 1. Resoluciones formales (con número de registro oficial) ─────────────
    seen_registros: set[str] = set()
    for m in RE_NUMERO_REGISTRO.finditer(text):
        numero = m.group(1)
        res_year = int(m.group(2))
        key = f"{numero}/{res_year}"
        if key in seen_registros:
            continue
        seen_registros.add(key)

        # Buscar inicio del proyecto de resolución (hasta 3000 chars atrás)
        lookback_start = max(0, m.start() - 3000)
        preceding = text[lookback_start:m.end()]
        proyecto_m = list(RE_INICIO_PROYECTO.finditer(preceding))
        if proyecto_m:
            texto_res = preceding[proyecto_m[-1].start():]
        else:
            texto_res = text[max(0, m.start() - 1500):m.end()]

        votos_f, votos_c = _extract_votos(texto_res)
        especies = list({em.group(0).lower() for em in RE_ESPECIE.finditer(texto_res)})
        cuotas = _parse_cuotas(texto_res)

        acta.resoluciones.append(Resolucion(
            numero=numero,
            year=res_year,
            texto=texto_res[:2000],
            fecha_acta=acta.fecha,
            tipo=classify_resolucion(texto_res),
            votos_favor=votos_f,
            votos_contra=votos_c,
            especies_mencionadas=especies,
            cuotas_toneladas=cuotas,
            empresas_mencionadas=extract_empresas(texto_res),
        ))

    # ── 2. Decisiones del cuerpo (sin número formal) ─────────────────────────
    # Posiciones de resoluciones formales para evitar solapamiento
    formal_positions = {
        (max(0, m.start() - 3000), m.end())
        for m in RE_NUMERO_REGISTRO.finditer(text)
    }

    decision_count = 0
    for m in RE_SE_DECIDE.finditer(text):
        # Saltar si está dentro de un bloque de resolución formal
        in_formal = any(start <= m.start() <= end for start, end in formal_positions)
        if in_formal:
            continue

        # Extraer contexto: 300 chars antes + hasta el final del párrafo (~600 chars)
        ctx_start = max(0, m.start() - 300)
        # Avanzar hasta el final del párrafo (doble newline o 600 chars)
        rest = text[m.start():]
        para_end = re.search(r"\n\n|\Z", rest, re.DOTALL)
        ctx_end = m.start() + (para_end.start() if para_end else min(600, len(rest)))
        ctx_end = min(ctx_end, m.start() + 600)

        texto_res = text[ctx_start:ctx_end].strip()
        if len(texto_res) < 50:
            continue

        decision_count += 1
        votos_f, votos_c = _extract_votos(texto_res)
        especies = list({em.group(0).lower() for em in RE_ESPECIE.finditer(texto_res)})
        cuotas = _parse_cuotas(texto_res)

        acta.resoluciones.append(Resolucion(
            numero=f"D{decision_count}",
            year=year,
            texto=texto_res[:2000],
            fecha_acta=acta.fecha,
            tipo=classify_resolucion(texto_res),
            votos_favor=votos_f,
            votos_contra=votos_c,
            especies_mencionadas=especies,
            cuotas_toneladas=cuotas,
            empresas_mencionadas=extract_empresas(texto_res),
        ))

    n_formal = len(seen_registros)
    n_informal = decision_count
    if acta.resoluciones:
        logger.debug(
            f"  {filename}: {n_formal} resoluciones formales + {n_informal} decisiones"
        )
    else:
        logger.debug(f"  {filename}: sin resoluciones ni decisiones detectadas")
    return acta


def _parse_cuotas(texto: str) -> list[float]:
    result = []
    for m in RE_CUOTA.finditer(texto):
        try:
            result.append(float(m.group(1).replace(".", "").replace(",", ".")))
        except ValueError:
            pass
    return result


def _extract_quorum(text: str) -> Optional[int]:
    m = RE_QUORUM.search(text)
    return int(m.group(1)) if m else None


def _extract_votos(text: str) -> tuple[Optional[int], Optional[int]]:
    m = RE_VOTOS.search(text)
    if m:
        favor = int(m.group(1))
        contra = int(m.group(2)) if m.group(2) else 0
        return favor, contra
    return None, None


def _extract_miembros(text: str) -> list[str]:
    """Extrae lista de miembros presentes del encabezado."""
    miembros = []
    # Buscar sección típica de presentes
    presentes_match = re.search(
        r"(?:PRESENTES?|Se\s+encuentran\s+presentes?)[:\s]+(.+?)(?:\n\n|\Z)",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    if presentes_match:
        bloque = presentes_match.group(1)
        # Extraer líneas con nombre + cargo
        for line in bloque.split("\n"):
            line = line.strip()
            if len(line) > 10 and len(line) < 100:
                miembros.append(line)
    return miembros[:20]  # Máximo 20 miembros


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
        except Exception as exc:
            logger.error(f"Error parseando {txt_path.name}: {exc}")

    logger.info(f"Parseados {count} documentos")
    return count
