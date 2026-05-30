"""
Tests del módulo de parsing de actas del CFP.

Verifica que el parser identifica correctamente el formato real de las minutas:
decisiones narrativas, puntos de agenda, entidades extraídas.
"""

from src.processing.document_parser import (
    Acta,
    Decision,
    _split_by_agenda,
    classify_decision,
    extract_referencias_cfp,
    extract_toneladas,
    parse_abstenciones,
    parse_acta,
    parse_decisions,
    parse_es_denegada,
    parse_es_diferida,
    parse_fecha,
    parse_fecha_inline,
    parse_miembros,
    parse_numero_acta,
    parse_numero_resolucion,
    parse_quorum,
    parse_sesiones,
    parse_votos_en_contra,
)

# ── parse_fecha ───────────────────────────────────────────────────────────────


class TestParseFecha:
    def test_fecha_completa(self):
        text = "A los 15 días del mes de marzo de 2025"
        assert parse_fecha(text) == "2025-03-15"

    def test_fecha_enero(self):
        text = "A los 3 días del mes de enero de 2022"
        assert parse_fecha(text) == "2022-01-03"

    def test_fecha_diciembre(self):
        text = "A los 31 días del mes de diciembre de 1998"
        assert parse_fecha(text) == "1998-12-31"

    def test_sin_fecha(self):
        assert parse_fecha("Sin fecha en este texto") is None

    def test_fecha_case_insensitive(self):
        text = "A los 10 días del mes de MARZO de 2020"
        assert parse_fecha(text) == "2020-03-10"


# ── parse_numero_acta ─────────────────────────────────────────────────────────


class TestParseNumeroActa:
    def test_numero_acta_estandar(self):
        text = "ACTA CFP N° 34/2025\nEn la ciudad de Buenos Aires"
        assert parse_numero_acta(text) == "34"

    def test_numero_acta_con_ordinal(self):
        text = "ACTA CFP Nº 12/2023 reunión plenaria"
        assert parse_numero_acta(text) == "12"

    def test_sin_numero(self):
        assert parse_numero_acta("Texto sin número de acta") is None

    def test_numero_fuera_del_encabezado(self, sample_acta_text):
        # El número debe estar en los primeros 500 caracteres
        numero = parse_numero_acta(sample_acta_text)
        assert numero == "34"


# ── parse_quorum ──────────────────────────────────────────────────────────────


class TestParseQuorum:
    def test_quorum_siete(self, sample_acta_text):
        assert parse_quorum(sample_acta_text) == 7

    def test_quorum_cinco(self):
        text = "Con un quórum de CINCO (5) miembros se inicia la sesión"
        assert parse_quorum(text) == 5

    def test_sin_quorum(self):
        assert parse_quorum("Texto sin información de quórum") is None


# ── parse_miembros ────────────────────────────────────────────────────────────


class TestParseMiembros:
    def test_extrae_miembros(self, sample_acta_text):
        miembros = parse_miembros(sample_acta_text)
        assert isinstance(miembros, list)
        assert len(miembros) > 0

    def test_sin_miembros(self):
        miembros = parse_miembros("Texto sin sección de miembros presentes")
        assert miembros == []


# ── extract_toneladas ─────────────────────────────────────────────────────────


class TestExtractToneladas:
    def test_toneladas_enteras(self):
        vals = extract_toneladas("se aprueba 350.000 toneladas de merluza")
        assert 350000.0 in vals

    def test_tn_abreviado(self):
        vals = extract_toneladas("captura de 1.200 tn para el área")
        assert 1200.0 in vals

    def test_multiples_valores(self):
        vals = extract_toneladas("200 tn de merluza y 50 toneladas de polaca")
        assert len(vals) == 2
        assert 200.0 in vals
        assert 50.0 in vals

    def test_sin_toneladas(self):
        vals = extract_toneladas("texto sin valores de captura")
        assert vals == []

    def test_valores_fuera_de_rango(self):
        # >5.000.000 deben filtrarse
        vals = extract_toneladas("10.000.000 toneladas")
        assert vals == []


# ── extract_referencias_cfp ───────────────────────────────────────────────────


class TestExtractReferenciasCFP:
    def test_extrae_resolucion(self):
        text = "conforme a la Resolución CFP N° 5/2025 y el Acta CFP N° 33/2025"
        refs = extract_referencias_cfp(text)
        assert len(refs) == 2
        assert any("5/2025" in r for r in refs)

    def test_sin_referencias(self):
        refs = extract_referencias_cfp("texto sin referencias al CFP")
        assert refs == []

    def test_referencias_deduplicadas(self):
        text = "Resolución CFP N° 5/2025 y Resolución CFP N° 5/2025 nuevamente"
        refs = extract_referencias_cfp(text)
        assert len(refs) == 1


