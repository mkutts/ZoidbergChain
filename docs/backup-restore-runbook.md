# Backup And Restore Runbook

This runbook is for the controlled public demo/testnet and is intentionally simple.

## What To Back Up

- JSON state if `STORAGE_BACKEND=json`
  - `blockchain.json`
  - `peers.json`
- SQLite state if `STORAGE_BACKEND=sqlite`
  - `SQLITE_DB_PATH`
- content storage
  - `CONTENT_STORAGE_DIR`
- logs if you need operational history
  - `LOG_DIR`

## Backup Procedure

1. Stop writes if possible or put the node into a maintenance window.
2. Record the active environment values for `ENVIRONMENT`, `NETWORK_NAME`, `NODE_ID`, `STORAGE_BACKEND`, `NODE_DATA_DIR`, and `CONTENT_STORAGE_DIR`.
3. Copy the chain state files for the active storage backend.
4. Copy the full content storage directory.
5. Store the backup with a timestamp and network label.

## Restore Procedure

1. Stop the node.
2. Preserve the current state as a rollback snapshot before restoring.
3. Restore the chain state files for the active backend.
4. Restore the content storage directory.
5. Start the node with the same `NETWORK_NAME` and intended `NODE_ID`.

## Post-Restore Verification

- call `GET /health`
- call `GET /chain/summary`
- verify the latest block hash matches the expected backup snapshot
- verify balances on a few known accounts through `/accounts/{wallet_address}`
- verify content hashes can still resolve through `/content/{content_hash}/metadata`
- verify a sample text object or image preview still loads

## Chain Integrity Notes

- if JSON state was restored, verify the blockchain file and peer file came from the same snapshot window
- if SQLite state was restored, verify the database file was fully copied while the node was stopped or quiesced
- if content storage is missing objects, the chain may still reference those hashes even though local preview fetches fail

## Two-Node Recovery Notes

- restore both nodes from snapshots taken from the same testnet epoch when possible
- verify both nodes report the same `network_name`, similar chain height, and the expected latest block hash after sync
- run the two-node native transfer verification after recovery before reopening the demo
