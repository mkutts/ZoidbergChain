# Live Domain Deployment Runbook

This runbook guides the manual server-side deployment of the controlled public demo for `zoidbergcoin.com` and `www.zoidbergcoin.com` as of Saturday, August 1, 2026.

It does not perform the live deployment by itself. DNS, server access, Certbot, and final smoke checks remain operator-driven steps.

## Local Preflight Before Push

Run locally before touching the server:

```bash
git diff --stat
python -m pytest
cd zoidbergcoin-ui
npm test
npm run build
```

Confirm:

- there are no accidental secret changes in the diff
- backend tests pass
- frontend tests pass
- frontend production build passes
- GitHub Actions for `main` are green before the live update continues

## Preflight Questions

Fill these values in before running commands:

- `SERVER_IP=<SERVER_IP>`
- `SERVER_OS=<SERVER_OS>`
- `REPO_URL=<REPO_URL>`
- `DEPLOY_USER=<DEPLOY_USER>`
- `PYTHON_VERSION=<PYTHON_VERSION>`
- `NODE_VERSION=<NODE_VERSION>`
- `PROJECT_ROOT=/srv/zoidbergchain/current`
- `VENV_ROOT=/srv/zoidbergchain/venv`
- `WEB_ROOT=/var/www/zoidbergchain`
- `DATA_DIR=/var/lib/zoidbergchain`
- `CONTENT_STORAGE_DIR=/var/lib/zoidbergchain/content`
- `ENV_PATH=/etc/zoidbergchain/zoidbergchain.env`
- `BACKEND_ENTRYPOINT=api:app`

If any value is unknown, keep the placeholder and resolve it before rollout.

## What Already Passed Locally

Before this runbook was prepared, the project passed:

- backend tests
- two-node native transfer regression
- frontend tests
- frontend production build

That means the remaining work is deployment execution, not new app feature work.

## DNS Setup

Required records:

- `A` record: `zoidbergcoin.com -> SERVER_IP`
- `A` or `CNAME` record: `www.zoidbergcoin.com -> SERVER_IP` or `zoidbergcoin.com`

Verification:

```bash
dig zoidbergcoin.com
dig www.zoidbergcoin.com
```

Wait for propagation before certificate issuance.

## Server Setup Commands

Ubuntu/Debian-oriented example commands:

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y git python3 python3-venv python3-pip nginx certbot python3-certbot-nginx curl openssl rsync
node --version || true
npm --version || true
```

If Node.js or npm are missing, install them according to the chosen server policy.

Create directories and permissions:

```bash
sudo mkdir -p /srv/zoidbergchain
sudo mkdir -p /var/lib/zoidbergchain/content
sudo mkdir -p /var/www/zoidbergchain
sudo mkdir -p /var/log/zoidbergchain
sudo mkdir -p /etc/zoidbergchain
sudo chown -R <DEPLOY_USER>:www-data /srv/zoidbergchain /var/lib/zoidbergchain /var/www/zoidbergchain /var/log/zoidbergchain
sudo chmod 750 /etc/zoidbergchain
```

## Repo Deployment Commands

Clone:

```bash
sudo -u <DEPLOY_USER> git clone <REPO_URL> /srv/zoidbergchain/current
```

Or update:

```bash
cd /srv/zoidbergchain/current
sudo -u <DEPLOY_USER> git fetch origin
sudo -u <DEPLOY_USER> git checkout main
sudo -u <DEPLOY_USER> git reset --hard origin/main
```

Python virtual environment:

```bash
cd /srv/zoidbergchain/current
sudo -u <DEPLOY_USER> python3 -m venv /srv/zoidbergchain/venv
sudo -u <DEPLOY_USER> /srv/zoidbergchain/venv/bin/python -m pip install --upgrade pip
sudo -u <DEPLOY_USER> /srv/zoidbergchain/venv/bin/python -m pip install -r requirements.txt
```

`requirements.txt` is the complete node installation and includes the core and originality/OCR groups. Install the system Tesseract OCR executable separately before starting a node that processes image originality submissions.

Frontend dependencies and build:

```bash
cd /srv/zoidbergchain/current/zoidbergcoin-ui
sudo -u <DEPLOY_USER> npm install
sudo -u <DEPLOY_USER> env \
  VITE_API_BASE_URL=/api \
  VITE_ENVIRONMENT=testnet \
  VITE_PUBLIC_DEMO_MODE=true \
  VITE_ENABLE_DEV_TOOLS=false \
  npm run build
