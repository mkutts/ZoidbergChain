# Local Two-Node Storage Verification

This guide runs two ZoidbergChain API nodes on one Windows machine with separate node identities and separate storage paths. It is designed for Task 5.8 verification across JSON, SQLite, and mixed-backend setups.

## JSON Startup

Node A JSON:

```powershell
$env:NODE_ID = "node-a"
$env:NODE_PORT = "8000"
$env:PUBLIC_NODE_URL = "http://127.0.0.1:8000"
$env:DATA_DIR = "data/node-a"
$env:NODE_DATA_DIR = "data/node-a"
$env:STORAGE_BACKEND = "json"
```

Node B JSON:

```powershell
$env:NODE_ID = "node-b"
$env:NODE_PORT = "8001"
$env:PUBLIC_NODE_URL = "http://127.0.0.1:8001"
$env:DATA_DIR = "data/node-b"
$env:NODE_DATA_DIR = "data/node-b"
$env:STORAGE_BACKEND = "json"
```

One-time JSON setup:

```powershell
.\scripts\init_two_node_data.ps1 -Reset
```

Start the JSON nodes:

```powershell
.\scripts\start_node_a.ps1
.\scripts\start_node_b.ps1
```

This keeps Node A on `data/node-a` and Node B on `data/node-b`. Each node reads and writes only its own JSON files.

## SQLite Startup

Node A SQLite:

```powershell
$env:NODE_ID = "node-a"
$env:NODE_PORT = "8000"
$env:PUBLIC_NODE_URL = "http://127.0.0.1:8000"
$env:DATA_DIR = "data/node-a"
$env:NODE_DATA_DIR = "data/node-a"
$env:STORAGE_BACKEND = "sqlite"
$env:SQLITE_DB_PATH = "data/node-a/zoidbergchain.db"
```

Node B SQLite:

```powershell
$env:NODE_ID = "node-b"
$env:NODE_PORT = "8001"
$env:PUBLIC_NODE_URL = "http://127.0.0.1:8001"
$env:DATA_DIR = "data/node-b"
$env:NODE_DATA_DIR = "data/node-b"
$env:STORAGE_BACKEND = "sqlite"
$env:SQLITE_DB_PATH = "data/node-b/zoidbergchain.db"
```

Recommended one-time SQLite setup:

```powershell
.\scripts\init_two_node_data.ps1 -Reset
.\.venv\Scripts\python.exe .\scripts\migrate_json_to_sqlite.py --data-dir data\node-a
.\.venv\Scripts\python.exe .\scripts\migrate_json_to_sqlite.py --data-dir data\node-b
```

Start the SQLite nodes:

```powershell
.\scripts\start_node_a_sqlite.ps1
.\scripts\start_node_b_sqlite.ps1
```

This keeps Node A on `data/node-a/zoidbergchain.db` and Node B on `data/node-b/zoidbergchain.db`. The two nodes do not share a database file.

## Mixed Backend Startup

The peer wire format is backend-agnostic, so one node can run JSON while the other runs SQLite.

Example:

```powershell
.\scripts\start_node_a.ps1
.\scripts\start_node_b_sqlite.ps1
```

Or the reverse:

```powershell
.\scripts\start_node_a_sqlite.ps1
.\scripts\start_node_b.ps1
```

## Peer Registration

Register Node B with Node A:

```powershell
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/peers/register" -ContentType "application/json" -Body '{"node_id":"node-b","url":"http://127.0.0.1:8001","network_name":"zoidberg-testnet"}'
```

Register Node A with Node B:

```powershell
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8001/peers/register" -ContentType "application/json" -Body '{"node_id":"node-a","url":"http://127.0.0.1:8000","network_name":"zoidberg-testnet"}'
```

