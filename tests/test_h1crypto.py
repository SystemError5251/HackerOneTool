"""Tests for the Ed25519 primitives in ``h1crypto``.

Pins the implementation against an official RFC 8032 (Section 7.1) test vector,
plus round-trip and rejection properties. Pure and offline.
"""
from __future__ import annotations

import binascii

import h1crypto


def _hx(s: str) -> bytes:
    return binascii.unhexlify(s)


# RFC 8032, Section 7.1, Test 1 (empty message).
_SK = _hx("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60")
_PK = _hx("d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a")
_SIG = _hx(
    "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e06522490155"
    "5fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b"
)


def test_rfc8032_test1_public_key():
    assert h1crypto.public_from_private(_SK) == _PK


def test_rfc8032_test1_signature():
    assert h1crypto.sign(b"", _SK, _PK) == _SIG


def test_rfc8032_test1_verify():
    assert h1crypto.verify(_SIG, b"", _PK) is True


def test_roundtrip_sign_verify():
    sk, pk = h1crypto.keypair()
    msg = b"authorized recon only"
    sig = h1crypto.sign(msg, sk, pk)
    assert h1crypto.verify(sig, msg, pk) is True


def test_wrong_message_is_rejected():
    sk, pk = h1crypto.keypair()
    sig = h1crypto.sign(b"original", sk, pk)
    assert h1crypto.verify(sig, b"tampered", pk) is False


def test_wrong_key_is_rejected():
    sk, pk = h1crypto.keypair()
    _, other_pk = h1crypto.keypair()
    sig = h1crypto.sign(b"m", sk, pk)
    assert h1crypto.verify(sig, b"m", other_pk) is False


def test_malformed_inputs_return_false_not_raise():
    _, pk = h1crypto.keypair()
    assert h1crypto.verify(b"", b"m", pk) is False
    assert h1crypto.verify(b"\x00" * 64, b"m", b"\x00" * 31) is False


def test_keypair_is_random():
    assert h1crypto.keypair()[0] != h1crypto.keypair()[0]
