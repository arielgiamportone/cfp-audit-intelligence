"""
Tests del extractor de PDF (`pdf_extractor`).

No requiere pdfplumber/PyMuPDF/Tesseract: se mockean los extractores para verificar
la lógica de la **cascada** (pdfplumber → PyMuPDF → OCR), el umbral mínimo de texto,
la limpieza de texto y el guardado por lotes preservando la estructura de directorios.
"""

from pathlib import Path

from src.processing import pdf_extractor as pe
from src.processing.pdf_extractor import _clean_text, batch_extract, extract_text


class TestCleanText:
    def test_normaliza_crlf(self):
        assert "\r" not in _clean_text("linea1\r\nlinea2\rlinea3")

    def test_elimina_caracteres_de_control(self):
        assert "\x00" not in _clean_text("a\x00b\x07c")

    def test_colapsa_espacios(self):
        assert _clean_text("a      b") == "a b"

    def test_colapsa_lineas_vacias(self):
        assert "\n\n\n" not in _clean_text("a\n\n\n\n\nb")


class TestCascada:
    def test_usa_pdfplumber_si_texto_suficiente(self, monkeypatch):
        monkeypatch.setattr(pe, "extract_with_pdfplumber", lambda p: "x" * 200)
        monkeypatch.setattr(pe, "extract_with_pymupdf", lambda p: None)
        monkeypatch.setattr(pe, "extract_with_ocr", lambda p, lang="spa": None)
        r = extract_text(Path("dummy.pdf"))
        assert r["method"] == "pdfplumber"
        assert r["char_count"] >= 200

    def test_fallback_a_pymupdf_si_pdfplumber_corto(self, monkeypatch):
        monkeypatch.setattr(pe, "extract_with_pdfplumber", lambda p: "corto")  # < MIN_TEXT_LENGTH
        monkeypatch.setattr(pe, "extract_with_pymupdf", lambda p: "y" * 150)
        monkeypatch.setattr(pe, "extract_with_ocr", lambda p, lang="spa": None)
        r = extract_text(Path("dummy.pdf"))
        assert r["method"] == "pymupdf"

    def test_fallback_a_ocr(self, monkeypatch):
        monkeypatch.setattr(pe, "extract_with_pdfplumber", lambda p: None)
        monkeypatch.setattr(pe, "extract_with_pymupdf", lambda p: None)
        monkeypatch.setattr(pe, "extract_with_ocr", lambda p, lang="spa": "z" * 300)
        r = extract_text(Path("dummy.pdf"))
        assert r["method"] == "ocr"

    def test_failed_si_todo_none(self, monkeypatch):
        monkeypatch.setattr(pe, "extract_with_pdfplumber", lambda p: None)
        monkeypatch.setattr(pe, "extract_with_pymupdf", lambda p: None)
        monkeypatch.setattr(pe, "extract_with_ocr", lambda p, lang="spa": None)
        r = extract_text(Path("dummy.pdf"))
        assert r["method"] == "failed"
        assert r["text"] == ""


class TestBatchExtract:
    def test_escribe_txt_y_preserva_estructura(self, tmp_path, monkeypatch):
        pdf_dir = tmp_path / "raw"
        (pdf_dir / "2024").mkdir(parents=True)
        (pdf_dir / "2024" / "acta.pdf").write_bytes(b"%PDF-1.4 fake")
        out_dir = tmp_path / "text"

        monkeypatch.setattr(
            pe, "extract_text",
            lambda p, lang="spa": {"text": "contenido", "method": "pdfplumber",
                                   "char_count": 9, "page_count": 1, "path": str(p)},
        )
        stats = batch_extract(pdf_dir, out_dir)

        assert stats["ok"] == 1
        assert (out_dir / "2024" / "acta.txt").read_text(encoding="utf-8") == "contenido"

    def test_omite_si_ya_existe(self, tmp_path, monkeypatch):
        pdf_dir = tmp_path / "raw"
        pdf_dir.mkdir()
        (pdf_dir / "acta.pdf").write_bytes(b"x")
        out_dir = tmp_path / "text"
        out_dir.mkdir()
        (out_dir / "acta.txt").write_text("ya existe", encoding="utf-8")

        monkeypatch.setattr(
            pe, "extract_text",
            lambda p, lang="spa": {"text": "nuevo", "method": "pdfplumber",
                                   "char_count": 5, "page_count": 1, "path": str(p)},
        )
        stats = batch_extract(pdf_dir, out_dir)

        assert stats["skipped"] == 1
        assert (out_dir / "acta.txt").read_text(encoding="utf-8") == "ya existe"
