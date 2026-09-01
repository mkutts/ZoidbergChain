# Protocol v1 Genesis and Reset Policy

Authoritative note: [docs/protocol-v1.md](/C:/Users/mattk/ZoidbergChain/docs/protocol-v1.md) is the primary Public Testnet v1 protocol specification. If this document conflicts with it or with [docs/protocol-v1-freeze-report.json](/C:/Users/mattk/ZoidbergChain/docs/protocol-v1-freeze-report.json), the authoritative spec and freeze report win.

This document freezes the canonical Public Testnet v1 genesis block and reset policy for ZoidbergChain.

The canonical Public Testnet v1 network identity is:

- `network_name = "zoidberg-testnet"` for the runtime display alias
- `network_id = "zoidberg-public-testnet-v1"` for all canonical Protocol v1 binding and validation

The canonical Public Testnet v1 genesis hash is:

- `2b99e87f80e0e855ab98b3269b635be5415273f41d7d4bf1a2aeb8b277b13061`

## 1. Genesis object

- Object type: `genesis`
- Genesis version: `1`
- Protocol version: `1`
- Canonical domain: `zoidbergchain/genesis/v1`
- Hash algorithm: `SHA-256`
- Hash construction: `SHA-256(canonical genesis domain envelope bytes)`

Public Testnet v1 genesis is a special Protocol v1 genesis object, not a normal accepted-media Protocol v1 block.

That means:

- it uses the Task 2 genesis domain instead of the accepted-media block domain
- it embeds the exact original Zoidberg genesis meme bytes recovered from the pre-v1 genesis record
- it does not pretend to be originality-earned content
- the embedded `media_bytes` are genesis-hash critical
- a missing local image file never changes the Public Testnet v1 genesis hash because the bytes are committed in the repository fixture and persisted in block 0

The previous media-less Public Testnet v1 genesis hash was superseded before launch. The network ID remains `zoidberg-public-testnet-v1` only because the public testnet had not launched; after launch, changing genesis under the same network ID is forbidden.

## 2. Exact canonical values

### Canonical genesis payload fields

| Field | Classification | Exact value |
|---|---|---|
| `domain` | canonical genesis-hashed | `zoidbergchain/genesis/v1` |
| `protocol` | canonical genesis-hashed | `zoidbergchain` |
| `protocol_version` | canonical genesis-hashed | `1` |
| `network_id` | canonical genesis-hashed and persisted | `zoidberg-public-testnet-v1` |
| `genesis_version` | canonical genesis-hashed and persisted | `1` |
| `index` | canonical genesis-hashed and persisted | `0` |
| `previous_hash` | canonical genesis-hashed and persisted | `0000000000000000000000000000000000000000000000000000000000000000` |
| `timestamp` | canonical genesis-hashed and persisted | `1785542400` |
| `transactions` | canonical genesis-hashed and persisted | exactly the three fixed bootstrap allocations below |
| `miner` | canonical genesis-hashed and persisted | `GENESIS` |
| `meme_text` | canonical genesis-hashed | `ZoidbergChain Public Testnet v1 Genesis` |
| `meme.text` | persisted representation of the canonical text marker | `ZoidbergChain Public Testnet v1 Genesis` |
| `media_hash` | canonical genesis-hashed and persisted | `dfba5a7e5e8e5f5da047a2ed58660c9d52665c39f2793da90cba51419f8525c7` |
| `media_bytes` | canonical genesis-hashed and persisted | Protocol v1 canonical bytes object for the recovered JPEG bytes |
| `mime_type` | canonical genesis-hashed and persisted | `image/jpeg` |
| `content_type` | canonical genesis-hashed and persisted | `image` |
| `total_supply` | canonical genesis-hashed and persisted | `1000000000` |
| `initial_reward_pool` | canonical genesis-hashed and persisted | `100000000` |
| `hash` | persisted but not hashed | `2b99e87f80e0e855ab98b3269b635be5415273f41d7d4bf1a2aeb8b277b13061` |
| `network_name` | derived/runtime alias only | `zoidberg-testnet` |
| validator membership | operational/config state, not genesis consensus state | not committed into genesis |
| `block_version` | not applicable to genesis | omitted |
| `native_transactions` | not applicable to genesis | omitted |
| submission/certificate fields | not applicable to genesis | omitted |
| native-transfer settlement fields | not applicable to genesis | omitted |

