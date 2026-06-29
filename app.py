from __future__ import annotations

import os
import signal
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from PySide6.QtCore import QCoreApplication
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from wtko.controller import ApplicationController
from wtko.paths import resource_path


def main() -> int:
    QCoreApplication.setOrganizationName("WTKillOverlay")
    QCoreApplication.setApplicationName("WTKillOverlay")

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationDisplayName("战争雷霆击杀提示")

    icon_path = resource_path("resources/app.ico")
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    controller = ApplicationController(app)
    controller.start()

    signal.signal(signal.SIGINT, lambda *_: app.quit())

    os._exit(app.exec())


if __name__ == "__main__":
    raise SystemExit(main())
