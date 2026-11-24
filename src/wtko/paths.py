from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

from PySide6.QtCore import QStandardPaths


def resource_path(relative: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return base / relative


def _qt_app_data_dir() -> Path:
    raw = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.AppLocalDataLocation
    )
    return Path(raw) if raw else Path.home() / ".WTKillOverlay"


def _local_sibling(path: Path) -> Path | None:
    """被系统重定向到 LocalLow 时，推出同一份数据在 Local 下的位置。

    低完整性进程（例如从带低完整性标记的可执行文件启动）会被 Windows
    把 AppData\\Local 换成 AppData\\LocalLow，于是程序看到一份空配置。
    """
    parts = list(path.parts)
    for index, part in enumerate(parts):
        if part.lower() == "locallow":
            parts[index] = "Local"
            return Path(*parts)
    return None


def _has_player_name(config_file: Path) -> bool:
    try:
        raw = json.loads(config_file.read_text(encoding="utf-8"))
        game = raw.get("game", {})
        return bool(str(game.get("player_name", "")).strip())
    except (OSError, ValueError, AttributeError):
        return False


def _adopt_local_data(target: Path) -> None:
    """当前目录还没有真实配置时，把 Local 下的配置和素材搬过来一次。"""
    sibling = _local_sibling(target)
    if sibling is None:
        return

    source_config = sibling / "config.json"
    target_config = target / "config.json"
    if not source_config.is_file() or not _has_player_name(source_config):
        return
    if target_config.is_file() and _has_player_name(target_config):
        return

    try:
        if target_config.is_file():
            shutil.copy2(target_config, target / "config.empty.json")
        shutil.copy2(source_config, target_config)
        source_assets = sibling / "assets"
        if source_assets.is_dir():
            shutil.copytree(source_assets, target / "assets", dirs_exist_ok=True)
    except OSError:
        pass


def app_data_dir() -> Path:
    path = _qt_app_data_dir()
    path.mkdir(parents=True, exist_ok=True)
    _adopt_local_data(path)
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
