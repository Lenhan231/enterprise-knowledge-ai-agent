# Handoff: 13 Nov 2026 evening (laptop → home PC)

Goal of the next session: run the backend on the home PC (i5-12400F, 32 GB, RTX 2060 not needed) instead of the Contabo VPS, and point the live site at it.

## 1. State when this note was written

- **main** has the new UI live (PR #49 and #50, both merged). Frontend only; no backend change went to main.
- **Huy** = main's UI plus Huy's unreviewed backend work (auto planner pass-through, accent-restored dense search, strict citation option, eval scripts; about 98 files). Not on main on purpose.
- **Live path today:** Vercel → `NGROK_URL` (Vercel env) → `https://ai4enterprise.duckdns.org` → Caddy on the VPS → `127.0.0.1:8000` (Docker Compose).
- Report is still frozen as of 12 Nov; nothing here was evaluated.

## 2. Why answers time out (measured 13 Nov, about 22:30 ICT)

| Measurement | VPS (India, Contabo) | Home laptop (VN) |
|---|---|---|
| TCP connect to Supabase pooler, Sydney (`aws-1-ap-southeast-2`) | 612–2951 ms | 231–339 ms |
| TCP connect to Supabase Mumbai endpoint | 3–964 ms (jitter) | — |
| TCP connect to www.google.com | 221–752 ms | — |
| TCP connect to api.groq.com | 4–507 ms | 33–55 ms |
| First hop (Contabo gateway) | 84 ms | — |
| DB connect / `select 1` from the backend container | 1.6–2.6 s / 0.5–0.8 s | — |

- The agent run limit is 60 s (`run_sync` in `src/core/agents/runtime.py`). Knowledge runs spend 3–23 s in embedding and 10–22 s in database search, then never reach reranking or answer writing, and fail at about 63 s.
- 24 h telemetry (`agent_run_events`): Knowledge 9 completed, 23 failed (avg 66 s). Failures started around 10:00 ICT and every run since 18:00 failed.
- 20 of the "failed" runs are `AgentClarificationRequired`: the SQL agent asking for a clearer question. That is working as designed but the monitoring page counts it as failure. Excluding them, the real success rate is about 22 / 58.
- Two causes: (1) the VPS network is unstable right now (Contabo side; ticket below); (2) the backend opens a **new database connection per request**, and the database is about 245 ms away even on a good day, so every answer pays several slow connects.
- VPS timezone is `Europe/Berlin`; that is only the clock setting. The server is in India.

## 3. Move the backend to the home PC

Do not copy secrets into chat or the repo. Copy the VPS `.env` privately (USB or `scp` straight to the PC).

1. Install Docker Desktop (WSL 2 backend) and Git. Give Docker at least 12 GB RAM and 6 CPUs.
2. `git clone https://github.com/Lenhan231/enterprise-knowledge-ai-agent.git && cd enterprise-knowledge-ai-agent && git switch main`
   Use **main** (the reviewed backend). Huy's backend changes stay on Huy until reviewed.
3. Copy `.env` from the VPS: `scp root@147.93.171.214:/root/<repo path>/.env .env` (find the path with `ssh root@147.93.171.214 "docker inspect a761cc275440 --format '{{ index .Config.Labels \"com.docker.compose.project.working_dir\" }}'"`).
   Then in `.env` on the PC: `RERANKER_THREADS=4`. Keep `AUTH_COOKIE_SECURE=true` (the site is HTTPS through the tunnel). Check `TRUSTED_FRONTEND_ORIGINS` still lists the Vercel domain.
4. `docker compose up -d --build`, then `curl http://127.0.0.1:8000/health` and `curl http://127.0.0.1:8000/api/auth/me` (expect 401).
5. Public HTTPS for the PC (home internet is usually behind CGNAT, so use a tunnel, not port forwarding):
   - **ngrok:** claim the free static domain in the ngrok dashboard, then `ngrok http --url=<your-static-domain> 8000`. Run it as a service so it survives reboots.
   - or **Cloudflare Tunnel** (`cloudflared tunnel --url http://127.0.0.1:8000` for a quick test; a named tunnel for a fixed address).
6. Vercel → Project → Settings → Environment Variables → set `NGROK_URL` to the tunnel's `https://` origin → Redeploy (it is read at build time by `vercel.mjs`).
7. Test on the live site: sign in, ask a document question, open Monitoring. Expect Knowledge answers in about 10–20 s.
8. Keep the VPS running until the PC has been stable for a day; it is the fallback (switch `NGROK_URL` back to `https://ai4enterprise.duckdns.org`).

Windows notes: set the PC to never sleep while serving; let Docker start on login; the repo path must not be too long (`git config --global core.longpaths true`).

## 4. Open items

- **Connection pool** (biggest code fix, helps anywhere): `src/core/database/connection_limit.py` opens a fresh `psycopg.connect` per request. Use `psycopg_pool.ConnectionPool` (keep the 10-session cap for the Supabase session pooler). Backend change: PR for Nhân to review.
- **Monitoring:** count `AgentClarificationRequired` as "needs clarification", not failure (`monitoring_snapshot` in `src/core/database/agent_run_repository.py` and the summary strip).
- **Longer term:** a Supabase project in Mumbai (`ap-south-1`) would put the database about 5 ms from an India VPS. New project plus data move; not before Review 3 (2 Dec).
- **Contabo ticket** about the network instability: text is in the 13 Nov chat; send it with the measurements above.
- Invoice source route hit a database `statement timeout` once (`GET /api/invoices/<id>/source` 500). Likely the same slow network; recheck after the move.
- Docker on the VPS answers `docker ps` very slowly (health-check `runc exec` calls queue up). Containers still serve traffic.
- `/impeccable document` to refresh `.impeccable/design.json` from the updated DESIGN.md.
- Tell Nhân: General Chat is now the one chat (Route to), new answer layout, Reports tab.
- Slides: pick one deck (redesign vs laptop academic), then apply the mentor's rules (no text under 18 pt, at most 25 slides).

## 5. UI work in this session (all on main)

- General Chat answers in the Ledger style (serif text, jade stamp, citation marks that highlight the cited sentence, footnote sources), example questions on the empty chat.
- Tool pages share one frame; Invoice Review with a zoomable image viewer that opens fitted; Knowledge Management rows with status pills and plain names; Access Control as a real matrix; Monitoring figures in one strip with bars split completed vs failed.
- "Knowledge Q&A" renamed "Reports"; in-app confirmation dialog; resizable sidebar; jade dropdowns; new login layout and logo.
- Local demo: `PYTHONIOENCODING=utf-8 PYTHONUTF8=1 uv run --no-sync python scripts/ui-demo/demo_server.py src/app/static 8769` then `http://localhost:8769/?theme=light` (synthetic data, no keys).
