#!/usr/bin/env bash
# analyze.sh — run a HackerOne recon helper and have OpenCode analyze the output.
#
# Feeds a tool's result into `opencode run` with a focused prompt so the local
# OpenCode agent can summarize a disclosed report, group a program's findings
# by bug class, or flag which in-scope assets look worth a closer (authorized)
# look.
#
# OpenCode runs fully offline here: it talks only to a loopback model server
# (a local llama-server on 127.0.0.1:8080, or the bundled mock on :8787), and
# opencode-env.sh turns off autoupdate, telemetry, model-catalogue downloads
# and cloud plugins, so nothing from the analysis leaves the host.
#
# Usage:
#   ./analyze.sh scope   <handle>      # analyze a program's scope
#   ./analyze.sh reports <handle>      # analyze a program's disclosed reports
#   ./analyze.sh report  <id|url>      # analyze one disclosed report
#
#   MODEL=mock/mock-1 ./analyze.sh reports mercadolibre   # force a model
set -euo pipefail

cmd="${1:-}"
arg="${2:-}"
here="$(cd "$(dirname "$0")" && pwd)"

if [[ -z "$cmd" || -z "$arg" ]]; then
  sed -n '2,/^set -/{/^set -/!p}' "$0" | sed 's/^# \{0,1\}//'
  exit 1
fi

if ! command -v opencode >/dev/null 2>&1; then
  cat >&2 <<'EOF'
error: the OpenCode CLI is not installed (the `opencode` command was not found).

Install it (Linux/macOS):
    curl -fsSL https://opencode.ai/install | bash     # standalone installer
    # or:  npm i -g opencode-ai

It then runs fully offline here — see the README's "OpenCode integration".
Note: this is sst/opencode (command `opencode`), NOT the Debian package
`pencode` (golang-github-ffuf-pencode-dev), which is an unrelated tool.
EOF
  exit 1
fi

# Load the offline lock before touching OpenCode (no autoupdate / telemetry /
# model-catalogue download, and loopback kept off any configured proxy).
# shellcheck source=opencode-env.sh
source "$here/opencode-env.sh"

case "$cmd" in
  scope)
    data="$(python3 "$here/h1scope.py" "$arg" --policy)"
    task="Summarize this HackerOne program scope and policy. List the highest-value in-scope, bounty-eligible assets and their tiers, and note the key testing restrictions a researcher must respect. Testing is authorized and read-only — do not propose scanning or attacks on target assets."
    ;;
  reports)
    data="$(python3 "$here/h1reports.py" "$arg" --limit 50)"
    task="Group these disclosed reports by vulnerability class and summarize what kinds of bugs land on this program, which areas recur, and what a researcher should study before testing. Do not invent details beyond the titles shown."
    ;;
  report)
    data="$(python3 "$here/h1report.py" "$arg")"
    task="Summarize this disclosed report: the bug class, severity, and what the lifecycle timeline suggests about triage. Note that the full write-up is only at the URL. Keep it factual."
    ;;
  *)
    echo "error: unknown command '$cmd' (use scope|reports|report)" >&2
    exit 1
    ;;
esac

# Pick a loopback model. An explicit MODEL wins; otherwise prefer the local
# llama-server on :8080 and fall back to the offline mock on :8787. Both are
# loopback-only, so the choice never sends anything off the host.
tcp_open() { (exec 3<>"/dev/tcp/127.0.0.1/$1") >/dev/null 2>&1 && exec 3>&-; }

model="${MODEL:-}"
if [[ -z "$model" ]]; then
  if tcp_open 8080; then
    model="llamacpp/local"
  elif tcp_open 8787; then
    model="mock/mock-1"
    echo "note: no llama-server on 127.0.0.1:8080 — using the offline mock model." >&2
  else
    echo "error: no local model server found." >&2
    echo "       start a llama-server on 127.0.0.1:8080 (see README's \"OpenCode integration\")," >&2
    echo "       or the offline mock: python3 \"$here/mock_model_server.py\" &" >&2
    exit 1
  fi
fi

printf '%s\n\n--- DATA ---\n%s\n' "$task" "$data" \
  | opencode run --model "$model" --dir "$here"
