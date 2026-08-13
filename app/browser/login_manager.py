from __future__ import annotations

from playwright.async_api import Page

from app.xhs import selectors


class LoginManager:
    def __init__(self, page: Page):
        self.page = page

    async def is_logged_in(self) -> bool:
        try:
            current_url = self.page.url
        except Exception:
            return False
        if not current_url.startswith("https://www.xiaohongshu.com"):
            return False
        for text in selectors.LOGIN_REQUIRED_TEXT:
            if await self._text_visible(text):
                return False
        for locator in selectors.LOGGED_IN_MARKERS:
            if await self._locator_visible(locator):
                return True
        return False

    async def _text_visible(self, text: str) -> bool:
        try:
            return await self.page.get_by_text(text, exact=False).first.is_visible(timeout=500)
        except Exception:
            return False

    async def _locator_visible(self, locator: str) -> bool:
        try:
            return await self.page.locator(locator).first.is_visible(timeout=500)
        except Exception:
            return False

    async def current_user_id(self) -> str | None:
        for locator in selectors.CURRENT_USER_LINKS:
            element = self.page.locator(locator).first
            try:
                href = await element.get_attribute("href", timeout=700)
            except Exception:
                continue
            if href and "/user/profile/" in href:
                return href.split("/user/profile/", 1)[1].split("?", 1)[0].split("/", 1)[0]
        return None
