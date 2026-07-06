# Local Two-Node Meme Consensus Verification

This guide runs two ZoidbergChain API nodes on one Windows machine with separate node identities and separate data directories. Use it to verify Meme-Based Proof of Originality Consensus without changing production deployment behavior.

## Node Configuration

Node A:

```powershell
$env:NODE_ID = "node-a"
$env:NODE_PORT = "8000"
$env:PUBLIC_NODE_URL = "http://127.0.0.1:8000"
$env:DATA_DIR = "data/node-a"
$env:STORAGE_BACKEND = "json"
# $env:SQLITE_DB_PATH = "data/node-a/zoidbergchain.db"
```

Node B:

```powershell
$env:NODE_ID = "node-b"
$env:NODE_PORT = "8001"
$env:PUBLIC_NODE_URL = "http://127.0.0.1:8001"
$env:DATA_DIR = "data/node-b"
$env:STORAGE_BACKEND = "json"
# $env:SQLITE_DB_PATH = "data/node-b/zoidbergchain.db"
```

The startup scripts also set `NODE_DATA_DIR` to the same path because the backend accepts both `DATA_DIR` and `NODE_DATA_DIR`. `STORAGE_BACKEND=json` keeps the current behavior explicit. If you switch to SQLite, `SQLITE_DB_PATH` should stay under the node-specific data directory so the two nodes do not share a database file.

## One-Time Setup

From the project root:

```powershell
.\scripts\init_two_node_data.ps1 -Reset
```

This creates:

- `data/node-a/blockchain.json`
- `data/node-b/blockchain.json`

Node B starts from a copy of Node A's genesis chain so both nodes have the same genesis hash. Chain sync rejects peers with different genesis hashes.

## Start The Nodes

Open two PowerShell terminals from the project root.

Terminal 1:

```powershell
.\scripts\start_node_a.ps1
```

Terminal 2:

```powershell
.\scripts\start_node_b.ps1
```

Node A runs at `http://127.0.0.1:8000`.
Node B runs at `http://127.0.0.1:8001`.

Manual equivalent for Node A:

```powershell
$env:NODE_ID = "node-a"
$env:NODE_HOST = "127.0.0.1"
$env:NODE_PORT = "8000"
$env:PUBLIC_NODE_URL = "http://127.0.0.1:8000"
$env:NETWORK_NAME = "zoidberg-testnet"
$env:DATA_DIR = "data/node-a"
$env:NODE_DATA_DIR = "data/node-a"
$env:STORAGE_BACKEND = "json"
# $env:SQLITE_DB_PATH = "data/node-a/zoidbergchain.db"
.\.venv\Scripts\python.exe -m uvicorn api:app --host 127.0.0.1 --port 8000
```

Manual equivalent for Node B:

```powershell
$env:NODE_ID = "node-b"
$env:NODE_HOST = "127.0.0.1"
$env:NODE_PORT = "8001"
$env:PUBLIC_NODE_URL = "http://127.0.0.1:8001"
$env:NETWORK_NAME = "zoidberg-testnet"
$env:DATA_DIR = "data/node-b"
$env:NODE_DATA_DIR = "data/node-b"
$env:STORAGE_BACKEND = "json"
# $env:SQLITE_DB_PATH = "data/node-b/zoidbergchain.db"
.\.venv\Scripts\python.exe -m uvicorn api:app --host 127.0.0.1 --port 8001
```

## Register Peers

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

## Scenario A: Normal Consensus Flow

1. Start Node A.
2. Start Node B.
3. Register Node B with Node A.
4. Register Node A with Node B.
5. Confirm `/peers` works on both nodes.
6. Submit meme content on Node A:

   ```powershell
   $walletA = (Invoke-RestMethod "http://127.0.0.1:8000/get_wallets").wallets[0].public_key
   $submission = curl.exe -s -X POST "http://127.0.0.1:8000/submit_content" -F "submitter=$walletA" -F "text_content=two node original meme" -F "image=@zoidberg.jpg" | ConvertFrom-Json
   $submissionId = $submission.submission.submission_id
   $submission.broadcast | ConvertTo-Json -Depth 5
   ```

7. Confirm the submission broadcasts to Node B:

   ```powershell
   Invoke-RestMethod "http://127.0.0.1:8001/submissions/$submissionId" | ConvertTo-Json -Depth 5
   ```

8. Vote from wallets across nodes. The current minimum vote count is 5. Use wallets that are not the creator wallet:

   ```powershell
   1..5 | ForEach-Object {
       $voter = (Invoke-RestMethod -Method Post "http://127.0.0.1:8001/generate_wallet").wallet.public_key
       curl.exe -s -X POST "http://127.0.0.1:8001/submissions/$submissionId/vote" -F "voter=$voter" -F "vote_type=original" | Out-Null
   }
   Invoke-RestMethod "http://127.0.0.1:8000/submissions/$submissionId/votes" | ConvertTo-Json -Depth 5
   ```

