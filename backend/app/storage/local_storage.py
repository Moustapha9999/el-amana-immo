import uuid
from pathlib import Path

from fastapi import UploadFile

from app.core.config import get_settings


class LocalStorageService:
    def __init__(self) -> None:
        settings = get_settings()
        self.root = Path(settings.upload_dir)
        self.root.mkdir(parents=True, exist_ok=True)

    async def save(self, file: UploadFile, subdir: str = "immobilisations") -> tuple[str, int]:
        target_dir = self.root / subdir
        target_dir.mkdir(parents=True, exist_ok=True)
        suffix = Path(file.filename or "file").suffix
        stored_name = f"{uuid.uuid4()}{suffix}"
        path = target_dir / stored_name
        content = await file.read()
        path.write_bytes(content)
        relative = str(path.relative_to(self.root)).replace("\\", "/")
        return relative, len(content)

    def absolute_path(self, relative_path: str) -> Path:
        return self.root / relative_path
