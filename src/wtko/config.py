from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
import shutil

from .models import AppConfig, default_config
from .paths import app_data_dir, resource_path


class ConfigManager:
    def __init__(self, path: Path) -> None:
        self.path = path

    def ensure_default_assets(self) -> None:
        source = resource_path("resources/default_assets")
        destination = app_data_dir() / "assets" / "default"
        destination.mkdir(parents=True, exist_ok=True)

        if not source.exists():
            return

        for item in source.iterdir():
            target = destination / item.name
            if item.is_file() and not target.exists():
                shutil.copy2(item, target)

    def load(self) -> AppConfig:
        self.ensure_default_assets()

        if not self.path.exists():
            config = default_config()
            self.save(config)
            return config

        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("配置根节点必须是对象")
            return AppConfig.from_dict(raw)
        except Exception:
            backup = self.path.with_suffix(".broken.json")
            try:
                shutil.copy2(self.path, backup)
            except OSError:
                pass
            config = default_config()
            self.save(config)
            return config

    def save(self, config: AppConfig) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(
                asdict(config),
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        temporary.replace(self.path)
