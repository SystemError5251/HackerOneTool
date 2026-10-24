#!/usr/bin/env python3
"""h1reports — list a HackerOne program's publicly disclosed reports.

Recon step that pairs with h1scope.py: before testing an asset, check what has
already been found and fixed so you don't re-report a known issue and so you
can see the bug classes that land on this program. It reads HackerOne's public
Hacktivity index (the same data as the program's Hacktivity tab) and prints
each disclosed report with its severity, award, date, and link.

Read-only against HackerOne's public API; sends nothing to any target asset.

Usage:
    python3 h1reports.py mercadolibre
    python3 h1reports.py mercadolibre --limit 50
    python3 h1reports.py mercadolibre --grep "2fa|account takeover|ato"
    python3 h1reports.py mercadolibre --json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request

GRAPHQL_URL = "https://hackerone.com/graphql"

# The Hacktivity index is a flat search index; a program's disclosed reports
# are selected with the `team_handle` field plus `disclosed:true`.
SEARCH_QUERY = """
query Hacktivity($q: String!, $from: Int!, $size: Int!) {
  search(
    index: CompleteHacktivityReportIndex
    query_string: $q
    from: $from
    size: $size
    sort: { field: "latest_disclosable_activity_at", direction: DESC }
  ) {
    total_count
    nodes {
      __typename
      ... on HacktivityDocument {
        id
        severity_rating
        total_awarded_amount
        currency
        disclosed_at
        report { title url created_at }
      }
    }
  }
}
"""


def graphql(query: str, variables: dict) -> dict:
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


def fetch_reports(handle: str, limit: int) -> tuple[int, list[dict]]:
    """Return (total_count, reports). Pages through the index as needed."""
    q = f"team_handle:{handle} AND disclosed:true"
    reports: list[dict] = []
    total = 0
    page = 100  # index max page size
    offset = 0
    while len(reports) < limit:
        want = min(page, limit - offset)
        data = graphql(SEARCH_QUERY, {"q": q, "from": offset, "size": want})["search"]
        total = data["total_count"]
        nodes = [n for n in data["nodes"] if n.get("report")]
        reports.extend(nodes)
        offset += want
        if offset >= total or not data["nodes"]:
            break
    return total, reports[:limit]


def fmt_amount(node: dict) -> str:
    amt = node.get("total_awarded_amount")
    if amt in (None, "", "0", 0):
        return "-"
    cur = (node.get("currency") or "usd").upper()
    return f"{amt} {cur}"


def print_report(handle: str, total: int, reports: list[dict], grep: str | None) -> None:
    pat = re.compile(grep, re.I) if grep else None
    if pat:
        reports = [r for r in reports if pat.search((r.get("report") or {}).get("title") or "")]

    print(f"# {handle} — {total} disclosed report(s)"
          + (f", {len(reports)} match /{grep}/" if grep else "")
          + f", showing {len(reports)}")
    print()
    for n in reports:
        r = n.get("report") or {}
        date = (n.get("disclosed_at") or "?")[:10]
        sev = (n.get("severity_rating") or "-").lower()
        print(f"  {date}  {sev:<8} {fmt_amount(n):<12} {r.get('title') or '(untitled)'}")
        print(f"            {r.get('url')}")
    if not reports:
        print("  (no disclosed reports)" if not grep else "  (no matches)")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="List a HackerOne program's publicly disclosed reports.")
    ap.add_argument("handle", help="program handle, e.g. 'mercadolibre'")
    ap.add_argument("--limit", type=int, default=25, help="max reports to fetch (default 25)")
    ap.add_argument("--grep", help="regex filtered against report titles (case-insensitive)")
    ap.add_argument("--json", action="store_true", help="emit raw JSON instead of a table")
    args = ap.parse_args(argv)

    try:
        total, reports = fetch_reports(args.handle, max(args.limit, 1))
        if args.json:
            print(json.dumps({"total_count": total, "reports": reports}, indent=2))
        else:
            print_report(args.handle, total, reports, args.grep)
    except (RuntimeError, urllib.error.URLError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
