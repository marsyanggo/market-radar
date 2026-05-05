#!/bin/bash
# Daily Market Radar pipeline — runs once, exits.
# Wired to LaunchAgent (com.marsyang.market_radar.daily.plist).
#
# Steps:
#   1. screener — refresh stocks universe
#   2. news fetch — pull last 24h news
#   3. poll trades (1 cycle) — backfill recent block trades via REST
#   4. report run — full pipeline + telegram + watchlists

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

# shellcheck disable=SC1091
source .venv/bin/activate

echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] starting market_radar daily run"

radar screener run
radar news fetch --hours 24
radar poll trades --cycles 1 --interval 60 || echo "block poll skipped/failed (non-fatal)"
radar report run --no-screener --telegram --watchlists

echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] market_radar daily run complete"
