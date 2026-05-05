# Market Radar — 每日趨勢分析與選股推薦系統

> 獨立於 AI_trader 之外的新案子。AI_trader 負責「執行」，Market Radar 負責「找標的」。
>
> 兩者透過 `data/watchlist.json` 介接：Market Radar 每日推薦 → 寫入 watchlist → AI_trader 自動掃描開倉。
>
> _建立日期：2026-05-05_
> _詳細規劃日期：2026-05-04_

---

## 專案總覽

每日盤前產出「**今天該關注哪些股票**」的智能報告：
- 🔥 哪些股票熱門（成交量、新聞、UOA）
- 💰 聰明錢往哪裡流（大單、Options Flow、Dark Pool）
- 📈 哪些有明確進場機會（多指標共振）
- 🚨 哪些要避開（過熱、技術破位、機構出貨）

**最終輸出**：每天早上 Telegram + Markdown 報告，10 個推薦標的 + 進場理由 + 風險評分。

---

## Phase 0 — 專案初始化（0.5 天） ✅

**目標**：建立 repo 骨架與基礎設定，能跑 hello world。

- [x] 建立目錄結構：`market_radar/{src,data,reports,tests,scripts,configs,logs}` + 子模組（db, alpaca, indicators, scoring, recommend, output, sentiment, options, edgar）
- [x] `pyproject.toml`（python 3.10+、alpaca-py、pandas、ta、pydantic-settings、loguru、click、anthropic、yfinance、py_vollib；optional dev/sentiment groups）
- [x] `.env.example`（Alpaca、Telegram、Anthropic、Reddit key + DB / log / reports / aitrader paths）
- [x] `configs/settings.py`（pydantic-settings 讀 .env，含 is_paper helper）
- [x] `src/logger.py`（loguru 設定，輸出到 `logs/radar_YYYY-MM-DD.log` + stderr，rotate daily, retain 30 days）
- [x] `src/cli.py`（click group，`radar ping` command）
- [x] `README.md` 簡介 + 啟動方式
- [x] git init + `.gitignore`（含 `.env`、`logs/`、`*.db`、`reports/`、`.venv/`）
- [x] GitHub repo `marsyanggo/market-radar`（private）+ GPG-signed initial commit + push
- [x] 驗證：`radar ping` → 印出 "Market Radar OK" + log 檔案產生

---

## Phase 1 — 基礎資料管線（1-2 天）

**目標**：能每日抓熱門股、即時偵測大單、接收新聞，存到 SQLite。

### 1.1 資料庫設計 ✅
- [x] `src/db/schema.sql`：建表 `stocks`、`trades_blocks`、`news`、`uoa`、`heat_scores`、`recommendations`、`technical_indicators`、`schema_version`
- [x] `src/db/connection.py`：SQLite 連線（WAL mode、foreign keys、Row factory、transaction context manager）
- [x] `src/db/migrations.py`：版本化 schema（base + 線性 migrations）
- [x] `src/db/repos.py`：StocksRepo / TradesRepo / NewsRepo / UoaRepo / HeatScoresRepo / RecommendationsRepo（with dataclass models）
- [x] `radar db init` CLI command
- [x] tests：`tests/test_db_repos.py`（10 tests，全過）

### 1.2 Alpaca client wrapper ✅
- [x] `src/alpaca/client.py`：ScreenerClient + StockHistoricalDataClient factories + `with_retry` decorator（exponential backoff）
- [x] `src/alpaca/screener.py`：`fetch_most_actives()` + `fetch_market_movers()` → upsert into `stocks`
- [x] `scripts/daily_screener.py` + `radar screener run` CLI command
- [x] 驗證：跑一次 → DB 38 筆資料（20 most-actives + 20 movers，去重）

### 1.3 News Fetcher（REST poller） ✅
- [x] `src/alpaca/news.py`：REST 版本（`fetch_news` + `persist_news` + `fetch_and_persist` + `run_news_poller`）
  - WebSocket 版略過（Alpaca free tier 1 個 WS 已被佔用，新聞 10 分鐘 cadence 足夠）
- [x] 寫入 `news` 表，dedup by `external_id`（unique constraint）
- [x] `radar news fetch` (one-shot) + `radar news poll` (long-running) CLI
- [x] **修 bug**：`daily_pipeline` 原本用「今日凌晨」當 since_iso → 漏算前日晚間新聞；改成 24h rolling window
- [x] 驗證：抓到 77 筆新聞，dedup 正確（重跑 0 inserted）；SKK/PN heat 從 30 升到 50（news_density=8）

