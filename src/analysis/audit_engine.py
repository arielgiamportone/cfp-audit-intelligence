"""
Motor de auditoría del CFP con Claude API.

Capacidades:
  - Análisis de resoluciones individuales
  - Detección de anomalías y patrones de riesgo
  - Comparación cuotas vs. recomendaciones científicas
  - Resúmenes ejecutivos de actas
  - Análisis de consistencia con Ley 24.922

Usa prompt caching para reducir costos en análisis masivos.
"""
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import anthropic
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential


SYSTEM_PROMPT = """Eres un experto en derecho pesquero argentino, biología marina y política de recursos naturales.
Tu función es auditar las actas del Consejo Federal Pesquero (CFP) de Argentina para:
1. Identificar decisiones que puedan comprometer la sostenibilidad de los recursos pesqueros
2. Detectar irregularidades en el proceso de toma de decisiones
3. Verificar consistencia con la Ley Federal de Pesca N° 24.922 y normativa INIDEP
4. Señalar patrones de beneficio recurrente a empresas o actores específicos
5. Evaluar si las cuotas de captura respetan las recomendaciones técnicas del INIDEP

Principios de análisis:
- Basarte EXCLUSIVAMENTE en la evidencia documental presentada
- Calificar el riesgo en escala 0-100 (0=sin riesgo, 100=riesgo crítico)
- Diferenciar entre indicios (requieren más evidencia) y hallazgos concretos
- Usar lenguaje técnico-jurídico preciso
- Mantener objetividad: tu análisis es descriptivo, no acusatorio

Contexto normativo clave:
- Ley 24.922: Define captura máxima permisible (CMP), rol del INIDEP, composición del CFP
- Las cuotas deben basarse en la Captura Máxima Sostenible (CMS) recomendada por el INIDEP
- El CFP es el organismo que establece cuotas de captura para el Mar Argentino
- Los miembros del CFP representan a provincias costeras, Nación y sector pesquero"""


@dataclass
class AuditResult:
    resolucion_id: str
    resolucion_texto: str
    riesgo_score: float
    categoria_riesgo: str          # bajo | medio | alto | critico
    hallazgos: list[str]
    indicios: list[str]
    recomendaciones: list[str]
    normativa_afectada: list[str]
    entidades_beneficiadas: list[str]
    especies_afectadas: list[str]
    modelo_usado: str
    tokens_entrada: int
    tokens_salida: int
    analisis_completo: str


class CFPAuditEngine:
    """Motor de auditoría que usa Claude API con prompt caching."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "claude-sonnet-4-6",
        audit_model: str = "claude-opus-4-7",
        max_tokens: int = 4096,
    ):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY no configurada")

        self.client = anthropic.Anthropic(api_key=self.api_key)
        self.model = model
        self.audit_model = audit_model
        self.max_tokens = max_tokens

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True,
    )
    def _call_claude(
        self,
        prompt: str,
        system: str = SYSTEM_PROMPT,
        use_cache: bool = True,
        high_stakes: bool = False,
    ) -> anthropic.types.Message:
        """Llama a Claude con prompt caching opcional."""
        model = self.audit_model if high_stakes else self.model

        messages = [{"role": "user", "content": prompt}]

        if use_cache:
            # Usar prompt caching para el system prompt (reducir costos en análisis masivos)
            response = self.client.messages.create(
                model=model,
                max_tokens=self.max_tokens,
                system=[
                    {
                        "type": "text",
                        "text": system,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=messages,
            )
        else:
            response = self.client.messages.create(
                model=model,
                max_tokens=self.max_tokens,
                system=system,
                messages=messages,
            )

        return response

    def analyze_resolucion(
        self,
        resolucion_id: str,
        texto: str,
        acta_context: Optional[str] = None,
        high_stakes: bool = False,
    ) -> AuditResult:
        """
        Analiza una resolución individual y retorna resultado de auditoría.

        Args:
            resolucion_id: Identificador único (ej: "2023_456")
            texto: Texto de la resolución
            acta_context: Contexto adicional del acta (fecha, miembros, etc.)
            high_stakes: Si True, usa modelo Opus para análisis más profundo
        """
        context_block = f"\n\nCONTEXTO DEL ACTA:\n{acta_context}" if acta_context else ""

        prompt = f"""Analiza la siguiente resolución del Consejo Federal Pesquero (CFP):

