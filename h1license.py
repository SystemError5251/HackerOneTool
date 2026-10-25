#!/usr/bin/env python3
"""h1license — mint and check license keys for the h1* recon helpers.

The recon helpers (`h1scope.py`, `h1reports.py`, `h1report.py`) refuse to run
without a valid license key (see the README's "License key" section). This
utility generates keys and verifies them. It is fully offline — no network, no
phone-home — and it does not itself require a license.

Usage:
  ./h1license.py new                 # mint a random key
  ./h1license.py new --count 5       # mint several
  ./h1license.py new --serial <15>   # mint a key for a specific serial
  ./h1license.py check <key>         # verify a key (exit 0 = valid, 1 = not)
  ./h1license.py install <key>       # save a key to the default license file
"""
from __future__ import annotations

import argparse
import sys

from h1common import (
    DEFAULT_LICENSE_FILE,
    H1Error,
    license_key_valid,
    make_license_key,
    run_cli,
)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Mint and check h1* license keys.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_new = sub.add_parser("new", help="mint one or more license keys")
    p_new.add_argument("--count", type=int, default=1, help="how many to mint (default 1)")
    p_new.add_argument("--serial", help="15-char serial to mint a key for (optional)")

    p_check = sub.add_parser("check", help="verify a license key")
    p_check.add_argument("key", help="the key to check")

    p_install = sub.add_parser("install", help="save a key to the default license file")
    p_install.add_argument("key", help="the key to install")

    args = ap.parse_args(argv)

    def run() -> None:
        if args.cmd == "new":
            if args.count < 1:
                raise H1Error("--count must be at least 1")
            if args.serial and args.count != 1:
                raise H1Error("--serial can only mint a single key; drop --count")
            for _ in range(args.count):
                print(make_license_key(args.serial))
        elif args.cmd == "check":
            if license_key_valid(args.key):
                print("valid")
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

    # This tool mints/validates keys, so it must run without a license itself.
    return run_cli(run, require_license=False)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
