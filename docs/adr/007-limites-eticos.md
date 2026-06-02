# ADR-007: Límites Éticos y Marco de Responsabilidad

**Estado:** Aceptado  
**Fecha:** 2026-06-02  
**Decidido por:** Ariel Giamportone

## Contexto

El proyecto audita decisiones de un organismo público (CFP) sobre recursos
pesqueros, identifica empresas beneficiarias y, desde la Entrega #07, cruza
directores de empresas con miembros del CFP para detectar conflictos de interés.
Este tipo de análisis tiene implicancias legales y reputacionales reales sobre
personas e instituciones nombradas.

Hasta ahora, los principios éticos estaban **dispersos**: parte en `AGENTS.md`
(sección "Restricciones de seguridad"), parte en `CLAUDE.md`, y parte embebidos
en el system prompt de `audit_engine.py` ("tu análisis es descriptivo, no
acusatorio"). Esta dispersión genera ambigüedad: un revisor académico o legal no
tiene un documento único y citable que defina los límites del sistema.

Cualquier publicación en venues serios (Marine Policy, FAccT, AIES) exige una
declaración explícita de consideraciones éticas. Consolidarla en un ADR es la
forma estándar de hacerla trazable y defendible.

## Decisión

Consolidar todos los límites éticos en este documento como **fuente única
citable**. Los principios son:

### 1. Marco legal

- **Ley 24.922** (Régimen Federal de Pesca) — define el mandato del CFP y la
  obligación de no superar la Captura Máxima Sostenible recomendada por INIDEP.
- **Ley 25.188** (Ética en el Ejercicio de la Función Pública), Art. 13 —
  incompatibilidades y conflictos de interés de funcionarios públicos.
- **Principios de acceso a información pública** (Ley 27.275) — habilitan el uso
  de actas, Boletín Oficial y repositorios oficiales como datos públicos.

### 2. Análisis descriptivo, no acusatorio

Los hallazgos **identifican patrones**, no imputan delitos. El sistema describe
correlaciones estadísticas (concentración de cuotas, reversiones de veda,
superposición director-CFP) sin afirmar intencionalidad ni ilegalidad. Toda
salida del `audit_engine` lleva la marca de que el análisis es descriptivo
(system prompt, `src/analysis/audit_engine.py`).

### 3. Solo datos públicos

Todas las fuentes son documentos públicos: actas CFP, Boletín Oficial
(Sección 4 — Sociedades), repositorios INIDEP/Mar Abierto, FAO FIRMS, CONICET.
Nunca se usan datos privados, filtrados ni obtenidos sin autorización.

### 4. No difamación

- No se publican nombres de personas privadas sin consentimiento.
- Los conflictos de interés detectados (Entrega #07) se persisten con
  `verificado=FALSE` por defecto y **requieren validación por experto legal**
  antes de cualquier publicación.
- Los datos `seed_demo` (sintéticos) están claramente marcados y no representan
  personas reales hasta su verificación contra el Boletín Oficial.

### 5. Salvaguarda técnica contra alucinaciones

El groundedness automático (ADR-005) marca con `[BAJA_EVIDENCIA]` cualquier
hallazgo del LLM con anclaje textual < 0.15 en el documento fuente. Esto reduce
el riesgo de afirmaciones no respaldadas por el acta original.

### 6. Recomendaciones de proceso para publicación

- **Pre-registro OSF**: registrar hipótesis y plan analítico en el Open Science
  Framework *antes* de cada entrega de la Serie ALG, para prevenir críticas de
  cherry-picking o ajuste de método post-hoc. Crítico especialmente para la
  Entrega #05 (modelo predictivo).
- **Commits firmados (GPG)**: los commits significativos deben firmarse con la
  identidad GPG del autor, de modo que un revisor que inspeccione el repositorio
  pueda verificar que la dirección, las decisiones de diseño y la revisión son
  humanas y atribuibles, más allá de la asistencia de herramientas.

## Justificación

| Opción | Pros | Contras | Decisión |
|--------|------|---------|----------|
| **ADR único citable** (elegida) | Trazable, defendible, sin duplicación | Requiere mantener referencias cruzadas | ✅ Adoptada |
| Principios dispersos en AGENTS/CLAUDE | Sin trabajo extra | Ambiguo, no citable, drift entre archivos | ❌ Estado previo, insuficiente |
| Disclaimer genérico en el README | Visible | No cubre marco legal ni proceso de publicación | ❌ Insuficiente |

## Consecuencias

- **Positivas**:
  - Documento único citable en la sección de ética de cualquier paper.
  - `AGENTS.md` y `CLAUDE.md` apuntan a este ADR en lugar de duplicar principios.
  - Marco explícito para decidir qué se puede publicar y qué requiere verificación.

- **Negativas / limitaciones**:
  - El cumplimiento del pre-registro OSF y la firma GPG depende del autor; el
    sistema no los fuerza automáticamente.
  - La verificación legal de conflictos de interés es un paso humano externo no
    automatizable.

## Referencias

- Ley 24.922 — Régimen Federal de Pesca (Argentina, 1998).
- Ley 25.188 — Ética en el Ejercicio de la Función Pública (Argentina, 1999), Art. 13.
- Ley 27.275 — Derecho de Acceso a la Información Pública (Argentina, 2016).
- OCDE (2003). *Managing Conflict of Interest in the Public Service: OECD Guidelines.*
- FAO (1995). *Code of Conduct for Responsible Fisheries*, Art. 7.1.2 (transparencia).
- Nosek, B. et al. (2018). The preregistration revolution. *PNAS*, 115(11).
- ADR-005 (evaluación y reproducibilidad) — salvaguarda de groundedness.
