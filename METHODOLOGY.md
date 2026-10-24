# Authorized testing methodology

A repeatable workflow for account-takeover / 2FA-bypass testing and for
Tier 3 (leak & misconfiguration) hunting, scoped to programs that have
authorized you. It is written to respect the common program bans we see on
HackerOne (no mass automated scanning, no brute force / rate-limit probing,
no DoS, no touching other users' accounts, confirm-only on leaks).

## 0. Ground rules (every target, every time)

- Test only assets the program marks `eligible_for_submission`. Re-pull the
  scope before each engagement with `h1scope.py` — scopes change.
- Use accounts you own or official test users. Never access a real user's
  account or data.
- No mass automated scanning, no brute force, no rate-limit hammering, no DoS.
  Work manually and human-paced.
- For leaks: confirm existence only. One non-destructive validation call is
  the limit — do not exfiltrate, pivot, or reuse data.
- Log every request/response with timestamps so reports are reproducible.
- Nothing public until the program agrees to disclosure.

## 1. Confirm authorization & pull scope

```bash
python3 h1scope.py <handle> --policy
```

Note per-asset tier and max severity, and read that program's specific bans
and considerations before touching anything.

## 2. Recon (passive first)

Subdomains (certificate transparency, passive DNS), tech stack, published API
docs, mobile app endpoints. Passive sources before any active request.

## 3. Map the auth surface

Create two test accounts you control (victim + attacker), both with 2FA on.
Document every login, password-reset, email/phone-change, "remember device",
OAuth/SSO, and 2FA challenge flow across web, mobile, and API.

## 4. ATO / 2FA-bypass checks (on your own accounts)

- **Response manipulation** — flip a `verified`/`success` flag in the 2FA
  response; does the client trust it?
- **Step skipping** — after factor one, call the post-2FA endpoint directly.
  Is the second factor enforced server-side or only hidden in the UI?
- **Code handling** — codes that don't expire, aren't invalidated after use,
  or are reusable across sessions. Demonstrate a *missing* lockout with a few
  requests — do not brute force.
- **Recovery paths** — "lost device", backup codes, SMS fallback skipping the
  stronger factor.
- **Tokens/sessions** — authenticated session issued *before* 2FA completes;
  pre-2FA token replay; session not invalidated after password change.
- **Race conditions** — a handful of concurrent requests around verify.
- **OAuth/SSO** — account-link binding an attacker identity to a victim;
  `redirect_uri`/state weaknesses leaking codes.
- **Adjacent ATO chains** — reset-token leakage/predictability/reuse, IDOR on
  account-management endpoints, email/phone change without re-auth.

Prove each on your two accounts, capture request/response, write the minimal
repro.

## 5. Tier 3 leak sweep

- Public code/paste search for the org's domains, internal hostnames, and
  employee corporate emails in commit authorship → committed tokens, keys,
  `.env` files.
- Misconfigured storage/dashboards with PII reachable without auth, on
  in-scope hosts.
- Dangling DNS → subdomain takeover: prove you can insert content, include
  CNAME/A + provider + claim steps, do not steal cookies or interact with
  users.
- Ownership must be demonstrable (corporate email in commits, internal
  references, in-scope host). Validity: one non-destructive call, then stop.

## 6. Validate & report

Minimal non-destructive PoC. Report: title, affected asset + tier, repro
steps, impact, CVSS 3.1 where applicable. For Tier 3: source location +
ownership evidence + validity note. One bounty per source.