### Fixed bootstrap allocation transactions

The canonical genesis payload contains exactly these three transactions in this exact order:

1. `GENESIS -> 034f355bdcb7cc0af728ef3cceb9615d90684bb5b2ca5f859ab0f0b704075871aa` for `790000000`
2. `GENESIS -> 02466d7fcae563e5cb09a0d1870bb580344804617879a14949cf22285f1bae3f27` for `100000000`
3. `GENESIS -> 023c72addb4fdf09af94f0c94d7fe92a386a7e70cf8a1d85916386bb2535c7b1b1` for `10000000`

Each transaction also freezes:

- `tip = 0`
- `signature = null`
- `payload_size_kb = 0`
- `created_at = 1785542400`

The bootstrap allocations plus the frozen initial reward pool equal the frozen total supply:

- `790000000 + 100000000 + 10000000 = 900000000`
- `900000000 + 100000000 = 1000000000`

### Persisted canonical genesis record

The exact literal record, including the full canonical bytes object, is frozen in `tests/fixtures/protocol_v1_golden_vectors.json`. Abridged shape:

```json
{
  "genesis_version": 1,
  "protocol_version": 1,
  "network_id": "zoidberg-public-testnet-v1",
  "index": 0,
  "previous_hash": "0000000000000000000000000000000000000000000000000000000000000000",
  "timestamp": 1785542400,
  "transactions": [
    {
      "sender": "GENESIS",
      "recipient": "034f355bdcb7cc0af728ef3cceb9615d90684bb5b2ca5f859ab0f0b704075871aa",
      "amount": 790000000,
      "tip": 0,
      "signature": null,
      "payload_size_kb": 0,
      "created_at": 1785542400
    },
    {
      "sender": "GENESIS",
      "recipient": "02466d7fcae563e5cb09a0d1870bb580344804617879a14949cf22285f1bae3f27",
      "amount": 100000000,
      "tip": 0,
      "signature": null,
      "payload_size_kb": 0,
      "created_at": 1785542400
    },
    {
      "sender": "GENESIS",
      "recipient": "023c72addb4fdf09af94f0c94d7fe92a386a7e70cf8a1d85916386bb2535c7b1b1",
      "amount": 10000000,
      "tip": 0,
      "signature": null,
      "payload_size_kb": 0,
      "created_at": 1785542400
    }
  ],
  "miner": "GENESIS",
  "meme": {
    "text": "ZoidbergChain Public Testnet v1 Genesis"
  },
  "media_hash": "dfba5a7e5e8e5f5da047a2ed58660c9d52665c39f2793da90cba51419f8525c7",
  "media_bytes": {
    "$type": "bytes",
    "$encoding": "hex",
    "$value": "<exact 57343 recovered JPEG bytes encoded as lowercase hex>"
  },
  "mime_type": "image/jpeg",
  "content_type": "image",
  "hash": "2b99e87f80e0e855ab98b3269b635be5415273f41d7d4bf1a2aeb8b277b13061",
  "total_supply": 1000000000,
  "initial_reward_pool": 100000000
}
```

## 3. Timestamp and previous-hash semantics

- Frozen timestamp scalar: `1785542400`
- Frozen UTC meaning: `2026-08-01T00:00:00+00:00`
- Frozen previous hash: `0000000000000000000000000000000000000000000000000000000000000000`

The genesis timestamp is an explicit integer Unix-seconds value. It is not derived from wall-clock startup time.

## 4. Initial ZOID state

Public Testnet v1 genesis freezes the following initial state:

- total supply: `1000000000`
- initial reward pool: `100000000`
- bootstrap balances: the three fixed transactions above

No raw floats are part of the canonical genesis payload.

## 5. Validator and bootstrap state

Controlled-validator membership is not currently committed into genesis consensus state.

Validator and bootstrap peer authorization remain operational/config state:

