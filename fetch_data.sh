#!/usr/bin/env bash
# Refreshes data/contributions.json and data/repos.jsonl. Needs the gh CLI (GH_TOKEN in Actions).
# Featured repos are picked automatically: the 3 most recently pushed public repos that have a
# description, skipping forks, archived repos and the profile repo itself. Change FEATURED to show more.
set -euo pipefail
cd "$(dirname "$0")"
LOGIN="${LOGIN:-ThatPandaBean}"
FEATURED=3

gh api graphql -F login="$LOGIN" -f query='
query($login: String!) { user(login: $login) { contributionsCollection { contributionCalendar {
  totalContributions weeks { contributionDays { date contributionCount } } } } } }' \
  --jq '{total: .data.user.contributionsCollection.contributionCalendar.totalContributions,
         days: [.data.user.contributionsCollection.contributionCalendar.weeks[].contributionDays[]
                | {date, count: .contributionCount}]}' > data/contributions.json

REPOS=$(gh repo list "$LOGIN" --visibility public --source --no-archived --limit 100 \
  --json name,description,pushedAt \
  --jq "[.[] | select(.description != \"\" and .name != \"$LOGIN\")] | sort_by(.pushedAt) | reverse | .[:$FEATURED][].name")

{
  gh api "users/$LOGIN" --jq '{public_repos}'
  for r in $REPOS; do
    gh api "repos/$LOGIN/$r" --jq '{name, description, stars: .stargazers_count, language, pushed: .pushed_at, homepage, url: .html_url}'
  done
} > data/repos.jsonl
