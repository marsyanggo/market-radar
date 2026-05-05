# Market Radar — 使用指南

涵蓋日常操作：安裝、設定、CLI 指令、排程任務、Web Dashboard。

> English version: [USER_GUIDE.md](./USER_GUIDE.md)

> ⚠️ **使用前**：請先閱讀 [DISCLAIMER.md](./DISCLAIMER.md)。本軟體為研究/教育工具；不是投資建議，您須自負所有交易風險。授權條款為 [PolyForm-NC 1.0.0](./LICENSE)（僅供非商業使用）。

---

## 1. 環境需求

| 需求 | 備註 |
|---|---|
| macOS 或 Linux | LaunchAgent 自動化僅 macOS 支援 |
| Python 3.10+ | 系統使用 3.11；`python3.11 --version` 確認 |
| Alpaca 帳號 | 免費 paper-trading tier 已足夠（除 WebSocket 進階用法外） |
| Telegram bot | 選配但建議（與 AI_trader 共用） |
| Anthropic API key | 選配 — LLM 新聞情緒打分需要 |
| SEC EDGAR | 不需 key（公開 API，需 User-Agent header） |
| StockTwits | 不需 key（公開 stream API） |

---

## 2. 安裝

```bash
git clone git@github.com-personal:marsyanggo/market-radar.git
cd market-radar

python3.11 -m venv .venv
source .venv/bin/activate

# 完整安裝（含開發工具 + dashboard）
pip install -e ".[dev,dashboard]"

# 選配：情緒分析額外套件（Reddit / Google Trends）
pip install -e ".[sentiment]"
```

---

## 3. 設定

```bash
cp .env.example .env
```

編輯 `.env`：

```bash
# Alpaca（必填）
ALPACA_API_KEY=...
ALPACA_SECRET_KEY=...
ALPACA_BASE_URL=https://paper-api.alpaca.markets
ALPACA_DATA_FEED=iex            # free tier — 不要改成 sip

# Telegram（選配 — 推送日報用）
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...

# Anthropic（選配 — 啟用 LLM 新聞情緒打分）
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-haiku-4-5-20251001

# Reddit（選配 — Phase 5 預留）
REDDIT_CLIENT_ID=
REDDIT_CLIENT_SECRET=

# 資料庫 / 路徑
DATABASE_URL=sqlite:///./data/radar.db
LOG_DIR=./logs
REPORTS_DIR=./reports
AITRADER_DATA_DIR=/path/to/AI_trader/data
```

初始化 SQLite：

```bash
radar db init
# → DB ready at version 5
```

驗證：

```bash
radar ping
# → Market Radar OK
```

---

## 4. CLI — `radar`

CLI 依職責分組，`radar --help` 看完整列表。

### 4.1 資料庫

```bash
radar db init                      # 套用所有 migrations
```

### 4.2 Screener — 刷新觀察池

```bash
radar screener run --most-actives 50 --movers 25
# 從 Alpaca 抓 top 50 most-actives + top 25 漲跌幅榜
# upsert 進 stocks 表
```

### 4.3 Bars + 技術指標

```bash
radar indicators run                       # 對 DB 中所有 stocks
radar indicators run --symbol NVDA         # 特定 symbol
```

### 4.4 News

```bash
radar news fetch --hours 24 --limit 100   # 一次性 REST 抓
radar news poll  --interval 600           # 常駐 poller（每 10 分鐘）
```

### 4.5 大單偵測

```bash
# REST poller — 與 AI_trader WebSocket 並存
radar poll trades --threshold 10000 --interval 60 --cycles 1

# WebSocket 版 — 僅當 AI_trader 沒佔用 WS 連線時可用
radar stream trades --threshold 10000
```

### 4.6 Options chain（UOA / P/C / IV skew / Smart Money）

```bash
radar options run --symbol NVDA --symbol AAPL
# 抓 snapshots，偵測 UOA（size ≥ 50、aggressive、OTM 5-25%）
# 計算 P/C ratio、IV skew(25Δ)、smart money score
```

### 4.7 情緒分析

```bash
# LLM + StockTwits 都跑
radar sentiment run --symbol NVDA --symbol PLTR

# 只跑 StockTwits（不需 Anthropic key）
radar sentiment run --no-llm

# 只跑 LLM（需 ANTHROPIC_API_KEY）
radar sentiment run --no-stocktwits
```

### 4.8 SEC EDGAR Form 4 — 內部人交易

```bash
radar edgar form4 --symbol NVDA --symbol AAPL --days 30
# 從 EDGAR 抓 Form 4 filings，解析 XML，寫入 insider_trades
```

### 4.9 Telegram

```bash
radar telegram test
# 推送 "Market Radar — telegram test ✅" 到你的 chat
```

### 4.10 每日報告（完整 pipeline）

