#!/usr/bin/env bash
# Refreshes data/contributions.json and data/repos.jsonl. Needs the gh CLI (GH_TOKEN in Actions).
# The repos listed here are the ones that get a card, in this order.
set -euo pipefail
cd "$(dirname "$0")"
LOGIN="${LOGIN:-ThatPandaBean}"
REPOS="concord workout"

gh api graphql -F login="$LOGIN" -f query='
query($login: String!) { user(login: $login) { contributionsCollection { contributionCalendar {
  totalContributions weeks { contributionDays { date contributionCount } } } } } }' \
  --jq '{total: .data.user.contributionsCollection.contributionCalendar.totalContributions,
         days: [.data.user.contributionsCollection.contributionCalendar.weeks[].contributionDays[]
                | {date, count: .contributionCount}]}' > data/contributions.json

{
  gh api "users/$LOGIN" --jq '{public_repos}'
  for r in $REPOS; do
    gh api "repos/$LOGIN/$r" --jq '{name, description, stars: .stargazers_count, language, pushed: .pushed_at, homepage, url: .html_url}'
  done
} > data/repos.jsonl
