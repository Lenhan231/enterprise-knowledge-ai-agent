#!/usr/bin/env bash
# One-time ref migration between the archived and squashed histories.
set -euo pipefail
cd "${DEPLOY_DIR:?set DEPLOY_DIR to the server checkout}"
archive=5fc49bfb2b1b82d050202b8922fa91555edf9037
squashed=d6dda7aab2e828e952846d0a241bc2b03ade14e0

git fetch --quiet origin refs/heads/codex/main-history-cutover
target=$(git rev-parse FETCH_HEAD)
if [ "$target" != "$archive" ] && [ "$target" != "$squashed" ]; then
  echo "Unexpected cutover target" >&2
  exit 2
fi
if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "Refusing to move a checkout with tracked edits" >&2
  exit 2
fi

before=$(git rev-parse HEAD)
if ! git merge-base --is-ancestor "$before" "$archive" && ! git merge-base --is-ancestor "$before" "$squashed"; then
  echo "Checkout is outside the two approved histories" >&2
  exit 3
fi
tree=$(git rev-parse "$before^{tree}")
match=$(git log --first-parent --format='%H %T' "$target" |
  awk -v tree="$tree" '$2 == tree && !found {print $1; found = 1}')
if [ -z "$match" ]; then
  echo "No identical snapshot found in the target history" >&2
  exit 3
fi
health_url=${HEALTH_URL:-http://127.0.0.1:8000/health}
curl -fsS --max-time 10 -o /dev/null "$health_url"
if [ "$before" != "$match" ]; then
  git update-ref -m 'Main history cutover' HEAD "$match" "$before"
fi
git diff --quiet HEAD --
printf 'Main history synced %s -> %s without restarting services\n' "$before" "$match"