```bash
radar report run \
  --no-screener \      # 重用既有 stocks 表
  --options \          # 含 options pipeline（top 20 by volume）
  --options-top 20 \
  --sentiment \        # 含情緒分析
  --insider \          # 含 EDGAR Form 4
  --insider-top 30 \
  --telegram \         # 推 Telegram
  --watchlists         # 寫 data/proposed_*.json 給 AI_trader
```

這就是 `scripts/run_daily.sh` 跑的內容。

### 4.11 回測

```bash
radar backtest run --lookback 60 --symbol NVDA --symbol AAPL --symbol MSFT
# 用歷史 bars 重播 engine_v2（僅技術 + 量能訊號）
# 輸出 5d / 20d 勝率、平均報酬、Sharpe（按分類）
```

### 4.12 Web dashboard

```bash
radar dashboard --port 8765 --reload
# 開瀏覽器 http://localhost:8765
```

---

## 5. 排程任務（macOS LaunchAgent）

提供兩個 LaunchAgent：

| Plist | 排程 | 內容 |
|---|---|---|
| `com.marsyang.market_radar.daily` | 06:30 PT | 完整 pipeline (`scripts/run_daily.sh`) |
| `com.marsyang.market_radar.intraday` | 07:30 / 08:30 / 09:30 / 10:30 / 11:30 / 12:30 PT | 精簡版小時更新 (`scripts/run_intraday.sh`) |

### 安裝 / 狀態 / 觸發

```bash
bash scripts/install_launchd.sh install              # 兩個都裝
bash scripts/install_launchd.sh install daily        # 只裝一個
bash scripts/install_launchd.sh status               # 查註冊狀態
bash scripts/install_launchd.sh trigger daily        # 立即觸發一次
bash scripts/install_launchd.sh uninstall            # 移除
```

### 日誌位置

| 路徑 | 來源 |
|---|---|
| `logs/launchd_stdout.log` / `launchd_stderr.log` | daily LaunchAgent stdout/err |
| `logs/intraday_stdout.log` / `intraday_stderr.log` | intraday LaunchAgent stdout/err |
| `logs/radar_YYYY-MM-DD.log` | 應用程式 log（每日輪替） |

### Daily run 做什麼

`scripts/run_daily.sh`:

1. `radar screener run` — 刷新 universe
2. `radar news fetch --hours 24` — 抓最近 24h 新聞
3. `radar poll trades --cycles 1` — 補抓大單
4. `radar report run --no-screener --telegram --watchlists --options --options-top 20 --sentiment` — 完整 pipeline + 推送

總耗時：~80 秒。

### Intraday run 做什麼

`scripts/run_intraday.sh`:

1. 跳過週末（`date +%u >= 6` → exit 0）
2. 跑 `src.recommend.intraday_pipeline.run_intraday_pipeline()`：
   - 輕量 screener
   - 最近 2h 新聞
   - bars + technicals
   - engine_v2 重新分類（複用早上的 options + sentiment 資料）
   - Telegram 推送（**靜音** — 不響）

總耗時：~5 秒。

---

## 6. Web Dashboard

```bash
# 前景（terminal 不能關）
radar dashboard --port 8765

# 背景（detached）
nohup uvicorn dashboard.api.app:app --port 8765 > logs/dashboard.log 2>&1 &
disown
```

開 **http://localhost:8765**。三個區塊 + 可展開的個股 detail：

- **🔥 Top Heat** — top 15 by Heat（含 vol×ADV / RSI / UOA / P/C / SM / sentiment）
- **💰 Smart Money** — top 15 by Smart Money 分數
- **🎯 Recommendations** — `strong_long` / `watch` / `avoid` 三欄
- 點任一 row → 展開個股 detail：4 個 metric cards + 最近新聞 / UOA / 內部人 / 大單

### API endpoints

| Endpoint | 回傳 |
|---|---|
| `GET /api/health` | schema 版本 + universe 大小 |
| `GET /api/heat?limit=N&as_of=YYYY-MM-DD` | top heat |
| `GET /api/recommendations?as_of=YYYY-MM-DD` | 推薦清單 |
| `GET /api/smart_money?limit=N&as_of=YYYY-MM-DD` | smart money 排行 |
| `GET /api/stock/{symbol}` | 完整個股 detail |

---

## 7. 推薦引擎（engine v2）

Engine v2 對每個 symbol 評估 **8 個獨立訊號**，每個 0-100：

| 訊號 | 來源 | Bullish 範圍 |
|---|---|---|
| `heat` | Heat score | > 60 |
| `smart_money` | block flow + UOA + P/C + IV skew | > 60 |
| `technical_alignment` | close > sma20 > sma50 (> sma200) | > 60 |
| `rsi` | RSI(14) calibrated，~58 為高峰 | > 60 |
| `volume` | volume / 30d 平均量 | > 60 |
| `options_skew` | put IV − call IV at 25Δ（負值看多） | > 60 |
| `sentiment` | Claude 新聞 + StockTwits | > 60 |
| `insider` | SEC Form 4 買 vs 賣（P 加權 2×） | > 60 |
| `fifty_two_week` | 距 52w 高百分比 | > 60 |

