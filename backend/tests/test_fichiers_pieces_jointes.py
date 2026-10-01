import io
import zipfile
from pathlib import Path

import pytest

from app.core.exceptions import ValidationError
from app.core.fichiers import valider_piece_jointe
from app.services.ocr_extract import docx_paragraphs, extract_text_from_file


def _zip(fichiers: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for nom, data in fichiers.items():
            z.writestr(nom, data)
    return buf.getvalue()


_DOCX_XML = (
    b'<?xml version="1.0"?>'
    b'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
    b"<w:p><w:r><w:t>Facture N FAC-001</w:t></w:r></w:p>"
    b"<w:p><w:r><w:t>Total TTC 4 500,00</w:t></w:r></w:p>"
    b"</w:body></w:document>"
)
DOCX = _zip({"[Content_Types].xml": b"<Types/>", "word/document.xml": _DOCX_XML})


@pytest.mark.parametrize(
    ("nom", "contenu", "mime"),
    [
        ("facture.pdf", b"%PDF-1.7\n...", "application/pdf"),
        ("facture.docx", DOCX, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        ("etat.XLSX", _zip({"xl/workbook.xml": b"<x/>"}), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        ("ancien.doc", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\0" * 32, "application/msword"),
        ("scan.jpg", b"\xff\xd8\xff\xe0" + b"\0" * 32, "image/jpeg"),
    ],
)
def test_formats_acceptes(nom, contenu, mime):
    assert valider_piece_jointe(nom, contenu) == mime


@pytest.mark.parametrize(
    ("nom", "contenu"),
    [
        ("virus.pdf", b"MZ\x90\x00 executable"),
        ("macro.docm", DOCX),
        ("macro.xlsx", _zip({"xl/workbook.xml": b"<x/>", "xl/vbaProject.bin": b"\0"})),
        ("faux.docx", _zip({"xl/workbook.xml": b"<x/>"})),
        ("donnees.csv", b"a;b\n1;2"),
        ("archive.zip", _zip({"a.txt": b"x"})),
        ("vide.pdf", b""),
        ("sans_extension", b"%PDF-1.4"),
    ],
)
def test_formats_refuses(nom, contenu):
    with pytest.raises(ValidationError):
        valider_piece_jointe(nom, contenu)


def test_texte_docx_extrait(tmp_path: Path):
    f = tmp_path / "facture.docx"
    f.write_bytes(DOCX)
    assert docx_paragraphs(f) == ["Facture N FAC-001", "Total TTC 4 500,00"]
    assert "FAC-001" in extract_text_from_file(f)