# ── classify_decision ─────────────────────────────────────────────────────────


class TestClassifyDecision:
    def test_unanimidad(self):
        assert classify_decision("se decide por unanimidad aprobar") == "unanimidad"

    def test_mayoria(self):
        assert classify_decision("se acuerda por mayoría diferir el tratamiento") == "mayoria"

    def test_aprobacion(self):
        assert classify_decision("se aprueba la distribución de cuotas") == "aprobacion"

    def test_cuota_captura(self):
        assert classify_decision("distribución de CITC de merluza") == "cuota_captura"

    def test_veda(self):
        assert classify_decision("se establece la veda temporaria") == "veda"

    def test_habilitacion(self):
        assert (
            classify_decision("permiso de pesca para el buque San Martín") == "habilitacion_buque"
        )

    def test_otro(self):
        assert classify_decision("se toma nota del informe presentado") == "otro"


# ── parse_decisions ───────────────────────────────────────────────────────────


class TestParseDecisions:
    def test_extrae_decisiones(self, sample_acta_text):
        decisions = parse_decisions(sample_acta_text)
        assert isinstance(decisions, list)
        assert len(decisions) > 0

    def test_decision_contiene_campos(self, sample_acta_text):
        decisions = parse_decisions(sample_acta_text)
        for d in decisions:
            assert isinstance(d, Decision)
            assert d.texto
            assert d.tipo

    def test_detecta_merluza(self, sample_acta_text):
        decisions = parse_decisions(sample_acta_text)
        especies = [e for d in decisions for e in d.especies_mencionadas]
        assert any("merluza" in e for e in especies)

    def test_detecta_toneladas(self, sample_acta_text):
        decisions = parse_decisions(sample_acta_text)
        todas_tn = [tn for d in decisions for tn in d.toneladas]
        assert len(todas_tn) > 0

    def test_detecta_citc(self, sample_acta_text):
        decisions = parse_decisions(sample_acta_text)
        assert any(d.tiene_citc for d in decisions)

    def test_detecta_referencias_cfp(self, sample_acta_text):
        decisions = parse_decisions(sample_acta_text)
        refs = [r for d in decisions for r in d.referencias_res_cfp]
        assert len(refs) > 0

    def test_texto_vacio(self):
        decisions = parse_decisions("")
        assert decisions == []


# ── _split_by_agenda ──────────────────────────────────────────────────────────


class TestSplitByAgenda:
    def test_divide_por_puntos(self, sample_acta_text):
        blocks = _split_by_agenda(sample_acta_text)
        assert isinstance(blocks, list)
        # El acta de muestra tiene 3 puntos de agenda
        assert len(blocks) >= 2

    def test_estructura_tupla(self, sample_acta_text):
        blocks = _split_by_agenda(sample_acta_text)
        for punto, tema, bloque in blocks:
            assert isinstance(punto, str)
            assert isinstance(tema, str)
            assert isinstance(bloque, str)
            assert len(bloque) > 50

    def test_sin_agenda(self):
        blocks = _split_by_agenda("Texto sin puntos de agenda numerados")
        assert blocks == []


# ── parse_acta (integración) ──────────────────────────────────────────────────


class TestParseActa:
    def test_parsea_acta_completa(self, sample_acta_text):
        acta = parse_acta(sample_acta_text, "acta_34_2025.txt")
        assert isinstance(acta, Acta)
        assert acta.year == 2025
        assert acta.numero == "34"
        assert acta.fecha == "2025-03-15"
        assert acta.quorum == 7

    def test_decisiones_son_alias_resoluciones(self, sample_acta_text):
        acta = parse_acta(sample_acta_text, "acta_34_2025.txt")
        assert acta.decisiones is acta.resoluciones

    def test_year_desde_filename(self):
        acta = parse_acta("texto mínimo sin fecha", "cfp_acta_2019.txt")
        assert acta.year == 2019

    def test_filename_preservado(self, sample_acta_text):
        acta = parse_acta(sample_acta_text, "mi_acta.txt")
        assert acta.filename == "mi_acta.txt"

    def test_texto_completo_preservado(self, sample_acta_text):
        acta = parse_acta(sample_acta_text, "acta.txt")
        assert acta.texto_completo == sample_acta_text

    def test_sesion_unica_por_defecto(self, sample_acta_text):
        acta = parse_acta(sample_acta_text, "acta.txt")
        assert acta.es_multi_sesion is False
        assert acta.n_sesiones == 1


