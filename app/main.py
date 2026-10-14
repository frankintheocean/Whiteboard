"""🚪 Start WhiteBoard and protect its local data."""
import os
import sys
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtGui import QIcon
from PySide6.QtCore import QLockFile, QTimer

from storage import Storage, get_data_dir
from main_window import MainWindow
import app_meta
import error_log


def _icon_path() -> str:
    """Resolve the app icon whether running from source or from a
    PyInstaller-frozen bundle (where files are unpacked under sys._MEIPASS)."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base = sys._MEIPASS
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "build", "assets", "whiteboard.ico")


def _install_excepthook():
    """Catch anything that reaches the top of the Qt event loop without
    being handled anywhere else, log it to Diagnostics' error log, and
    let the default handler still run afterward (prints to stderr,
    preserves normal crash behavior) -- this only adds a record of what
    happened, it never suppresses or changes how an unhandled exception
    is otherwise treated."""
    default_hook = sys.excepthook

    def _hook(exc_type, exc_value, exc_tb):
        try:
            error_log.log_error("Unhandled exception", exc_value)
        except Exception:
            pass
        default_hook(exc_type, exc_value, exc_tb)

    sys.excepthook = _hook


def main():
    _install_excepthook()
    app = QApplication(sys.argv)
    app.setApplicationName("WhiteBoard")
    app.setApplicationVersion(app_meta.APP_VERSION)
    # No initial setStyleSheet() call here: MainWindow.__init__ immediately
    # applies the user's actual saved theme via _apply_theme(), so setting
    # the hardcoded default stylesheet first would just be a wasted full
    # QSS parse/apply on every single startup, always instantly overwritten.

    icon_path = _icon_path()
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    try:
        data_dir = get_data_dir()
        lock = QLockFile(os.path.join(data_dir, "whiteboard.lock"))
        # QLockFile still checks whether a recorded process is alive.
        lock.setStaleLockTime(0)
        if not lock.tryLock(0):
            QMessageBox.information(None, "🔒 WhiteBoard is already open",
                "Another WhiteBoard window is using this data folder, or the folder is not writable. Close the other window or check folder permissions.")
            return 1
        storage = Storage(data_dir)
    except OSError as error:
        QMessageBox.critical(None, "🚫 Could not open your data", str(error))
        return 1
    error_log.init(storage.data_dir)
    window = MainWindow(storage)
    if os.path.exists(icon_path):
        window.setWindowIcon(QIcon(icon_path))
    window.show()

    if storage.recovery_messages:
        QTimer.singleShot(0, lambda: QMessageBox.warning(window, "🧰 Data recovery",
            "\n".join(storage.recovery_messages)))
    if "--smoke-test" in sys.argv:
        QTimer.singleShot(400, app.quit)
    code = app.exec()
    lock.unlock()
    return code


if __name__ == "__main__":
    sys.exit(main())
