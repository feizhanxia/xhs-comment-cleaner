from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, Mock

from app.core.exceptions import OwnershipNotConfirmed, UnsupportedPageState
from app.storage.models import Comment
from app.xhs.deleter import CommentDeleter
from app.xhs.scanner import HistoryScanner


def comment(author_id: str | None = "mine", url: str = "https://www.xiaohongshu.com/explore/n1") -> Comment:
    return Comment(
        id=1, feed_id="n1", comment_id="c1", parent_comment_id=None,
        comment_type="comment", content="x", note_url=url, created_at=None,
        author_id=author_id,
    )


class DeletionSafetyTest(unittest.IsolatedAsyncioTestCase):
    async def test_refuses_mismatched_owner_before_navigation(self) -> None:
        page = Mock()
        with self.assertRaises(OwnershipNotConfirmed):
            await CommentDeleter(page, "mine").delete_comment(comment("someone-else"))
        page.goto.assert_not_called()

    async def test_refuses_missing_owner_before_navigation(self) -> None:
        page = Mock()
        with self.assertRaises(OwnershipNotConfirmed):
            await CommentDeleter(page, "mine").delete_comment(comment(None))
        page.goto.assert_not_called()

    async def test_refuses_non_xhs_url_before_navigation(self) -> None:
        page = Mock()
        with self.assertRaises(UnsupportedPageState):
            await CommentDeleter(page, "mine").delete_comment(comment("mine", "https://example.com/"))
        page.goto.assert_not_called()

    async def test_scanner_refuses_home_feed_instead_of_reporting_zero(self) -> None:
        locator = Mock()
        locator.first = locator
        locator.is_visible = AsyncMock(return_value=False)
        page = Mock()
        page.url = "https://www.xiaohongshu.com/explore"
        page.get_by_text.return_value = locator
        scanner = HistoryScanner(page, Mock(), "mine")

        with self.assertRaisesRegex(UnsupportedPageState, "不会把 0 条误报"):
            await scanner.scan_my_comment_history()


if __name__ == "__main__":
    unittest.main()
