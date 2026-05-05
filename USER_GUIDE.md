# Market Radar — User Guide

This guide covers day-to-day operation of Market Radar: installation, configuration, CLI commands, scheduled jobs, and the web dashboard.

> 繁體中文版本：[USER_GUIDE.zh-TW.md](./USER_GUIDE.zh-TW.md)

---

## 1. Prerequisites

| Requirement | Notes |
|---|---|
| macOS or Linux | LaunchAgent automation is macOS-specific |
| Python 3.10+ | The system uses 3.11; check with `python3.11 --version` |
| Alpaca account | Free paper-trading tier is enough for everything except the websocket variants |
| Telegram bot | Optional but recommended (shared with AI_trader) |
| Anthropic API key | Optional — required for LLM news sentiment |
| SEC EDGAR | No key required (public API with User-Agent header) |
| StockTwits | No key required (public stream API) |

---

## 2. Installation

```bash
git clone git@github.com-personal:marsyanggo/market-radar.git
cd market-radar

python3.11 -m venv .venv
source .venv/bin/activate

# Install with all extras (dev tools + web dashboard)
pip install -e ".[dev,dashboard]"

# Optional: sentiment extras (Reddit, Google Trends)
pip install -e ".[sentiment]"
```

---

## 3. Configuration

```bash
cp .env.example .env
```

Edit `.env`:

```bash
# Alpaca (required)
ALPACA_API_KEY=...
ALPACA_SECRET_KEY=...
ALPACA_BASE_URL=https://paper-api.alpaca.markets
ALPACA_DATA_FEED=iex            # free tier — do NOT change to sip

# Telegram (optional — for daily report push)
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...

# Anthropic (optional — enables LLM news sentiment)
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-haiku-4-5-20251001

# Reddit (optional — Phase 5 future)
REDDIT_CLIENT_ID=
REDDIT_CLIENT_SECRET=

# Database / paths
DATABASE_URL=sqlite:///./data/radar.db
LOG_DIR=./logs
REPORTS_DIR=./reports
AITRADER_DATA_DIR=/path/to/AI_trader/data
```

Initialize the SQLite database:

```bash
radar db init
# → DB ready at version 5
```

Sanity check:

```bash
radar ping
# → Market Radar OK
```

---

## 4. The CLI — `radar`

The CLI is grouped by responsibility. Run `radar --help` for the full list.

### 4.1 Database

```bash
radar db init                      # apply all migrations
```

### 4.2 Screener — refresh the universe

```bash
radar screener run --most-actives 50 --movers 25
# Pulls top 50 most-actives + top 25 gainers/losers from Alpaca
# Upserts into the stocks table.
```

### 4.3 Bars + technicals

```bash
radar indicators run                       # compute for all stocks in DB
radar indicators run --symbol NVDA         # specific symbol(s)
```

### 4.4 News

```bash
radar news fetch --hours 24 --limit 100   # one-shot REST fetch
radar news poll  --interval 600           # long-running poller (every 10 min)
```

### 4.5 Block trades

```bash
# REST poller — works alongside AI_trader's WebSocket
radar poll trades --threshold 10000 --interval 60 --cycles 1

# WebSocket variant — only if AI_trader is NOT using its WS slot
radar stream trades --threshold 10000
```

### 4.6 Options chain (UOA, P/C, IV skew, Smart Money)

```bash
radar options run --symbol NVDA --symbol AAPL
# Fetches snapshots, detects UOA (size ≥ 50, aggressive, OTM 5-25%),
# computes Put/Call ratio, IV skew(25Δ), smart money score
```

### 4.7 Sentiment

```bash
# Both LLM + StockTwits
radar sentiment run --symbol NVDA --symbol PLTR

# StockTwits only (no Anthropic key required)
radar sentiment run --no-llm

# LLM only (uses ANTHROPIC_API_KEY)
radar sentiment run --no-stocktwits
```

### 4.8 SEC EDGAR Form 4 — insider trades

```bash
radar edgar form4 --symbol NVDA --symbol AAPL --days 30
# Pulls Form 4 filings from EDGAR, parses XML, persists insider transactions
```

### 4.9 Telegram

```bash
radar telegram test
# Sends "Market Radar — telegram test ✅" to your chat
```

### 4.10 Daily report (full pipeline)

```bash
radar report run \
  --no-screener \      # reuse existing stocks table
  --options \          # include options pipeline (top 20 by volume)
  --options-top 20 \
  --sentiment \        # include sentiment pipeline
  --insider \          # include EDGAR Form 4
  --insider-top 30 \
  --telegram \         # push to Telegram
  --watchlists         # write data/proposed_*.json for AI_trader
```

This is what `scripts/run_daily.sh` runs.