9. Evaluate and approve on Node A:

   ```powershell
   $evaluation = curl.exe -s -X POST "http://127.0.0.1:8000/submissions/$submissionId/evaluate" -F "automated_originality_passed=true" | ConvertFrom-Json
   $evaluation | ConvertTo-Json -Depth 8
   ```

10. Confirm an Originality Certificate exists on Node A:

    ```powershell
    $certificate = Invoke-RestMethod "http://127.0.0.1:8000/submissions/$submissionId/certificate"
    $certificate | ConvertTo-Json -Depth 8
    ```

    If needed, manually rebroadcast the certificate:

    ```powershell
    Invoke-RestMethod -Method Post "http://127.0.0.1:8000/certificates/$($certificate.certificate.certificate_id)/broadcast" | ConvertTo-Json -Depth 8
    ```

11. Mint the approved submission on Node A:

    ```powershell
    $mint = Invoke-RestMethod -Method Post "http://127.0.0.1:8000/mint-queue/$submissionId/mint"
    $mint.block | ConvertTo-Json -Depth 8
    ```

12. Confirm the minted block includes the certificate-backed fields:

    ```powershell
    $mint.block.submission_id
    $mint.block.certificate_id
    $mint.block.content_hash
    $mint.block.originality_score
    ```

13. Confirm the block broadcast reached Node B. If the peer receive response says `sync_needed`, run sync on Node B:

    ```powershell
    Invoke-RestMethod -Method Post "http://127.0.0.1:8001/chain/sync" | ConvertTo-Json -Depth 8
    ```

14. Confirm both nodes show the same latest block hash and cumulative originality score:

    ```powershell
    Invoke-RestMethod "http://127.0.0.1:8000/chain/summary" | ConvertTo-Json -Depth 5
    Invoke-RestMethod "http://127.0.0.1:8001/chain/summary" | ConvertTo-Json -Depth 5
    ```

## Scenario B: Higher Originality Score Beats Longer Lower-Score Chain

This is easiest to verify through the automated backend tests because creating competing certified chains by hand requires carefully copying certificates and submissions between nodes.

Automated route:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\integration\test_two_node_consensus_verification.py -k "higher_score or longer_lower"
```

Expected result:

- A chain with higher `cumulative_originality_score` is selected.
- A longer chain with lower `cumulative_originality_score` is rejected.
- Fork choice does not choose merely by height.

Manual API route, if you have prepared two matching-genesis nodes with supporting certificate data:

1. Make Chain A longer using legacy or non-certified blocks so its cumulative originality score stays lower.
2. Make Chain B shorter but include a certified meme block with a higher originality score.
3. Register the Chain B node as a peer of the Chain A node.
4. Run:

   ```powershell
   Invoke-RestMethod -Method Post "http://127.0.0.1:8000/chain/sync" | ConvertTo-Json -Depth 8
   ```

5. Confirm the sync result reason is `higher_originality_score` and the local summary now matches the higher-score chain.

## Scenario C: Deterministic Tie-Breaker

Equal-score forks are easiest to verify with automated tests because they need precise chain construction.

Automated route:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\integration\test_two_node_consensus_verification.py -k "equal_score"
```

Expected result:

- If cumulative originality scores are tied, higher chain height wins.
- If score and height are tied, the lexicographically lowest `latest_block_hash` wins.
- The result is deterministic regardless of peer order.

The broader fork-choice tests are also available:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\blockchain\test_chain_originality_comparison.py tests\api\test_chain_sync_api.py
```

## Lightweight Verification Script

Run the focused two-node consensus verification set:

```powershell
.\.venv\Scripts\python.exe .\scripts\test_two_node_consensus.py
```

The script runs the in-process two-node consensus tests plus the peer block receive and chain sync API tests. It does not start server processes.

## Notes And Current Limits

- Each node uses its own data directory through `DATA_DIR` and `NODE_DATA_DIR`.
- `STORAGE_BACKEND=json` is the supported backend for now.
- `STORAGE_BACKEND=sqlite` is also supported and uses `SQLITE_DB_PATH`.
- Node A writes to `data/node-a`.
- Node B writes to `data/node-b`.
- Submission metadata can sync between nodes, but image binary transport is not implemented yet. Mint submissions on the node that has the uploaded image file.
- Certificate-backed block broadcasts send the certificate before the block and also include the certificate payload with the block receive request.
- Chain sync returns certificate payloads for returned certificate-backed blocks. If a peer omits a required certificate, sync fails safely with a clear missing certificate error.
- Certificate-backed synced blocks still require matching submission metadata. Submission/image binary transport remains separate, and image binary transport is not implemented yet.
- Peer block receive returns `sync_needed` on previous-hash mismatch. It does not start a background sync job.
- Fork choice is based on cumulative originality score, then height, then lexicographically lowest latest block hash.
- JSON to SQLite migration is deferred to Task 5.3.
