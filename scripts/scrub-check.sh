#!/bin/sh
set -eu

ROOT_DIR="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

echo "Running scrub checks in $ROOT_DIR"

TRACKED_FILES="$(mktemp)"
trap 'rm -f "$TRACKED_FILES"' EXIT HUP INT TERM
git ls-files > "$TRACKED_FILES"

if [ -s "$TRACKED_FILES" ]; then
  SEARCH_FILES="$(grep -v '^scripts/scrub-check\.sh$' "$TRACKED_FILES")"
  if [ -n "$SEARCH_FILES" ]; then
    # tracked repo paths do not contain spaces, so positional args keep the invocation portable.
    set -- $SEARCH_FILES
    if rg -n \
      -e '/Users/heeho/' \
      -e '44258118' \
      -e 'Application Support/financier-v2' \
      -e 'financier-v2/scripts/toss-bridge' \
      -e 'accountNo":[0-9]' \
      -e 'XSRF-TOKEN=[^"]{12,}' \
      -e 'browserSessionId[^[:space:]]{8,}' \
      -e 'WTS-BROWSER-TAB-ID[^[:space:]]{8,}' \
      -- "$@"; then
      echo "Scrub check failed"
      exit 1
    fi
  fi
fi

if git ls-files | grep -E 'chrome-profile|token$|daemon\.pid$|daemon\.log$|playwright-storage-state' >/dev/null; then
  echo "Scrub check failed: runtime artifact tracked"
  exit 1
fi

echo "Scrub check passed"
