"""Politique unique des pièces jointes BEA DIGITAL (GED, archives, pièces comptables…).

Formats bureautiques : PDF, Word, Excel. Les scans / photos restent acceptés
(factures papier numérisées). Le contenu réel est vérifié (signature du fichier),
l'extension seule ne suffit pas ; les documents à macros sont refusés.
"""

from __future__ import annotations

import io
import socket
import struct
import zipfile
from pathlib import Path

from app.core.exceptions import ValidationError

TAILLE_MAX = 25 * 1024 * 1024  # 25 Mo

TYPES_MIME: dict[str, str] = {
    ".pdf": "application/pdf",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
}
EXTENSIONS_AUTORISEES = frozenset(TYPES_MIME)

MESSAGE_FORMATS = "Formats acceptés : PDF, Word (.doc, .docx), Excel (.xls, .xlsx) et images scannées (.jpg, .png, .tif)."

_OLE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


def _signature_ok(ext: str, content: bytes) -> bool:
    tete = content[:16]
    if ext == ".pdf":
        return b"%PDF-" in content[:1024]
    if ext in (".doc", ".xls"):
        return tete.startswith(_OLE)
    if ext in (".docx", ".xlsx"):
        return tete.startswith(b"PK\x03\x04")
    if ext == ".png":
        return tete.startswith(b"\x89PNG\r\n\x1a\n")
    if ext in (".jpg", ".jpeg"):
        return tete.startswith(b"\xff\xd8\xff")
    if ext == ".gif":
        return tete.startswith((b"GIF87a", b"GIF89a"))
    if ext == ".webp":
        return tete[:4] == b"RIFF" and tete[8:12] == b"WEBP"
    if ext in (".tif", ".tiff"):
        return tete.startswith((b"II*\x00", b"MM\x00*"))
    return False


def _ooxml_ok(ext: str, content: bytes) -> bool:
    """docx → dossier word/, xlsx → dossier xl/, sans projet VBA (macros)."""
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as z:
            noms = z.namelist()
    except zipfile.BadZipFile:
        return False
    racine = "word/" if ext == ".docx" else "xl/"
    if not any(n.startswith(racine) for n in noms):
        return False
    return not any(n.lower().endswith("vbaproject.bin") for n in noms)


def _clamd_instream(host: str, port: int, content: bytes) -> str:
    with socket.create_connection((host, port), timeout=30) as sock:
        sock.sendall(b"zINSTREAM\0")
        for i in range(0, len(content), 64 * 1024):
            chunk = content[i : i + 64 * 1024]
            sock.sendall(struct.pack("!L", len(chunk)) + chunk)
        sock.sendall(struct.pack("!L", 0))
        reply = b""
        while not reply.endswith(b"\0"):
            data = sock.recv(4096)
            if not data:
                break
            reply += data
    return reply.rstrip(b"\0").decode("utf-8", "replace")


def analyser_antivirus(content: bytes) -> None:
    """Refuse le fichier si clamd (CLAMAV_HOST) détecte une menace ; fail-closed si configuré mais injoignable."""
    from app.core.config import get_settings

    s = get_settings()
    if not s.clamav_host:
        return
    try:
        reply = _clamd_instream(s.clamav_host, s.clamav_port, content)
    except OSError as exc:
        raise ValidationError("Analyse antivirale indisponible : dépôt refusé, réessayez plus tard.") from exc
    if reply.endswith("FOUND"):
        raise ValidationError("Fichier refusé : menace détectée par l'analyse antivirale.")
    if not reply.endswith("OK"):
        raise ValidationError("Analyse antivirale non concluante : dépôt refusé.")


def valider_piece_jointe(filename: str | None, content: bytes) -> str:
    """Valide nom + contenu ; renvoie le type MIME normalisé (ne jamais faire confiance au client)."""
    ext = Path(filename or "").suffix.lower()
    if ext not in EXTENSIONS_AUTORISEES:
        raise ValidationError(f"Type de fichier non autorisé ({ext or 'sans extension'}). {MESSAGE_FORMATS}")
    if not content:
        raise ValidationError("Fichier vide")
    if len(content) > TAILLE_MAX:
        raise ValidationError("Fichier trop volumineux (max 25 Mo)")
    if not _signature_ok(ext, content) or (ext in (".docx", ".xlsx") and not _ooxml_ok(ext, content)):
        raise ValidationError(
            f"Le contenu du fichier ne correspond pas à son extension {ext} (fichier corrompu, renommé ou avec macros)."
        )
    analyser_antivirus(content)
    return TYPES_MIME[ext]
