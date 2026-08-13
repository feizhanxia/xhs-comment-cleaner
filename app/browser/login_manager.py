from __future__ import annotations

from playwright.sync_api import Page

from app.xhs import selectors


class LoginManager:
    def __init__(self, page: Page):
        self.page = page

    def is_logged_in(self) -> bool:
        """Conservative check: login prompts win over weak positive signals."""
        if not self.page.url.startswith("https://www.xiaohongshu.com"):
            return False
        for text in selectors.LOGIN_REQUIRED_TEXT:
            if self.page.get_by_text(text, exact=False).first.is_visible(timeout=500):
                return False
        for locator in selectors.LOGGED_IN_MARKERS:
            if self.page.locator(locator).first.is_visible(timeout=500):
                return True
        return False

    def current_user_id(self) -> str | None:
        for locator in selectors.CURRENT_USER_LINKS:
            element = self.page.locator(locator).first
            try:
                href = element.get_attribute("href", timeout=700)
            except Exception:
                continue
            if href and "/user/profile/" in href:
                return href.split("/user/profile/", 1)[1].split("?", 1)[0].split("/", 1)[0]
        return None
