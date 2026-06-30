# Local Two-Node Peer Networking

This guide starts two ZoidbergChain API nodes on one machine with separate local data directories.

## One-Time Setup

From the project root:

```powershell
.\scripts\init_two_node_data.ps1 -Reset
```

This creates:

- `data/node-a/blockchain.json`
- `data/node-b/blockchain.json`

Node B starts from a copy of Node A's genesis chain so both nodes have the same genesis hash. That matters because basic chain sync rejects different-genesis peers.

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
Invoke-RestMethod "http://127.0.0.1:8000/peers"
Invoke-RestMethod "http://127.0.0.1:8001/peers"
```

## Manual End-To-End Checklist

1. Start Node A with `.\scripts\start_node_a.ps1`.
2. Start Node B with `.\scripts\start_node_b.ps1`.
3. Register Node B with Node A.
4. Register Node A with Node B.
5. Confirm `/peers` on both nodes includes the other node.
6. Create a submission on Node A.

   ```powershell
   $walletA = (Invoke-RestMethod "http://127.0.0.1:8000/get_wallets").wallets[0].public_key
   $submission = curl.exe -s -X POST "http://127.0.0.1:8000/submit_content" -F "submitter=$walletA" -F "text_content=two node submission" -F "image=@zoidberg.jpg" | ConvertFrom-Json
   $submissionId = $submission.submission.submission_id
   $submission.broadcast | ConvertTo-Json -Depth 5
   ```

   The broadcast should show at least one attempted peer and one success. If it shows `attempted: 0`, register Node B with Node A and rebroadcast. If it shows a failed peer attempt, confirm Node B has Node A registered and rebroadcast.

7. Confirm the submission appears on Node B.

   ```powershell
   Invoke-RestMethod "http://127.0.0.1:8001/submissions/$submissionId"
   ```

   If this returns `Submission not found`, inspect identity and peer registration:

   ```powershell
   Invoke-RestMethod "http://127.0.0.1:8000/node-info"
   Invoke-RestMethod "http://127.0.0.1:8001/node-info"
   Invoke-RestMethod "http://127.0.0.1:8000/peers" | ConvertTo-Json -Depth 5
   Invoke-RestMethod "http://127.0.0.1:8001/peers" | ConvertTo-Json -Depth 5
   ```

   Node A must report `node_id: node-a`, Node B must report `node_id: node-b`, Node A must know Node B, and Node B must know Node A. After fixing registration, rebroadcast from Node A:

   ```powershell
   Invoke-RestMethod -Method Post "http://127.0.0.1:8000/submissions/$submissionId/broadcast" | ConvertTo-Json -Depth 5
   Invoke-RestMethod "http://127.0.0.1:8001/submissions/$submissionId"
   ```

8. Vote on Node B and confirm the vote appears on Node A.

   Generate or choose a non-creator wallet on Node B, then vote:

   ```powershell
   $voterB = (Invoke-RestMethod -Method Post "http://127.0.0.1:8001/generate_wallet").wallet.public_key
   curl.exe -s -X POST "http://127.0.0.1:8001/submissions/$submissionId/vote" -F "voter=$voterB" -F "vote_type=original"
   Invoke-RestMethod "http://127.0.0.1:8000/submissions/$submissionId/votes"
   ```

9. Cast enough distinct votes for approval. The current minimum is 5 votes, so generate additional voters on Node B as needed and vote `original`.
10. Evaluate the submission on Node A.

    ```powershell
    curl.exe -s -X POST "http://127.0.0.1:8000/submissions/$submissionId/evaluate" -F "automated_originality_passed=true"
    ```

11. Mint the queued submission on Node A.

    ```powershell
    Invoke-RestMethod -Method Post "http://127.0.0.1:8000/mint-queue/$submissionId/mint"
    ```

12. Confirm Node B received the new block.

    ```powershell
    Invoke-RestMethod "http://127.0.0.1:8000/chain/summary"
    Invoke-RestMethod "http://127.0.0.1:8001/chain/summary"
    ```

13. Stop Node B.
14. Create and mint another submission on Node A.
15. Restart Node B.
16. Run chain sync on Node B.

    ```powershell
    Invoke-RestMethod -Method Post "http://127.0.0.1:8001/chain/sync"
    ```

17. Confirm Node B catches up to Node A's chain height and latest hash.

    ```powershell
    Invoke-RestMethod "http://127.0.0.1:8000/chain/summary"
    Invoke-RestMethod "http://127.0.0.1:8001/chain/summary"
    ```

## Notes

- Each node uses its own data directory through `NODE_DATA_DIR`.
- Node A writes to `data/node-a`.
- Node B writes to `data/node-b`.
- Submission metadata syncs between nodes, but image binary transport is not implemented yet. Mint submissions on the node that has the uploaded image file.
- Chain sync only appends a longer valid chain with the same genesis hash. It does not resolve equal-height forks.