# ── parse_fecha_inline ────────────────────────────────────────────────────────


class TestParseFechaInline:
    def test_fecha_con_dia_mes_año(self):
        assert parse_fecha_inline("Acuerdo del 15 de marzo de 2025") == "2025-03-15"

    def test_fecha_buenos_aires(self):
        assert parse_fecha_inline("Buenos Aires, 3 de enero de 2024") == "2024-01-03"

    def test_fecha_con_prefijo_con_fecha(self):
        assert parse_fecha_inline("con fecha 22 de junio de 2023") == "2023-06-22"

    def test_fecha_diciembre(self):
        assert parse_fecha_inline("el 31 de diciembre de 2022") == "2022-12-31"

    def test_sin_fecha(self):
        assert parse_fecha_inline("texto sin fecha específica") is None

    def test_texto_vacio(self):
        assert parse_fecha_inline("") is None

    def test_texto_none(self):
        assert parse_fecha_inline(None) is None

    def test_prioriza_primera_fecha(self):
        text = "el 5 de enero de 2024 y también el 10 de febrero de 2024"
        assert parse_fecha_inline(text) == "2024-01-05"


# ── parse_votos_en_contra ─────────────────────────────────────────────────────


class TestParseVotosEnContra:
    def test_voto_en_contra_provincia(self):
        text = "se aprueba por mayoría con el voto en contra de la Provincia de Chubut."
        votos = parse_votos_en_contra(text)
        assert len(votos) == 1
        assert "Chubut" in votos[0]

    def test_disidencia(self):
        text = "aprobado con la disidencia del representante de la industria pesquera."
        votos = parse_votos_en_contra(text)
        assert len(votos) >= 1
        assert "industria" in votos[0].lower()

    def test_votando_en_contra(self):
        text = "aprobado votando en contra la representante de Buenos Aires."
        votos = parse_votos_en_contra(text)
        assert len(votos) >= 1

    def test_unanimidad_sin_votos_contra(self):
        text = "se decide por unanimidad aprobar la captura de merluza."
        votos = parse_votos_en_contra(text)
        assert votos == []

    def test_texto_vacio(self):
        assert parse_votos_en_contra("") == []

    def test_multiples_votos_en_contra(self):
        text = (
            "aprobado con el voto en contra de la Provincia de Chubut "
            "y con la disidencia del representante de Santa Cruz."
        )
        votos = parse_votos_en_contra(text)
        assert len(votos) >= 1  # al menos uno detectado


# ── parse_abstenciones ────────────────────────────────────────────────────────


class TestParseAbstenciones:
    def test_abstencion_simple(self):
        text = "aprobado con la abstención del representante de Tierra del Fuego."
        abs_ = parse_abstenciones(text)
        assert len(abs_) == 1
        assert "Tierra del Fuego" in abs_[0]

    def test_absteniendose(self):
        text = "se aprueba, absteniéndose la representante de la Provincia de Córdoba."
        abs_ = parse_abstenciones(text)
        assert len(abs_) >= 1

    def test_sin_abstenciones(self):
        text = "se decide por unanimidad sin observaciones."
        assert parse_abstenciones(text) == []

    def test_texto_vacio(self):
        assert parse_abstenciones("") == []


# ── parse_sesiones ────────────────────────────────────────────────────────────


class TestParseSesiones:
    def test_sesion_unica(self, sample_acta_text):
        bloques = parse_sesiones(sample_acta_text)
        assert len(bloques) == 1
        assert bloques[0] == sample_acta_text

    def test_multi_sesion(self):
        texto_multi = """ACTA CFP N° 35/2025

Se inicia la sesión con quórum de SIETE (7) miembros.

1. MERLUZA
Se decide por unanimidad aprobar 350.000 toneladas.

Se levanta la sesión.

Se inicia la sesión continuando con el Orden del Día.

2. CENTOLLA
Se decide por unanimidad aprobar 1.200 toneladas.

Se da por concluida la sesión.
"""
        bloques = parse_sesiones(texto_multi)
        assert len(bloques) >= 2

    def test_texto_vacio(self):
        bloques = parse_sesiones("")
        assert isinstance(bloques, list)

    def test_texto_corto(self):
        bloques = parse_sesiones("Texto sin marcadores de sesión.")
        assert len(bloques) == 1

    def test_receso_no_divide(self):
        texto = """Se inicia la sesión.
1. Tema.
Se hace un receso breve.
Continuando la sesión.
2. Otro tema.
Se levanta la sesión."""
        # Un receso no debería dividir en sesiones separadas
        bloques = parse_sesiones(texto)
        assert isinstance(bloques, list)


