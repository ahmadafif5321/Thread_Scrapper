from __future__ import annotations

import asyncio
from pathlib import Path

import httpx

from .config import USER_AGENT, HTTP_TIMEOUT_SECONDS, REQUEST_DELAY_SECONDS
from .parser import parse_profile_html
from .models import ProfileSnapshot


class ThreadsFetchError(RuntimeError):
    pass


DEBUG_DIR = Path("debug_html")
PLAYWRIGHT_TIMEOUT_MS = 30000
PLAYWRIGHT_RENDER_WAIT_MS = 3000
PLAYWRIGHT_SCROLLS = 2
PLAYWRIGHT_MAX_SCROLLS = 20


def _is_valid_snapshot(snap: ProfileSnapshot) -> bool:
    return bool(snap.followers or snap.posts)


def _save_debug_html(username: str, source: str, html: str) -> Path:
    DEBUG_DIR.mkdir(exist_ok=True)
    safe_username = username.strip().lstrip("@").lower()
    path = DEBUG_DIR / f"{safe_username}_{source}.html"
    path.write_text(html, encoding="utf-8", errors="ignore")
    return path


def _scroll_count(limit: int) -> int:
    return max(PLAYWRIGHT_SCROLLS, min(PLAYWRIGHT_MAX_SCROLLS, (limit + 4) // 5))


def _better_snapshot(current: ProfileSnapshot | None, candidate: ProfileSnapshot | None) -> ProfileSnapshot | None:
    if candidate is None:
        return current
    if current is None:
        return candidate
    if len(candidate.posts) > len(current.posts):
        return candidate
    if len(candidate.posts) == len(current.posts) and candidate.followers > current.followers:
        return candidate
    return current


async def _fetch_with_httpx(username: str, limit: int = 30) -> ProfileSnapshot | None:
    username = username.strip().lstrip("@")
    urls = [
        f"https://www.threads.com/@{username}",
        f"https://www.threads.net/@{username}",
    ]

    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,ms;q=0.8",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }

    last_error = None
    async with httpx.AsyncClient(
        headers=headers,
        timeout=HTTP_TIMEOUT_SECONDS,
        follow_redirects=True,
    ) as client:
        for url in urls:
            try:
                await asyncio.sleep(REQUEST_DELAY_SECONDS)

                resp = await client.get(url)

                if resp.status_code in (403, 429):
                    last_error = f"{resp.status_code} from {url}"
                    continue

                if resp.status_code >= 400:
                    last_error = f"{resp.status_code} from {url}"
                    continue

                html = resp.text
                _save_debug_html(username, "httpx", html)

                snap = parse_profile_html(username, html, limit=limit)
                if _is_valid_snapshot(snap):
                    return snap
            except httpx.HTTPError as exc:
                last_error = str(exc)
                continue

    if last_error:
        raise ThreadsFetchError(f"HTTP fetch failed: {last_error}")
    return None


async def _fetch_with_playwright(username: str, limit: int = 30) -> ProfileSnapshot | None:
    username = username.strip().lstrip("@")

    try:
        from playwright.async_api import async_playwright
    except Exception as exc:
        raise ThreadsFetchError(
            "Playwright belum tersedia. Run: uv sync && uv run playwright install chromium"
        ) from exc

    urls = [
        f"https://www.threads.com/@{username}",
        f"https://www.threads.net/@{username}",
    ]

    browser = None
    last_error = None
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                ],
            )

            context = await browser.new_context(
                user_agent=USER_AGENT,
                locale="en-US",
                viewport={"width": 1366, "height": 900},
            )

            page = await context.new_page()

            for url in urls:
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=PLAYWRIGHT_TIMEOUT_MS)
                    await page.wait_for_timeout(PLAYWRIGHT_RENDER_WAIT_MS)

                    # Scroll sikit supaya public posts sempat hydrate/render.
                    for _ in range(_scroll_count(limit)):
                        await page.mouse.wheel(0, 1800)
                        await page.wait_for_timeout(1000)

                    html = await page.content()
                    _save_debug_html(username, "playwright", html)

                    snap = parse_profile_html(username, html, limit=limit)
                    if _is_valid_snapshot(snap):
                        return snap

                except Exception as exc:
                    last_error = exc
                    continue
    finally:
        if browser:
            await browser.close()

    if last_error:
        raise ThreadsFetchError(f"Playwright fetch failed: {last_error}")
    return None


async def fetch_profile(username: str, limit: int = 30) -> ProfileSnapshot:
    username = username.strip().lstrip("@")
    if not username:
        raise ThreadsFetchError("Username is required.")

    errors = []
    best_snap = None
    try:
        snap = await _fetch_with_httpx(username, limit=limit)
        best_snap = _better_snapshot(best_snap, snap)
        if best_snap and len(best_snap.posts) >= limit:
            return best_snap
    except ThreadsFetchError as exc:
        errors.append(str(exc))

    try:
        snap = await _fetch_with_playwright(username, limit=limit)
        best_snap = _better_snapshot(best_snap, snap)
        if best_snap:
            return best_snap
    except ThreadsFetchError as exc:
        errors.append(str(exc))

    if best_snap:
        return best_snap

    detail = f" Last error: {errors[-1]}" if errors else ""

    raise ThreadsFetchError(
        "HTML berjaya diambil tetapi parser masih tidak jumpa profile/post data. "
        "Semak folder debug_html/. Kemungkinan Threads ubah struktur page, account tidak public, "
        f"atau page memerlukan login/JS tambahan.{detail}"
    )
