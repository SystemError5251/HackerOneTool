"""Tests for the shared transport module ``h1common``.

The HTTP layer is fully mocked — no test here reaches HackerOne or any real
network. Each test replaces ``h1common``'s ``urlopen`` with a fake that
replays a scripted sequence of responses/errors, and replaces ``time.sleep``
so retries don't actually wait.
"""
from __future__ import annotations

import io
import json
import socket
import urllib.error

import pytest

import h1common


# --------------------------------------------------------------------------
# Test doubles
# --------------------------------------------------------------------------
class _FakeResponse:
    """Minimal stand-in for the object returned by ``urlopen`` (a context
    manager whose body ``json.load`` reads)."""

    def __init__(self, payload: dict):
        self._data = json.dumps(payload).encode()

    def read(self, *args, **kwargs):
        return self._data

    def __enter__(self):
        return io.BytesIO(self._data)

    def __exit__(self, *exc):
        return False


def _http_error(code: int, reason: str = "err", retry_after: str | None = None):
    headers = {}
    if retry_after is not None:
        headers["Retry-After"] = retry_after
    return urllib.error.HTTPError(
        url=h1common.GRAPHQL_URL, code=code, msg=reason, hdrs=headers, fp=None
    )


class _FakeUrlopen:
    """Replays a scripted list of outcomes, one per ``urlopen`` call.

    Each outcome is either an ``Exception`` (raised) or a ``dict`` (returned
    as a ``_FakeResponse`` body). Records every ``Request`` it was handed.
    """

    def __init__(self, outcomes):
        self._outcomes = list(outcomes)
        self.calls = []

    def __call__(self, req, timeout=None):
        self.calls.append(req)
        if not self._outcomes:
            raise AssertionError("urlopen called more times than scripted")
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return _FakeResponse(outcome)


@pytest.fixture
def no_sleep(monkeypatch):
    """Record backoff sleeps without actually waiting."""
    slept = []
    monkeypatch.setattr(h1common.time, "sleep", lambda s: slept.append(s))
    return slept


def _patch_urlopen(monkeypatch, outcomes):
    fake = _FakeUrlopen(outcomes)
    monkeypatch.setattr(h1common.urllib.request, "urlopen", fake)
    return fake


_OK = {"data": {"ok": True}}


# --------------------------------------------------------------------------
# valid_handle()
# --------------------------------------------------------------------------
class TestValidHandle:
    @pytest.mark.parametrize(
        "handle",
        ["mercadolibre", "a", "x1", "foo-bar", "foo_bar", "foo.bar", "A1b2", "0day"],
    )
    def test_accepts_valid_handles(self, handle):
        assert h1common.valid_handle(handle) == handle

    @pytest.mark.parametrize(
        "handle",
        [
            "",            # empty
            " ",           # whitespace
            "foo bar",     # space
            "foo bar OR 1",  # lucene operator smuggled in via spaces
            '"quoted"',    # quotes
            "-leading",    # must start alphanumeric
            ".dot",        # must start alphanumeric
            "_under",      # must start alphanumeric
            "foo/bar",     # slash
            "foo:bar",     # colon
            "foo*",        # wildcard
            "föö",         # non-ascii
        ],
    )
    def test_rejects_invalid_handles(self, handle):
        with pytest.raises(h1common.H1Error):
            h1common.valid_handle(handle)

    def test_error_message_names_the_bad_handle(self):
        with pytest.raises(h1common.H1Error) as exc:
            h1common.valid_handle("bad handle")
        assert "bad handle" in str(exc.value)


# --------------------------------------------------------------------------
# User-Agent header
# --------------------------------------------------------------------------
class TestUserAgent:
    def test_request_carries_user_agent(self, monkeypatch, no_sleep):
        fake = _patch_urlopen(monkeypatch, [_OK])
        h1common.graphql("query {}", {})
        assert len(fake.calls) == 1
        # urllib stores header keys capitalized: "User-Agent" -> "User-agent".
        assert fake.calls[0].get_header("User-agent") == h1common.USER_AGENT

    def test_request_sends_json_content_type(self, monkeypatch, no_sleep):
        fake = _patch_urlopen(monkeypatch, [_OK])
        h1common.graphql("query {}", {"handle": "mercadolibre"})
        req = fake.calls[0]
        assert req.get_header("Content-type") == "application/json"
        # body is the JSON-encoded query + variables
        sent = json.loads(req.data)
        assert sent["query"] == "query {}"
        assert sent["variables"] == {"handle": "mercadolibre"}


# --------------------------------------------------------------------------
# graphql() happy path
# --------------------------------------------------------------------------
class TestGraphqlSuccess:
    def test_returns_data_field(self, monkeypatch, no_sleep):
        _patch_urlopen(monkeypatch, [{"data": {"team": {"handle": "x"}}}])
        assert h1common.graphql("q", {}) == {"team": {"handle": "x"}}

    def test_missing_data_returns_empty_dict(self, monkeypatch, no_sleep):
        _patch_urlopen(monkeypatch, [{}])
        assert h1common.graphql("q", {}) == {}

    def test_graphql_level_errors_raise(self, monkeypatch, no_sleep):
        _patch_urlopen(monkeypatch, [{"errors": [{"message": "boom"}]}])
        with pytest.raises(h1common.H1Error) as exc:
            h1common.graphql("q", {})
        assert "boom" in str(exc.value)


