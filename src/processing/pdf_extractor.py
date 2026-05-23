"""
Extracción de texto de PDFs del CFP.

Estrategia en cascada:
  1. pdfplumber  → texto directo (mayoría de PDFs)
  2. PyMuPDF     → fallback para PDFs con fuentes embebidas complejas
  3. Tesseract OCR → fallback para PDFs escaneados (imágenes)
"""
import io
from pathlib import Path
from typing import Optional

from loguru import logger


MIN_TEXT_LENGTH = 100   # Umbral para considerar que la extracción fue exitosa


def extract_with_pdfplumber(pdf_path: Path) -> Optional[str]:
    try:
        import pdfplumber
        with pdfplumber.open(pdf_path) as pdf:
            pages_text = []
            for page in pdf.pages:
                text = page.extract_text(x_tolerance=3, y_tolerance=3)
                if text:
                    pages_text.append(text)
            return "\n\n".join(pages_text) if pages_text else None
    except Exception as exc:
        logger.debug(f"pdfplumber falló en {pdf_path.name}: {exc}")
        return None


def extract_with_pymupdf(pdf_path: Path) -> Optional[str]:
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(str(pdf_path))
        pages_text = []
        for page in doc:
            text = page.get_text("text")
            if text.strip():
                pages_text.append(text)
        doc.close()
        return "\n\n".join(pages_text) if pages_text else None
    except Exception as exc:
        logger.debug(f"PyMuPDF falló en {pdf_path.name}: {exc}")
        return None


def extract_with_ocr(pdf_path: Path, lang: str = "spa") -> Optional[str]:
    """OCR usando Tesseract vía PyMuPDF para renderizar páginas como imágenes."""
    try:
        import fitz
        import pytesseract
        from PIL import Image

        doc = fitz.open(str(pdf_path))
        pages_text = []

        for page in doc:
            # Renderizar a 300 DPI para mejor precisión OCR
            mat = fitz.Matrix(300 / 72, 300 / 72)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            text = pytesseract.image_to_string(img, lang=lang, config="--psm 1")
            if text.strip():
                pages_text.append(text)

        doc.close()
        return "\n\n".join(pages_text) if pages_text else None

    except ImportError:
        logger.warning("pytesseract o fitz no disponible; OCR omitido")
        return None
    except Exception as exc:
        logger.error(f"OCR falló en {pdf_path.name}: {exc}")
        return None


def extract_text(pdf_path: Path, ocr_lang: str = "spa") -> dict:
    """
    Extrae texto de un PDF usando la estrategia en cascada.

    Retorna dict con:
        text        : texto extraído
        method      : 'pdfplumber' | 'pymupdf' | 'ocr' | 'failed'
        page_count  : número de páginas
        char_count  : caracteres extraídos
    """
    pdf_path = Path(pdf_path)
    result = {
        "path": str(pdf_path),
        "text": "",
        "method": "failed",
        "page_count": 0,
        "char_count": 0,
    }

    # Intentar obtener número de páginas
    try:
        import fitz
        doc = fitz.open(str(pdf_path))
        result["page_count"] = doc.page_count
        doc.close()
    except Exception:
        pass

    # Cascada de extracción
    for method_name, method_fn in [
        ("pdfplumber", lambda: extract_with_pdfplumber(pdf_path)),
        ("pymupdf", lambda: extract_with_pymupdf(pdf_path)),
        ("ocr", lambda: extract_with_ocr(pdf_path, ocr_lang)),
    ]:
        text = method_fn()
        if text and len(text.strip()) >= MIN_TEXT_LENGTH:
            result["text"] = _clean_text(text)
            result["method"] = method_name
            result["char_count"] = len(result["text"])
            logger.debug(
                f"  {pdf_path.name}: {result['char_count']} chars via {method_name}"
            )
            return result

    logger.warning(f"  No se pudo extraer texto de {pdf_path.name}")
    return result


def _clean_text(text: str) -> str:
    """Limpieza básica del texto extraído."""
    import re
    # Normalizar saltos de línea
    text = re.sub(r"\r\n|\r", "\n", text)
    # Eliminar caracteres de control (excepto newlines y tabs)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    # Colapsar espacios múltiples dentro de líneas
    text = re.sub(r"[ \t]{2,}", " ", text)
    # Eliminar líneas vacías excesivas (más de 2 consecutivas)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def batch_extract(
    pdf_dir: Path,
    output_dir: Path,
    ocr_lang: str = "spa",
    overwrite: bool = False,
) -> dict[str, int]:
    """Extrae texto de todos los PDFs en pdf_dir y guarda en output_dir."""
    pdf_dir = Path(pdf_dir)
    output_dir = Path(output_dir)
    stats = {"ok": 0, "ocr": 0, "failed": 0, "skipped": 0}

    pdfs = sorted(pdf_dir.rglob("*.pdf"))
    logger.info(f"Procesando {len(pdfs)} PDFs desde {pdf_dir}")

    for pdf_path in pdfs:
        # Preservar estructura de directorios
        rel = pdf_path.relative_to(pdf_dir)
        out_path = output_dir / rel.with_suffix(".txt")

        if out_path.exists() and not overwrite:
            stats["skipped"] += 1
            continue

        out_path.parent.mkdir(parents=True, exist_ok=True)
        result = extract_text(pdf_path, ocr_lang)

        if result["text"]:
            out_path.write_text(result["text"], encoding="utf-8")
            if result["method"] == "ocr":
                stats["ocr"] += 1
            else:
                stats["ok"] += 1
        else:
            stats["failed"] += 1

    logger.info(
        f"Extracción completada: {stats['ok']} directos, "
        f"{stats['ocr']} OCR, {stats['failed']} fallidos, "
        f"{stats['skipped']} omitidos"
    )
    return stats
