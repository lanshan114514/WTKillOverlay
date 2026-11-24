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
from .audio_engine import AudioEngine
from .config import ConfigManager
from .listener import ListenerSettings, WarThunderListener
from .main_window import MainWindow
from .media import AudioPlayer
from .models import RandomPoolItem
from .mouse_listener import MouseClickWorker
from .overlay import OverlayWindow
from .paths import config_path, logs_dir, resolve_data_path, resource_path
from .picker import pick_item


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
        # 常驻流混音器；打不开设备时自动回退到上面的 AudioPlayer
        self.audio_engine = AudioEngine(self)
        self.listener: WarThunderListener | None = None

        self.combo_count = 0
        self.last_kill_time = 0.0
        self.sequence_level = 0
        self._last_random_identity = ""

        # 鼠标点击状态
        self._mouse_holding = False
        self._mouse_loop_timer = QTimer(self)
        self._mouse_loop_timer.setSingleShot(False)
        self._mouse_loop_timer.timeout.connect(self._on_mouse_loop_tick)

        self._mouse_worker = MouseClickWorker(self)
        self._mouse_worker.leftPressed.connect(self._on_mouse_pressed)
        self._mouse_worker.leftReleased.connect(self._on_mouse_released)

        self._connect_signals()
        self._create_tray()
        self._apply_style()

    def start(self) -> None:
        self.window.show()
        self.log("程序已启动。")
        self.log(f"数据目录：{config_path().parent}")

        self.audio_engine.stateChanged.connect(self._on_audio_ready)
        self.audio_engine.start()
        self._preload_sounds()

        if self.config.general.start_listening_on_launch:
            QTimer.singleShot(300, self.start_listener)

        # 鼠标监听始终启动（不需要 WT 连接）
        self._mouse_worker.start()

    def _on_audio_ready(self, ok: bool, detail: str) -> None:
        if ok:
            self.log(f"音频引擎就绪：{detail}")
        else:
            self.log(f"音频引擎不可用（回退到旧播放器）：{detail}")

    def _preload_sounds(self) -> None:
        paths: list[Path] = []
        for level in self.config.levels.values():
            if level.sound:
                paths.append(resolve_data_path(level.sound))
        for item in self.config.random.items:
            if item.sound:
                paths.append(resolve_data_path(item.sound))
        if self.config.mouse_click.sound:
            paths.append(resolve_data_path(self.config.mouse_click.sound))
        self.audio_engine.preload(paths)

    def _play_sound(self, path: Path, volume: float) -> None:
        """立刻起声，不排队、不故意错开。

        密集连杀时靠音频引擎的侧链闪避把新一炮的起声顶出来，
        这里不再人为拉开间隔。
        """
        self._emit_sound(path, volume)

    def _emit_sound(self, path: Path, volume: float) -> None:
        if self.audio_engine.is_ready() and self.audio_engine.play(path, volume):
            return
        self.audio.play(path, volume)

    def _connect_signals(self) -> None:
        self.window.startRequested.connect(self.start_listener)
        self.window.stopRequested.connect(self.stop_listener)
        self.window.saveRequested.connect(self.save_config)
        self.window.previewRequested.connect(self.preview_level)
        self.window.sequenceRequested.connect(self.start_sequence_preview)
        self.window.chooseMediaRequested.connect(self.choose_media)
        self.window.chooseSoundRequested.connect(self.choose_sound)
        self.window.exitRequested.connect(self.exit_application)
        self.window.resetComboRequested.connect(self.reset_combo)
        self.window.chooseMouseMediaRequested.connect(self.choose_mouse_media)
        self.window.chooseMouseSoundRequested.connect(self.choose_mouse_sound)
        self.window.previewMouseClickRequested.connect(self._play_mouse_click_once)
        self.window.chooseRandomMediaRequested.connect(self.choose_random_media)
        self.window.chooseRandomSoundRequested.connect(self.choose_random_sound)
        self.window.previewRandomRequested.connect(self.preview_random)
        self.window.importRandomFromLevelsRequested.connect(self.import_random_from_levels)

        self.overlay.playbackFailed.connect(
            lambda text: self.log(f"播放失败：{text}")
        )
        self.overlay.playbackStarted.connect(
            lambda level: self.log(f"开始显示 {level} 杀素材。") if level > 0 else None
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
                "请先在【设置】页面填写游戏中的完整昵称。",
            )
            return

        if self.listener is not None and self.listener.isRunning():
            return

        self.listener = WarThunderListener(self._listener_settings())
        self.listener.connectionChanged.connect(self._connection_changed)
        self.listener.rawMessage.connect(self._raw_message)
        self.listener.killDetected.connect(self._kill_detected)
        self.listener.gameReset.connect(self._on_game_reset)
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
        infinite = self.config.combo.infinite_timeout
        if infinite:
            self.combo_count = self.combo_count + 1 if self.last_kill_time > 0 else 1
        elif (
            self.last_kill_time > 0
            and (now - self.last_kill_time) * 1000 <= self.config.combo.timeout_ms
        ):
            self.combo_count += 1
        else:
            self.combo_count = 1

        self.last_kill_time = now
        self.window.update_combo_display(self.combo_count)

        if self._random_mode_active():
            self._play_random()
            return

        resolved = self.resolve_level(self.combo_count)
        self.log(
            f"检测到本人击杀，当前连杀 {self.combo_count}，使用 {resolved} 杀素材。"
        )
        self.play_level(resolved)

    # ── 随机播放 ─────────────────────────────────────────────────────────

    def _random_mode_active(self) -> bool:
        config = self.config.random
        return config.enabled and any(item.is_usable() for item in config.items)

    def _play_random(self) -> None:
        self.config = self.window.apply_controls_to_config()
        item = pick_item(
            self.config.random.items,
            self.combo_count,
            last_identity=self._last_random_identity,
            avoid_repeat=self.config.random.avoid_repeat,
        )

        if item is None:
            self.log("随机池没有可用条目，回退到按连杀数播放。")
            self._last_random_identity = ""
            self.play_level(self.resolve_level(self.combo_count))
            return

        self._last_random_identity = item.identity()
        name = Path(item.media or item.sound).name
        self.log(f"随机播放：{name}（当前连杀 {self.combo_count}）")

        if item.media:
            self.overlay.play_generic(
                media=item.media,
                duration_ms=item.duration_ms,
                chroma_key=item.chroma_key,
                scale=item.scale,
                overlay_config=self.config.overlay,
            )
        if item.sound:
            self._play_sound(resolve_data_path(item.sound), item.volume)

    def preview_random(self, index: int) -> None:
        self.config = self.window.apply_controls_to_config()
        items = self.config.random.items
        if not 0 <= index < len(items):
            return
        item = items[index]
        if not item.is_usable():
            self.log("这条随机素材还没设置内容。")
            return
        self.log(f"手动预览随机素材：{Path(item.media or item.sound).name}")
        if item.media:
            self.overlay.play_generic(
                media=item.media,
                duration_ms=item.duration_ms,
                chroma_key=item.chroma_key,
                scale=item.scale,
                overlay_config=self.config.overlay,
            )
        if item.sound:
            self._play_sound(resolve_data_path(item.sound), item.volume)

    def choose_random_media(self, index: int) -> None:
        filters = (
            "媒体文件 (*.png *.jpg *.jpeg *.bmp *.webp *.gif "
            "*.mp4 *.webm *.mov *.mkv *.avi)"
        )
        filename, _ = QFileDialog.getOpenFileName(
            self.window, "选择随机素材图片或视频", str(Path.home()), filters
        )
        if not filename:
            return
        try:
            stored = self.asset_service.import_media(Path(filename))
            self.window.set_random_media_path(index, stored)
            self.save_config()
            self.log(f"已导入随机素材：{stored}")
        except Exception as exc:
            self.window.show_error("素材导入失败", str(exc))

    def choose_random_sound(self, index: int) -> None:
        filters = "音频文件 (*.wav *.mp3 *.ogg *.flac *.m4a)"
        filename, _ = QFileDialog.getOpenFileName(
            self.window, "选择随机音效", str(Path.home()), filters
        )
        if not filename:
            return
        try:
            stored = self.asset_service.import_audio(Path(filename))
            self.window.set_random_sound_path(index, stored)
            self.save_config()
            self.log(f"已导入随机音效：{stored}")
        except Exception as exc:
            self.window.show_error("音效导入失败", str(exc))

    def import_random_from_levels(self) -> None:
        self.config = self.window.apply_controls_to_config()
        was_empty = not any(item.is_usable() for item in self.config.random.items)
        existing = {item.identity() for item in self.config.random.items}

        imported: list[RandomPoolItem] = []
        skipped = 0
        for key in sorted(
            (k for k in self.config.levels if k.isdigit()), key=int
        ):
            level = self.config.levels[key]
            if not (level.media or level.sound):
                continue
            item = RandomPoolItem(
                media=level.media,
                sound=level.sound,
                duration_ms=level.duration_ms,
                volume=level.volume,
                scale=level.scale,
                chroma_key=level.chroma_key,
                weight=1.0,
                min_combo=0,
            )
            if item.identity() in existing:
                skipped += 1
                continue
            existing.add(item.identity())
            imported.append(item)

        if not imported:
            self.log(
                f"没有可导入的新条目（{skipped} 条已在池子里）。"
                if skipped
                else "连杀档位里没有已设置的素材，无可导入内容。"
            )
            return

        self.window.append_random_items(imported)
        if was_empty:
            self.window.set_random_enabled(True)
        self.save_config()
        self.log(
            f"已从连杀档位导入 {len(imported)} 条到随机池"
            f"{f'，跳过 {skipped} 条重复' if skipped else ''}"
            f"{'，并自动开启随机播放' if was_empty else ''}。"
        )

    def reset_combo(self) -> None:
        self.combo_count = 0
        self.last_kill_time = 0.0
        self.window.update_combo_display(0)
        self.log("连杀计数已重置。")

    def _on_game_reset(self) -> None:
        if self.combo_count > 0:
            self.log("检测到游戏重置，连杀计数已清零。")
        self.reset_combo()

    def resolve_level(self, combo: int) -> int:
        enabled_levels = sorted(
            int(k)
            for k, v in self.config.levels.items()
            if k.isdigit() and v.enabled
        )
        if not enabled_levels:
            return 1
        matching = [lvl for lvl in enabled_levels if lvl <= combo]
        return max(matching) if matching else min(enabled_levels)

    def play_level(self, level: int) -> None:
        self.config = self.window.apply_controls_to_config()
        level_config = self.config.levels[str(level)]
        if not level_config.enabled:
            return
        self.overlay.play_level(level, level_config, self.config.overlay)
        if level_config.sound:
            self._play_sound(resolve_data_path(level_config.sound), level_config.volume)

    def preview_level(self, level: int) -> None:
        self.log(f"手动预览 {level} 杀。")
        self.play_level(level)

    def start_sequence_preview(self) -> None:
        self.sequence_level = 1
        self._play_next_sequence_level()

    def _play_next_sequence_level(self) -> None:
        max_level = max((int(k) for k in self.config.levels if k.isdigit()), default=5)
        if self.sequence_level > max_level:
            return
        self.preview_level(self.sequence_level)
        self.sequence_level += 1
        QTimer.singleShot(1700, self._play_next_sequence_level)

    # ── 鼠标点击 ─────────────────────────────────────────────────────────

    def _on_mouse_pressed(self) -> None:
        # 仅在监听器运行期间生效
        if self.listener is None or not self.listener.isRunning():
            return

        self.config = self.window.apply_controls_to_config()
        mc = self.config.mouse_click
        if not mc.enabled:
            return

        self._mouse_holding = True
        self._play_mouse_click_once()

        if mc.loop_on_hold:
            interval = max(50, mc.duration_ms)
            self._mouse_loop_timer.setInterval(interval)
            self._mouse_loop_timer.start()

    def _on_mouse_released(self) -> None:
        self._mouse_holding = False
        self._mouse_loop_timer.stop()

    def _on_mouse_loop_tick(self) -> None:
        if not self._mouse_holding:
            self._mouse_loop_timer.stop()
            return
        self._play_mouse_click_once()

    def _play_mouse_click_once(self) -> None:
        self.config = self.window.apply_controls_to_config()
        mc = self.config.mouse_click
        if not mc.enabled:
            return

        self.overlay.play_generic(
            media=mc.media,
            duration_ms=mc.duration_ms,
            chroma_key=mc.chroma_key,
            scale=mc.scale,
            overlay_config=self.config.overlay,
        )
        if mc.sound:
            self._play_sound(resolve_data_path(mc.sound), mc.volume)

    def choose_mouse_media(self) -> None:
        filters = (
            "媒体文件 (*.png *.jpg *.jpeg *.bmp *.webp *.gif "
            "*.mp4 *.webm *.mov *.mkv *.avi)"
        )
        filename, _ = QFileDialog.getOpenFileName(
            self.window, "选择鼠标点击图片或视频", str(Path.home()), filters
        )
        if not filename:
            return
        try:
            stored = self.asset_service.import_media(Path(filename))
            self.window.set_mouse_media_path(stored)
            self.save_config()
            self.log(f"已导入鼠标点击素材：{stored}")
        except Exception as exc:
            self.window.show_error("素材导入失败", str(exc))

    def choose_mouse_sound(self) -> None:
        filters = "音频文件 (*.wav *.mp3 *.ogg *.flac *.m4a)"
        filename, _ = QFileDialog.getOpenFileName(
            self.window, "选择鼠标点击音效", str(Path.home()), filters
        )
        if not filename:
            return
        try:
            stored = self.asset_service.import_audio(Path(filename))
            self.window.set_mouse_sound_path(stored)
            self.save_config()
            self.log(f"已导入鼠标点击音效：{stored}")
        except Exception as exc:
            self.window.show_error("音效导入失败", str(exc))

    # ── 连杀素材文件选择 ──────────────────────────────────────────────────

    def choose_media(self, level: int) -> None:
        filters = (
            "媒体文件 (*.png *.jpg *.jpeg *.bmp *.webp *.gif "
            "*.mp4 *.webm *.mov *.mkv *.avi)"
        )
        filename, _ = QFileDialog.getOpenFileName(
            self.window, f"选择 {level} 杀图片或视频", str(Path.home()), filters
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
        filename, _ = QFileDialog.getOpenFileName(
            self.window, f"选择 {level} 杀音效", str(Path.home()), filters
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
            with log_file.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError:
            pass

    def exit_application(self) -> None:
        self.window.force_close = True
        self.app.quit()

    def shutdown(self) -> None:
        self._mouse_worker.stop()
        self._mouse_loop_timer.stop()
        if self.listener is not None and self.listener.isRunning():
            self.listener.stop()
            self.listener.wait(1200)
        self.audio_engine.shutdown()
        self.audio.stop()
        self.overlay.close_overlay()
        self.tray.hide()
