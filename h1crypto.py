"""h1crypto — minimal Ed25519 signatures, standard library only.

This is the public-domain reference implementation of Ed25519 from RFC 8032
(Appendix A / D. J. Bernstein's original), using only ``hashlib`` for SHA-512.
It is correct but not fast or side-channel resistant — which is fine here: it
signs/verifies a single short license token per invocation, not bulk traffic,
and the signing key never runs on an attacker-controlled machine.

Exposed helpers:
  keypair()                 -> (private_32_bytes, public_32_bytes)
  public_from_private(sk)   -> public_32_bytes
  sign(message, sk, pk)     -> signature_64_bytes
  verify(signature, message, pk) -> bool

Keys and signatures are raw bytes; callers hex/base64-encode them for storage.
"""
from __future__ import annotations

import hashlib
import os

# Curve / group parameters (Ed25519).
_b = 256
_q = 2 ** 255 - 19
_L = 2 ** 252 + 27742317777372353535851937790883648493


def _H(m: bytes) -> bytes:
    return hashlib.sha512(m).digest()


def _inv(x: int) -> int:
    return pow(x, _q - 2, _q)


_d = (-121665 * _inv(121666)) % _q
_I = pow(2, (_q - 1) // 4, _q)


def _xrecover(y: int) -> int:
    xx = (y * y - 1) * _inv(_d * y * y + 1)
    x = pow(xx, (_q + 3) // 8, _q)
    if (x * x - xx) % _q != 0:
        x = (x * _I) % _q
    if x % 2 != 0:
        x = _q - x
    return x


_By = (4 * _inv(5)) % _q
_Bx = _xrecover(_By)
_B = [_Bx % _q, _By % _q]


def _edwards(P, Q):
    x1, y1 = P
    x2, y2 = Q
    x3 = (x1 * y2 + x2 * y1) * _inv(1 + _d * x1 * x2 * y1 * y2)
    y3 = (y1 * y2 + x1 * x2) * _inv(1 - _d * x1 * x2 * y1 * y2)
    return [x3 % _q, y3 % _q]


def _scalarmult(P, e: int):
    if e == 0:
        return [0, 1]
    Q = _scalarmult(P, e // 2)
    Q = _edwards(Q, Q)
    if e & 1:
        Q = _edwards(Q, P)
    return Q


def _encodeint(y: int) -> bytes:
    bits = [(y >> i) & 1 for i in range(_b)]
    return bytes(
        sum(bits[i * 8 + j] << j for j in range(8)) for i in range(_b // 8)
    )


def _encodepoint(P) -> bytes:
    x, y = P
    bits = [(y >> i) & 1 for i in range(_b - 1)] + [x & 1]
    return bytes(
        sum(bits[i * 8 + j] << j for j in range(8)) for i in range(_b // 8)
    )


def _bit(h: bytes, i: int) -> int:
    return (h[i // 8] >> (i % 8)) & 1


def _secret_scalar(sk: bytes) -> int:
    h = _H(sk)
    return 2 ** (_b - 2) + sum(2 ** i * _bit(h, i) for i in range(3, _b - 2))


def public_from_private(sk: bytes) -> bytes:
    """Derive the 32-byte public key from a 32-byte private key seed."""
    if len(sk) != 32:
        raise ValueError("private key must be 32 bytes")
    A = _scalarmult(_B, _secret_scalar(sk))
    return _encodepoint(A)


def keypair() -> tuple[bytes, bytes]:
    """Generate a fresh (private, public) keypair."""
    sk = os.urandom(32)
    return sk, public_from_private(sk)


def _Hint(m: bytes) -> int:
    h = _H(m)
    return sum(2 ** i * _bit(h, i) for i in range(2 * _b))


def sign(message: bytes, sk: bytes, pk: bytes) -> bytes:
    """Sign ``message`` with private key ``sk`` (public ``pk``) -> 64 bytes."""
    if len(sk) != 32:
        raise ValueError("private key must be 32 bytes")
    h = _H(sk)
    a = _secret_scalar(sk)
    r = _Hint(h[_b // 8:_b // 4] + message)
    R = _scalarmult(_B, r)
    S = (r + _Hint(_encodepoint(R) + pk + message) * a) % _L
    return _encodepoint(R) + _encodeint(S)


def _isoncurve(P) -> bool:
    x, y = P
    return (-x * x + y * y - 1 - _d * x * x * y * y) % _q == 0


def _decodeint(s: bytes) -> int:
    return sum(2 ** i * _bit(s, i) for i in range(0, _b))


def _decodepoint(s: bytes):
    y = sum(2 ** i * _bit(s, i) for i in range(0, _b - 1))
    x = _xrecover(y)
    if x & 1 != _bit(s, _b - 1):
        x = _q - x
    P = [x, y]
    if not _isoncurve(P):
        raise ValueError("point is not on the curve")
    return P


def verify(signature: bytes, message: bytes, pk: bytes) -> bool:
    """Return True iff ``signature`` is a valid Ed25519 signature of ``message``.

    Never raises on a malformed signature or key — returns False instead.
    """
    try:
        if len(signature) != 64 or len(pk) != 32:
            return False
        R = _decodepoint(signature[:32])
        A = _decodepoint(pk)
        S = _decodeint(signature[32:])
        # A has order L, so reducing the hash scalar mod L is equivalent and
        # roughly halves the cost of this scalar multiplication.
        h = _Hint(_encodepoint(R) + pk + message) % _L
        return _scalarmult(_B, S) == _edwards(R, _scalarmult(A, h))
    except (ValueError, IndexError):
        return False
