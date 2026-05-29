"""
Tests del NER pesquero especializado (FisheriesNER).

Verifica el reconocimiento de entidades de dominio CFP:
ESPECIE_PESCA, EMPRESA_PESCA, ZONA_PESCA, CUOTA_PESCA, NORMATIVA_CFP, BUQUE_PESCA.
"""
import pytest

spacy = pytest.importorskip("spacy", reason="spacy no instalado — omitiendo tests NER")

from src.processing.ner_pesquero import (
    FisheriesNER,
    ResultadoNER,
    EntidadExtraida,
    LABEL_ESPECIE,
    LABEL_EMPRESA,
    LABEL_ZONA,
    LABEL_CUOTA,
    LABEL_NORMATIVA,
    LABEL_BUQUE,
    get_ner,
)


@pytest.fixture(scope="module")
def ner():
    return FisheriesNER()


# ── Especies ──────────────────────────────────────────────────────────────────

class TestEspecies:
    def test_merluza_hubbsi(self, ner):
        r = ner.process("Se aprueba cuota de merluza hubbsi para 2024.")
        assert "merluza hubbsi" in r.especies

    def test_merluza_negra(self, ner):
        r = ner.process("El stock de merluza negra en zona austral.")
        assert "merluza negra" in r.especies

    def test_calamar_illex(self, ner):
        r = ner.process("Temporada de calamar illex en el Mar Argentino.")
        assert "calamar illex" in r.especies

    def test_langostino_patagonico(self, ner):
        r = ner.process("La evaluación de langostino patagónico indica recuperación.")
        assert "langostino patagónico" in r.especies

    def test_centolla(self, ner):
        r = ner.process("La centolla en Tierra del Fuego tiene veda.")
        assert "centolla" in r.especies

    def test_vieira(self, ner):
        r = ner.process("La vieira patagónica se encuentra en buen estado.")
        assert "vieira patagónica" in r.especies

    def test_abadejo(self, ner):
        r = ner.process("Cuota de abadejo aprobada por el CFP.")
        assert "abadejo" in r.especies

    def test_anchoita(self, ner):
        r = ner.process("Evaluación de anchoíta en aguas argentinas.")
        assert "anchoíta" in r.especies

    def test_merluza_cola(self, ner):
        r = ner.process("Merluza de cola en zona patagónica.")
        assert any(e.lower() == "merluza de cola" for e in r.especies)

    def test_sin_especie(self, ner):
        r = ner.process("El CFP sesionó el 15 de marzo de 2024.")
        assert r.especies == []

    def test_case_insensitive(self, ner):
        r = ner.process("Cuota de MERLUZA HUBBSI aprobada.")
        assert "MERLUZA HUBBSI" in r.especies or "merluza hubbsi" in [e.lower() for e in r.especies]


# ── Empresas ──────────────────────────────────────────────────────────────────

class TestEmpresas:
    def test_argenova_sa(self, ner):
        r = ner.process("ARGENOVA S.A. solicitó habilitación para pescar merluza.")
        assert any("ARGENOVA" in e for e in r.empresas)

    def test_conarpesa(self, ner):
        r = ner.process("CONARPESA presentó la documentación requerida.")
        assert "CONARPESA" in r.empresas

    def test_arbumasa(self, ner):
        r = ner.process("La empresa ARBUMASA opera en el Atlántico Sur.")
        assert "ARBUMASA" in r.empresas

    def test_patron_sa_generico(self, ner):
        r = ner.process("PESQUERA DEL SUR S.A. solicita extensión de cuota.")
        assert any("S.A" in e for e in r.empresas)

    def test_patron_srl(self, ner):
        r = ner.process("MARPESCA S.R.L. presentó informe técnico.")
        assert any("S.R.L" in e for e in r.empresas)

    def test_multiples_empresas(self, ner):
        r = ner.process("CONARPESA y ARBUMASA solicitaron cuotas de merluza.")
        assert len(r.empresas) >= 2


# ── Zonas ─────────────────────────────────────────────────────────────────────

class TestZonas:
    def test_sur_41(self, ner):
        r = ner.process("Cuota para merluza en Sur 41°S aprobada.")
        assert any("Sur 41" in z for z in r.zonas)

    def test_norte_41(self, ner):
        r = ner.process("El stock norte 41°S se encuentra sobrexplotado.")
        assert any("Norte 41" in z or "norte 41" in z.lower() for z in r.zonas)

    def test_golfo_san_jorge(self, ner):
        r = ner.process("La pesca en el Golfo San Jorge fue evaluada.")
        assert any("Golfo San Jorge" in z for z in r.zonas)

    def test_patagonia(self, ner):
        r = ner.process("Los recursos pesqueros de la Patagonia incluyen langostino y merluza.")
        assert any("patagonia" in z.lower() or "patagón" in z.lower() for z in r.zonas)

    def test_tierra_del_fuego(self, ner):
        r = ner.process("La centolla en Tierra del Fuego tiene veda establecida.")
        assert any("Tierra del Fuego" in z for z in r.zonas)

    def test_mar_argentino(self, ner):
        r = ner.process("El calamar en el Mar Argentino se explota intensamente.")
        assert any("Mar Argentino" in z or "mar argentino" in z.lower() for z in r.zonas)