Confirm peers:

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/peers" | ConvertTo-Json -Depth 5
Invoke-RestMethod "http://127.0.0.1:8001/peers" | ConvertTo-Json -Depth 5
```

## Manual Checklist: JSON Backend

1. Run `.\scripts\init_two_node_data.ps1 -Reset`.
2. Start `.\scripts\start_node_a.ps1`.
3. Start `.\scripts\start_node_b.ps1`.
4. Register Node A and Node B as peers.
5. Submit content on Node A:

   ```powershell
   $walletA = (Invoke-RestMethod "http://127.0.0.1:8000/get_wallets").wallets[0].public_key
   $submission = curl.exe -s -X POST "http://127.0.0.1:8000/submit_content" -F "submitter=$walletA" -F "text_content=two node json meme" -F "image=@zoidberg.jpg" | ConvertFrom-Json
   $submissionId = $submission.submission.submission_id
   ```

6. Confirm the submission appears on Node B:

   ```powershell
   Invoke-RestMethod "http://127.0.0.1:8001/submissions/$submissionId" | ConvertTo-Json -Depth 8
   ```

7. Vote from Node B:

   ```powershell
   1..5 | ForEach-Object {
       $voter = (Invoke-RestMethod -Method Post "http://127.0.0.1:8001/generate_wallet").wallet.public_key
       curl.exe -s -X POST "http://127.0.0.1:8001/submissions/$submissionId/vote" -F "voter=$voter" -F "vote_type=original" | Out-Null
   }
   ```

8. Confirm the votes appear on Node A:

   ```powershell
   Invoke-RestMethod "http://127.0.0.1:8000/submissions/$submissionId/votes" | ConvertTo-Json -Depth 8
   ```

9. Evaluate on Node A:

   ```powershell
   $evaluation = curl.exe -s -X POST "http://127.0.0.1:8000/submissions/$submissionId/evaluate" -F "automated_originality_passed=true" | ConvertFrom-Json
   $evaluation | ConvertTo-Json -Depth 8
   ```

10. Confirm the Originality Certificate exists on Node A and Node B:

   ```powershell
   Invoke-RestMethod "http://127.0.0.1:8000/submissions/$submissionId/certificate" | ConvertTo-Json -Depth 8
   Invoke-RestMethod "http://127.0.0.1:8001/submissions/$submissionId/certificate" | ConvertTo-Json -Depth 8
   ```

11. Mint on Node A:

   ```powershell
   Invoke-RestMethod -Method Post "http://127.0.0.1:8000/mint-queue/$submissionId/mint" | ConvertTo-Json -Depth 8
   ```

12. If Node B reports `sync_needed`, run:

   ```powershell
   Invoke-RestMethod -Method Post "http://127.0.0.1:8001/chain/sync" | ConvertTo-Json -Depth 8
   ```

13. Confirm both nodes show compatible chain summaries:

   ```powershell
   Invoke-RestMethod "http://127.0.0.1:8000/chain/summary" | ConvertTo-Json -Depth 5
   Invoke-RestMethod "http://127.0.0.1:8001/chain/summary" | ConvertTo-Json -Depth 5
   ```

14. Restart both nodes and confirm that chain state, submissions, votes, certificates, peers, and wallet-safe data still load from each node's own JSON files.

## Manual Checklist: SQLite Backend

1. Run `.\scripts\init_two_node_data.ps1 -Reset`.
2. Migrate both data directories with `scripts\migrate_json_to_sqlite.py`.
3. Start `.\scripts\start_node_a_sqlite.ps1`.
4. Start `.\scripts\start_node_b_sqlite.ps1`.
5. Repeat the same peer registration, submit, vote, evaluate, certificate, mint, sync, and restart flow used for JSON.
6. Confirm Node A reloads from `data/node-a/zoidbergchain.db`.
7. Confirm Node B reloads from `data/node-b/zoidbergchain.db`.
8. Confirm the two SQLite nodes do not share state unless it is synced through the API.

## Manual Checklist: Mixed Backend

1. Start one node with JSON and the other with SQLite.
2. Register peers both ways.
3. Submit on one node and confirm the submission appears on the other.
4. Cast votes on the opposite node and confirm they appear on the origin node.
5. Evaluate, create the certificate, and mint on the origin node.
6. Confirm the certificate and block reach the peer, or run `/chain/sync` if the peer reports `sync_needed`.
7. Restart both nodes and confirm the JSON node reloads from its JSON files while the SQLite node reloads from its own database.

## Restart And Catch-Up

This is the safest manual restart flow for certificate-backed blocks:

1. Start both nodes.
2. Register peers both ways.
3. Submit content on Node A and let the submission and vote metadata reach Node B.
4. Stop Node B.
5. On Node A, evaluate the submission, create the certificate, and mint the block.
6. Restart Node B.
7. Run:

   ```powershell
   Invoke-RestMethod -Method Post "http://127.0.0.1:8001/chain/sync" | ConvertTo-Json -Depth 8
   ```

8. Confirm Node B catches up, the latest block hash matches Node A, and the cumulative originality score matches.

Current limitation:

- Certificate-backed chain sync still requires the receiving node to have the supporting submission metadata.
- Image binary transport is still separate from storage sync, so mint on the node that has the uploaded image available locally.

## Backup And Integrity

JSON node example:

```powershell
.\.venv\Scripts\python.exe .\scripts\storage_backup.py --data-dir data\node-a --storage-backend json
.\.venv\Scripts\python.exe -c "from storage import JSONStorageBackend, check_storage_integrity; backend = JSONStorageBackend(blockchain_file='data/node-a/blockchain.json', peers_file='data/node-a/peers.json'); print(check_storage_integrity(backend))"
```

SQLite node example:

```powershell
.\.venv\Scripts\python.exe .\scripts\storage_backup.py --data-dir data\node-b --storage-backend sqlite
.\.venv\Scripts\python.exe -c "from storage import SQLiteStorageBackend, check_storage_integrity; backend = SQLiteStorageBackend(sqlite_db_path='data/node-b/zoidbergchain.db'); print(check_storage_integrity(backend))"
```

For SQLite-specific backup verification:

```powershell
.\.venv\Scripts\python.exe -c "from storage import SQLiteStorageBackend; backend = SQLiteStorageBackend(sqlite_db_path='data/node-b/zoidbergchain.db'); print(backend.backup_sqlite_database())"
```

## Automated Verification

Run the focused two-node verification set:

```powershell
.\.venv\Scripts\python.exe .\scripts\test_two_node_consensus.py
```

Run the backend-specific two-node storage tests directly:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\integration\test_two_node_storage_backends.py tests\integration\test_two_node_consensus_verification.py tests\storage\test_storage_regression_pass.py
```

## Known Limitations

- `STORAGE_BACKEND=json` remains the default backend.
- SQLite support is available for validation and opt-in local testing, but rollout remains conservative.
- Backups and exports are file-based and unencrypted.
- Dev exports with private keys remain highly sensitive.
- Import is intentionally conservative about genesis and network mismatches.
- SQLite storage is still snapshot-oriented and not normalized.
- Submission metadata and image binary transport are separate concerns.
- Certificate-backed chain sync depends on supporting submission metadata already being present on the receiving node.
