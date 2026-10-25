"""h1common — shared transport for the h1* HackerOne recon helpers.

Read-only access to HackerOne's public GraphQL endpoint, with a User-Agent,
bounded retries on transient failures, clear errors, and program-handle
validation. Standard library only; sends nothing to any target's assets.

The endpoint can be overridden with the HACKERONE_GRAPHQL environment variable
(used by the offline mock server and the test suite).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable

GRAPHQL_URL = os.environ.get("HACKERONE_GRAPHQL", "https://hackerone.com/graphql")
USER_AGENT = "HackerOneTool/1.0 (+https://github.com/SystemError5251/HackerOneTool)"
DEFAULT_TIMEOUT = 30.0
DEFAULT_RETRIES = 3
MAX_BACKOFF = 8.0

# A HackerOne program handle: starts alphanumeric, then letters/digits/._-.
_HANDLE_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$", re.IGNORECASE)

# --------------------------------------------------------------------------
# License gate
#
# A lightweight, fully offline check that runs before any helper does work, so
# the tools are used deliberately by someone who holds a key rather than by
# anyone who happens to clone the repo. There is no "verify on git clone" —
# cloning only copies files and runs no code on the cloner's machine — so the
# check runs at tool start-up instead.
#
# The scheme is self-contained (no network, no phone-home, stdlib only): a key
# is a serial plus a checksum derived from it, so a key can be validated with
# nothing but this file. It is a usage gate, not DRM: because this module is
# open source, anyone who reads it can mint a key, and that is by design.
# --------------------------------------------------------------------------
LICENSE_ENV = "HACKERONETOOL_LICENSE"
LICENSE_FILE_ENV = "HACKERONETOOL_LICENSE_FILE"
DEFAULT_LICENSE_FILE = Path.home() / ".hackeronetool" / "license"

# Crockford-style base32 alphabet (no I/L/O/U, to avoid look-alikes).
_KEY_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
# Mixed into the checksum so a bare serial is not trivially a valid key. Not a
# secret (it lives here in the open) — it only shapes the key format.
_LICENSE_SALT = "HackerOneTool/license/v1"
_KEY_RE = re.compile(
    r"^H1-([0-9A-Z]{5})-([0-9A-Z]{5})-([0-9A-Z]{5})-([0-9A-Z]{5})$"
)


class H1Error(RuntimeError):
    """Any error worth showing the user as a one-line message (no traceback)."""


def valid_handle(handle: str) -> str:
    """Validate a program handle before it is interpolated into a query.

    Prevents a handle with spaces, quotes, or query operators from silently
    corrupting a Hacktivity query_string or changing what it matches.
    """
    if not handle or not _HANDLE_RE.match(handle):
        raise H1Error(
            f"invalid program handle: {handle!r} "
            "(expected letters, digits, '.', '_' or '-')"
        )
    return handle


def _normalize_key(key: str) -> str:
    """Upper-case and strip separators/whitespace, keeping one 'H1-...' shape."""
    cleaned = re.sub(r"\s+", "", key or "").upper()
    # Accept keys pasted without dashes, e.g. "H1ABCDE...": re-insert them.
    if cleaned.startswith("H1-"):
        return cleaned
    if cleaned.startswith("H1") and "-" not in cleaned and len(cleaned) == 22:
        body = cleaned[2:]
        groups = [body[i:i + 5] for i in range(0, 20, 5)]
        return "H1-" + "-".join(groups)
    return cleaned


def _key_checksum(serial: str) -> str:
    """Derive the 5-char checksum group from a 15-char serial, deterministically."""
    digest = hashlib.sha256((_LICENSE_SALT + serial).encode()).digest()
    n = int.from_bytes(digest[:8], "big")
    out = []
    for _ in range(5):
        out.append(_KEY_ALPHABET[n & 31])
        n >>= 5
    return "".join(reversed(out))


def license_key_valid(key: str) -> bool:
    """Return True if ``key`` is a well-formed, checksum-correct license key.

    Pure and offline: no network, no clock, no side effects.
    """
    m = _KEY_RE.match(_normalize_key(key))
    if not m:
        return False
    g1, g2, g3, chk = m.groups()
    return secrets.compare_digest(_key_checksum(g1 + g2 + g3), chk)


def make_license_key(serial: str | None = None) -> str:
    """Mint a valid license key. With no serial, a random one is generated.

    Used by the ``h1license`` helper; kept here so key format lives in one place.
    """
    if serial is None:
        serial = "".join(secrets.choice(_KEY_ALPHABET) for _ in range(15))
    else:
        serial = re.sub(r"[\s-]+", "", serial).upper()
        if len(serial) != 15 or any(c not in _KEY_ALPHABET for c in serial):
            raise H1Error(
                "serial must be 15 characters from the key alphabet "
                f"({_KEY_ALPHABET})"
            )
    groups = [serial[i:i + 5] for i in range(0, 15, 5)]
    return "H1-" + "-".join(groups) + "-" + _key_checksum(serial)


def load_license_key() -> str | None:
    """Find a license key: env var, then a file (env override or the default)."""
    env = os.environ.get(LICENSE_ENV)
    if env and env.strip():
        return env.strip()
    path_str = os.environ.get(LICENSE_FILE_ENV)
    path = Path(path_str) if path_str else DEFAULT_LICENSE_FILE
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            return line
    return None


def verify_license() -> None:
    """Raise H1Error unless a valid license key is present. Else return quietly."""
    key = load_license_key()
    if key is None:
        raise H1Error(
            "no license key found. Set the "
            f"{LICENSE_ENV} environment variable, or save your key to "
            f"{DEFAULT_LICENSE_FILE} (or a path in {LICENSE_FILE_ENV}). "
            "See the README's \"License key\" section."
        )
    if not license_key_valid(key):
        raise H1Error(
            "invalid license key. Expected the format "
            "H1-XXXXX-XXXXX-XXXXX-XXXXX. Check the value in "
            f"{LICENSE_ENV} or your license file."
        )


def _host() -> str:
    try:
        return urllib.parse.urlsplit(GRAPHQL_URL).netloc or GRAPHQL_URL
    except Exception:
        return GRAPHQL_URL


def _retry_after(err: urllib.error.HTTPError, attempt: int) -> float:
    """Honor a Retry-After header when present, else exponential backoff."""
    header = err.headers.get("Retry-After") if err.headers else None
    if header:
        try:
            return min(float(header), MAX_BACKOFF)
        except ValueError:
            pass
    return min(2.0 ** attempt, MAX_BACKOFF)


def graphql(
    query: str,
    variables: dict,
    timeout: float = DEFAULT_TIMEOUT,
    retries: int = DEFAULT_RETRIES,
) -> dict:
    """POST a GraphQL query and return its `data`, or raise H1Error.

    Retries on 429 and 5xx responses and on transient network errors, with
    backoff (honoring Retry-After); 4xx (other than 429) and GraphQL-level
    errors fail immediately.
    """
    payload = json.dumps({"query": query, "variables": variables}).encode()
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
    }

    body = None
    for attempt in range(retries + 1):
        req = urllib.request.Request(GRAPHQL_URL, data=payload, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = json.load(resp)
            break
        except urllib.error.HTTPError as e:
            if (e.code == 429 or 500 <= e.code < 600) and attempt < retries:
                time.sleep(_retry_after(e, attempt))
                continue
            raise H1Error(f"HTTP {e.code} from {_host()}: {e.reason}") from e
        except (urllib.error.URLError, socket.timeout, TimeoutError) as e:
            if attempt < retries:
                time.sleep(min(2.0 ** attempt, MAX_BACKOFF))
                continue
            reason = getattr(e, "reason", e)
            raise H1Error(f"network error reaching {_host()}: {reason}") from e
        except json.JSONDecodeError as e:
            raise H1Error(f"invalid JSON from {_host()}: {e}") from e

    if body is None:  # defensive; the loop either breaks with a body or raises
        raise H1Error(f"no response from {_host()}")
    if body.get("errors"):
        msgs = "; ".join(e.get("message", "?") for e in body["errors"])
        raise H1Error(f"GraphQL error: {msgs}")
    return body.get("data") or {}


def run_cli(body: Callable[[], None], require_license: bool = True) -> int:
    """Run a CLI body, turning expected errors into a stderr line + exit 1.

    Before the body runs, the license gate is checked (``require_license``);
    a missing or invalid key prints a one-line ``error:`` and exits 1, so the
    helpers refuse to do work without a valid license. Pass
    ``require_license=False`` for tools that must run without one (e.g. the
    key generator itself).

    Exits quietly on a broken pipe (e.g. output piped into `head`) instead of
    dumping a traceback, and on Ctrl-C.
    """
    try:
        if require_license:
            verify_license()
        body()
        return 0
    except (H1Error, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    except BrokenPipeError:
        # The reader went away (`| head`). Silence the shutdown-time flush error.
        try:
            devnull = os.open(os.devnull, os.O_WRONLY)
            os.dup2(devnull, sys.stdout.fileno())
        except OSError:
            pass
        return 0
    except KeyboardInterrupt:
        return 130
