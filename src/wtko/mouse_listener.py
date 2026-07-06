from __future__ import annotations

import threading

from PySide6.QtCore import QObject, Signal


class MouseClickWorker(QObject):
    """在后台线程中监听全局鼠标左键，通过 Qt 信号通知主线程。"""

    leftPressed = Signal()
    leftReleased = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._listener: object | None = None
        self._thread: threading.Thread | None = None
        self._running = False

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._listener is not None:
            try:
                self._listener.stop()  # type: ignore[union-attr]
            except Exception:
                pass
        self._listener = None

    def _run(self) -> None:
        try:
            from pynput import mouse

            def on_click(
                x: int,
                y: int,
                button: mouse.Button,
                pressed: bool,
            ) -> None:
                if not self._running:
                    return False  # 停止监听
                if button == mouse.Button.left:
                    if pressed:
                        self.leftPressed.emit()
                    else:
                        self.leftReleased.emit()

            with mouse.Listener(on_click=on_click) as listener:
                self._listener = listener
                listener.join()
        except Exception:
            pass
