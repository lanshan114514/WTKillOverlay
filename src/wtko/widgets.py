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

from .models import LevelConfig, MouseClickConfig, RandomConfig, RandomPoolItem


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


class RandomItemEditor(QFrame):
    """随机池里的一条素材。素材和音效可以只填一样。"""

    changed = Signal()
    chooseMedia = Signal(object)
    chooseSound = Signal(object)
    preview = Signal(object)
    removeRequested = Signal(object)

    def __init__(self, index: int, config: RandomPoolItem) -> None:
        super().__init__()
        self.setObjectName("levelCard")
        self.setFrameShape(QFrame.Shape.StyledPanel)

        root = QVBoxLayout(self)

        header = QHBoxLayout()
        self.title = QLabel(f"#{index + 1}")
        self.title.setObjectName("cardTitle")
        preview_button = QPushButton("预览")
        remove_button = QPushButton("删除这条")
        header.addWidget(self.title)
        header.addStretch()
        header.addWidget(preview_button)
        header.addWidget(remove_button)
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
        form.addRow("缩放", self.scale)

        self.chroma = QComboBox()
        self.chroma.addItem("无", "none")
        self.chroma.addItem("绿幕", "green")
        self.chroma.addItem("黑幕", "black")
        form.addRow("视频抠像", self.chroma)

        self.weight = QDoubleSpinBox()
        self.weight.setRange(0.0, 20.0)
        self.weight.setSingleStep(0.5)
        self.weight.setDecimals(1)
        self.weight.setToolTip("相对概率。0 表示这条暂时不参与抽取。")
        form.addRow("权重", self.weight)

        self.min_combo = QSpinBox()
        self.min_combo.setRange(0, 999)
        self.min_combo.setSpecialValueText("不限")
        self.min_combo.setToolTip("连杀数达到这个值之后，这条才参与抽取。")
        form.addRow("连杀下限", self.min_combo)

        root.addLayout(form)
        self.set_config(config)

        preview_button.clicked.connect(lambda: self.preview.emit(self))
        remove_button.clicked.connect(lambda: self.removeRequested.emit(self))
        media_button.clicked.connect(lambda: self.chooseMedia.emit(self))
        media_clear.clicked.connect(self._clear_media)
        sound_button.clicked.connect(lambda: self.chooseSound.emit(self))
        sound_clear.clicked.connect(self._clear_sound)

        for signal in (
            self.duration.valueChanged,
            self.volume.valueChanged,
            self.scale.valueChanged,
            self.weight.valueChanged,
            self.min_combo.valueChanged,
            self.chroma.currentIndexChanged,
        ):
            signal.connect(lambda *_: self.changed.emit())

    def set_title_index(self, index: int) -> None:
        self.title.setText(f"#{index + 1}")

    def set_config(self, config: RandomPoolItem) -> None:
        self.media_edit.setText(config.media)
        self.sound_edit.setText(config.sound)
        self.duration.setValue(config.duration_ms)
        self.volume.setValue(config.volume)
        self.scale.setValue(config.scale)
        self.weight.setValue(config.weight)
        self.min_combo.setValue(config.min_combo)
        index = self.chroma.findData(config.chroma_key)
        self.chroma.setCurrentIndex(max(index, 0))

    def get_config(self) -> RandomPoolItem:
        return RandomPoolItem(
            media=self.media_edit.text().strip(),
            sound=self.sound_edit.text().strip(),
            duration_ms=self.duration.value(),
            volume=self.volume.value(),
            scale=self.scale.value(),
            chroma_key=str(self.chroma.currentData()),
            weight=self.weight.value(),
            min_combo=self.min_combo.value(),
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


class RandomPoolEditor(QFrame):
    """随机播放页：启用开关 + 池子条目列表。"""

    changed = Signal()
    chooseMedia = Signal(int)
    chooseSound = Signal(int)
    preview = Signal(int)

    def __init__(self, config: RandomConfig) -> None:
        super().__init__()
        self.setObjectName("levelCard")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.editors: list[RandomItemEditor] = []

        root = QVBoxLayout(self)

        header = QHBoxLayout()
        title = QLabel("随机播放")
        title.setObjectName("cardTitle")
        self.enabled = QCheckBox("启用（击杀时随机抽取，替代连杀素材）")
        header.addWidget(title)
        header.addStretch()
        header.addWidget(self.enabled)
        root.addLayout(header)

        tip = QLabel(
            "池子里放几条素材/音效，每次击杀按权重随机抽一条，连杀数达到【连杀下限】的条目才参与抽取。\n"
            "素材和音效可以只填一样。权重 0 表示暂时不参与。"
        )
        tip.setWordWrap(True)
        tip.setObjectName("muted")
        root.addWidget(tip)

        self.avoid_repeat = QCheckBox("避免连续重复：抽到和上一炮同一条时换一条")
        root.addWidget(self.avoid_repeat)

        self.items_layout = QVBoxLayout()
        root.addLayout(self.items_layout)

        self.set_config(config)

        self.enabled.toggled.connect(lambda _v: self.changed.emit())
        self.avoid_repeat.toggled.connect(lambda _v: self.changed.emit())

    def set_config(self, config: RandomConfig) -> None:
        self.enabled.setChecked(config.enabled)
        self.avoid_repeat.setChecked(config.avoid_repeat)
        self.clear_items()
        for item in config.items:
            self.add_item(item)
        if not config.items:
            self.add_item(RandomPoolItem())

    def get_config(self) -> RandomConfig:
        return RandomConfig(
            enabled=self.enabled.isChecked(),
            items=[editor.get_config() for editor in self.editors],
            avoid_repeat=self.avoid_repeat.isChecked(),
        )

    def clear_items(self) -> None:
        for editor in list(self.editors):
            self._detach(editor)
        self.editors.clear()

    def add_item(self, config: RandomPoolItem | None = None) -> RandomItemEditor:
        editor = RandomItemEditor(len(self.editors), config or RandomPoolItem())
        editor.changed.connect(self.changed.emit)
        editor.chooseMedia.connect(self._relay_media)
        editor.chooseSound.connect(self._relay_sound)
        editor.preview.connect(self._relay_preview)
        editor.removeRequested.connect(self._remove_editor)
        self.items_layout.addWidget(editor)
        self.editors.append(editor)
        return editor

    def remove_last(self) -> None:
        if not self.editors:
            return
        self._remove_editor(self.editors[-1])

    def set_media_path(self, index: int, path: str) -> None:
        if 0 <= index < len(self.editors):
            self.editors[index].set_media_path(path)

    def set_sound_path(self, index: int, path: str) -> None:
        if 0 <= index < len(self.editors):
            self.editors[index].set_sound_path(path)

    def _detach(self, editor: RandomItemEditor) -> None:
        self.items_layout.removeWidget(editor)
        editor.setParent(None)  # type: ignore[arg-type]
        editor.deleteLater()

    def _remove_editor(self, editor: RandomItemEditor) -> None:
        if editor not in self.editors:
            return
        self.editors.remove(editor)
        self._detach(editor)
        for position, remaining in enumerate(self.editors):
            remaining.set_title_index(position)
        self.changed.emit()

    def _index_of(self, editor: RandomItemEditor) -> int:
        try:
            return self.editors.index(editor)
        except ValueError:
            return -1

    def _relay_media(self, editor: RandomItemEditor) -> None:
        index = self._index_of(editor)
        if index >= 0:
            self.chooseMedia.emit(index)

    def _relay_sound(self, editor: RandomItemEditor) -> None:
        index = self._index_of(editor)
        if index >= 0:
            self.chooseSound.emit(index)

    def _relay_preview(self, editor: RandomItemEditor) -> None:
        index = self._index_of(editor)
        if index >= 0:
            self.preview.emit(index)
