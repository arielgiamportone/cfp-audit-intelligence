# ADR-012: Puertos del dominio (Hexagonal) con `typing.Protocol`

**Estado**: Aceptado — 2026-07-17
**Autores**: Ariel Giamportone
**Extiende**: ADR-011 (que dejó los puertos como trabajo futuro)
**Contexto**: Trabajo Final de Máster — Unidad 3 (Arquitectura de software)

---

## Contexto

El ADR-011 estableció que el proyecto sigue un patrón **Hexagonal** (dominio agnóstico
a la UI, expuesto por dos adaptadores de entrega: API y dashboard) y dejó pendiente
**explicitar los puertos** hacia servicios externos.

Diagnóstico del acoplamiento (evidencia en código):
- `CFPAuditEngine.__init__` instancia `anthropic.Anthropic(...)` internamente → acoplamiento
  directo al SDK de Claude.
- `CFPVectorStore` instancia `chromadb.PersistentClient(...)` internamente → acoplamiento a ChromaDB.
- Los consumidores dependen de esas **clases concretas**, no de una abstracción.

Consecuencia: para testear o sustituir el LLM/almacén vectorial hay que tocar y mockear
las implementaciones concretas.

## Decisión

Introducir **puertos** (interfaces) en `src/ports.py` usando **`typing.Protocol` estructural**:

- `VectorStorePort` — contrato del almacén vectorial (RAG): `search`, `add_resolucion`,
  `add_batch`, `get_by_id`, `count`, `index_from_json_dir`.
- `AuditorPort` — contrato del motor de auditoría IA: `analyze_resolucion`, `summarize_acta`,
  `detect_patterns`, `analyze_sustainability`.

Los adaptadores actuales (`CFPVectorStore`, `CFPAuditEngine`) **satisfacen el puerto por
duck typing**, sin herencia ni cambios. El código de alto nivel puede **tipar contra el
puerto** (DIP) en lugar de la clase concreta.

Se elige `Protocol` (estructural) frente a `ABC` (herencia) porque es **no invasivo**:
no obliga a modificar clases existentes ni a heredar, encaja con el código actual y con
los 1003 tests sin romper nada.

## Consecuencias

**Positivas**
- **DIP**: el dominio depende de abstracciones, no de Anthropic/ChromaDB.
- **Testabilidad**: se pueden inyectar **fakes** que cumplan el puerto (sin llamadas reales).
- **Adaptadores intercambiables**: cambiar de LLM o de vector store no obliga a tocar a los consumidores.
- **Cero breakage**: `typing.Protocol` estructural; test de conformidad en `tests/test_ports.py`.

**Limitaciones / trabajo futuro**
- Aún **no hay un composition root único**: el *wiring* de dependencias sigue en las páginas
  del dashboard. Centralizarlo (un `buildAdapters(config)` por entorno dev/test/prod) queda
  como mejora futura.
- La anotación de los consumidores con los tipos-puerto se hará gradualmente.

## Alternativas consideradas

| Alternativa | Veredicto |
|-------------|-----------|
| **`typing.Protocol` estructural** | ✅ Elegida (no invasiva, sin herencia, sin romper tests) |
| `abc.ABC` + herencia | Descartada para ahora (invasiva; obliga a modificar las clases) |
| No hacer nada | Descartada (mantiene el acoplamiento y dificulta tests/sustitución) |
