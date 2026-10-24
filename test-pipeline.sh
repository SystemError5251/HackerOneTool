#!/usr/bin/env bash
# test-pipeline.sh — one-shot, offline smoke test of the OpenCode integration.
#
# Boots the mock model server, runs OpenCode against it through analyze.sh,
# asserts the mock replied, and tears the server down. No real provider, API
# key, or network to an LLM required — suitable for CI.
#
# Exit 0 = pipeline works, non-zero = failure.
#
# Usage:
#   ./test-pipeline.sh
#
# The port is fixed at 8787 to match the `mock` provider's baseURL in
# opencode.json, so OpenCode actually reaches the server it boots.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
port="8787"
model="mock/mock-1"
server_pid=""

cleanup() {
  if [[ -n "$server_pid" ]]; then
    kill "$server_pid" 2>/dev/null || true
    wait "$server_pid" 2>/dev/null || true
  fi
  # fallback: make sure nothing we started is still bound to the port
  pkill -f "mock_model_server.py --port $port" 2>/dev/null || true
}
trap cleanup EXIT

fail() { echo "FAIL: $*" >&2; exit 1; }

command -v opencode >/dev/null 2>&1 || fail "opencode not installed"

# --- boot the mock server ---
echo "== booting mock model on 127.0.0.1:$port =="
python3 "$here/mock_model_server.py" --port "$port" >/tmp/mock-pipeline.log 2>&1 &
server_pid=$!

# wait up to 10s for it to accept connections
for _ in $(seq 1 20); do
  if curl -sS --max-time 1 "http://127.0.0.1:$port/v1/models" >/dev/null 2>&1; then
    ready=1; break
  fi
  kill -0 "$server_pid" 2>/dev/null || fail "mock server died on startup (see /tmp/mock-pipeline.log)"
  sleep 0.5
done
[[ "${ready:-}" == 1 ]] || fail "mock server did not become ready in time"
echo "   ready."

# --- run the pipeline through OpenCode ---
# Point opencode.json's mock provider at this port for the duration of the run.
echo "== running analyze.sh against the mock =="
out="$(cd "$here" && MODEL="$model" \
       timeout 120 ./analyze.sh report 2289836 2>&1)" || fail "analyze.sh exited non-zero"

echo "----- output -----"
echo "$out"
echo "------------------"

# --- assert the mock actually answered through the chain ---
echo "$out" | grep -q "\[mock model\]" || fail "mock reply marker not found in output"
echo "$out" | grep -qi "injected data" || fail "mock did not report receiving injected data"

echo "PASS: pipeline works (mock replied through OpenCode)."