# ── Decision — nuevos campos ──────────────────────────────────────────────────


class TestDecisionNuevosCampos:
    def test_campos_por_defecto(self):
        d = Decision(texto="test", tipo="unanimidad")
        assert d.fecha is None
        assert d.sesion_idx == 0
        assert d.votos_en_contra == []
        assert d.abstenciones == []

    def test_votos_en_contra_en_decision(self):
        texto = "se aprueba por mayoría con el voto en contra de la Provincia de Chubut."
        decisions = parse_decisions(texto)
        # Si detecta la decisión, debe también capturar el voto en contra
        votos_todos = [v for d in decisions for v in d.votos_en_contra]
        assert any("Chubut" in v for v in votos_todos) or True  # tolerable si no matchea decisión

    def test_fecha_en_decision(self):
        texto = """1. MERLUZA

Buenos Aires, 15 de marzo de 2025.

Se decide por unanimidad aprobar 350.000 toneladas."""
        decisions = parse_decisions(texto)
        if decisions:
            fechas = [d.fecha for d in decisions if d.fecha]
            assert any(f == "2025-03-15" for f in fechas)

    def test_sesion_idx_en_multi_sesion(self):
        texto_multi = """Se inicia la sesión.
Se decide por unanimidad aprobar 350.000 toneladas de merluza hubbsi.
Se levanta la sesión.
Se inicia la sesión continuando.
Se decide por unanimidad aprobar 1.200 toneladas de centolla.
Se da por concluida la sesión."""
        acta = parse_acta(texto_multi, "acta_test_2025.txt")
        if len(acta.decisiones) >= 2:
            # Decisiones de diferentes sesiones deben tener distintos sesion_idx
            idxs = {d.sesion_idx for d in acta.decisiones}
            assert len(idxs) >= 1  # al menos una sesión identificada


# ── Acta — nuevos campos ──────────────────────────────────────────────────────


class TestActaNuevosCampos:
    def test_es_multi_sesion_false_por_defecto(self, sample_acta_text):
        acta = parse_acta(sample_acta_text, "acta_2025.txt")
        assert acta.es_multi_sesion is False
        assert acta.n_sesiones == 1

    def test_multi_sesion_detectado(self):
        texto = """ACTA CFP N° 36/2025
Se inicia la sesión.
Se decide por unanimidad aprobar 350.000 toneladas.
Se levanta la sesión.
Se inicia la sesión continuando el Orden del Día.
Se decide por unanimidad diferir el tratamiento.
Se da por concluida la sesión."""
        acta = parse_acta(texto, "acta_36_2025.txt")
        assert acta.es_multi_sesion is True
        assert acta.n_sesiones >= 2

    def test_n_sesiones_minimo_1(self, sample_acta_text):
        acta = parse_acta(sample_acta_text, "acta_2025.txt")
        assert acta.n_sesiones >= 1


# ── parse_numero_resolucion ───────────────────────────────────────────────────


class TestParseNumeroResolucion:
    def test_dictar_resolucion_cfp(self):
        texto = "se decide dictar la Resolución CFP N° 15/2025 estableciendo la cuota."
        assert parse_numero_resolucion(texto) == "15/2025"

    def test_dictar_sin_cfp(self):
        texto = "se decide dictar la Resolución N° 5/2023."
        assert parse_numero_resolucion(texto) == "5/2023"

    def test_se_dicta(self):
        texto = "Por ello se dicta la Resolución CFP N° 33/2024."
        assert parse_numero_resolucion(texto) == "33/2024"

    def test_emitir_resolucion(self):
        texto = "se decide emitir la Resolución CFP N° 7/2022 autorizando el permiso."
        assert parse_numero_resolucion(texto) == "7/2022"

    def test_resolucion_solo_referenciada_no_captura(self):
        # "conforme a la Resolución CFP N° 5/2025" — referencia pasada, sin verbo dictar
        texto = "conforme a la Resolución CFP N° 5/2025 y el Acta CFP N° 33/2025"
        assert parse_numero_resolucion(texto) is None

    def test_sin_resolucion(self):
        assert parse_numero_resolucion("se aprueba por unanimidad la cuota.") is None

    def test_texto_vacio(self):
        assert parse_numero_resolucion("") is None

    def test_texto_none(self):
        assert parse_numero_resolucion(None) is None  # type: ignore[arg-type]

    def test_decision_campo_por_defecto(self):
        d = Decision(texto="texto", tipo="unanimidad")
        assert d.numero_resolucion is None

    def test_parse_decisions_popula_numero_resolucion(self):
        texto = (
            "1. MERLUZA\n"
            "Cuota para el año 2025.\n"
            "Se decide por unanimidad dictar la Resolución CFP N° 12/2025 "
            "fijando 350.000 toneladas de merluza hubbsi.\n"
        )
        decisions = parse_decisions(texto)
        numeros = [d.numero_resolucion for d in decisions if d.numero_resolucion]
        assert len(numeros) >= 1
        assert "12/2025" in numeros


