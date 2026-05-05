# Market Radar

每日盤前產出「**今天該關注哪些股票**」的智能報告：熱度、聰明錢流向、進場機會、風險警示。

> 獨立於 [AI_trader](../AI_trader) 之外的選股系統。AI_trader 負責「執行」，Market Radar 負責「找標的」。
> 兩者透過 `data/watchlist.json` 介接。

## 功能

- 🔥 **Heat Score**：成交量、大單佔比、UOA、新聞密度
- 💰 **Smart Money**：Block trade imbalance、Options flow、IV skew、Dark pool
- 📈 **技術指標**：RSI / MACD / MA / BB / ATR / 52w high-low
- 📊 **情緒**：Reddit / StockTwits / Google Trends / News LLM
- 🎯 **推薦引擎**：多訊號共振，每日 Top 10 + Strong/Watch/Avoid 分類
- 📤 **輸出**：Telegram + Markdown 日報 + 寫入 AI_trader watchlist

## 開發狀態

詳見 [TARGET.md](./TARGET.md)。目前在 **Phase 0 — 專案初始化** 階段。

## 技術棧

Python 3.10+ · alpaca-py · pandas-ta · py_vollib · SQLite · loguru · Claude Haiku 4.5 · macOS launchd · Telegram Bot

## 啟動

```bash
# TODO: 待 Phase 0 完成後填入
```

## License

Private. Personal project.
