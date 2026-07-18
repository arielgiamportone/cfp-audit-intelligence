# ADR-011: Streamlit como adaptador de entrega (UI) sobre un dominio agnóstico

**Estado**: Aceptado — 2026-07-17
**Autores**: Ariel Giamportone
**Contexto**: Trabajo Final de Máster (Máster en Desarrollo con IA)

---

## Contexto

El proyecto se presenta como TFM de un máster orientado a **desarrollo** (no solo data
science). Surgió la pregunta de si **Streamlit** es la opción adecuada para la capa de
interfaz, o si convendría un frontend "de desarrollo" (p. ej. React/Next sobre la API).

Radiografía del proyecto en el momento de la decisión:

| Componente | LOC | Rol |
|-----------|-----|-----|
| Núcleo (`acquisition`, `processing`, `analysis`, `knowledge_base`) + **API FastAPI** (5 routers) | ~15.700 (73%) | Dominio + API de producción |
| Dashboard **Streamlit** (17 páginas) | ~5.700 (27%) | Presentación / exploración |

Verificaciones sobre el código (evidencia, no supuestos):
- `import streamlit` fuera de `src/dashboard/` = **0** → el dominio **no depende de la UI**.
- Ningún módulo de dominio importa de `dashboard/` → **sin acoplamiento inverso**.
- El dashboard **reutiliza** el dominio (14 imports de `analysis`, 11 de `acquisition`, etc.).
- `Dockerfile` expone **API (8000)** y **dashboard (8501)**.

En términos del máster (Arquitectura de software), esto es un patrón **Hexagonal
(Ports & Adapters)**: un mismo dominio expuesto por **dos adaptadores de entrega**
(API REST y dashboard Streamlit).

## Decisión

**Mantener Streamlit como adaptador de presentación**, entendido explícitamente como
**un** adaptador de entrega (no *el* sistema), sobre un dominio agnóstico a la UI y
junto a una **API REST FastAPI** que actúa como interfaz de integración/producción.

Justificación:
- La aplicación es **analítica y con muchos datos** (tablas, gráficos, exploración):
  el terreno natural de Streamlit.
- Permite concentrar el esfuerzo en el **dominio** (73% del código), que es el valor real.
- **Despliegue trivial y gratuito** (Streamlit Community Cloud) → viable para el TFM.
- No genera *lock-in*: al estar el dominio limpio y existir la API, la UI es **reemplazable**.

## Consecuencias

**Positivas**
- Arquitectura demostrable (hexagonal) y coherente con el temario del máster.
- Time-to-market bajo; demo pública en funcionamiento.
- La credibilidad de "desarrollo" se sostiene en backend + API + Docker + 945 tests.

**Limitaciones asumidas**
- Streamlit re-ejecuta el script en cada interacción; control de UX y estado limitados.
- Modelo de sesión y escalado acotados (Community Cloud ~1 GB RAM); no apto para
  multiusuario en producción tal cual.
- Percepción de herramienta "data science"; se mitiga dando protagonismo a la **API**
  (OpenAPI `/docs`) en la presentación del TFM.

## Alternativas consideradas

| Alternativa | Veredicto |
|-------------|-----------|
| **Streamlit + potenciar la API** | ✅ Elegida (mejor coste/beneficio para el TFM) |
| FastAPI + React/Next (frontend real) | Aplazada a fase productiva (coste alto; es el camino de escalado natural) |
| Gradio | Descartada (aún más orientada a demo ML; no aporta sobre Streamlit) |

## Trabajo futuro (no bloqueante)
- Explicitar **puertos** (interfaces) para dependencias externas (LLM, vector store) para
  rematar el patrón hexagonal y mejorar testabilidad (candidato a ADR propio).
- Frontend React/Next consumiendo la API como evolución productiva.
