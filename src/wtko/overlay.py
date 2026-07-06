from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    QTimer,
    Qt,
    Signal,
)
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
        self.hide_timer.timeout.connect(self._start_fade_out)

        self._fade_anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.InOutSine)
        self._fade_anim.finished.connect(self._on_fade_finished)

        self._pending_level = 0
        self._target_opacity = 1.0
        self._fade_out_ms = 0
        self._fading_out = False

    # ── 公开接口 ───────────────────────────────────────────────────────────

    def play_level(
        self,
        level: int,
        level_config: LevelConfig,
        overlay_config: OverlayConfig,
    ) -> None:
        if not level_config.enabled or not level_config.media:
            return
        path = resolve_data_path(level_config.media)
        if not path.is_file():
            self.playbackFailed.emit(f"{level} 杀素材不存在：{path}")
            return
        self._pending_level = level
        self._play_media(
            media_path=path,
            duration_ms=level_config.duration_ms,
            chroma_key=level_config.chroma_key,
            scale=level_config.scale,
            overlay_config=overlay_config,
        )

    def play_generic(
        self,
        media: str,
        duration_ms: int,
        chroma_key: str,
        scale: float,
        overlay_config: OverlayConfig,
    ) -> None:
        """通用播放接口，供鼠标点击等非连杀场景使用。"""
        if not media:
            return
        path = resolve_data_path(media)
        if not path.is_file():
            self.playbackFailed.emit(f"素材不存在：{path}")
            return
        self._pending_level = 0
        self._play_media(
            media_path=path,
            duration_ms=duration_ms,
            chroma_key=chroma_key,
            scale=scale,
            overlay_config=overlay_config,
        )

    # ── 内部播放 ───────────────────────────────────────────────────────────

    def _play_media(
        self,
        media_path: Path,
        duration_ms: int,
        chroma_key: str,
        scale: float,
        overlay_config: OverlayConfig,
    ) -> None:
        self._fading_out = False
        self._fade_anim.stop()
        self.hide_timer.stop()
        self.media.stop()

        self._target_opacity = max(0.1, min(overlay_config.opacity, 1.0))
        self._fade_out_ms = max(0, overlay_config.fade_out_ms)
        fade_in_ms = max(0, overlay_config.fade_in_ms)

        self._apply_geometry_raw(scale, overlay_config)

        self.show()
        self.raise_()
        self.media.show()
        self.media.raise_()

        self.media.play(
            MediaRequest(path=media_path, duration_ms=duration_ms, chroma_key=chroma_key)
        )

        if fade_in_ms > 0:
            self.setWindowOpacity(0.0)
            self._fade_anim.setStartValue(0.0)
            self._fade_anim.setEndValue(self._target_opacity)
            self._fade_anim.setDuration(fade_in_ms)
            self._fading_out = False
            self._fade_anim.start()
        else:
            self.setWindowOpacity(self._target_opacity)

    def _apply_geometry_raw(self, scale: float, overlay_config: OverlayConfig) -> None:
        screens = QApplication.screens()
        if not screens:
            return
        screen_index = max(0, min(overlay_config.screen_index, len(screens) - 1))
        geometry = screens[screen_index].geometry()
        self.setGeometry(geometry)
        size = round(overlay_config.base_size_px * overlay_config.global_scale * scale)
        size = max(120, min(size, min(geometry.width(), geometry.height())))
        self.media.resize(size, size)
        cx = round(geometry.width() * overlay_config.x_ratio)
        cy = round(geometry.height() * overlay_config.y_ratio)
        self.media.move(cx - size // 2, cy - size // 2)

    def _start_fade_out(self) -> None:
        if self._fade_out_ms > 0:
            self._fading_out = True
            self._fade_anim.stop()
            self._fade_anim.setStartValue(self.windowOpacity())
            self._fade_anim.setEndValue(0.0)
            self._fade_anim.setDuration(self._fade_out_ms)
            self._fade_anim.start()
        else:
            self.hide_media()

    def _on_fade_finished(self) -> None:
        if self._fading_out:
            self._fading_out = False
            self.hide_media()

    def _on_ready(self, duration_ms: int) -> None:
        self.playbackStarted.emit(self._pending_level)
        delay = max(0, max(duration_ms, 100) - self._fade_out_ms)
        self.hide_timer.start(delay)

    def _on_failed(self, message: str) -> None:
        self.hide_media()
        self.playbackFailed.emit(message)

    def hide_media(self) -> None:
        self._fade_anim.stop()
        self.hide_timer.stop()
        self.media.stop()
        self.media.hide()

    def close_overlay(self) -> None:
        self.hide_media()
        self.close()
