# Testnet Reset Runbook

This runbook applies to the controlled public demo/testnet only.

## Reset Policy

- reset is allowed only for the controlled public demo/testnet
- reset is not exposed as a public unauthenticated endpoint
- production/public demo nodes must not run with development reset routes enabled
- only designated operators should run the reset procedure

## Before Reset

1. Announce that the controlled testnet may reset and that test ZOID has no real monetary value.
2. Capture a full backup of chain state and content storage.
3. Record the latest block hash and chain height before reset.

## Reset Procedure

1. Stop the node.
2. Preserve the existing data directory as an archival snapshot.
3. Clear or replace the chain state in the configured data directory.
4. Clear or replace content storage only if the reset is intended to remove old test content too.
5. Restart the node in the intended `testnet` environment with public-demo-safe settings.

## After Reset

1. Confirm `GET /health` and `GET /chain/summary` return a fresh network state.
2. Confirm dev-only endpoints remain blocked on the public node.
3. Confirm the UI still displays:
   - ZoidbergChain controlled testnet
   - Test ZOID has no real monetary value
   - This network may reset
   - Not mainnet
4. Notify users that old test balances, submissions, and transfers may no longer exist.
