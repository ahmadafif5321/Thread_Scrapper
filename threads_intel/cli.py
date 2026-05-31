from __future__ import annotations

import asyncio
import httpx
import typer
from rich.console import Console
from rich.table import Table
from .fetcher import fetch_profile, ThreadsFetchError
from .storage import save_snapshot, latest_snapshot
from .analytics import summarize, engagement_rate, score_virality, detect_hook_type, total_engagement, trigger_tags
from .config import FETCH_TIMEOUT_SECONDS, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from .telegram_bot import TelegramBotError, run_bot

app = typer.Typer(help="Threads public intelligence CLI")
console = Console()


@app.command()
def fetch(username: str, limit: int = 30):
    """Fetch public profile and save latest posts."""
    try:
        snap = asyncio.run(asyncio.wait_for(fetch_profile(username, limit=limit), timeout=FETCH_TIMEOUT_SECONDS))
        save_snapshot(snap)
        s = summarize(snap)
        console.print(f"[bold green]Saved @{snap.username}[/bold green] | followers={s['followers']} | posts={s['posts_loaded']} | avg ER={s['avg_engagement_rate']}% | score={s['account_score']}/100")
    except TimeoutError:
        console.print(f"[bold red]Fetch timed out after {FETCH_TIMEOUT_SECONDS:g}s.[/bold red] Try again later or increase FETCH_TIMEOUT_SECONDS in .env.")
        raise typer.Exit(1)
    except ThreadsFetchError as e:
        console.print(f"[bold red]Fetch failed:[/bold red] {e}")
        raise typer.Exit(1)


@app.command("list")
def list_posts(username: str):
    """Show latest stored posts."""
    snap = latest_snapshot(username)
    if not snap:
        console.print("No data yet. Run: bebenang fetch USERNAME")
        raise typer.Exit(1)
    table = Table(title=f"@{snap.username}")
    for col in ["ER%", "Likes", "Replies", "Reposts", "Quotes", "Text"]:
        table.add_column(col)
    for p in snap.posts:
        table.add_row(str(engagement_rate(p, snap.followers)), str(p.likes), str(p.replies), str(p.reposts), str(p.quotes), p.text[:120])
    console.print(table)


@app.command()
def summary(username: str):
    """Show account summary and top hooks."""
    snap = latest_snapshot(username)
    if not snap:
        console.print("No data yet. Run: bebenang fetch USERNAME")
        raise typer.Exit(1)
    s = summarize(snap)
    console.print(f"[bold]@{snap.username}[/bold]")
    console.print(f"Followers: {s['followers']} | Posts loaded: {s['posts_loaded']} | Score: {s['account_score']}/100 | Avg ER: {s['avg_engagement_rate']}% | Top ER: {s['top_engagement_rate']}%")
    console.print(f"Likes: {s['total_likes']} | Comments: {s['total_comments']} | Reposts: {s['total_reposts']} | Quotes: {s['total_quotes']} | Total engagement: {s['total_engagement']}")
    console.print(s["score_diagnosis"])
    if s['breakout']:
        console.print("🔥 BREAKOUT detected")
    table = Table(title="Top Hooks")
    table.add_column("ER%")
    table.add_column("Engagement")
    table.add_column("Likes")
    table.add_column("Comments")
    table.add_column("Virality")
    table.add_column("Hook Type")
    table.add_column("Triggers")
    table.add_column("Text")
    for p in sorted(snap.posts, key=lambda x: engagement_rate(x, snap.followers), reverse=True)[:10]:
        table.add_row(str(engagement_rate(p, snap.followers)), str(total_engagement(p)), str(p.likes), str(p.replies), f"{score_virality(p, snap.followers)}/10", detect_hook_type(p.text), ", ".join(trigger_tags(p.text)), p.text[:120])
    console.print(table)


@app.command("telegram-summary")
def telegram_summary(username: str):
    """Send latest summary to Telegram."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        console.print("Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env first.")
        raise typer.Exit(1)
    snap = latest_snapshot(username)
    if not snap:
        console.print("No data yet. Run fetch first.")
        raise typer.Exit(1)
    s = summarize(snap)
    top = sorted(snap.posts, key=lambda x: engagement_rate(x, snap.followers), reverse=True)[:5]
    lines = [
        f"Megu Threads Scrape: @{snap.username}",
        f"Followers: {s['followers']:,}",
        f"Posts: {s['posts_loaded']}",
        f"Score: {s['account_score']}/100",
        f"Avg ER: {s['avg_engagement_rate']}%",
        f"Likes: {s['total_likes']} | Comments: {s['total_comments']} | Reposts: {s['total_reposts']} | Quotes: {s['total_quotes']}",
        s["score_diagnosis"],
        "",
        "Top hooks:",
    ]
    for p in top:
        lines.append(f"• {engagement_rate(p, snap.followers)}% ER | {total_engagement(p)} engagement | {p.likes} likes | {p.replies} comments | {detect_hook_type(p.text)}")
        lines.append(p.text[:160].replace("\n", " "))
        if p.url:
            lines.append(p.url)
        lines.append("")
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    r = httpx.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": "\n".join(lines), "disable_web_page_preview": True}, timeout=20)
    r.raise_for_status()
    console.print("Sent to Telegram.")


@app.command("telegram-bot")
def telegram_bot():
    """Run an interactive Telegram bot for fetch, summary, and AI analysis."""
    try:
        console.print("Telegram bot running. Commands: /fetch USERNAME, /summary USERNAME, /analyze USERNAME")
        asyncio.run(run_bot())
    except TelegramBotError as e:
        console.print(f"[bold red]Telegram bot failed:[/bold red] {e}")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
