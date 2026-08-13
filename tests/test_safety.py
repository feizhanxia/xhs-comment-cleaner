from __future__ import annotations

import unittest
from unittest.mock import Mock

from app.core.exceptions import OwnershipNotConfirmed, UnsupportedPageState
from app.storage.models import Comment
from app.xhs.deleter import CommentDeleter


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


if __name__ == "__main__":
    unittest.main()
