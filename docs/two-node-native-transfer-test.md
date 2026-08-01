# Two-Node Native Transfer Test

This runbook covers the automated two-node native ZOID transfer verification added for Task 8.9.

## What it proves

The test spins up two isolated local node app instances with separate data directories, separate node IDs, and separate URLs on the same `zoidberg-testnet` network. It verifies this full lifecycle:

1. A sender wallet receives chain-derived ZOID from a deterministic dev-only genesis allocation that is present on both nodes.
2. Node A mints a certified meme reward block and Node B accepts it.
3. The sender signs a native transfer on Node A.
4. The transfer is recorded, admitted to Node A's local mempool, and broadcast to Node B.
5. Node B accepts the transaction without any local wallet session.
6. Node A mints a certified meme block that includes the transfer.
7. Node B accepts the settlement block and clears the mempool entry.
8. Final balances and chain tip match on both nodes.

It also checks these failure cases:

- duplicate transaction gossip is idempotent
- duplicate block receive is idempotent
- tampered transaction amount is rejected
- tampered signature is rejected
- wrong-network transaction is rejected
- same sender plus same nonce plus different transaction is rejected
- invalid transfer-bearing block is rejected without mutating balances
- transfer-only block is rejected
- a transaction does not settle until a meme-mined block includes it

## Prerequisites

- Windows, macOS, or Linux with the project checked out locally
- the project virtual environment installed at `.venv`
- backend test dependencies installed
- `zoidberg.jpg` present at the project root

## Command to run

Run the standalone verification:

```powershell
.\.venv\Scripts\python.exe .\scripts\two_node_native_transfer_test.py
```

Run the pytest integration check:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\integration\test_two_node_native_transfer_verification.py -q
```

## Environment variables

No manual environment variables are required for the automated harness.

The harness configures dev-only temporary node settings internally:

- `ENVIRONMENT=development`
- `NETWORK_NAME=zoidberg-testnet`
- unique `NODE_ID` values for Node A and Node B
- unique `PUBLIC_NODE_URL` values for Node A and Node B
- unique temporary `DATA_DIR` values for Node A and Node B

The temporary data directories are created under the OS temp area for the duration of the run and are cleaned up automatically.

## Expected output

The script prints step-by-step progress and ends with a summary similar to:

```text
Two-node native transfer verification summary
Node A URL: http://node-a.test:8000
Node B URL: http://node-b.test:8001
Network: zoidberg-testnet
Sender: 0x...
Recipient: 0x...
Reward block: <hash> @ height 1
Transfer tx_id: <tx_id>
Transfer amount: 3 ZOID
Node A mempool status before settlement: mempool
Node B mempool status before settlement: mempool
Settlement block: <hash> @ height 2
Sender final balance: Node A 2 / Node B 2
Recipient final balance: Node A 3 / Node B 3
TWO-NODE NATIVE TRANSFER TEST PASSED
```

## Troubleshooting

- If the script reports a missing dependency, activate or rebuild `.venv` and reinstall backend requirements.
- If the script reports a missing `zoidberg.jpg`, restore the project root test asset before rerunning.
- If a peer registration or sync assertion fails, check that both temporary nodes stayed on `zoidberg-testnet`.
- If a settlement assertion fails, inspect whether the transfer ever reached `mempool` on both nodes before the settlement mint.
- If a balance mismatch appears, inspect whether the prefunded genesis state matched before peer registration and whether the reward block reached Node B before the transfer was created.

## Important behavior notes

- Mempools are local. Node A and Node B can temporarily disagree before block inclusion.
- Native transfers settle only when a valid meme-mined block includes them.
- Transfer-only blocks are disallowed by design.
- Replacement policy is still not implemented.
- The sender's starting spendable balance in this harness comes from a dev-only deterministic genesis allocation. The separate reward block is used to prove cross-node block acceptance before the transfer settles.
- This harness does not change Meme Proof of Originality consensus or originality scoring.
