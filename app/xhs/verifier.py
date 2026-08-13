from __future__ import annotations

from playwright.sync_api import Page

from app.storage.models import Comment
from app.xhs import selectors


def comment_locator(page: Page, comment_id: str):
    for template in selectors.COMMENT_BY_ID:
        locator = page.locator(template.format(comment_id=comment_id)).first
        try:
            if locator.count() and locator.is_visible(timeout=700):
                return locator
        except Exception:
            continue
    return None


def verify_deleted(page: Page, comment: Comment) -> bool:
    """Verify by stable comment ID absence after a reload, never by click success."""
    page.reload(wait_until="domcontentloaded", timeout=30_000)
    page.wait_for_timeout(1_000)
    return comment_locator(page, comment.comment_id) is None
