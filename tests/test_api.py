"""
Tests de la API REST FastAPI del CFP Audit Intelligence.

Usa TestClient de FastAPI con una BD SQLite temporal para tests aislados.
"""
import sqlite3
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from unittest.mock import patch


@pytest.fixture(scope="module")
def test_db(tmp_path_factory):
    """BD SQLite temporal con datos de prueba."""
    db = tmp_path_factory.mktemp("api_db") / "catalog.db"
    conn = sqlite3.connect(db)
    conn.executescript("""
        CREATE TABLE actas (
            id INTEGER PRIMARY KEY, year INTEGER, nombre TEXT, url TEXT,
            filename TEXT, is_anexo INTEGER DEFAULT 0, local_path TEXT,
            file_hash TEXT, download_status TEXT DEFAULT 'pending',
            text_extracted INTEGER DEFAULT 0, text_path TEXT,
            embedded INTEGER DEFAULT 0, analyzed INTEGER DEFAULT 0
        );
        CREATE TABLE resoluciones (
            id INTEGER PRIMARY KEY, acta_id INTEGER, numero TEXT,
            tipo TEXT, fecha TEXT, texto_completo TEXT, texto_resumen TEXT,
            votos_favor INTEGER, votos_contra INTEGER, abstenciones INTEGER,
            quorum INTEGER, riesgo_score REAL, categoria TEXT, analisis_ia TEXT
        );
        CREATE TABLE entidades (
            id INTEGER PRIMARY KEY, tipo TEXT, nombre TEXT, nombre_norm TEXT
        );
        CREATE TABLE menciones (
            id INTEGER PRIMARY KEY, resolucion_id INTEGER,
            entidad_id INTEGER, contexto TEXT, sentimiento TEXT
        );
        CREATE TABLE alertas_reglas (
            id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT, tipo TEXT,
            especie_code TEXT, zona TEXT, year_desde INTEGER, year_hasta INTEGER,
            umbral_pct REAL, umbral_estado TEXT, severidad TEXT DEFAULT 'warning',
            activa INTEGER DEFAULT 1, descripcion TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE alertas_historial (
            id INTEGER PRIMARY KEY AUTOINCREMENT, regla_id INTEGER,
            tipo TEXT, especie TEXT, especie_code TEXT, zona TEXT, year INTEGER,
            valor_detectado REAL, umbral REAL, mensaje TEXT, severidad TEXT,
            acta_referencia TEXT, resuelta INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE inidep_evaluaciones (
            id INTEGER PRIMARY KEY, especie TEXT, especie_code TEXT,
            zona TEXT, year INTEGER, cba_recomendada_tn REAL,
            cba_alternativa_tn REAL, estado_stock TEXT, numero_ito TEXT,
            fuente_url TEXT, notas TEXT, created_at TEXT
        );
        CREATE TABLE cfp_cuotas (
            id INTEGER PRIMARY KEY, especie TEXT, especie_code TEXT,
            zona TEXT, year INTEGER, cmp_aprobada_tn REAL,
            tipo_decision TEXT, acta_referencia TEXT, resolucion_cfp TEXT,
            created_at TEXT
        );
        CREATE TABLE comparacion_cfp_inidep (
            id INTEGER PRIMARY KEY, especie TEXT, especie_code TEXT,
            zona TEXT, year INTEGER, cba_inidep_tn REAL, cmp_cfp_tn REAL,
            diferencia_tn REAL, ratio_sobreasignacion REAL, nivel_alerta TEXT,
            descripcion_alerta TEXT, numero_ito TEXT, acta_cfp TEXT,
            created_at TEXT
        );
    """)
    # Datos de prueba
    conn.execute(
        "INSERT INTO actas (id, year, nombre, url, download_status) VALUES (?,?,?,?,?)",
        (1, 2023, "Acta CFP 180/2023", "https://cfp.gob.ar/acta/180", "downloaded"),
    )
    conn.execute(
        "INSERT INTO actas (id, year, nombre, url, download_status, text_extracted) VALUES (?,?,?,?,?,?)",
        (2, 2024, "Acta CFP 190/2024", "https://cfp.gob.ar/acta/190", "downloaded", 1),
    )
    conn.execute(
        """INSERT INTO resoluciones (id, acta_id, numero, tipo, categoria,
           texto_resumen, votos_favor, votos_contra)
           VALUES (?,?,?,?,?,?,?,?)""",
        (1, 1, "5", "cuota_captura", "cuota_captura",
         "Se aprueba cuota de merluza hubbsi para 2023.", 8, 0),
    )
    conn.execute(
        "INSERT INTO entidades (id, tipo, nombre, nombre_norm) VALUES (?,?,?,?)",
        (1, "especie", "merluza hubbsi", "merluza hubbsi"),
    )
    conn.execute(
        "INSERT INTO entidades (id, tipo, nombre, nombre_norm) VALUES (?,?,?,?)",
        (2, "empresa", "ARGENOVA S.A.", "argenova s.a."),
    )
    conn.execute(
        "INSERT INTO menciones (id, resolucion_id, entidad_id, contexto) VALUES (?,?,?,?)",
        (1, 1, 1, "cuota de merluza hubbsi"),
    )
    conn.execute(
        "INSERT INTO menciones (id, resolucion_id, entidad_id, contexto) VALUES (?,?,?,?)",
        (2, 1, 2, "aprobada para ARGENOVA S.A."),
    )
    conn.execute(
        """INSERT INTO comparacion_cfp_inidep
           (id, especie, especie_code, zona, year, cba_inidep_tn, cmp_cfp_tn,
            diferencia_tn, ratio_sobreasignacion, nivel_alerta)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (1, "merluza hubbsi", "merluza_hubbsi", "Sur 41°S", 2023,
         300000, 345000, 45000, 1.15, "amarillo"),
    )
    conn.execute(
        """INSERT INTO alertas_historial
           (tipo, especie, especie_code, zona, year, valor_detectado, umbral,
            mensaje, severidad, resuelta)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        ("cba_exceso", "merluza hubbsi", "merluza_hubbsi", "Sur 41°S",
         2023, 115.0, 115.0,
         "merluza hubbsi 2023: CMP aprobada = 345.000 tn (115.0% de CBA 300.000 tn)",
         "warning", 0),
    )
    conn.commit()
    conn.close()
    return db


