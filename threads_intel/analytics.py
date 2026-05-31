from __future__ import annotations

from statistics import median
from .models import ProfileSnapshot, ThreadPost


def total_engagement(post: ThreadPost) -> int:
    return post.likes + post.replies + post.reposts + post.quotes


def engagement_rate(post: ThreadPost, followers: int) -> float:
    if followers <= 0:
        return 0.0
    return round((total_engagement(post) / followers) * 100, 2)


def _avg(values: list[int | float]) -> float:
    return round(sum(values) / len(values), 2) if values else 0.0


def engagement_level(er: float) -> str:
    if er >= 5:
        return "excellent"
    if er >= 2:
        return "strong"
    if er >= 1:
        return "healthy"
    if er >= 0.3:
        return "developing"
    return "low"


def account_score(snapshot: ProfileSnapshot) -> dict:
    posts = snapshot.posts
    if not posts:
        return {
            "score": 0,
            "engagement": 0,
            "conversation": 0,
            "consistency": 0,
            "format": 0,
            "diagnosis": "No posts loaded yet.",
        }

    ers = [engagement_rate(p, snapshot.followers) for p in posts]
    totals = [total_engagement(p) for p in posts]
    replies = [p.replies for p in posts]
    texts = [p.text.strip() for p in posts if p.text.strip()]
    avg_er = _avg(ers)
    active_posts = sum(1 for total in totals if total > 0)
    conversation_ratio = (sum(replies) / sum(totals)) if sum(totals) else 0
    useful_posts = sum(1 for text in texts if any(tag in trigger_tags(text) for tag in ("useful", "specific", "curiosity")))
    varied_hooks = len({detect_hook_type(text) for text in texts})

    engagement = min(40, round(avg_er * 12))
    conversation = min(20, round(conversation_ratio * 100))
    consistency = round((active_posts / len(posts)) * 20)
    format_score = min(20, round((useful_posts / max(len(texts), 1)) * 12) + min(varied_hooks * 2, 8))
    score = min(100, engagement + conversation + consistency + format_score)

    if score >= 75:
        diagnosis = "Strong account signal. Keep scaling winning topics and formats."
    elif score >= 50:
        diagnosis = "Good base. Improve reply-driving hooks and posting consistency."
    elif score >= 25:
        diagnosis = "Early traction. Focus on clearer hooks, stronger topics, and more conversation prompts."
    else:
        diagnosis = "Low visible traction. Test sharper hooks, stronger positioning, and more useful posts."

    return {
        "score": score,
        "engagement": engagement,
        "conversation": conversation,
        "consistency": consistency,
        "format": format_score,
        "diagnosis": diagnosis,
    }


TOPIC_KEYWORDS = {
    "business": ["bisnes", "business", "sales", "marketing", "brand", "customer", "market", "syarikat"],
    "tech": ["ai", "data", "scrape", "python", "api", "software", "app", "system"],
    "personal": ["aku", "saya", "dulu", "hidup", "pengalaman", "wife", "keluarga"],
    "food": ["makan", "kedai", "food", "restoran", "minum", "kopi"],
    "learning": ["belajar", "baca", "falsafah", "idea", "knowledge", "tips", "cara"],
    "sports": ["lari", "marathon", "nba", "kasut", "nike", "jordan"],
}


def topic_tags(text: str) -> list[str]:
    t = text.lower()
    tags = [topic for topic, words in TOPIC_KEYWORDS.items() if any(word in t for word in words)]
    return tags or ["general"]


def topic_summary(posts: list[ThreadPost]) -> list[dict]:
    totals: dict[str, dict] = {}
    for post in posts:
        for topic in topic_tags(post.text):
            item = totals.setdefault(topic, {"topic": topic, "posts": 0, "engagement": 0})
            item["posts"] += 1
            item["engagement"] += total_engagement(post)
    rows = list(totals.values())
    for row in rows:
        row["avg_engagement"] = round(row["engagement"] / row["posts"], 2) if row["posts"] else 0
    return sorted(rows, key=lambda row: (row["engagement"], row["posts"]), reverse=True)


def _post_hour(posted_at: str) -> int | None:
    if not posted_at:
        return None
    try:
        import pandas as pd

        raw = str(posted_at).strip()
        if raw.isdigit():
            unit = "ms" if len(raw) > 10 else "s"
            ts = pd.to_datetime(int(raw), unit=unit, utc=True, errors="coerce")
        else:
            ts = pd.to_datetime(raw, utc=True, errors="coerce", format="mixed")
        if pd.isna(ts):
            return None
        return int(ts.tz_convert("Asia/Kuala_Lumpur").hour)
    except Exception:
        return None


def best_posting_hours(posts: list[ThreadPost]) -> list[dict]:
    buckets: dict[int, dict] = {}
    for post in posts:
        hour = _post_hour(post.posted_at)
        if hour is None:
            continue
        item = buckets.setdefault(hour, {"hour": hour, "posts": 0, "engagement": 0})
        item["posts"] += 1
        item["engagement"] += total_engagement(post)
    rows = list(buckets.values())
    for row in rows:
        row["avg_engagement"] = round(row["engagement"] / row["posts"], 2) if row["posts"] else 0
        row["time_window"] = f"{row['hour']:02d}:00-{(row['hour'] + 1) % 24:02d}:00"
    return sorted(rows, key=lambda row: row["avg_engagement"], reverse=True)


