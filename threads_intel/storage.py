from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from .config import DB_PATH
from .models import ProfileSnapshot


def connect(db_path: str = DB_PATH):
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    con.execute("""
    CREATE TABLE IF NOT EXISTS snapshots (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      username TEXT NOT NULL,
      fetched_at TEXT NOT NULL,
      followers INTEGER NOT NULL,
      payload TEXT NOT NULL
    )
    """)
    con.execute("""
    CREATE TABLE IF NOT EXISTS posts (
      username TEXT NOT NULL,
      post_id TEXT,
      url TEXT,
      text TEXT,
      posted_at TEXT,
      likes INTEGER,
      replies INTEGER,
      reposts INTEGER,
      quotes INTEGER,
      reactions INTEGER,
      fetched_at TEXT,
      PRIMARY KEY(username, post_id, text)
    )
    """)
    return con


def save_snapshot(snapshot: ProfileSnapshot, db_path: str = DB_PATH):
    con = connect(db_path)
    with con:
        con.execute(
            "INSERT INTO snapshots(username, fetched_at, followers, payload) VALUES(?,?,?,?)",
            (snapshot.username, snapshot.fetched_at, snapshot.followers, snapshot.model_dump_json()),
        )
        for p in snapshot.posts:
            con.execute("""
            INSERT OR REPLACE INTO posts(username, post_id, url, text, posted_at, likes, replies, reposts, quotes, reactions, fetched_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?)
            """, (p.username, p.post_id, p.url, p.text, p.posted_at, p.likes, p.replies, p.reposts, p.quotes, p.reactions, snapshot.fetched_at))
    con.close()


def _load_snapshot(payload: str) -> ProfileSnapshot | None:
    try:
        return ProfileSnapshot(**json.loads(payload))
    except (json.JSONDecodeError, TypeError, ValueError):
        return None


def latest_snapshot(username: str, db_path: str = DB_PATH) -> ProfileSnapshot | None:
    con = connect(db_path)
    rows = con.execute(
        "SELECT payload FROM snapshots WHERE username=? ORDER BY id DESC",
        (username.strip().lstrip("@").lower(),),
    ).fetchall()
    con.close()
    for row in rows:
        snapshot = _load_snapshot(row["payload"])
        if snapshot:
            return snapshot
    return None


def snapshot_versions(username: str, limit: int = 2, db_path: str = DB_PATH) -> list[ProfileSnapshot]:
    con = connect(db_path)
    rows = con.execute(
        "SELECT payload FROM snapshots WHERE username=? ORDER BY id DESC LIMIT ?",
        (username.strip().lstrip("@").lower(), limit),
    ).fetchall()
    con.close()
    snapshots = []
    for row in rows:
        snapshot = _load_snapshot(row["payload"])
        if snapshot:
            snapshots.append(snapshot)
    return snapshots


def new_posts_since_previous(username: str, db_path: str = DB_PATH) -> list[dict]:
    versions = snapshot_versions(username, limit=2, db_path=db_path)
    if len(versions) < 2:
        return []
    latest, previous = versions[0], versions[1]
    previous_keys = {(post.post_id or post.text[:120]) for post in previous.posts}
    rows = []
    for post in latest.posts:
        key = post.post_id or post.text[:120]
        if key not in previous_keys:
            rows.append(
                {
                    "posted_at": post.posted_at,
                    "likes": post.likes,
                    "comments": post.replies,
                    "reposts": post.reposts,
                    "quotes": post.quotes,
                    "engagement": post.reactions,
                    "text": post.text,
                    "link": post.url,
                }
            )
    return rows


def list_usernames(db_path: str = DB_PATH) -> list[str]:
    con = connect(db_path)
    rows = con.execute("SELECT DISTINCT username FROM snapshots ORDER BY username").fetchall()
    con.close()
    return [row["username"] for row in rows]


def delete_account(username: str, db_path: str = DB_PATH) -> int:
    username = username.strip().lstrip("@").lower()
    if not username:
        return 0
    con = connect(db_path)
    with con:
        snapshot_count = con.execute("DELETE FROM snapshots WHERE username=?", (username,)).rowcount
        post_count = con.execute("DELETE FROM posts WHERE username=?", (username,)).rowcount
    con.close()
    return snapshot_count + post_count


def snapshot_history(username: str, db_path: str = DB_PATH) -> list[dict]:
    con = connect(db_path)
    rows = con.execute(
        """
        SELECT fetched_at, followers, payload
        FROM snapshots
        WHERE username=?
        ORDER BY fetched_at
        """,
        (username.strip().lstrip("@").lower(),),
    ).fetchall()
    con.close()
    history = []
    for row in rows:
        try:
            payload = json.loads(row["payload"])
        except (json.JSONDecodeError, TypeError):
            continue
        posts = payload.get("posts", [])
        reactions = [sum(int(post.get(k, 0) or 0) for k in ("likes", "replies", "reposts", "quotes")) for post in posts]
        history.append(
            {
                "fetched_at": row["fetched_at"],
                "followers": row["followers"],
                "posts_loaded": len(posts),
                "top_reactions": max(reactions, default=0),
            }
        )
    return history


def recent_fetches(limit: int = 20, db_path: str = DB_PATH) -> list[dict]:
    con = connect(db_path)
    rows = con.execute(
        """
        SELECT username, fetched_at, followers, payload
        FROM snapshots
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    con.close()
    logs = []
    for row in rows:
        try:
            payload = json.loads(row["payload"])
        except (json.JSONDecodeError, TypeError):
            payload = {"posts": []}
        logs.append(
            {
                "username": row["username"],
                "fetched_at": row["fetched_at"],
                "followers": row["followers"],
                "posts_loaded": len(payload.get("posts", [])),
            }
        )
    return logs