- peer registration
- shared-secret configuration
- signed peer-message policy
- any operator allowlists

Those settings still matter operationally, but they are not part of the frozen canonical genesis hash.

## 6. Canonical serialization and golden vectors

Public Testnet v1 genesis uses the Task 2 canonical domain envelope.

Golden vectors committed in source and tests include:

- canonical Public Testnet v1 genesis envelope bytes
- canonical Public Testnet v1 genesis hash
- genesis media byte encoding and media SHA-256
- alternate-network genesis hash
- one-field-mutated genesis hash
- one-byte media mutation genesis hash

Current literal test vectors:

- canonical genesis hash: `2b99e87f80e0e855ab98b3269b635be5415273f41d7d4bf1a2aeb8b277b13061`
- genesis media hash: `dfba5a7e5e8e5f5da047a2ed58660c9d52665c39f2793da90cba51419f8525c7`
- same payload under `network_id = "zoidberg-public-testnet-v1-reset-1"`: `097d76e704deba4a476fa682f8ff9e10b78e5a6c569435bd99edcdf8e8566fbc`
- same network with `timestamp = 1785542401`: `bc9a7f7344bb96cc1c6f7a29a0a3faceb69b73c8fe47acc22542beae38e400ac`
- same network with one changed media byte: `0278be27ada816685debc6f5356d458d9a2f562fa8be25ef45dcdbc839603d3a`

These vectors prove that network identity, genesis-field mutations, and media-byte mutations change the genesis identity.

## 7. Startup behavior

### Clean node

If no chain data exists:

- the node loads exactly the canonical Public Testnet v1 genesis record
- the node verifies the literal expected genesis hash
- the node persists the canonical genesis immediately

### Existing valid Public Testnet v1 chain

If chain data exists and the stored genesis matches the frozen canonical genesis:

- the node loads the chain
- validates genesis first
- validates the rest of the chain normally

### Existing legacy chain

If the stored chain begins with a legacy runtime-generated genesis:

- the node refuses Public Testnet v1 startup
- raises a `legacy_chain_reset_required` failure
- does not silently delete or replace the stored chain

### Existing mismatched or mutated genesis

If the stored chain contains a different Public Testnet v1 genesis payload or hash:

- the node fails closed
- raises a `genesis_mismatch` or `invalid_chain_state` failure
- does not append a new genesis
- does not continue syncing

### Corrupted or malformed storage

If stored chain data cannot be parsed into a valid chain state:

- the node fails closed
- raises an explicit `invalid_chain_state` or `missing_genesis` failure
- does not silently delete the existing storage

## 8. Network identity invariant

Frozen rule:

> A Public Testnet network identity uniquely identifies one canonical genesis.

Therefore:

- `same network_id + different genesis` is forbidden
- changing any consensus-significant genesis value requires a different network identity
- a future reset must publish a new network identity and a new canonical genesis/hash

## 9. Storage behavior

Public Testnet v1 genesis is identical across:

- JSON storage
- SQLite storage
- restart/load cycles
- JSON to SQLite migration of a valid Public Testnet v1 chain
- export/import backup round trips

Fresh-node and restart tests assert:

- fresh JSON genesis hash equals fresh SQLite genesis hash
- both equal the literal expected genesis hash
- round-trip persistence preserves the exact genesis record and hash
- embedded genesis `media_bytes` survive byte-for-byte

## 10. JSON to SQLite migration

Migration behavior is frozen as follows:

- canonical Public Testnet v1 chains migrate normally
- migrated genesis must remain byte-for-byte and hash-for-hash identical
- migrated genesis media bytes must remain byte-for-byte identical
- source snapshots with legacy or mutated genesis are rejected
- migration never rewrites a foreign genesis into the Public Testnet v1 canonical genesis silently

## 11. Backup, export, and import

Protocol v1 export metadata now carries:

- `protocol_version`
- `network_id`
- `canonical_genesis_hash`
- `genesis_hash`
- `genesis_status`

Import behavior is frozen as follows:

