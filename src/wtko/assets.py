from __future__ import annotations

import hashlib
from pathlib import Path
import re
import shutil

from .paths import app_data_dir, relative_to_data


MEDIA_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".bmp", ".webp", ".gif",
    ".mp4", ".webm", ".mov", ".mkv", ".avi",
}

AUDIO_EXTENSIONS = {
    ".wav", ".mp3", ".ogg", ".flac", ".m4a",
}


class AssetService:
    MAX_FILE_SIZE = 100 * 1024 * 1024

    def __init__(self) -> None:
        self.destination = app_data_dir() / "assets" / "user"
        self.destination.mkdir(parents=True, exist_ok=True)

    def import_media(self, source: Path) -> str:
        return self._import(source, MEDIA_EXTENSIONS)

    def import_audio(self, source: Path) -> str:
        return self._import(source, AUDIO_EXTENSIONS)

    def _import(self, source: Path, allowed: set[str]) -> str:
        source = source.expanduser().resolve()

        if not source.is_file():
            raise FileNotFoundError(f"找不到文件：{source}")

        suffix = source.suffix.lower()
        if suffix not in allowed:
            raise ValueError(f"不支持的文件格式：{suffix}")

        size = source.stat().st_size
        if size <= 0:
            raise ValueError("文件为空。")
        if size > self.MAX_FILE_SIZE:
            raise ValueError("单个素材不能超过 100 MB。")

        digest = self._sha256(source)[:12]
        safe_stem = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff_-]+", "_", source.stem)
        safe_stem = safe_stem[:60] or "asset"

        target = self.destination / f"{digest}_{safe_stem}{suffix}"
        if not target.exists():
            shutil.copy2(source, target)

        return relative_to_data(target)

    @staticmethod
    def _sha256(path: Path) -> str:
        hasher = hashlib.sha256()
        with path.open("rb") as file:
            while block := file.read(1024 * 1024):
                hasher.update(block)
        return hasher.hexdigest()
