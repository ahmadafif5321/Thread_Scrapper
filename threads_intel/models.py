from __future__ import annotations

from datetime import datetime, timezone
from pydantic import BaseModel, Field


class ThreadPost(BaseModel):
    username: str
    post_id: str = ""
    url: str = ""
    text: str = ""
    posted_at: str = ""
    likes: int = 0
    replies: int = 0
    reposts: int = 0
    quotes: int = 0

    @property
    def reactions(self) -> int:
        return self.likes + self.replies + self.reposts + self.quotes


class ProfileSnapshot(BaseModel):
    username: str
    followers: int = 0
    posts_loaded: int = 0
    fetched_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    posts: list[ThreadPost] = Field(default_factory=list)
