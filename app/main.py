from __future__ import annotations

import os
import sys

from PySide6.QtCore import QLockFile, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from app.storage.database import Database
from app.ui.main_window import MainWindow
from app.utils.logger import configure_logging
from app.utils.paths import get_app_paths


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("XHSCommentCleaner")
    paths = get_app_paths()
    logger = configure_logging(paths.log_file, debug=os.environ.get("XHS_CLEANER_DEBUG") == "1")
    lock = QLockFile(str(paths.root / "app.lock"))
    lock.setStaleLockTime(0)
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
