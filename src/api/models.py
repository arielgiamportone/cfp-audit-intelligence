"""
Modelos Pydantic de respuesta para la API REST del CFP Audit Intelligence.
"""

from pydantic import BaseModel, Field

# ── Actas ─────────────────────────────────────────────────────────────────────


class ActaOut(BaseModel):
    id: int
    year: int
    nombre: str
    url: str | None = None
    filename: str | None = None
    download_status: str | None = None
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
    numero: str | None = None
    tipo: str | None = None
    categoria: str | None = None
    texto_resumen: str | None = None
    votos_favor: int | None = None
    votos_contra: int | None = None
    quorum: int | None = None
    riesgo_score: float | None = None
    year: int | None = None

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
    nombre_norm: str | None = None
    menciones: int = 0

    model_config = {"from_attributes": True}


class EntidadListOut(BaseModel):
    total: int
    items: list[EntidadOut]


# ── Alertas ───────────────────────────────────────────────────────────────────


class AlertaOut(BaseModel):
    id: int
    tipo: str
    especie: str | None = None
    zona: str | None = None
    year: int | None = None
    valor_detectado: float | None = None
    umbral: float | None = None
    mensaje: str
    severidad: str
    acta_referencia: str | None = None
    resuelta: bool = False
    created_at: str | None = None
    regla_nombre: str | None = None

    model_config = {"from_attributes": True}


class AlertaListOut(BaseModel):
    total: int
    items: list[AlertaOut]


# ── INIDEP / Comparaciones ────────────────────────────────────────────────────


class INIDEPEvalOut(BaseModel):
    id: int
    especie: str
    especie_code: str
    zona: str | None = None
    year: int
    cba_recomendada_tn: float | None = None
    estado_stock: str | None = None
    numero_ito: str | None = None

    model_config = {"from_attributes": True}


class ComparacionOut(BaseModel):
    id: int
    especie: str
    especie_code: str
    zona: str | None = None
    year: int
    cba_inidep_tn: float | None = None
    cmp_cfp_tn: float | None = None
    diferencia_tn: float | None = None
    ratio_sobreasignacion: float | None = None
    nivel_alerta: str | None = None
    descripcion_alerta: str | None = None

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
    year_desde: int | None = None
    year_hasta: int | None = None


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
