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
    backup_directory="${XDG_STATE_HOME:-$HOME/.local/state}/enterprise-knowledge-ai-agent/dashboard-backups"
    if [ -d "$backup_directory" ]; then
      legacy_backup=$(find "$backup_directory" -maxdepth 1 -type f -name '*.sqlite3' -size +0c -printf '%T@ %p\n' | sort -nr | sed -n '1{s/^[^ ]* //;p;}')
    fi
    if [ -z "$legacy_backup" ]; then
      echo "Backend is stopped and no retained dashboard snapshot is available; refusing to discard its writable layer." >&2
      exit 6
    fi
    say "Reusing retained dashboard snapshot from the previous deployment attempt"
  else
    umask 077
    backup_directory="${XDG_STATE_HOME:-$HOME/.local/state}/enterprise-knowledge-ai-agent/dashboard-backups"
    mkdir -p "$backup_directory"
    chmod 700 "$backup_directory"
    legacy_backup=$(mktemp "$backup_directory/XXXXXXXX.sqlite3")
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
' < /dev/null > "$legacy_backup"
  fi
fi

say "Building and restarting changed services"

all_services=(backend-api document-processing retrieval-api chunking embeddings reranker)
build_services=()
deploy_services=()
add_service() {
  local target=$1 service
  for service in "${deploy_services[@]}"; do [ "$service" = "$target" ] && return; done
  deploy_services+=("$target")
}
add_build_service() {
  local target=$1 service
  add_service "$target"
  for service in "${build_services[@]}"; do [ "$service" = "$target" ] && return; done
  build_services+=("$target")
}

if [ "$before" != "$target" ]; then
  while IFS= read -r path; do
    case "$path" in
      docker/Dockerfile.backend-api) add_build_service backend-api ;;
      docker/Dockerfile.document-processing) add_build_service document-processing ;;
      docker/Dockerfile.retrieval) add_build_service retrieval-api ;;
      docker/Dockerfile.chunking) add_build_service chunking ;;
      docker/Dockerfile.embeddings) add_build_service embeddings ;;
      docker/Dockerfile.reranker) add_build_service reranker ;;
      .dockerignore)
        # The semantic-data allowlist in this file is consumed by the backend image.
        add_build_service backend-api
        ;;
      docker-compose.yml|pyproject.toml|uv.lock)
        for service in "${all_services[@]}"; do add_build_service "$service"; done
        ;;
      src/core/services/runtime.py)
        # This runtime is copied into every API image.
        for service in backend-api document-processing retrieval-api embeddings reranker; do add_build_service "$service"; done
        ;;
      src/document_processing/diagnostics.py)
        add_build_service document-processing
        add_build_service backend-api
        ;;
      src/document_processing/*) add_build_service document-processing ;;
      src/app/*|data/semantic/*|src/core/agents/*|src/core/agents/dashboard/*|src/core/auth/*)
        add_build_service backend-api
        ;;
      src/core/embeddings/*) add_build_service embeddings ;;
      src/core/retrieval/reranker.py) add_build_service reranker ;;
      src/core/retrieval/*) add_build_service retrieval-api ;;
      src/core/chunking/*) add_build_service chunking ;;
      src/core/*|src/*) add_build_service backend-api ;;
    esac
  done < <(git diff --name-only "$before" "$target")
fi

# Recover stopped or unhealthy services with their existing image even when their source did not change.
for service in "${all_services[@]}"; do
  container_id=$(docker compose ps -q "$service")
  if [ -z "$container_id" ]; then
    add_build_service "$service"
    continue
  fi
  container_status=$(docker inspect --format '{{.State.Status}}' "$container_id")
  health_status=$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$container_id")
  if [ "$container_status" != running ] || { [ "$health_status" != healthy ] && [ "$health_status" != none ]; }; then
    add_service "$service"
  fi
done

if [ "${#build_services[@]}" -gt 0 ]; then
  say "Building: ${build_services[*]}"
  docker compose build "${build_services[@]}"
fi
if [ "${#deploy_services[@]}" -gt 0 ]; then
  say "Starting: ${deploy_services[*]}"
  docker compose up -d --no-deps "${deploy_services[@]}"
else
  say "No service changes or unhealthy containers; checking the current stack"
fi

if [ -n "$legacy_backup" ] && [ -s "$legacy_backup" ]; then
  say "Copying legacy dashboards to shared storage (local backup retained)"
  docker cp "$legacy_backup" "$(docker compose ps -q backend-api):/tmp/dashboard-migration.sqlite3"
  docker compose exec -T backend-api python -c '
import json, sys
from core.agents.dashboard.postgres_store import PostgresDashboardStore
print(json.dumps(PostgresDashboardStore().import_sqlite(sys.argv[1])))
' /tmp/dashboard-migration.sqlite3 < /dev/null
fi

docker compose exec -T backend-api python -c '
from uuid import uuid4
from core.agents.dashboard.store import create_dashboard_store
from core.agents.dashboard.postgres_store import PostgresDashboardStore
store = create_dashboard_store()
assert isinstance(store, PostgresDashboardStore), "Production dashboards require shared PostgreSQL storage"
store.list("deployment-check-" + uuid4().hex)
print("Shared dashboard storage is ready")
' < /dev/null

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
