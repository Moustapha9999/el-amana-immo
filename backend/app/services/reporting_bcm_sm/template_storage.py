"""Stockage persistant du canevas officiel — chemins calculés, jamais fournis par l'API."""

from __future__ import annotations

import hashlib
import shutil
import uuid
from pathlib import Path

from app.core.exceptions import AppError
from app.services.platform_backup_engine import upload_root

OFFICIAL_SHA256 = "54e3b687434f4901889c1164b8d6d7fbc3bd225a117b1b36016c84e8fc852658"
OFFICIAL_FILENAME = "BEA-SM-10-2026.xlsx"
TEMPLATE_CODE = "BEA-SM"


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _raise(code: str, message: str, status_code: int) -> None:
    raise AppError(message, status_code=status_code, code=code)


def resolved_upload_root() -> Path:
    root = upload_root().resolve()
    if not root.exists():
        try:
            root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            _raise("STORAGE_UNAVAILABLE", f"upload_root inaccessible: {exc}", 503)
    if not root.is_dir():
        _raise("STORAGE_UNAVAILABLE", "upload_root n'est pas un répertoire", 503)
    return root


def template_dest_dir(template_id: uuid.UUID) -> Path:
    if not isinstance(template_id, uuid.UUID):
        try:
            template_id = uuid.UUID(str(template_id))
        except (ValueError, TypeError):
            _raise("TEMPLATE_PATH_UNSAFE", "template_id n'est pas un UUID", 500)
    if ".." in str(template_id):
        _raise("TEMPLATE_PATH_UNSAFE", "traversée de répertoire refusée", 500)
    root = resolved_upload_root()
    dest = (root / "reporting-bcm-sm" / "templates" / str(template_id)).resolve()
    try:
        dest.relative_to(root)
    except ValueError:
        _raise("TEMPLATE_PATH_UNSAFE", "chemin hors upload_root", 500)
    return dest


def template_dest_file(template_id: uuid.UUID, filename: str = OFFICIAL_FILENAME) -> Path:
    if ".." in filename or "/" in filename or "\\" in filename:
        _raise("TEMPLATE_PATH_UNSAFE", "nom de fichier refusé", 500)
    return template_dest_dir(template_id) / filename


def copy_official_template(
    source: Path,
    template_id: uuid.UUID,
    *,
    expected_sha256: str | None = OFFICIAL_SHA256,
) -> dict:
    """Copie immuable. N'écrase jamais une copie existante d'un autre SHA."""
    src = source.resolve()
    if not src.is_file():
        _raise("TEMPLATE_NOT_FOUND", f"canevas source introuvable: {source}", 404)
    if ".." in str(source):
        _raise("TEMPLATE_PATH_UNSAFE", "traversée refusée dans le chemin source", 500)

    sha_src = file_sha256(src)
    if expected_sha256 and sha_src.lower() != expected_sha256.lower():
        _raise(
            "TEMPLATE_SHA_MISMATCH",
            f"SHA source {sha_src} ≠ attendu {expected_sha256}",
            409,
        )

    dest = template_dest_file(template_id, src.name)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        sha_dest = file_sha256(dest)
        if sha_dest.lower() != sha_src.lower():
            _raise("TEMPLATE_SHA_MISMATCH", "copie existante d'un SHA différent — écrasement interdit", 409)
        return {"stored_path": str(dest), "sha256": sha_dest, "copied": False}

    try:
        shutil.copy2(src, dest)
    except OSError as exc:
        _raise("STORAGE_UNAVAILABLE", f"copie impossible: {exc}", 503)

    sha_dest = file_sha256(dest)
    if sha_dest.lower() != sha_src.lower():
        dest.unlink(missing_ok=True)
        _raise("TEMPLATE_SHA_MISMATCH", "SHA après copie incohérent", 409)
    try:
        dest.chmod(0o444)
    except OSError:
        pass
    return {"stored_path": str(dest), "sha256": sha_dest, "copied": True}


def verify_stored_template(stored_path: str, expected_sha256: str) -> Path:
    path = Path(stored_path)
    if ".." in stored_path:
        _raise("TEMPLATE_PATH_UNSAFE", "traversée refusée", 500)
    root = resolved_upload_root()
    resolved = path.resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        _raise("TEMPLATE_PATH_UNSAFE", "stored_path hors upload_root", 500)
    if not resolved.is_file():
        _raise("TEMPLATE_NOT_FOUND", "copie template absente du disque", 404)
    sha = file_sha256(resolved)
    if sha.lower() != expected_sha256.lower():
        _raise("TEMPLATE_SHA_MISMATCH", "SHA fichier ≠ SHA colonne", 409)
    return resolved
