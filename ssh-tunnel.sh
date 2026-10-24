#!/usr/bin/env bash
# ssh-tunnel.sh — set up a secure SSH tunnel through a bastion / jump host.
#
# For AUTHORIZED testing only: reach hosts you are permitted to access, through
# a bastion you control or have been granted use of. It opens no shell (-N) and
# uses key-based auth only; it hardcodes no hosts or secrets — configure it with
# a gitignored tunnel.conf (copy tunnel.conf.example) or environment variables.
#
# Modes:
#   db      local-forward (-L) a remote service (e.g. a database) to localhost,
#           so a local client connects to 127.0.0.1:$LOCAL_PORT as if it were
#           $REMOTE_HOST:$REMOTE_PORT, reachable only from the bastion's network.
#   expose  remote-forward (-R) a local service up to the bastion, so something
#           on the bastion's side can reach your 127.0.0.1:$LOCAL_PORT.
#   socks   dynamic (-D) SOCKS5 proxy on 127.0.0.1:$SOCKS_PORT, tunneling all
#           its traffic through the bastion.
#
# Usage:
#   ./ssh-tunnel.sh db
#   ./ssh-tunnel.sh expose
#   ./ssh-tunnel.sh socks
#   ./ssh-tunnel.sh check      # validate config and connectivity, then exit
#
# Stop a tunnel with Ctrl-C.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
conf="${TUNNEL_CONF:-$here/tunnel.conf}"

# --- load config (shell file of KEY=value); env vars still win ---
if [[ -f "$conf" ]]; then
  # shellcheck disable=SC1090
  source "$conf"
fi

# --- settings, with safe defaults; override in tunnel.conf or the environment ---
BASTION_HOST="${BASTION_HOST:-}"          # e.g. bastion.example.com   (required)
BASTION_USER="${BASTION_USER:-${USER:-$(id -un 2>/dev/null || echo user)}}"
BASTION_PORT="${BASTION_PORT:-22}"
SSH_KEY="${SSH_KEY:-$HOME/.ssh/id_ed25519}"
KNOWN_HOSTS="${KNOWN_HOSTS:-$HOME/.ssh/known_hosts}"
# accept-new = trust a new host on first use but pin it after; set to "yes" to
# require the key already be in KNOWN_HOSTS (strongest).
STRICT_HOST_KEY="${STRICT_HOST_KEY:-accept-new}"

# db mode
REMOTE_HOST="${REMOTE_HOST:-}"            # host reachable FROM the bastion
REMOTE_PORT="${REMOTE_PORT:-5432}"
LOCAL_PORT="${LOCAL_PORT:-15432}"
LOCAL_BIND="${LOCAL_BIND:-127.0.0.1}"     # keep loopback-only unless you must share

# expose mode
EXPOSE_LOCAL_PORT="${EXPOSE_LOCAL_PORT:-8080}"
EXPOSE_REMOTE_BIND="${EXPOSE_REMOTE_BIND:-127.0.0.1}"  # bind on the bastion
EXPOSE_REMOTE_PORT="${EXPOSE_REMOTE_PORT:-8080}"

# socks mode
SOCKS_PORT="${SOCKS_PORT:-1080}"

mode="${1:-}"

die() { echo "error: $*" >&2; exit 1; }

require() { [[ -n "${!1:-}" ]] || die "$1 is not set (put it in $conf or the environment)"; }

[[ -n "$mode" ]] || { sed -n '2,/^set -/{/^set -/!p}' "$0" | sed 's/^# \{0,1\}//'; exit 1; }

require BASTION_HOST
[[ -f "$SSH_KEY" ]] || die "SSH key not found: $SSH_KEY (set SSH_KEY)"

# --- hardened common options ---
# BatchMode: never prompt for a password (key-only); fail fast instead.
# IdentitiesOnly: use exactly the given key, not whatever the agent offers.
# ExitOnForwardFailure: if the forward can't bind, don't sit idle pretending to work.
# No agent forwarding (-a), no X11 (-x), no remote command (-N).
common_opts=(
  -N -a -x
  -p "$BASTION_PORT"
  -i "$SSH_KEY"
  -o BatchMode=yes
  -o PasswordAuthentication=no
  -o IdentitiesOnly=yes
  -o StrictHostKeyChecking="$STRICT_HOST_KEY"
  -o UserKnownHostsFile="$KNOWN_HOSTS"
  -o ExitOnForwardFailure=yes
  -o ServerAliveInterval=30
  -o ServerAliveCountMax=3
)
target="${BASTION_USER}@${BASTION_HOST}"

case "$mode" in
  check)
    echo "config:"
    echo "  bastion : ${target}:${BASTION_PORT}"
    echo "  key     : ${SSH_KEY}"
    echo "  strict  : ${STRICT_HOST_KEY}"
    echo "testing auth (no shell)..."
    if ssh "${common_opts[@]}" -o ConnectTimeout=10 -O check "$target" 2>/dev/null \
       || ssh -n -a -x -p "$BASTION_PORT" -i "$SSH_KEY" \
            -o BatchMode=yes -o PasswordAuthentication=no -o IdentitiesOnly=yes \
            -o StrictHostKeyChecking="$STRICT_HOST_KEY" -o UserKnownHostsFile="$KNOWN_HOSTS" \
            -o ConnectTimeout=10 "$target" true 2>/dev/null; then
      echo "OK: bastion reachable and key accepted."
    else
      die "could not authenticate to the bastion with $SSH_KEY"
    fi
    ;;
  db)
    require REMOTE_HOST
    echo "forwarding ${LOCAL_BIND}:${LOCAL_PORT} -> ${REMOTE_HOST}:${REMOTE_PORT} via ${target}"
    echo "connect your client to ${LOCAL_BIND}:${LOCAL_PORT}. Ctrl-C to stop."
    exec ssh "${common_opts[@]}" \
      -L "${LOCAL_BIND}:${LOCAL_PORT}:${REMOTE_HOST}:${REMOTE_PORT}" \
      "$target"
    ;;
  expose)
    echo "remote-forwarding ${EXPOSE_REMOTE_BIND}:${EXPOSE_REMOTE_PORT} on bastion -> local 127.0.0.1:${EXPOSE_LOCAL_PORT}"
    echo "note: binding beyond 127.0.0.1 on the bastion also needs its sshd GatewayPorts. Ctrl-C to stop."
    exec ssh "${common_opts[@]}" \
      -R "${EXPOSE_REMOTE_BIND}:${EXPOSE_REMOTE_PORT}:127.0.0.1:${EXPOSE_LOCAL_PORT}" \
      "$target"
    ;;
  socks)
    echo "SOCKS5 proxy on 127.0.0.1:${SOCKS_PORT} via ${target}. Point tools at socks5h://127.0.0.1:${SOCKS_PORT}. Ctrl-C to stop."
    exec ssh "${common_opts[@]}" \
      -D "127.0.0.1:${SOCKS_PORT}" \
      "$target"
    ;;
  *)
    die "unknown mode '$mode' (use: db | expose | socks | check)"
    ;;
esac
