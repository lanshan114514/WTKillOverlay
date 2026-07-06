from __future__ import annotations

from typing import Any

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtGui import QCloseEvent, QDesktopServices
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .models import AppConfig, MouseClickConfig
from .paths import app_data_dir
from .widgets import LevelEditor, MouseClickEditor, PositionEditor


class MainWindow(QMainWindow):
    startRequested = Signal()
    stopRequested = Signal()
    saveRequested = Signal()
    previewRequested = Signal(int)
    sequenceRequested = Signal()
    chooseMediaRequested = Signal(int)
    chooseSoundRequested = Signal(int)
    exitRequested = Signal()
    resetComboRequested = Signal()
    chooseMouseMediaRequested = Signal()
    chooseMouseSoundRequested = Signal()
    previewMouseClickRequested = Signal()

    def __init__(self, config: AppConfig) -> None:
        super().__init__()
        self.config = config
        self.force_close = False
        self._loading = True

        self.setWindowTitle("战争雷霆击杀提示")
        self.resize(1120, 760)
        self.setMinimumSize(920, 650)

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        self._build_dashboard()
        self._build_levels()
        self._build_mouse_click()
        self._build_position()
        self._build_settings()
        self._build_logs()

        self._load_config_to_controls()
        self._loading = False

        self.auto_save_timer = QTimer(self)
        self.auto_save_timer.setSingleShot(True)
        self.auto_save_timer.timeout.connect(self.saveRequested.emit)

    # ── 标签页构建 ─────────────────────────────────────────────────────────

    def _build_dashboard(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)

        title = QLabel("WTKillOverlay")
        title.setObjectName("pageTitle")
        subtitle = QLabel("关注B站升仙的黄老仙谢谢喵~")
        subtitle.setObjectName("muted")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        status_box = QGroupBox("运行状态")
        status_layout = QGridLayout(status_box)
        self.connection_status = QLabel("未启动")
        self.listener_status = QLabel("已停止")
        self.last_message = QLabel("暂无")
        self.last_message.setWordWrap(True)
        self.combo_display = QLabel("0")
        self.combo_display.setObjectName("comboDisplay")
        status_layout.addWidget(QLabel("8111 接口"), 0, 0)
        status_layout.addWidget(self.connection_status, 0, 1)
        status_layout.addWidget(QLabel("监听器"), 1, 0)
        status_layout.addWidget(self.listener_status, 1, 1)
        status_layout.addWidget(QLabel("当前连杀"), 2, 0)
        status_layout.addWidget(self.combo_display, 2, 1)
        status_layout.addWidget(QLabel("最近 HUD 消息"), 3, 0)
        status_layout.addWidget(self.last_message, 3, 1)
        layout.addWidget(status_box)

        buttons = QHBoxLayout()
        self.start_button = QPushButton("启动监听")
        self.start_button.setObjectName("primaryButton")
        self.stop_button = QPushButton("停止监听")
        preview_one = QPushButton("预览一杀")
        sequence = QPushButton("演示 1→N")
        self.reset_combo_button = QPushButton("重置连杀")
        buttons.addWidget(self.start_button)
        buttons.addWidget(self.stop_button)
        buttons.addWidget(preview_one)
        buttons.addWidget(sequence)
        buttons.addWidget(self.reset_combo_button)
        buttons.addStretch()
        layout.addLayout(buttons)

        notice = QLabel("注：使用无边框全屏或窗口化。")
        notice.setWordWrap(True)
        notice.setObjectName("notice")
        layout.addWidget(notice)
        layout.addStretch()

        self.start_button.clicked.connect(self.startRequested.emit)
        self.stop_button.clicked.connect(self.stopRequested.emit)
        preview_one.clicked.connect(lambda: self.previewRequested.emit(1))
        sequence.clicked.connect(self.sequenceRequested.emit)
        self.reset_combo_button.clicked.connect(self.resetComboRequested.emit)

        self.tabs.addTab(page, "控制台")

    def _build_levels(self) -> None:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        layout = QVBoxLayout(container)

        kw_box = QGroupBox("击杀关键词")
        kw_layout = QVBoxLayout(kw_box)
        kw_hint = QLabel("每行一个关键词，用于判断 HUD 消息是否为本人击杀。")
        kw_hint.setWordWrap(True)
        kw_hint.setObjectName("muted")
        kw_layout.addWidget(kw_hint)
        self.kill_keywords_edit = QTextEdit()
        self.kill_keywords_edit.setPlaceholderText("每行一个关键词")
        self.kill_keywords_edit.setMaximumHeight(140)
        kw_layout.addWidget(self.kill_keywords_edit)
        layout.addWidget(kw_box)

        intro = QLabel("每个连杀等级可使用不同图片、GIF、视频与音效。")
        intro.setWordWrap(True)
        intro.setObjectName("muted")
        layout.addWidget(intro)

        self._levels_inner_layout = QVBoxLayout()
        layout.addLayout(self._levels_inner_layout)

        level_btn_row = QHBoxLayout()
        add_level_btn = QPushButton("＋ 添加连杀等级")
        del_level_btn = QPushButton("－ 删除最后一级")
        level_btn_row.addWidget(add_level_btn)
        level_btn_row.addWidget(del_level_btn)
        level_btn_row.addStretch()
        layout.addLayout(level_btn_row)

        layout.addStretch()
        scroll.setWidget(container)
        self.tabs.addTab(scroll, "连杀素材")

        self.level_editors: dict[int, LevelEditor] = {}
        sorted_keys = sorted(
            (int(k) for k in self.config.levels.keys() if k.isdigit()),
            key=int,
        )
        if not sorted_keys:
            sorted_keys = [1]
        for n in sorted_keys:
            from .models import _default_level
            cfg = self.config.levels.get(str(n), _default_level(n))
            self._add_level_editor(n, cfg)

        add_level_btn.clicked.connect(self._add_level)
        del_level_btn.clicked.connect(self._remove_last_level)
        self.kill_keywords_edit.textChanged.connect(lambda: self.schedule_save())

    def _add_level_editor(self, level: int, config: Any) -> None:
        editor = LevelEditor(level, config)
        editor.changed.connect(lambda _l: self.schedule_save())
        editor.chooseMedia.connect(self.chooseMediaRequested.emit)
        editor.chooseSound.connect(self.chooseSoundRequested.emit)
        editor.preview.connect(self.previewRequested.emit)
        self._levels_inner_layout.addWidget(editor)
        self.level_editors[level] = editor

    def _add_level(self) -> None:
        next_n = max(self.level_editors.keys(), default=0) + 1
        from .models import _default_level
        self._add_level_editor(next_n, _default_level(next_n))
        self.schedule_save()

    def _remove_last_level(self) -> None:
        if len(self.level_editors) <= 1:
            return
        last = max(self.level_editors.keys())
        editor = self.level_editors.pop(last)
        self._levels_inner_layout.removeWidget(editor)
        editor.setParent(None)  # type: ignore[arg-type]
        editor.deleteLater()
        self.config.levels.pop(str(last), None)
        self.schedule_save()

    def _build_mouse_click(self) -> None:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        layout = QVBoxLayout(container)

        intro = QLabel(
            "单击鼠标左键触发一次图标/音效；按住左键则按【每次持续时间】循环播放。\n"
            "图标位置和大小使用【位置与显示】页的全局设置，可通过【缩放】单独调整。"
        )
        intro.setWordWrap(True)
        intro.setObjectName("muted")
        layout.addWidget(intro)

        self.mouse_click_editor = MouseClickEditor(self.config.mouse_click)
        self.mouse_click_editor.changed.connect(self.schedule_save)
        self.mouse_click_editor.chooseMedia.connect(self.chooseMouseMediaRequested.emit)
        self.mouse_click_editor.chooseSound.connect(self.chooseMouseSoundRequested.emit)
        self.mouse_click_editor.preview.connect(self.previewMouseClickRequested.emit)
        layout.addWidget(self.mouse_click_editor)

        layout.addStretch()
        scroll.setWidget(container)
        self.tabs.addTab(scroll, "鼠标点击")

    def _build_position(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)

        self.position_editor = PositionEditor()
        layout.addWidget(self.position_editor, 1)

        controls = QGridLayout()

        self.screen_combo = QComboBox()
        self.refresh_screens()

        self.x_spin = QDoubleSpinBox()
        self.x_spin.setRange(0.0, 100.0)
        self.x_spin.setSuffix("%")
        self.x_spin.setDecimals(1)

        self.y_spin = QDoubleSpinBox()
        self.y_spin.setRange(0.0, 100.0)
        self.y_spin.setSuffix("%")
        self.y_spin.setDecimals(1)

        self.base_size_spin = QSpinBox()
        self.base_size_spin.setRange(120, 1400)
        self.base_size_spin.setSuffix(" px")

        self.global_scale_spin = QDoubleSpinBox()
        self.global_scale_spin.setRange(0.3, 2.0)
        self.global_scale_spin.setSingleStep(0.05)

        self.opacity_spin = QDoubleSpinBox()
        self.opacity_spin.setRange(0.1, 1.0)
        self.opacity_spin.setSingleStep(0.05)

        self.fade_in_spin = QSpinBox()
        self.fade_in_spin.setRange(0, 2000)
        self.fade_in_spin.setSuffix(" ms")
        self.fade_in_spin.setSpecialValueText("关闭")

        self.fade_out_spin = QSpinBox()
        self.fade_out_spin.setRange(0, 2000)
        self.fade_out_spin.setSuffix(" ms")
        self.fade_out_spin.setSpecialValueText("关闭")

        actual_preview = QPushButton("在实际屏幕预览一杀")
        reset = QPushButton("恢复默认位置")

        controls.addWidget(QLabel("显示器"), 0, 0)
        controls.addWidget(self.screen_combo, 0, 1)
        controls.addWidget(QLabel("X"), 0, 2)
        controls.addWidget(self.x_spin, 0, 3)
        controls.addWidget(QLabel("Y"), 0, 4)
        controls.addWidget(self.y_spin, 0, 5)

        controls.addWidget(QLabel("基础尺寸"), 1, 0)
        controls.addWidget(self.base_size_spin, 1, 1)
        controls.addWidget(QLabel("全局缩放"), 1, 2)
        controls.addWidget(self.global_scale_spin, 1, 3)
        controls.addWidget(QLabel("透明度"), 1, 4)
        controls.addWidget(self.opacity_spin, 1, 5)

        controls.addWidget(QLabel("渐入时长"), 2, 0)
        controls.addWidget(self.fade_in_spin, 2, 1)
        controls.addWidget(QLabel("渐出时长"), 2, 2)
        controls.addWidget(self.fade_out_spin, 2, 3)

        controls.addWidget(actual_preview, 3, 0, 1, 3)
        controls.addWidget(reset, 3, 3, 1, 3)
        layout.addLayout(controls)

        self.position_editor.positionChanged.connect(self._editor_position_changed)
        self.x_spin.valueChanged.connect(self._spin_position_changed)
        self.y_spin.valueChanged.connect(self._spin_position_changed)
        self.screen_combo.currentIndexChanged.connect(lambda _v: self.schedule_save())
        self.base_size_spin.valueChanged.connect(lambda _v: self.schedule_save())
        self.global_scale_spin.valueChanged.connect(self._global_scale_changed)
        self.opacity_spin.valueChanged.connect(lambda _v: self.schedule_save())
        self.fade_in_spin.valueChanged.connect(lambda _v: self.schedule_save())
        self.fade_out_spin.valueChanged.connect(lambda _v: self.schedule_save())
        actual_preview.clicked.connect(lambda: self.previewRequested.emit(1))
        reset.clicked.connect(self._reset_position)

        self.tabs.addTab(page, "位置与显示")

    def _build_settings(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)

        form_box = QGroupBox("游戏监听")
        form = QFormLayout(form_box)

        self.player_name_edit = QLineEdit()
        self.player_name_edit.setPlaceholderText("填写游戏中显示的完整昵称")
        self.base_url_edit = QLineEdit()
        self.poll_spin = QSpinBox()
        self.poll_spin.setRange(80, 2000)
        self.poll_spin.setSuffix(" ms")

        self.combo_timeout_spin = QSpinBox()
        self.combo_timeout_spin.setRange(500, 30000)
        self.combo_timeout_spin.setSuffix(" ms")

        self.infinite_combo_check = QCheckBox("无限（游戏结束/手动重置）")
        self.infinite_combo_check.toggled.connect(
            lambda checked: self.combo_timeout_spin.setEnabled(not checked)
        )

        combo_row = QHBoxLayout()
        combo_row.addWidget(self.combo_timeout_spin)
        combo_row.addWidget(self.infinite_combo_check)

        form.addRow("玩家昵称", self.player_name_edit)
        form.addRow("8111 地址", self.base_url_edit)
        form.addRow("轮询间隔", self.poll_spin)
        form.addRow("连杀时间窗", combo_row)

        layout.addWidget(form_box)

        general_box = QGroupBox("程序行为")
        general_layout = QVBoxLayout(general_box)
        self.minimize_tray_check = QCheckBox("关闭主窗口时最小化到系统托盘")
        self.auto_start_listener_check = QCheckBox("程序启动后自动监听")
        general_layout.addWidget(self.minimize_tray_check)
        general_layout.addWidget(self.auto_start_listener_check)
        layout.addWidget(general_box)

        save_button = QPushButton("立即保存设置")
        save_button.setObjectName("primaryButton")
        save_button.clicked.connect(self.saveRequested.emit)
        layout.addWidget(save_button)
        layout.addStretch()

        for widget_signal in (
            self.player_name_edit.textChanged,
            self.base_url_edit.textChanged,
            self.poll_spin.valueChanged,
            self.combo_timeout_spin.valueChanged,
            self.infinite_combo_check.toggled,
            self.minimize_tray_check.toggled,
            self.auto_start_listener_check.toggled,
        ):
            widget_signal.connect(lambda *_: self.schedule_save())

        self.tabs.addTab(page, "设置")

    def _build_logs(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)

        self.log_edit = QTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        layout.addWidget(self.log_edit, 1)

        buttons = QHBoxLayout()
        clear = QPushButton("清空界面日志")
        open_folder = QPushButton("打开数据目录")
        buttons.addWidget(clear)
        buttons.addWidget(open_folder)
        buttons.addStretch()
        layout.addLayout(buttons)

        clear.clicked.connect(self.log_edit.clear)
        open_folder.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(app_data_dir())))
        )

        self.tabs.addTab(page, "日志")

    # ── 加载 / 保存 ─────────────────────────────────────────────────────────

    def _load_config_to_controls(self) -> None:
        config = self.config

        self.player_name_edit.setText(config.game.player_name)
        self.base_url_edit.setText(config.game.base_url)
        self.poll_spin.setValue(config.game.poll_interval_ms)
        self.kill_keywords_edit.setPlainText("\n".join(config.game.kill_keywords))
        self.combo_timeout_spin.setValue(config.combo.timeout_ms)
        self.infinite_combo_check.setChecked(config.combo.infinite_timeout)
        self.combo_timeout_spin.setEnabled(not config.combo.infinite_timeout)
        self.minimize_tray_check.setChecked(config.general.minimize_to_tray)
        self.auto_start_listener_check.setChecked(config.general.start_listening_on_launch)

        self.screen_combo.setCurrentIndex(
            max(0, min(config.overlay.screen_index, self.screen_combo.count() - 1))
        )
        self.x_spin.setValue(config.overlay.x_ratio * 100)
        self.y_spin.setValue(config.overlay.y_ratio * 100)
        self.base_size_spin.setValue(config.overlay.base_size_px)
        self.global_scale_spin.setValue(config.overlay.global_scale)
        self.opacity_spin.setValue(config.overlay.opacity)
        self.fade_in_spin.setValue(config.overlay.fade_in_ms)
        self.fade_out_spin.setValue(config.overlay.fade_out_ms)

        self.position_editor.set_position(config.overlay.x_ratio, config.overlay.y_ratio)
        self.position_editor.set_item_scale(config.overlay.global_scale)

    def refresh_screens(self) -> None:
        self.screen_combo.clear()
        for index, screen in enumerate(QApplication.screens()):
            g = screen.geometry()
            self.screen_combo.addItem(
                f"{index + 1}: {screen.name()} ({g.width()}×{g.height()})"
            )

    def apply_controls_to_config(self) -> AppConfig:
        self.config.game.player_name = self.player_name_edit.text().strip()
        self.config.game.base_url = self.base_url_edit.text().strip().rstrip("/")
        self.config.game.poll_interval_ms = self.poll_spin.value()
        self.config.game.kill_keywords = [
            line.strip()
            for line in self.kill_keywords_edit.toPlainText().splitlines()
            if line.strip()
        ]

        self.config.combo.timeout_ms = self.combo_timeout_spin.value()
        self.config.combo.infinite_timeout = self.infinite_combo_check.isChecked()

        self.config.overlay.screen_index = max(self.screen_combo.currentIndex(), 0)
        self.config.overlay.x_ratio = self.x_spin.value() / 100
        self.config.overlay.y_ratio = self.y_spin.value() / 100
        self.config.overlay.base_size_px = self.base_size_spin.value()
        self.config.overlay.global_scale = self.global_scale_spin.value()
        self.config.overlay.opacity = self.opacity_spin.value()
        self.config.overlay.fade_in_ms = self.fade_in_spin.value()
        self.config.overlay.fade_out_ms = self.fade_out_spin.value()

        self.config.general.minimize_to_tray = self.minimize_tray_check.isChecked()
        self.config.general.start_listening_on_launch = (
            self.auto_start_listener_check.isChecked()
        )

        current_keys = {str(n) for n in self.level_editors}
        for key in list(self.config.levels.keys()):
            if key not in current_keys:
                del self.config.levels[key]
        for level, editor in self.level_editors.items():
            self.config.levels[str(level)] = editor.get_config()

        self.config.mouse_click = self.mouse_click_editor.get_config()

        return self.config

    def schedule_save(self) -> None:
        if not self._loading and hasattr(self, "auto_save_timer"):
            self.auto_save_timer.start(450)

    # ── 状态更新 ─────────────────────────────────────────────────────────

    def set_connection_status(self, connected: bool, detail: str) -> None:
        self.connection_status.setText("已连接" if connected else "未连接")
        self.connection_status.setProperty("connected", connected)
        self.connection_status.style().unpolish(self.connection_status)
        self.connection_status.style().polish(self.connection_status)
        if detail:
            self.connection_status.setToolTip(detail)

    def set_listener_running(self, running: bool) -> None:
        self.listener_status.setText("运行中" if running else "已停止")
        self.start_button.setEnabled(not running)
        self.stop_button.setEnabled(running)

    def set_last_message(self, message: str) -> None:
        self.last_message.setText(message)

    def update_combo_display(self, count: int) -> None:
        self.combo_display.setText(str(count))

    def append_log(self, text: str) -> None:
        self.log_edit.append(text)

    def set_media_path(self, level: int, path: str) -> None:
        if level in self.level_editors:
            self.level_editors[level].set_media_path(path)

    def set_sound_path(self, level: int, path: str) -> None:
        if level in self.level_editors:
            self.level_editors[level].set_sound_path(path)

    def set_mouse_media_path(self, path: str) -> None:
        self.mouse_click_editor.set_media_path(path)

    def set_mouse_sound_path(self, path: str) -> None:
        self.mouse_click_editor.set_sound_path(path)

    # ── 位置编辑 ─────────────────────────────────────────────────────────

    def _editor_position_changed(self, x_ratio: float, y_ratio: float) -> None:
        self.x_spin.blockSignals(True)
        self.y_spin.blockSignals(True)
        self.x_spin.setValue(x_ratio * 100)
        self.y_spin.setValue(y_ratio * 100)
        self.x_spin.blockSignals(False)
        self.y_spin.blockSignals(False)
        self.schedule_save()

    def _spin_position_changed(self, _value: float) -> None:
        self.position_editor.set_position(
            self.x_spin.value() / 100, self.y_spin.value() / 100
        )
        self.schedule_save()

    def _global_scale_changed(self, value: float) -> None:
        self.position_editor.set_item_scale(value)
        self.schedule_save()

    def _reset_position(self) -> None:
        self.x_spin.setValue(50.0)
        self.y_spin.setValue(28.0)
        self.global_scale_spin.setValue(1.0)
        self.opacity_spin.setValue(1.0)
        self.schedule_save()

    def closeEvent(self, event: QCloseEvent) -> None:
        if not self.force_close and self.config.general.minimize_to_tray:
            self.hide()
            event.ignore()
            return
        if not self.force_close:
            self.exitRequested.emit()
        event.accept()

    def show_error(self, title: str, message: str) -> None:
        QMessageBox.critical(self, title, message)

    def show_info(self, title: str, message: str) -> None:
        QMessageBox.information(self, title, message)
