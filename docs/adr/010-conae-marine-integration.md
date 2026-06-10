# ADR-010: Integración del Geoportal Marino CONAE (4° vértice del triángulo de auditoría)

**Estado**: Aceptado — 2026-06-10  
**Autores**: Ariel Giamportone  
**Reemplaza/extiende**: ADR-009 (geovisor SERE INIDEP, 3° fuente geoespacial)

---

## Contexto

El geoportal marino de la CONAE (Comisión Nacional de Actividades Espaciales) —
`https://geoportal.conae.gov.ar/mapstore/#/viewer/openlayers/aplicaciones_marinas` —
expone capas satelitales del Mar Argentino vía WMS estándar OGC:

| Grupo | Capas (sufijo `_1..8`) | Resolución | Fuente satélite |
|-------|------------------------|------------|----------------|
| Esfuerzo pesquero GFW | `Pesca:GFW_AIS_EPA_1..8` | 1 km/día | Global Fishing Watch AIS |
| SST diurna | `Pesca:SNPP_VIIRS_SST_1..8` | 4 km/día | VIIRS/SNPP |
| SST nocturna | `Pesca:SNPP_VIIRS_NSST_1..8` | 4 km/día | VIIRS/SNPP |
| Clorofila diaria | `Pesca:SNPP_VIIRS_CHLA_1..8` | 4 km/día | VIIRS/SNPP |
| Clorofila 8 días | `Pesca:SNPP_VIIRS_CHLA8D_1..8` | 4 km/día | VIIRS/SNPP |
| Luces nocturnas | `Pesca:SNPP_VIIRS_LN_1..8` | 500 m | VIIRS/DNB |

El sufijo `_1..8` corresponde a sub-tiles geográficos que en conjunto cubren la Zona
Económica Exclusiva argentina. El scraper prueba los 8 sub-tiles y usa el primero que
devuelve un valor no nulo para cada punto.

El proyecto ya tiene tres vértices del triángulo de auditoría:
1. **CBA** — recomendación científica INIDEP (`inidep_evaluaciones`)
2. **CMP** — cuota aprobada CFP (`cfp_cuotas`, pendiente de datos reales)
3. **Captura real** — desembarques SAGPyA/SIPA (`capturas_reales`)

Un **4° vértice satelital** independiente permite preguntar:
> *¿El esfuerzo pesquero real (GFW AIS) decrece efectivamente dentro de las zonas
> de veda durante su período de vigencia?*

Esta pregunta no depende del pipeline de actas CFP: es evidencia externa, objetiva
y verificable que fortalece o contradice los hallazgos del corpus de actas.

---

## Decisión

Integrar el geoportal marino CONAE como fuente de verificación satelital mediante:

### 1. Técnica de consulta: WMS GetFeatureInfo por muestreo de puntos

El servidor CONAE no expone WCS (Web Coverage Service) ni WFS para descarga masiva
de raster. La única interfaz disponible para obtener valores numéricos es
`GetFeatureInfo` sobre píxeles específicos.

**Enfoque adoptado**: muestreo de centroides de zonas representativas (6 zonas
predefinidas — `ZONAS_MUESTRA`) usando una ventana BBOX de 0.2° × 0.2° alrededor
del centroide y consultando el píxel central (posición 5/5 en imagen 11×11).
No hay consulta de áreas ni interpolación — el valor devuelto es el valor raster
en el píxel más cercano al centroide.

**BBOX protocol (WMS 1.1.1, EPSG:4326)**:
```
GET ?SERVICE=WMS&VERSION=1.1.1&REQUEST=GetFeatureInfo
    &LAYERS=<capa>&QUERY_LAYERS=<capa>
    &BBOX=<lon-0.1>,<lat-0.1>,<lon+0.1>,<lat+0.1>
    &WIDTH=11&HEIGHT=11&SRS=EPSG:4326
    &X=5&Y=5&INFO_FORMAT=application/json&FEATURE_COUNT=1
```

### 2. Modelo de datos: tabla `esfuerzo_satelital`

```sql
CREATE TABLE IF NOT EXISTS esfuerzo_satelital (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    zona        TEXT NOT NULL,
    especie_code TEXT,
    fecha       TEXT NOT NULL,
    lon         REAL NOT NULL,
    lat         REAL NOT NULL,
    sst         REAL,        -- SST diurna (°C), VIIRS/SNPP
    sst_noche   REAL,        -- SST nocturna (°C), VIIRS/SNPP
    clorofila   REAL,        -- Chl-a diario (mg/m³)
    clorofila_8d REAL,       -- Chl-a compuesto 8 días (mg/m³)
    esfuerzo_gfw REAL,       -- GFW AIS (horas de pesca / km²)
    luces_noche REAL,        -- VIIRS DNB (radiancia, proxy detección buques)
    fuente      TEXT DEFAULT 'CONAE geoportal (WMS GetFeatureInfo)',
    created_at  TEXT DEFAULT (datetime('now')),
    UNIQUE(zona, fecha)
);
```

