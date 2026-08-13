from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def configure_logging(log_file: Path, debug: bool = False) -> logging.Logger:
    logger = logging.getLogger("xhs_comment_cleaner")
    logger.setLevel(logging.DEBUG if debug else logging.INFO)
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
