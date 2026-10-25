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
```

The recon helpers need only Python 3 (`pkg install python` on Termux) and no
packages. OpenCode is optional and runs **fully offline** here — no
`opencode auth login`, no cloud provider; it talks only to a local model server
(see [OpenCode integration](#opencode-integration)). On **Termux/Android** it
has no official build — see
[Termux / Android](#termux--android-no-official-build) for the working paths.

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

## `bbp` — one command for everything

`bbp` is a single, bilingual entry point that bundles the recon helpers and the
OpenCode analysis behind one coloured terminal UI. You pick the language right
when you start it — interactively, or with `bbp --lang de|en` — and it's
remembered in `~/.config/bbp/config`.

```bash
./bbp                      # interactive menu (asks for a language first)
./bbp --lang de            # force German, then the menu
```

It also works non-interactively, so it's scriptable too — *„command für
alles"*:

```bash
./bbp scope   mercadolibre          # program scope + policy   (→ h1scope.py)
./bbp reports mercadolibre          # disclosed reports        (→ h1reports.py)
./bbp report  2289836               # one report in detail     (→ h1report.py)
./bbp analyze reports mercadolibre  # AI analysis of the above (→ analyze.sh)
./bbp check                         # environment doctor (read-only, no egress)
./bbp help                          # full help (in the active language)
```

Everything `bbp` runs flows through the existing gated helpers, so the
Ed25519 **license gate** (see below) still applies exactly as before — `bbp`
never bypasses it, and shows the current license status in its header.

### Offline mode — stay in scope

For the AI analysis step, `bbp` can enforce a **loopback-only** model so nothing
leaves your machine while you test in scope. It refuses any external provider in
offline mode:

```bash
./bbp --offline        analyze scope mercadolibre   # auto: local if up, else mock
./bbp --offline=local  analyze scope mercadolibre   # llama.cpp on 127.0.0.1:8080
./bbp --offline=mock   analyze report 2289836       # bundled mock (127.0.0.1:8787)
```

- **auto** — use the local llama.cpp server (`llamacpp/local`,
  `http://127.0.0.1:8080/v1`) if it's running, otherwise fall back to the
  bundled offline mock. This is the offline OpenCode integration from
  [OPENCODE-LOCAL](https://github.com/SystemError5251/OPENCODE-LOCAL); start it
  with `opencode-local` / `scripts/start-llama.sh`.
- **mock** — the bundled `mock_model_server.py`, booted automatically for the
  run. No provider, API key, or real network needed (used by CI).
- **local** — require the local llama.cpp server; error out if it isn't up.

In any offline mode, a model that isn't a `mock/…` or `llamacpp/…` provider is
**blocked** before OpenCode is invoked. Online mode (`--online`, the default)
uses whatever provider/`MODEL` you've configured.

| Environment variable | Meaning |
|---|---|
| `BBP_LANG=de\|en` | default language (overrides the saved config) |
| `BBP_OFFLINE=off\|auto\|mock\|local` | default offline backend for `analyze` |
| `MODEL=provider/model` | model for the analysis step (as for `analyze.sh`) |
| `NO_COLOR=1` | disable colour |

## License key

The recon helpers (`h1scope.py`, `h1reports.py`, `h1report.py`) require a valid
**license key** and refuse to run without one. Cloning the repository is not
enough — a `git clone` only copies files and runs no code on the cloner's
machine, so there is no way to verify anything *at clone time*. Instead the
check runs when a tool starts, before it does any work.

Keys are **Ed25519 signatures**: you issue them with a private signing key that
only you hold, and the tools verify them **offline** against the public key
embedded in `h1common.py`. Nobody without your private key can forge a valid
key, and verification makes no network call — no phone-home, no clock.

### Using a key

```bash
export HACKERONETOOL_LICENSE="H1K1.<payload>.<signature>"   # per shell, or
./h1license.py install H1K1.<payload>.<signature>           # save to ~/.hackeronetool/license
```

A tool looks for the key in this order: the `HACKERONETOOL_LICENSE` environment
variable, then a file at `HACKERONETOOL_LICENSE_FILE`, then the default
`~/.hackeronetool/license`. Without a valid key you get a clean one-line error
and exit `1` — no traceback:

```
error: no license key found. Set the HACKERONETOOL_LICENSE environment variable, ...
```

### Issuing keys (operator, one-time setup)

1. **Generate your signing keypair** (do this once; keep the private key safe
   and out of the repo — it is gitignored):

   ```bash
   ./h1license.py keygen            # writes ~/.hackeronetool/signing_key (+ .pub)
   ```

2. **Embed your public key** so the tools trust keys you sign: copy the public
   key it prints into `LICENSE_PUBLIC_KEY_HEX` near the top of `h1common.py`,
   and commit that change.

3. **Issue keys** to whoever is authorized:

   ```bash
   ./h1license.py new                 # a key with a random id
   ./h1license.py new --subject acme  # a key tied to a licensee/id
   ./h1license.py check <key>         # verify against the embedded public key
   ./h1license.py install <key>       # save a valid key to the default file
   ```

The signing key is read from `--key-file`, else `$HACKERONETOOL_SIGNING_KEY`,
else `$HACKERONETOOL_SIGNING_KEY_FILE`, else `~/.hackeronetool/signing_key`.

> **Security note.** Until you replace the embedded public key with your own
> (step 2), the repo ships with a default public key whose private half is a
> bootstrap key — fine for trying it out, not for real gating. Rotating to your
> own keypair is what makes keys issuable only by you. The private key never
> lives in this repo. This gates *who can mint keys*; it is not DRM against
> someone who edits their own checkout.

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

The repo is set up for the [OpenCode](https://opencode.ai) CLI agent, wired to
run **fully offline** so the AI-analysis layer never leaves the authorized
scope — no cloud provider, no API key, no telemetry, no phone-home:

- `AGENTS.md` — project context and the authorized-testing guardrails OpenCode
  should respect here.
- `opencode.json` — loads those instructions, restricts OpenCode to **loopback**
  model providers only (`llamacpp/local` on `127.0.0.1:8080`, or the bundled
  `mock` on `127.0.0.1:8787`), turns off autoupdate / telemetry / sharing, and
  denies `webfetch`, `websearch` and network shell commands to the agent.
- `opencode-env.sh` — the offline lock, sourced by `analyze.sh` before OpenCode
  starts: disables update checks, the models.dev catalogue download, LSP
  downloads and cloud auth plugins, and keeps `127.0.0.1`/`localhost` off any
  configured proxy (so Burp & co. don't swallow the local model call).
- `analyze.sh` — pipes a helper's output into `opencode run` for analysis,
  auto-selecting the local llama-server when it's up and the mock otherwise.

> The offline setup is extracted from the companion project
> [**OPENCODE-LOCAL**](https://github.com/SystemError5251/OPENCODE-LOCAL),
> which packages OpenCode + a local `llama.cpp` model server. Use it to run the
> `llamacpp/local` model server referenced here; any OpenAI-compatible server
> on `127.0.0.1:8080` works too.

### Install OpenCode

Install the [OpenCode](https://opencode.ai) CLI (pick one):

```bash
curl -fsSL https://opencode.ai/install | bash   # standalone installer
# or
npm i -g opencode-ai                             # npm / Node.js
# or:  brew install sst/tap/opencode  ·  paru -S opencode-bin
```

This is **sst/opencode** (the `opencode` command). It is *not* the Debian
package `pencode` (`golang-github-ffuf-pencode-dev`) that `apt` may suggest —
that is an unrelated tool. Upgrade any time with `opencode upgrade`. The methods
above work on ordinary glibc Linux (x86_64 / arm64) and macOS.

### Run a local model server

Point a local, OpenAI-compatible model server at `127.0.0.1:8080`. The simplest
path is the companion project:

```bash
git clone https://github.com/SystemError5251/OPENCODE-LOCAL.git ~/opencode-local
cd ~/opencode-local && ./quickstart.sh        # builds llama.cpp, fetches a model
scripts/start-llama.sh                        # serve a GGUF model on :8080
```

No model yet? You can still exercise the whole pipeline with the offline **mock**
model (see "Offline test model" below) — `analyze.sh` falls back to it
automatically when nothing answers on `:8080`.

### Launch the TUI

Launch OpenCode **from the repo root** so it picks up this project's
`AGENTS.md`, `opencode.json`, and `.opencode/command/` automatically. Load the
offline lock first so the TUI stays offline too:

```bash
cd HackerOneTool
source ./opencode-env.sh   # offline lock (analyze.sh does this for you)
opencode                   # start the interactive TUI in this repo
```

Inside the TUI you can chat, or run the project slash commands directly
(`/analyze-program`, `/analyze-report`, `/scope` — see below). For
non-interactive / scripted use, prefer `analyze.sh` (next section), which loads
the offline lock and selects a loopback model for you.

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

`analyze.sh` wraps `opencode run`, loading the offline lock and feeding a
helper's output straight into a prompt. It picks the model for you: the local
llama-server on `127.0.0.1:8080` when it's up, otherwise the offline mock.

```bash
./analyze.sh reports mercadolibre          # summarize disclosed findings
./analyze.sh report 2289836                # summarize one report
./analyze.sh scope mercadolibre            # summarize a program's scope
MODEL=mock/mock-1 ./analyze.sh scope mercadolibre   # force a specific model
```

Both models are loopback-only, so analysis never leaves the host. (The recon
helpers themselves still query HackerOne's own public API — that is their job
and not a program's target asset.)

### Offline test model (no model needed)

`mock_model_server.py` is a fake OpenAI-compatible model so you can exercise
the whole OpenCode pipeline — `analyze.sh`, the slash commands — with no real
model, GPU, or network. It returns a deterministic reply that echoes what it
received, proving the plumbing works. The `mock` provider in `opencode.json`
points OpenCode at it, and `analyze.sh` falls back to it when no llama-server
is running.

```bash
python3 mock_model_server.py &                 # listen on 127.0.0.1:8787
MODEL=mock/mock-1 ./analyze.sh report 2289836  # full pipeline, offline
kill %1                                         # stop the server
```

For real analysis, start a local llama-server on `127.0.0.1:8080` (see "Run a
local model server" above) and drop the `MODEL=` override — `analyze.sh` then
uses `llamacpp/local` automatically.

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