# ── Cuotas ────────────────────────────────────────────────────────────────────

class TestCuotas:
    def test_toneladas(self, ner):
        r = ner.process("Se aprueba una cuota de 300.000 toneladas de merluza.")
        assert any("300.000" in c or "300" in c for c in r.cuotas)

    def test_tn(self, ner):
        r = ner.process("La CBA recomendada es de 150.000 tn para langostino.")
        assert any("150.000" in c for c in r.cuotas)

    def test_cuota_con_prefijo_cba(self, ner):
        r = ner.process("CBA de 200.000 toneladas recomendadas por INIDEP.")
        assert r.cuotas != []

    def test_sin_cuota(self, ner):
        r = ner.process("El CFP aprobó la resolución por unanimidad.")
        assert r.cuotas == []


# ── Normativas ────────────────────────────────────────────────────────────────

class TestNormativas:
    def test_resolucion_cfp_con_numero(self, ner):
        r = ner.process("Resolución CFP N° 15/2024 fue aprobada.")
        assert any("15/2024" in n for n in r.normativas)

    def test_resolucion_cfp_simple(self, ner):
        r = ner.process("La Resolución CFP fue revisada por el consejo.")
        assert r.normativas != []

    def test_ley_24922(self, ner):
        r = ner.process("Según lo establece la Ley 24.922, el CFP debe basarse en el INIDEP.")
        assert any("24.922" in n or "24922" in n for n in r.normativas)

    def test_articulo_9(self, ner):
        r = ner.process("El Art. 9 de la Ley 24.922 establece la obligación de respetar la CBA.")
        assert r.normativas != []

    def test_sin_normativa(self, ner):
        r = ner.process("Se aprueba cuota de merluza hubbsi.")
        assert r.normativas == []


# ── Buques ────────────────────────────────────────────────────────────────────

class TestBuques:
    def test_bp_nombre(self, ner):
        r = ner.process("El B/P ARGENOVA IV opera en la zona Sur.")
        assert any("ARGENOVA" in b for b in r.buques)

    def test_bm_nombre(self, ner):
        r = ner.process("El B/M ESTREMAR opera con bandera argentina.")
        assert any("ESTREMAR" in b for b in r.buques)

    def test_sin_buque(self, ner):
        r = ner.process("CONARPESA presentó solicitud de cuota.")
        assert r.buques == []


# ── ResultadoNER ──────────────────────────────────────────────────────────────

class TestResultadoNER:
    def test_texto_vacio(self, ner):
        r = ner.process("")
        assert r.entidades == []
        assert r.especies == []

    def test_texto_none_like(self, ner):
        r = ner.process("   ")
        assert r.entidades == []

    def test_to_dict_keys(self, ner):
        r = ner.process("Cuota de merluza hubbsi aprobada por CONARPESA.")
        d = r.to_dict()
        assert set(d.keys()) == {"especies", "empresas", "zonas", "cuotas", "normativas", "buques"}

    def test_by_label(self, ner):
        r = ner.process("Cuota de merluza hubbsi para CONARPESA.")
        assert "merluza hubbsi" in r.by_label(LABEL_ESPECIE)

    def test_dedup_entidades(self, ner):
        r = ner.process("merluza hubbsi y merluza hubbsi son mencionadas dos veces.")
        # No deben aparecer duplicados
        assert len(r.especies) == len(set(r.especies))

    def test_contexto_incluido(self, ner):
        r = ner.process("Aprobación de cuota de merluza hubbsi para la zona.")
        esp = [e for e in r.entidades if e.etiqueta == LABEL_ESPECIE]
        assert len(esp) > 0
        assert len(esp[0].contexto) > 0

    def test_extract_from_acta(self, ner):
        texto = """
        A los 15 días del mes de marzo de 2024, se reunió el CFP.
        Se aprueba Resolución CFP N° 5/2024: cuota de 300.000 toneladas
        de merluza hubbsi en zona Sur 41°S para ARGENOVA S.A.
        Se decide por unanimidad.
        """
        d = ner.extract_from_acta(texto)
        assert "merluza hubbsi" in d["especies"]
        assert any("ARGENOVA" in e for e in d["empresas"])
        assert any("Sur 41" in z for z in d["zonas"])


# ── Batch processing ──────────────────────────────────────────────────────────

class TestBatch:
    def test_batch_retorna_lista(self, ner):
        textos = [
            "Cuota de merluza hubbsi aprobada.",
            "Langostino patagónico en recuperación.",
            "Sin especies relevantes aquí.",
        ]
        resultados = ner.process_batch(textos)
        assert len(resultados) == 3

    def test_batch_entidades_correctas(self, ner):
        textos = ["merluza hubbsi", "calamar illex", "langostino"]
        resultados = ner.process_batch(textos)
        especies = [r.especies[0] if r.especies else None for r in resultados]
        assert "merluza hubbsi" in especies
        assert "calamar illex" in especies


# ── get_ner singleton ─────────────────────────────────────────────────────────

class TestSingleton:
    def test_get_ner_retorna_instancia(self):
        ner1 = get_ner()
        ner2 = get_ner()
        assert ner1 is ner2

    def test_singleton_funcional(self):
        ner = get_ner()
        r = ner.process("cuota de merluza hubbsi")
        assert "merluza hubbsi" in r.especies
