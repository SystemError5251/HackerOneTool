#!/usr/bin/env bash
# test-bbp.sh — offline tests for the `bbp` launcher.
#
# Exercises argument parsing, the bilingual (DE/EN) output, the environment
# doctor, and the offline guard. No network, no OpenCode, and no license key
# are required: these cover bbp's own logic, not the gated recon helpers (which
# have their own unit tests and smoke test).
#
# Exit 0 = all checks pass.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
bbp="$here/../bbp"
export NO_COLOR=1
# Keep every run out of the real user config, and start with no language set.
export XDG_CONFIG_HOME; XDG_CONFIG_HOME="$(mktemp -d)"
unset BBP_LANG BBP_OFFLINE MODEL 2>/dev/null || true

pass=0
check() {  # check "<name>" "<expected substring>" -- <command...>
  local name="$1" want="$2"; shift 2; [[ "$1" == "--" ]] && shift
  local out
  out="$("$@" 2>&1)" || true
  if printf '%s' "$out" | grep -qF -- "$want"; then
    printf 'ok   %s\n' "$name"; pass=$((pass + 1))
  else
    printf 'FAIL %s\n     wanted substring: %s\n----- got -----\n%s\n---------------\n' \
      "$name" "$want" "$out" >&2
    exit 1
  fi
}

expect_fail() {  # expect_fail "<name>" -- <command...>
  local name="$1"; shift; [[ "$1" == "--" ]] && shift
  if "$@" >/dev/null 2>&1; then
    printf 'FAIL %s (expected non-zero exit)\n' "$name" >&2; exit 1
  fi
  printf 'ok   %s\n' "$name"; pass=$((pass + 1))
}

# --- syntax ---
bash -n "$bbp" && printf 'ok   bash -n parses\n' && pass=$((pass + 1))

# --- version / help ---
check "version"      "bbp 1.1.0"  -- "$bbp" version
check "help EN"      "Usage"      -- "$bbp" --lang en help
check "help DE"      "Aufruf"     -- "$bbp" --lang de help
check "help flag EN" "Usage"      -- "$bbp" --lang en --help

# --- doctor / status ---
check "check EN online"  "online"             -- "$bbp" --lang en check
check "check DE heading"  "Umgebungs-Check"   -- "$bbp" --lang de check
# Offline leaves MODEL unset so analyze.sh auto-detects the loopback provider.
check "check model auto"     "automatic (loopback)" -- "$bbp" --lang en --offline=mock check
# An explicit loopback MODEL is still honoured and shown.
check "check model explicit" "mock/mock-1" -- \
  env MODEL=mock/mock-1 "$bbp" --lang en --offline=mock check

# --- offline guard: external provider blocked when offline ---
check "guard blocks external" "external provider blocked" -- \
  env MODEL=anthropic/claude-sonnet-4-5 "$bbp" --lang en --offline=local check
check "guard ok loopback" "ok (loopback model)" -- \
  "$bbp" --lang en --offline=mock check

# --- language persistence via config file ---
mkdir -p "$XDG_CONFIG_HOME/bbp"
printf 'lang=de\n' >"$XDG_CONFIG_HOME/bbp/config"
check "config lang DE" "Umgebungs-Check" -- env -u BBP_LANG "$bbp" check

# --- error paths ---
expect_fail "unknown command"       -- "$bbp" --lang en frobnicate
expect_fail "analyze missing args"  -- "$bbp" --lang en analyze

printf '\nPASS: %d bbp checks\n' "$pass"
