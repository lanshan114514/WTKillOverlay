from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import av
import numpy as np

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, QUrl, Signal, Qt
from PySide6.QtGui import QImage, QMovie, QPixmap
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import QLabel


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}
GIF_EXTENSIONS = {".gif"}
VIDEO_EXTENSIONS = {".mp4", ".webm", ".mov", ".mkv", ".avi"}


@dataclass(frozen=True)
class MediaRequest:
    path: Path
    duration_ms: int
    chroma_key: str


class AudioPlayer(QObject):
    error = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.output = QAudioOutput(self)
        self.player = QMediaPlayer(self)
        self.player.setAudioOutput(self.output)
        self.player.errorOccurred.connect(
            lambda _error, text: self.error.emit(text)
        )

    def play(self, path: Path, volume: float) -> None:
        if not path.is_file():
            self.error.emit(f"音效不存在：{path}")
            return

        self.player.stop()
        self.output.setVolume(max(0.0, min(float(volume), 1.0)))
        self.player.setSource(QUrl.fromLocalFile(str(path)))
        self.player.play()

    def stop(self) -> None:
        self.player.stop()


class VideoDecodeSignals(QObject):
    loaded = Signal(str, object, object, int)
    failed = Signal(str, str)


class VideoDecodeTask(QRunnable):
    def __init__(self, key: str, path: Path, chroma_key: str) -> None:
        super().__init__()
        self.key = key
        self.path = path
        self.chroma_key = chroma_key
        self.signals = VideoDecodeSignals()

    def run(self) -> None:
        try:
            frames, delays = decode_video(self.path, self.chroma_key)
            self.signals.loaded.emit(
                self.key,
                frames,
                delays,
                sum(delays),
            )
        except Exception as exc:
            self.signals.failed.emit(self.key, str(exc))


def decode_video(
    path: Path,
    chroma_key: str,
) -> tuple[list[QImage], list[int]]:
    frames: list[QImage] = []
    times: list[float | None] = []

    with av.open(str(path), timeout=5.0) as container:
        if not container.streams.video:
            raise ValueError("文件中没有视频轨道")

        stream = container.streams.video[0]
        stream.thread_type = "AUTO"

        try:
            rate = float(stream.average_rate) if stream.average_rate else 30.0
            fallback_delay = max(10, round(1000 / rate))
        except (TypeError, ValueError, ZeroDivisionError):
            fallback_delay = 33

        for frame in container.decode(stream):
            rgba = frame.to_ndarray(format="rgba")

            if chroma_key in {"green", "black"}:
                rgba = apply_chroma_key(rgba, chroma_key)

            rgba = np.ascontiguousarray(rgba)
            height, width, _channels = rgba.shape

            image = QImage(
                rgba.data,
                width,
                height,
                rgba.strides[0],
                QImage.Format.Format_RGBA8888,
            ).copy()

            frames.append(image)
            times.append(float(frame.time) if frame.time is not None else None)

            if len(frames) > 900:
                raise ValueError("视频超过 900 帧，请使用更短的击杀动画")

    if not frames:
        raise ValueError("视频没有可解码的画面")

    delays: list[int] = []
    for index in range(len(frames)):
        if index + 1 < len(times):
            current = times[index]
            following = times[index + 1]
            if current is not None and following is not None and following > current:
                delay = round((following - current) * 1000)
            else:
                delay = fallback_delay
        else:
            delay = fallback_delay

        delays.append(max(10, min(delay, 250)))

    return frames, delays


def apply_chroma_key(rgba: np.ndarray, mode: str) -> np.ndarray:
    result = rgba.copy()
    rgb = result[:, :, :3].astype(np.int16)

    if mode == "green":
        key = np.array([0, 255, 0], dtype=np.int16)
        tolerance = 95
    else:
        key = np.array([0, 0, 0], dtype=np.int16)
        tolerance = 45

    distance = np.sqrt(np.sum((rgb - key) ** 2, axis=2))
    alpha = result[:, :, 3].astype(np.float32)

    fully_transparent = distance <= tolerance
    feather = (distance > tolerance) & (distance < tolerance + 45)

    alpha[fully_transparent] = 0
    alpha[feather] *= (distance[feather] - tolerance) / 45
    result[:, :, 3] = alpha.clip(0, 255).astype(np.uint8)

    return result


