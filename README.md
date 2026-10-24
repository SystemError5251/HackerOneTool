# HackerOneTool

Helpers for **authorized** bug-bounty work on HackerOne programs.

The only rule that matters: test an asset only when the program lists it as
`eligible_for_submission`, use accounts you own or provisioned test users, and
follow that program's written policy. These tools are read-only recon against
HackerOne's own public API — they send no traffic to any target's assets.

## `h1scope.py`

Step 1 of any engagement: know exactly what you are allowed to touch. Given a
program handle, it pulls the structured scopes and sorts them into
*eligible for bounty* / *submit only* / *out of scope*, with each asset's tier
and max severity, and can print the full program policy.

```bash
python3 h1scope.py mercadolibre            # scope table
python3 h1scope.py mercadolibre --all      # include out-of-scope entries
python3 h1scope.py mercadolibre --policy   # also dump the policy text
python3 h1scope.py mercadolibre --json     # raw JSON for scripting
```

No dependencies beyond the Python 3 standard library.

## Testing methodology

See [`METHODOLOGY.md`](METHODOLOGY.md) for the ATO / 2FA-bypass and Tier 3
leak workflow, written to stay inside program rules (no mass scanning, no
brute force, confirm-only on leaks, test on your own accounts).
