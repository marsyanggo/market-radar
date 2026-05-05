#!/bin/bash
# Lite intraday market_radar run — fired hourly during US market hours.
# Skips: options chain (heavy), LLM news scoring, watchlists.
# Includes: screener, news fetch (last 2h), bars/technicals, heat, classify, telegram.

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

# Skip on weekends (US market closed). 6=Sat, 7=Sun.
DOW=$(date +%u)
if [[ "$DOW" -ge 6 ]]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] weekend — skipping intraday run"
    exit 0
fi

# shellcheck disable=SC1091
source .venv/bin/activate

echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] intraday run starting"
python -c "from src.recommend.intraday_pipeline import run_intraday_pipeline; run_intraday_pipeline()"
echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] intraday run complete"
