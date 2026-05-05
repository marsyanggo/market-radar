#!/bin/bash
# Install / uninstall the Market Radar LaunchAgents.
#
# Usage:
#   ./scripts/install_launchd.sh install              # install both daily + intraday
#   ./scripts/install_launchd.sh install daily        # install only daily
#   ./scripts/install_launchd.sh install intraday     # install only intraday
#   ./scripts/install_launchd.sh uninstall            # uninstall both
#   ./scripts/install_launchd.sh status               # show status
#   ./scripts/install_launchd.sh trigger daily        # fire daily once
#   ./scripts/install_launchd.sh trigger intraday     # fire intraday once

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DAILY_LABEL="com.marsyang.market_radar.daily"
INTRADAY_LABEL="com.marsyang.market_radar.intraday"

label_for() {
    case "$1" in
        daily)    echo "$DAILY_LABEL" ;;
        intraday) echo "$INTRADAY_LABEL" ;;
        *)        echo ""; return 1 ;;
    esac
}

install_one() {
    local key="$1"
    local label
    label=$(label_for "$key") || { echo "unknown plist: $key"; return 1; }
    local src="$PROJECT_ROOT/${label}.plist"
    local dst="$HOME/Library/LaunchAgents/${label}.plist"
    cp "$src" "$dst"
    launchctl unload "$dst" 2>/dev/null || true
    launchctl load "$dst"
    echo "✓ installed: $dst"
}

uninstall_one() {
    local key="$1"
    local label
    label=$(label_for "$key") || { echo "unknown plist: $key"; return 1; }
    local dst="$HOME/Library/LaunchAgents/${label}.plist"
    if [[ -f "$dst" ]]; then
        launchctl unload "$dst" 2>/dev/null || true
        rm "$dst"
        echo "✓ uninstalled: $dst"
    else
        echo "($label not installed)"
    fi
}

cmd="${1:-status}"
which="${2:-all}"

case "$cmd" in
    install)
        if [[ "$which" == "all" ]]; then
            install_one daily
            install_one intraday
        else
            install_one "$which"
        fi
        echo ""
        echo "  daily:    06:30 Mac-local"
        echo "  intraday: 07:30 / 08:30 / 09:30 / 10:30 / 11:30 / 12:30 Mac-local"
        echo "            (weekend skip in run_intraday.sh)"
        ;;
    uninstall)
        if [[ "$which" == "all" ]]; then
            uninstall_one daily
            uninstall_one intraday
        else
            uninstall_one "$which"
        fi
        ;;
    status)
        for key in daily intraday; do
            label=$(label_for "$key")
            if launchctl list | grep -q "$label"; then
                launchctl list | grep "$label"
            else
                echo "$label: (not loaded)"
            fi
        done
        ;;
    trigger)
        if [[ "$which" == "all" ]]; then
            echo "specify daily or intraday"
            exit 1
        fi
        label=$(label_for "$which") || { echo "unknown: $which"; exit 1; }
        echo "triggering $label..."
        launchctl start "$label"
        echo "fired."
        ;;
    *)
        echo "usage: $0 {install|uninstall|status|trigger} [daily|intraday|all]"
        exit 1
        ;;
esac
