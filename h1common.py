"""h1common — shared transport for the h1* HackerOne recon helpers.

Read-only access to HackerOne's public GraphQL endpoint, with a User-Agent,
bounded retries on transient failures, clear errors, and program-handle
validation. Standard library only; sends nothing to any target's assets.

The endpoint can be overridden with the HACKERONE_GRAPHQL environment variable
(used by the offline mock server and the test suite).
"""
from __future__ import annotations

import base64
import json
import os
import re
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable

import h1crypto

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
# A fully offline check that runs before any helper does work, so the tools are
# used deliberately by someone who holds a valid key rather than by anyone who
# happens to clone the repo. There is no "verify on git clone" — cloning only
# copies files and runs no code on the cloner's machine — so the check runs at
# tool start-up instead.
#
# A key is an Ed25519 signature, issued with a private signing key that only
# the operator holds and verified here against the embedded *public* key. That
# makes keys unforgeable (nobody without the private key can mint a valid one)
# while keeping verification fully offline: no network, no phone-home, no clock.
# The signing key never lives in this repo. Rotate the operator's keypair with
# `h1license.py keygen` and paste the new public key into LICENSE_PUBLIC_KEY_HEX.
# --------------------------------------------------------------------------
LICENSE_ENV = "HACKERONETOOL_LICENSE"
LICENSE_FILE_ENV = "HACKERONETOOL_LICENSE_FILE"
DEFAULT_LICENSE_FILE = Path.home() / ".hackeronetool" / "license"

# The operator's Ed25519 public key (hex). Replace this with your own from
# `h1license.py keygen` so that only your private key can issue valid licenses.
# Overridable at runtime with HACKERONETOOL_PUBLIC_KEY (used by tests/CI).
LICENSE_PUBLIC_KEY_HEX = (
    "d92b78820c728c983b4b46c97234c15b7a8eb2e7d3950f3ae1a20a6515ee9ddd"
)
LICENSE_PUBLIC_KEY_ENV = "HACKERONETOOL_PUBLIC_KEY"

# Token: "H1K1.<b64url(payload)>.<b64url(signature)>". The signature covers
# _LICENSE_DOMAIN + payload, so a key for one tool/version can't be replayed as
# another. The payload is a short, human-meaningful subject (licensee/id).
LICENSE_PREFIX = "H1K1"
_LICENSE_DOMAIN = b"HackerOneTool-license-v1:"


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


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(text: str) -> bytes:
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


def public_key_bytes() -> bytes:
    """The public key licenses are verified against (env override, else embedded)."""
    hex_key = os.environ.get(LICENSE_PUBLIC_KEY_ENV) or LICENSE_PUBLIC_KEY_HEX
    try:
        key = bytes.fromhex(hex_key.strip())
    except ValueError as e:
        raise H1Error(f"malformed public key ({LICENSE_PUBLIC_KEY_ENV}): {e}") from e
    if len(key) != 32:
        raise H1Error("public key must be 32 bytes (64 hex chars)")
    return key


def _split_key(key: str) -> tuple[bytes, bytes] | None:
    """Parse a token into (payload, signature) bytes, or None if malformed."""
    parts = (key or "").strip().split(".")
    if len(parts) != 3 or parts[0] != LICENSE_PREFIX:
        return None
    try:
        payload = _b64url_decode(parts[1])
        signature = _b64url_decode(parts[2])
    except (ValueError, base64.binascii.Error):
        return None
    return payload, signature


def license_key_valid(key: str) -> bool:
    """Return True iff ``key`` is a valid, correctly signed license key.

    Pure and offline: verifies the Ed25519 signature against the public key.
    No network, no clock, no side effects; never raises on a malformed key.
    """
    parsed = _split_key(key)
    if parsed is None:
        return False
    payload, signature = parsed
    try:
        pub = public_key_bytes()
    except H1Error:
        return False
    return h1crypto.verify(signature, _LICENSE_DOMAIN + payload, pub)


def license_subject(key: str) -> str | None:
    """The subject embedded in a *valid* key (e.g. licensee), else None."""
    if not license_key_valid(key):
        return None
    payload, _ = _split_key(key)  # type: ignore[misc]
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError:
        return None


def sign_license(subject: str | None, private_key_hex: str) -> str:
    """Issue a signed license token for ``subject`` using a private signing key.

    Used by the ``h1license`` helper. Needs the private key, which only the
    operator holds — this is never called from the gated recon helpers.
    """
    try:
        priv = bytes.fromhex(private_key_hex.strip())
    except ValueError as e:
        raise H1Error(f"malformed private key: {e}") from e
    if len(priv) != 32:
        raise H1Error("private key must be 32 bytes (64 hex chars)")
    payload = (subject or os.urandom(8).hex()).encode("utf-8")
    pub = h1crypto.public_from_private(priv)
    signature = h1crypto.sign(_LICENSE_DOMAIN + payload, priv, pub)
    return ".".join(
        (LICENSE_PREFIX, _b64url_encode(payload), _b64url_encode(signature))
    )


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
            "invalid license key: it is malformed or not signed by the "
            "expected key. Check the value in "
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
