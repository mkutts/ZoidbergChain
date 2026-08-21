# Testnet Restart Recovery Checklist

Use this checklist after restarting the live controlled testnet backend on Friday, August 21, 2026 or later.

## Service Checks

```bash
sudo systemctl status zoidbergchain-backend --no-pager
sudo journalctl -u zoidbergchain-backend -n 100 --no-pager
```

Confirm:

- the backend service is active
- there is no repeated crash loop
- startup diagnostics do not report unexplained environment errors

## Safe API Checks

```bash
curl https://zoidbergcoin.com/api/health
curl https://zoidbergcoin.com/api/status
curl https://zoidbergcoin.com/api/ops/status
curl https://zoidbergcoin.com/api/access/status
curl https://zoidbergcoin.com/api/admin/session
```

Confirm:

- `/api/health` returns `status=ok`
- `/api/status` returns chain height and safe environment validation counts
- `/api/ops/status` remains public-safe only
- `/api/access/status` still reports `invite_only`
- `/api/admin/session` does not authenticate anonymous visitors

## Access Gate Checks

Confirm in a private browser window:

- the controlled gate appears for an unauthenticated visitor
- the app is not unlocked for an unauthenticated visitor
- request access still submits successfully if requests are enabled

## Admin Checks

Confirm:

- `/admin` loads
- admin login works
- admin ops panel loads
- recent admin audit entries are visible

## Approved Wallet Recovery Checks

Confirm with an already approved wallet:

1. connect the previously bound wallet
2. sign the wallet challenge if prompted
3. verify the app unlocks without requiring a new invite code

Then confirm with a different wallet:

1. connect an unapproved or different wallet
2. verify the app stays locked

## Storage And Chain Checks

Confirm:

- content upload storage is writable
- database is reachable
- chain height is stable and did not reset unexpectedly
- latest block hash matches expected recent chain state

## If Something Looks Wrong

Run:

```bash
python -m scripts.ops env-validate
python -m scripts.ops backup-status
python -m scripts.ops verify-backup
python -m scripts.ops sqlite-integrity-check
python -m scripts.ops storage-integrity
```

Then review:

- [task-10-6-testnet-ops-hardening.md](/C:/Users/mattk/ZoidbergChain/docs/task-10-6-testnet-ops-hardening.md)
- [backup-restore-runbook.md](/C:/Users/mattk/ZoidbergChain/docs/backup-restore-runbook.md)
