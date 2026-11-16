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

# Docker Desktop on WSL keeps registry credentials through a Windows helper (credsStore "desktop.exe"), but SSH
# sessions (manual or the GitHub job over Tailscale SSH) get no Windows PATH, so builds fail to find it.
DOCKER_DESKTOP_BIN=${DOCKER_DESKTOP_BIN:-"/mnt/c/Program Files/Docker/Docker/resources/bin"}
if [ -x "$DOCKER_DESKTOP_BIN/docker-credential-desktop.exe" ] && ! command -v docker-credential-desktop.exe >/dev/null; then
  PATH="$PATH:$DOCKER_DESKTOP_BIN"
fi

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

# Snapshot SQLite while the old container is still running; its writable layer will be replaced.
legacy_backup=
legacy_container=$(docker compose ps -aq backend-api)
if [ -n "$legacy_container" ]; then
  if [ "$(docker inspect --format '{{.State.Running}}' "$legacy_container")" != true ]; then
    echo "Start the existing backend before deploying so its saved dashboards can be backed up." >&2
    exit 6
  fi
  umask 077
  mkdir -p artifacts/local/dashboard-backups
  legacy_backup="artifacts/local/dashboard-backups/$(date -u +%Y%m%dT%H%M%SZ).sqlite3"
  docker compose exec -T backend-api python -c '
import os, pathlib, sqlite3, sys, tempfile
from contextlib import closing
source = pathlib.Path(os.getenv("DASHBOARD_STORAGE_DIR", "artifacts/local/dashboards")) / "dashboards.sqlite3"
if source.is_file():
    with tempfile.TemporaryDirectory() as directory:
        target = pathlib.Path(directory) / "dashboards.sqlite3"
        with closing(sqlite3.connect("file:" + str(source) + "?mode=ro", uri=True)) as reader, closing(sqlite3.connect(target)) as writer:
            reader.backup(writer)
        sys.stdout.buffer.write(target.read_bytes())
' > "$legacy_backup"
fi

say "Building and restarting changed services"
docker compose up -d --build

if [ -n "$legacy_backup" ] && [ -s "$legacy_backup" ]; then
  say "Copying legacy dashboards to shared storage (local backup retained)"
  docker cp "$legacy_backup" "$(docker compose ps -q backend-api):/tmp/dashboard-migration.sqlite3"
  docker compose exec -T backend-api python -c '
import json, sys
from core.dashboards.postgres_store import PostgresDashboardStore
print(json.dumps(PostgresDashboardStore().import_sqlite(sys.argv[1])))
' /tmp/dashboard-migration.sqlite3
fi

docker compose exec -T backend-api python -c '
from uuid import uuid4
from core.dashboards.store import create_dashboard_store
from core.dashboards.postgres_store import PostgresDashboardStore
store = create_dashboard_store()
assert isinstance(store, PostgresDashboardStore), "Production dashboards require shared PostgreSQL storage"
store.list("deployment-check-" + uuid4().hex)
print("Shared dashboard storage is ready")
'

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
