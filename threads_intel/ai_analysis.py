from __future__ import annotations

import json

import httpx

from .analytics import summarize, total_engagement
from .config import OPENAI_API_KEY, OPENAI_MODEL
from .models import ProfileSnapshot, ThreadPost


class AIAnalysisError(RuntimeError):
    pass


def _require_key() -> str:
    if not OPENAI_API_KEY:
        raise AIAnalysisError("Set OPENAI_API_KEY in .env to enable AI analysis.")
    return OPENAI_API_KEY


def _post_brief(post: ThreadPost) -> dict:
    return {
        "text": post.text[:700],
        "likes": post.likes,
        "comments": post.replies,
        "reposts": post.reposts,
        "quotes": post.quotes,
        "engagement": total_engagement(post),
    }


def _responses_text(prompt: str, timeout: int = 60) -> str:
    key = _require_key()
    payload = {
        "model": OPENAI_MODEL,
        "input": prompt,
    }
    response = httpx.post(
        "https://api.openai.com/v1/responses",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json=payload,
        timeout=timeout,
    )
    response.raise_for_status()
    data = response.json()
    if data.get("output_text"):
        return data["output_text"].strip()
    chunks = []
    for item in data.get("output", []):
        for content in item.get("content", []):
            text = content.get("text")
            if text:
                chunks.append(text)
    return "\n".join(chunks).strip()


def analyze_snapshot(snapshot: ProfileSnapshot) -> str:
    summary = summarize(snapshot)
    top_posts = sorted(snapshot.posts, key=total_engagement, reverse=True)[:8]
    prompt = (
        "You are a practical social media strategist for Threads accounts. "
        "Analyze this account using concise Malay/English mix. "
        "Give: account diagnosis, content pillars, hook problems, engagement problems, "
        "3 specific next actions, and 5 post ideas.\n\n"
        f"Summary:\n{json.dumps(summary, ensure_ascii=False)}\n\n"
        f"Top posts:\n{json.dumps([_post_brief(post) for post in top_posts], ensure_ascii=False)}"
    )
    return _responses_text(prompt)


def rewrite_hook(post_text: str) -> str:
    prompt = (
        "Rewrite this Threads post opening hook. Return 8 alternatives only. "
        "Make them specific, curiosity-driven, and natural in Malay/English mix. "
        "Do not invent facts outside the post.\n\n"
        f"Post:\n{post_text[:1500]}"
    )
    return _responses_text(prompt)