sudo rsync -av --delete /srv/zoidbergchain/current/zoidbergcoin-ui/dist/ /var/www/zoidbergchain/
```

Notes:

- `zoidbergcoin-ui/dist/` is the canonical deployable frontend artifact.
- `zoidbergcoin-ui/zoidbergchain-dist.zip` is obsolete and should not be used as a deployment source.
- backend `GET /` serves only a minimal backend info page; the public app root should come from the deployed `dist/` files.

## Server Environment File

Create:

- `/etc/zoidbergchain/zoidbergchain.env`

Generate the peer secret:

```bash
openssl rand -hex 32
```

Example contents:

```env
ENVIRONMENT=testnet
PUBLIC_DEMO_MODE=true
PUBLIC_API_MODE=true
NETWORK_NAME=zoidberg-testnet
NODE_ID=zoidberg-public-demo-node-1
NODE_HOST=127.0.0.1
NODE_PORT=8000
PUBLIC_NODE_URL=https://zoidbergcoin.com
API_BASE_URL=https://zoidbergcoin.com/api
FRONTEND_ORIGIN=https://zoidbergcoin.com
CORS_ALLOWED_ORIGINS=https://zoidbergcoin.com,https://www.zoidbergcoin.com
STORAGE_BACKEND=sqlite
DATA_DIR=/var/lib/zoidbergchain
SQLITE_DB_PATH=/var/lib/zoidbergchain/zoidbergchain.sqlite3
CONTENT_STORAGE_DIR=/var/lib/zoidbergchain/content
PEER_SHARED_SECRET=<generate-real-secret>
REQUIRE_PEER_AUTH=true
ENABLE_SIGNED_PEER_MESSAGES=true
RATE_LIMITING_ENABLED=true
MAX_CONTENT_FILE_SIZE_BYTES=5242880
MAX_TEXT_CONTENT_BYTES=100000
LOG_LEVEL=INFO
ADMIN_UI_ENABLED=true
ADMIN_AUTH_ENABLED=true
ADMIN_SESSION_TTL_SECONDS=3600
ADMIN_PASSWORD_HASH=pbkdf2_sha256$...
# Optional only for early testing. Prefer ADMIN_PASSWORD_HASH.
# ADMIN_BOOTSTRAP_TOKEN=<strong-random-secret>
```

Generate the admin password hash before editing the live env file:

```bash
cd /srv/zoidbergchain/current
/srv/zoidbergchain/venv/bin/python -m scripts.access_admin generate-admin-password-hash
```

Apply secure file permissions:

```bash
sudo cp /srv/zoidbergchain/current/deploy/examples/zoidbergchain.server.env.example /etc/zoidbergchain/zoidbergchain.env
sudo chmod 640 /etc/zoidbergchain/zoidbergchain.env
sudo chown root:<DEPLOY_USER> /etc/zoidbergchain/zoidbergchain.env
```

Do not commit the live file and do not print the real secret into documentation.

## systemd Service

File:

- `/etc/systemd/system/zoidbergchain-backend.service`

Install and start:

```bash
sudo cp /srv/zoidbergchain/current/deploy/systemd/zoidbergchain-backend.service /etc/systemd/system/zoidbergchain-backend.service
sudo systemctl daemon-reload
sudo systemctl enable zoidbergchain-backend
sudo systemctl start zoidbergchain-backend
sudo systemctl status zoidbergchain-backend
```

Service expectations:

- backend binds only to `127.0.0.1:8000`
- environment is loaded from `/etc/zoidbergchain/zoidbergchain.env`
- restart on failure is enabled
- backend is not exposed directly to the internet

## Nginx Config

File:

- `/etc/nginx/sites-available/zoidbergcoin.com`

Install and enable:

```bash
sudo cp /srv/zoidbergchain/current/deploy/nginx/zoidbergcoin.com.conf /etc/nginx/sites-available/zoidbergcoin.com
sudo ln -s /etc/nginx/sites-available/zoidbergcoin.com /etc/nginx/sites-enabled/zoidbergcoin.com
sudo nginx -t
sudo systemctl reload nginx
```

Nginx behavior:

- serves frontend static assets
- proxies `/api/` to `127.0.0.1:8000`
- uses `server_name zoidbergcoin.com www.zoidbergcoin.com`
- applies `client_max_body_size 5M`
- supports history fallback with `try_files`

## HTTP Verification Before HTTPS

Run:

```bash
curl -I http://zoidbergcoin.com
curl http://zoidbergcoin.com/api/health
curl http://zoidbergcoin.com/api/node-info
curl http://zoidbergcoin.com/api/chain/summary
```

If `/api/health` fails, inspect whether `proxy_pass` is stripping `/api/` correctly. The current Nginx config is intended to map:

- public `/api/health` -> backend `/health`

## HTTPS / Certbot

Run:

```bash
sudo certbot --nginx -d zoidbergcoin.com -d www.zoidbergcoin.com
sudo certbot renew --dry-run
curl -I https://zoidbergcoin.com
curl https://zoidbergcoin.com/api/health
```

After issuance:

- confirm HTTP redirects to HTTPS
- confirm both hostnames are covered

## Post-Deploy Smoke Checks

Verify:

- homepage loads
- public demo/testnet banner is visible
- `/admin` loads
- admin login succeeds with the configured server-side credential
- pending access requests list only after admin login
- one-time invite codes are shown only immediately after approval or direct invite creation
- wallet connect is visible
- dev tools are hidden
- `/api/health` works
- `/api/status` works
- `/api/ops/status` works
- `/api/node-info` works
- `/api/chain/summary` works
- `/api/access/status` still reports `invite_only`
- `/api/admin/session` does not authenticate a public visitor
- explorer loads
- no private keys in public responses
- no session tokens in public responses
- no peer secrets in public responses
- upload limits work
- CORS works from `https://zoidbergcoin.com`
- backend logs do not show obvious errors

