from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class Comment:
    id: int | None
    feed_id: str
    comment_id: str
    parent_comment_id: str | None
    comment_type: str
    content: str
    note_url: str
    created_at: str | None
    author_id: str | None = None
    scan_status: str = "discovered"
    delete_status: str = "pending"
    discovered_at: str | None = None
    deleted_at: str | None = None
    retry_count: int = 0
    last_error: str | None = None