class MediaLabel(QLabel):
    ready = Signal(int)
    failed = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("background: transparent;")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        self._movie: QMovie | None = None
        self._source_pixmap: QPixmap | None = None

        self._video_frames: list[QImage] = []
        self._video_delays: list[int] = []
        self._video_index = 0
        self._video_timer = QTimer(self)
        self._video_timer.setSingleShot(True)
        self._video_timer.timeout.connect(self._show_next_video_frame)

        self._thread_pool = QThreadPool.globalInstance()
        self._cache: dict[str, tuple[list[QImage], list[int], int]] = {}
        self._current_key = ""
        self._requested_duration = 0

    def stop(self) -> None:
        self._video_timer.stop()
        self._video_frames = []
        self._video_delays = []
        self._video_index = 0

        if self._movie is not None:
            self._movie.stop()
            self._movie.deleteLater()
            self._movie = None

        self._source_pixmap = None
        self.clear()
        self.setText("")

    def play(self, request: MediaRequest) -> None:
        self.stop()

        path = request.path
        if not path.is_file():
            self.failed.emit(f"素材不存在：{path}")
            return

        suffix = path.suffix.lower()
        self._requested_duration = max(0, request.duration_ms)
        self._current_key = (
            f"{path.resolve()}|{path.stat().st_mtime_ns}|{request.chroma_key}"
        )

        if suffix in IMAGE_EXTENSIONS:
            self._play_image(path)
        elif suffix in GIF_EXTENSIONS:
            self._play_gif(path)
        elif suffix in VIDEO_EXTENSIONS:
            self._play_video(path, request.chroma_key)
        else:
            self.failed.emit(f"不支持的素材格式：{suffix}")

    def _play_image(self, path: Path) -> None:
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            self.failed.emit(f"图片读取失败：{path}")
            return

        self._source_pixmap = pixmap
        self._refresh_pixmap()
        self.ready.emit(self._requested_duration or 1400)

    def _play_gif(self, path: Path) -> None:
        movie = QMovie(str(path))
        movie.setCacheMode(QMovie.CacheMode.CacheAll)

        if not movie.isValid():
            self.failed.emit(f"GIF 读取失败：{path}")
            movie.deleteLater()
            return

        self._movie = movie
        movie.frameChanged.connect(self._refresh_movie_frame)
        movie.start()
        self.ready.emit(self._requested_duration or 1800)

    def _play_video(self, path: Path, chroma_key: str) -> None:
        key = self._current_key
        if key in self._cache:
            frames, delays, duration = self._cache[key]
            self._start_video(frames, delays, duration)
            return

        self.setText("正在解码视频…")
        task = VideoDecodeTask(key, path, chroma_key)
        task.signals.loaded.connect(self._video_loaded)
        task.signals.failed.connect(self._video_failed)
        self._thread_pool.start(task)

    def _video_loaded(
        self,
        key: str,
        frames: list[QImage],
        delays: list[int],
        duration: int,
    ) -> None:
        self._cache[key] = (frames, delays, duration)
        if key != self._current_key:
            return
        self._start_video(frames, delays, duration)

    def _video_failed(self, key: str, error: str) -> None:
        if key == self._current_key:
            self.failed.emit(f"视频解码失败：{error}")

    def _start_video(
        self,
        frames: list[QImage],
        delays: list[int],
        duration: int,
    ) -> None:
        self.setText("")
        self._video_frames = frames
        self._video_delays = delays
        self._video_index = 0
        self._show_next_video_frame()
        self.ready.emit(self._requested_duration or max(duration, 100))

    def _show_next_video_frame(self) -> None:
        if self._video_index >= len(self._video_frames):
            return

        image = self._video_frames[self._video_index]
        delay = self._video_delays[self._video_index]
        self._source_pixmap = QPixmap.fromImage(image)
        self._refresh_pixmap()

        self._video_index += 1
        if self._video_index < len(self._video_frames):
            self._video_timer.start(delay)

    def _refresh_movie_frame(self) -> None:
        if self._movie is None:
            return
        pixmap = self._movie.currentPixmap()
        if not pixmap.isNull():
            self._source_pixmap = pixmap
            self._refresh_pixmap()

    def _refresh_pixmap(self) -> None:
        if self._source_pixmap is None or self._source_pixmap.isNull():
            return

        scaled = self._source_pixmap.scaled(
            self.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.setPixmap(scaled)

    def resizeEvent(self, event: Any) -> None:
        super().resizeEvent(event)
        self._refresh_pixmap()
