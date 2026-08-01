# ZoidbergChain

As of Saturday, August 1, 2026, ZoidbergChain is ready for Task 9 public-demo and controlled-testnet hardening on top of the completed Task 1 through Task 8 implementation.

## Stage 1 Goal

Stage 1 is a controlled public demo at `zoidbergcoin.com` with these public labels:

- ZoidbergChain controlled testnet
- Test ZOID has no real monetary value
- This network may reset
- Not mainnet

Current known limitations:

- no anti-Sybil rules yet
- no voter rewards yet
- no replacement policy
- mempools are local, not consensus-wide
- no transfer-only blocks
- no wrapped ZOID / ERC-20 behavior
- not mainnet

## Environment Modes

- `development`: local-only reset/debug tools may be enabled, dev wallet generation may be enabled, localhost CORS is allowed, and rate limits may be relaxed.
- `testnet`: public-demo/testnet mode. Dev-only tools are blocked, private key export is blocked, signed peer messaging and rate limits should be enabled, and CORS should be restricted to expected domains.
- `production`: same lockdown as testnet, with dev tools blocked, private key export blocked, public-safe errors only, and secrets supplied externally.

Disabling dev multi-account tools does not solve anti-Sybil behavior by itself. One real person can still create many real MetaMask wallets. That work remains part of Task 10.

## Deployment Notes

Backend:

- set `ENVIRONMENT=testnet` for the controlled public demo
- configure `PUBLIC_API_MODE=true`
- set `PUBLIC_DEMO_MODE=true`
- configure `NODE_ID`, `NETWORK_NAME`, `PUBLIC_NODE_URL`, `NODE_DATA_DIR`, `CONTENT_STORAGE_DIR`, and `LOG_DIR`
- set a real `PEER_SHARED_SECRET`
- keep `ENABLE_SIGNED_PEER_MESSAGES=true`
- keep rate limits and upload limits enabled

Frontend:

- build `zoidbergcoin-ui` with `VITE_API_BASE_URL` pointing at the HTTPS API origin
- set `VITE_ENVIRONMENT=testnet`
- set `VITE_PUBLIC_DEMO_MODE=true`
- keep `VITE_ENABLE_DEV_TOOLS=false`

Reverse proxy:

- terminate HTTPS at Nginx
- proxy API traffic to the backend host and port
- serve the frontend build output as the public site
- allow only expected public origins through CORS

See the detailed runbooks in:

- [docs/public-demo-deployment-checklist.md](/C:/Users/mattk/ZoidbergChain/docs/public-demo-deployment-checklist.md)
- [docs/backup-restore-runbook.md](/C:/Users/mattk/ZoidbergChain/docs/backup-restore-runbook.md)
- [docs/live-domain-deployment-checklist.md](/C:/Users/mattk/ZoidbergChain/docs/live-domain-deployment-checklist.md)
- [docs/testnet-reset-runbook.md](/C:/Users/mattk/ZoidbergChain/docs/testnet-reset-runbook.md)
- [docs/live-domain-deployment-runbook.md](/C:/Users/mattk/ZoidbergChain/docs/live-domain-deployment-runbook.md)