### 4.11 Backtest

```bash
radar backtest run --lookback 60 --symbol NVDA --symbol AAPL --symbol MSFT
# Replays engine_v2 against historical bars (technical + volume signals only)
# Reports 5d / 20d win rate, avg return, Sharpe per category
```

### 4.12 Web dashboard

```bash
radar dashboard --port 8765 --reload
# Open http://localhost:8765
```

---

## 5. Scheduled jobs (macOS LaunchAgent)

Two LaunchAgents are provided:

| Plist | Schedule | What it runs |
|---|---|---|
| `com.marsyang.market_radar.daily` | 06:30 PT | Full pipeline (`scripts/run_daily.sh`) |
| `com.marsyang.market_radar.intraday` | 07:30 / 08:30 / 09:30 / 10:30 / 11:30 / 12:30 PT | Lite hourly refresh (`scripts/run_intraday.sh`) |

### Install / status / trigger

```bash
bash scripts/install_launchd.sh install              # install both
bash scripts/install_launchd.sh install daily        # install one
bash scripts/install_launchd.sh status               # show registration
bash scripts/install_launchd.sh trigger daily        # fire now (one-shot)
bash scripts/install_launchd.sh uninstall            # remove both
```

### Logs

| Path | Source |
|---|---|
| `logs/launchd_stdout.log` / `launchd_stderr.log` | daily LaunchAgent stdout/err |
| `logs/intraday_stdout.log` / `intraday_stderr.log` | intraday LaunchAgent stdout/err |
| `logs/radar_YYYY-MM-DD.log` | application log (rotated daily) |

### What the daily run does

`scripts/run_daily.sh`:

1. `radar screener run` — refresh universe
2. `radar news fetch --hours 24` — pull last 24h news
3. `radar poll trades --cycles 1` — backfill block trades
4. `radar report run --no-screener --telegram --watchlists --options --options-top 20 --sentiment` — full pipeline + push

Total runtime: ~80 seconds.

### What the intraday run does

`scripts/run_intraday.sh`:

1. Skips weekends (`date +%u >= 6` → exit 0)
2. Runs `src.recommend.intraday_pipeline.run_intraday_pipeline()`:
   - Light screener
   - Recent news (last 2h)
   - Bars + technicals
   - Re-classify with engine_v2 (re-uses morning's options + sentiment data)
   - Telegram push (silent — no notification ping)

Total runtime: ~5 seconds.

---

## 6. Web Dashboard

```bash
# Foreground (terminal must stay open)
radar dashboard --port 8765

# Background (detached)
nohup uvicorn dashboard.api.app:app --port 8765 > logs/dashboard.log 2>&1 &
disown
```

Open **http://localhost:8765**. Three sections plus an expandable detail panel:

- **🔥 Top Heat** — top 15 by Heat score with vol×ADV / RSI / UOA / P/C / SM / sentiment
- **💰 Smart Money** — top 15 by Smart Money score
- **🎯 Recommendations** — `strong_long` / `watch` / `avoid` lists
- Click any row to expand a per-symbol detail panel: heat metrics, latest news, recent UOA, insider trades, block trades

### API endpoints

| Endpoint | Returns |
|---|---|
| `GET /api/health` | schema version + universe size |
| `GET /api/heat?limit=N&as_of=YYYY-MM-DD` | top heat |
| `GET /api/recommendations?as_of=YYYY-MM-DD` | recommendations |
| `GET /api/smart_money?limit=N&as_of=YYYY-MM-DD` | smart money ranking |
| `GET /api/stock/{symbol}` | full per-symbol detail |

---

## 7. The Recommendation Engine (engine v2)

Engine v2 evaluates **8 independent signals** per symbol, each scored 0–100:

| Signal | Source | Bullish range |
|---|---|---|
| `heat` | Heat score | > 60 |
| `smart_money` | block flow + UOA + P/C + IV skew | > 60 |
| `technical_alignment` | close > sma20 > sma50 (> sma200) | > 60 |
| `rsi` | RSI(14) calibrated, peak at ~58 | > 60 |
| `volume` | volume / 30d avg | > 60 |
| `options_skew` | put IV − call IV at 25Δ (negative is bullish) | > 60 |
| `sentiment` | Claude news + StockTwits | > 60 |
| `insider` | SEC Form 4 buys vs sells (P weighted 2×) | > 60 |
| `fifty_two_week` | distance from 52w high | > 60 |

**Classification rules** (any veto → `avoid` regardless of bullish count):

- `strong_long` — ≥ 4 bullish, ≤ 1 bearish, weighted score ≥ 65, no veto
- `watch` — ≥ 3 bullish, no veto
- `avoid` — risk veto OR (≥ 3 bearish AND heat ≥ 60)

**Risk vetoes** (`src/recommend/risk_score.py`):

- Overheated: heat > 90 AND RSI > 80
- Earnings within 4 trading days

**Risk score adders** (don't veto, but reduce confidence):

- avg_volume < 500K — low liquidity
- close < $5 — penny stock
- ATR / close > 8% — high volatility
- close < 92% of SMA50 — broken trend

---

## 8. Outputs

### 8.1 Markdown report

`reports/YYYY-MM-DD.md` — full daily report. `reports/YYYY-MM-DD_intraday_HHMM.md` for intraday snapshots.

### 8.2 Telegram

Daily report (06:30 PT) — full text, with notification ping.
Intraday updates (07:30–12:30 PT) — silent (no ping), each is one compact message.

### 8.3 Watchlists for AI_trader

```
data/proposed_watchlist.json          # IC candidates (RSI near 50, liquid)
data/proposed_phase2_watchlist.json   # Oversold candidates (RSI < 35)
```

These are **proposed** — they are NOT auto-promoted to AI_trader's `data/`. Review and copy manually:

```bash
cp data/proposed_watchlist.json /path/to/AI_trader/data/watchlist.json
```

---

## 9. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `radar ping` fails with `Alpaca credentials missing` | `.env` not loaded | Confirm `.env` exists in project root and has `ALPACA_API_KEY` + `ALPACA_SECRET_KEY` |
| `subscription does not permit querying recent SIP data` | `ALPACA_DATA_FEED=sip` on free tier | Change to `iex` |
| `connection limit exceeded` from WS | Free tier — only 1 WS allowed; AI_trader is using it | Use `radar poll trades` (REST) instead of `radar stream trades` |
| `ANTHROPIC_API_KEY missing — skipping LLM sentiment` | No key in `.env` | Add the key, or accept that StockTwits-only sentiment still works |
| `gpg failed to sign the data` on commit | gpg not on PATH | `git config gpg.program /opt/homebrew/bin/gpg` |
| Dashboard returns nothing at `/` | server not running | Start it (see §6); check `lsof -i :8765` |
| LaunchAgent doesn't fire | Mac was asleep | LaunchAgents do NOT fire on a sleeping Mac (unlike `caffeinate`d ones). The next firing happens normally. |
| Form 4 parse errors | `primary_doc` is HTML wrapper | The fix in `find_form4_xml_doc` resolves this — make sure you're on the latest commit |
| Pydantic warning `serialized value may not be as expected` | upstream alpaca-py | Harmless; ignore |
| `radar` command not found | venv not activated | `source .venv/bin/activate` |

---

## 10. File map

```
market_radar/
├── configs/settings.py            # pydantic-settings, .env loader
├── src/
│   ├── alpaca/                    # client, screener, news, bars,
│   │                              # trades_stream, trades_poller,
│   │                              # options_chain
│   ├── db/                        # schema.sql, connection, migrations,
│   │                              # repos
│   ├── edgar/                     # SEC EDGAR client + Form 4 parser
│   ├── indicators/                # technical (RSI/MACD/MA/BB/ATR), eod runner
│   ├── options/                   # contract_parser, uoa_detector,
│   │                              # flow_metrics, runner
│   ├── sentiment/                 # news_llm (Claude), stocktwits, runner
│   ├── scoring/                   # normalize, heat, smart_money,
│   │                              # sentiment_score, institutional
│   ├── recommend/                 # signals, risk_score, engine_v1,
│   │                              # engine_v2, daily_pipeline,
│   │                              # intraday_pipeline
│   ├── output/                    # markdown_report, telegram,
│   │                              # watchlist_writer
│   ├── backtest/replay.py
│   ├── cli.py                     # `radar` Click CLI
│   └── logger.py
├── dashboard/
│   ├── api/app.py                 # FastAPI
│   └── web/index.html             # vanilla JS + Tailwind CDN
├── scripts/
│   ├── run_daily.sh               # daily LaunchAgent entry
│   ├── run_intraday.sh            # intraday LaunchAgent entry
│   └── install_launchd.sh         # install/uninstall/status/trigger
├── com.marsyang.market_radar.daily.plist
├── com.marsyang.market_radar.intraday.plist
├── tests/                         # 68 tests
├── data/                          # SQLite + proposed watchlists
├── reports/                       # daily + intraday markdown
└── logs/                          # launchd + application logs
```

---

## 11. Updating

```bash
git pull
source .venv/bin/activate
pip install -e ".[dev,dashboard]"
radar db init                  # apply any new migrations
```

If `pip install` fails on `pandas-ta`, that's a known stale dep — `ta` library is the live one (already in `pyproject.toml`).
