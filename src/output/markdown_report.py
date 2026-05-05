"""Render the daily Market Radar report as Markdown."""

from datetime import datetime, timezone
from pathlib import Path

from configs.settings import settings
from src.db.connection import get_conn


def render_report(as_of: str) -> str:
    with get_conn() as conn:
        heat_rows = conn.execute(
            """
            SELECT h.symbol, h.heat_score, h.volume_vs_adv, h.options_uoa_count, h.news_density,
                   t.close, t.rsi_14, t.sma_20, t.pct_from_high_52w,
                   f.put_call_ratio, f.iv_skew_25d, f.smart_money_score, f.uoa_count,
                   s.sentiment_score AS sent
            FROM heat_scores h
            LEFT JOIN technical_indicators t
              ON t.symbol = h.symbol AND t.as_of = h.as_of
            LEFT JOIN option_flow f
              ON f.symbol = h.symbol AND f.as_of = h.as_of
            LEFT JOIN sentiment_daily s
              ON s.symbol = h.symbol AND s.as_of = h.as_of
            WHERE h.as_of = ?
            ORDER BY h.heat_score DESC
            LIMIT 10
            """,
            (as_of,),
        ).fetchall()

        sm_rows = conn.execute(
            """
            SELECT f.symbol, f.smart_money_score, f.uoa_count, f.put_call_ratio, f.iv_skew_25d
            FROM option_flow f
            WHERE f.as_of = ? AND f.smart_money_score IS NOT NULL
            ORDER BY f.smart_money_score DESC
            LIMIT 10
            """,
            (as_of,),
        ).fetchall()

        recs = conn.execute(
            "SELECT * FROM recommendations WHERE as_of = ? ORDER BY heat_score DESC",
            (as_of,),
        ).fetchall()

    lines: list[str] = []
    lines.append(f"# 📡 Market Radar Daily — {as_of}\n")
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines.append(f"_Generated {generated}_\n")
    lines.append("---\n")

    # Top heat
    lines.append("## 🔥 Top Heat Today\n")
    if not heat_rows:
        lines.append("_no heat data_\n")
    else:
        lines.append("| # | Symbol | Heat | Vol×ADV | RSI | Close | UOA | P/C | SM | Sent |")
        lines.append("|---|--------|------|---------|-----|-------|-----|-----|----|------|")
        for i, r in enumerate(heat_rows, 1):
            vol = f"{r['volume_vs_adv']:.2f}×" if r["volume_vs_adv"] else "—"
            rsi = f"{r['rsi_14']:.0f}" if r["rsi_14"] else "—"
            close = f"${r['close']:.2f}" if r["close"] else "—"
            uoa = str(r["uoa_count"]) if r["uoa_count"] else "—"
            pc = f"{r['put_call_ratio']:.2f}" if r["put_call_ratio"] else "—"
            sm = f"{r['smart_money_score']:.0f}" if r["smart_money_score"] is not None else "—"
            sent = f"{r['sent']:.0f}" if r["sent"] is not None else "—"
            lines.append(
                f"| {i} | **{r['symbol']}** | {r['heat_score']:.0f} | {vol} | {rsi} | {close} | {uoa} | {pc} | {sm} | {sent} |"
            )
    lines.append("")

    # Smart money flow
    if sm_rows:
        lines.append("## 💰 Smart Money Flow\n")
        lines.append("| # | Symbol | SM Score | UOA | P/C | IV Skew |")
        lines.append("|---|--------|----------|-----|-----|---------|")
        for i, r in enumerate(sm_rows, 1):
            uoa = str(r["uoa_count"]) if r["uoa_count"] else "—"
            pc = f"{r['put_call_ratio']:.2f}" if r["put_call_ratio"] else "—"
            skew = f"{r['iv_skew_25d']:+.3f}" if r["iv_skew_25d"] is not None else "—"
            lines.append(
                f"| {i} | **{r['symbol']}** | {r['smart_money_score']:.0f} | {uoa} | {pc} | {skew} |"
            )
        lines.append("")

    # Recommendations grouped by category
    lines.append("## 🎯 Today's Recommendations\n")
    by_cat: dict[str, list] = {"strong_long": [], "watch": [], "avoid": []}
    for r in recs:
        if r["category"] in by_cat:
            by_cat[r["category"]].append(r)

    if by_cat["strong_long"]:
        lines.append("### ✅ Strong Long")
        for r in by_cat["strong_long"]:
            close = f"${r['entry_price']:.2f}" if r["entry_price"] else "—"
            lines.append(f"- **{r['symbol']}** — Heat {r['heat_score']:.0f}, entry ~{close}")
        lines.append("")
    if by_cat["watch"]:
        lines.append("### 📊 Watch")
        for r in by_cat["watch"]:
            lines.append(f"- **{r['symbol']}** — Heat {r['heat_score']:.0f}")
        lines.append("")
    if by_cat["avoid"]:
        lines.append("### ❌ Avoid")
        for r in by_cat["avoid"]:
            lines.append(f"- **{r['symbol']}** — overheated (Heat {r['heat_score']:.0f})")
        lines.append("")
    if not any(by_cat.values()):
        lines.append("_no recommendations triggered today_\n")

    lines.append("---")
    lines.append("_Market Radar v0.0.1 — Heat = volume + news + UOA + block;")
    lines.append("Smart Money = block imbalance + UOA call/put + P/C ratio + IV skew._")

    return "\n".join(lines)


def write_report(as_of: str) -> Path:
    settings.reports_dir.mkdir(parents=True, exist_ok=True)
    path = settings.reports_dir / f"{as_of}.md"
    path.write_text(render_report(as_of), encoding="utf-8")
    return path
