"""
Protocolo de anotación y gold set sintético para validación del audit_engine.

El gold set sintético sirve como demo funcional del framework de evaluación
hasta que un experto real (INIDEP o ex-CFP) realice las anotaciones definitivas.

Distribución del gold set (30 resoluciones):
  - 12 bajo  (40%): resoluciones rutinarias, sin banderas rojas
  - 10 medio (33%): resoluciones con indicios, requieren monitoreo
  -  5 alto  (17%): decisiones que superan CBA o revierten vedas
  -  3 crítico (10%): violaciones documentadas Ley 24.922 Art. 9

Nota metodológica: estas etiquetas son sintéticas y reflejan el juicio
del desarrollador del sistema. Deben ser revisadas y reemplazadas por un
experto del dominio antes de cualquier publicación académica.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from loguru import logger

GOLD_SET = [
    # ── bajo (12) ────────────────────────────────────────────────────────
    {
        "texto": "El CFP aprueba por unanimidad el plan de manejo de langostino patagónico "
                 "para el período 2023-2024, ajustando las cuotas de acuerdo con las "
                 "recomendaciones del INIDEP (ITO 42/2023). Votos a favor: 7. En contra: 0.",
        "categoria_humana": "bajo",
        "hallazgos_humanos": ["Cuota ajustada conforme CBA INIDEP"],
        "riesgo_score_humano": 10,
        "notas": "Decisión técnicamente fundada, aprobación unánime, cita INIDEP explícita.",
    },
    {
        "texto": "Se aprueba la habilitación del buque pesquero 'Antarés' para operar en "
                 "la Zona Económica Exclusiva Argentina. Se verifica documentación en regla.",
        "categoria_humana": "bajo",
        "hallazgos_humanos": [],
        "riesgo_score_humano": 5,
        "notas": "Habilitación de rutina, sin cuotas ni especies de alto riesgo.",
    },
    {
        "texto": "Se aprueba el presupuesto de actividades de investigación pesquera del INIDEP "
                 "para el ejercicio 2024. El monto asignado es de $450 millones.",
        "categoria_humana": "bajo",
        "hallazgos_humanos": [],
        "riesgo_score_humano": 8,
        "notas": "Resolución administrativa, no afecta cuotas ni recursos.",
    },
    {
        "texto": "El CFP toma conocimiento del informe de inspección de flotas pesqueras. "
                 "Se detectaron 3 infracciones menores que serán sancionadas.",
        "categoria_humana": "bajo",
        "hallazgos_humanos": ["Infracciones registradas y en proceso de sanción"],
        "riesgo_score_humano": 15,
        "notas": "Control normal, sistema funcionando.",
    },
    {
        "texto": "Se aprueba la renovación del permiso de pesca de corvina rubia para la "
                 "empresa Pesquera del Sur SA. La cuota asignada es de 800 toneladas, "
                 "dentro del límite de 950 toneladas recomendado por INIDEP.",
        "categoria_humana": "bajo",
        "hallazgos_humanos": ["Cuota dentro del límite INIDEP"],
        "riesgo_score_humano": 12,
        "notas": "Cuota por debajo de CBA. Gestión correcta.",
    },
    {
        "texto": "El CFP aprueba el calendario de vedas para el período de reproducción "
                 "de la merluza común. La veda rige del 1 de agosto al 30 de septiembre.",
        "categoria_humana": "bajo",
        "hallazgos_humanos": [],
        "riesgo_score_humano": 5,
        "notas": "Veda estacional rutinaria, medida de conservación apropiada.",
    },
    {
        "texto": "Se aprueba el plan de monitoreo satelital de buques pesqueros. "
                 "Obligatorio para embarcaciones mayores de 28 metros.",
        "categoria_humana": "bajo",
        "hallazgos_humanos": [],
        "riesgo_score_humano": 3,
        "notas": "Medida de control y transparencia.",
    },
    {
        "texto": "El CFP aprueba un convenio de cooperación técnica con el INIDEP para "
                 "el monitoreo de stocks de centolla del Canal Beagle. Período 2024-2026.",
        "categoria_humana": "bajo",
        "hallazgos_humanos": [],
        "riesgo_score_humano": 7,
        "notas": "Fortalecimiento de la base científica.",
    },
    {
        "texto": "Se aprueba la transferencia de cuota de merluza hubbsi entre Pesquera "
                 "Norte SA y Pesquera Sur SA. El total de cuota no se modifica.",
        "categoria_humana": "bajo",
        "hallazgos_humanos": ["Transferencia sin modificación del total de cuota"],
        "riesgo_score_humano": 18,
        "notas": "Transferencia sin modificación del total. Requiere monitoreo de concentración.",
    },
    {
        "texto": "El CFP toma nota del informe anual de capturas 2023. Las capturas totales "
                 "fueron de 780.000 toneladas, dentro de los límites establecidos.",
        "categoria_humana": "bajo",
        "hallazgos_humanos": [],
        "riesgo_score_humano": 10,
        "notas": "Dentro de límites. Indicador de sistema funcionando.",
    },
    {
        "texto": "Se aprueba el reglamento de pesca artesanal para comunidades costeras "
                 "de la provincia de Buenos Aires. Límite: 500 kg por embarcación por viaje.",
        "categoria_humana": "bajo",
        "hallazgos_humanos": [],
        "riesgo_score_humano": 8,
        "notas": "Regulación apropiada de pesca artesanal.",
    },
    {
        "texto": "El CFP aprueba el informe de estado de stocks de calamar illex para 2024. "
                 "El stock se encuentra en estado de plena explotación según INIDEP.",
        "categoria_humana": "bajo",
        "hallazgos_humanos": ["Stock en plena explotación — monitoreo continuo requerido"],
        "riesgo_score_humano": 22,
        "notas": "Plena explotación es la categoría límite; cualquier incremento es riesgo.",
    },
    # ── medio (10) ───────────────────────────────────────────────────────
    {
        "texto": "El CFP aprueba por 5 votos a favor y 2 en contra la cuota de merluza "
                 "común para 2024: 280.000 toneladas. La CBA recomendada por INIDEP fue "
                 "de 250.000 toneladas (ITO 36/2024).",
        "categoria_humana": "medio",
        "hallazgos_humanos": [
            "Cuota aprobada supera CBA INIDEP en 12% (280.000 vs 250.000 tn)",
            "Votación dividida (5-2) indica disidencia técnica",
        ],
        "riesgo_score_humano": 55,
        "notas": "Supera CBA pero dentro del umbral amarillo (≤15%). Requiere seguimiento.",
    },
    {
        "texto": "Se aprueba la ampliación de la zona de pesca de langostino patagónico "
                 "hacia el área sur del paralelo 48°S. El INIDEP no presentó objeción "
                 "formal pero recomendó estudios adicionales antes de la apertura.",
        "categoria_humana": "medio",
        "hallazgos_humanos": [
            "Ampliación sin evaluación completa de INIDEP",
            "Recomendación de estudios previos no implementada",
        ],
        "riesgo_score_humano": 50,
        "notas": "Decisión parcialmente fundamentada. Riesgo de impacto en stock no evaluado.",
    },
    {
        "texto": "El CFP ratifica con quórum mínimo (4 votos) la habilitación de Pesquera "
                 "Atlántica SA para operar en el área protegida del Banco Namuncurá. "
                 "La empresa es beneficiaria recurrente en los últimos 5 años.",
        "categoria_humana": "medio",
        "hallazgos_humanos": [
            "Aprobación con quórum mínimo (4 votos)",
            "Área protegida habilitada sin evaluación pública",
            "Empresa beneficiaria recurrente",
        ],
        "riesgo_score_humano": 60,
        "notas": "Quórum mínimo + área sensible + recurrencia de beneficiario son señales.",
    },
    {
        "texto": "Se otorga cuota de polaca de 45.000 toneladas para 2024. INIDEP recomendó "
                 "40.000 toneladas como CBA. La empresa Pesquera del Norte SA recibe el 60% "
                 "del total asignado.",
        "categoria_humana": "medio",
        "hallazgos_humanos": [
            "Cuota supera CBA en 12.5% (45.000 vs 40.000 tn)",
            "Una empresa recibe 60% del total — alta concentración",
        ],
        "riesgo_score_humano": 58,
        "notas": "Combinación de sobreasignación moderada y concentración empresarial.",
    },
    {
        "texto": "El CFP aprueba modificar el período de veda de abadejo, reduciéndolo de "
                 "90 días a 60 días. El INIDEP había recomendado mantener los 90 días.",
        "categoria_humana": "medio",
        "hallazgos_humanos": [
            "Reducción de veda contra recomendación INIDEP",
            "Potencial impacto en período reproductivo",
        ],
        "riesgo_score_humano": 55,
        "notas": "Decisión contraria a INIDEP pero sin revertir veda completamente.",
    },
    {
        "texto": "Se aprueba el traspaso de permiso de pesca de merluza negra entre empresas. "
                 "La empresa receptora tiene antecedentes de multas por pesca ilegal en 2019.",
        "categoria_humana": "medio",
        "hallazgos_humanos": [
            "Antecedentes de infracciones en empresa receptora",
            "Transferencia sin evaluación de historial completo",
        ],
        "riesgo_score_humano": 52,
        "notas": "Antecedentes son señal de alerta. Requiere verificación del proceso.",
    },
    {
        "texto": "El CFP aprueba cuota de anchoíta de 150.000 toneladas. INIDEP recomendó "
                 "135.000 toneladas. La votación fue unánime (7-0) sin debate registrado.",
        "categoria_humana": "medio",
        "hallazgos_humanos": [
            "Cuota supera CBA en 11% (150.000 vs 135.000 tn)",
            "Aprobación unánime sin debate — posible ausencia de deliberación real",
        ],
        "riesgo_score_humano": 48,
        "notas": "Unanimidad sin debate puede indicar presión o falta de independencia.",
    },
    {
        "texto": "Se aprueba la instalación de jaulas de cultivo de salmón en la Patagonia "
                 "Austral. El estudio de impacto ambiental fue presentado por la empresa, "
                 "no por organismo público.",
        "categoria_humana": "medio",
        "hallazgos_humanos": [
            "EIA presentado por parte interesada sin revisión independiente",
            "Potencial conflicto de interés en evaluación de impacto",
        ],
        "riesgo_score_humano": 50,
        "notas": "EIA propio genera conflicto metodológico. Requiere revisión independiente.",
    },
    {
        "texto": "El CFP establece un cupo especial de 5.000 toneladas de centolla para "
                 "exportación urgente. La medida no pasó por el proceso de consulta habitual "
                 "con las provincias costeras.",
        "categoria_humana": "medio",
        "hallazgos_humanos": [
            "Cupo extraordinario sin proceso de consulta provincial",
            "Posible bypass del procedimiento reglamentario",
        ],
        "riesgo_score_humano": 55,
        "notas": "Irregularidad procesal más que técnica.",
    },
    {
        "texto": "Se aprueba la pesca de corvina rubia en zona de exclusión temporal. "
                 "El período de exclusión fue establecido hace 18 meses por el mismo CFP.",
        "categoria_humana": "medio",
        "hallazgos_humanos": [
            "Reversión parcial de exclusión establecida por el propio CFP",
            "Sin informe técnico actualizado que justifique el cambio",
        ],
        "riesgo_score_humano": 58,
        "notas": "Auto-reversión sin nueva evidencia científica.",
    },
    # ── alto (5) ─────────────────────────────────────────────────────────
    {
        "texto": "El CFP aprueba cuota de merluza hubbsi de 420.000 toneladas para 2024. "
                 "La CBA recomendada por INIDEP fue de 319.000 toneladas (ITO 36/2024). "
                 "Votos a favor: 6. En contra: 1. La empresa Pesquera del Plata SA "
                 "recibirá el 35% del total.",
        "categoria_humana": "alto",
        "hallazgos_humanos": [
            "Cuota supera CBA en 31.7% (420.000 vs 319.000 tn) — nivel crítico",
            "Una empresa recibe 147.000 tn — alta concentración (HHI elevado)",
            "Votación 6-1: disidencia del representante del INIDEP",
        ],
        "riesgo_score_humano": 78,
        "notas": "Supera el umbral del 30% (FAO límite precautorio). Un voto en contra.",
    },
    {
        "texto": "Se levanta la veda de merluza negra en el área Malvinas Norte, vigente "
                 "desde 2021. El INIDEP advirtió que el stock aún no se ha recuperado "
                 "al nivel de explotación sostenible. La resolución fue aprobada con "
                 "4 votos a favor y 3 en contra.",
        "categoria_humana": "alto",
        "hallazgos_humanos": [
            "Reversion de veda activa contra recomendación INIDEP explícita",
            "Stock sin recuperar según evidencia científica disponible",
            "Votación ajustada (4-3) en decisión de alto impacto",
        ],
        "riesgo_score_humano": 82,
        "notas": "Caso claro de reversion de veda contra evidencia científica.",
    },
    {
        "texto": "El CFP otorga cuota de polaca de 80.000 toneladas. INIDEP recomendó "
                 "55.000 toneladas. La diferencia del 45% supera ampliamente el umbral "
                 "de alerta. Votación: 5-2.",
        "categoria_humana": "alto",
        "hallazgos_humanos": [
            "Cuota supera CBA en 45% — muy por encima del límite precautorio FAO",
            "Votación dividida indica reconocimiento de riesgo por parte de miembros",
        ],
        "riesgo_score_humano": 80,
        "notas": "45% sobre CBA es nivel de riesgo muy alto para stock pelágico.",
    },
    {
        "texto": "Se aprueba la pesca de fondo en áreas de alta sensibilidad ecológica "
                 "en el Atlántico Sur. El mismo CFP había declarado esas áreas como "
                 "zonas de protección especial en 2020. No se presentó nueva evidencia "
                 "científica que justifique el cambio.",
        "categoria_humana": "alto",
        "hallazgos_humanos": [
            "Reversión de área de protección especial sin nueva evidencia científica",
            "Pesca de fondo en zona sensible — daño potencial irreversible",
            "Inconsistencia con decisión propia de 2020",
        ],
        "riesgo_score_humano": 82,
        "notas": "Reversión sin fundamento científico en área ecológicamente sensible.",
    },
    {
        "texto": "El CFP aprueba cuota de langostino patagónico de 120.000 toneladas. "
                 "La CBA del INIDEP fue de 88.000 toneladas. Una sola empresa (Pesquera "
                 "del Sur SA) recibe el 45% del total. Votación: 7-0 en sesión de 12 minutos.",
        "categoria_humana": "alto",
        "hallazgos_humanos": [
            "Cuota supera CBA en 36.4% — nivel crítico FAO",
            "Altísima concentración: una empresa recibe 54.000 tn",
            "Sesión de 12 minutos para decisión de alto impacto — deliberación insuficiente",
        ],
        "riesgo_score_humano": 85,
        "notas": "Triple señal: sobreasignación masiva + concentración + deliberación mínima.",
    },
    # ── crítico (3) ──────────────────────────────────────────────────────
    {
        "texto": "El CFP aprueba cuota de merluza hubbsi de 550.000 toneladas para 2022. "
                 "La CBA recomendada por INIDEP fue de 290.000 toneladas. Incremento del "
                 "89.7%. Las tres empresas beneficiarias — Pesquera del Plata SA, "
                 "Atlántica Pesca SA y Pesquera Sur SA — son las principales contribuyentes "
                 "del fondo sectorial. El representante del INIDEP votó en contra.",
        "categoria_humana": "critico",
        "hallazgos_humanos": [
            "Cuota supera CBA en 89.7% — riesgo crítico de colapso de stock",
            "Potencial conflicto de interés: beneficiarios son contribuyentes del fondo",
            "Voto en contra del representante científico del INIDEP",
            "Violación directa del Art. 9 Ley 24.922",
        ],
        "riesgo_score_humano": 95,
        "notas": "Caso de máximo riesgo: sobreasignación extrema + conflicto de interés + oposición técnica.",
    },
    {
        "texto": "Se levanta la veda de merluza negra del Canal Beagle, establecida en 2018 "
                 "por recomendación de INIDEP debido a colapso del stock. El INIDEP advirtió "
                 "en 2024 que el stock sigue en estado crítico. La empresa Austral Pesca SA, "
                 "que solicitó el levantamiento, recibe permiso exclusivo por 3 años.",
        "categoria_humana": "critico",
        "hallazgos_humanos": [
            "Levantamiento de veda con stock en estado de colapso documentado",
            "Decisión directamente contraria a recomendación técnica INIDEP 2024",
            "Concesión exclusiva multi-año a empresa solicitante — posible captura regulatoria",
            "Violación del principio precautorio Ley 24.922 Art. 9",
        ],
        "riesgo_score_humano": 98,
        "notas": "Colapso documentado + levantamiento de veda + concesión exclusiva.",
    },
    {
        "texto": "El CFP aprueba cuota de calamar illex de 400.000 toneladas. INIDEP "
                 "recomendó 180.000 toneladas. El incremento del 122% se aprueba en sesión "
                 "extraordinaria de 8 minutos. Votación: 6-1. El miembro disidente declaró "
                 "que la medida 'compromete la disponibilidad futura del recurso'.",
        "categoria_humana": "critico",
        "hallazgos_humanos": [
            "Cuota supera CBA en 122% — sin precedente histórico",
            "Sesión extraordinaria de 8 minutos para decisión de máximo impacto",
            "El miembro disidente reconoce explícitamente el riesgo de agotamiento",
            "Riesgo crítico de sobreexplotación del stock de calamar illex",
        ],
        "riesgo_score_humano": 97,
        "notas": "122% sobre CBA es el nivel más extremo. Sesión extraordinaria de 8 min.",
    },
]


def seed_gold_set(db_path: Path | str) -> int:
    """
    Inserta el gold set sintético en la tabla anotaciones_humanas.

    Las resoluciones se crean en la tabla resoluciones con acta_id=NULL
    (registros de evaluación, no del pipeline real).

    Returns:
        Número de anotaciones insertadas.
    """
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(db_path) as conn:
        # Asegurar que las tablas existen
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS resoluciones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                acta_id INTEGER,
                numero TEXT, tipo TEXT, fecha TEXT, texto_completo TEXT,
                texto_resumen TEXT, votos_favor INTEGER, votos_contra INTEGER,
                abstenciones INTEGER, quorum INTEGER, riesgo_score REAL,
                categoria TEXT, analisis_ia TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS anotaciones_humanas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                resolucion_id INTEGER REFERENCES resoluciones(id),
                anotador TEXT NOT NULL,
                categoria_ia TEXT, categoria_humana TEXT,
                hallazgos_ia TEXT, hallazgos_humanos TEXT,
                riesgo_score_ia REAL, riesgo_score_humano INTEGER,
                coincide_categoria BOOLEAN, notas TEXT, confianza_pct INTEGER,
                is_gold_set BOOLEAN DEFAULT FALSE,
                timestamp TEXT DEFAULT (datetime('now')),
                UNIQUE(resolucion_id, anotador)
            );
            """
        )

        count = 0
        for i, item in enumerate(GOLD_SET, start=1):
            # Insertar resolución demo
            cur = conn.execute(
                """
                INSERT INTO resoluciones (numero, tipo, fecha, texto_completo, categoria)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    f"GOLD-{i:03d}",
                    "evaluacion_gold_set",
                    "2024-01-01",
                    item["texto"],
                    item["categoria_humana"],  # como referencia
                ),
            )
            resolucion_id = cur.lastrowid

            # Insertar anotación
            conn.execute(
                """
                INSERT INTO anotaciones_humanas
                    (resolucion_id, anotador, categoria_humana, hallazgos_humanos,
                     riesgo_score_humano, notas, is_gold_set, confianza_pct)
                VALUES (?,?,?,?,?,?,?,?)
                ON CONFLICT(resolucion_id, anotador) DO NOTHING
                """,
                (
                    resolucion_id,
                    "gold_sintetico",
                    item["categoria_humana"],
                    json.dumps(item["hallazgos_humanos"], ensure_ascii=False),
                    item["riesgo_score_humano"],
                    item["notas"],
                    True,
                    None,  # confianza no aplica para gold sintético
                ),
            )
            count += 1

        conn.commit()

    logger.info(f"Gold set sintético: {count} resoluciones insertadas en {db_path}")
    return count
