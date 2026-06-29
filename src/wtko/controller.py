from __future__ import annotations

from datetime import datetime
from pathlib import Path
import time

from PySide6.QtCore import QObject, QTimer
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QMenu,
    QSystemTrayIcon,
)

from .assets import AssetService
from .config import ConfigManager
from .listener import ListenerSettings, WarThunderListener
from .main_window import MainWindow
from .media import AudioPlayer
from .overlay import OverlayWindow
from .paths import config_path, logs_dir, resolve_data_path, resource_path


class ApplicationController(QObject):
    def __init__(self, app: QApplication) -> None:
        super().__init__()
        self.app = app

        self.config_manager = ConfigManager(config_path())
        self.config = self.config_manager.load()
        self.asset_service = AssetService()

        self.window = MainWindow(self.config)
        self.overlay = OverlayWindow()
        self.audio = AudioPlayer(self)
        self.listener: WarThunderListener | None = None

        self.combo_count = 0
        self.last_kill_time = 0.0
        self.sequence_level = 0

        self._connect_signals()
        self._create_tray()
        self._apply_style()

    def start(self) -> None:
        self.window.show()
        self.log("程序已启动。")
        self.log(f"数据目录：{config_path().parent}")

        if self.config.general.start_listening_on_launch:
            QTimer.singleShot(300, self.start_listener)

    def _connect_signals(self) -> None:
        self.window.startRequested.connect(self.start_listener)
        self.window.stopRequested.connect(self.stop_listener)
        self.window.saveRequested.connect(self.save_config)
        self.window.previewRequested.connect(self.preview_level)
        self.window.sequenceRequested.connect(self.start_sequence_preview)
        self.window.chooseMediaRequested.connect(self.choose_media)
        self.window.chooseSoundRequested.connect(self.choose_sound)
        self.window.exitRequested.connect(self.exit_application)

        self.overlay.playbackFailed.connect(
            lambda text: self.log(f"播放失败：{text}")
        )
        self.overlay.playbackStarted.connect(
            lambda level: self.log(f"开始显示 {level} 杀素材。")
        )
        self.audio.error.connect(
            lambda text: self.log(f"音频错误：{text}")
        )
        self.app.aboutToQuit.connect(self.shutdown)

    def _create_tray(self) -> None:
        icon_path = resource_path("resources/app.ico")
        icon = QIcon(str(icon_path)) if icon_path.exists() else self.app.windowIcon()

        self.tray = QSystemTrayIcon(icon, self)
        self.tray.setToolTip("战争雷霆击杀提示")

        menu = QMenu()
        open_action = QAction("打开控制台", menu)
        start_action = QAction("启动监听", menu)
        stop_action = QAction("停止监听", menu)
        preview_action = QAction("预览一杀", menu)
        exit_action = QAction("退出", menu)

        open_action.triggered.connect(self.show_window)
        start_action.triggered.connect(self.start_listener)
        stop_action.triggered.connect(self.stop_listener)
        preview_action.triggered.connect(lambda: self.preview_level(1))
        exit_action.triggered.connect(self.exit_application)

        menu.addAction(open_action)
        menu.addSeparator()
        menu.addAction(start_action)
        menu.addAction(stop_action)
        menu.addAction(preview_action)
        menu.addSeparator()
        menu.addAction(exit_action)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(
            lambda reason: self.show_window()
            if reason == QSystemTrayIcon.ActivationReason.DoubleClick
            else None
        )

        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()

    def _apply_style(self) -> None:
        style_path = resource_path("resources/style.qss")
        if style_path.exists():
            self.app.setStyleSheet(style_path.read_text(encoding="utf-8"))

    def show_window(self) -> None:
        self.window.show()
        self.window.raise_()
        self.window.activateWindow()

    def save_config(self) -> None:
        self.config = self.window.apply_controls_to_config()
        self.config_manager.save(self.config)

        if self.listener is not None and self.listener.isRunning():
            self.listener.update_settings(self._listener_settings())

    def start_listener(self) -> None:
        self.save_config()

        if not self.config.game.player_name:
            self.window.show_error(
                "缺少玩家昵称",
                "请先在“设置”页面填写游戏中的完整昵称。",
            )
            return

        if self.listener is not None and self.listener.isRunning():
            return

        self.listener = WarThunderListener(self._listener_settings())
        self.listener.connectionChanged.connect(self._connection_changed)
        self.listener.rawMessage.connect(self._raw_message)
        self.listener.killDetected.connect(self._kill_detected)
        self.listener.diagnostic.connect(
            lambda text: self.log(f"诊断：{text}")
        )
        self.listener.finished.connect(
            lambda: self.window.set_listener_running(False)
        )

        self.listener.start()
        self.window.set_listener_running(True)
        self.log("监听器已启动，等待战争雷霆 8111 接口。")

    def stop_listener(self) -> None:
        if self.listener is None:
            self.window.set_listener_running(False)
            return

        if self.listener.isRunning():
            self.listener.stop()
            self.listener.wait(1800)

        self.listener = None
        self.window.set_listener_running(False)
        self.window.set_connection_status(False, "监听已停止")
        self.log("监听器已停止。")

    def _listener_settings(self) -> ListenerSettings:
        return ListenerSettings(
            player_name=self.config.game.player_name,
            base_url=self.config.game.base_url,
            poll_interval_ms=self.config.game.poll_interval_ms,
            kill_keywords=tuple(self.config.game.kill_keywords),
        )

    def _connection_changed(self, connected: bool, detail: str) -> None:
        self.window.set_connection_status(connected, detail)
        self.log(detail)

    def _raw_message(self, message: str) -> None:
        self.window.set_last_message(message)
        self.log(f"HUD：{message}")

    def _kill_detected(self, message: str) -> None:
        now = time.monotonic()
        if (
            self.last_kill_time > 0
            and (now - self.last_kill_time) * 1000
            <= self.config.combo.timeout_ms
        ):
            self.combo_count += 1
        else:
            self.combo_count = 1

        self.last_kill_time = now
        resolved = self.resolve_level(self.combo_count)
        self.log(
            f"检测到本人击杀，当前连杀 {self.combo_count}，"
            f"使用 {resolved} 杀素材。"
        )
        self.play_level(resolved)

    def resolve_level(self, combo: int) -> int:
        enabled_levels = [
            level
            for level in range(1, 6)
            if self.config.levels[str(level)].enabled
        ]

        if not enabled_levels:
            return 1

        matching = [level for level in enabled_levels if level <= combo]
        if matching:
            return max(matching)

        return min(enabled_levels)

    def play_level(self, level: int) -> None:
        self.config = self.window.apply_controls_to_config()
        level_config = self.config.levels[str(level)]

        self.overlay.play_level(
            level,
            level_config,
            self.config.overlay,
        )

        sound_path = resolve_data_path(level_config.sound)
        if level_config.sound:
            self.audio.play(sound_path, level_config.volume)

    def preview_level(self, level: int) -> None:
        self.log(f"手动预览 {level} 杀。")
        self.play_level(level)

    def start_sequence_preview(self) -> None:
        self.sequence_level = 1
        self._play_next_sequence_level()

    def _play_next_sequence_level(self) -> None:
        if self.sequence_level > 5:
            return

        self.preview_level(self.sequence_level)
        self.sequence_level += 1
        QTimer.singleShot(1700, self._play_next_sequence_level)

    def choose_media(self, level: int) -> None:
        filters = (
            "媒体文件 (*.png *.jpg *.jpeg *.bmp *.webp *.gif "
            "*.mp4 *.webm *.mov *.mkv *.avi)"
        )
        filename, _selected = QFileDialog.getOpenFileName(
            self.window,
            f"选择 {level} 杀图片或视频",
            str(Path.home()),
            filters,
        )
        if not filename:
            return

        try:
            stored = self.asset_service.import_media(Path(filename))
            self.window.set_media_path(level, stored)
            self.save_config()
            self.log(f"已导入 {level} 杀素材：{stored}")
        except Exception as exc:
            self.window.show_error("素材导入失败", str(exc))

    def choose_sound(self, level: int) -> None:
        filters = "音频文件 (*.wav *.mp3 *.ogg *.flac *.m4a)"
        filename, _selected = QFileDialog.getOpenFileName(
            self.window,
            f"选择 {level} 杀音效",
            str(Path.home()),
            filters,
        )
        if not filename:
            return

        try:
            stored = self.asset_service.import_audio(Path(filename))
            self.window.set_sound_path(level, stored)
            self.save_config()
            self.log(f"已导入 {level} 杀音效：{stored}")
        except Exception as exc:
            self.window.show_error("音效导入失败", str(exc))

    def log(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        line = f"[{timestamp}] {message}"
        self.window.append_log(line)

        log_file = logs_dir() / f"{datetime.now():%Y-%m-%d}.log"
        try:
            with log_file.open("a", encoding="utf-8") as file:
                file.write(line + "\n")
        except OSError:
            pass

    def exit_application(self) -> None:
        self.window.force_close = True
        self.app.quit()

    def shutdown(self) -> None:
        if self.listener is not None and self.listener.isRunning():
            self.listener.stop()
            self.listener.wait(1200)
        self.audio.stop()
        self.overlay.close_overlay()
        self.tray.hide()