### 1.4 大單偵測（Trades WebSocket + REST polling fallback） ✅
- [x] `src/alpaca/trades_stream.py`：WebSocket 版（subscribe trades + quotes，buffer + flush，signal handlers）
- [x] `src/alpaca/trades_poller.py`：REST polling 版（fallback：因 Alpaca free tier 限制 1 WS 連線，AI_trader price_stream 已佔用）
- [x] Lee-Ready side classification（`classify_side` shared by 兩版）：trade ≥ ask → buy / ≤ bid → sell / 中價以上 buy / 中價以下 sell
- [x] 過濾 `size >= threshold`（預設 10K）寫入 `trades_blocks`，REST 版用 `(symbol, ts, price, size, exchange)` 去重
- [x] `scripts/run_trades_stream.py` + `radar stream trades` (WS) + `radar poll trades` (REST) CLI commands
- [x] tests：`test_trades_stream.py`（7 個 side classification tests）；總計 34/34 過
- [x] 驗證：poller 抓過去 24h trades → DB 寫入 2 筆 (NVDA 8081 sell, AAPL 5420 unknown)
- [ ] **已知限制**：Alpaca free tier 同時只允許 1 個 WS；要使用 stream 版需先停 AI_trader 或升級帳號。日常使用 `radar poll trades` 即可

---

## Phase 2 — 技術指標模組（1 天） ✅

**目標**：每日盤後計算所有觀察股的技術指標，存進 DB。

- [x] 安裝 `ta` library（取代停更的 pandas-ta）
- [x] `src/indicators/technical.py`：`compute_all(symbol, df_bars, as_of) -> TechnicalSnapshot`
  - [x] RSI(14)、MACD（12/26/9）、20/50/200 SMA、Bollinger Bands(20,2)、ATR(14)
  - [x] 52w high/low、距 52w high/low 百分比
  - [ ] Volume Profile（簡化版：近 20 日 POC） — 延後到需要時再做
- [x] `src/alpaca/bars.py`：`fetch_daily_bars` + `fetch_daily_bars_batch`（含 IEX feed 支援）
- [x] `technical_indicators` 表（Phase 1.1 已建）+ `TechnicalsRepo.upsert/get`
- [x] `src/indicators/eod.py`：runner（依 stocks 表逐批抓 bars + 算指標 + upsert）
- [x] `scripts/eod_indicators.py` + `radar indicators run` CLI
- [x] tests：`tests/test_technical.py`（4 tests，過 14/14 全測試）
- [x] 驗證：對 38 檔跑 → DB 寫入 37 筆（1 檔資料不足 skipped）；NVDA close=198.56 RSI=53 MACD~0 52w-high pct=-8.3%

---

## Phase 3 — Heat Score 與初版推薦（1 天）⭐ MVP 里程碑 ✅

**目標**：用 Phase 1+2 的資料算 Heat Score，產出第一份推薦報告（不含 options）。

- [x] `src/scoring/normalize.py`：linear/clamp 工具 + 4 個 norm_*  函式（0-100）
- [x] `src/scoring/heat.py`：Heat 公式 + `compute_heat()` + `volume_vs_adv_from_bars()`
- [x] `src/recommend/engine_v1.py`：3 規則 (avoid > 90+RSI>80, strong_long > 80+RSI<70+>SMA20, watch > 70)
- [x] `src/output/markdown_report.py`：render + write to `reports/YYYY-MM-DD.md`
- [x] `src/recommend/daily_pipeline.py`：orchestrator (screener→bars→technicals+heat→classify→report)
- [x] `scripts/daily_report.py` + `radar report run` CLI
- [x] tests：`test_scoring.py` (7) + `test_engine_v1.py` (6)；總計 27/27 過
- [x] 驗證：`radar report run --no-screener` → reports/2026-05-05.md，38 universe / 37 technicals / 38 heats
- [x] **MVP 觀察**：所有 heat 目前都 = 30（只有 volume weight 0.30 啟用）；recommendations 空白屬預期 — 待 Phase 1.3 (news) + 1.4 (block) + 4 (UOA) 接上後 heat 才會真正分散

---

## Phase 4 — Options Flow 偵測（2-3 天）⭐ 差異化核心 ✅

**目標**：偵測 UOA、Put/Call ratio、IV Skew 異常，整合進 Smart Money Score。

