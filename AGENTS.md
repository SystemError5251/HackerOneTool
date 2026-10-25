# HackerOneTool — agent guide

Context for any AI coding agent (OpenCode, Claude Code, etc.) working in this
repository.

## What this repo is

Read-only recon helpers for **authorized** bug-bounty work on HackerOne, plus a
testing methodology. Every tool talks only to HackerOne's own public GraphQL
API (`https://hackerone.com/graphql`) — none of them send traffic to a
program's target assets, so they cannot violate a program's "no scanning" rule.

- `h1scope.py <handle>` — a program's scopes, sorted into eligible-for-bounty /
  submit-only / out-of-scope, with tier and max severity. `--policy`, `--json`.
- `h1reports.py <handle>` — a program's publicly disclosed reports. `--grep`,
  `--limit`, `--json`.
- `h1report.py <id|url>` — one disclosed report's metadata and lifecycle
  timeline. `--comments`, `--json`.
- `h1common.py` — shared transport (User-Agent, retries/backoff, error
  handling, handle validation). All three CLIs import from it; keep new
  network code here rather than re-implementing it per tool. Each CLI exposes
  its `--timeout`; the endpoint is read from `HACKERONE_GRAPHQL` (defaults to
  the public API, overridden by the mock server and tests).
- `METHODOLOGY.md` — ATO/2FA-bypass and Tier 3 leak workflow.
- `analyze.sh` — pipes a helper's output into `opencode run` for analysis.
- `mock_model_server.py` — fake OpenAI-compatible model for offline pipeline
  testing (the `mock` provider in `opencode.json`). No real LLM, no network.
- `.opencode/command/` — `/analyze-program`, `/analyze-report`, `/scope`.

## Guardrails (do not weaken these)

This repo supports **authorized** testing only. When extending it:

- Keep the tools read-only against HackerOne's public API. Do not add code that
  sends requests to a program's target assets, scans, brute-forces, or probes
  rate limits.
- Do not add credential-stuffing, exploitation payloads, or anything that would
  act on real users' accounts or data. Testing is done on accounts the
  researcher owns or on provisioned test users.
- Leak handling is confirm-only: never add code that exfiltrates or reuses
  discovered secrets beyond a single non-destructive validation.
- Preserve the "test only in-scope, authorized programs" framing in docs.

## Conventions

- Python 3, standard library only — no third-party dependencies.
- Each tool: a module docstring with usage, `argparse` CLI, a `--json` mode,
  errors to stderr with a non-zero exit (via `h1common.run_cli`).
- Validate any program handle with `h1common.valid_handle` before putting it in
  a query; raise `h1common.H1Error` for user-facing failures.
- Match the existing style (type hints, small focused functions).
- Run a quick manual check against `mercadolibre` after changes.
