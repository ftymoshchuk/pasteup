#!/usr/bin/env bash
# Apply the branch protection sigrix-io uses on its public repositories, plus
# the security settings a public repository should have.
#
#   scripts/protect-repo.sh [owner/repo]      (default: ftymoshchuk/pasteup)
#
# Needs the GitHub CLI signed in as an admin of the repository (`gh auth
# status`). Safe to re-run: the ruleset is updated in place and every setting
# is idempotent. Run it again right after making the repository public, since
# some of these settings only exist for public repositories.
set -euo pipefail

repo="${1:-ftymoshchuk/pasteup}"
ruleset_name="default-branch"
ruleset_id_query=".[] | select(.name == \"$ruleset_name\" and .source_type == \"Repository\") | .id"

# sigrix-io/mullion's "default-branch" ruleset: the default branch cannot be
# deleted or force-pushed, changes land only through pull requests (no
# approval needed), and a pull request merges only when the `ci-passed` check
# is green and the branch is up to date with main. 15368 is the GitHub Actions
# app, so nothing else can report that check.
#
# Two differences from the sigrix original:
# - Its bypass actor is a sigrix team, and a personal repository has no teams.
#   Repository admins (built-in role 5) take its place, with the same limit:
#   they can bypass only through a pull request, never by pushing directly.
# - Review parameters it leaves at their defaults (required reviewers,
#   dismissal restrictions) are left out rather than repeated.
ruleset=$(cat <<'JSON'
{
  "name": "default-branch",
  "target": "branch",
  "enforcement": "active",
  "conditions": {
    "ref_name": { "include": ["~DEFAULT_BRANCH"], "exclude": [] }
  },
  "rules": [
    { "type": "deletion" },
    { "type": "non_fast_forward" },
    {
      "type": "pull_request",
      "parameters": {
        "required_approving_review_count": 0,
        "dismiss_stale_reviews_on_push": false,
        "require_code_owner_review": false,
        "require_last_push_approval": false,
        "required_review_thread_resolution": false,
        "allowed_merge_methods": ["merge", "squash", "rebase"]
      }
    },
    {
      "type": "required_status_checks",
      "parameters": {
        "strict_required_status_checks_policy": true,
        "do_not_enforce_on_create": false,
        "required_status_checks": [{ "context": "ci-passed", "integration_id": 15368 }]
      }
    }
  ],
  "bypass_actors": [
    { "actor_id": 5, "actor_type": "RepositoryRole", "bypass_mode": "pull_request" }
  ]
}
JSON
)

die() {
  echo "error: $*" >&2
  exit 1
}

explain_ruleset_failure() {
  echo "Ruleset not applied: $1" >&2
  if [ "$visibility" = private ] && grep -q "HTTP 403" <<<"$1"; then
    echo "On GitHub Free, rulesets work only on public repositories. Make $repo public, then" >&2
    echo "run this script again straight away. Going public gives nobody push access, so" >&2
    echo "the minute in between exposes nothing." >&2
  fi
}

apply_ruleset() {
  local existing_id output
  if ! existing_id=$(gh api "repos/$repo/rulesets" --jq "$ruleset_id_query" 2>&1); then
    explain_ruleset_failure "$existing_id"
    return 1
  fi

  if [ -n "$existing_id" ]; then
    output=$(gh api --method PUT "repos/$repo/rulesets/$existing_id" --input - <<<"$ruleset" 2>&1) || {
      explain_ruleset_failure "$output"
      return 1
    }
    echo "Updated the '$ruleset_name' ruleset"
  else
    output=$(gh api --method POST "repos/$repo/rulesets" --input - <<<"$ruleset" 2>&1) || {
      explain_ruleset_failure "$output"
      return 1
    }
    echo "Created the '$ruleset_name' ruleset"
  fi
}

command -v gh >/dev/null || die "the GitHub CLI (gh) is not installed"
visibility=$(gh api "repos/$repo" --jq .visibility) || die "cannot read $repo; check the name and \`gh auth status\`"
echo "$repo is $visibility"

ruleset_applied=true
apply_ruleset || ruleset_applied=false

# The same merge settings as sigrix: all three merge methods, no auto-merge,
# and branches deleted once their pull request merges.
gh api --method PATCH "repos/$repo" \
  -F allow_merge_commit=true -F allow_squash_merge=true -F allow_rebase_merge=true \
  -F allow_auto_merge=false -F delete_branch_on_merge=true >/dev/null
echo "Merge settings: merge, squash and rebase allowed; merged branches are deleted"

gh api --method PUT "repos/$repo/vulnerability-alerts" >/dev/null
echo "Dependabot alerts enabled"

if [ "$visibility" = public ]; then
  # SECURITY.md tells reporters to use this.
  gh api --method PUT "repos/$repo/private-vulnerability-reporting" >/dev/null
  echo "Private vulnerability reporting enabled"

  gh api --method PATCH "repos/$repo" --input - >/dev/null <<'JSON'
{
  "security_and_analysis": {
    "secret_scanning": { "status": "enabled" },
    "secret_scanning_push_protection": { "status": "enabled" }
  }
}
JSON
  echo "Secret scanning and push protection enabled"
else
  echo "Still private: run this again after making it public, to enable private vulnerability"
  echo "reporting, secret scanning and push protection, which exist only for public repositories."
fi

if [ "$ruleset_applied" = true ]; then
  ruleset_id=$(gh api "repos/$repo/rulesets" --jq "$ruleset_id_query")
  gh api "repos/$repo/rulesets/$ruleset_id" --jq \
    '"In force: \(.name) (\(.enforcement)), rules: \([.rules[].type] | join(", "))"'
else
  exit 2
fi
