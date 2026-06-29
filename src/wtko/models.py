from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


DEFAULT_KILL_KEYWORDS = [
    "摧毁",
    "击毁",
    "消灭",
    "击杀",
    "destroyed",
    "killed",
    "set afire",
    "уничтожил",
    "уничтожила",
]


@dataclass
class GameConfig:
    player_name: str = ""
    base_url: str = "http://127.0.0.1:8111"
    poll_interval_ms: int = 180
    kill_keywords: list[str] = field(
        default_factory=lambda: list(DEFAULT_KILL_KEYWORDS)
    )


@dataclass
class ComboConfig:
    timeout_ms: int = 5000
    use_highest_for_overflow: bool = True


@dataclass
class OverlayConfig:
    screen_index: int = 0
    x_ratio: float = 0.5
    y_ratio: float = 0.28
    base_size_px: int = 520
    global_scale: float = 1.0
    opacity: float = 1.0


@dataclass
class GeneralConfig:
    minimize_to_tray: bool = False
    start_listening_on_launch: bool = False


@dataclass
class LevelConfig:
    enabled: bool = True
    title: str = "KILL"
    media: str = ""
    sound: str = ""
    duration_ms: int = 1300
    volume: float = 0.9
    scale: float = 1.0
    chroma_key: str = "none"


@dataclass
class AppConfig:
    version: int = 1
    game: GameConfig = field(default_factory=GameConfig)
    combo: ComboConfig = field(default_factory=ComboConfig)
    overlay: OverlayConfig = field(default_factory=OverlayConfig)
    general: GeneralConfig = field(default_factory=GeneralConfig)
    levels: dict[str, LevelConfig] = field(default_factory=dict)

    @staticmethod
    def from_dict(raw: dict[str, Any]) -> "AppConfig":
        defaults = default_config()
        levels_raw = raw.get("levels", {})

        levels: dict[str, LevelConfig] = {}
        for level in range(1, 6):
            key = str(level)
            base = defaults.levels[key]
            value = levels_raw.get(key, {})
            levels[key] = LevelConfig(
                enabled=bool(value.get("enabled", base.enabled)),
                title=str(value.get("title", base.title)),
                media=str(value.get("media", base.media)),
                sound=str(value.get("sound", base.sound)),
                duration_ms=int(value.get("duration_ms", base.duration_ms)),
                volume=float(value.get("volume", base.volume)),
                scale=float(value.get("scale", base.scale)),
                chroma_key=str(value.get("chroma_key", base.chroma_key)),
            )

        game_raw = raw.get("game", {})
        combo_raw = raw.get("combo", {})
        overlay_raw = raw.get("overlay", {})
        general_raw = raw.get("general", {})

        return AppConfig(
            version=int(raw.get("version", defaults.version)),
            game=GameConfig(
                player_name=str(
                    game_raw.get("player_name", defaults.game.player_name)
                ),
                base_url=str(game_raw.get("base_url", defaults.game.base_url)),
                poll_interval_ms=int(
                    game_raw.get(
                        "poll_interval_ms",
                        defaults.game.poll_interval_ms,
                    )
                ),
                kill_keywords=[
                    str(item).strip()
                    for item in game_raw.get(
                        "kill_keywords",
                        defaults.game.kill_keywords,
                    )
                    if str(item).strip()
                ],
            ),
            combo=ComboConfig(
                timeout_ms=int(
                    combo_raw.get("timeout_ms", defaults.combo.timeout_ms)
                ),
                use_highest_for_overflow=bool(
                    combo_raw.get(
                        "use_highest_for_overflow",
                        defaults.combo.use_highest_for_overflow,
                    )
                ),
            ),
            overlay=OverlayConfig(
                screen_index=int(
                    overlay_raw.get(
                        "screen_index",
                        defaults.overlay.screen_index,
                    )
                ),
                x_ratio=float(
                    overlay_raw.get("x_ratio", defaults.overlay.x_ratio)
                ),
                y_ratio=float(
                    overlay_raw.get("y_ratio", defaults.overlay.y_ratio)
                ),
                base_size_px=int(
                    overlay_raw.get(
                        "base_size_px",
                        defaults.overlay.base_size_px,
                    )
                ),
                global_scale=float(
                    overlay_raw.get(
                        "global_scale",
                        defaults.overlay.global_scale,
                    )
                ),
                opacity=float(
                    overlay_raw.get("opacity", defaults.overlay.opacity)
                ),
            ),
            general=GeneralConfig(
                minimize_to_tray=bool(
                    general_raw.get(
                        "minimize_to_tray",
                        defaults.general.minimize_to_tray,
                    )
                ),
                start_listening_on_launch=bool(
                    general_raw.get(
                        "start_listening_on_launch",
                        defaults.general.start_listening_on_launch,
                    )
                ),
            ),
            levels=levels,
        )


def default_config() -> AppConfig:
    titles = {
        1: "KILL",
        2: "DOUBLE KILL",
        3: "MULTI KILL",
        4: "ULTRA KILL",
        5: "UNBELIEVABLE",
    }

    levels = {
        str(level): LevelConfig(
            title=titles[level],
            media=f"assets/default/kill_{level}.png",
            sound=f"assets/default/kill_{level}.wav",
            duration_ms=1100 + level * 120,
            volume=min(0.65 + level * 0.06, 1.0),
            scale=1.0 + (level - 1) * 0.04,
        )
        for level in range(1, 6)
    }

    return AppConfig(levels=levels)
