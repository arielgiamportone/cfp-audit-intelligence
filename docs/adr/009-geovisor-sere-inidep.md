# ADR-009: Integración del Geovisor SERE del INIDEP (prototipo verificado)

**Estado:** Aceptado (prototipo) — persistencia completa diferida a datos reales del pipeline
**Fecha:** 2026-06-06
**Decidido por:** Ariel Giamportone

## Contexto

El INIDEP publicó **SERE — Visualizador de Especies** (`sere.inidep.edu.ar`), un geovisor
que corre sobre **GeoServer** y expone capas vía servicios OGC estándar (WFS/WMS),
**públicos y sin autenticación**. Se verificó en vivo qué expone y si aporta valor al
triángulo de auditoría.

## Hallazgos verificados (consultas WFS en vivo, 2026-06-06)

Servicio base: `https://sere.inidep.edu.ar/geoserver/ows` — WFS 2.0.0, `outputFormat=application/json`.

### 1. Distribución de especies — 195 capas, datos desde ~1982
Una capa por especie con ocurrencias georreferenciadas:
```json
{"especie": "Cynoscion guatucupa", "nom_comun": "Pescadilla de red",
 "anio": 1982, "geometry": {"type": "Point", "coordinates": [-53, -35.41]}}
```
65 cartilaginosos, 119 óseos, 11 cefalópodos. Una sola especie (`Cynoscion_guatucupa`)
devolvió **1.897 registros**.

### 2. Vedas geoespaciales 2024 — citan directamente la resolución CFP/CTMFM
Esto es lo más valioso: cada polígono de veda trae el **número de resolución y el link
directo al PDF oficial**:
```json
{"Especie": "Centolla", "nam_area": "Zona C V",
 "Resolucion": "Res. 12/2018", "Fuente": "CFP",
 "Link_res": "https://cfp.gob.ar/resoluciones/Resolucion%2012%20...",
 "Inicio": "2024-06-01Z", "Fin": "2024-12-31Z"}
```
Capas relevantes para las especies ya verificadas en el comparador (README): Merluza
Hubbsi (4 estacionales + permanente), Merluza Negra, Centolla (+ áreas), Langostino
(+ subáreas), Abadejo (pozos), Vieira (unidad de manejo + áreas cerradas), Rincón
(demersales costeros), + 2 capas de veda de arte de pesca (arrastre 28m, condrictios).

### 3. Líneas base — `lineas_base_sere`
Batimetría, plataforma continental, ZEE (`zcpau`), áreas protegidas, puertos. Contexto
geoespacial reutilizable, no prioritario para el triángulo de auditoría.

## Por qué importa para el proyecto

1. **Ground truth externo para `veda_revertida`**: `pattern_detector` detecta
   reversiones de veda con una heurística (resolución `tipo='veda'` seguida de
   `cuota_captura` en ≤2 años). El geovisor da una **lista verificable de resoluciones
   de veda activas con número y link al PDF**, fuente independiente del parser propio
   — permite auditar si el parser está extrayendo bien las resoluciones de veda.

2. **Anclaje geoespacial de `zona`**: hoy `inidep_evaluaciones.zona` y `cfp_cuotas.zona`
   son texto libre (ej. `"Zona C-II"`). Las capas de áreas de manejo
   (`Vieira_Unidad_Manejo`, `Langostino_subareas`, `areas_centolla`) dan polígonos reales
   — permitirían validar si la cuota aprobada corresponde a una zona donde la especie
   efectivamente aparece en 40+ años de campañas (capas de distribución).

3. **Enriquecimiento NER**: 195 especies con nombre científico + común, reutilizable
   como fuente de sinónimos verificados para `EntityRuler` en `ner_pesquero.py`.

## Verificación de cruce con datos actuales (resultado: aún no cruza — como ADR-008)

Se consultó `data/processed/catalog.db`: la tabla `resoluciones` (128 filas) **no tiene
ninguna fila `tipo='veda'`** y ninguno de los números de resolución citados por el
geovisor (`12/2018`, `12/2019`, `3/2024`) aparece en `numero`. Es el mismo bloqueante
que ADR-008: el corpus real de actas todavía no está cargado vía `--step process`.

**Esto no invalida el prototipo** — al contrario, da una lista de referencia (números
de resolución + fechas + links a PDF) contra la cual **validar la cobertura del parser**
en cuanto el pipeline real cargue las actas correspondientes (2018, 2019, 2024).

## Decisión

**Aceptar el prototipo** (`src/acquisition/inidep_geovisor_scraper.py` +
`vedas_geoespaciales`) porque:
- el servicio es público, estable, sin auth, y devuelve datos estructurados verificables
  (no requiere esperar al pipeline real para *obtener* los datos — solo para *cruzarlos*)
- a diferencia de ADR-008 (auditoría de citas), aquí el origen de datos es independiente
  del propio parser: persistirlo ahora no "audita sobre el vacío", documenta una fuente
  externa que será insumo de validación cuando el corpus esté completo

**Diferir** el cruce activo (`GeovisorCrossValidator`) hasta que `--step process` cargue
actas 2018/2019/2024 con resoluciones de veda reales.

## Diseño implementado (prototipo)

```python
@dataclass
class VedaGeoespacial:
    capa, especie, area, fecha_inicio, fecha_fin,
    resolucion_numero, resolucion_fuente, resolucion_url, notas, geometry_type

class SEREGeovisorClient:
    def fetch_veda_layer(type_name) -> list[VedaGeoespacial]
    def fetch_especie_distribucion(type_name, max_features) -> list[dict]
    def scrape_all_vedas() -> list[VedaGeoespacial]

SCHEMA_VEDAS_GEO: CREATE TABLE vedas_geoespaciales(
    capa, especie, especie_code, area, fecha_inicio, fecha_fin,
    resolucion_numero, resolucion_fuente, resolucion_url, notas, geometry_type)

def save_vedas_to_db(records, db_path) -> int   # dedup por (capa, area, resolucion_numero)
```

## Ruta de migración (cruce activo, futuro)

1. Correr `--step process` real → poblar `resoluciones` con actas 2018/2019/2024.
2. `GeovisorCrossValidator.validar_cobertura_vedas()`: por cada `VedaGeoespacial` con
   `resolucion_numero`, buscar coincidencia en `resoluciones.numero` + año de
   `fecha_inicio`. Reportar % de vedas citadas por INIDEP que el parser capturó.
3. Si la cobertura es alta → usar el geovisor como fuente de verificación automática
   continua del parser (cada año el geovisor publica `vedas_<año>`).

## Consecuencias

- **Positivas:** nueva fuente pública de datos geoespaciales verificables, con links
  directos a PDFs oficiales — material reutilizable para visualización en el dashboard
  (mapas de vedas activas) independientemente del cruce con el parser.
- **Negativas:** el valor completo (validación cruzada) depende de poblar `resoluciones`
  con el corpus real — mismo bloqueante que ADR-008.

## Referencias

- ADR-003 (SQLite), ADR-008 (auditoría de citas — mismo patrón de bloqueante).
- `src/acquisition/inidep_scraper.py` — patrón de scraper INIDEP existente (DSpace API).
- `src/analysis/pattern_detector.py` — heurística `veda_revertida` a validar.
- Servicio: `https://sere.inidep.edu.ar/geoserver/ows` (WFS 2.0.0, GeoServer, OGC estándar).
