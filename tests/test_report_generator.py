"""
Tests del generador de reportes PDF ejecutivos.
"""
import sqlite3
import pytest
from pathlib import Path

pytest.importorskip("reportlab", reason="reportlab no instalado")


@pytest.fixture(scope="module")
def report_db(tmp_path_factory):
    """BD SQLite temporal con datos suficientes para generar el reporte."""
    db = tmp_path_factory.mktemp("report_db") / "catalog.db"
    conn = sqlite3.connect(db)
    conn.executescript("""
        CREATE TABLE actas (
            id INTEGER PRIMARY KEY, year INTEGER, nombre TEXT,
            download_status TEXT DEFAULT 'pending',
            text_extracted INTEGER DEFAULT 0
        );
        CREATE TABLE resoluciones (
            id INTEGER PRIMARY KEY, acta_id INTEGER, numero TEXT, tipo TEXT
        );
        CREATE TABLE entidades (
            id INTEGER PRIMARY KEY, tipo TEXT, nombre TEXT, nombre_norm TEXT
        );
        CREATE TABLE menciones (
            id INTEGER PRIMARY KEY, resolucion_id INTEGER,
            entidad_id INTEGER, contexto TEXT
        );
        CREATE TABLE alertas_historial (
            id INTEGER PRIMARY KEY, tipo TEXT, especie TEXT, especie_code TEXT,
            zona TEXT, year INTEGER, valor_detectado REAL, umbral REAL,
            mensaje TEXT, severidad TEXT, resuelta INTEGER DEFAULT 0
        );
        CREATE TABLE comparacion_cfp_inidep (
            id INTEGER PRIMARY KEY, especie TEXT, especie_code TEXT,
            zona TEXT, year INTEGER, cba_inidep_tn REAL, cmp_cfp_tn REAL,
            diferencia_tn REAL, ratio_sobreasignacion REAL, nivel_alerta TEXT,
            descripcion_alerta TEXT, numero_ito TEXT, acta_cfp TEXT, created_at TEXT
        );
    """)
    conn.execute("INSERT INTO actas VALUES (1, 2023, 'Acta 180', 'downloaded', 1)")
    conn.execute("INSERT INTO actas VALUES (2, 2022, 'Acta 170', 'downloaded', 1)")
    conn.execute("INSERT INTO resoluciones VALUES (1, 1, '5', 'cuota_captura')")
    conn.execute("INSERT INTO resoluciones VALUES (2, 2, '3', 'cuota_captura')")
    conn.execute("INSERT INTO entidades VALUES (1, 'especie', 'merluza hubbsi', 'merluza hubbsi')")
    conn.execute("INSERT INTO entidades VALUES (2, 'empresa', 'ARGENOVA S.A.', 'argenova')")
    conn.execute("INSERT INTO entidades VALUES (3, 'empresa', 'PESQUERA DEL SUR', 'pesquera del sur')")
    conn.execute("INSERT INTO menciones VALUES (1, 1, 1, 'cuota merluza')")
    conn.execute("INSERT INTO menciones VALUES (2, 1, 2, 'ARGENOVA aprobada')")
    conn.execute("INSERT INTO menciones VALUES (3, 2, 3, 'Pesquera del Sur')")
    conn.execute("""INSERT INTO alertas_historial
        VALUES (1, 'cba_exceso', 'merluza hubbsi', 'merluza_hubbsi',
                'Sur 41S', 2023, 115.0, 100.0,
                'merluza hubbsi 2023: CMP excede CBA', 'critical', 0)""")
    conn.execute("""INSERT INTO alertas_historial
        VALUES (2, 'cba_exceso', 'langostino', 'langostino',
                'Patagónica', 2022, 108.0, 100.0,
                'langostino 2022: advertencia', 'warning', 0)""")
    conn.execute("""INSERT INTO comparacion_cfp_inidep
        VALUES (1, 'merluza hubbsi', 'merluza_hubbsi', 'Sur 41S', 2023,
                300000, 345000, 45000, 1.15, 'amarillo',
                NULL, 'ITO-2023-01', 'Acta 180', '2023-01-01')""")
    conn.execute("""INSERT INTO comparacion_cfp_inidep
        VALUES (2, 'langostino', 'langostino', 'Patagónica', 2022,
                100000, 135000, 35000, 1.35, 'critico',
                NULL, 'ITO-2022-05', 'Acta 170', '2022-01-01')""")
    conn.commit()
    conn.close()
    return db


@pytest.fixture(scope="module")
def generator(report_db):
    from src.analysis.report_generator import CFPReportGenerator
    return CFPReportGenerator(db_path=report_db)


# ── Tests de generación ───────────────────────────────────────────────────────

