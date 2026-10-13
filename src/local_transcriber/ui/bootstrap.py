"""Lazy GUI launch; import/CLI help do not start Qt, SQL or GPU."""

from pathlib import Path


def run_gui(env_file: Path | None = None) -> int:
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
