from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


DEFAULT_KILL_KEYWORDS = [
    "摧毁了",
    "击毁了",
    "消灭了",
    "击杀了",
    "目标已摧毁",
    "destroyed",
    "shot down",
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
    infinite_timeout: bool = False
    use_highest_for_overflow: bool = True


@dataclass
class OverlayConfig:
    screen_index: int = 0
    x_ratio: float = 0.5
    y_ratio: float = 0.28
    base_size_px: int = 520
    global_scale: float = 1.0
    opacity: float = 1.0
    fade_in_ms: int = 0
    fade_out_ms: int = 0


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
class MouseClickConfig:
    """鼠标左键点击触发提示配置。单击一次；按住则循环播放。"""
    enabled: bool = False
    media: str = ""
    sound: str = ""
    duration_ms: int = 500   # 每次持续时间
    volume: float = 0.8
    scale: float = 0.8
    chroma_key: str = "none"
    loop_on_hold: bool = True  # 按住时是否循环


def _load_level(raw: dict[str, Any], base: LevelConfig) -> LevelConfig:
    return LevelConfig(
        enabled=bool(raw.get("enabled", base.enabled)),
        title=str(raw.get("title", base.title)),
        media=str(raw.get("media", base.media)),
        sound=str(raw.get("sound", base.sound)),
        duration_ms=int(raw.get("duration_ms", base.duration_ms)),
        volume=float(raw.get("volume", base.volume)),
        scale=float(raw.get("scale", base.scale)),
        chroma_key=str(raw.get("chroma_key", base.chroma_key)),
    )


@dataclass
class AppConfig:
    version: int = 1
    game: GameConfig = field(default_factory=GameConfig)
    combo: ComboConfig = field(default_factory=ComboConfig)
    overlay: OverlayConfig = field(default_factory=OverlayConfig)
    general: GeneralConfig = field(default_factory=GeneralConfig)
    levels: dict[str, LevelConfig] = field(default_factory=dict)
    mouse_click: MouseClickConfig = field(default_factory=MouseClickConfig)

    @staticmethod
    def from_dict(raw: dict[str, Any]) -> "AppConfig":
        defaults = default_config()

        levels_raw = raw.get("levels", {})
        levels: dict[str, LevelConfig] = {}
        if levels_raw:
            for key, value in levels_raw.items():
                try:
                    int(key)
                except ValueError:
                    continue
                base_level = defaults.levels.get(key, _default_level(int(key)))
                levels[key] = _load_level(
                    value if isinstance(value, dict) else {}, base_level
                )
        else:
            levels = dict(defaults.levels)

        game_raw = raw.get("game", {})
        combo_raw = raw.get("combo", {})
        overlay_raw = raw.get("overlay", {})
        general_raw = raw.get("general", {})
        mc_raw = raw.get("mouse_click", {})
        mc_base = defaults.mouse_click

        return AppConfig(
            version=int(raw.get("version", defaults.version)),
            game=GameConfig(
                player_name=str(game_raw.get("player_name", defaults.game.player_name)),
                base_url=str(game_raw.get("base_url", defaults.game.base_url)),
                poll_interval_ms=int(
                    game_raw.get("poll_interval_ms", defaults.game.poll_interval_ms)
                ),
                kill_keywords=[
                    str(item).strip()
                    for item in game_raw.get("kill_keywords", defaults.game.kill_keywords)
                    if str(item).strip()
                ],
            ),
            combo=ComboConfig(
                timeout_ms=int(combo_raw.get("timeout_ms", defaults.combo.timeout_ms)),
                infinite_timeout=bool(
                    combo_raw.get("infinite_timeout", defaults.combo.infinite_timeout)
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
                    overlay_raw.get("screen_index", defaults.overlay.screen_index)
                ),
                x_ratio=float(overlay_raw.get("x_ratio", defaults.overlay.x_ratio)),
                y_ratio=float(overlay_raw.get("y_ratio", defaults.overlay.y_ratio)),
                base_size_px=int(
                    overlay_raw.get("base_size_px", defaults.overlay.base_size_px)
                ),
                global_scale=float(
                    overlay_raw.get("global_scale", defaults.overlay.global_scale)
                ),
                opacity=float(overlay_raw.get("opacity", defaults.overlay.opacity)),
                fade_in_ms=int(
                    overlay_raw.get("fade_in_ms", defaults.overlay.fade_in_ms)
                ),
                fade_out_ms=int(
                    overlay_raw.get("fade_out_ms", defaults.overlay.fade_out_ms)
                ),
            ),
            general=GeneralConfig(
                minimize_to_tray=bool(
                    general_raw.get("minimize_to_tray", defaults.general.minimize_to_tray)
                ),
                start_listening_on_launch=bool(
                    general_raw.get(
                        "start_listening_on_launch",
                        defaults.general.start_listening_on_launch,
                    )
                ),
            ),
            levels=levels,
            mouse_click=MouseClickConfig(
                enabled=bool(mc_raw.get("enabled", mc_base.enabled)),
                media=str(mc_raw.get("media", mc_base.media)),
                sound=str(mc_raw.get("sound", mc_base.sound)),
                duration_ms=int(mc_raw.get("duration_ms", mc_base.duration_ms)),
                volume=float(mc_raw.get("volume", mc_base.volume)),
                scale=float(mc_raw.get("scale", mc_base.scale)),
                chroma_key=str(mc_raw.get("chroma_key", mc_base.chroma_key)),
                loop_on_hold=bool(mc_raw.get("loop_on_hold", mc_base.loop_on_hold)),
            ),
        )


def _default_level(n: int) -> LevelConfig:
    titles = {
        1: "KILL", 2: "DOUBLE KILL", 3: "MULTI KILL",
        4: "ULTRA KILL", 5: "UNBELIEVABLE",
    }
    return LevelConfig(
        title=titles.get(n, f"{n} KILLS"),
        media=f"assets/default/kill_{min(n, 5)}.png",
        sound=f"assets/default/kill_{min(n, 5)}.wav",
        duration_ms=1100 + min(n, 10) * 120,
        volume=min(0.65 + min(n, 10) * 0.06, 1.0),
        scale=1.0 + (min(n, 10) - 1) * 0.04,
    )


def default_config() -> AppConfig:
    levels = {str(n): _default_level(n) for n in range(1, 6)}
    return AppConfig(levels=levels)
