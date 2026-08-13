from __future__ import annotations

import unittest
import asyncio
import threading
from pathlib import Path
from unittest.mock import AsyncMock, Mock

from app.browser.browser_manager import BrowserManager
from app.browser.login_manager import LoginManager
from app.ui.main_window import BrowserWorker
from app.xhs import selectors


class FakeLocator:
    @property
    def first(self):
        return self

    async def is_visible(self, timeout=None):
        raise RuntimeError("page changed while checking")


class FakePage:
    def __init__(self, url: str, closed: bool = False):
        self.url = url
        self.closed = closed

    def is_closed(self) -> bool:
        return self.closed

    def get_by_text(self, *args, **kwargs):
        return FakeLocator()

    def locator(self, *args, **kwargs):
        return FakeLocator()


class ErrorUrlPage:
    @property
    def url(self):
        raise RuntimeError("closed")


class LoginResilienceTest(unittest.IsolatedAsyncioTestCase):
    async def test_dom_errors_are_treated_as_uncertain_not_raised(self) -> None:
        page = FakePage("https://www.xiaohongshu.com/explore")
        self.assertFalse(await LoginManager(page).is_logged_in())

    async def test_url_error_is_treated_as_not_logged_in(self) -> None:
        self.assertFalse(await LoginManager(ErrorUrlPage()).is_logged_in())

    async def test_browser_reselects_live_xhs_tab_after_original_closed(self) -> None:
        manager = BrowserManager(Mock(), Mock())
        manager.page = FakePage("https://www.xiaohongshu.com/", closed=True)
        fallback = FakePage("edge://newtab/")
        xhs = FakePage("https://www.xiaohongshu.com/user/profile/me")
        manager.context = Mock()
        manager.context.pages = [manager.page, fallback, xhs]
        self.assertIs(await manager.active_page(), xhs)

    async def test_browser_restores_xhs_after_all_pages_were_closed(self) -> None:
        manager = BrowserManager(Mock(), Mock())
        blank = FakePage("about:blank")

        async def goto(url, **_kwargs):
            blank.url = url

        blank.goto = AsyncMock(side_effect=goto)
        blank.bring_to_front = AsyncMock()
        manager.start = AsyncMock(return_value=blank)

        page = await manager.ensure_xhs_page()

        self.assertIs(page, blank)
        blank.goto.assert_awaited_once_with(
            "https://www.xiaohongshu.com/", wait_until="domcontentloaded"
        )
        blank.bring_to_front.assert_awaited_once()

    async def test_generic_login_word_is_not_a_required_marker(self) -> None:
        self.assertNotIn("登录", selectors.LOGIN_REQUIRED_TEXT)

    async def test_worker_converts_unexpected_check_error_to_ui_signal(self) -> None:
        worker = BrowserWorker(Mock(), Mock(), Mock())
        worker._browser = Mock(side_effect=RuntimeError("connection closed"))
        errors: list[str] = []
        states: list[tuple[str, str]] = []
        worker.error.connect(errors.append)
        worker.state_changed.connect(lambda state, text: states.append((state, text)))
        try:
            await worker._check_login()
            self.assertEqual(len(errors), 1)
            self.assertIn("检查登录状态失败", errors[0])
            self.assertEqual(states[0][0], "ERROR")
        finally:
            worker.shutdown_and_wait()

    async def test_worker_survives_page_closing_during_login_check(self) -> None:
        browser = Mock()
        browser.ensure_xhs_page = AsyncMock(return_value=ErrorUrlPage())
        worker = BrowserWorker(Mock(), Mock(), Mock())
        worker._browser = Mock(return_value=browser)
        errors: list[str] = []
        states: list[tuple[str, str]] = []
        worker.error.connect(errors.append)
        worker.state_changed.connect(lambda state, text: states.append((state, text)))
        try:
            await worker._check_login()
            self.assertEqual(errors, [])
            self.assertEqual(states[0][0], "LOGIN_REQUIRED")
        finally:
            worker.shutdown_and_wait()

    async def test_production_code_does_not_import_sync_playwright(self) -> None:
        sources = "\n".join(path.read_text(encoding="utf-8") for path in Path("app").rglob("*.py"))
        self.assertNotIn("playwright.sync_api", sources)

    async def test_browser_commands_run_serially_on_dedicated_async_thread(self) -> None:
        worker = BrowserWorker(Mock(), Mock(), Mock())
        done = threading.Event()
        order: list[str] = []
        active = 0
        max_active = 0
        thread_ids: list[int] = []

        async def operation(name: str) -> None:
            nonlocal active, max_active
            active += 1
            max_active = max(max_active, active)
            thread_ids.append(threading.get_ident())
            order.append(f"{name}:start")
            await asyncio.sleep(0.02)
            order.append(f"{name}:end")
            active -= 1
            if name == "second":
                done.set()

        try:
            worker._submit(lambda: operation("first"))
            worker._submit(lambda: operation("second"))
            self.assertTrue(done.wait(2))
            self.assertEqual(max_active, 1)
            self.assertEqual(order, ["first:start", "first:end", "second:start", "second:end"])
            self.assertTrue(all(thread_id == worker._thread.ident for thread_id in thread_ids))
        finally:
            worker.shutdown_and_wait()


if __name__ == "__main__":
    unittest.main()
