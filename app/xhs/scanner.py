from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterator
from urllib.parse import quote

from playwright.async_api import Page, Response

from app.storage.database import Database
from app.storage.models import Comment
from app.xhs.risk_detector import detect_risk_control


class HistoryScanner:
    """Discover owned comments exposed by the normal web notification pages.

    Xiaohongshu Web has no sent-comment history. The notification feeds can still
    expose an owned target comment after someone replies to or likes it. We navigate
    the normal notification UI, observe its own JSON responses, and only accept a
    target whose embedded author ID exactly matches the logged-in user.
    """

    NOTIFICATION_URL = "https://www.xiaohongshu.com/notification"
    NOTIFICATION_API_PARTS = ("/api/sns/web/v1/you/mentions", "/api/sns/web/v1/you/likes")

    def __init__(
        self,
        page: Page,
        database: Database,
        current_user_id: str,
        on_discovered: Callable[[int], None] | None = None,
        should_pause: Callable[[], bool] | None = None,
    ):
        self.page = page
        self.database = database
        self.current_user_id = current_user_id
        self.on_discovered = on_discovered or (lambda _count: None)
        self.should_pause = should_pause or (lambda: False)
        self._seen: set[tuple[str, str]] = set()
        self._response_error: str | None = None
        self._response_count = 0

    @property
    def response_count(self) -> int:
        return self._response_count

    @property
    def response_error(self) -> str | None:
        return self._response_error

    async def scan_my_comment_history(self, max_stagnant_rounds: int = 5) -> tuple[int, bool]:
        response_tasks: set[asyncio.Task] = set()

        def schedule_response(response: Response) -> None:
            task = asyncio.create_task(self._on_response(response))
            response_tasks.add(task)
            task.add_done_callback(response_tasks.discard)

        self.page.on("response", schedule_response)
        discovered_before = self.database.counts()["discovered"]
        try:
            await self.page.goto(self.NOTIFICATION_URL, wait_until="domcontentloaded", timeout=30_000)
            await self.page.wait_for_timeout(1_500)
            await detect_risk_control(self.page)
            await self._scan_current_notification_tab(max_stagnant_rounds)

            likes_tab = self.page.get_by_text("赞和收藏", exact=True).first
            try:
                if await likes_tab.is_visible(timeout=2_000):
                    await likes_tab.click(timeout=5_000)
                    await self.page.wait_for_timeout(1_000)
                    await self._scan_current_notification_tab(max_stagnant_rounds)
            except Exception:
                # Mentions remain useful even if the second tab changed or vanished.
                self._response_error = "LikesTabUnavailable"

            if response_tasks:
                await asyncio.gather(*tuple(response_tasks), return_exceptions=True)
            total = self.database.counts()["discovered"]
            # Notification feeds are a useful recovery source, never a complete
            # history of sent comments. Preserve that distinction in persisted state.
            self.database.set_state("scan_complete", "false")
            self.database.set_state("scan_source", "web_notifications")
            self.database.set_state("last_scanned_url", self.page.url)
            return total - discovered_before, False
        finally:
            self.page.remove_listener("response", schedule_response)
            if response_tasks:
                await asyncio.gather(*response_tasks, return_exceptions=True)

    async def _scan_current_notification_tab(self, max_stagnant_rounds: int) -> None:
        stagnant = 0
        while stagnant < max_stagnant_rounds and not self.should_pause():
            before_comments = self.database.counts()["discovered"]
            before_responses = self._response_count
            await self.page.mouse.wheel(0, 1800)
            await self.page.wait_for_timeout(1_500)
            await detect_risk_control(self.page)
            changed = (
                self.database.counts()["discovered"] != before_comments
                or self._response_count != before_responses
            )
            stagnant = 0 if changed else stagnant + 1

    async def _on_response(self, response: Response) -> None:
        if not any(part in response.url for part in self.NOTIFICATION_API_PARTS):
            return
        content_type = response.headers.get("content-type", "")
        if "json" not in content_type or not response.ok:
            return
        try:
            payload = await response.json()
            self._response_count += 1
            data = payload.get("data", payload) if isinstance(payload, dict) else {}
            messages = data.get("message_list", data.get("messageList", []))
            if not isinstance(messages, list):
                return
            for message in messages:
                if not isinstance(message, dict):
                    continue
                for comment in self._comments_from_notification(message):
                    self._persist(comment)
        except Exception as exc:
            # Response parsing is opportunistic; never interrupt the page request.
            self._response_error = type(exc).__name__

    def _comments_from_notification(self, message: dict) -> list[Comment]:
        item = message.get("item_info") or message.get("itemInfo") or message.get("note_info") or {}
        if not isinstance(item, dict):
            return []
        feed_id = self._first(item, "id", "note_id", "noteId")
        if not feed_id:
            return []
        token = self._first(item, "xsec_token", "xsecToken")
        note_url = f"https://www.xiaohongshu.com/explore/{feed_id}"
        if token:
            note_url += f"?xsec_token={quote(str(token), safe='')}&xsec_source=pc_notification"

        comment_roots = [
            value for key, value in message.items()
            if "comment" in key.lower() and isinstance(value, (dict, list))
        ]
        candidates: list[dict] = []
        for root in comment_roots:
            for mapping in self._walk_dicts(root):
                author_id = self._nested_first(
                    mapping, ("user_id", "userId", "userid", "author_id", "authorId")
                )
                comment_id = self._first(mapping, "comment_id", "commentId", "id")
                if not author_id or str(author_id) != self.current_user_id or not comment_id:
                    continue
                # Notification/message IDs also use `id`. Require comment-shaped fields
                # so an owned user object or notification record can never become a delete target.
                if not any(key in mapping for key in (
                    "content", "comment_content", "target_comment", "targetComment",
                    "root_comment_id", "parent_comment_id",
                )):
                    continue
                candidates.append(mapping)

        comments: list[Comment] = []
        local_seen: set[str] = set()
        for mapping in candidates:
            comment_id = str(self._first(mapping, "comment_id", "commentId", "id"))
            if comment_id in local_seen:
                continue
            local_seen.add(comment_id)
            parent_id = self._first(
                mapping, "parent_comment_id", "parentCommentId", "root_comment_id", "rootCommentId"
            )
            content = self._first(mapping, "content", "text", "comment_content", "commentContent") or ""
            created_at = self._first(mapping, "created_at", "create_time", "createTime", "time")
            separator = "&" if "?" in note_url else "?"
            targeted_note_url = (
                f"{note_url}{separator}top_comment_id={quote(comment_id, safe='')}"
            )
            comments.append(Comment(
                id=None,
                feed_id=str(feed_id),
                comment_id=comment_id,
                parent_comment_id=str(parent_id) if parent_id else None,
                comment_type="reply" if parent_id else "comment",
                content=str(content),
                note_url=targeted_note_url,
                created_at=str(created_at) if created_at else None,
                author_id=self.current_user_id,
            ))
        return comments

    def _persist(self, comment: Comment) -> None:
        key = (comment.feed_id, comment.comment_id)
        if key in self._seen:
            return
        self._seen.add(key)
        self.database.upsert_comment(comment)
        self.on_discovered(self.database.counts()["discovered"])

    @staticmethod
    def _walk_dicts(value: object) -> Iterator[dict]:
        if isinstance(value, dict):
            yield value
            for child in value.values():
                yield from HistoryScanner._walk_dicts(child)
        elif isinstance(value, list):
            for child in value:
                yield from HistoryScanner._walk_dicts(child)

    @staticmethod
    def _first(item: dict, *keys: str):
        for key in keys:
            if key in item and item[key] not in (None, ""):
                return item[key]
        return None

    @staticmethod
    def _nested_first(item: dict, keys: tuple[str, ...]):
        direct = HistoryScanner._first(item, *keys)
        if direct:
            return direct
        for container_key in ("user", "user_info", "userInfo", "author", "owner", "comment_user"):
            container = item.get(container_key)
            if isinstance(container, dict):
                value = HistoryScanner._first(container, *keys, "id")
                if value:
                    return value
        return None
