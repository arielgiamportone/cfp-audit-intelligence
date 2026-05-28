"""
Tests del módulo de gestión del catálogo SQLite.

Verifica el ciclo de vida completo: upsert, marcado de estados,
consultas de pendientes y estadísticas.
"""
import sqlite3
import tempfile

import pytest

from src.acquisition.catalog_manager import CatalogManager


@pytest.fixture
def catalog(tmp_db):
    """CatalogManager inicializado en DB temporal."""
    return CatalogManager(tmp_db)


@pytest.fixture
def sample_meta():
    """Metadatos de acta de ejemplo (formato dict que acepta upsert_acta)."""
    return {
        "year": 2025,
        "nombre": "ACTA CFP N° 34/2025",
        "url": "https://cfp.gob.ar/actas/acta_34_2025.pdf",
        "filename": "acta_34_2025.pdf",
        "is_anexo": False,
    }


# ── Inicialización ─────────────────────────────────────────────────────────────

class TestInit:
    def test_crea_db(self, tmp_db):
        CatalogManager(tmp_db)
        assert tmp_db.exists()

    def test_crea_tabla_actas(self, catalog, tmp_db):
        with sqlite3.connect(tmp_db) as conn:
            tables = [
                r[0] for r in
                conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            ]
        assert "actas" in tables


# ── upsert_acta ───────────────────────────────────────────────────────────────

class TestUpsertActa:
    def test_inserta_nueva(self, catalog, sample_meta):
        acta_id = catalog.upsert_acta(sample_meta)
        assert acta_id is not None
        assert isinstance(acta_id, int)

    def test_idempotente_mismo_url(self, catalog, sample_meta):
        id1 = catalog.upsert_acta(sample_meta)
        id2 = catalog.upsert_acta(dict(sample_meta))
        assert id1 == id2

    def test_diferentes_urls_diferentes_ids(self, catalog, sample_meta):
        id1 = catalog.upsert_acta(sample_meta)
        meta2 = {
            **sample_meta,
            "url": "https://cfp.gob.ar/otra.pdf",
            "filename": "otra.pdf",
        }
        id2 = catalog.upsert_acta(meta2)
        assert id1 != id2

    def test_inserta_varios(self, catalog):
        for i in range(5):
            catalog.upsert_acta({
                "year": 2020 + i,
                "nombre": f"ACTA CFP N° {i}/202{i}",
                "url": f"https://cfp.gob.ar/acta_{i}.pdf",
                "filename": f"acta_{i}.pdf",
                "is_anexo": False,
            })
        stats = catalog.stats()
        assert stats["total"] == 5


# ── mark_downloaded ───────────────────────────────────────────────────────────

class TestMarkDownloaded:
    def test_marca_descargado_por_url(self, catalog, sample_meta, tmp_path):
        catalog.upsert_acta(sample_meta)
        # mark_downloaded toma url y path de archivo real
        fake_pdf = tmp_path / "acta.pdf"
        fake_pdf.write_bytes(b"%PDF fake content")
        catalog.mark_downloaded(sample_meta["url"], fake_pdf)
        # Verificar que ya no está en pendientes de descarga
        pending = catalog.get_pending("download")
        assert all(
            row["url"] != sample_meta["url"] for row in pending
        )

    def test_registra_local_path(self, catalog, sample_meta, tmp_path, tmp_db):
        catalog.upsert_acta(sample_meta)
        fake_pdf = tmp_path / "acta.pdf"
        fake_pdf.write_bytes(b"%PDF-1.4 test")
        catalog.mark_downloaded(sample_meta["url"], fake_pdf)
        with sqlite3.connect(tmp_db) as conn:
            row = conn.execute(
                "SELECT local_path, download_status FROM actas WHERE url=?",
                (sample_meta["url"],),
            ).fetchone()
        assert row[1] == "ok"
        assert str(fake_pdf) in row[0]


# ── mark_processed ────────────────────────────────────────────────────────────

class TestMarkProcessed:
    def test_marca_procesado(self, catalog, sample_meta, tmp_path, tmp_db):
        acta_id = catalog.upsert_acta(sample_meta)
        fake_pdf = tmp_path / "acta.pdf"
        fake_pdf.write_bytes(b"%PDF fake")
        catalog.mark_downloaded(sample_meta["url"], fake_pdf)
        text_path = tmp_path / "acta.txt"
        text_path.write_text("texto extraído")
        catalog.mark_processed(acta_id, text_path)
        with sqlite3.connect(tmp_db) as conn:
            row = conn.execute(
                "SELECT text_extracted, text_path FROM actas WHERE id=?",
                (acta_id,),
            ).fetchone()
        assert row[0] == 1
        assert str(text_path) in row[1]


# ── get_pending ───────────────────────────────────────────────────────────────

class TestGetPending:
    def test_pendientes_descarga(self, catalog, sample_meta):
        catalog.upsert_acta(sample_meta)
        pending = catalog.get_pending("download")
        assert len(pending) == 1

    def test_sin_pendientes_tras_descarga(self, catalog, sample_meta, tmp_path):
        catalog.upsert_acta(sample_meta)
        fake_pdf = tmp_path / "acta.pdf"
        fake_pdf.write_bytes(b"%PDF fake")
        catalog.mark_downloaded(sample_meta["url"], fake_pdf)
        pending = catalog.get_pending("download")
        assert len(pending) == 0

    def test_stage_invalido_retorna_lista(self, catalog):
        # Con stage inválido, usa filtro por defecto (download_status='pending')
        result = catalog.get_pending("nonexistent_stage")
        assert isinstance(result, list)


# ── stats ─────────────────────────────────────────────────────────────────────

class TestStats:
    def test_stats_vacio(self, catalog):
        stats = catalog.stats()
        assert stats["total"] == 0

    def test_stats_total(self, catalog):
        for i in range(3):
            catalog.upsert_acta({
                "year": 2025,
                "nombre": f"Acta {i}",
                "url": f"https://cfp.gob.ar/{i}.pdf",
                "filename": f"{i}.pdf",
                "is_anexo": False,
            })
        stats = catalog.stats()
        assert stats["total"] == 3

    def test_stats_by_year(self, catalog):
        catalog.upsert_acta({
            "year": 2023,
            "nombre": "Acta 2023",
            "url": "https://cfp.gob.ar/2023.pdf",
            "filename": "2023.pdf",
            "is_anexo": False,
        })
        catalog.upsert_acta({
            "year": 2024,
            "nombre": "Acta 2024",
            "url": "https://cfp.gob.ar/2024.pdf",
            "filename": "2024.pdf",
            "is_anexo": False,
        })
        stats = catalog.stats()
        assert 2023 in stats["by_year"]
        assert 2024 in stats["by_year"]

    def test_stats_descargados(self, catalog, sample_meta, tmp_path):
        catalog.upsert_acta(sample_meta)
        fake_pdf = tmp_path / "acta.pdf"
        fake_pdf.write_bytes(b"%PDF fake")
        catalog.mark_downloaded(sample_meta["url"], fake_pdf)
        stats = catalog.stats()
        assert stats["downloaded"] == 1
