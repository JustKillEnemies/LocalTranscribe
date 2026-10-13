"""Lazy GUI launch; import/CLI help do not start Qt, SQL or GPU."""

import os
from pathlib import Path


class QtPrivacy:
    """Scoped bootstrap policy: no native media metadata dumps or nested network protocols."""

    def __init__(self) -> None:
        self.previous = {
            key: os.environ.get(key)
            for key in ("QT_FFMPEG_DEBUG", "QT_LOGGING_RULES", "QT_FFMPEG_PROTOCOL_WHITELIST")
        }
        os.environ["QT_FFMPEG_DEBUG"] = "0"
        os.environ["QT_FFMPEG_PROTOCOL_WHITELIST"] = "file"
        os.environ["QT_LOGGING_RULES"] = "*.multimedia.*=false"
        from PySide6.QtCore import QLoggingCategory, qInstallMessageHandler

        from local_transcriber.infrastructure.diagnostics import AuditEvent, audit

        QLoggingCategory.setFilterRules("*.multimedia.*=false")

        def diagnostic(kind, context, message):
            # Never forward opaque Qt text, paths, metadata or a traceback to the journal.
            try:
                audit(AuditEvent.DIAGNOSTIC)
            except Exception:
                # Do not raise across a C++ callback or fall back to printing opaque text.
                return

        self.handler = diagnostic
        self.original_handler = qInstallMessageHandler(self.handler)

    def close(self) -> None:
        from PySide6.QtCore import QLoggingCategory, qInstallMessageHandler

        qInstallMessageHandler(self.original_handler)
        for key, value in self.previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        QLoggingCategory.setFilterRules(self.previous["QT_LOGGING_RULES"] or "")


def run_gui(env_file: Path | None = None) -> int:
    privacy = QtPrivacy()
    from PySide6.QtCore import QCoreApplication, QEvent, Qt
    from PySide6.QtGui import QColor, QPalette
    from PySide6.QtWidgets import QApplication

    from local_transcriber.infrastructure.desktop_backend import DesktopService
    from local_transcriber.ui.bridge import DesktopBridge
    from local_transcriber.ui.window import MainWindow

    app = QApplication([])
    app.setApplicationName("LocalTranscribe")
    app.setQuitOnLastWindowClosed(False)
    app.setStyle("Fusion")
    palette = QPalette()
    for role, color in (
        (QPalette.ColorRole.Window, "#1c2028"),
        (QPalette.ColorRole.WindowText, "#e6ebf2"),
        (QPalette.ColorRole.Base, "#141820"),
        (QPalette.ColorRole.AlternateBase, "#242a35"),
        (QPalette.ColorRole.Text, "#e6ebf2"),
        (QPalette.ColorRole.PlaceholderText, "#8793a5"),
        (QPalette.ColorRole.Button, "#303847"),
        (QPalette.ColorRole.ButtonText, "#e6ebf2"),
        (QPalette.ColorRole.Highlight, "#3677bd"),
        (QPalette.ColorRole.HighlightedText, "#ffffff"),
    ):
        palette.setColor(role, QColor(color))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor("#8793a5"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor("#8793a5"))
    app.setPalette(palette)
    bridge = DesktopBridge(lambda path: DesktopService(path), env_file)
    window = MainWindow(bridge)
    bridge.closed.connect(app.quit, Qt.ConnectionType.QueuedConnection)
    window.show()
    bridge.start()
    try:
        return app.exec()
    finally:
        bridge.request_close()
        bridge.wait_closed()
        window.deleteLater()
        bridge.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        privacy.close()
