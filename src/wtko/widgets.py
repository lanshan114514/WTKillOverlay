from __future__ import annotations

from typing import Any

from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .models import LevelConfig, MouseClickConfig


class PositionEditor(QWidget):
    positionChanged = Signal(float, float)

    def __init__(self) -> None:
        super().__init__()
        self.setMinimumSize(640, 360)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.x_ratio = 0.5
        self.y_ratio = 0.28
        self.item_scale = 1.0
        self.dragging = False
        self.drag_offset = QPoint()

    def set_position(self, x_ratio: float, y_ratio: float) -> None:
        self.x_ratio = max(0.0, min(float(x_ratio), 1.0))
        self.y_ratio = max(0.0, min(float(y_ratio), 1.0))
        self.update()

    def set_item_scale(self, scale: float) -> None:
        self.item_scale = max(0.3, min(float(scale), 2.0))
        self.update()

    def item_rect(self) -> QRect:
        w = round(170 * self.item_scale)
        h = round(110 * self.item_scale)
        cx = round(self.width() * self.x_ratio)
        cy = round(self.height() * self.y_ratio)
        return QRect(cx - w // 2, cy - h // 2, w, h)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self.item_rect().contains(event.position().toPoint())
        ):
            self.dragging = True
            self.drag_offset = event.position().toPoint() - self.item_rect().topLeft()
            self.setFocus()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if not self.dragging:
            return
        rect = self.item_rect()
        tl = event.position().toPoint() - self.drag_offset
        self.x_ratio = max(0.0, min((tl.x() + rect.width() / 2) / max(self.width(), 1), 1.0))
        self.y_ratio = max(0.0, min((tl.y() + rect.height() / 2) / max(self.height(), 1), 1.0))
        self.positionChanged.emit(self.x_ratio, self.y_ratio)
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.dragging = False

    def keyPressEvent(self, event: Any) -> None:
        step = 0.002 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 0.008
        changed = True
        if event.key() == Qt.Key.Key_Left:
            self.x_ratio -= step
        elif event.key() == Qt.Key.Key_Right:
            self.x_ratio += step
        elif event.key() == Qt.Key.Key_Up:
            self.y_ratio -= step
        elif event.key() == Qt.Key.Key_Down:
            self.y_ratio += step
        else:
            changed = False
            super().keyPressEvent(event)
        if changed:
            self.x_ratio = max(0.0, min(self.x_ratio, 1.0))
            self.y_ratio = max(0.0, min(self.y_ratio, 1.0))
            self.positionChanged.emit(self.x_ratio, self.y_ratio)
            self.update()

    def paintEvent(self, event: Any) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#111827"))
        border = self.rect().adjusted(1, 1, -2, -2)
        painter.setPen(QPen(QColor("#334155"), 2))
        painter.drawRoundedRect(border, 14, 14)
        painter.setPen(QPen(QColor("#334155"), 1, Qt.PenStyle.DashLine))
        painter.drawLine(self.width() // 2, 0, self.width() // 2, self.height())
        painter.drawLine(0, self.height() // 2, self.width(), self.height() // 2)
        rect = self.item_rect()
        painter.setPen(QPen(QColor("#f8fafc"), 2))
        painter.setBrush(QColor(37, 99, 235, 170))
        painter.drawRoundedRect(rect, 12, 12)
        painter.setPen(QColor("#ffffff"))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "击杀素材\n拖动或方向键微调")


class LevelEditor(QFrame):
    changed = Signal(int)
    chooseMedia = Signal(int)
    chooseSound = Signal(int)
    preview = Signal(int)

    def __init__(self, level: int, config: LevelConfig) -> None:
        super().__init__()
        self.level = level
        self.setObjectName("levelCard")
        self.setFrameShape(QFrame.Shape.StyledPanel)

        root = QVBoxLayout(self)

        header = QHBoxLayout()
        title = QLabel(f"{level} 杀")
        title.setObjectName("cardTitle")
        self.enabled = QCheckBox("启用")
        self.preview_button = QPushButton("预览")
        header.addWidget(title)
        header.addStretch()
        header.addWidget(self.enabled)
        header.addWidget(self.preview_button)
        root.addLayout(header)

        form = QFormLayout()
        self.title_edit = QLineEdit()
        form.addRow("显示名称", self.title_edit)

        media_row = QHBoxLayout()
        self.media_edit = QLineEdit()
        self.media_edit.setReadOnly(True)
        media_button = QPushButton("选择图片/视频")
        media_clear = QPushButton("清除")
        media_row.addWidget(self.media_edit, 1)
        media_row.addWidget(media_button)
        media_row.addWidget(media_clear)
        form.addRow("素材", media_row)

        sound_row = QHBoxLayout()
        self.sound_edit = QLineEdit()
        self.sound_edit.setReadOnly(True)
        sound_button = QPushButton("选择音效")
        sound_clear = QPushButton("清除")
        sound_row.addWidget(self.sound_edit, 1)
        sound_row.addWidget(sound_button)
        sound_row.addWidget(sound_clear)
        form.addRow("音效", sound_row)

        self.duration = QSpinBox()
        self.duration.setRange(0, 10000)
        self.duration.setSuffix(" ms")
        self.duration.setSpecialValueText("自动")
        form.addRow("显示时间", self.duration)

        self.volume = QDoubleSpinBox()
        self.volume.setRange(0.0, 1.0)
        self.volume.setSingleStep(0.05)
        self.volume.setDecimals(2)
        form.addRow("音量", self.volume)

        self.scale = QDoubleSpinBox()
        self.scale.setRange(0.3, 2.0)
        self.scale.setSingleStep(0.05)
        self.scale.setDecimals(2)
        form.addRow("等级缩放", self.scale)

        self.chroma = QComboBox()
        self.chroma.addItem("无", "none")
        self.chroma.addItem("绿幕", "green")
        self.chroma.addItem("黑幕", "black")
        form.addRow("视频抠像", self.chroma)

        root.addLayout(form)
        self.set_config(config)

        self.enabled.toggled.connect(lambda _v: self.changed.emit(self.level))
        self.title_edit.textChanged.connect(lambda _v: self.changed.emit(self.level))
        self.duration.valueChanged.connect(lambda _v: self.changed.emit(self.level))
        self.volume.valueChanged.connect(lambda _v: self.changed.emit(self.level))
        self.scale.valueChanged.connect(lambda _v: self.changed.emit(self.level))
        self.chroma.currentIndexChanged.connect(lambda _v: self.changed.emit(self.level))
        media_button.clicked.connect(lambda: self.chooseMedia.emit(self.level))
        media_clear.clicked.connect(self._clear_media)
        sound_button.clicked.connect(lambda: self.chooseSound.emit(self.level))
        sound_clear.clicked.connect(self._clear_sound)
        self.preview_button.clicked.connect(lambda: self.preview.emit(self.level))

    def set_config(self, config: LevelConfig) -> None:
        self.enabled.setChecked(config.enabled)
        self.title_edit.setText(config.title)
        self.media_edit.setText(config.media)
        self.sound_edit.setText(config.sound)
        self.duration.setValue(config.duration_ms)
        self.volume.setValue(config.volume)
        self.scale.setValue(config.scale)
        index = self.chroma.findData(config.chroma_key)
        self.chroma.setCurrentIndex(max(index, 0))

    def get_config(self) -> LevelConfig:
        return LevelConfig(
            enabled=self.enabled.isChecked(),
            title=self.title_edit.text().strip() or f"{self.level} KILL",
            media=self.media_edit.text().strip(),
            sound=self.sound_edit.text().strip(),
            duration_ms=self.duration.value(),
            volume=self.volume.value(),
            scale=self.scale.value(),
            chroma_key=str(self.chroma.currentData()),
        )

    def set_media_path(self, path: str) -> None:
        self.media_edit.setText(path)
        self.changed.emit(self.level)

    def set_sound_path(self, path: str) -> None:
        self.sound_edit.setText(path)
        self.changed.emit(self.level)

    def _clear_media(self) -> None:
        self.media_edit.setText("")
        self.changed.emit(self.level)

    def _clear_sound(self) -> None:
        self.sound_edit.setText("")
        self.changed.emit(self.level)


class MouseClickEditor(QFrame):
    """鼠标左键点击提示的配置编辑器。"""

    changed = Signal()
    chooseMedia = Signal()
    chooseSound = Signal()
    preview = Signal()

    def __init__(self, config: MouseClickConfig) -> None:
        super().__init__()
        self.setObjectName("levelCard")
        self.setFrameShape(QFrame.Shape.StyledPanel)

        root = QVBoxLayout(self)

        header = QHBoxLayout()
        title = QLabel("鼠标左键点击")
        title.setObjectName("cardTitle")
        self.enabled = QCheckBox("启用")
        preview_btn = QPushButton("预览")
        header.addWidget(title)
        header.addStretch()
        header.addWidget(self.enabled)
        header.addWidget(preview_btn)
        root.addLayout(header)

        form = QFormLayout()

        media_row = QHBoxLayout()
        self.media_edit = QLineEdit()
        self.media_edit.setReadOnly(True)
        media_button = QPushButton("选择图片/视频")
        media_clear = QPushButton("清除")
        media_row.addWidget(self.media_edit, 1)
        media_row.addWidget(media_button)
        media_row.addWidget(media_clear)
        form.addRow("素材", media_row)

        sound_row = QHBoxLayout()
        self.sound_edit = QLineEdit()
        self.sound_edit.setReadOnly(True)
        sound_button = QPushButton("选择音效")
        sound_clear = QPushButton("清除")
        sound_row.addWidget(self.sound_edit, 1)
        sound_row.addWidget(sound_button)
        sound_row.addWidget(sound_clear)
        form.addRow("音效", sound_row)

        self.duration = QSpinBox()
        self.duration.setRange(50, 10000)
        self.duration.setSuffix(" ms")
        form.addRow("每次持续时间", self.duration)

        self.volume = QDoubleSpinBox()
        self.volume.setRange(0.0, 1.0)
        self.volume.setSingleStep(0.05)
        self.volume.setDecimals(2)
        form.addRow("音量", self.volume)

        self.scale = QDoubleSpinBox()
        self.scale.setRange(0.3, 2.0)
        self.scale.setSingleStep(0.05)
        self.scale.setDecimals(2)
        form.addRow("缩放", self.scale)

        self.chroma = QComboBox()
        self.chroma.addItem("无", "none")
        self.chroma.addItem("绿幕", "green")
        self.chroma.addItem("黑幕", "black")
        form.addRow("视频抠像", self.chroma)

        self.loop_check = QCheckBox("按住时循环播放")
        form.addRow("", self.loop_check)

        root.addLayout(form)
        self.set_config(config)

        self.enabled.toggled.connect(lambda _v: self.changed.emit())
        self.duration.valueChanged.connect(lambda _v: self.changed.emit())
        self.volume.valueChanged.connect(lambda _v: self.changed.emit())
        self.scale.valueChanged.connect(lambda _v: self.changed.emit())
        self.chroma.currentIndexChanged.connect(lambda _v: self.changed.emit())
        self.loop_check.toggled.connect(lambda _v: self.changed.emit())
        media_button.clicked.connect(self.chooseMedia.emit)
        media_clear.clicked.connect(self._clear_media)
        sound_button.clicked.connect(self.chooseSound.emit)
        sound_clear.clicked.connect(self._clear_sound)
        preview_btn.clicked.connect(self.preview.emit)

    def set_config(self, config: MouseClickConfig) -> None:
        self.enabled.setChecked(config.enabled)
        self.media_edit.setText(config.media)
        self.sound_edit.setText(config.sound)
        self.duration.setValue(config.duration_ms)
        self.volume.setValue(config.volume)
        self.scale.setValue(config.scale)
        idx = self.chroma.findData(config.chroma_key)
        self.chroma.setCurrentIndex(max(idx, 0))
        self.loop_check.setChecked(config.loop_on_hold)

    def get_config(self) -> MouseClickConfig:
        return MouseClickConfig(
            enabled=self.enabled.isChecked(),
            media=self.media_edit.text().strip(),
            sound=self.sound_edit.text().strip(),
            duration_ms=self.duration.value(),
            volume=self.volume.value(),
            scale=self.scale.value(),
            chroma_key=str(self.chroma.currentData()),
            loop_on_hold=self.loop_check.isChecked(),
        )

    def set_media_path(self, path: str) -> None:
        self.media_edit.setText(path)
        self.changed.emit()

    def set_sound_path(self, path: str) -> None:
        self.sound_edit.setText(path)
        self.changed.emit()

    def _clear_media(self) -> None:
        self.media_edit.setText("")
        self.changed.emit()

    def _clear_sound(self) -> None:
        self.sound_edit.setText("")
        self.changed.emit()
