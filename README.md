# Megu Threads Scrape

Projek Python untuk monitor public Threads account: followers, posts, engagement, breakout post, dan dashboard local.

## Cara install di Linux Mint

```bash
sudo apt update
sudo apt install -y python3 python3-venv git curl sqlite3
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc

cd ~
unzip bebenang_intel.zip
cd bebenang_intel
uv sync
cp .env.example .env
```

## Run CLI

```bash
uv run bebenang fetch akmalrahim --limit 20
uv run bebenang fetch mydinmalaysia --limit 20
uv run bebenang list akmalrahim
uv run bebenang summary akmalrahim
```

## Run dashboard

```bash
uv run streamlit run threads_intel/dashboard.py
```

Buka URL yang Streamlit beri, biasanya `http://localhost:8501`.

## Hantar summary ke Telegram

1. Create bot di BotFather.
2. Masukkan token dan chat id dalam `.env`.
3. Run:

```bash
uv run bebenang telegram-summary akmalrahim
```

## Telegram bot interaktif

Masukkan secret dalam `.env`:

```env
TELEGRAM_BOT_TOKEN=token_dari_botfather
OPENAI_API_KEY=optional_untuk_ai_analysis
OPENAI_MODEL=gpt-5.4-mini
```

Run bot:

```bash
uv run bebenang telegram-bot
```

Dalam Telegram, hantar salah satu:

```text
ahmadafif5321
https://www.threads.com/@ahmadafif5321
/fetch ahmadafif5321
/summary ahmadafif5321
/analyze ahmadafif5321
```

Bot akan fetch profile, simpan data, dan balas score, details engagement, top 3 hooks, serta link Threads. `/analyze` perlukan `OPENAI_API_KEY`.

## Cron harian contoh

```bash
crontab -e
```

Tambah:

```cron
0 8 * * * cd /home/$USER/bebenang_intel && uv run bebenang fetch akmalrahim --limit 30 && uv run bebenang telegram-summary akmalrahim
```

## Nota penting

Scraper ini baca data public page sahaja. Jangan guna untuk private account, jangan spam request, jangan bypass login/captcha, dan jangan gunakan data untuk ganggu orang. Public web structure Threads boleh berubah; kalau Meta ubah HTML/JSON, parser perlu patch.