@pytest.fixture(scope="module")
def client(test_db):
    """TestClient con BD temporal."""
    with patch("src.api.deps.DB_PATH", test_db), \
         patch("src.api.routers.actas.DB_PATH", test_db), \
         patch("src.api.routers.entidades.DB_PATH", test_db), \
         patch("src.api.routers.alertas.DB_PATH", test_db), \
         patch("src.api.routers.inidep.DB_PATH", test_db), \
         patch("src.api.routers.analysis.DB_PATH", test_db):
        from src.api.main import app
        with TestClient(app) as c:
            yield c


# ── Health ────────────────────────────────────────────────────────────────────

class TestHealth:
    def test_health_ok(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_root_redirects(self, client):
        r = client.get("/", follow_redirects=False)
        assert r.status_code in (302, 307)

    def test_openapi_schema(self, client):
        r = client.get("/openapi.json")
        assert r.status_code == 200
        schema = r.json()
        assert schema["info"]["title"] == "CFP Audit Intelligence API"


# ── Actas ─────────────────────────────────────────────────────────────────────

class TestActas:
    def test_list_actas(self, client):
        r = client.get("/actas")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] >= 2
        assert len(data["items"]) >= 2

    def test_list_actas_filtro_year(self, client):
        r = client.get("/actas?year=2023")
        assert r.status_code == 200
        data = r.json()
        assert all(a["year"] == 2023 for a in data["items"])

    def test_get_acta_existente(self, client):
        r = client.get("/actas/1")
        assert r.status_code == 200
        assert r.json()["id"] == 1
        assert r.json()["year"] == 2023

    def test_get_acta_inexistente(self, client):
        r = client.get("/actas/9999")
        assert r.status_code == 404

    def test_get_resoluciones_acta(self, client):
        r = client.get("/actas/1/resoluciones")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] >= 1

    def test_paginacion(self, client):
        r = client.get("/actas?page=1&page_size=1")
        assert r.status_code == 200
        assert len(r.json()["items"]) == 1


