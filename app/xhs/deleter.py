from __future__ import annotations

from playwright.async_api import Page

from app.core.exceptions import (
    CommentNotFound,
    DeleteVerificationFailed,
    OwnershipNotConfirmed,
    UnsupportedPageState,
)
from app.storage.models import Comment
from app.xhs import selectors
from app.xhs.risk_detector import detect_risk_control
from app.xhs.verifier import comment_locator, verify_deleted


class CommentDeleter:
    def __init__(self, page: Page, current_user_id: str):
        self.page = page
        self.current_user_id = current_user_id

    async def delete_comment(self, comment: Comment) -> None:
        if not comment.note_url.startswith("https://www.xiaohongshu.com/"):
            raise UnsupportedPageState("评论链接不是小红书网页地址")
        if not comment.author_id or comment.author_id != self.current_user_id:
            raise OwnershipNotConfirmed("无法确认这条评论属于当前账号")

        await self.page.goto(comment.note_url, wait_until="domcontentloaded", timeout=30_000)
        await detect_risk_control(self.page)
        target = await comment_locator(self.page, comment.comment_id)
        if target is None:
            raise CommentNotFound("无法按评论 ID 定位目标评论")

        author = target.locator(selectors.COMMENT_AUTHOR_LINK).first
        href = await author.get_attribute("href", timeout=3_000)
        if not href or f"/user/profile/{self.current_user_id}" not in href:
            raise OwnershipNotConfirmed("页面中的评论作者与当前账号不一致")

        menu = None
        for name in selectors.COMMENT_MENU_BUTTONS:
            candidate = target.get_by_role("button", name=name, exact=False).first
            if await candidate.count() and await candidate.is_visible(timeout=500):
                menu = candidate
                break
        if menu is None:
            raise UnsupportedPageState("找不到目标评论的操作菜单")
        await menu.click(timeout=5_000)

        delete = self.page.get_by_role("menuitem", name=selectors.DELETE_TEXT, exact=True).last
        if not await delete.is_visible(timeout=3_000):
            raise UnsupportedPageState("找不到删除按钮")
        await delete.click(timeout=5_000)

        for label in selectors.CONFIRM_DELETE_TEXT:
            confirm = self.page.get_by_role("button", name=label, exact=True).last
            try:
                if await confirm.is_visible(timeout=700):
                    await confirm.click(timeout=5_000)
                    break
            except Exception:
                continue

        await self.page.wait_for_timeout(1_000)
        await detect_risk_control(self.page)
        if not await verify_deleted(self.page, comment):
            raise DeleteVerificationFailed("删除后仍能定位到目标评论")
