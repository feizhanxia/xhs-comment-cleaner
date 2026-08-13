from __future__ import annotations

import logging
import sys
import threading
import traceback
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path


_crash_stream = None


def configure_logging(log_file: Path, debug: bool = False) -> logging.Logger:
    logger = logging.getLogger("xhs_comment_cleaner")
    logger.setLevel(logging.DEBUG if debug else logging.INFO)
    logger.propagate = False
    if logger.handlers:
        return logger
    handler = RotatingFileHandler(log_file, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    if debug:
        console = logging.StreamHandler()
        console.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
        logger.addHandler(console)
    return logger


def install_exception_logging(logger: logging.Logger, crash_file: Path, version: str = "unknown") -> None:
    """Keep GUI builds diagnosable even when no console is available."""
    global _crash_stream
    _crash_stream = crash_file.open("a", encoding="utf-8", buffering=1)
    _crash_stream.write(
        f"\n=== session {datetime.now().isoformat(timespec='seconds')} version={version} ===\n"
    )

    def handle_exception(exc_type, exc_value, exc_traceback) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        logger.critical(
            "action=uncaught_exception thread=%s error=%s",
            threading.current_thread().name,
            exc_type.__name__,
            exc_info=(exc_type, exc_value, exc_traceback),
        )
        traceback.print_exception(exc_type, exc_value, exc_traceback, file=_crash_stream)

    def handle_thread_exception(args: threading.ExceptHookArgs) -> None:
        handle_exception(args.exc_type, args.exc_value, args.exc_traceback)

    sys.excepthook = handle_exception
    threading.excepthook = handle_thread_exception

    try:
        import faulthandler

        faulthandler.enable(file=_crash_stream, all_threads=True)
    except Exception:
        logger.exception("action=faulthandler_enable result=failed")
