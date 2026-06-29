from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QStandardPaths


def resource_path(relative: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return base / relative


def app_data_dir() -> Path:
    raw = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.AppLocalDataLocation
    )
    path = Path(raw) if raw else Path.home() / ".WTKillOverlay"
    path.mkdir(parents=True, exist_ok=True)
    return path


def config_path() -> Path:
    return app_data_dir() / "config.json"


def logs_dir() -> Path:
    path = app_data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def resolve_data_path(stored_path: str) -> Path:
    path = Path(stored_path)
    if path.is_absolute():
        return path
    return app_data_dir() / path


def relative_to_data(path: Path) -> str:
    try:
        return path.resolve().relative_to(app_data_dir().resolve()).as_posix()
    except ValueError:
        return str(path.resolve())