ID: {resolucion_id}
{context_block}

TEXTO DE LA RESOLUCIÓN:
{texto}

Proporciona tu análisis en el siguiente formato JSON:

{{
  "riesgo_score": <número 0-100>,
  "categoria_riesgo": "<bajo|medio|alto|critico>",
  "hallazgos": [
    "<hallazgo concreto con evidencia del texto>"
  ],
  "indicios": [
    "<indicio que requiere investigación adicional>"
  ],
  "recomendaciones": [
    "<acción recomendada para verificación o corrección>"
  ],
  "normativa_afectada": [
    "<artículo o norma potencialmente afectada>"
  ],
  "entidades_beneficiadas": [
    "<empresa o actor que se beneficia de esta resolución>"
  ],
  "especies_afectadas": [
    "<especie pesquera afectada>"
  ],
  "resumen_ejecutivo": "<2-3 oraciones resumiendo la resolución y su impacto>",
  "banderas_rojas": [
    "<señal de alerta específica si existe>"
  ]
}}

Sé preciso y basa tu análisis únicamente en el texto proporcionado."""

        try:
            response = self._call_claude(prompt, high_stakes=high_stakes)
            content = response.content[0].text

            # Extraer JSON del response
            parsed = _extract_json(content)

            return AuditResult(
                resolucion_id=resolucion_id,
                resolucion_texto=texto,
                riesgo_score=float(parsed.get("riesgo_score", 0)),
                categoria_riesgo=parsed.get("categoria_riesgo", "bajo"),
                hallazgos=parsed.get("hallazgos", []),
                indicios=parsed.get("indicios", []),
                recomendaciones=parsed.get("recomendaciones", []),
                normativa_afectada=parsed.get("normativa_afectada", []),
                entidades_beneficiadas=parsed.get("entidades_beneficiadas", []),
                especies_afectadas=parsed.get("especies_afectadas", []),
                modelo_usado=response.model,
                tokens_entrada=response.usage.input_tokens,
                tokens_salida=response.usage.output_tokens,
                analisis_completo=content,
            )

        except Exception as exc:
            logger.error(f"Error analizando resolución {resolucion_id}: {exc}")
            return AuditResult(
                resolucion_id=resolucion_id,
                resolucion_texto=texto,
                riesgo_score=0,
                categoria_riesgo="error",
                hallazgos=[],
                indicios=[],
                recomendaciones=[],
                normativa_afectada=[],
                entidades_beneficiadas=[],
                especies_afectadas=[],
                modelo_usado=self.model,
                tokens_entrada=0,
                tokens_salida=0,
                analisis_completo=f"ERROR: {exc}",
            )

    def summarize_acta(self, acta_texto: str, filename: str) -> dict[str, Any]:
        """Genera resumen ejecutivo de un acta completa."""
        # Limitar texto para no exceder contexto
        texto_truncado = acta_texto[:12000]

        prompt = f"""Resume el siguiente acta del CFP ({filename}):

{texto_truncado}

Genera un resumen estructurado en JSON:
{{
  "fecha": "<fecha de la sesión>",
  "tipo_sesion": "<ordinaria|extraordinaria|especial>",
  "temas_principales": ["<tema 1>", "<tema 2>"],
  "resoluciones_destacadas": [
    {{
      "numero": "<N°>",
      "descripcion": "<descripción breve>",
      "impacto": "<impacto en el sector pesquero>"
    }}
  ],
  "especies_tratadas": ["<especie 1>"],
  "cuotas_otorgadas_toneladas": <total si aplica o null>,
  "alertas_sostenibilidad": ["<alerta si existe>"],
  "resumen_narrativo": "<párrafo descriptivo del acta>"
}}"""

        try:
            response = self._call_claude(prompt)
            content = response.content[0].text
            parsed = _extract_json(content)
            parsed["_tokens"] = {
                "entrada": response.usage.input_tokens,
                "salida": response.usage.output_tokens,
            }
            return parsed
        except Exception as exc:
            logger.error(f"Error resumiendo acta {filename}: {exc}")
            return {"error": str(exc)}

    def detect_patterns(self, resoluciones_texts: list[str]) -> dict[str, Any]:
        """
        Analiza un conjunto de resoluciones buscando patrones sistémicos.
        Ideal para analizar todas las resoluciones de un año o de una empresa.
        """
        combined = "\n\n---\n\n".join(resoluciones_texts[:20])  # Límite de 20

        prompt = f"""Analiza el siguiente conjunto de resoluciones del CFP en búsqueda de PATRONES SISTÉMICOS:

