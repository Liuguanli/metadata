#!/usr/bin/env bash
set -euo pipefail

if [ "${1:-}" = "" ]; then
  echo "Usage: bash paper/new_review_cycle.sh <cycle-id>"
  echo "Example: bash paper/new_review_cycle.sh c2026-05-08-v1"
  exit 1
fi

CYCLE_ID="$1"
BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
TEMPLATE="${BASE_DIR}/reviews/TEMPLATE.md"
TARGET="${BASE_DIR}/reviews/${CYCLE_ID}.md"

if [ -f "$TARGET" ]; then
  echo "Target already exists: $TARGET"
  exit 1
fi

cp "$TEMPLATE" "$TARGET"
DATE_STR="$(date +%F)"

sed -i.bak "s/^- Cycle ID:.*/- Cycle ID: ${CYCLE_ID}/" "$TARGET"
sed -i.bak "s/^- Date:.*/- Date: ${DATE_STR}/" "$TARGET"
rm -f "${TARGET}.bak"

echo "Created review cycle file: $TARGET"
