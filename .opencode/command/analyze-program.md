---
description: Summarize a HackerOne program's scope, policy, and disclosed reports
agent: build
---
You are helping with authorized, read-only bug-bounty recon. Do not propose
scanning or attacks on target assets.

Program scope and policy:

!`python3 h1scope.py $ARGUMENTS --policy`

Publicly disclosed reports:

!`python3 h1reports.py $ARGUMENTS --limit 50`

Using only the data above, give me:
1. The highest-value in-scope, bounty-eligible assets and their tiers.
2. The key testing restrictions a researcher must respect for this program.
3. The recurring vulnerability classes in the disclosed reports, and what to
   study before testing. Do not invent details beyond what is shown.
