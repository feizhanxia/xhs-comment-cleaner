from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.storage.database import Database
from app.storage.models import Comment


def sample(comment_id: str = "c1") -> Comment:
    return Comment(
        id=None,
        feed_id="f1",
        comment_id=comment_id,
        parent_comment_id=None,
        comment_type="comment",
        content="测试评论",
        note_url="https://www.xiaohongshu.com/explore/f1",
        created_at=None,
        author_id="u1",
    )


class DatabaseTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.database = Database(Path(self.temp.name) / "data.db")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_upsert_deduplicates_feed_and_comment(self) -> None:
        self.database.upsert_comment(sample())
        self.database.upsert_comment(sample())
        self.assertEqual(self.database.counts()["discovered"], 1)

    def test_resume_keeps_deleted_and_returns_pending(self) -> None:
        self.database.upsert_comment(sample("c1"))
        self.database.upsert_comment(sample("c2"))
        pending = self.database.get_next_pending()
        assert pending and pending.id
        self.database.mark_deleted(pending.id)

        reopened = Database(self.database.path)
        counts = reopened.counts()
        self.assertEqual(counts["deleted"], 1)
        self.assertEqual(counts["pending"], 1)
        self.assertNotEqual(reopened.get_next_pending().comment_id, pending.comment_id)

    def test_three_failed_attempts_becomes_failed(self) -> None:
        self.database.upsert_comment(sample())
        row = self.database.get_next_pending()
        assert row and row.id
        self.assertEqual(self.database.mark_attempt_failed(row.id, "x"), "pending")
        self.assertEqual(self.database.mark_attempt_failed(row.id, "x"), "pending")
        self.assertEqual(self.database.mark_attempt_failed(row.id, "x"), "failed")
        self.assertEqual(self.database.counts()["failed"], 1)

    def test_state_persists(self) -> None:
        self.database.set_state("scan_complete", "false")
        self.assertEqual(Database(self.database.path).get_state("scan_complete"), "false")


if __name__ == "__main__":
    unittest.main()
