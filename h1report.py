#!/usr/bin/env python3
"""h1report — show the detail of a single disclosed HackerOne report.

Pairs with h1reports.py: once you've spotted a relevant disclosed report
(e.g. a past account-takeover), pull its metadata and lifecycle timeline to
study what class of bug it was, how severe, what it paid, and how long triage
took. The full narrative text is not exposed through the public API, so the
report URL is printed for the write-up itself.

Read-only against HackerOne's public API; sends nothing to any target asset.

Usage:
    python3 h1report.py 2289836
    python3 h1report.py https://hackerone.com/reports/2289836
    python3 h1report.py 2289836 --json
"""
from __future__ import annotations

import argparse
import json
import re
import sys

from h1common import DEFAULT_TIMEOUT, graphql, run_cli

REPORT_QUERY = """
query Report($id: Int!) {
  report(id: $id) {
    id
    title
    substate
    created_at
    disclosed_at
    severity { rating score }
    weakness { name }
    reporter { username }
    team { handle name }
    bounties { nodes { awarded_amount bonus_amount } }
    activities {
      nodes {
        __typename
        ... on ActivitiesBugFiled { created_at }
        ... on ActivitiesBugNew { created_at }
        ... on ActivitiesBugTriaged { created_at }
        ... on ActivitiesBugNeedsMoreInfo { created_at }
        ... on ActivitiesReportSeverityUpdated { created_at }
        ... on ActivitiesBountyAwarded { created_at }
        ... on ActivitiesBountySuggested { created_at }
        ... on ActivitiesBugResolved { created_at }
        ... on ActivitiesBugInformative { created_at }
        ... on ActivitiesBugNotApplicable { created_at }
        ... on ActivitiesBugDuplicate { created_at }
        ... on ActivitiesComment { created_at }
        ... on ActivitiesAgreedOnGoingPublic { created_at }
        ... on ActivitiesReportBecamePublic { created_at }
        ... on ActivitiesReportTitleUpdated { created_at }
      }
    }
  }
}
"""


def parse_id(raw: str) -> int:
    m = re.search(r"(\d+)", raw)
    if not m:
        raise ValueError(f"could not find a report id in '{raw}'")
    return int(m.group(1))


def fetch_report(report_id: int, timeout: float = DEFAULT_TIMEOUT) -> dict:
    report = graphql(REPORT_QUERY, {"id": report_id}, timeout=timeout)["report"]
    if report is None:
        raise RuntimeError(f"report {report_id} not found or not public")
    return report


def total_bounty(report: dict) -> str:
    nodes = (report.get("bounties") or {}).get("nodes") or []
    awarded = sum(float(n.get("awarded_amount") or 0) for n in nodes)
    bonus = sum(float(n.get("bonus_amount") or 0) for n in nodes)
    total = awarded + bonus
    if total <= 0:
        return "- (not disclosed)"
    extra = f" (+{bonus:g} bonus)" if bonus else ""
    return f"${total:g}{extra}"


# Readable labels for the timeline event types we select above.
EVENT_LABELS = {
    "ActivitiesBugFiled": "filed",
    "ActivitiesBugNew": "new",
    "ActivitiesBugTriaged": "triaged",
    "ActivitiesBugNeedsMoreInfo": "needs more info",
    "ActivitiesReportSeverityUpdated": "severity updated",
    "ActivitiesBountyAwarded": "bounty awarded",
    "ActivitiesBountySuggested": "bounty suggested",
    "ActivitiesBugResolved": "resolved",
    "ActivitiesBugInformative": "informative",
    "ActivitiesBugNotApplicable": "not applicable",
    "ActivitiesBugDuplicate": "duplicate",
    "ActivitiesComment": "comment",
    "ActivitiesAgreedOnGoingPublic": "agreed to disclose",
    "ActivitiesReportBecamePublic": "became public",
    "ActivitiesReportTitleUpdated": "title updated",
}


def print_report(report: dict, report_id: int, show_comments: bool) -> None:
    sev = report.get("severity") or {}
    rating = sev.get("rating") or "-"
    score = sev.get("score")
    weakness = (report.get("weakness") or {}).get("name") or "-"
    team = report.get("team") or {}
    url = f"https://hackerone.com/reports/{report_id}"

    print(f"# {report['title']}")
    print(f"  {url}")
    print(f"  program:  {team.get('name')} (@{team.get('handle')})")
    print(f"  state:    {report.get('substate')}")
    print(f"  severity: {rating}" + (f" (CVSS {score})" if score is not None else ""))
    print(f"  weakness: {weakness}")
    print(f"  reporter: {report.get('reporter', {}).get('username')}")
    print(f"  bounty:   {total_bounty(report)}")
    print(f"  filed:    {(report.get('created_at') or '?')[:10]}")
    print(f"  public:   {(report.get('disclosed_at') or '?')[:10]}")
    print()
    print("  note: the full write-up is not exposed via the API — read it at the URL above.")
    print()

    nodes = (report.get("activities") or {}).get("nodes") or []
    events = [(n.get("created_at"), n["__typename"]) for n in nodes if n.get("created_at")]
    events.sort(key=lambda e: e[0] or "")
    print(f"== timeline — {len(events)} dated events ==")
    for when, typename in events:
        label = EVENT_LABELS.get(typename, typename)
        if typename == "ActivitiesComment" and not show_comments:
            continue
        print(f"  {when[:10]}  {label}")
    if not show_comments:
        n_comments = sum(1 for _, t in events if t == "ActivitiesComment")
        if n_comments:
            print(f"  ({n_comments} comments hidden — pass --comments to show)")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Show detail of a disclosed HackerOne report.")
    ap.add_argument("report", help="report id or URL, e.g. 2289836")
    ap.add_argument("--comments", action="store_true", help="include comment events in the timeline")
    ap.add_argument("--json", action="store_true", help="emit raw JSON instead of a summary")
    ap.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT,
                    help=f"request timeout in seconds (default {DEFAULT_TIMEOUT:g})")
    args = ap.parse_args(argv)

    def run() -> None:
        report_id = parse_id(args.report)
        report = fetch_report(report_id, args.timeout)
        if args.json:
            print(json.dumps(report, indent=2))
        else:
            print_report(report, report_id, show_comments=args.comments)

    return run_cli(run)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