# ── Entidades ─────────────────────────────────────────────────────────────────

class TestEntidades:
    def test_list_entidades(self, client):
        r = client.get("/entidades")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] >= 2

    def test_filtro_tipo_especie(self, client):
        r = client.get("/entidades?tipo=especie")
        assert r.status_code == 200
        items = r.json()["items"]
        assert all(e["tipo"] == "especie" for e in items)

    def test_busqueda_por_nombre(self, client):
        r = client.get("/entidades?q=merluza")
        assert r.status_code == 200
        items = r.json()["items"]
        assert any("merluza" in e["nombre"].lower() for e in items)

    def test_get_entidad(self, client):
        r = client.get("/entidades/1")
        assert r.status_code == 200
        assert r.json()["id"] == 1

    def test_get_entidad_inexistente(self, client):
        r = client.get("/entidades/9999")
        assert r.status_code == 404


# ── Alertas ───────────────────────────────────────────────────────────────────

class TestAlertas:
    def test_list_alertas(self, client):
        r = client.get("/alertas")
        assert r.status_code == 200
        data = r.json()
        assert "total" in data
        assert "items" in data

    def test_resumen_alertas(self, client):
        r = client.get("/alertas/resumen")
        assert r.status_code == 200
        data = r.json()
        assert "total" in data

    def test_filtro_severidad(self, client):
        r = client.get("/alertas?severidad=warning")
        assert r.status_code == 200

    def test_evaluar_alertas(self, client):
        r = client.post("/alertas/evaluar")
        assert r.status_code == 200
        data = r.json()
        assert "alertas_generadas" in data


# ── INIDEP ────────────────────────────────────────────────────────────────────

class TestINIDEP:
    def test_comparaciones(self, client):
        r = client.get("/inidep/comparaciones")
        assert r.status_code == 200
        data = r.json()
        assert "total" in data
        assert "items" in data

    def test_comparaciones_filtro_alerta(self, client):
        r = client.get("/inidep/comparaciones?nivel_alerta=amarillo")
        assert r.status_code == 200
        items = r.json()["items"]
        assert all(i["nivel_alerta"] == "amarillo" for i in items)

    def test_evaluaciones(self, client):
        r = client.get("/inidep/evaluaciones")
        assert r.status_code == 200

    def test_comparaciones_paginacion(self, client):
        r = client.get("/inidep/comparaciones?page=1&page_size=10")
        assert r.status_code == 200


# ── Analysis / NER ────────────────────────────────────────────────────────────

class TestAnalysis:
    def test_stats(self, client):
        r = client.get("/analysis/stats")
        assert r.status_code == 200
        data = r.json()
        assert "total_actas" in data
        assert data["total_actas"] >= 2

    def test_ner_endpoint(self, client):
        r = client.post("/analysis/ner", json={
            "texto": "Se aprueba cuota de merluza hubbsi para ARGENOVA S.A. en Sur 41°S."
        })
        # 200 si spacy disponible, 503 si no
        assert r.status_code in (200, 503)
        if r.status_code == 200:
            data = r.json()
            assert "especies" in data
            assert "empresas" in data

    def test_ner_texto_vacio(self, client):
        r = client.post("/analysis/ner", json={"texto": ""})
        assert r.status_code == 422  # validation error

    def test_ner_texto_muy_largo(self, client):
        r = client.post("/analysis/ner", json={"texto": "x" * 60_000})
        assert r.status_code == 422
