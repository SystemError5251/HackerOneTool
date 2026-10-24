#!/usr/bin/env python3
"""h1scope — pull the scope and policy of a HackerOne program.

Step 1 of any authorized bug-bounty engagement: know exactly what you are
allowed to touch. Given a program handle, this prints the structured scopes
(filtered to what you may actually submit against) with their tiers and max
severity, plus the program's own rules.

Everything here is read-only: it queries HackerOne's public GraphQL endpoint,
the same data shown on the program page. It sends no traffic to the target's
own assets, so it breaks no program's "no automated scanning" rule.

Usage:
    python3 h1scope.py mercadolibre
    python3 h1scope.py mercadolibre --json
    python3 h1scope.py mercadolibre --all        # include out-of-scope entries
    python3 h1scope.py mercadolibre --policy      # also print the full policy
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request

GRAPHQL_URL = "https://hackerone.com/graphql"

SCOPE_QUERY = """
query Scopes($handle: String!) {
  team(handle: $handle) {
    name
    handle
    offers_bounties
    state
    submission_state
    structured_scopes(first: 500, archived: false) {
      total_count
      edges {
        node {
          asset_type
          asset_identifier
          eligible_for_bounty
          eligible_for_submission
          max_severity
          instruction
        }
      }
    }
  }
}
"""

POLICY_QUERY = """
query Policy($handle: String!) {
  team(handle: $handle) { policy }
}
"""


def graphql(query: str, variables: dict) -> dict:
    """POST a GraphQL query and return the parsed JSON, or raise on error."""
    payload = json.dumps({"query": query, "variables": variables}).encode()
    req = urllib.request.Request(
        GRAPHQL_URL,
        data=payload,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.load(resp)
    if body.get("errors"):
        msgs = "; ".join(e.get("message", "?") for e in body["errors"])
        raise RuntimeError(f"GraphQL error: {msgs}")
    return body["data"]


def fetch_scopes(handle: str) -> dict:
    team = graphql(SCOPE_QUERY, {"handle": handle})["team"]
    if team is None:
        raise RuntimeError(f"No program found for handle '{handle}'.")
    return team


def fetch_policy(handle: str) -> str:
    team = graphql(POLICY_QUERY, {"handle": handle})["team"]
    if team is None:
        raise RuntimeError(f"No program found for handle '{handle}'.")
    return team.get("policy") or ""


def classify(node: dict) -> str:
    """One of: submit+bounty, submit-only, out-of-scope."""
    if not node["eligible_for_submission"]:
        return "out-of-scope"
    return "submit+bounty" if node["eligible_for_bounty"] else "submit-only"


def print_report(team: dict, include_all: bool) -> None:
    edges = [e["node"] for e in team["structured_scopes"]["edges"]]
    groups = {"submit+bounty": [], "submit-only": [], "out-of-scope": []}
    for n in edges:
        groups[classify(n)].append(n)

    print(f"# {team['name']}  (@{team['handle']})")
    print(f"  state={team['state']}  submissions={team['submission_state']}"
          f"  bounties={'yes' if team['offers_bounties'] else 'no'}")
    print(f"  scope entries: {team['structured_scopes']['total_count']}")
    print()

    sections = [
        ("ELIGIBLE FOR BOUNTY (test + get paid)", "submit+bounty"),
        ("SUBMIT ONLY (no bounty)", "submit-only"),
    ]
    if include_all:
        sections.append(("OUT OF SCOPE (do not test)", "out-of-scope"))

    for title, key in sections:
        rows = groups[key]
        print(f"== {title} — {len(rows)} ==")
        if not rows:
            print("  (none)")
        for n in sorted(rows, key=lambda x: (x["asset_type"], x["asset_identifier"])):
            tier = (n["instruction"] or "").strip().splitlines()[0] if n["instruction"] else ""
            tier = f"  [{tier[:60]}]" if tier else ""
            print(f"  {n['asset_type']:<18} {n['asset_identifier']:<42}"
                  f" max={n['max_severity'] or '-'}{tier}")
        print()


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Pull a HackerOne program's scope and policy.")
    ap.add_argument("handle", help="program handle, e.g. 'mercadolibre'")
    ap.add_argument("--json", action="store_true", help="emit raw scope JSON instead of a table")
    ap.add_argument("--all", action="store_true", help="include out-of-scope entries")
    ap.add_argument("--policy", action="store_true", help="also print the full program policy")
    args = ap.parse_args(argv)

    try:
        team = fetch_scopes(args.handle)
        if args.json:
            print(json.dumps(team, indent=2))
        else:
            print_report(team, include_all=args.all)
        if args.policy:
            print("=" * 60)
            print(fetch_policy(args.handle))
    except (RuntimeError, urllib.error.URLError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
