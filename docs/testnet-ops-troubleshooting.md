# Testnet Ops Troubleshooting

Use these commands for safe first-pass troubleshooting on the controlled public testnet.

## Backend Logs

```bash
sudo journalctl -u zoidbergchain-backend -n 100 --no-pager
sudo journalctl -u zoidbergchain-backend -f
```

## Nginx Logs

```bash
sudo tail -n 100 /var/log/nginx/access.log
sudo tail -n 100 /var/log/nginx/error.log
```

## Service Status

```bash
sudo systemctl status zoidbergchain-backend --no-pager
sudo systemctl status nginx --no-pager
```

## Safe Curl Checks

```bash
curl https://zoidbergcoin.com/api/health
curl https://zoidbergcoin.com/api/status
curl https://zoidbergcoin.com/api/ops/status
curl https://zoidbergcoin.com/api/access/status
curl https://zoidbergcoin.com/api/admin/session
```

## Safe Local Diagnostics

```bash
python -m scripts.ops env-validate
python -m scripts.ops backup-status
python -m scripts.ops verify-backup
python -m scripts.ops sqlite-integrity-check
python -m scripts.ops storage-integrity
```

## Common Operator Questions

If `/api/health` is up but the site still feels wrong:

- compare `/api/status` chain height with the recent expected value
- confirm `/api/access/status` still says `invite_only`
- confirm the frontend is using `https://zoidbergcoin.com/api` as its base URL

If approved users are locked out:

- confirm the access account is still `active`
- confirm the wallet binding is still `active`
- confirm the user reconnects the same previously bound wallet
- confirm the wallet session re-verification completes successfully

If the admin dashboard looks unhealthy:

- check environment validation warnings in `/admin`
- run `python -m scripts.ops env-validate`
- review the recent audit log for recent revocations or auth failures

If backups are missing:

- run `python -m scripts.ops backup-status`
- run `python -m scripts.ops verify-backup`
- create a fresh backup before attempting any restore testing
