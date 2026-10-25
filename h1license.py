#!/usr/bin/env python3
"""h1license — issue and check license keys for the h1* recon helpers.

The recon helpers (`h1scope.py`, `h1reports.py`, `h1report.py`) refuse to run
without a valid license key (see the README's "License key" section). Keys are
Ed25519 signatures: you issue them with a *private* signing key that only you
hold, and the tools verify them offline against the embedded *public* key. No
network, no phone-home. This utility does not itself require a license.

Setup (once):
  ./h1license.py keygen              # make your signing keypair; prints the
                                     # public key to paste into h1common.py

Issue / verify:
  ./h1license.py new                 # issue a key (random subject)
  ./h1license.py new --subject acme  # issue a key tied to a subject/licensee
  ./h1license.py check <key>         # verify a key (exit 0 = valid)
  ./h1license.py install <key>       # save a valid key to the default file

The private signing key is read from --key-file, else $HACKERONETOOL_SIGNING_KEY
(hex), else $HACKERONETOOL_SIGNING_KEY_FILE, else ~/.hackeronetool/signing_key.
Keep it secret and out of the repo.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import h1crypto
from h1common import (
    DEFAULT_LICENSE_FILE,
    H1Error,
    license_key_valid,
    license_subject,
    sign_license,
)

SIGNING_KEY_ENV = "HACKERONETOOL_SIGNING_KEY"
SIGNING_KEY_FILE_ENV = "HACKERONETOOL_SIGNING_KEY_FILE"
DEFAULT_SIGNING_KEY_FILE = Path.home() / ".hackeronetool" / "signing_key"


def _write_private(path: Path, priv_hex: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(priv_hex + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def _load_signing_key(key_file: str | None) -> str:
    """Resolve the private signing key: --key-file, env, env file, default file."""
    if key_file:
        return Path(key_file).read_text(encoding="utf-8").strip()
    env = os.environ.get(SIGNING_KEY_ENV)
    if env and env.strip():
        return env.strip()
    path_str = os.environ.get(SIGNING_KEY_FILE_ENV)
    path = Path(path_str) if path_str else DEFAULT_SIGNING_KEY_FILE
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        raise H1Error(
            "no signing key found. Run './h1license.py keygen' first, or set "
            f"{SIGNING_KEY_ENV} / {SIGNING_KEY_FILE_ENV}."
        )


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Issue and check h1* license keys.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_keygen = sub.add_parser("keygen", help="generate a signing keypair")
    p_keygen.add_argument(
        "--out", help=f"private key path (default {DEFAULT_SIGNING_KEY_FILE})"
    )
    p_keygen.add_argument(
        "--force", action="store_true", help="overwrite an existing key file"
    )

    p_new = sub.add_parser("new", help="issue a license key")
    p_new.add_argument("--subject", help="licensee / id to embed (optional)")
    p_new.add_argument("--count", type=int, default=1, help="how many (default 1)")
    p_new.add_argument("--key-file", help="private signing key file")

    p_check = sub.add_parser("check", help="verify a license key")
    p_check.add_argument("key", help="the key to check")

    p_install = sub.add_parser("install", help="save a key to the default file")
    p_install.add_argument("key", help="the key to install")

    args = ap.parse_args(argv)

    def run() -> None:
        if args.cmd == "keygen":
            out = Path(args.out) if args.out else DEFAULT_SIGNING_KEY_FILE
            if out.exists() and not args.force:
                raise H1Error(f"{out} already exists (use --force to overwrite)")
            priv, pub = h1crypto.keypair()
            _write_private(out, priv.hex())
            pub_path = out.with_name(out.name + ".pub")
            pub_path.write_text(pub.hex() + "\n", encoding="utf-8")
            print(f"private signing key -> {out} (keep secret, do not commit)")
            print(f"public key          -> {pub_path}")
            print()
            print("Public key (paste into h1common.LICENSE_PUBLIC_KEY_HEX):")
            print(pub.hex())
        elif args.cmd == "new":
            if args.count < 1:
                raise H1Error("--count must be at least 1")
            if args.subject and args.count != 1:
                raise H1Error("--subject issues a single key; drop --count")
            priv_hex = _load_signing_key(args.key_file)
            for _ in range(args.count):
                print(sign_license(args.subject, priv_hex))
        elif args.cmd == "check":
            if license_key_valid(args.key):
                subj = license_subject(args.key)
                print(f"valid (subject: {subj})" if subj else "valid")
            else:
                raise H1Error("invalid license key")
        elif args.cmd == "install":
            if not license_key_valid(args.key):
                raise H1Error("refusing to install an invalid license key")
            DEFAULT_LICENSE_FILE.parent.mkdir(parents=True, exist_ok=True)
            DEFAULT_LICENSE_FILE.write_text(args.key.strip() + "\n", encoding="utf-8")
            try:
                DEFAULT_LICENSE_FILE.chmod(0o600)
            except OSError:
                pass
            print(f"installed license key to {DEFAULT_LICENSE_FILE}")

    # This tool issues/validates keys, so it must run without a license itself.
    # Surface a couple of extra I/O errors as clean one-line messages too.
    try:
        run()
        return 0
    except (H1Error, ValueError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
