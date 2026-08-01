# Live Domain Deployment Checklist

Use this checklist to execute the first live controlled public-demo deployment for `zoidbergcoin.com`.

## Preflight Values

Fill these in before running commands:

- `SERVER_IP=<SERVER_IP>`
- `SERVER_OS=<SERVER_OS>`
- `DEPLOY_USER=<DEPLOY_USER>`
- `REPO_URL=<REPO_URL>`
- `PROJECT_ROOT=/srv/zoidbergchain/current`
- `VENV_ROOT=/srv/zoidbergchain/venv`
- `WEB_ROOT=/var/www/zoidbergchain`
- `DATA_DIR=/var/lib/zoidbergchain`
- `CONTENT_STORAGE_DIR=/var/lib/zoidbergchain/content`
- `ENV_PATH=/etc/zoidbergchain/zoidbergchain.env`
- `BACKEND_SERVICE=/etc/systemd/system/zoidbergchain-backend.service`
- `NGINX_SITE=/etc/nginx/sites-available/zoidbergcoin.com`
- `PYTHON_BIN=<PYTHON_BIN>`
- `NODE_BIN=<NODE_BIN>`
- `NPM_BIN=<NPM_BIN>`

If any value is still unknown, stop and resolve it before touching production DNS or certificates.

## DNS

- Create `A` record: `zoidbergcoin.com -> SERVER_IP`
- Create `A` or `CNAME` for `www.zoidbergcoin.com`
- Wait for propagation
- Verify:

```bash
dig zoidbergcoin.com
dig www.zoidbergcoin.com
```

## Server Packages

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y git python3 python3-venv python3-pip nginx certbot python3-certbot-nginx curl openssl
node --version || true
npm --version || true
```

If Node.js or npm are missing, install them using the server’s package source policy before building the frontend.

## Directories And Permissions

```bash
sudo mkdir -p /srv/zoidbergchain
sudo mkdir -p /var/lib/zoidbergchain/content
sudo mkdir -p /var/www/zoidbergchain
sudo mkdir -p /var/log/zoidbergchain
sudo mkdir -p /etc/zoidbergchain
sudo chown -R <DEPLOY_USER>:www-data /srv/zoidbergchain /var/www/zoidbergchain /var/log/zoidbergchain
sudo chown -R <DEPLOY_USER>:www-data /var/lib/zoidbergchain
sudo chmod 750 /etc/zoidbergchain
```

## Repo Deploy

Initial clone:

```bash
sudo -u <DEPLOY_USER> git clone <REPO_URL> /srv/zoidbergchain/current
```

Update existing checkout:

```bash
cd /srv/zoidbergchain/current
sudo -u <DEPLOY_USER> git fetch --all --tags
sudo -u <DEPLOY_USER> git pull --ff-only
```

## Python Environment

```bash
cd /srv/zoidbergchain/current
sudo -u <DEPLOY_USER> python3 -m venv /srv/zoidbergchain/venv
sudo -u <DEPLOY_USER> /srv/zoidbergchain/venv/bin/python -m pip install --upgrade pip
sudo -u <DEPLOY_USER> /srv/zoidbergchain/venv/bin/pip install -r requirements.txt
```

## Frontend Build

```bash
cd /srv/zoidbergchain/current/zoidbergcoin-ui
sudo -u <DEPLOY_USER> npm install
sudo -u <DEPLOY_USER> env \
  VITE_API_BASE_URL=https://zoidbergcoin.com/api \
  VITE_ENVIRONMENT=testnet \
  VITE_PUBLIC_DEMO_MODE=true \
  VITE_ENABLE_DEV_TOOLS=false \
  npm run build
sudo rsync -av --delete /srv/zoidbergchain/current/zoidbergcoin-ui/dist/ /var/www/zoidbergchain/
```

## Server Environment File

Generate a real peer secret:

```bash
openssl rand -hex 32
```

Create `/etc/zoidbergchain/zoidbergchain.env` from [deploy/examples/zoidbergchain.server.env.example](/C:/Users/mattk/ZoidbergChain/deploy/examples/zoidbergchain.server.env.example), then lock it down:

```bash
sudo cp /srv/zoidbergchain/current/deploy/examples/zoidbergchain.server.env.example /etc/zoidbergchain/zoidbergchain.env
sudo chmod 640 /etc/zoidbergchain/zoidbergchain.env
sudo chown root:<DEPLOY_USER> /etc/zoidbergchain/zoidbergchain.env
```

Do not commit the real file and do not paste the real secret into any shared runbook.

## systemd Service

```bash
sudo cp /srv/zoidbergchain/current/deploy/systemd/zoidbergchain-backend.service /etc/systemd/system/zoidbergchain-backend.service
sudo systemctl daemon-reload
sudo systemctl enable zoidbergchain-backend
sudo systemctl start zoidbergchain-backend
sudo systemctl status zoidbergchain-backend
```

## Nginx

```bash
sudo cp /srv/zoidbergchain/current/deploy/nginx/zoidbergcoin.com.conf /etc/nginx/sites-available/zoidbergcoin.com
sudo ln -s /etc/nginx/sites-available/zoidbergcoin.com /etc/nginx/sites-enabled/zoidbergcoin.com
sudo nginx -t
sudo systemctl reload nginx
```

## HTTP Verification Before HTTPS

```bash
curl -I http://zoidbergcoin.com
curl http://zoidbergcoin.com/api/health
curl http://zoidbergcoin.com/api/node-info
curl http://zoidbergcoin.com/api/chain/summary
```

If `/api/health` fails, verify whether `proxy_pass` is stripping `/api/` correctly. With the current config, `location /api/` plus `proxy_pass http://127.0.0.1:8000/;` should forward `/api/health` to `/health`.

## HTTPS

```bash
sudo certbot --nginx -d zoidbergcoin.com -d www.zoidbergcoin.com
sudo certbot renew --dry-run
curl -I https://zoidbergcoin.com
curl https://zoidbergcoin.com/api/health
```

## Post-Deploy Smoke Check

- homepage loads
- public demo banner is visible
- wallet connect is visible
- dev tools are hidden
- `/api/health` works
- `/api/node-info` works
- `/api/chain/summary` works
- explorer loads
- public responses do not expose private keys, session tokens, or peer secrets
- upload limits behave as expected
- CORS works from `https://zoidbergcoin.com`
- backend logs do not show obvious startup or runtime failures

## Functional Smoke Check

- connect MetaMask
- verify wallet
- submit signed content
- vote if enough test wallets are available
- mint certified meme block if practical
- verify reward balance
- create native ZOID transfer
- admit to mempool
- mint meme block including transfer
- verify settlement
- verify explorer shows the transaction and block

If multi-wallet voting is not practical yet, record it as not completed and keep the site labeled controlled testnet.

## Backup After Successful Deploy

```bash
sudo cp /var/lib/zoidbergchain/zoidbergchain.sqlite3 /var/lib/zoidbergchain/zoidbergchain.sqlite3.post-deploy.bak
sudo tar -czf /var/lib/zoidbergchain/content.post-deploy.tgz /var/lib/zoidbergchain/content
sudo tar -czf /var/www/zoidbergchain.post-deploy.tgz /var/www/zoidbergchain
sudo cp /etc/nginx/sites-available/zoidbergcoin.com /var/lib/zoidbergchain/zoidbergcoin.com.nginx.bak
sudo cp /etc/systemd/system/zoidbergchain-backend.service /var/lib/zoidbergchain/zoidbergchain-backend.service.bak
```

Record the environment file path reference:

- `/etc/zoidbergchain/zoidbergchain.env`

Do not copy the secret contents into the repository.