def compare_snapshots(snapshots: list[ProfileSnapshot]) -> list[dict]:
    rows = []
    for snapshot in snapshots:
        s = summarize(snapshot)
        rows.append(
            {
                "username": snapshot.username,
                "followers": s["followers"],
                "posts_loaded": s["posts_loaded"],
                "score": s["account_score"],
                "avg_er": s["avg_engagement_rate"],
                "total_engagement": s["total_engagement"],
                "likes": s["total_likes"],
                "comments": s["total_comments"],
                "top_er": s["top_engagement_rate"],
            }
        )
    return sorted(rows, key=lambda row: (row["score"], row["avg_er"]), reverse=True)


def summarize(snapshot: ProfileSnapshot) -> dict:
    posts = snapshot.posts
    engagements = [total_engagement(p) for p in posts]
    likes = [p.likes for p in posts]
    replies = [p.replies for p in posts]
    reposts = [p.reposts for p in posts]
    quotes = [p.quotes for p in posts]
    ers = [engagement_rate(p, snapshot.followers) for p in posts]
    top_post = max(posts, key=total_engagement, default=None)
    top_eng = max(posts, key=lambda p: engagement_rate(p, snapshot.followers), default=None)
    score = account_score(snapshot)
    topics = topic_summary(posts)
    best_hours = best_posting_hours(posts)
    return {
        "username": snapshot.username,
        "followers": snapshot.followers,
        "posts_loaded": len(posts),
        "total_likes": sum(likes),
        "total_replies": sum(replies),
        "total_comments": sum(replies),
        "total_reposts": sum(reposts),
        "total_quotes": sum(quotes),
        "total_engagement": sum(engagements),
        "avg_engagement": _avg(engagements),
        "median_engagement": int(median(engagements)) if engagements else 0,
        "top_engagement": total_engagement(top_post) if top_post else 0,
        "top_reactions": total_engagement(top_post) if top_post else 0,
        "median_reactions": int(median(engagements)) if engagements else 0,
        "avg_engagement_rate": _avg(ers),
        "top_engagement_rate": engagement_rate(top_eng, snapshot.followers) if top_eng else 0,
        "engagement_level": engagement_level(_avg(ers)),
        "breakout": bool(top_eng and engagement_rate(top_eng, snapshot.followers) >= 5),
        "account_score": score["score"],
        "score_engagement": score["engagement"],
        "score_conversation": score["conversation"],
        "score_consistency": score["consistency"],
        "score_format": score["format"],
        "score_diagnosis": score["diagnosis"],
        "top_topic": topics[0]["topic"] if topics else "general",
        "best_time": best_hours[0]["time_window"] if best_hours else "Not enough timestamp data",
    }


def score_virality(post: ThreadPost, followers: int) -> int:
    er = engagement_rate(post, followers)
    if er >= 50:
        return 10
    if er >= 20:
        return 9
    if er >= 10:
        return 8
    if er >= 5:
        return 7
    if er >= 2:
        return 5
    if er >= 1:
        return 4
    return 2 if post.reactions else 0


def detect_hook_type(text: str) -> str:
    t = text.lower().strip()
    if any(x in t for x in ["sejarah", "akhirnya", "pecah", "rekod", "baru"]):
        return "Bold Claim / Milestone"
    if any(x in t for x in ["aku", "saya", "dulu", "masa tu", "start"]):
        return "Personal Story"
    if "?" in t or any(x in t for x in ["kenapa", "macam mana", "apa jadi"]):
        return "Curiosity Question"
    if any(ch.isdigit() for ch in t):
        return "Specific Number"
    return "Observation"


def hook_reason(text: str) -> str:
    hook_type = detect_hook_type(text)
    reasons = {
        "Bold Claim / Milestone": "Detected milestone or strong-claim words such as sejarah, akhirnya, pecah, rekod, baru.",
        "Personal Story": "Detected first-person or timeline words such as aku, saya, dulu, masa tu, start.",
        "Curiosity Question": "Detected a question mark or curiosity words such as kenapa, macam mana, apa jadi.",
        "Specific Number": "Detected numbers, which usually make a hook feel more concrete.",
        "Observation": "No stronger hook pattern detected; treated as a general observation.",
    }
    return reasons.get(hook_type, "")


def trigger_tags(text: str) -> list[str]:
    t = text.lower()
    tags = []
    if any(x in t for x in ["sejarah", "rekod", "akhirnya", "pecah"]):
        tags.append("surprise")
    if any(x in t for x in ["aku", "saya", "dulu", "masa tu"]):
        tags.append("personal")
    if any(x in t for x in ["belajar", "cara", "tips", "guna"]):
        tags.append("useful")
    if any(ch.isdigit() for ch in t):
        tags.append("specific")
    if not tags:
        tags.append("curiosity")
    return tags[:4]


def trigger_reason(tag: str) -> str:
    reasons = {
        "surprise": "Uses milestone, record, or unexpected-change language.",
        "personal": "Uses first-person or lived-experience language.",
        "useful": "Signals practical value, tips, learning, or how-to content.",
        "specific": "Uses numbers or concrete details.",
        "curiosity": "Default curiosity signal when no stronger trigger is detected.",
    }
    return reasons.get(tag, "")
