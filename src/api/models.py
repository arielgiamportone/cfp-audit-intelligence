"""
Modelos Pydantic de respuesta para la API REST del CFP Audit Intelligence.
"""
from typing import Optional
from pydantic import BaseModel, Field


# ── Actas ─────────────────────────────────────────────────────────────────────

class ActaOut(BaseModel):
    id: int
    year: int
    nombre: str
    url: Optional[str] = None
    filename: Optional[str] = None
    download_status: Optional[str] = None
    text_extracted: bool = False
    embedded: bool = False
    analyzed: bool = False

    model_config = {"from_attributes": True}


class ActaListOut(BaseModel):
    total: int
    items: list[ActaOut]
    page: int
    page_size: int


# ── Resoluciones ──────────────────────────────────────────────────────────────

class ResolucionOut(BaseModel):
    id: int
    acta_id: int
    numero: Optional[str] = None
    tipo: Optional[str] = None
    categoria: Optional[str] = None
    texto_resumen: Optional[str] = None
    votos_favor: Optional[int] = None
    votos_contra: Optional[int] = None
    quorum: Optional[int] = None
    riesgo_score: Optional[float] = None
    year: Optional[int] = None

    model_config = {"from_attributes": True}


class ResolucionListOut(BaseModel):
    total: int
    items: list[ResolucionOut]
    page: int
    page_size: int


# ── Entidades ─────────────────────────────────────────────────────────────────

class EntidadOut(BaseModel):
    id: int
    tipo: str
    nombre: str
    nombre_norm: Optional[str] = None
    menciones: int = 0

    model_config = {"from_attributes": True}


class EntidadListOut(BaseModel):
    total: int
    items: list[EntidadOut]


# ── Alertas ───────────────────────────────────────────────────────────────────

class AlertaOut(BaseModel):
    id: int
    tipo: str
    especie: Optional[str] = None
    zona: Optional[str] = None
    year: Optional[int] = None
    valor_detectado: Optional[float] = None
    umbral: Optional[float] = None
    mensaje: str
    severidad: str
    acta_referencia: Optional[str] = None
    resuelta: bool = False
    created_at: Optional[str] = None
    regla_nombre: Optional[str] = None

    model_config = {"from_attributes": True}


class AlertaListOut(BaseModel):
    total: int
    items: list[AlertaOut]


# ── INIDEP / Comparaciones ────────────────────────────────────────────────────

class INIDEPEvalOut(BaseModel):
    id: int
    especie: str
    especie_code: str
    zona: Optional[str] = None
    year: int
    cba_recomendada_tn: Optional[float] = None
    estado_stock: Optional[str] = None
    numero_ito: Optional[str] = None

    model_config = {"from_attributes": True}


class ComparacionOut(BaseModel):
    id: int
    especie: str
    especie_code: str
    zona: Optional[str] = None
    year: int
    cba_inidep_tn: Optional[float] = None
    cmp_cfp_tn: Optional[float] = None
    diferencia_tn: Optional[float] = None
    ratio_sobreasignacion: Optional[float] = None
    nivel_alerta: Optional[str] = None
    descripcion_alerta: Optional[str] = None

    model_config = {"from_attributes": True}


class ComparacionListOut(BaseModel):
    total: int
    items: list[ComparacionOut]


# ── NER ───────────────────────────────────────────────────────────────────────

class NERRequest(BaseModel):
    texto: str = Field(..., min_length=1, max_length=50_000, description="Texto a analizar")

class NEREntidadOut(BaseModel):
    texto: str
    etiqueta: str
    inicio: int
    fin: int

class NERResponse(BaseModel):
    especies: list[str]
    empresas: list[str]
    zonas: list[str]
    cuotas: list[str]
    normativas: list[str]
    buques: list[str]
    entidades_raw: list[NEREntidadOut]


# ── Búsqueda ──────────────────────────────────────────────────────────────────

class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    n_results: int = Field(default=10, ge=1, le=50)
    year_desde: Optional[int] = None
    year_hasta: Optional[int] = None

class SearchResultOut(BaseModel):
    id: str
    texto: str
    distancia: float
    metadata: dict


class SearchResponse(BaseModel):
    query: str
    total: int
    results: list[SearchResultOut]


# ── Stats ─────────────────────────────────────────────────────────────────────

class StatsOut(BaseModel):
    total_actas: int
    actas_descargadas: int
    actas_procesadas: int
    actas_analizadas: int
    total_resoluciones: int
    total_entidades: int
    total_menciones: int
    años_cubiertos: list[int]
    alertas_abiertas: int
    alertas_criticas: int