{combined}

Identifica:
1. Empresas o actores que aparecen repetidamente como beneficiarios
2. Patrones de votación inusuales (siempre unánime, quórum mínimo recurrente)
3. Especies donde las cuotas muestran tendencia al alza sostenida
4. Decisiones que parecen contradecir decisiones previas sin justificación
5. Períodos temporales de concentración de beneficios

Responde en JSON:
{{
  "patrones_detectados": [
    {{
      "tipo": "<tipo de patrón>",
      "descripcion": "<descripción detallada>",
      "evidencia": ["<cita del texto>"],
      "riesgo": "<bajo|medio|alto|critico>",
      "frecuencia": "<número de ocurrencias>"
    }}
  ],
  "actores_recurrentes": [
    {{"nombre": "<actor>", "apariciones": <n>, "rol": "<beneficiario|solicitante|interviniente>"}}
  ],
  "tendencias_cuotas": [
    {{"especie": "<especie>", "tendencia": "<alza|baja|estable>", "preocupacion": "<si/no>"}}
  ],
  "conclusion_general": "<evaluación global del conjunto de resoluciones>"
}}"""

        try:
            response = self._call_claude(prompt, high_stakes=True)
            content = response.content[0].text
            return _extract_json(content)
        except Exception as exc:
            logger.error(f"Error detectando patrones: {exc}")
            return {"error": str(exc)}

    def analyze_sustainability(
        self,
        especie: str,
        resoluciones_por_anio: dict[int, list[str]],
    ) -> dict[str, Any]:
        """
        Analiza la evolución de decisiones sobre una especie a lo largo del tiempo.
        Compara con tendencias conocidas de sostenibilidad.
        """
        context = "\n".join(
            f"AÑO {year}: {' | '.join(texts[:3])}"
            for year, texts in sorted(resoluciones_por_anio.items())
        )

        prompt = f"""Analiza la evolución histórica de las decisiones del CFP sobre {especie.upper()}:

{context[:10000]}

Evalúa:
1. ¿Las cuotas han aumentado o disminuido respecto al stock disponible?
2. ¿Se han respetado las recomendaciones del INIDEP históricamente?
3. ¿Hay señales de sobrexplotación o presión excesiva sobre la especie?
4. ¿Existen períodos de reversión de vedas o reapertura de áreas cerradas?
5. ¿La tendencia decisional es sostenible a largo plazo?

Responde en JSON:
{{
  "especie": "{especie}",
  "años_analizados": <n>,
  "tendencia_cuotas": "<creciente|decreciente|estable|variable>",
  "riesgo_sostenibilidad": <0-100>,
  "señales_sobrexplotacion": ["<señal>"],
  "decisiones_cuestionables": [
    {{"año": <año>, "descripcion": "<decisión cuestionable>", "impacto": "<impacto>"}}
  ],
  "periodos_criticos": ["<período>"],
  "conclusion": "<evaluación de sostenibilidad a largo plazo>"
}}"""

        try:
            response = self._call_claude(prompt, high_stakes=True)
            return _extract_json(response.content[0].text)
        except Exception as exc:
            logger.error(f"Error analizando sostenibilidad de {especie}: {exc}")
            return {"error": str(exc)}


def _extract_json(text: str) -> dict:
    """Extrae el primer objeto JSON válido del texto de respuesta."""
    import re
    # Buscar bloque JSON
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    # Fallback: retornar texto como mensaje de error
    return {"raw_response": text, "parse_error": True}
