"""Tests para GroundednessChecker — verificación de anclaje textual de hallazgos."""

import pytest

from src.evaluation.groundedness import (
    LOW_EVIDENCE_PREFIX,
    LOW_EVIDENCE_THRESHOLD,
    GroundednessChecker,
    _jaccard,
    _tokenize,
)


class TestTokenize:
    def test_minusculas(self):
        tokens = _tokenize("Merluza Hubbsi INIDEP")
        assert all(t == t.lower() for t in tokens)

    def test_elimina_stopwords(self):
        tokens = _tokenize("de la el merluza")
        assert "de" not in tokens
        assert "merluza" in tokens

    def test_solo_alfanumericos(self):
        tokens = _tokenize("cuota: 300.000 ton.")
        assert all(t.isalnum() for t in tokens)

    def test_texto_vacio(self):
        assert _tokenize("") == []

    def test_normaliza_acentos(self):
        tokens = _tokenize("cuotas aprobación sostenibilidad")
        assert "aprobacion" in tokens or "aprobacion" in " ".join(tokens)


class TestJaccard:
    def test_identicos(self):
        s = frozenset({"a", "b", "c"})
        assert _jaccard(s, s) == 1.0

    def test_disjuntos(self):
        assert _jaccard(frozenset({"a"}), frozenset({"b"})) == 0.0

    def test_parcial(self):
        a = frozenset({"a", "b", "c"})
        b = frozenset({"b", "c", "d"})
        score = _jaccard(a, b)
        assert 0 < score < 1

    def test_vacios(self):
        assert _jaccard(frozenset(), frozenset()) == 0.0


class TestGroundednessChecker:
    def setup_method(self):
        self.checker = GroundednessChecker()

    def test_score_alto_cita_textual(self):
        texto = (
            "El CFP aprueba cuota de merluza hubbsi de 420.000 toneladas "
            "para el período 2024. La CBA recomendada por INIDEP fue de "
            "319.000 toneladas según ITO 36/2024."
        )
        hallazgo = "cuota merluza 420 toneladas 2024 INIDEP 319"
        score = self.checker.score_hallazgo(hallazgo, texto)
        assert score > 0.15

    def test_score_bajo_hallazgo_inventado(self):
        texto = "El CFP aprueba la veda de langostino patagónico."
        hallazgo = "La empresa XYZ recibió una concesión exclusiva de 50 años."
        score = self.checker.score_hallazgo(hallazgo, texto)
        assert score < LOW_EVIDENCE_THRESHOLD

    def test_score_entre_cero_y_uno(self):
        for hallazgo, texto in [
            ("merluza cuota INIDEP", "El CFP aprueba cuotas de merluza según INIDEP."),
            ("empresa recurrente beneficiario", "Buque habilitado para pesca artesanal."),
            ("", "texto"),
            ("hallazgo", ""),
        ]:
            score = self.checker.score_hallazgo(hallazgo, texto)
            assert 0.0 <= score <= 1.0

    def test_hallazgo_vacio_retorna_cero(self):
        assert self.checker.score_hallazgo("", "texto fuente") == 0.0

    def test_fuente_vacia_retorna_cero(self):
        assert self.checker.score_hallazgo("hallazgo importante", "") == 0.0

    def test_check_all_longitud(self):
        hallazgos = ["hallazgo a", "hallazgo b", "hallazgo c"]
        texto = "contexto de prueba con datos sobre pesca"
        resultado = self.checker.check_all(hallazgos, texto)
        assert len(resultado["scores"]) == len(hallazgos)
        assert "avg" in resultado
        assert "low_evidence_indices" in resultado

    def test_check_all_vacio(self):
        resultado = self.checker.check_all([], "texto fuente")
        assert resultado["scores"] == []
        assert resultado["avg"] == 0.0
        assert resultado["low_evidence_indices"] == []

    def test_check_all_indices_correctos(self):
        hallazgos = [
            "cuota merluza aprobada 280000 toneladas INIDEP",  # presente en texto
            "empresa recibió millones de dólares en contratos secretos",  # inventado
        ]
        texto = "El CFP aprueba cuota merluza 280000 toneladas recomendada por INIDEP."
        resultado = self.checker.check_all(hallazgos, texto)
        assert 1 in resultado["low_evidence_indices"]

    def test_flag_agrega_prefijo(self):
        hallazgos = ["hallazgo sin evidencia en el texto fuente inventado"]
        scores = [0.05]
        flagged = self.checker.flag_low_evidence(hallazgos, scores)
        assert flagged[0].startswith(LOW_EVIDENCE_PREFIX)

    def test_flag_no_duplica_prefijo(self):
        hallazgo = LOW_EVIDENCE_PREFIX + "ya prefijado"
        flagged = self.checker.flag_low_evidence([hallazgo], [0.05])
        assert flagged[0].count(LOW_EVIDENCE_PREFIX) == 1

    def test_flag_no_afecta_buena_evidencia(self):
        hallazgos = ["cuota merluza aprobada por INIDEP"]
        scores = [0.8]
        flagged = self.checker.flag_low_evidence(hallazgos, scores)
        assert not flagged[0].startswith(LOW_EVIDENCE_PREFIX)

    def test_score_reproducible(self):
        hallazgo = "cuota langostino patagónico INIDEP recomendación"
        texto = "El CFP aprueba cuota de langostino patagónico según recomendación de INIDEP."
        s1 = self.checker.score_hallazgo(hallazgo, texto)
        s2 = self.checker.score_hallazgo(hallazgo, texto)
        assert s1 == s2

    def test_score_mayor_con_texto_mas_especifico(self):
        hallazgo = "merluza cuota INIDEP 319000 toneladas"
        texto_especifico = "cuota merluza INIDEP 319000 toneladas CFP aprueba"
        texto_irrelevante = "embarcación pesquera habilitada zona exclusiva costera provincial"
        s_especifico = self.checker.score_hallazgo(hallazgo, texto_especifico)
        s_irrelevante = self.checker.score_hallazgo(hallazgo, texto_irrelevante)
        assert s_especifico > s_irrelevante
