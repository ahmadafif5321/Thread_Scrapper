from __future__ import annotations

import asyncio
import re

import httpx

from .ai_analysis import AIAnalysisError, analyze_snapshot
from .analytics import detect_hook_type, engagement_rate, summarize, total_engagement, trigger_tags
from .config import FETCH_TIMEOUT_SECONDS, TELEGRAM_BOT_TOKEN
from .fetcher import ThreadsFetchError, fetch_profile
from .storage import latest_snapshot, save_snapshot


class TelegramBotError(RuntimeError):
    pass


def _api_url(method: str) -> str:
    if not TELEGRAM_BOT_TOKEN:
        raise TelegramBotError("Set TELEGRAM_BOT_TOKEN in .env first.")
    return f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}"


def _extract_username(text: str) -> str:
    text = text.strip()
    match = re.search(r"threads\.(?:net|com)/@?([A-Za-z0-9_.]+)", text)
    if match:
        return match.group(1).strip("._").lower()
    if text.startswith("@"):
        text = text[1:]
    return re.sub(r"[^A-Za-z0-9_.]", "", text).strip("._").lower()


def _top_hooks_text(snap, limit: int = 3) -> list[str]:
    lines = ["", "Top 3 hooks:"]
    top = sorted(snap.posts, key=lambda post: (engagement_rate(post, snap.followers), total_engagement(post)), reverse=True)[:limit]
    for idx, post in enumerate(top, start=1):
        lines.extend(
            [
                f"{idx}. {engagement_rate(post, snap.followers)}% ER | {total_engagement(post)} engagement",
                f"Likes {post.likes} | Comments {post.replies} | Reposts {post.reposts} | Quotes {post.quotes}",
                f"Hook: {detect_hook_type(post.text)} | Triggers: {', '.join(trigger_tags(post.text))}",
                post.text[:450].replace("\n", " "),
            ]
        )
        if post.url:
            lines.append(post.url)
        lines.append("")
    return lines


def _summary_text(username: str, include_hooks: bool = True) -> str:
    snap = latest_snapshot(username)
    if not snap:
        return f"No data for @{username}. Send /fetch {username} first."
    s = summarize(snap)
    lines = [
        f"Megu Threads Scrape: @{snap.username}",
        f"Threads: https://www.threads.com/@{snap.username}",
        f"Followers: {s['followers']:,}",
        f"Posts loaded: {s['posts_loaded']}",
        f"Score: {s['account_score']}/100",
        f"Avg ER: {s['avg_engagement_rate']}% | Top ER: {s['top_engagement_rate']}%",
        f"Likes: {s['total_likes']} | Comments: {s['total_comments']}",
        f"Reposts: {s['total_reposts']} | Quotes: {s['total_quotes']}",
        f"Top topic: {s['top_topic']} | Best time: {s['best_time']}",
        s["score_diagnosis"],
    ]
    if include_hooks:
        lines.extend(_top_hooks_text(snap, limit=3))
    return "\n".join(lines)


async def _fetch_and_summarize(username: str) -> str:
    snap = await asyncio.wait_for(fetch_profile(username, limit=100), timeout=FETCH_TIMEOUT_SECONDS)
    save_snapshot(snap)
    return f"Fetched @{snap.username}: {len(snap.posts)} posts\n\n{_summary_text(snap.username)}"


async def _send(client: httpx.AsyncClient, chat_id: int, text: str):
    await client.post(
        _api_url("sendMessage"),
        json={"chat_id": chat_id, "text": text[:3900], "disable_web_page_preview": True},
    )


async def _handle_message(client: httpx.AsyncClient, message: dict):
    chat_id = message.get("chat", {}).get("id")
    text = (message.get("text") or "").strip()
    if not chat_id or not text:
        return

    parts = text.split()
    command = parts[0].lower()
    username = parts[1].strip().lstrip("@") if len(parts) > 1 else ""

    if command in ("/start", "/help"):
        await _send(
            client,
            chat_id,
            "Send a Threads username or URL for full analysis.\nCommands: /fetch username, /summary username, /analyze username",
        )
    elif command == "/summary" and username:
        await _send(client, chat_id, _summary_text(username))
    elif command == "/fetch" and username:
        try:
            await _send(client, chat_id, f"Fetching @{username}...")
            await _send(client, chat_id, await _fetch_and_summarize(username))
        except TimeoutError:
            await _send(client, chat_id, f"Fetch timed out for @{username}. Try again later.")
        except ThreadsFetchError as exc:
            await _send(client, chat_id, f"Fetch failed for @{username}: {exc}")
    elif command == "/analyze" and username:
        snap = latest_snapshot(username)
        if not snap:
            await _send(client, chat_id, f"No data for @{username}. Send /fetch {username} first.")
            return
        try:
            await _send(client, chat_id, analyze_snapshot(snap))
        except AIAnalysisError as exc:
            await _send(client, chat_id, str(exc))
        except Exception as exc:
            await _send(client, chat_id, f"AI analysis failed: {exc}")
    elif not command.startswith("/"):
        username = _extract_username(text)
        if not username:
            await _send(client, chat_id, "Send a valid Threads username or URL.")
            return
        try:
            await _send(client, chat_id, f"Fetching and analyzing @{username}...")
            await _send(client, chat_id, await _fetch_and_summarize(username))
        except TimeoutError:
            await _send(client, chat_id, f"Fetch timed out for @{username}. Try /summary {username} if data already exists.")
        except ThreadsFetchError as exc:
            existing = latest_snapshot(username)
            if existing:
                await _send(client, chat_id, f"Live fetch failed, using stored data.\n\n{_summary_text(username)}")
            else:
                await _send(client, chat_id, f"Fetch failed for @{username}: {exc}")
    else:
        await _send(client, chat_id, "Unknown command. Use /help.")


async def run_bot():
    offset = 0
    async with httpx.AsyncClient(timeout=60) as client:
        while True:
            response = await client.get(_api_url("getUpdates"), params={"timeout": 30, "offset": offset})
            response.raise_for_status()
            for update in response.json().get("result", []):
                offset = max(offset, update["update_id"] + 1)
                await _handle_message(client, update.get("message", {}))
            await asyncio.sleep(1)
