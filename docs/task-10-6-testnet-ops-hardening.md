# Task 10.6 Testnet Ops Hardening

As of Friday, August 21, 2026, Task 10.6 adds safer operational visibility and operator runbooks for the controlled ZoidbergChain testnet.

This task does not turn the project into full production observability. It keeps the current manual deployment model, but it makes the invite-only public testnet easier to monitor and safer to operate.

## What Was Added

- safe public status endpoints:
  - `GET /health`
  - `GET /status`
  - `GET /ops/status`
- admin-only operational visibility:
  - `GET /admin/ops/status`
  - `GET /admin/audit-log`
- persistent audit logging for sensitive admin actions
- startup environment validation warnings for unsafe testnet settings
- safe backup, integrity, and environment CLI checks:
  - `python -m scripts.ops backup-status`
  - `python -m scripts.ops verify-backup`
  - `python -m scripts.ops sqlite-integrity-check`
  - `python -m scripts.ops env-validate`
  - `python -m scripts.ops storage-integrity`

## Public Status Endpoints

These endpoints are intentionally safe for public probing and uptime checks.

They include:

- service alive status
- environment
- network name
- storage backend
- database/content-storage reachability
- chain height
- pending submissions count
- pending access requests count
- mempool transaction count
- peer count
- uptime
- safe build metadata when present
- public demo mode

They do not expose:

- admin credentials
- admin sessions
- invite hashes
- wallet session tokens
- private keys
- peer shared secrets

## Admin Ops Dashboard Usage

The `/admin` dashboard now includes an Ops section and a recent audit log section.

The Ops section shows:

- backend health summary
- environment and storage backend
- chain height
- pending access requests
- pending review submissions
- mempool size
- peer count
- latest block summary
- storage reachability
- integrity and backup signals
- recent access requests, account decisions, and wallet binding activity

The audit log section shows recent sensitive admin actions with:

- timestamp
- action
- result
- related request, account, or wallet identifier when applicable
- safe actor/session identifier when available
- remote IP and user agent when available
- optional reason/operator note

## Audit Log Behavior

The audit trail is persistent node state and is intended for operator review, not public exposure.

Currently audited actions include:

- admin login success
- admin login failure
- admin logout
- access request approval
- access request rejection
- direct invite creation
- access account suspension
- access account reactivation
- access account revocation
- wallet binding revocation
- admin ops dashboard view

Invite codes, password hashes, wallet signatures, and peer secrets are not written into the audit log.

## Beta Readiness Checklist

Use this checklist before inviting 3 to 5 external testers:

- backend `python -m pytest` passes
- frontend `npm test` passes
- frontend `npm run build` passes
- live access gate works for private visitors
- admin dashboard loads and login works
- admin ops dashboard reports healthy or explainable warning state
- recent admin actions appear in the audit log
- mobile access request flow has been tested
- MetaMask Mobile flow has been tested
- approved wallet reconnect works without reusing an invite code
- unapproved wallet remains blocked
- backup verification has been run
- public disclaimer copy is visible
- `Test ZOID has no real monetary value` copy is visible

## Known Limitations

- no Prometheus, Grafana, or long-term metrics pipeline yet
- no automated CI/CD deployment yet
- deployment and rollback are still manual
- backup restore remains operator-driven and should be tested in a separate restore location first
- admin sessions are still the current lightweight server-side model, not a broader enterprise auth system