### 4.1 Options 資料管線 ✅
- [x] `src/options/contract_parser.py`：OCC 符號解析（regex + dataclass + otm_pct helper）
- [x] `src/alpaca/options_chain.py`：`fetch_chain()` + `fetch_recent_trades()`（snapshot 含 IV/Greeks/quote/trade）
- [x] DB migration v2: `option_snapshots` 表（per-day per-contract snapshot；UNIQUE on contract+as_of）
- [x] DB migration v3: `option_flow` 表（per-day per-symbol summary：P/C、IV skew、UOA count、Smart Money）
- [x] `OptionSnapshotsRepo` + `OptionFlowRepo`
- [ ] WebSocket stream — 略過（同 Phase 1.4，free tier 1 連線限制）

### 4.2 UOA 規則引擎 ✅
- [x] `src/options/uoa_detector.py`：rules `is_unusual()` + `classify_side()` + `to_uoa_event()` + `detect_and_persist()`
  - size ≥ 50 contracts (threshold lowered for snapshot-based detection)
  - aggressive（last_price ≥ ask → buy / ≤ bid → sell）
  - OTM 5-25%
  - volume/OI 跳過（free tier 沒 OI feed）

### 4.3 衍生指標 ✅
- [x] `src/options/flow_metrics.py`：`compute_flow()` → P/C ratio (puts/calls) + IV skew(25Δ)
- [x] `src/scoring/smart_money.py`：4 子分數加權平均 (block 0.30 + UOA 0.30 + P/C 0.20 + skew 0.20) → 0-100

### 4.4 整合進推薦 ✅
- [x] `src/options/runner.py`：`run_for_symbol()` + `run_options_pipeline()`（chain → snapshots → UOA → flow → smart money）
- [x] `daily_pipeline` 加 `run_options` flag（top-N by volume，bound API cost）
- [x] Heat 公式 uoa_count 真正啟用（read from `uoa` table after options ran）
- [x] `radar options run --symbol X` + `radar report run --options --options-top N` CLI
- [x] markdown report 加 UOA / P/C / SM 欄位 + 新「Smart Money Flow」section
- [x] tests：`test_options.py` (12 tests，含 OCC 解析、smart money 各子分數、組合)；總計 46/46 過
- [x] 驗證：NVDA 抓 4790 snapshots → 18 UOA；PLTR 2528 snapshots → 4 UOA；TZA/NOK 衝到 SM 75（bullish IV skew）

---

## Phase 5 — 情緒分析（1-2 天）

**目標**：加入散戶情緒（反向指標）+ 新聞情緒。

- [ ] `src/sentiment/reddit.py`：抓 r/wallstreetbets、r/stocks 提及次數（PRAW）
- [ ] `src/sentiment/stocktwits.py`：StockTwits API bullish/bearish 比
- [ ] `src/sentiment/google_trends.py`：pytrends（注意 rate limit）
- [ ] `src/sentiment/news_llm.py`：Claude API 對新聞 headline 情緒打分（-1 ~ +1）
  - [ ] 用 Haiku 4.5 控成本
  - [ ] batch 處理 + prompt caching
- [ ] `src/scoring/sentiment_score.py`：整合 → Sentiment Score 0-100
- [ ] 驗證：對熱門股跑 → 看到情緒分數

---

## Phase 6 — 推薦引擎進階版（2 天） ✅

**目標**：多訊號共振規則引擎、風險評分、回測。

- [x] `src/recommend/signals.py`：7 個獨立 scorer (heat / smart_money / technical_alignment / rsi / volume / options_skew / 52w)，每個 0-100，None 若資料不足
- [x] `src/recommend/risk_score.py`：assess_risk → veto + score + reasons
  - veto: overheated (heat>90+RSI>80) / earnings 內 ≤4 天
  - score: 流動性 (<500K avg vol) / penny stock (<$5) / 高 ATR (>8%) / 跌破 50MA 8%
- [x] `src/recommend/engine_v2.py`：classify based on bullish/bearish 共振計數
  - strong_long: ≥4 bullish, ≤1 bearish, weighted ≥ 65, no veto
  - watch: ≥3 bullish, no veto
  - avoid: veto OR (≥3 bearish + heat ≥ 60)
- [x] daily_pipeline 接 v2（v1 fallback via `use_v2=False`）；reason 欄位記錄 weighted_score / bullish_signals / risk_reasons
- [x] `src/backtest/replay.py`：歷史 bar 重播
  - 對每天 D：computeAll(bars[:D]) → engine_v2 classify → entry=open[D+1]
  - 5d / 20d return；hit rate；Sharpe (5d)
  - 注意：歷史只能用 technical+volume signals（SM / news / UOA 沒有歷史資料）
