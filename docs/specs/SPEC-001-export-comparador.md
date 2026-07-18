# SPEC-001 · Exportar la comparación CBA/CMP (CSV/JSON)

**Estado**: Propuesta
**Autor**: Ariel Giamportone
**Fecha**: 2026-07-17
**Nivel SDD**: Spec-First (la especificación es la fuente de verdad; el código se implementa a partir de ella)
**Relacionado**: RF06 (comparador), RF11 (API) · `docs/REQUISITOS.md`

> Ejemplo de **Spec-Driven Development** aplicado al proyecto: se define **qué** debe hacer la
> funcionalidad y **cómo se verifica** antes de escribir el código.

---

## 1. Contexto y problema
El Comparador CBA/CMP (pág. 05) y la API exponen las comparaciones por especie/año con su nivel
de alerta, pero **no permiten exportar** esos resultados. Un auditor, periodista o investigador
necesita llevarse los datos (a Excel, a un informe, a otro análisis) sin copiarlos a mano.

## 2. Objetivos y no-objetivos
**Objetivos**
- Exportar el conjunto de comparaciones (filtrado) a **CSV** y **JSON**.
- Disponible desde el **dashboard** (botón de descarga) y desde la **API** (`format=csv|json`).

**No-objetivos (YAGNI)**
- No generar PDF (ya existe el reporte ejecutivo, RF10).
- No exportar el corpus completo de actas ni embeddings.
- No añadir autenticación (la app es pública, ver ADR-011).

## 3. Especificación funcional (qué debe hacer)
**Entrada (filtros opcionales):** `especie`, `year_desde`, `year_hasta`, `nivel_alerta`.
**Salida:** un archivo con una fila por comparación y estas columnas (contrato de datos):

```
especie_code, especie, zona, year, cba_tn, cmp_tn, diferencia_tn, diferencia_pct, nivel_alerta
```

- CSV: separador `,`, codificación UTF-8, cabecera incluida.
- JSON: lista de objetos con esas claves.
- Nombre sugerido del archivo: `comparacion_cba_cmp_{filtros}_{YYYYMMDD}.csv`.

## 4. Criterios de aceptación (Given-When-Then)
```
DADO    que existen comparaciones CBA/CMP en la base de datos
CUANDO  el usuario pulsa "Exportar CSV" en el Comparador
ENTONCES se descarga un CSV UTF-8 con cabecera y una fila por comparación filtrada
```
```
DADO    la API en marcha
CUANDO  hago GET /inidep/comparacion?format=csv&especie=merluza_hubbsi
ENTONCES recibo un CSV (Content-Type text/csv) solo con esa especie
```
```
DADO    un filtro que no devuelve resultados
CUANDO  se solicita la exportación
ENTONCES se devuelve un archivo con solo la cabecera (CSV) o lista vacía (JSON), sin error
```

## 5. Casos borde
- Sin datos → archivo con cabecera / lista vacía (no romper).
- Valores nulos (p. ej. `cmp_tn` ausente) → celda vacía, no `None` literal.
- Números en formato internacional (`.` decimal) en el archivo, aunque la UI muestre formato argentino.

## 6. Impacto y trazabilidad
- **Código previsto:** `analysis/inidep_comparator.py` (método `export(...)` que devuelve DataFrame/bytes),
  `dashboard/pages/05_INIDEP_Comparador.py` (`st.download_button`), `api/routers/inidep.py` (`format`).
- **Requisitos:** satisface una extensión de RF06 y RF11.
- **Tests:** contrato de columnas, filtros, y caso sin datos (`tests/test_inidep_comparator.py`).

## 7. Plan de implementación (por fases)
1. `export_comparaciones(filtros) -> pandas.DataFrame` en el comparador (+ test de contrato).
2. Botón de descarga CSV/JSON en la página 05 (usa el DataFrame).
3. Parámetro `format` en el endpoint de la API (reusa la misma función).

## 8. Métricas de éxito
- El usuario puede exportar en < 3 clics.
- El CSV abre correctamente en Excel/LibreOffice con las 9 columnas.
- Tests del contrato de exportación en verde.
