from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppPaths:
    root: Path
    profile: Path
    data: Path
    database: Path
    logs: Path
    log_file: Path
    screenshots: Path
    runtime: Path


def get_app_paths() -> AppPaths:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        # Non-Windows is supported for development only.
        base = Path(os.environ.get("XHS_CLEANER_DATA_DIR", Path.home() / ".local" / "share"))
    root = base / "XHSCommentCleaner"
    paths = AppPaths(
        root=root,
        profile=root / "profile",
        data=root / "data",
        database=root / "data" / "data.db",
        logs=root / "logs",
        log_file=root / "logs" / "app.log",
        screenshots=root / "screenshots",
        runtime=root / "runtime",
    )
    for directory in (paths.root, paths.profile, paths.data, paths.logs, paths.screenshots, paths.runtime):
        directory.mkdir(parents=True, exist_ok=True)
    return paths
