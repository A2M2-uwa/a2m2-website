#!/usr/bin/env bash
# Capture headless Firefox screenshots of the site for visual review.
#
# Usage:
#   tools/shoot.sh <page.html> [width] [height] [label]
#
# Notes
#   - Requires a local server on 127.0.0.1:8765 (python3 -m http.server 8765).
#   - Output goes to ~/shots, and the Firefox profile lives in ~/ffprof,
#     because this Firefox build cannot read paths outside $HOME.
set -euo pipefail

PAGE="${1:-index.html}"
WIDTH="${2:-1440}"
HEIGHT="${3:-1300}"
LABEL="${4:-$(basename "$PAGE" .html)}"

SHOTS="$HOME/shots"
PROFILE="$HOME/ffprof"
mkdir -p "$SHOTS" "$PROFILE"

OUT="$SHOTS/${LABEL}.png"
rm -f "$OUT"

MOZ_HEADLESS=1 timeout 200 firefox \
  --headless \
  --profile "$PROFILE" \
  --no-remote \
  --window-size="${WIDTH},${HEIGHT}" \
  --screenshot "$OUT" \
  "http://127.0.0.1:8765/${PAGE}" >/dev/null 2>&1 || true

if [[ -f "$OUT" ]]; then
  echo "ok   $OUT"
else
  echo "FAIL $PAGE" >&2
  exit 1
fi
