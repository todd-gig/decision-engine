#!/usr/bin/env bash
# Install the Drift Sentinel as a weekly launchd job.
#
# Sets it to run Sundays at 8 AM local time, scanning local + downloads
# + GitHub, and posting a digest to Slack (requires SLACK_WEBHOOK_URL).
#
# Usage:
#   bash install_launchd.sh              # install
#   bash install_launchd.sh uninstall    # remove
#
# After install, verify with:  launchctl list | grep drift-sentinel
# Trigger manually with:       launchctl start com.gigaton.drift-sentinel
set -euo pipefail

PLIST_NAME="com.gigaton.drift-sentinel.plist"
SRC="$(cd "$(dirname "$0")" && pwd)/${PLIST_NAME}"
DST="${HOME}/Library/LaunchAgents/${PLIST_NAME}"

if [[ "${1:-}" == "uninstall" ]]; then
  launchctl unload -w "${DST}" 2>/dev/null || true
  rm -f "${DST}"
  echo "[install] uninstalled ${PLIST_NAME}"
  exit 0
fi

mkdir -p "${HOME}/Library/LaunchAgents"
cp "${SRC}" "${DST}"

# Reload if already loaded
launchctl unload -w "${DST}" 2>/dev/null || true
launchctl load -w "${DST}"

echo "[install] installed ${PLIST_NAME}"
echo "[install] scheduled: Sundays @ 08:00 local time"
echo "[install] verify:    launchctl list | grep drift-sentinel"
echo "[install] manual:    launchctl start com.gigaton.drift-sentinel"
echo
echo "Set SLACK_WEBHOOK_URL in your shell profile (or hard-code in the plist)"
echo "before the next scheduled run, or Slack posting will be skipped."