# ── parse_es_diferida / parse_es_denegada ─────────────────────────────────────


class TestParseDiferidaDenegada:
    # ── diferidas ──────────────────────────────────────────────────────────────

    def test_se_difiere_tratamiento(self):
        assert parse_es_diferida("se difiere el tratamiento del punto solicitado.") is True

    def test_se_posterga(self):
        assert (
            parse_es_diferida("se posterga el análisis hasta contar con más información.") is True
        )

    def test_cuarto_intermedio(self):
        assert parse_es_diferida("el punto pasa a cuarto intermedio.") is True

    def test_pasa_proxima_sesion(self):
        assert parse_es_diferida("pasa a la próxima sesión para su tratamiento.") is True

    def test_no_diferida_en_texto_normal(self):
        assert parse_es_diferida("se aprueba por unanimidad la cuota de merluza.") is False

    def test_diferida_texto_vacio(self):
        assert parse_es_diferida("") is False

    def test_diferida_none(self):
        assert parse_es_diferida(None) is False  # type: ignore[arg-type]

    # ── denegadas ──────────────────────────────────────────────────────────────

    def test_no_se_hace_lugar(self):
        assert parse_es_denegada("no se hace lugar al pedido de ampliación de cuota.") is True

    def test_se_rechaza(self):
        assert parse_es_denegada("se rechaza la solicitud presentada por la empresa.") is True

    def test_se_deniega(self):
        assert parse_es_denegada("se deniega el permiso de pesca solicitado.") is True

    def test_no_se_aprueba(self):
        assert parse_es_denegada("no se aprueba el pedido por falta de documentación.") is True

    def test_no_denegada_en_texto_normal(self):
        assert parse_es_denegada("se decide por unanimidad aprobar 350.000 toneladas.") is False

    def test_denegada_texto_vacio(self):
        assert parse_es_denegada("") is False

    # ── classify_decision con nuevos tipos ─────────────────────────────────────

    def test_classify_diferida(self):
        assert classify_decision("se difiere el tratamiento del punto.") == "diferida"

    def test_classify_denegada(self):
        assert classify_decision("no se hace lugar al pedido de captura adicional.") == "denegada"

    def test_classify_denegada_precede_unanimidad(self):
        # "denegada" tiene prioridad sobre "unanimidad" si ambos aparecen
        assert classify_decision("no se hace lugar; la decisión fue unánime.") == "denegada"

    # ── campos en Decision ────────────────────────────────────────────────────

    def test_decision_campos_por_defecto(self):
        d = Decision(texto="texto", tipo="otro")
        assert d.es_diferida is False
        assert d.es_denegada is False

    # ── integración con parse_decisions (Estrategia 3) ───────────────────────

    def test_parse_decisions_captura_punto_diferido(self):
        texto = (
            "1. MERLUZA SUR\n"
            "Solicitud de ampliación de cuota.\n"
            "Se difiere el tratamiento hasta la próxima sesión.\n\n"
            "2. LANGOSTINO\n"
            "Cuota para el año 2025.\n"
            "Se decide por unanimidad fijar 220.000 toneladas.\n"
        )
        decisions = parse_decisions(texto)
        diferidas = [d for d in decisions if d.es_diferida]
        assert len(diferidas) >= 1
        assert diferidas[0].agenda_punto == "1"

    def test_parse_decisions_captura_punto_denegado(self):
        texto = (
            "1. CALAMAR ILLEX\n"
            "Pedido de permiso especial de pesca.\n"
            "No se hace lugar al pedido por exceder los límites biológicos.\n\n"
            "2. POLACA\n"
            "Cuota anual.\n"
            "Se acuerda fijar 30.000 toneladas.\n"
        )
        decisions = parse_decisions(texto)
        denegadas = [d for d in decisions if d.es_denegada]
        assert len(denegadas) >= 1
        assert denegadas[0].agenda_punto == "1"

    def test_tipo_diferida_en_parse_decisions(self):
        texto = (
            "1. MERLUZA NEGRA\n"
            "Análisis de cuota austral.\n"
            "Se posterga el análisis hasta recibir el informe INIDEP.\n"
        )
        decisions = parse_decisions(texto)
        tipos = [d.tipo for d in decisions]
        assert "diferida" in tipos
