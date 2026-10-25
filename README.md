# HackerOneTool

Helpers for **authorized** bug-bounty work on HackerOne programs.

The only rule that matters: test an asset only when the program lists it as
`eligible_for_submission`, use accounts you own or provisioned test users, and
follow that program's written policy. These tools are read-only recon against
HackerOne's own public API — they send no traffic to any target's assets.

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
```

No dependencies beyond the Python 3 standard library. All three share
`h1common.py` for transport: a User-Agent, bounded retries with backoff on
rate-limits and transient errors, clean one-line error messages, and
program-handle validation. Every tool also takes `--timeout <seconds>`, and the
endpoint can be overridden with the `HACKERONE_GRAPHQL` environment variable.

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
```

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