- [x] `radar backtest run --lookback 60 --symbol ...` CLI
- [x] tests：`test_engine_v2.py`（17 tests：signals + risk + classify）；總計 62/62 過
- [x] 驗證：18 個推薦產生（含 1 strong_long: BB；NOK watch with SM 75）；BZAI/SKK 風險原因正確標出
- [x] **回測發現**（10 mega caps, 60d lookback）：watch 36.6% win 5d / strong_long 0% — pure-technical 不夠，正好驗證 Phase 4 options data 的必要性

---

## Phase 7 — 自動化與輸出（1 天） ✅

**目標**：每日全自動產出 + 推送 Telegram + 整合 AI_trader。

- [x] `src/output/telegram.py`：httpx-based bot wrapper（共用 AI_trader 的 token），auto-split 4096 char limit
- [x] `src/output/watchlist_writer.py`：寫到 `data/proposed_watchlist.json` + `data/proposed_phase2_watchlist.json`
  - 預設 heuristic（待 Phase 4 IV Rank 接好後升級）：IC = RSI 接近 50 + 流動性 OK；Phase2 = RSI < 35
  - 故意寫到「proposed」前綴 — 不直接覆蓋 AI_trader hand-curated watchlists，需手動 promote
- [x] `daily_pipeline.run_daily_pipeline()` 加 `send_telegram` + `write_watchlists_files` flags
- [x] `radar telegram test` + `radar report run --telegram --watchlists` CLI
- [x] `scripts/run_daily.sh`：screener → news → poll trades (1 cycle) → report (with telegram + watchlists)
- [x] `com.marsyang.market_radar.daily.plist`：StartCalendarInterval 06:30 Mac-local
- [x] `scripts/install_launchd.sh`：install / uninstall / status / trigger sub-commands
- [x] 驗證：`bash scripts/run_daily.sh` 完整跑通，universe=93、ic=18、phase2=6、telegram OK

---

## Phase 8 — 進階聰明錢追蹤（選配，2-3 天）

**目標**：機構與內部人動態。

- [ ] `src/edgar/client.py`：SEC EDGAR API 包裝
- [ ] `src/edgar/form_13f.py`：每季抓 13F → 偵測新進/出清部位
- [ ] `src/edgar/form_4.py`：每日抓內部人交易（買賣金額、職位）
- [ ] `src/scoring/institutional.py`：整合進 Smart Money Score
- [ ] （選配付費）`src/polygon/dark_pool.py`：DP 比例

---

## Phase 9 — Web Dashboard（選配，3-5 天）

**目標**：視覺化即時資訊。

- [ ] `dashboard/api/`：FastAPI（routes：/heat、/smart_money、/recommendations、/stock/{symbol}）
- [ ] `dashboard/web/`：React + Vite + TailwindCSS
- [ ] 即時熱度榜（WebSocket push）
- [ ] 聰明錢流向圖（chart.js）
- [ ] 個股詳細頁（K 線 + 指標 + UOA 列表）
- [ ] 部署：本機 docker-compose 起 nginx + api + web

---

## 實作順序建議（MVP 優先）

```
Phase 0  → Phase 1 (1.1, 1.2 先做) → Phase 2 → Phase 3 (MVP 第一份報告) ⭐
   ↓
Phase 1.3, 1.4 (即時 stream，補強資料)
   ↓
Phase 4 (差異化) → Phase 5 → Phase 6 (推薦變強)
   ↓
Phase 7 (自動化上線)
   ↓
Phase 8 / 9 (選配)
```

**第一個可驗證的里程碑：Phase 3 結束** — 能用 1-2 天的累積資料產出第一份手動跑的推薦報告。

---

## 介面契約（與 AI_trader）

- Market Radar 只**推薦**，不**下單**
- AI_trader 只**執行**，不**選股**
- 介接檔案：
  - `data/watchlist.json` — 適合 IC 的標的
  - `data/phase2_watchlist.json` — 適合抄底的標的
- Schema 由兩邊協商，先 freeze 一版簡單格式

---

## 技術棧

| 層級 | 選擇 |
|------|------|
| 語言 | Python 3.10+ |
| 資料 | SQLite（data/radar.db） |
| 技術指標 | pandas-ta |
| 期權 | py_vollib（複用 AI_trader）|
| Alpaca SDK | alpaca-py |
| LLM | Claude Haiku 4.5（情緒打分）|
| 排程 | macOS launchd |
| 通知 | Telegram Bot（共用 AI_trader）|
| 日誌 | loguru |
| 設定 | pydantic-settings |
| 前端（選配） | FastAPI + React + Vite |
