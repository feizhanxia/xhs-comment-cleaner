from __future__ import annotations

import os
import sys

from PySide6.QtCore import QLockFile, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from app.storage.database import Database
from app.ui.main_window import MainWindow
from app.utils.logger import configure_logging
from app.utils.logger import install_exception_logging
from app.utils.paths import get_app_paths
from app.utils.version import APP_VERSION


class SafeApplication(QApplication):
    """Prevent Python exceptions in Qt callbacks from terminating a GUI build."""

    def notify(self, receiver, event) -> bool:
        try:
            return super().notify(receiver, event)
        except Exception:
            sys.excepthook(*sys.exc_info())
            return False


def main() -> int:
    app = SafeApplication(sys.argv)
    app.setApplicationName("XHSCommentCleaner")
    paths = get_app_paths()
    logger = configure_logging(paths.log_file, debug=os.environ.get("XHS_CLEANER_DEBUG") == "1")
    install_exception_logging(logger, paths.logs / "crash.log")
    logger.info(
        "action=app_start version=%s platform=%s frozen=%s",
        APP_VERSION, sys.platform, bool(getattr(sys, "frozen", False)),
    )
    lock = QLockFile(str(paths.root / "app.lock"))
    # A crashed process must not leave an unrecoverable permanent lock.
    lock.setStaleLockTime(30_000)
    if not lock.tryLock(100):
        QMessageBox.information(None, "程序已在运行", "小红书评论清理工具已经在运行。")
        return 1
    database = Database(paths.database)
    window = MainWindow(paths, database, logger)
    window.show()
    if "--smoke-test" in sys.argv:
        QTimer.singleShot(300, window.close)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
