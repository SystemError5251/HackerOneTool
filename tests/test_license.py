"""Tests for the offline, signature-based license gate in ``h1common``.

Everything here is local and deterministic — no network, no clock. Keys are
Ed25519 signatures; the tests generate a throwaway keypair, point the verifier
at its public key via the env override, and check that only keys signed by the
matching private key pass. The underlying Ed25519 primitives have their own
RFC 8032 vector test in ``test_h1crypto.py``.
"""
from __future__ import annotations

import pytest

import h1common
import h1crypto


@pytest.fixture()
def operator_key(monkeypatch):
    """A fresh signing keypair, installed as the verifier's public key."""
    priv, pub = h1crypto.keypair()
    monkeypatch.setenv(h1common.LICENSE_PUBLIC_KEY_ENV, pub.hex())
    return priv.hex(), pub.hex()


def _issue(priv_hex, subject="tester"):
    return h1common.sign_license(subject, priv_hex)


# --------------------------------------------------------------------------
# Signing + verifying
# --------------------------------------------------------------------------
def test_issued_key_is_valid_and_well_formed(operator_key):
    priv_hex, _ = operator_key
    key = _issue(priv_hex, "acme-corp")
    assert h1common.license_key_valid(key)
    assert key.startswith(h1common.LICENSE_PREFIX + ".")
    assert len(key.split(".")) == 3
    assert h1common.license_subject(key) == "acme-corp"


def test_key_without_subject_gets_a_random_one(operator_key):
    priv_hex, _ = operator_key
    a = _issue(priv_hex, None)
    b = _issue(priv_hex, None)
    assert a != b  # random payloads
    assert h1common.license_key_valid(a) and h1common.license_key_valid(b)


def test_whitespace_around_key_is_tolerated(operator_key):
    priv_hex, _ = operator_key
    key = _issue(priv_hex)
    assert h1common.license_key_valid(f"  {key}\n")


# --------------------------------------------------------------------------
# Forgery resistance — the whole point of the scheme
# --------------------------------------------------------------------------
def test_key_from_a_different_private_key_is_rejected(operator_key):
    # A key issued by someone else's signing key must not validate against the
    # operator's public key.
    other_priv, _ = h1crypto.keypair()
    forged = h1common.sign_license("mallory", other_priv.hex())
    assert not h1common.license_key_valid(forged)
    assert h1common.license_subject(forged) is None


def test_tampered_subject_breaks_the_signature(operator_key):
    priv_hex, _ = operator_key
    key = h1common.sign_license("basic", priv_hex)
    prefix, payload, sig = key.split(".")
    # Swap in a different (valid-base64) payload while keeping the signature.
    other_payload = h1common._b64url_encode(b"premium")
    forged = ".".join((prefix, other_payload, sig))
    assert not h1common.license_key_valid(forged)


def test_garbage_and_empty_keys_are_rejected(operator_key):
    for bad in ["", "not-a-key", "H1K1.only-two", "XXXX.aa.bb", "H1K1..", "H1K1.$$.$$"]:
        assert not h1common.license_key_valid(bad)


def test_flipping_a_signature_bit_is_rejected(operator_key):
    priv_hex, _ = operator_key
    key = _issue(priv_hex)
    prefix, payload, sig = key.split(".")
    raw = bytearray(h1common._b64url_decode(sig))
    raw[0] ^= 0x01
    forged = ".".join((prefix, payload, h1common._b64url_encode(bytes(raw))))
    assert not h1common.license_key_valid(forged)


# --------------------------------------------------------------------------
# Public-key resolution
# --------------------------------------------------------------------------
def test_env_public_key_overrides_embedded(monkeypatch):
    priv, pub = h1crypto.keypair()
    monkeypatch.setenv(h1common.LICENSE_PUBLIC_KEY_ENV, pub.hex())
    assert h1common.public_key_bytes() == pub


def test_embedded_public_key_is_used_without_override(monkeypatch):
    monkeypatch.delenv(h1common.LICENSE_PUBLIC_KEY_ENV, raising=False)
    assert h1common.public_key_bytes() == bytes.fromhex(h1common.LICENSE_PUBLIC_KEY_HEX)


def test_malformed_override_public_key_raises(monkeypatch):
    monkeypatch.setenv(h1common.LICENSE_PUBLIC_KEY_ENV, "not-hex")
    with pytest.raises(h1common.H1Error):
        h1common.public_key_bytes()


def test_sign_license_rejects_bad_private_key():
    with pytest.raises(h1common.H1Error):
        h1common.sign_license("x", "too-short")


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
# verify_license + run_cli: the gate behaviour
# --------------------------------------------------------------------------
def _clear_license(monkeypatch, tmp_path):
    monkeypatch.delenv(h1common.LICENSE_ENV, raising=False)
    monkeypatch.setenv(h1common.LICENSE_FILE_ENV, str(tmp_path / "missing"))


def test_verify_passes_with_valid_env_key(monkeypatch, tmp_path, operator_key):
    priv_hex, _ = operator_key
    _clear_license(monkeypatch, tmp_path)
    monkeypatch.setenv(h1common.LICENSE_ENV, _issue(priv_hex))
    h1common.verify_license()  # should not raise


def test_verify_raises_when_missing(monkeypatch, tmp_path):
    _clear_license(monkeypatch, tmp_path)
    with pytest.raises(h1common.H1Error) as e:
        h1common.verify_license()
    assert "no license key" in str(e.value)


def test_verify_raises_when_invalid(monkeypatch, tmp_path, operator_key):
    _clear_license(monkeypatch, tmp_path)
    monkeypatch.setenv(h1common.LICENSE_ENV, "H1K1.AA.BB")
    with pytest.raises(h1common.H1Error) as e:
        h1common.verify_license()
    assert "invalid license key" in str(e.value)


def test_run_cli_blocks_body_without_license(monkeypatch, tmp_path, capsys):
    _clear_license(monkeypatch, tmp_path)
    ran = []
    rc = h1common.run_cli(lambda: ran.append(True))
    assert rc == 1
    assert ran == []  # body never ran
    assert "error:" in capsys.readouterr().err


def test_run_cli_runs_body_with_valid_license(monkeypatch, tmp_path, operator_key):
    priv_hex, _ = operator_key
    _clear_license(monkeypatch, tmp_path)
    monkeypatch.setenv(h1common.LICENSE_ENV, _issue(priv_hex))
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