### 3. Validación de cumplimiento de vedas: `validar_cumplimiento_satelital()`

Método nuevo en `GeovisorCrossValidator` que cruza:
- `esfuerzo_satelital.especie_code` + `fecha` con
- `vedas_geoespaciales.especie_code` + (`fecha_inicio`, `fecha_fin`)

Calcula mediana de `esfuerzo_gfw` durante veda vs. fuera de veda, y si hay suficientes
datos corre Mann-Whitney U (scipy) para evaluar la significancia estadística.

### 4. Pipeline: `--step conae`

Nueva etapa en `run_full_pipeline.py` que muestrea todas las `ZONAS_MUESTRA` y
persiste resultados. Pensada para correr periódicamente (semanal/mensual) a fin de
construir una serie temporal.

### 5. Dashboard: página 17 `17_CONAE_Satelital.py`

Muestra:
- Mapa de zonas de muestreo
- Series temporales de SST y clorofila por zona
- Esfuerzo GFW por zona y fecha
- Comparación de esfuerzo dentro/fuera de períodos de veda (si `vedas_geoespaciales` poblada)

---

## Justificación de las zonas de muestreo

Seis centroides representativos de las principales pesquerías argentinas, elegidos por:
(a) presencia documentada de vedas en `vedas_geoespaciales` para la especie asociada, y
(b) relevancia pesquera histórica (Bertolotti et al. 2001, INIDEP Informes Técnicos):

| Zona | Especie | Lat | Lon | Justificación |
|------|---------|-----|-----|---------------|
| `golfo_san_jorge_norte` | merluza_hubbsi | -44.5 | -65.0 | Principal caladero merluza; veda invernal |
| `plataforma_bonaerense` | merluza_hubbsi | -39.0 | -57.0 | Frente Subtropical; alta concentración flota |
| `rawson_offshore` | langostino | -43.2 | -63.5 | Principal sub-área langostino (Chubut) |
| `golfo_nuevo` | centolla | -42.7 | -64.0 | Veda centolla Golfo Nuevo/San José |
| `sur_atlantico` | merluza_negra | -51.5 | -60.0 | Zona subantártica bajo CCAMLR |
| `offshore_chubut` | vieira | -46.0 | -62.0 | Pozos de vieira offshore Chubut |

---

## Limitaciones conocidas

1. **Sin consulta histórica**: el WMS CONAE sirve composites recientes (~rolling window
   de 8 períodos). No es posible consultar fechas arbitrarias del pasado mediante
   GetFeatureInfo. La serie temporal se construye acumulando runs periódicos.

2. **Muestreo puntual, no poligonal**: se consulta el centroide de la zona, no la
   distribución espacial completa. Esto subestima la heterogeneidad intra-zona.

3. **Proxy de esfuerzo, no captura**: GFW AIS mide horas de actividad pesquera
   estimada por AIS, no toneladas desembarcadas. Embarcaciones sin AIS (flotas pequeñas,
   flota extranjera sin transponder) no son detectadas.

4. **Resolución espacio-temporal**: SST/Clorofila a 4 km; GFW a 1 km; nubes degradan
   cobertura del óptico/IR. Los valores `null` (NoData) se registran como `NULL` en DB.

5. **Luces nocturnas como proxy**: VIIRS DNB es indicativo, no confirmatorio.
   Luces de buques pesqueros vs. plataformas no son distinguibles a esta resolución.

---

## Consecuencias

- **Positivo**: evidencia satelital independiente del pipeline de actas. Si el esfuerzo
  GFW decrece significativamente durante vedas, refuerza la coherencia regulatoria.
  Si no decrece, es un hallazgo propio de alto impacto metodológico.

- **Positivo**: datos ambientales (SST, clorofila) permiten contextualizar variaciones
  de captura por factores oceanográficos (no sólo regulatorios), mejorando la robustez
  causal de los análisis.

- **Negativo**: sin acceso WCS, no es posible construir distribuciones espaciales
  completas ni generar mapas de alta resolución. Solo análisis zonales con los centroides.

- **Trabajo futuro**: cuando CONAE habilite WCS o descarga directa de NetCDF, migrar a
  consulta temporal explícita con parámetro `TIME` del estándar OGC WMS 1.3.0.

---

## Referencias

- CONAE (2025). Visor de Aplicaciones Marinas.
  `https://geoportal.conae.gov.ar/mapstore/#/viewer/openlayers/aplicaciones_marinas`
- Kroodsma, D.A. et al. (2018). Tracking the global footprint of fisheries.
  *Science* 359(6378), 904–908. DOI: 10.1126/science.aao5646
- Bertolotti, M.I. et al. (2001). Impacto económico de la actividad pesquera argentina.
  INIDEP Informe Técnico 47.
- FAO (1995). Code of Conduct for Responsible Fisheries. Art. 7.2.1.
- ADR-009: Geovisor SERE (INIDEP) — vedas geoespaciales y validación de cobertura.
