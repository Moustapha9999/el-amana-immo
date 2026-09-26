"""Extraction texte — pdfplumber (PDF natif) + Tesseract (images / PDF scannés)."""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".tif", ".tiff", ".bmp"}
_MIN_NATIVE_CHARS = 40


def extract_text_from_file(path: Path, *, lang: str = "fra+eng") -> str:
    """Retourne le texte extrait. Lève RuntimeError si échec technique."""
    if not path.is_file():
        raise RuntimeError(f"Fichier introuvable: {path}")

    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _extract_pdf(path, lang=lang)
    if suffix in _IMAGE_SUFFIXES:
        return _ocr_image(path, lang=lang)
    if suffix in {".txt", ".csv"}:
        return path.read_text(encoding="utf-8", errors="ignore")
    # Office / zip : pas d'OCR — texte vide (statut done côté worker)
    logger.info("OCR non applicable pour suffixe %s (%s)", suffix, path.name)
    return ""


def _extract_pdf(path: Path, *, lang: str) -> str:
    native = _pdf_native_text(path)
    if len(native.strip()) >= _MIN_NATIVE_CHARS:
        return native.strip()
    # PDF scanné : OCR page par page si pdf2image/poppler disponibles
    ocr_pages = _pdf_ocr_pages(path, lang=lang)
    if ocr_pages.strip():
        return ocr_pages.strip()
    if native.strip():
        return native.strip()
    raise RuntimeError(
        "PDF sans texte extractible (natif insuffisant et OCR pages indisponible)"
    )


def _pdf_native_text(path: Path) -> str:
    try:
        import pdfplumber
    except ImportError as exc:
        raise RuntimeError("pdfplumber non installé") from exc

    parts: list[str] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            if text.strip():
                parts.append(text)
    return "\n\n".join(parts)


def _pdf_ocr_pages(path: Path, *, lang: str) -> str:
    try:
        from pdf2image import convert_from_path
    except ImportError:
        logger.warning("pdf2image absent — OCR PDF scanné indisponible")
        return ""

    try:
        images = convert_from_path(str(path), dpi=200)
    except Exception:
        logger.exception("Conversion PDF→images échouée pour %s", path)
        return ""

    parts: list[str] = []
    for img in images:
        try:
            parts.append(_ocr_pil(img, lang=lang))
        except Exception:
            logger.exception("OCR page PDF échouée")
    return "\n\n".join(p for p in parts if p.strip())


def _ocr_image(path: Path, *, lang: str) -> str:
    try:
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("Pillow non installé") from exc
    with Image.open(path) as img:
        return _ocr_pil(img, lang=lang)


def _ocr_pil(image, *, lang: str) -> str:
    try:
        import pytesseract
    except ImportError as exc:
        raise RuntimeError("pytesseract non installé") from exc
    try:
        text = pytesseract.image_to_string(image, lang=lang)
    except pytesseract.TesseractNotFoundError as exc:
        raise RuntimeError("Binaire tesseract introuvable sur le système") from exc
    except Exception as exc:
        # Fallback anglais seul si pack fra manquant
        try:
            text = pytesseract.image_to_string(image, lang="eng")
        except Exception as exc2:
            raise RuntimeError(f"Tesseract a échoué: {exc2}") from exc
    return (text or "").strip()
