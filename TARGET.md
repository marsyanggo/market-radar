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

### 1.1 資料庫設計
- [ ] `src/db/schema.sql`：建表 `stocks`、`trades_blocks`、`news`、`uoa`、`heat_scores`、`recommendations`
- [ ] `src/db/connection.py`：SQLite 連線池（`data/radar.db`）
- [ ] `src/db/migrations.py`：版本化 schema（簡單版即可）
- [ ] `src/db/repos.py`：CRUD repository（StocksRepo, TradesRepo, NewsRepo, UoaRepo）
- [ ] tests：`tests/test_db_repos.py`（基本 CRUD 測試）

### 1.2 Alpaca client wrapper
- [ ] `src/alpaca/client.py`：包裝 alpaca-py 的 REST/Stream client（自動 retry、rate limit）
- [ ] `src/alpaca/screener.py`：`get_most_actives()` + `get_movers()` → 寫入 `stocks` 表
- [ ] `scripts/daily_screener.py`：每日跑一次抓 Top 50 熱門股
- [ ] 驗證：跑一次 → DB 看到資料

### 1.3 News Stream（即時）
- [ ] `src/alpaca/news_stream.py`：訂閱 News WebSocket（Bloomberg/Benzinga）
- [ ] 寫入 `news` 表（symbol, headline, source, url, ts, content）
- [ ] 簡單 dedup（hash by url）
- [ ] `scripts/run_news_stream.py`：常駐執行
- [ ] 驗證：開盤跑 1 小時看到新聞流入

### 1.4 大單偵測（Trades WebSocket）
- [ ] `src/alpaca/trades_stream.py`：訂閱 Trades WebSocket（focus on Top 50 watchlist）
- [ ] 過濾 `size >= 10000` 寫入 `trades_blocks`
- [ ] 標記 buy/sell side（用 quote 中價判斷）
- [ ] `scripts/run_trades_stream.py`：常駐執行
- [ ] 驗證：開盤跑 1 小時看到大單記錄

---

## Phase 2 — 技術指標模組（1 天）

**目標**：每日盤後計算所有觀察股的技術指標，存進 DB。

- [ ] 安裝 `pandas-ta`（純 python，不用 TA-Lib C 套件）
- [ ] `src/indicators/technical.py`：函式 `compute_all(symbol, df_bars) -> dict`
  - [ ] RSI(14)、MACD、20/50/200 SMA、Bollinger Bands、ATR(14)
  - [ ] 52w high/low、距 52w high/low 百分比
  - [ ] Volume Profile（簡化版：近 20 日 POC）
- [ ] `src/alpaca/bars.py`：抓 daily/hourly bars（StockBars API）
- [ ] `src/db/schema.sql` 新增 `technical_indicators` 表
- [ ] `scripts/eod_indicators.py`：每日盤後（16:30 ET）對所有 watchlist 跑一次
- [ ] tests：`tests/test_technical.py`（用固定資料驗證指標數值）
- [ ] 驗證：對 NVDA 跑 → 數值 sanity check（RSI 0-100、MACD 有正負）

---

## Phase 3 — Heat Score 與初版推薦（1 天）⭐ MVP 里程碑

**目標**：用 Phase 1+2 的資料算 Heat Score，產出第一份推薦報告（不含 options）。

- [ ] `src/scoring/heat.py`：實作 Heat 公式
  ```
  Heat = 0.30 × volume_vs_adv
       + 0.25 × large_block_pct
       + 0.25 × options_uoa_count   # Phase 3.5 前先設 0
       + 0.20 × news_density
  ```
- [ ] `src/scoring/normalize.py`：把各指標歸一化到 0-100
- [ ] `src/recommend/engine_v1.py`：簡單版規則引擎
  - [ ] Heat > 70 + RSI < 70 → Watch
  - [ ] Heat > 80 + RSI < 70 + 突破 20MA → Strong Long
  - [ ] Heat > 90 + RSI > 80 → Avoid
- [ ] `src/output/markdown_report.py`：產生 `reports/YYYY-MM-DD.md`
- [ ] `scripts/daily_report.py`：08:00 ET 跑一次，整合所有 step
- [ ] 驗證：手動跑 → 看到 Top 10 + 推薦清單

---

## Phase 4 — Options Flow 偵測（2-3 天）⭐ 差異化核心

**目標**：偵測 UOA、Put/Call ratio、IV Skew 異常，整合進 Smart Money Score。

### 4.1 Options 資料管線
- [ ] `src/alpaca/options_stream.py`：訂閱 OptionDataStream
- [ ] `src/alpaca/options_chain.py`：抓 OptionChain（IV、Greeks、OI、volume）
- [ ] `src/db/schema.sql` 新增 `options_quotes`、`options_trades` 表

### 4.2 UOA 規則引擎
- [ ] `src/options/uoa_detector.py`：
  - [ ] size > 500 contracts
  - [ ] aggressive（成交在 ask 以上）
  - [ ] OTM 距離 5-15%
  - [ ] volume / OI > 2
- [ ] 寫入 `uoa` 表（symbol, contract, side, size, premium, ts, reason）

### 4.3 衍生指標
- [ ] `src/options/put_call_ratio.py`：1h 滾動 P/C ratio + 變化率
- [ ] `src/options/iv_skew.py`：put IV - call IV（25 delta），偵測突變
- [ ] `src/scoring/smart_money.py`：整合各訊號 → Smart Money Score 0-100

### 4.4 整合進推薦
- [ ] 更新 Heat 公式，加入 `options_uoa_count`
- [ ] `engine_v1.py` 加入 Smart Money Score 過濾條件
- [ ] 驗證：對 NVDA 跑 → 報告含 UOA 數量

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

## Phase 6 — 推薦引擎進階版（2 天）

**目標**：多訊號共振規則引擎、風險評分、回測。

- [ ] `src/recommend/engine_v2.py`：共振規則
  - [ ] 至少 3 個獨立訊號同向才推薦
  - [ ] 每個訊號獨立 score → 加權平均
- [ ] `src/recommend/risk_score.py`：
  - [ ] 過熱判斷（Heat > 90 + RSI > 80）
  - [ ] 財報前 3 天黑名單（yfinance earnings calendar）
  - [ ] 流動性過濾（avg volume > 500K）
- [ ] `src/backtest/replay.py`：用歷史資料模擬推薦 → 計算勝率
  - [ ] 假設進場 = 推薦次日開盤
  - [ ] 5 日 / 20 日後報酬
  - [ ] 勝率、平均報酬、Sharpe
- [ ] tests：`tests/test_engine_v2.py`
- [ ] 驗證：跑近 30 天回測，輸出勝率報表

---

## Phase 7 — 自動化與輸出（1 天）

**目標**：每日全自動產出 + 推送 Telegram + 整合 AI_trader。

- [ ] `src/output/telegram.py`：複用 AI_trader 的 bot，發送格式化報告
- [ ] `src/output/watchlist_writer.py`：
  - [ ] IV Rank 低 + 未爆量 → `data/watchlist.json`
  - [ ] RSI 超賣 + 大單買進 → `data/phase2_watchlist.json`
- [ ] `scripts/run_daily.sh`：整合所有 step（screener → indicators → score → recommend → output）
- [ ] LaunchAgent plist：`com.marsyang.market_radar.plist`（每日 08:00 ET）
- [ ] `scripts/install_launchd.sh`：安裝/卸載 LaunchAgent
- [ ] 驗證：手動觸發 LaunchAgent → 收到 Telegram 報告

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