**分類規則**（任何 veto → `avoid`，無視 bullish 數）：

- `strong_long` — ≥ 4 bullish、≤ 1 bearish、weighted ≥ 65、無 veto
- `watch` — ≥ 3 bullish、無 veto
- `avoid` — 風險 veto 或（≥ 3 bearish 且 heat ≥ 60）

**Risk vetoes**（`src/recommend/risk_score.py`）：

- 過熱：heat > 90 且 RSI > 80
- 財報 4 個交易日內

**Risk score 加分項**（不 veto，但降信心）：

- avg_volume < 500K — 流動性差
- close < $5 — 雞蛋水餃
- ATR / close > 8% — 高波動
- close < 92% of SMA50 — 跌破中期趨勢

---

## 8. 輸出

### 8.1 Markdown 報告

`reports/YYYY-MM-DD.md` — 每日完整報告。`reports/YYYY-MM-DD_intraday_HHMM.md` 為小時 snapshot。

### 8.2 Telegram

每日報告（06:30 PT）— 完整文字，響鈴。
小時更新（07:30–12:30 PT）— **靜音**（不響），每則為一則精簡訊息。

### 8.3 給 AI_trader 的 watchlists

```
data/proposed_watchlist.json          # IC 候選（RSI 接近 50、流動性 OK）
data/proposed_phase2_watchlist.json   # 抄底候選（RSI < 35）
```

這是**提案**清單 — **不會**自動覆蓋 AI_trader 的 `data/`。請審核後手動複製：

```bash
cp data/proposed_watchlist.json /path/to/AI_trader/data/watchlist.json
```

---

## 9. 疑難排解

| 症狀 | 可能原因 | 解法 |
|---|---|---|
| `radar ping` 顯示 `Alpaca credentials missing` | `.env` 沒讀到 | 確認 `.env` 在專案根目錄、含 `ALPACA_API_KEY` + `ALPACA_SECRET_KEY` |
| `subscription does not permit querying recent SIP data` | free tier 用了 `ALPACA_DATA_FEED=sip` | 改成 `iex` |
| WebSocket `connection limit exceeded` | Free tier 只允許 1 個 WS；AI_trader 在用 | 改用 `radar poll trades`（REST）取代 `radar stream trades` |
| `ANTHROPIC_API_KEY missing — skipping LLM sentiment` | `.env` 沒填 key | 填上 key；或接受只用 StockTwits 也可運作 |
| commit 時 `gpg failed to sign the data` | gpg 不在 PATH | `git config gpg.program /opt/homebrew/bin/gpg` |
| Dashboard `/` 沒東西 | server 沒跑 | 啟動（見 §6）；`lsof -i :8765` 確認 |
| LaunchAgent 沒觸發 | Mac 在睡覺 | LaunchAgent **不會**喚醒睡眠的 Mac（除非用 caffeinate）。下次正常觸發。 |
| Form 4 解析錯誤 | `primary_doc` 是 HTML wrapper | `find_form4_xml_doc` 已修；確認在最新 commit |
| Pydantic warning `serialized value may not be as expected` | 上游 alpaca-py | 無害，可忽略 |
| `radar` 指令找不到 | venv 沒啟動 | `source .venv/bin/activate` |

---

## 10. 檔案結構

```
market_radar/
├── configs/settings.py            # pydantic-settings、.env 載入
├── src/
│   ├── alpaca/                    # client、screener、news、bars
│   │                              # trades_stream、trades_poller
│   │                              # options_chain
│   ├── db/                        # schema.sql、connection、migrations、repos
│   ├── edgar/                     # SEC EDGAR client + Form 4 parser
│   ├── indicators/                # technical（RSI/MACD/MA/BB/ATR）、eod runner
│   ├── options/                   # contract_parser、uoa_detector
│   │                              # flow_metrics、runner
│   ├── sentiment/                 # news_llm（Claude）、stocktwits、runner
│   ├── scoring/                   # normalize、heat、smart_money
│   │                              # sentiment_score、institutional
│   ├── recommend/                 # signals、risk_score、engine_v1、engine_v2
│   │                              # daily_pipeline、intraday_pipeline
│   ├── output/                    # markdown_report、telegram、watchlist_writer
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
└── logs/                          # launchd + 應用程式 logs
```

---

## 11. 更新

```bash
git pull
source .venv/bin/activate
pip install -e ".[dev,dashboard]"
radar db init                  # 套用任何新的 migration
```

如果 `pip install` 在 `pandas-ta` 失敗，那是已知過時 dep — 真正使用的是 `ta` library（`pyproject.toml` 已經改了）。
