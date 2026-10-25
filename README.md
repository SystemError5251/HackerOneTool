# HackerOneTool

Helpers for **authorized** bug-bounty work on HackerOne programs.

> [!IMPORTANT]
> **Authorized testing only — stay in scope.** Use these tools and the workflow
> in [`METHODOLOGY.md`](METHODOLOGY.md) *only* against programs and assets you
> are permitted to test: an asset the program lists as
> `eligible_for_submission`, tested with accounts you own or provisioned test
> users, following that program's written policy. The recon helpers are
> read-only against HackerOne's own public API and send no traffic to any
> target's assets. Using any part of this against systems you are not
> authorized to test is out of scope here, violates the AUP, and is likely
> illegal — don't.

## Acceptable use

This project exists for **authorized** security testing and research only, in
line with Anthropic's
[Acceptable Use Policy](https://www.anthropic.com/legal/aup) (the AUP permits
authorized pentesting and security research; it prohibits unauthorized access,
attacks on systems you don't have permission to test, malware, and misuse of
data). Concretely, within this repo:

- **In scope only** — test an asset only when the target program authorizes it,
  and follow its policy and rules of engagement.
- **Your own accounts** — exercise flows (including the ATO / 2FA workflow in
  `METHODOLOGY.md`) against accounts you own or test users you provisioned,
  never a real user's account or data.
- **No attack traffic from these helpers** — `h1scope.py`, `h1reports.py`, and
  `h1report.py` only read HackerOne's public API; they do not scan,
  brute-force, probe rate limits, or send payloads to a program's assets, and
  must not be extended to.
- **Leaks are confirm-only** — validate a finding non-destructively and report
  it; never exfiltrate, reuse, or act on discovered secrets.
- **`ssh-tunnel.sh`** is for reaching hosts you're authorized to access through
  a bastion you control — not for tunnelling into anything else.

The agent guardrails in [`AGENTS.md`](AGENTS.md) encode these same rules for any
AI coding agent working in the repo.

## Install / Update / Upgrade

All-in-one. Requires `git`, Python 3, and (for the OpenCode pieces) Node.js.

**Install** — clone, make the tools executable, and install the OpenCode CLI:

```bash
git clone https://github.com/SystemError5251/HackerOneTool.git
cd HackerOneTool
chmod +x *.py *.sh
npm i -g opencode-ai        # optional: only for analyze.sh / slash commands
opencode auth login         # optional: pick a model provider
```