- import validates the snapshot network binding
- import validates canonical Public Testnet v1 genesis before writing
- import preserves the embedded genesis media bytes
- wrong or legacy genesis snapshots are rejected
- import never rewrites foreign genesis
- explicit overwrite is still required before replacing existing local data

## 12. Peer genesis validation and chain replacement

Before adopting peer chain data, the node now validates:

- peer `network_name`
- peer `network_id`
- peer `protocol_version`
- peer `genesis_hash`
- canonical genesis validity of the received chain
- embedded genesis `media_bytes`, `media_hash`, `mime_type`, and `content_type`

An authenticated peer with a different genesis is still rejected.

Fork choice is only applied after the candidate chain passes canonical genesis validation.

That means:

- stronger or longer foreign-genesis chains are rejected before fork choice
- same-genesis chains are compared normally by the originality/height/hash rule

## 13. Legacy-chain and mixed-chain policy

Public Testnet v1 startup does not silently adopt legacy genesis data.

Current implementation behavior is:

- legacy genesis at height `0` is rejected for Public Testnet v1 startup
- historical legacy data can still be inspected out of band from the raw storage files
- the repository still retains explicit legacy block compatibility paths outside genesis freezing

Current Task 8 code does not redefine every post-genesis legacy compatibility path. A chain that begins with the canonical Public Testnet v1 genesis is still validated by the existing explicit legacy/v1 block rules after height `0`.

Operationally, Public Testnet v1 should still be treated as starting from the frozen canonical genesis after an explicit reset. Legacy data is not auto-upgraded into that chain.

## 14. Genesis confirmation and finality treatment

Genesis is the canonical root of the selected Public Testnet v1 chain.

Genesis classification is:

- canonical immediately when it is the selected chain root
- confirmed by the normal depth rule once `confirmations >= 2`
- finalized by the normal depth rule once `confirmations >= 6`

Genesis is not marked finalized by definition in code today. It follows the same depth-derived confirmation/finality calculation as any other canonical block, with `confirmations = canonical_tip_height - 0`.

With the default Public Testnet v1 depths, genesis becomes:

- confirmed once the canonical tip reaches height `2`
- finalized once the canonical tip reaches height `6`

`PROTOCOL_V1_CONFIRMATION_DEPTH` and `PROTOCOL_V1_FINALITY_DEPTH` remain operational depth-policy parameters, not part of the frozen genesis hash.

## 15. Reset policy

### Pre-launch or legacy-dev reset

Existing legacy or mismatched local chain data must be reset explicitly before the node can join Public Testnet v1.

Existing local chains rooted at the superseded media-less Public Testnet v1 genesis hash must also be reset explicitly. The node fails closed and does not rewrite block 0 in place.

The node does not delete incompatible data automatically.

### Public Testnet v1 reset after launch

If a reset is ever required after launch:

- do not generate a new genesis under `zoidberg-public-testnet-v1`
- publish a new network identity, for example `zoidberg-public-testnet-v1-reset-1`
- publish the new canonical genesis and hash
- require nodes and validators to opt into that reset deliberately

## 16. Operator reset instructions

Recommended operator sequence:

1. Stop the node.
2. Back up the existing data directory before deleting anything.
3. Remove only the local blockchain storage for the active backend.
4. Restart the node and confirm it recreates the canonical genesis hash `2b99e87f80e0e855ab98b3269b635be5415273f41d7d4bf1a2aeb8b277b13061`.

Current storage deletion scope:

- JSON backend reset removes `blockchain.json` and `blockchain.json.bak`
- SQLite backend reset removes `zoidbergchain.db` and its backup file
- peer lists, content cache, and other local files are not automatically deleted by genesis reset logic

The development-only reset endpoints:

- `/dev/reset`
- `/reset_blockchain`

remain disabled outside development mode and are not part of the Public Testnet operator reset path.

## 17. Known limitations

- The repository still contains explicit legacy post-genesis block compatibility paths that are outside this genesis freeze.
- Submission IDs remain random UUIDs and are not part of the genesis identity work.
- Peer replay-state persistence is still operational security state, not genesis state.
- Public Testnet v1 confirmation/finality depth settings remain operational policy values rather than genesis-hashed constants.
