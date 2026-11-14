#!/usr/bin/env bash
# Deploy the latest origin/main on this server (run by the GitHub "Deploy" workflow over SSH, or by hand).
#   DEPLOY_DIR=/path/to/checkout bash scripts/deploy/deploy.sh
# Safe by design: only fast-forwards, stops if tracked files were edited by hand, and fails unless the
# backend answers /health afterwards. Shared Supabase migrations are still applied by hand.
set -euo pipefail

DEPLOY_DIR=${DEPLOY_DIR:?set DEPLOY_DIR to the server checkout}
HEALTH_URL=${HEALTH_URL:-http://127.0.0.1:8000/health}
HEALTH_WAIT_SECONDS=${HEALTH_WAIT_SECONDS:-600}
cd "$DEPLOY_DIR"

say() { printf '\n== %s\n' "$*"; }

say "Server $(hostname), checkout $DEPLOY_DIR"
before=$(git rev-parse HEAD)
git fetch --quiet origin main
target=$(git rev-parse origin/main)
echo "running: $(git log --oneline -1 "$before")"
echo "target:  $(git log --oneline -1 "$target")"

if ! git diff --quiet HEAD --; then
  echo "Refusing to deploy: tracked files were changed by hand on this server:" >&2
  git status --short --untracked-files=no >&2
  echo "Commit and push them (or restore them) first." >&2
  exit 2
fi
if ! git merge-base --is-ancestor "$before" "$target"; then
  echo "Refusing to deploy: this checkout has commits that are not on origin/main." >&2
  exit 3
fi

if [ "$before" = "$target" ]; then
  say "Already on the target commit; checking that the stack is up"
else
  say "Updating code"
  if git symbolic-ref -q HEAD >/dev/null; then git merge --ff-only --quiet "$target"; else git checkout --quiet --detach "$target"; fi
  git log --oneline "$before..$target" | head -30
fi

say "Building and restarting changed services"
docker compose up -d --build

say "Waiting for $HEALTH_URL (up to ${HEALTH_WAIT_SECONDS}s)"
deadline=$((SECONDS + HEALTH_WAIT_SECONDS))
until [ "$(curl -s -o /dev/null -w '%{http_code}' "$HEALTH_URL" || true)" = 200 ]; do
  if [ $SECONDS -ge $deadline ]; then
    echo "Backend did not become healthy in time." >&2
    docker compose ps >&2
    docker compose logs --tail 40 backend-api >&2 || true
    exit 4
  fi
  sleep 5
done
auth=$(curl -s -o /dev/null -w '%{http_code}' "${HEALTH_URL%/health}/api/auth/me" || true)
[ "$auth" = 401 ] || { echo "Expected 401 from /api/auth/me, got $auth" >&2; exit 5; }

say "Deployed $(git log --oneline -1)"
docker compose ps --format 'table {{.Service}}\t{{.State}}\t{{.Status}}'