The recon helpers need only Python 3 (`pkg install python` on Termux) and no
packages. OpenCode is optional; on **Termux/Android** it has no official build —
see [Termux / Android](#termux--android-no-official-build) for the working paths.

One-liner (clone + setup):

```bash
git clone https://github.com/SystemError5251/HackerOneTool.git && cd HackerOneTool && chmod +x *.py *.sh && npm i -g opencode-ai
```

**Update** — pull the latest tools and refresh OpenCode:

```bash
cd HackerOneTool
git pull --ff-only origin main   # update the helpers
chmod +x *.py *.sh               # re-arm any new scripts
opencode upgrade                 # upgrade the OpenCode CLI (optional)
```

One-liner (update everything):

```bash
cd HackerOneTool && git pull --ff-only origin main && chmod +x *.py *.sh && opencode upgrade
```

The helpers need no Python packages — standard library only. Verify a working
setup any time with `./test-pipeline.sh` (offline, no provider needed).

## `h1scope.py`

Step 1 of any engagement: know exactly what you are allowed to touch. Given a
program handle, it pulls the structured scopes and sorts them into
*eligible for bounty* / *submit only* / *out of scope*, with each asset's tier
and max severity, and can print the full program policy.

```bash
python3 h1scope.py mercadolibre            # scope table
python3 h1scope.py mercadolibre --all      # include out-of-scope entries
python3 h1scope.py mercadolibre --policy   # also dump the policy text
python3 h1scope.py mercadolibre --json     # raw JSON for scripting
python3 h1scope.py mercadolibre --timeout 10   # cap each request at 10s
```

No dependencies beyond the Python 3 standard library. All three tools share
`h1common.py` for transport — see [Transport, errors & retries](#transport-errors--retries)
below for the `--timeout` flag, the `HACKERONE_GRAPHQL` override, retry
behaviour, and error messages.

## `h1reports.py`

Pairs with `h1scope.py`: before testing an asset, see what's already been
found and fixed so you don't re-report a known issue and can read the bug
classes that land on the program. Lists the program's publicly disclosed
reports (HackerOne's Hacktivity data) with severity, award, date, and link.

```bash
python3 h1reports.py mercadolibre
python3 h1reports.py mercadolibre --limit 50
python3 h1reports.py mercadolibre --grep "2fa|account takeover|ato"
python3 h1reports.py mercadolibre --json
python3 h1reports.py mercadolibre --timeout 10   # per-request timeout
```

Also stdlib-only and read-only against HackerOne's public API.

## `h1report.py`

Shows one disclosed report's detail — bug class, severity + CVSS, award, and a
lifecycle timeline — given its id or URL. The full narrative isn't exposed by
the API, so it links to the report page for the write-up.

```bash
python3 h1report.py 2289836
python3 h1report.py https://hackerone.com/reports/2289836 --comments
python3 h1report.py 2289836 --json
python3 h1report.py 2289836 --timeout 10         # per-request timeout
```

## Transport, errors & retries

All three helpers talk to HackerOne's public GraphQL API through the shared
`h1common.py` module, so they behave identically on the wire. It is standard
library only and stays read-only — it sends nothing to a program's target
assets.

**Request behaviour**

- Each request is sent with a descriptive `User-Agent` and a timeout. The
  timeout defaults to **30 seconds** and is set per invocation with
  `--timeout <seconds>` (accepted by every tool).
- The endpoint defaults to `https://hackerone.com/graphql` and can be
  overridden with the `HACKERONE_GRAPHQL` environment variable (used by the
  offline mock server and the test suite).
- Program handles are validated before they go into a query, so a handle with
  spaces, quotes, or query operators is rejected instead of silently changing
  what the query matches.

**Retries** — on a rate-limit (HTTP 429), a server error (HTTP 5xx), or a
transient network error, the request is retried up to **3 times** with
exponential backoff (1s, 2s, 4s), each wait capped at 8 seconds. A
`Retry-After` header on a 429 response is honoured when present (also capped at
8 seconds). Other `4xx` responses and GraphQL-level
errors are **not** retried — they fail immediately.

**Errors** — expected failures are printed as a single `error: <message>` line
to stderr with exit code `1`, never a Python traceback. They are raised as
`h1common.H1Error`, and cover:

| Message | Cause |
|---|---|
| `error: invalid program handle: '…' (expected letters, digits, '.', '_' or '-')` | handle failed validation |
| `error: No program found for handle '…'.` | the handle resolved to no program (`h1scope.py`) |
| `error: report <id> not found or not public` | the report id isn't a public, disclosed report (`h1report.py`) |
| `error: HTTP <code> from hackerone.com: <reason>` | non-retryable HTTP error (e.g. 404), or retries exhausted |
| `error: network error reaching hackerone.com: <reason>` | connection/timeout error after retries |
| `error: GraphQL error: <messages>` | the API returned GraphQL errors |
| `error: invalid JSON from hackerone.com: …` | a malformed response body |

Piping a tool's output into a reader that closes early (e.g. `| head`) exits
cleanly with no broken-pipe traceback, and `Ctrl-C` exits with code `130`.

## OpenCode integration

The repo is set up for the [OpenCode](https://opencode.ai) CLI agent:

- `AGENTS.md` — project context and the authorized-testing guardrails OpenCode
  should respect here.
- `opencode.json` — loads those instructions and keeps edits/pushes behind a
  confirmation prompt.
- `analyze.sh` — pipes a helper's output into `opencode run` for analysis.

### Terminal integration & installation

Install the [OpenCode](https://opencode.ai) CLI (pick one):

```bash
npm i -g opencode-ai                      # npm / Node.js
# or
curl -fsSL https://opencode.ai/install | bash   # standalone installer
# or:  brew install sst/tap/opencode  ·  paru -S opencode-bin
```

Then authenticate once and launch it **from the repo root** so it picks up this
project's `AGENTS.md`, `opencode.json`, and `.opencode/command/` automatically:

```bash
cd HackerOneTool
opencode auth login        # one-time: choose a model provider
opencode                   # start the interactive TUI in this repo
```

Inside the TUI you can chat, or run the project slash commands directly
(`/analyze-program`, `/analyze-report`, `/scope` — see below). For
non-interactive / scripted use, drive it from the terminal with `opencode run`:

```bash
opencode run "list the in-scope assets for mercadolibre"   # one-shot prompt
opencode run --model mock/mock-1 "hello"                   # offline, see below
```

No provider yet? Use the offline mock model (next section) to exercise the whole
terminal flow with no API key. Upgrade the CLI any time with `opencode upgrade`.

The methods above work on ordinary glibc Linux (x86_64 / arm64) and macOS.

#### Termux / Android (no official build)

OpenCode has **no official Termux build**. `npm i -g opencode-ai` fails there
because the `opencode-android-arm64` package is unpublished, and the prebuilt
binary is a glibc/PIE executable that Termux's bionic libc can't run
([#12515](https://github.com/anomalyco/opencode/issues/12515),
[#10504](https://github.com/anomalyco/opencode/issues/10504),
[#11689](https://github.com/anomalyco/opencode/issues/11689)). Options, in order
of preference:

1. **Run a real Linux in Termux with `proot-distro`** — stays on the upstream
   build; the most reliable on-device path:
   ```bash
   pkg install proot-distro
   proot-distro install debian
   proot-distro login debian
   # then inside Debian: apt install nodejs npm && npm i -g opencode-ai
   ```
2. **Community native installer** —
   [`vjaykrsna/opencode-termux-native`](https://github.com/vjaykrsna/opencode-termux-native)
   patches the glibc binary to run natively on Termux. Its README warns **not**
   to run `opencode upgrade` without its launcher.
3. **Community `.deb`** — [`guysoft/opencode-termux`](https://github.com/guysoft/opencode-termux)
   ships an aarch64 build (`ripgrep` is the only extra dep).

These are third-party; review what their installers do before running them.

**You don't need OpenCode for the recon helpers.** `h1scope.py`, `h1reports.py`,
and `h1report.py` are pure Python 3 standard library and run fine on Termux as-is
(`pkg install python`). OpenCode is only needed for `analyze.sh`, `test-pipeline.sh`,
and the slash commands — the AI-analysis layer on top.

### Analyze from the terminal

`analyze.sh` wraps `opencode run`, feeding a helper's output straight into a prompt:

```bash
opencode auth login                        # one-time: pick a provider
./analyze.sh reports mercadolibre          # summarize disclosed findings
./analyze.sh report 2289836                # summarize one report
MODEL=anthropic/claude-sonnet-4-5 ./analyze.sh scope mercadolibre
```

### Offline test model (no provider needed)

`mock_model_server.py` is a fake OpenAI-compatible model so you can exercise
the whole OpenCode pipeline — `analyze.sh`, the slash commands — with no real
provider, API key, or network. It returns a deterministic reply that echoes
what it received, proving the plumbing works. The `mock` provider in
`opencode.json` points OpenCode at it.

```bash
python3 mock_model_server.py &                 # listen on 127.0.0.1:8787
opencode run --model mock/mock-1 "hello"       # talks to the mock
MODEL=mock/mock-1 ./analyze.sh report 2289836  # full pipeline, offline
kill %1                                         # stop the server
```

Swap `mock/mock-1` for a real `provider/model` (after `opencode auth login`)
for actual analysis.

`test-pipeline.sh` is a one-shot smoke test (for CI): it boots the mock, runs
`analyze.sh` against it through OpenCode, asserts the mock replied, and tears
the server down. Exit 0 means the pipeline works.

```bash
./test-pipeline.sh
```

### Custom commands (OpenCode TUI)

`.opencode/command/` adds slash commands you can run inside the OpenCode TUI.
Each injects the relevant helper's output and asks for a summary:

| Command | Does |
|---|---|
| `/analyze-program <handle>` | scope + policy + disclosed reports, summarized |
| `/analyze-report <id\|url>` | one disclosed report, summarized |
| `/scope <handle>` | scope grouped by tier, with out-of-scope called out |

```
opencode
> /analyze-program mercadolibre
> /analyze-report 2289836
```

## Testing methodology

See [`METHODOLOGY.md`](METHODOLOGY.md) for the ATO / 2FA-bypass and Tier 3
leak workflow, written to stay inside program rules (no mass scanning, no
brute force, confirm-only on leaks, test on your own accounts).

## Program reference page

[`policy-reference.html`](policy-reference.html) is a self-contained,
themeable reference page for the Mercado Libre program — scope (by tier),
bounty table, Tier 3 rules, and key restrictions — compiled from the public
program data. Open it in a browser. It is unofficial; the
[official program page](https://hackerone.com/mercadolibre) is authoritative.

Regenerate the underlying data with `python3 h1scope.py mercadolibre --policy`.

## Secure SSH tunnel

`ssh-tunnel.sh` sets up a hardened SSH tunnel through a bastion / jump host, for
**authorized** testing only — reaching hosts you're permitted to access via a
bastion you control or have been granted. It opens no shell (`-N`), uses
key-based auth only (`BatchMode`, `IdentitiesOnly`), pins host keys, and hardcodes
no hosts or secrets. Configure it with a gitignored `tunnel.conf` (copy
`tunnel.conf.example`) or environment variables.

```bash
cp tunnel.conf.example tunnel.conf   # fill in your bastion + key path
./ssh-tunnel.sh check                # validate config + auth, then exit
./ssh-tunnel.sh db                   # local-forward a remote DB port to localhost
./ssh-tunnel.sh expose               # remote-forward a local service to the bastion
./ssh-tunnel.sh socks                # dynamic SOCKS5 proxy via the bastion
```

Authentication is by SSH key referenced by path — the config never contains the
key or any password. Only tunnel hosts/services you're authorized to access.

## License

MIT — see [`LICENSE`](LICENSE).
