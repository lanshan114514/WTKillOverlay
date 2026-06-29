from __future__ import annotations

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtWidgets import QApplication, QWidget

from .media import MediaLabel, MediaRequest
from .models import LevelConfig, OverlayConfig
from .paths import resolve_data_path


class OverlayWindow(QWidget):
    playbackFailed = Signal(str)
    playbackStarted = Signal(int)

    def __init__(self) -> None:
        super().__init__()

        self.setWindowTitle("WTKillOverlay")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)

        self.media = MediaLabel()
        self.media.setParent(self)
        self.media.hide()
        self.media.ready.connect(self._on_ready)
        self.media.failed.connect(self._on_failed)

        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.hide_media)

        self._pending_level = 0

    def play_level(
        self,
        level: int,
        level_config: LevelConfig,
        overlay_config: OverlayConfig,
    ) -> None:
        if not level_config.enabled:
            return

        path = resolve_data_path(level_config.media)
        if not path.is_file():
            self.playbackFailed.emit(f"{level} 杀素材不存在：{path}")
            return

        self.hide_timer.stop()
        self.media.stop()

        self._apply_geometry(level_config, overlay_config)
        self.setWindowOpacity(max(0.1, min(overlay_config.opacity, 1.0)))

        self._pending_level = level
        self.show()
        self.raise_()
        self.media.show()
        self.media.raise_()

        self.media.play(
            MediaRequest(
                path=path,
                duration_ms=level_config.duration_ms,
                chroma_key=level_config.chroma_key,
            )
        )

    def _apply_geometry(
        self,
        level_config: LevelConfig,
        overlay_config: OverlayConfig,
    ) -> None:
        screens = QApplication.screens()
        if not screens:
            return

        screen_index = max(0, min(overlay_config.screen_index, len(screens) - 1))
        geometry = screens[screen_index].geometry()
        self.setGeometry(geometry)

        size = round(
            overlay_config.base_size_px
            * overlay_config.global_scale
            * level_config.scale
        )
        size = max(120, min(size, min(geometry.width(), geometry.height())))
        self.media.resize(size, size)

        center_x = round(geometry.width() * overlay_config.x_ratio)
        center_y = round(geometry.height() * overlay_config.y_ratio)
        self.media.move(center_x - size // 2, center_y - size // 2)

    def _on_ready(self, duration_ms: int) -> None:
        self.playbackStarted.emit(self._pending_level)
        self.hide_timer.start(max(duration_ms, 100))

    def _on_failed(self, message: str) -> None:
        self.hide_media()
        self.playbackFailed.emit(message)

    def hide_media(self) -> None:
        self.hide_timer.stop()
        self.media.stop()
        self.media.hide()

    def close_overlay(self) -> None:
        self.hide_media()
        self.close()
