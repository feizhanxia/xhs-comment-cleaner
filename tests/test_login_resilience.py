from __future__ import annotations

import unittest
from unittest.mock import Mock

from app.browser.browser_manager import BrowserManager
from app.browser.login_manager import LoginManager
from app.ui.main_window import BrowserWorker
from app.xhs import selectors


class FakeLocator:
    @property
    def first(self):
        return self

    def is_visible(self, timeout=None):
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


class LoginResilienceTest(unittest.TestCase):
    def test_dom_errors_are_treated_as_uncertain_not_raised(self) -> None:
        page = FakePage("https://www.xiaohongshu.com/explore")
        self.assertFalse(LoginManager(page).is_logged_in())

    def test_url_error_is_treated_as_not_logged_in(self) -> None:
        self.assertFalse(LoginManager(ErrorUrlPage()).is_logged_in())

    def test_browser_reselects_live_xhs_tab_after_original_closed(self) -> None:
        manager = BrowserManager(Mock(), Mock())
        manager.page = FakePage("https://www.xiaohongshu.com/", closed=True)
        fallback = FakePage("edge://newtab/")
        xhs = FakePage("https://www.xiaohongshu.com/user/profile/me")
        manager.context = Mock()
        manager.context.pages = [manager.page, fallback, xhs]
        self.assertIs(manager.active_page(), xhs)

    def test_generic_login_word_is_not_a_required_marker(self) -> None:
        self.assertNotIn("登录", selectors.LOGIN_REQUIRED_TEXT)

    def test_worker_converts_unexpected_check_error_to_ui_signal(self) -> None:
        worker = BrowserWorker(Mock(), Mock(), Mock())
        worker._browser = Mock(side_effect=RuntimeError("connection closed"))
        errors: list[str] = []
        states: list[tuple[str, str]] = []
        worker.error.connect(errors.append)
        worker.state_changed.connect(lambda state, text: states.append((state, text)))

        worker.check_login()

        self.assertEqual(len(errors), 1)
        self.assertIn("检查登录状态失败", errors[0])
        self.assertEqual(states[0][0], "ERROR")

    def test_worker_survives_page_closing_during_login_check(self) -> None:
        browser = Mock()
        browser.start.return_value = ErrorUrlPage()
        worker = BrowserWorker(Mock(), Mock(), Mock())
        worker._browser = Mock(return_value=browser)
        errors: list[str] = []
        states: list[tuple[str, str]] = []
        worker.error.connect(errors.append)
        worker.state_changed.connect(lambda state, text: states.append((state, text)))

        worker.check_login()

        self.assertEqual(errors, [])
        self.assertEqual(states[0][0], "LOGIN_REQUIRED")


if __name__ == "__main__":
    unittest.main()