class TestGenerate:
    def test_generate_returns_bytes(self, generator):
        pdf = generator.generate()
        assert isinstance(pdf, bytes)
        assert len(pdf) > 0

    def test_generates_valid_pdf(self, generator):
        pdf = generator.generate()
        assert pdf[:4] == b"%PDF", "No empieza con header PDF"

    def test_generate_with_custom_title(self, generator):
        pdf = generator.generate(title="Informe Test")
        assert isinstance(pdf, bytes)
        assert len(pdf) > 1000

    def test_generate_saves_to_disk(self, generator, tmp_path):
        output = tmp_path / "test_report.pdf"
        pdf = generator.generate(output_path=output)
        assert output.exists()
        assert output.stat().st_size > 0
        assert output.read_bytes() == pdf

    def test_generate_returns_same_as_file(self, generator, tmp_path):
        output = tmp_path / "compare.pdf"
        pdf_bytes = generator.generate(output_path=output)
        assert output.read_bytes() == pdf_bytes

    def test_pdf_size_reasonable(self, generator):
        pdf = generator.generate()
        assert len(pdf) > 3_000, "PDF demasiado pequeño"
        assert len(pdf) < 5_000_000, "PDF demasiado grande"


class TestGetStats:
    def test_returns_dict(self, generator):
        stats = generator._get_stats()
        assert isinstance(stats, dict)

    def test_expected_keys(self, generator):
        stats = generator._get_stats()
        expected_keys = [
            "total_actas", "actas_descargadas", "actas_procesadas",
            "total_resoluciones", "total_entidades", "total_menciones",
            "n_empresas", "n_especies",
        ]
        for k in expected_keys:
            assert k in stats, f"Falta clave: {k}"

    def test_counts_correct(self, generator):
        stats = generator._get_stats()
        assert stats["total_actas"] == 2
        assert stats["total_resoluciones"] == 2
        assert stats["n_empresas"] == 2
        assert stats["n_especies"] == 1

    def test_año_range(self, generator):
        stats = generator._get_stats()
        assert stats["años_min"] == 2022
        assert stats["años_max"] == 2023


class TestGetAlertas:
    def test_returns_list(self, generator):
        alertas = generator._get_alertas_criticas()
        assert isinstance(alertas, list)

    def test_has_expected_alerts(self, generator):
        alertas = generator._get_alertas_criticas()
        assert len(alertas) == 2

    def test_alertas_have_required_fields(self, generator):
        alertas = generator._get_alertas_criticas()
        for a in alertas:
            assert "tipo" in a.keys()
            assert "severidad" in a.keys()
            assert "mensaje" in a.keys()

    def test_criticas_first(self, generator):
        alertas = generator._get_alertas_criticas()
        severidades = [a["severidad"] for a in alertas]
        if "critical" in severidades and "warning" in severidades:
            critical_idx = severidades.index("critical")
            warning_idx = severidades.index("warning")
            assert critical_idx < warning_idx, "Críticas deben aparecer antes"


class TestGetComparaciones:
    def test_returns_list(self, generator):
        comps = generator._get_comparaciones()
        assert isinstance(comps, list)

    def test_has_data(self, generator):
        comps = generator._get_comparaciones()
        assert len(comps) == 2

    def test_sorted_by_ratio(self, generator):
        comps = generator._get_comparaciones()
        ratios = [c["ratio_sobreasignacion"] for c in comps]
        assert ratios == sorted(ratios, reverse=True)

    def test_required_columns(self, generator):
        comps = generator._get_comparaciones()
        for c in comps:
            for col in ["especie", "zona", "year", "cba_inidep_tn", "cmp_cfp_tn"]:
                assert col in c.keys()


class TestGetTopActores:
    def test_top_empresas(self, generator):
        empresas = generator._get_top_empresas()
        assert isinstance(empresas, list)
        assert len(empresas) > 0
        assert "nombre" in empresas[0].keys()
        assert "n_menciones" in empresas[0].keys()

    def test_top_especies(self, generator):
        especies = generator._get_top_especies()
        assert isinstance(especies, list)
        assert len(especies) > 0


# ── Tests con DB vacía ────────────────────────────────────────────────────────

class TestNoDB:
    def test_no_db_generates_pdf(self, tmp_path):
        from src.analysis.report_generator import CFPReportGenerator
        gen = CFPReportGenerator(db_path=tmp_path / "nonexistent.db")
        pdf = gen.generate()
        assert isinstance(pdf, bytes)
        assert pdf[:4] == b"%PDF"

    def test_no_db_stats_all_zero(self, tmp_path):
        from src.analysis.report_generator import CFPReportGenerator
        gen = CFPReportGenerator(db_path=tmp_path / "nonexistent.db")
        stats = gen._get_stats()
        assert stats["total_actas"] == 0
        assert stats["total_resoluciones"] == 0

    def test_no_db_alertas_empty(self, tmp_path):
        from src.analysis.report_generator import CFPReportGenerator
        gen = CFPReportGenerator(db_path=tmp_path / "nonexistent.db")
        assert gen._get_alertas_criticas() == []


# ── Test función de conveniencia ──────────────────────────────────────────────

class TestGenerateReport:
    def test_convenience_function(self, report_db):
        from src.analysis.report_generator import generate_report
        pdf = generate_report(db_path=report_db)
        assert isinstance(pdf, bytes)
        assert pdf[:4] == b"%PDF"

    def test_convenience_with_output(self, report_db, tmp_path):
        from src.analysis.report_generator import generate_report
        output = tmp_path / "convenience_test.pdf"
        pdf = generate_report(db_path=report_db, output_path=output)
        assert output.exists()
        assert output.read_bytes() == pdf