# --------------------------------------------------------------------------
# Retry behaviour on 429 / 5xx (including Retry-After)
# --------------------------------------------------------------------------
class TestRetryOnHttpErrors:
    def test_retries_on_429_then_succeeds(self, monkeypatch, no_sleep):
        fake = _patch_urlopen(monkeypatch, [_http_error(429), _OK])
        assert h1common.graphql("q", {}, retries=3) == {"ok": True}
        assert len(fake.calls) == 2
        assert len(no_sleep) == 1  # one backoff between the two attempts

    @pytest.mark.parametrize("code", [500, 502, 503, 504])
    def test_retries_on_5xx_then_succeeds(self, monkeypatch, no_sleep, code):
        fake = _patch_urlopen(monkeypatch, [_http_error(code), _OK])
        assert h1common.graphql("q", {}, retries=3) == {"ok": True}
        assert len(fake.calls) == 2

    def test_honors_retry_after_header(self, monkeypatch, no_sleep):
        _patch_urlopen(monkeypatch, [_http_error(429, retry_after="5"), _OK])
        h1common.graphql("q", {}, retries=3)
        assert no_sleep == [5.0]

    def test_retry_after_is_capped_at_max_backoff(self, monkeypatch, no_sleep):
        _patch_urlopen(
            monkeypatch, [_http_error(503, retry_after="9999"), _OK]
        )
        h1common.graphql("q", {}, retries=3)
        assert no_sleep == [h1common.MAX_BACKOFF]

    def test_bad_retry_after_falls_back_to_exponential(self, monkeypatch, no_sleep):
        _patch_urlopen(
            monkeypatch, [_http_error(429, retry_after="soon"), _OK]
        )
        h1common.graphql("q", {}, retries=3)
        # attempt 0 -> 2 ** 0 == 1.0
        assert no_sleep == [1.0]

    def test_exhausts_retries_then_raises(self, monkeypatch, no_sleep):
        fake = _patch_urlopen(
            monkeypatch, [_http_error(503) for _ in range(4)]
        )
        with pytest.raises(h1common.H1Error) as exc:
            h1common.graphql("q", {}, retries=3)
        # 1 initial attempt + 3 retries
        assert len(fake.calls) == 4
        assert len(no_sleep) == 3
        assert "HTTP 503" in str(exc.value)

    def test_no_retries_when_retries_zero(self, monkeypatch, no_sleep):
        fake = _patch_urlopen(monkeypatch, [_http_error(429)])
        with pytest.raises(h1common.H1Error):
            h1common.graphql("q", {}, retries=0)
        assert len(fake.calls) == 1
        assert no_sleep == []


# --------------------------------------------------------------------------
# 4xx (other than 429) fails immediately, no retry
# --------------------------------------------------------------------------
class TestNoRetryOnClientErrors:
    @pytest.mark.parametrize("code", [400, 401, 403, 404, 422])
    def test_4xx_raises_without_retry(self, monkeypatch, no_sleep, code):
        fake = _patch_urlopen(monkeypatch, [_http_error(code), _OK])
        with pytest.raises(h1common.H1Error) as exc:
            h1common.graphql("q", {}, retries=3)
        assert len(fake.calls) == 1  # no retry
        assert no_sleep == []
        assert f"HTTP {code}" in str(exc.value)


# --------------------------------------------------------------------------
# Network errors map to H1Error
# --------------------------------------------------------------------------
class TestNetworkErrorMapping:
    @pytest.mark.parametrize(
        "err",
        [
            urllib.error.URLError("name resolution failed"),
            socket.timeout("timed out"),
            TimeoutError("timed out"),
        ],
    )
    def test_transient_network_error_is_retried_then_mapped(
        self, monkeypatch, no_sleep, err
    ):
        fake = _patch_urlopen(
            monkeypatch, [type(err)(*err.args) for _ in range(4)]
        )
        with pytest.raises(h1common.H1Error) as exc:
            h1common.graphql("q", {}, retries=3)
        assert len(fake.calls) == 4
        assert "network error" in str(exc.value)

    def test_network_error_then_success(self, monkeypatch, no_sleep):
        fake = _patch_urlopen(
            monkeypatch, [urllib.error.URLError("flaky"), _OK]
        )
        assert h1common.graphql("q", {}, retries=3) == {"ok": True}
        assert len(fake.calls) == 2

    def test_invalid_json_maps_to_h1error(self, monkeypatch, no_sleep):
        class _BadJsonResponse:
            def __enter__(self):
                return io.BytesIO(b"not json")

            def __exit__(self, *exc):
                return False

        monkeypatch.setattr(
            h1common.urllib.request, "urlopen", lambda req, timeout=None: _BadJsonResponse()
        )
        with pytest.raises(h1common.H1Error) as exc:
            h1common.graphql("q", {})
        assert "invalid JSON" in str(exc.value)

    def test_error_message_names_the_host(self, monkeypatch, no_sleep):
        _patch_urlopen(monkeypatch, [urllib.error.URLError("down") for _ in range(4)])
        with pytest.raises(h1common.H1Error) as exc:
            h1common.graphql("q", {}, retries=3)
        # _host() derives the netloc from GRAPHQL_URL
        assert h1common._host() in str(exc.value)
