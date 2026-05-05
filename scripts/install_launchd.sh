#!/bin/bash
# Install / uninstall the Market Radar daily LaunchAgent.
#
# Usage:
#   ./scripts/install_launchd.sh install
#   ./scripts/install_launchd.sh uninstall
#   ./scripts/install_launchd.sh status
#   ./scripts/install_launchd.sh trigger     # fire it now (one-shot test)

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLIST_NAME="com.marsyang.market_radar.daily"
PLIST_SRC="$PROJECT_ROOT/${PLIST_NAME}.plist"
PLIST_DST="$HOME/Library/LaunchAgents/${PLIST_NAME}.plist"

cmd="${1:-status}"

case "$cmd" in
    install)
        cp "$PLIST_SRC" "$PLIST_DST"
        launchctl unload "$PLIST_DST" 2>/dev/null || true
        launchctl load "$PLIST_DST"
        echo "✓ installed: $PLIST_DST"
        echo "  schedule: 06:30 Mac-local, daily"
        echo "  edit time in $PLIST_SRC then re-run install"
        ;;
    uninstall)
        if [[ -f "$PLIST_DST" ]]; then
            launchctl unload "$PLIST_DST" 2>/dev/null || true
            rm "$PLIST_DST"
            echo "✓ uninstalled: $PLIST_DST"
        else
            echo "(not installed)"
        fi
        ;;
    status)
        if launchctl list | grep -q "$PLIST_NAME"; then
            launchctl list | grep "$PLIST_NAME"
        else
            echo "(not loaded)"
        fi
        ;;
    trigger)
        echo "triggering one-shot run..."
        launchctl start "$PLIST_NAME"
        echo "fired. tail logs/launchd_stdout.log"
        ;;
    *)
        echo "usage: $0 {install|uninstall|status|trigger}"
        exit 1
        ;;
esac
