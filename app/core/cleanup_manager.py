from __future__ import annotations

import logging
import random
import threading
from collections.abc import Awaitable, Callable

from app.core.exceptions import (
    CommentNotFound,
    LoginExpired,
    OwnershipNotConfirmed,
    RiskControlDetected,
    UnsupportedPageState,
)
from app.core.state import CleanupState
from app.storage.database import Database
from app.xhs.deleter import CommentDeleter


class CleanupManager:
    def __init__(
        self,
        database: Database,
        deleter: CommentDeleter,
        logger: logging.Logger,
        on_state: Callable[[CleanupState, str], None],
        on_progress: Callable[[dict[str, int]], None],
        wait_ms: Callable[[int], Awaitable[None]],
        screenshot: Callable[[str], Awaitable[object]],
    ):
        self.database = database
        self.deleter = deleter
        self.logger = logger
        self.on_state = on_state
        self.on_progress = on_progress
        self.wait_ms = wait_ms
        self.screenshot = screenshot
        self._pause_requested = threading.Event()

    def pause(self) -> None:
        self._pause_requested.set()

    async def run(self) -> None:
        self._pause_requested.clear()
        self.on_state(CleanupState.DELETING, "正在逐条删除")
        while not self._pause_requested.is_set():
            comment = self.database.get_next_pending()
            if comment is None:
                counts = self.database.counts()
                state = CleanupState.FINISHED if not counts["failed"] else CleanupState.READY
                self.on_state(state, "当前扫描到的评论已全部处理")
                self.on_progress(counts)
                return
            assert comment.id is not None
            try:
                await self.deleter.delete_comment(comment)
                self.database.mark_deleted(comment.id)
                self.logger.info(
                    "action=delete feed_id=%s comment_id=%s result=deleted retry_count=%d",
                    comment.feed_id, comment.comment_id, comment.retry_count,
                )
            except OwnershipNotConfirmed as exc:
                self.database.mark_skipped(comment.id, str(exc))
                self.logger.warning("action=delete comment_id=%s result=skipped error=ownership", comment.comment_id)
            except (RiskControlDetected, LoginExpired) as exc:
                state = CleanupState.BLOCKED if isinstance(exc, RiskControlDetected) else CleanupState.LOGIN_REQUIRED
                self.on_state(state, str(exc))
                return
            except UnsupportedPageState as exc:
                self.database.mark_attempt_failed(comment.id, str(exc))
                await self.screenshot("unsupported_page")
                self.on_state(CleanupState.PAUSED, "小红书页面结构发生变化，任务已暂停")
                return
            except Exception as exc:
                status = self.database.mark_attempt_failed(comment.id, str(exc))
                await self.screenshot("delete_failed")
                self.logger.exception(
                    "action=delete comment_id=%s result=%s retry_count=%d error=%s",
                    comment.comment_id, status, comment.retry_count + 1, type(exc).__name__,
                )
            self.on_progress(self.database.counts())
            if not self._pause_requested.is_set():
                await self.wait_ms(random.randint(2_000, 5_000))
        self.on_state(CleanupState.PAUSED, "已暂停，将从下一条继续")
