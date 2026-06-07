# Datasheet — CFP Audit Intelligence Dataset

> Estructura basada en Gebru et al. (2018/2021), *Datasheets for Datasets* (CACM).
> Última actualización: 2026-06-02

---

## Motivation

- **¿Para qué se creó el dataset?** Permitir la auditoría reproducible de 25+ años
  de decisiones del Consejo Federal Pesquero (CFP) de Argentina sobre cuotas de
  captura, y contrastarlas con las recomendaciones científicas del INIDEP y las
  capturas reales (triángulo de auditoría CBA → CMP → captura).
- **¿Quién lo creó?** Ariel Giamportone, proyecto CFP Audit Intelligence.
- **¿Financiamiento?** Proyecto independiente / I+D+i.

## Composition

- **¿Qué representa cada instancia?** Según la tabla:
  - `actas` / `resoluciones`: decisiones del CFP extraídas de PDFs públicos 1998–2025.
  - `entidades` / `menciones`: especies, empresas, personas, normativa mencionadas.
  - `inidep_evaluaciones`: CBA recomendada por ITO/especie/año (Mar Abierto INIDEP).
  - `cfp_cuotas`: CMP aprobada por el CFP (poblada por el pipeline real).
  - `capturas_reales`: desembarques efectivos (SIPA/SAGPyA).
  - `cargos_directivos` / `conflictos_detectados`: directores de empresas (Boletín
    Oficial) y su cruce con miembros del CFP (Entrega #07).
- **Derivados publicables:** `triangulo_auditoria.csv`, `patrones_historicos.csv`.
- **¿Cuántas instancias?** Variable según cobertura del pipeline. El conteo real
  se reporta vía `make stats`.
- **¿Etiquetas?** El gold set de 30 resoluciones tiene categoría de riesgo anotada
  (actualmente sintética/demo, ver Model Card).
- **Datos faltantes:** `cfp_cuotas.cmp_aprobada_tn` puede estar vacío hasta correr
  el pipeline completo; los `cargos_directivos` `seed_demo` son sintéticos.

## Collection Process

- **Fuentes:** PDFs públicos del CFP (`batch_scraper`), DSpace 7 de Mar Abierto
  INIDEP (`inidep_scraper`), datos.gob.ar/SAGPyA (`sipa_scraper`), FAO FIRMS
  (`fao_firms_scraper`), CONICET (`conicet_scraper`), Boletín Oficial Sección 4
  (`boletin_oficial_scraper`).
- **Mecanismo:** scraping con `requests` + `tenacity` (retry, rate limiting); sin
  llamadas que violen términos de uso. Todas las fuentes son públicas.

## Preprocessing / Cleaning / Labeling

- Extracción PDF en cascada: pdfplumber → PyMuPDF → OCR Tesseract.
- Parser estructural de actas (`document_parser`), NER pesquero (spaCy EntityRuler).
- Normalización de nombres de entidades (minúsculas, sin acentos) y alias de empresas.
- Embeddings multilingües (`paraphrase-multilingual-MiniLM-L12-v2`) en ChromaDB.

## Uses

- **Usos previstos:** investigación académica, periodismo de datos, control público.
- **Usos NO apropiados:** imputación legal, difamación, decisiones administrativas
  automáticas. Ver `docs/adr/007-limites-eticos.md`.
- **Impacto en sujetos:** los conflictos de interés involucran personas nombradas;
  se distribuyen solo registros `verificado=TRUE` validados por experto legal.

## Distribution

- **¿Cómo se distribuirá?** Dataset abierto en **Zenodo** con DOI para citabilidad;
  código en GitHub (`arielgiamportone/cfp-audit-intelligence`).
- **Licencia:** MIT (código). El dataset derivado se publicará con licencia abierta
  (CC-BY) citando las fuentes oficiales.
- **Restricción:** no se incluyen datos `seed_demo` sintéticos como si fueran reales.

## Maintenance

- **¿Quién lo mantiene?** El autor del proyecto.
- **¿Cómo se actualiza?** Re-corriendo el pipeline (`make pipeline`) sobre nuevos
  años de actas; versionado por commits.
- **Trazabilidad de análisis IA:** cada salida del audit engine queda identificada
  por `(prompt_hash, input_hash, modelo_ia)` — reproducibilidad (ADR-005).

## Limitaciones conocidas

- Parte de los datos auxiliares son **seed/sintéticos** hasta correr el pipeline
  real (`cfp_cuotas`, `cargos_directivos` demo, gold set de evaluación).
- El parser puede fallar en actas de estructura atípica (sesiones extraordinarias).
- La cobertura temporal depende de la disponibilidad de PDFs públicos por año.

---

## Referencias

Ver [`docs/bibliography.md`](bibliography.md) para la bibliografía completa verificada del proyecto.

Referencias específicas de este documento:
- Gebru, T. et al. (2021). Datasheets for Datasets. *Communications of the ACM*, 64(12), 86–92. https://doi.org/10.1145/3458723
- Wilkinson, M.D. et al. (2016). The FAIR Guiding Principles for scientific data management. *Scientific Data*, 3, 160018. https://doi.org/10.1038/sdata.2016.18
- Villasante, S. et al. (2015). Reconstruction of marine fisheries catches in Argentina (1950–2010). *Sea Around Us Working Paper*. http://www.seaaroundus.org/doc/publications/wp/2015/Villasante-et-al-Argentina.pdf
- ADR-005 (reproducibilidad), ADR-007 (límites éticos).
