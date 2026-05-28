"""
Tests del módulo de parsing de actas del CFP.

Verifica que el parser identifica correctamente el formato real de las minutas:
decisiones narrativas, puntos de agenda, entidades extraídas.
"""
import pytest

from src.processing.document_parser import (
    Acta,
    Decision,
    _split_by_agenda,
    classify_decision,
    extract_referencias_cfp,
    extract_toneladas,
    parse_acta,
    parse_decisions,
    parse_fecha,
    parse_miembros,
    parse_numero_acta,
    parse_quorum,
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
        assert classify_decision("permiso de pesca para el buque San Martín") == "habilitacion_buque"

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