## Functional Smoke Test

Try:

1. connect MetaMask
2. verify wallet
3. submit signed content
4. vote if enough test wallets are available
5. mint certified meme block if practical
6. verify reward balance
7. create native ZOID transfer
8. admit to mempool
9. mint meme block including transfer
10. verify settlement
11. verify explorer shows transaction and block

If multi-wallet voting is not practical on the public server yet, mark it incomplete and keep the deployment labeled controlled testnet.

## Backup After Successful Deployment

Back up:

- SQLite database
- content storage directory
- deployed frontend build
- environment file path reference, not the secret contents
- Nginx config
- systemd service file

Example commands:

```bash
sudo cp /var/lib/zoidbergchain/zoidbergchain.sqlite3 /var/lib/zoidbergchain/zoidbergchain.sqlite3.post-deploy.bak
sudo tar -czf /var/lib/zoidbergchain/content.post-deploy.tgz /var/lib/zoidbergchain/content
sudo tar -czf /var/www/zoidbergchain.post-deploy.tgz /var/www/zoidbergchain
sudo cp /etc/nginx/sites-available/zoidbergcoin.com /var/lib/zoidbergchain/zoidbergcoin.com.nginx.bak
sudo cp /etc/systemd/system/zoidbergchain-backend.service /var/lib/zoidbergchain/zoidbergchain-backend.service.bak
```

Record:

- `/etc/zoidbergchain/zoidbergchain.env`

Do not archive the live secret contents into the repository.

## Rollback

1. stop backend service
2. restore previous frontend build
3. restore previous backend code release
4. restore previous `.env`
5. restore latest state backup if needed
6. restart service
7. verify `/api/health`, `/api/status`, `/api/access/status`, and explorer

## Report Template

Record the final operator outcome for:

- DNS status
- server setup status
- backend service status
- frontend build/deploy status
- Nginx status
- HTTPS status
- health check result
- smoke check result
- functional test result
- backup status
- remaining launch blockers
