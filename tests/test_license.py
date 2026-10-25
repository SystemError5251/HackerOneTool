"""Tests for the offline license gate in ``h1common``.

Everything here is local and deterministic — no network, no clock. The gate's
job is only to let a valid key through and to refuse a missing or malformed one
with a clean message, so that is what these tests pin down.
"""
from __future__ import annotations

import pytest

import h1common


# --------------------------------------------------------------------------
# Key format: mint, validate, reject
# --------------------------------------------------------------------------
def test_make_key_is_valid_and_well_formed():
    key = h1common.make_license_key()
    assert h1common.license_key_valid(key)
    # H1- prefix + four 5-char groups joined by dashes.
    parts = key.split("-")
    assert parts[0] == "H1"
    assert len(parts) == 5
    assert all(len(p) == 5 for p in parts[1:])
    assert all(c in h1common._KEY_ALPHABET for p in parts[1:] for c in p)


def test_make_key_is_deterministic_for_a_serial():
    a = h1common.make_license_key("ABCDE12345FGHJK")
    b = h1common.make_license_key("ABCDE12345FGHJK")
    assert a == b
    assert h1common.license_key_valid(a)


def test_make_key_rejects_bad_serial():
    with pytest.raises(h1common.H1Error):
        h1common.make_license_key("TOO-SHORT")
    with pytest.raises(h1common.H1Error):
        # 'I' is not in the Crockford-style alphabet.
        h1common.make_license_key("IIIIIIIIIIIIIII")


def test_valid_key_normalizes_case_whitespace_and_missing_dashes():
    key = h1common.make_license_key("ABCDE12345FGHJK")
    assert h1common.license_key_valid(key.lower())
    assert h1common.license_key_valid(f"  {key}  ")
    assert h1common.license_key_valid(key.replace("-", ""))


def test_tampered_or_garbage_keys_are_rejected():
    key = h1common.make_license_key("ABCDE12345FGHJK")
    flipped = key[:-1] + ("A" if key[-1] != "A" else "B")
    assert not h1common.license_key_valid(flipped)
    assert not h1common.license_key_valid("")
    assert not h1common.license_key_valid("not-a-key")
    assert not h1common.license_key_valid("H1-AAAAA-AAAAA-AAAAA-AAAAA")


# --------------------------------------------------------------------------
# load_license_key: env var vs. file, precedence
# --------------------------------------------------------------------------
def test_load_prefers_env_var(monkeypatch):
    monkeypatch.setenv(h1common.LICENSE_ENV, "  K-FROM-ENV  ")
    assert h1common.load_license_key() == "K-FROM-ENV"


def test_load_reads_file_when_env_absent(monkeypatch, tmp_path):
    monkeypatch.delenv(h1common.LICENSE_ENV, raising=False)
    f = tmp_path / "license"
    f.write_text("# a comment\n\nK-FROM-FILE\n", encoding="utf-8")
    monkeypatch.setenv(h1common.LICENSE_FILE_ENV, str(f))
    assert h1common.load_license_key() == "K-FROM-FILE"


def test_load_returns_none_when_nothing_found(monkeypatch, tmp_path):
    monkeypatch.delenv(h1common.LICENSE_ENV, raising=False)
    monkeypatch.setenv(h1common.LICENSE_FILE_ENV, str(tmp_path / "missing"))
    assert h1common.load_license_key() is None


# --------------------------------------------------------------------------
# verify_license: the gate behaviour
# --------------------------------------------------------------------------
def _clear_license(monkeypatch, tmp_path):
    monkeypatch.delenv(h1common.LICENSE_ENV, raising=False)
    monkeypatch.setenv(h1common.LICENSE_FILE_ENV, str(tmp_path / "missing"))


def test_verify_passes_with_valid_env_key(monkeypatch, tmp_path):
    _clear_license(monkeypatch, tmp_path)
    monkeypatch.setenv(h1common.LICENSE_ENV, h1common.make_license_key())
    h1common.verify_license()  # should not raise


def test_verify_raises_when_missing(monkeypatch, tmp_path):
    _clear_license(monkeypatch, tmp_path)
    with pytest.raises(h1common.H1Error) as e:
        h1common.verify_license()
    assert "no license key" in str(e.value)


def test_verify_raises_when_invalid(monkeypatch, tmp_path):
    _clear_license(monkeypatch, tmp_path)
    monkeypatch.setenv(h1common.LICENSE_ENV, "H1-AAAAA-AAAAA-AAAAA-AAAAA")
    with pytest.raises(h1common.H1Error) as e:
        h1common.verify_license()
    assert "invalid license key" in str(e.value)


# --------------------------------------------------------------------------
# run_cli: the gate runs before the body, and can be skipped
# --------------------------------------------------------------------------
def test_run_cli_blocks_body_without_license(monkeypatch, tmp_path, capsys):
    _clear_license(monkeypatch, tmp_path)
    ran = []
    rc = h1common.run_cli(lambda: ran.append(True))
    assert rc == 1
    assert ran == []  # body never ran
    assert "error:" in capsys.readouterr().err


def test_run_cli_runs_body_with_valid_license(monkeypatch, tmp_path):
    _clear_license(monkeypatch, tmp_path)
    monkeypatch.setenv(h1common.LICENSE_ENV, h1common.make_license_key())
    ran = []
    rc = h1common.run_cli(lambda: ran.append(True))
    assert rc == 0
    assert ran == [True]


def test_run_cli_skips_gate_when_not_required(monkeypatch, tmp_path):
    _clear_license(monkeypatch, tmp_path)  # no license at all
    ran = []
    rc = h1common.run_cli(lambda: ran.append(True), require_license=False)
    assert rc == 0
    assert ran == [True]
