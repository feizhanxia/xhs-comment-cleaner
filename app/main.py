from __future__ import annotations

import asyncio
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
    if sys.platform == "win32" and hasattr(asyncio, "WindowsProactorEventLoopPolicy"):
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    app = SafeApplication(sys.argv)
    app.setApplicationName("XHSCommentCleaner")
    paths = get_app_paths()
    logger = configure_logging(paths.log_file, debug=os.environ.get("XHS_CLEANER_DEBUG") == "1")
    install_exception_logging(logger, paths.logs / "crash.log", APP_VERSION)
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
    browser_smoke = "--browser-smoke-test" in sys.argv
    browser_smoke_result = {"done": False, "ok": False}
    if browser_smoke:
        def finish_browser_smoke(ok: bool) -> None:
            if browser_smoke_result["done"]:
                return
            browser_smoke_result.update(done=True, ok=ok)
            window.close()

        window.worker.browser_smoke_finished.connect(finish_browser_smoke)
        QTimer.singleShot(300, window.worker.browser_smoke_test)
        QTimer.singleShot(30_000, lambda: finish_browser_smoke(False))
    if "--smoke-test" in sys.argv:
        QTimer.singleShot(300, window.close)
    exit_code = app.exec()
    if browser_smoke:
        return 0 if browser_smoke_result["ok"] else 1
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
