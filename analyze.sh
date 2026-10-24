#!/usr/bin/env bash
# analyze.sh — run a HackerOne recon helper and have OpenCode analyze the output.
#
# Feeds a tool's result into `opencode run` with a focused prompt so the local
# OpenCode agent can summarize a disclosed report, group a program's findings
# by bug class, or flag which in-scope assets look worth a closer (authorized)
# look. OpenCode needs a provider configured first: `opencode auth login`.
#
# Usage:
#   ./analyze.sh scope   <handle>      # analyze a program's scope
#   ./analyze.sh reports <handle>      # analyze a program's disclosed reports
#   ./analyze.sh report  <id|url>      # analyze one disclosed report
#
#   MODEL=anthropic/claude-sonnet-4-5 ./analyze.sh reports mercadolibre
set -euo pipefail

cmd="${1:-}"
arg="${2:-}"
here="$(cd "$(dirname "$0")" && pwd)"

if [[ -z "$cmd" || -z "$arg" ]]; then
  sed -n '2,/^set -/{/^set -/!p}' "$0" | sed 's/^# \{0,1\}//'
  exit 1
fi

if ! command -v opencode >/dev/null 2>&1; then
  echo "error: opencode is not installed. Install it, then 'opencode auth login'." >&2
  exit 1
fi

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

model_args=()
[[ -n "${MODEL:-}" ]] && model_args=(--model "$MODEL")

printf '%s\n\n--- DATA ---\n%s\n' "$task" "$data" \
  | opencode run "${model_args[@]}" --dir "$here"
