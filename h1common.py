"""h1common — shared transport for the h1* HackerOne recon helpers.

Read-only access to HackerOne's public GraphQL endpoint, with a User-Agent,
bounded retries on transient failures, clear errors, and program-handle
validation. Standard library only; sends nothing to any target's assets.

The endpoint can be overridden with the HACKERONE_GRAPHQL environment variable
(used by the offline mock server and the test suite).
"""
from __future__ import annotations

import json
import os
import re
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable

GRAPHQL_URL = os.environ.get("HACKERONE_GRAPHQL", "https://hackerone.com/graphql")
USER_AGENT = "HackerOneTool/1.0 (+https://github.com/SystemError5251/HackerOneTool)"
DEFAULT_TIMEOUT = 30.0
DEFAULT_RETRIES = 3
MAX_BACKOFF = 8.0

# A HackerOne program handle: starts alphanumeric, then letters/digits/._-.
_HANDLE_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$", re.IGNORECASE)


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


def run_cli(body: Callable[[], None]) -> int:
    """Run a CLI body, turning expected errors into a stderr line + exit 1.

    Exits quietly on a broken pipe (e.g. output piped into `head`) instead of
    dumping a traceback, and on Ctrl-C.
    """
    try:
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
