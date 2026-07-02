# bebenang — Threads profile intelligence

CLI, Streamlit dashboard, and Telegram bot for monitoring public [Threads](https://www.threads.com) profiles: followers, post engagement, account scoring, and hook analysis. ("Bebenang" plays on *benang*, Bahasa Melayu for "thread".)

## What it does

Give it a public Threads username and it fetches the profile page, parses the embedded JSON out of the HTML, and stores a snapshot (followers + latest posts with likes/replies/reposts/quotes) in SQLite. On top of that data it computes:

- **Engagement rate** per post and account averages
- **Account score (0–100)** across four signals: engagement, conversation ratio, posting consistency, and format variety — with a plain-language diagnosis
- **Hook classification** (Bold Claim, Personal Story, Curiosity Question, Specific Number, Observation) and psychological trigger tags, tuned for mixed Malay/English post text
- **Topic clusters** and **best posting hours** (Asia/Kuala_Lumpur)
- **Breakout detection** and new-posts-since-last-fetch diffs

Fetching tries plain HTTP (httpx) first, then falls back to a headless Chromium render via Playwright when the static HTML isn't enough. Because snapshots are versioned in SQLite, repeated fetches build a follower/engagement history per account.

## Quick start

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/ahmadafif5321/Thread_Scrapper.git
cd Thread_Scrapper
uv sync
uv run playwright install chromium   # for the browser fallback
cp .env.example .env                 # defaults work; tokens optional
```

### CLI

```bash
uv run bebenang fetch someusername --limit 20   # fetch and store a snapshot
uv run bebenang list someusername               # table of stored posts
uv run bebenang summary someusername            # score, diagnosis, top hooks
```

### Dashboard

```bash
uv run streamlit run threads_intel/dashboard.py
```

Fetch accounts from the sidebar, then explore account comparison, history charts, topic clusters, best posting time, top hooks, and per-post tables.

### Telegram bot (optional)

Set `TELEGRAM_BOT_TOKEN` (from BotFather) and `TELEGRAM_CHAT_ID` in `.env`, then:

```bash
uv run bebenang telegram-summary someusername   # one-off summary push
uv run bebenang telegram-bot                    # interactive long-polling bot
```

The bot accepts a bare username, a `threads.com/@user` URL, or `/fetch`, `/summary`, and `/analyze` commands.

### AI analysis (optional)

With `OPENAI_API_KEY` set in `.env`, the dashboard and the bot's `/analyze` command send the account summary and top posts to the OpenAI Responses API for a content-strategy write-up and hook rewrite suggestions. Everything else works without it.

## Tech stack

- **Python 3.11+**, packaged with **uv** (`bebenang` console script via Typer)
- **httpx** + **Playwright** (Chromium) for fetching, **BeautifulSoup** for HTML/JSON extraction
- **Pydantic** models, **SQLite** storage
- **Streamlit** + **pandas** dashboard, **Rich** CLI tables
- Telegram Bot API and OpenAI Responses API called directly over HTTP — no heavy SDK dependencies

## Project layout

```
threads_intel/
  fetcher.py       # httpx-first fetch with Playwright fallback
  parser.py        # extract profile/posts from embedded page JSON
  analytics.py     # ER, account score, hooks, triggers, topics, timing
  storage.py       # SQLite snapshots, history, diffs
  cli.py           # Typer commands
  dashboard.py     # Streamlit app
  telegram_bot.py  # long-polling bot
  ai_analysis.py   # optional OpenAI-backed analysis
```

## Limitations and fair use

This reads **public profile pages only** — no login, no captcha bypass. Requests are rate-limited via a configurable delay. Threads' page structure changes over time, so the parser may need patching when Meta ships updates. Don't use this to monitor private accounts or harass anyone.

---

Built by [Ahmad Afif](https://ahmadafif.com) ([@ahmadafif5321](https://github.com/ahmadafif5321)).
