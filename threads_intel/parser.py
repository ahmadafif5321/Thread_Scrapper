from __future__ import annotations

import json
import re
from bs4 import BeautifulSoup
from .models import ProfileSnapshot, ThreadPost


def _walk(obj):
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from _walk(v)
    elif isinstance(obj, list):
        for x in obj:
            yield from _walk(x)


def _to_int(value) -> int:
    if value is None:
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    s = str(value).replace(",", "").strip().lower()
    mult = 1
    if s.endswith("k"):
        mult, s = 1000, s[:-1]
    elif s.endswith("m"):
        mult, s = 1_000_000, s[:-1]
    try:
        return int(float(s) * mult)
    except Exception:
        return 0


def _extract_json_objects(html: str) -> list[dict | list]:
    soup = BeautifulSoup(html, "html.parser")
    candidates: list[dict | list] = []

    decoder = json.JSONDecoder()

    def try_add(raw: str):
        raw = raw.strip()
        if not raw:
            return

        # Direct JSON script
        if raw.startswith("{") or raw.startswith("["):
            try:
                candidates.append(json.loads(raw))
                return
            except Exception:
                pass

        # Scan JSON fragments around useful keys.
        useful_tokens = [
            '{"require"',
            '{"__bbox"',
            '{"data"',
            '{"props"',
            '{"user"',
            '{"thread_items"',
            '{"thread"',
            '{"post"',
        ]

        starts = set()
        for token in useful_tokens:
            idx = raw.find(token)
            while idx != -1:
                starts.add(idx)
                idx = raw.find(token, idx + 1)

        # Fallback: scan near common Threads/Relay words only.
        for marker in ["follower_count", "like_count", "reply_count", "thread_items", "caption"]:
            idx = raw.find(marker)
            while idx != -1:
                left = raw.rfind("{", 0, idx)
                if left != -1:
                    starts.add(left)
                idx = raw.find(marker, idx + 1)

        for start in sorted(starts):
            try:
                obj, _ = decoder.raw_decode(raw[start:])
                if isinstance(obj, (dict, list)):
                    candidates.append(obj)
            except Exception:
                continue

    for script in soup.find_all("script"):
        raw = script.string or script.get_text() or ""
        try_add(raw)

    return candidates


def _guess_followers(all_dicts: list[dict]) -> int:
    best = 0
    keys = ("follower_count", "followers_count", "followerCount", "followers")
    for d in all_dicts:
        for k in keys:
            if k in d:
                val = d[k]
                if isinstance(val, dict):
                    val = val.get("count") or val.get("value")
                best = max(best, _to_int(val))
    # fallback from rendered text
    return best


def _get_text_from_dict(d: dict) -> str:
    for key in ("text", "caption", "accessibility_caption"):
        val = d.get(key)
        if isinstance(val, str) and len(val.strip()) > 5:
            return val.strip()
        if isinstance(val, dict):
            for kk in ("text", "value"):
                if isinstance(val.get(kk), str):
                    return val[kk].strip()
    return ""


def _extract_posts(username: str, all_dicts: list[dict], limit: int) -> list[ThreadPost]:
    posts: dict[str, ThreadPost] = {}
    for d in all_dicts:
        text = _get_text_from_dict(d)
        if not text or len(text) < 8:
            continue

        # avoid profile bio / app metadata noise
        if text.lower().startswith(("threads", "log in", "sign up")):
            continue

        code = d.get("code") or d.get("shortcode") or d.get("pk") or d.get("id") or ""
        post_id = str(code)[:80]
        url = ""
        if d.get("url") and "threads" in str(d.get("url")):
            url = str(d.get("url"))
        elif post_id:
            url = f"https://www.threads.com/@{username}/post/{post_id}" if not post_id.isdigit() else f"https://www.threads.com/@{username}"

        likes = _to_int(d.get("like_count") or d.get("likeCount") or d.get("likes"))
        replies = _to_int(d.get("reply_count") or d.get("replyCount") or d.get("direct_reply_count") or d.get("replies"))
        reposts = _to_int(d.get("repost_count") or d.get("repostCount") or d.get("reshare_count") or d.get("reposts"))
        quotes = _to_int(d.get("quote_count") or d.get("quoteCount") or d.get("quotes"))
        posted_at = str(d.get("taken_at") or d.get("created_at") or d.get("publish_date") or d.get("timestamp") or "")

        key = post_id or text[:90]
        old = posts.get(key)
        new = ThreadPost(username=username, post_id=post_id, url=url, text=text, posted_at=posted_at,
                         likes=likes, replies=replies, reposts=reposts, quotes=quotes)
        if old is None or new.reactions >= old.reactions:
            posts[key] = new
    return sorted(posts.values(), key=lambda p: p.reactions, reverse=True)[:limit]


def parse_profile_html(username: str, html: str, limit: int = 30) -> ProfileSnapshot:
    username = username.strip().lstrip("@").lower()
    objs = _extract_json_objects(html)
    all_dicts: list[dict] = []
    for obj in objs:
        all_dicts.extend([x for x in _walk(obj) if isinstance(x, dict)])

    followers = _guess_followers(all_dicts)
    if not followers:
        m = re.search(r"([0-9][0-9,\.]*\s?[kKmM]?)\s+followers", html)
        if m:
            followers = _to_int(m.group(1))

    posts = _extract_posts(username, all_dicts, limit)
    return ProfileSnapshot(username=username, followers=followers, posts_loaded=len(posts), posts=posts)
