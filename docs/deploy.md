# Continuous deployment

Every push to `main` deploys both backends automatically (`.github/workflows/deploy.yml`).

```
push to main ──▶ GitHub Actions "Deploy"
                   ├─ job 1  VPS (fallback)   joins the tailnet as tag:ci, ssh to the VPS's tailnet address with a key restricted to the deploy script
                   │          └─ scripts/deploy/deploy.sh  → git fast-forward → docker compose up -d --build → /health 200, /api/auth/me 401
                   ├─ job 2  Laptop home-pc (main)    only if job 1 succeeded; joins the tailnet as tag:ci, Tailscale SSH
                   │          └─ same script
                   └─ job 3  Desktop (2nd fallback)   after job 2 whatever its result; allowed to fail (often switched off)
                              └─ same script
Vercel deploys the web page from main on its own; /api goes to the laptop (NGROK_URL), /api-fallback to the VPS
(FALLBACK_URL), /api-fallback-2 to the desktop (FALLBACK_2_URL, Tailscale Funnel). The page uses the fastest healthy one
and moves a request that cannot reach its backend to the next one.
```

- **One backend is always up.** The jobs run one after the other, never in parallel, and the PC is only touched after the VPS is healthy again. `concurrency` stops two deploys overlapping.
- **Nothing from a pull request runs on the servers.** Jobs run on GitHub's machines and only on pushes to `main` (or a manual run); fork PRs get no secrets.
- **Safe on the servers.** The script only fast-forwards, refuses to run if tracked files were edited by hand, and fails the job unless the backend is healthy afterwards. Supabase migrations are still applied by hand (both backends share one database).
- **The VPS's public SSH port stays closed to GitHub.** The provider firewall admits only the team's IPs on port 22; the job reaches the VPS over Tailscale instead (ACL: `tag:ci` may reach only port 22 of `tag:vps` and `tag:home-pc`).
- **Evidence.** Each run in the repository's Actions tab shows which commit was deployed to which server, the build and health-check log, and a pass/fail status.

## Secrets (repository → Settings → Secrets and variables → Actions)

| Secret | Value |
|---|---|
| `VPS_KNOWN_HOSTS` | output of `ssh-keyscan -t ed25519,rsa,ecdsa <VPS IP>` |
| `VPS_DEPLOY_SSH_KEY` | private key `/root/.ssh/github_deploy` on the VPS (`cat` it there; it never leaves the VPS otherwise) |
| `TS_OAUTH_CLIENT_ID`, `TS_OAUTH_SECRET` | Tailscale OAuth client with the Auth Keys write scope, limited to `tag:ci` |

On the VPS the deploy key's `authorized_keys` line forces the command
`cd /opt/enterprise-knowledge-ai-agent && git fetch -q origin main && git show origin/main:scripts/deploy/deploy.sh | DEPLOY_DIR=… bash`
with port, agent and X11 forwarding and the terminal disabled, so the key can only deploy `main`.

## Manual deploy or check

```bash
DEPLOY_DIR=/opt/enterprise-knowledge-ai-agent bash scripts/deploy/deploy.sh   # VPS
DEPLOY_DIR=~/projects/ekai-prod bash scripts/deploy/deploy.sh                 # home PC
```
Or Actions → Deploy → Run workflow. Do not deploy by hand while a workflow run is in progress.
