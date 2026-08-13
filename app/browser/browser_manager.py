from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from playwright.async_api import BrowserContext, Page, Playwright, async_playwright

from app.core.exceptions import EdgeUnavailable

XHS_HOME = "https://www.xiaohongshu.com/"


class BrowserManager:
    """Own one async Playwright instance in one dedicated asyncio thread."""

    def __init__(self, profile_dir: Path, logger: logging.Logger, headless: bool = False):
        self.profile_dir = profile_dir
        self.logger = logger
        self.headless = headless
        self._playwright: Playwright | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None

    async def start(self) -> Page:
        if self.context:
            try:
                return await self.active_page()
            except Exception:
                self.logger.exception("action=edge_recover result=relaunch")
                await self.close()
        try:
            self._playwright = await async_playwright().start()
            self.context = await self._playwright.chromium.launch_persistent_context(
                user_data_dir=str(self.profile_dir),
                channel="msedge",
                headless=self.headless,
                timeout=30_000,
                no_viewport=True,
                args=["--disable-features=msEdgeSidebarV2"],
            )
            self.context.set_default_timeout(8_000)
            self.context.set_default_navigation_timeout(30_000)
            self.page = await self.active_page()
            self.logger.info("action=edge_start result=success pages=%d api=async", len(self.context.pages))
            return self.page
        except Exception as exc:
            await self.close()
            self.logger.exception("action=edge_start result=failed error=%s", type(exc).__name__)
            raise EdgeUnavailable("无法启动 Microsoft Edge。请确认 Microsoft Edge 已正常安装。") from exc

    async def active_page(self) -> Page:
        if not self.context:
            raise RuntimeError("Edge context is not running")
        pages = [page for page in self.context.pages if not page.is_closed()]
        for page in reversed(pages):
            try:
                if page.url.startswith(XHS_HOME):
                    self.page = page
                    return page
            except Exception:
                continue
        if pages:
            self.page = pages[-1]
            return self.page
        self.page = await self.context.new_page()
        return self.page

    async def open_xhs(self) -> Page:
        page = await self.start()
        await page.goto(XHS_HOME, wait_until="domcontentloaded")
        await page.bring_to_front()
        return page

    async def screenshot(self, directory: Path, label: str) -> Path | None:
        if not self.page or self.page.is_closed():
            return None
        safe_label = "".join(c for c in label if c.isalnum() or c in "_-")[:40]
        path = directory / f"{datetime.now():%Y%m%d_%H%M%S}_{safe_label}.png"
        try:
            await self.page.screenshot(path=str(path), full_page=False)
            return path
        except Exception:
            self.logger.exception("action=screenshot result=failed")
            return None

    async def close(self) -> None:
        try:
            if self.context:
                await self.context.close()
        except Exception:
            self.logger.exception("action=edge_close result=failed")
        finally:
            self.context = None
            self.page = None
        try:
            if self._playwright:
                await self._playwright.stop()
        except Exception:
            self.logger.exception("action=playwright_stop result=failed")
        finally:
            self._playwright = None
