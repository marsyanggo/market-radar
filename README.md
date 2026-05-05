# Market Radar

A daily pre-market screening and recommendation system. Given a US-equity universe, it computes a multi-signal **Heat Score**, identifies **Smart Money** flow, scores **Sentiment**, applies a multi-signal resonance recommendation engine, and ships the result as a Telegram report, Markdown archive, JSON watchlists, and a web dashboard.

> Companion to [AI_trader](../AI_trader). AI_trader **executes**; Market Radar **finds targets**. The two communicate via `data/proposed_*.json` watchlists.

## What it does

| Pillar | Signals |
|---|---|
| 🔥 **Heat Score** | volume × ADV, large-block %, UOA count, 24h news density |
| 💰 **Smart Money** | block trade buy/sell imbalance, UOA call vs put, P/C ratio, IV skew (25Δ) |
| 📈 **Technicals** | RSI(14), MACD(12/26/9), SMA 20/50/200, Bollinger Bands, ATR(14), 52w high/low |
| 📊 **Sentiment** | Claude Haiku 4.5 news headline scoring (with prompt caching), StockTwits Bullish/Bearish |
| 🏛️ **Insider** | SEC EDGAR Form 4 — open-market buys vs sells, weighted (P codes 2× weight) |
| 🎯 **Recommendations** | multi-signal resonance + risk veto (`strong_long` / `watch` / `avoid`) |
| 📤 **Outputs** | Telegram + `reports/YYYY-MM-DD.md` + watchlists for AI_trader + web dashboard |

## Project Status

All 9 phases of the original plan are complete. See [TARGET.md](./TARGET.md) for the full status; see [USER_GUIDE.md](./USER_GUIDE.md) for operational instructions ([中文版](./USER_GUIDE.zh-TW.md)).

| Phase | Status |
|---|---|
| 0 — Project init | ✅ |
| 1.1–1.4 — Data pipelines (DB, screener, news, blocks) | ✅ |
| 2 — Technicals | ✅ |
| 3 — Heat + first report ⭐ MVP | ✅ |
| 4 — Options Flow ⭐⭐ | ✅ |
| 5 — Sentiment ⭐⭐⭐ | ✅ |
| 6 — Engine v2 + backtest | ✅ |
| 7 — Automation (LaunchAgent + Telegram) | ✅ |
| 8 — SEC EDGAR insider trades | ✅ |
| 9 — Web Dashboard | ✅ |

## Quick Start

```bash
# 1. Create venv (Python 3.10+ required)
python3.11 -m venv .venv
source .venv/bin/activate

# 2. Install
pip install -e ".[dev,dashboard]"

# 3. Configure
cp .env.example .env
# edit .env — add ALPACA, TELEGRAM, ANTHROPIC keys

# 4. Initialize the database
radar db init

# 5. Sanity check
radar ping
# → Market Radar OK

# 6. Run the daily pipeline manually
bash scripts/run_daily.sh

# 7. Start the dashboard
radar dashboard --port 8765
# open http://localhost:8765
```

## Architecture

```
                Alpaca           SEC EDGAR        StockTwits      Anthropic
                  │                  │                │              │
                  ▼                  ▼                ▼              ▼
              screener · news · trades · option chain · Form 4 · sentiment LLM
                  │
                  ▼
              SQLite (data/radar.db, 13 tables)
                  │
                  ▼
        Heat / Smart Money / Sentiment / Insider scoring
                  │
                  ▼
        Engine v2 — multi-signal resonance + risk veto
                  │
                  ├──▶ Telegram (daily + 6× hourly intraday)
                  ├──▶ reports/YYYY-MM-DD.md
                  ├──▶ data/proposed_*.json (→ AI_trader)
                  └──▶ FastAPI Dashboard (http://localhost:8765)
```

## Tech Stack

Python 3.10+ · alpaca-py · ta (technical-indicator library) · py_vollib · SQLite · loguru · pydantic-settings · click · Anthropic SDK (Haiku 4.5 with prompt caching) · FastAPI + uvicorn · macOS launchd · Telegram Bot.

## Documentation

- **[USER_GUIDE.md](./USER_GUIDE.md)** — full English operations guide
- **[USER_GUIDE.zh-TW.md](./USER_GUIDE.zh-TW.md)** — 繁體中文操作指南
- **[TARGET.md](./TARGET.md)** — phase-by-phase implementation history
- **[SAVE.md](./SAVE.md)** — session journal (gitignored, local only)

## License

Private. Personal project.
