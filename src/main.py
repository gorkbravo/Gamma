from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from src.ui.plot_theme import apply_terminal_mpl_theme
from src.utils.logging_config import setup_logging


def main() -> int:
    load_dotenv()
    setup_logging()
    os.environ.setdefault("QT_API", "pyside6")
    use_software = os.getenv("MQW_WEBENGINE_SOFTWARE", "0")
    if use_software == "1":
        # Avoid conflicting flags like --disable-gpu with swiftshader.
        os.environ.setdefault(
            "QTWEBENGINE_CHROMIUM_FLAGS",
            "--use-gl=swiftshader --disable-gpu-compositing --disable-gpu-rasterization",
        )
        os.environ.setdefault("QT_OPENGL", "software")
    else:
        # Favor D3D11 on Windows hybrids to avoid ANGLE/GPU context issues.
        os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--use-angle=d3d11 --ignore-gpu-blocklist")
        os.environ.setdefault("QT_OPENGL", "desktop")

    # Required by QtWebEngine on some platforms to avoid blank views.
    from PySide6.QtCore import QCoreApplication, Qt
    from PySide6.QtWidgets import QApplication

    QCoreApplication.setAttribute(Qt.AA_ShareOpenGLContexts)
    if use_software == "1":
        QCoreApplication.setAttribute(Qt.AA_UseSoftwareOpenGL)
    # Ensure QtWebEngine is initialized before creating the QApplication.
    from PySide6 import QtWebEngineWidgets  # noqa: F401
    from src.ui.main_window import MainWindow

    app = QApplication(sys.argv)
    apply_terminal_mpl_theme()
    qss_path = Path(__file__).resolve().parent / "ui" / "theme.qss"
    if qss_path.exists():
        app.setStyleSheet(qss_path.read_text(encoding="utf-8"))
    window = MainWindow()
    window.resize(1200, 800)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
