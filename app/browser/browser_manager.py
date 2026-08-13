from __future__ import annotations

import logging
from pathlib import Path

from playwright.sync_api import BrowserContext, Page, Playwright, sync_playwright

from app.core.exceptions import EdgeUnavailable

XHS_HOME = "https://www.xiaohongshu.com/"


class BrowserManager:
    """Owns one Playwright instance and one isolated persistent Edge context.

    This object must only be used by the worker thread that created it.
    """

    def __init__(self, profile_dir: Path, logger: logging.Logger):
        self.profile_dir = profile_dir
        self.logger = logger
        self._playwright: Playwright | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None

    def start(self) -> Page:
        if self.page and not self.page.is_closed():
            return self.page
        try:
            self._playwright = sync_playwright().start()
            self.context = self._playwright.chromium.launch_persistent_context(
                user_data_dir=str(self.profile_dir),
                channel="msedge",
                headless=False,
                timeout=30_000,
                no_viewport=True,
                args=["--disable-features=msEdgeSidebarV2"],
            )
            self.context.set_default_timeout(8_000)
            self.context.set_default_navigation_timeout(30_000)
            self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
            return self.page
        except Exception as exc:
            self.close()
            self.logger.exception("action=edge_start result=failed error=%s", type(exc).__name__)
            raise EdgeUnavailable("无法启动 Microsoft Edge。请确认 Microsoft Edge 已正常安装。") from exc

    def open_xhs(self) -> Page:
        page = self.start()
        page.goto(XHS_HOME, wait_until="domcontentloaded")
        page.bring_to_front()
        return page

    def screenshot(self, directory: Path, label: str) -> Path | None:
        if not self.page or self.page.is_closed():
            return None
        from datetime import datetime

        safe_label = "".join(c for c in label if c.isalnum() or c in "_-")[:40]
        path = directory / f"{datetime.now():%Y%m%d_%H%M%S}_{safe_label}.png"
        try:
            self.page.screenshot(path=str(path), full_page=False)
            return path
        except Exception:
            self.logger.exception("action=screenshot result=failed")
            return None

    def close(self) -> None:
        try:
            if self.context:
                self.context.close()
        except Exception:
            self.logger.exception("action=edge_close result=failed")
        finally:
            self.context = None
            self.page = None
        try:
            if self._playwright:
                self._playwright.stop()
        except Exception:
            pass
        finally:
            self._playwright = None
