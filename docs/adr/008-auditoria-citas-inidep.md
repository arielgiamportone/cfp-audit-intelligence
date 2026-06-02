# ADR-008: Auditoría de Citas INIDEP (diseño diferido)

**Estado:** Diferido  
**Fecha:** 2026-06-02  
**Decidido por:** Ariel Giamportone

## Contexto

Existe una pregunta de investigación de alto impacto mediático y académico que el
sistema aún no responde:

> En 25 años de decisiones, **¿con qué frecuencia el CFP cita explícitamente un
> Informe Técnico Oficial (ITO) del INIDEP que recomienda X toneladas y luego
> aprueba una cuota que contradice esa recomendación?**

Esto es distinto del comparador actual. `INIDEPComparator.compute_comparisons()`
ya cruza CBA vs CMP por `(especie, año, zona)` y emite alertas de sobreasignación.
Pero **no verifica el acto de citación**: no comprueba si el acta *menciona* el ITO
cuya recomendación está contradiciendo. La "auditoría de citas" detecta una
**contradicción explícita en el razonamiento del CFP**, no solo una discrepancia
numérica estructural — un hallazgo cualitativamente más fuerte.

## Estado del modelo de datos (verificado)

| Pieza | Estado | Ubicación |
|-------|--------|-----------|
| Captura de citas ITO en texto | ✅ Existe | `document_parser.parse_fundamento_inidep()` (regex `RE_FUNDAMENTO_INIDEP`) → `Decision.fundamento_inidep: list[str]`, ej. `"Informe INIDEP N° 36/2024"` |
| CBA recomendada por ITO | ✅ Poblado (seed) | `inidep_evaluaciones.numero_ito` (`"36/2024"`) + `cba_recomendada_tn` |
| CMP aprobada por el CFP | ❌ **Vacío** | `cfp_cuotas.cmp_aprobada_tn` — sin poblar hasta el pipeline real |
| Citas en base relacional | ❌ **Solo en JSON** | `Decision.fundamento_inidep` vive en `data/processed/json/`, no en SQLite |

**Bloqueante:** sin `cmp_aprobada_tn` poblado y sin las citas en la base, el
análisis correría sobre tablas vacías. La infraestructura de extracción existe;
falta el *plumbing* de persistencia y los datos reales.

## Decisión

**Diferir la implementación.** Documentar aquí el diseño completo para que sea
ejecutable en cuanto el pipeline real popule las tablas. No se construye el módulo
en este sprint porque produciría una pieza analítica sobre el vacío.

## Diseño propuesto (para implementar con datos reales)

### 1. Persistir citas y CMP (ETL)
```sql
ALTER TABLE resoluciones ADD COLUMN fundamento_inidep TEXT;  -- JSON array
```
- `load_parsed_json_into_db()`: recorre `data/processed/json/`, upsert de cada
  `Decision` en `resoluciones` con `fundamento_inidep` serializado.
- `populate_cfp_cuotas_from_decisions()`: para cada decisión con `toneladas` y
  `tipo not in (diferida, denegada)`, persistir `cmp_aprobada_tn` + `resolucion_cfp`
  en `cfp_cuotas`.

### 2. Módulo `CitationAuditor`
```python
@dataclass
class CitationInconsistency:
    acta_id: int
    cited_ito: str            # "36/2024"
    cba_recommended_tn: float
    cmp_approved_tn: float
    contradiction_pct: float  # (cmp/cba - 1) * 100
    especie: str
    year: int

class CitationAuditor:
    def audit(self, db_path) -> list[CitationInconsistency]:
        # 1. Por cada resolución con fundamento_inidep no vacío
        # 2. Extraer nº ITO con regex N[°º]?\s*(\d+/\d{4})
        # 3. JOIN con inidep_evaluaciones.numero_ito → cba_recomendada_tn
        # 4. Si cmp_aprobada_tn > cba * 1.1 → registrar inconsistencia
```

### 3. Salida
- Tabla `citas_auditadas` + reporte: % de resoluciones que citan un ITO y lo
  contradicen, evolución temporal (1998–2025), ranking por especie.
- Entrega #08 de la Serie ALG con visualización de la serie temporal.

## Ruta de migración

1. Correr `--step process` real → poblar `cfp_cuotas.cmp_aprobada_tn`.
2. Ejecutar ETL de citas (`fundamento_inidep` → `resoluciones`).
3. Implementar `CitationAuditor` + tests con datos reales.
4. Publicar Entrega #08.

## Consecuencias

- **Positivas:** el diseño queda capturado y citable; cuando lleguen los datos,
  la implementación es directa (el join es trivial sobre `numero_ito`).
- **Negativas:** el hallazgo de mayor impacto queda pendiente de los datos reales;
  no hay resultado hasta entonces.

## Referencias

- ADR-003 (SQLite), ADR-005 (reproducibilidad), ADR-007 (límites éticos).
- `src/analysis/inidep_comparator.py` — comparador CBA/CMP existente.
- `src/processing/document_parser.py` — `parse_fundamento_inidep()`.
