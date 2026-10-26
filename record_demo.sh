#!/usr/bin/env bash
# record_demo.sh — record a ~90-second demo GIF with VHS.
# Regenerates docs/demo.gif.
# Usage: bash record_demo.sh
set -euo pipefail

: "${ANTHROPIC_API_KEY:?ANTHROPIC_API_KEY must be set}"

if ! command -v vhs &>/dev/null; then
  echo "vhs not found."
  echo "Install with:  brew install vhs"
  echo "           or: go install github.com/charmbracelet/vhs@latest"
  exit 1
fi

# Ensure DB is seeded
python scripts/seed.py

# Start API in background
uvicorn agent_eval_lab.api:app --port 8000 &
API_PID=$!
trap "kill $API_PID 2>/dev/null || true" EXIT

# Wait for API to be ready (up to 15 s)
echo "Waiting for API on :8000..."
for i in $(seq 1 15); do
  if curl -sf http://localhost:8000/suites >/dev/null 2>&1; then
    echo "API ready."
    break
  fi
  sleep 1
done

# Record the tape
vhs docs/demo.tape

echo "docs/demo.gif written — open it to verify."
