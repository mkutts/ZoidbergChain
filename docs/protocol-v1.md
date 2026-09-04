# Protocol v1

This document is the authoritative Public Testnet v1 protocol specification for ZoidbergChain as of Saturday, August 29, 2026. If another Protocol v1 document conflicts with this file or with [docs/protocol-v1-freeze-report.json](/C:/Users/mattk/ZoidbergChain/docs/protocol-v1-freeze-report.json), this file and the freeze report win.

## 1. Scope and status

ZoidbergChain Public Testnet v1 is:

- an independent Layer 1 blockchain
- a controlled-validator testnet
- a native-asset chain where ZOID is the Layer 1 asset
- a chain where MetaMask and Ethereum-style `0x` signatures are used for wallet identity and signing
- a chain where one accepted media submission creates exactly one certified Protocol v1 block
- a chain where MODEL A is fixed: full accepted media bytes are part of the immutable Protocol v1 block record

Protocol-frozen behavior:

- canonical serialization
- object domains and network binding
- Protocol v1 block hashing
- vote signing and vote-set hashing
- certificate ID derivation
- native transfer signing and transaction IDs
- peer-message authentication and replay protection
- canonical genesis
- lifecycle, confirmation, and finality semantics

Operational and testnet limitations:

- validator membership is controlled operationally, not by an on-chain validator-election protocol
- finality is operational depth policy, not BFT or cryptographic irreversibility
- peer transport uses a shared secret, not per-peer asymmetric keys
- side branches are evaluated during sync and replacement, but are not durably stored as a full alternate-branch database

Legacy compatibility behavior:

- legacy blocks, votes, certificates, transfers, and peer auth paths still exist on explicit compatibility branches
- legacy behavior is not part of the canonical Public Testnet v1 object format
- legacy or mismatched genesis state must be reset explicitly before joining the canonical Public Testnet v1 chain

## 2. Protocol identity

Exact protocol identity:

- protocol name: `zoidbergchain`
- protocol version: `1`
- version tag: `v1`
- canonical network ID: `zoidberg-public-testnet-v1`
- runtime network alias: `zoidberg-testnet`

Object domains:

- block: `zoidbergchain/block/v1`
- genesis: `zoidbergchain/genesis/v1`
- submission: `zoidbergchain/submission/v1`
- vote: `zoidbergchain/vote/v1`
- originality certificate: `zoidbergchain/originality-certificate/v1`
- native transfer: `zoidbergchain/native-transfer/v1`
- peer message: `zoidbergchain/peer-message/v1`

`network_id` and `protocol_version` are consensus-critical or signature-critical anywhere Protocol v1 hashes, signs, validates, or authenticates an object.

The submission domain is defined in `protocol_v1.py`, but there is no separate explicit Protocol v1 submission object version today. Submission IDs remain application identifiers, not canonical signed Protocol v1 object IDs.

| Object | Object version | Protocol version | Network bound? | Domain separated? | Legacy path? |
| ------ | -------------: | ---------------: | -------------- | ----------------- | ------------ |
| block | 1 | 1 | Yes | Yes | Yes |
| vote | 1 | 1 | Yes | Yes | Yes |
| certificate | 1 | 1 | Yes | Yes | Yes |
| native transfer | 1 | 1 | Yes | Yes | Yes |
| peer message | 1 | 1 | Yes | Yes | Yes |
| genesis | 1 | 1 | Yes | Yes | Yes, but only as an explicit reset-required rejection path |

## 3. Canonical serialization

Protocol v1 canonical serialization is UTF-8 JSON with these exact rules:

- dictionaries require string keys only
- dictionary keys are sorted lexicographically
- lists preserve input order
- JSON uses separators `(",", ":")`
- no insignificant whitespace is emitted
- `ensure_ascii=False`
- `allow_nan=False`
- Unicode code points are preserved exactly as provided
- no Unicode normalization is performed

Allowed primitive values:

- strings
- integers
- booleans
- `null`

Rejected values:

- floats, including `NaN`, `Infinity`, and `-Infinity`
- `Decimal` unless the caller converts it explicitly before serialization
- `datetime`, `date`, and `time`
- tuples
- sets
- arbitrary class instances
- dictionaries with non-string keys

Bytes are encoded only as the reserved tagged object:

```json
{
  "$type": "bytes",
  "$encoding": "hex",
  "$value": "00ff"
}
```

Byte rules:

- exact keys must be `$type`, `$encoding`, and `$value`
- `$type` must be `bytes`
- `$encoding` must be `hex`
- `$value` must be lowercase hexadecimal
- the shape is reserved, so raw user dictionaries with that exact shape are rejected to avoid collisions

Consensus-critical decimal-like values are not left as floats. Callers normalize them to plain decimal strings before canonical serialization. Current Protocol v1 helpers use:

- no exponent notation
- no trailing zeroes
- `0` instead of `-0`
- finite values only

This means another implementation must reproduce:

- the exact UTF-8 bytes
- the exact key ordering
- the exact list order
- the exact byte tagging
- the exact caller-side numeric-string normalization

## 4. Hashing

Protocol v1 uses SHA-256 and lowercase hexadecimal output.

The canonical bytes hashed for each object are:

- block: `sha256(Block.consensus_payload_v1_bytes())`
- certificate ID: `sha256(canonical_domain_bytes(certificate_identity_payload, object_type="originality-certificate", network_id=network_id))`
- vote signed-message hash: `sha256(canonical_domain_bytes(vote_payload, object_type="vote", network_id=network_id))`
- vote-set hash: `sha256(canonical_domain_bytes(vote_set_payload, object_type="vote", network_id=network_id))`
- native transfer signed-message hash: `sha256(canonical_domain_bytes(transfer_payload, object_type="native-transfer", network_id=network_id))`
- native transaction ID: the same canonical native-transfer envelope bytes as the signed-message hash
- peer message ID: `sha256(protocol_v1_peer_envelope_bytes(...))`
- genesis: `sha256(canonical_domain_bytes(genesis_payload, object_type="genesis", network_id=network_id))`

Protocol v1 does not use `str(dict)` or legacy string concatenation for v1 hashes. Those legacy techniques remain only on explicit legacy compatibility branches.

## 5. Wallet identity and signing

Wallet identity uses MetaMask and Ethereum-style `personal_sign`.

Rules:

- the user signs the exact canonical Protocol v1 message text returned by the backend
- the backend recovers the signer from the signed message and signature
- the recovered wallet address is normalized to lowercase `0x...`
- the recovered wallet must match the expected declared wallet
- signature recovery is necessary but not sufficient; the message content must also match the reconstructed Protocol v1 payload

Domain separation principle:

- votes cannot be replayed as transfers
- transfers cannot be replayed as votes
- objects on another network produce different hashes or signatures
- changing protocol version changes the signed identity

MetaMask support does not make ZOID an ERC-20 token. ZOID remains the native Layer 1 asset of ZoidbergChain.

## 6. Submission lifecycle

Persisted submission statuses remain:

- `pending`
- `approved`
- `queued`
- `rejected`
- `hard_rejected`
- `minted`

Protocol v1 lifecycle states are derived from persisted submission state, certificate validity, the selected chain, and the confirmation/finality policy.

Definitions:

- submitted: the submission record exists
- voting: status is `pending` and voting is not locked
- rejected: status is `rejected` or `hard_rejected`
- certified: a valid originality certificate exists for the submission
- mint-eligible: certified, not already minted, not mint-blocked, and sufficient block inputs exist
- block created: a local candidate block was built
- block accepted: a candidate block passed local acceptance validation and was appended
- canonical: the block is on the currently selected chain
- confirmed: canonical and `confirmations >= 2`
- finalized: canonical and `confirmations >= 6`

Current derived phase order:

`submitted -> voting -> rejected or certified -> mint-eligible -> block-created -> block-accepted -> canonical -> confirmed -> finalized`

Forbidden transitions under normal protocol flow:

- submitted -> block-created without certification
- rejected -> certified
- rejected -> block-created
- certified -> voting
- finalized -> voting
- finalized -> rejected

Voting is locked when:

- submission status is `approved`, `queued`, `rejected`, `hard_rejected`, or `minted`, or
- an originality certificate already exists for the submission

## 7. Votes

Protocol v1 vote fields are:

- `vote_version`
- `protocol_version`
- `network_id`
- `submission_id`
- `content_hash`
- `voter_wallet_address`
- `vote_type`
- `nonce`
- `issued_at`
- `expires_at`

Exact vote domain:

- `zoidbergchain/vote/v1`

Exact signed payload:

- the inner vote payload contains `vote_version`, `submission_id`, `content_hash`, `voter_wallet_address`, `vote_type`, `nonce`, `issued_at`, and `expires_at`
- the signed envelope also binds `domain`, `network_id`, `object_type="vote"`, `protocol`, `protocol_version`, and `payload`

Replay binding comes from the signed combination of:

- domain
- network ID
- submission ID
- content hash
- wallet
- vote choice
- nonce
- issued/expiry timestamps

Duplicate and update semantics:

- one wallet may cast only one vote per submission
- there is no update-in-place vote path
- duplicate votes are rejected
- finalized or certified submissions do not accept more votes

Expiry semantics:

- expiry governs whether the signed vote is accepted as a fresh authorization
- expiry does not retroactively invalidate an already-certified historical vote record used to validate an already-issued certificate

## 8. Originality certificates

Protocol v1 originality certificates use:

- `certificate_version = 1`

Canonical certificate identity fields are:

- `certificate_version`
- `submission_id`
- `content_hash`
- `creator_wallet`
- `vote_hash`
- `vote_total`
- `decisive_vote_total`
- `original_votes`
- `not_original_votes`
- `unsure_votes`
- `minimum_votes_required`
- `approval_threshold`
- `approval_percentage`
- `originality_score`

Vote-set hashing rules:

- the vote-set payload contains `vote_set_version`, `submission_id`, `content_hash`, and ordered `votes`
- each vote contributes only `voter` and `vote_type`
- voters are normalized
- duplicate voters are rejected
- final vote sets are sorted by `(voter, vote_type)`
- database insertion order and peer arrival order do not affect the vote hash

Numeric normalization:

- `approval_threshold`
- `approval_percentage`
- `originality_score`

are normalized to canonical decimal strings before hashing.

Certificate ID algorithm:

- `sha256(canonical_domain_bytes(certificate_identity_payload, object_type="originality-certificate", network_id=network_id))`

Timestamp treatment:

- `approved_at` is persisted but not part of the certificate identity payload

Persisted metadata excluded from certificate ID:

- `protocol_version`
- `network_id`
- `approved_at`
- `network_name`
- `issuing_node_id`
- `content_id`

Why those fields are excluded:

- `protocol_version` and `network_id` are already bound by the outer canonical envelope
- `approved_at`, `network_name`, `issuing_node_id`, and `content_id` are metadata that should not cause honest nodes with the same final vote set and accepted content to derive different certificate IDs

Blocks link certificates through:

- `certificate_id`
- `submission_id`
- `content_hash`
- `content_id`
- `creator_wallet`
- `vote_hash`
- `approval_percentage`
- `decisive_vote_total`
- `minimum_votes_required`
- `approved_at`
- `originality_score`

## 9. Meme Proof of Originality

Current certification rules are:

- the voting window is `24` hours
- minimum votes required are `max(5, ceil(active_users * 0.05))`
- the submission may be decided when the voting window expires or the current minimum-vote threshold is reached
- approval threshold is `0.70`
- decisive vote total is `original_votes + not_original_votes`
- decisive vote total must be greater than zero for certification

Current originality score formula is:

`1.0 + decisive_vote_total * 0.10 + approval_percentage * 1.0 + unsure_votes * 0.0`

Certification effect:

- if `approval_percentage >= 0.70`, the submission is approved and a certificate may be created
- otherwise the submission is rejected
- an approved certified submission becomes eligible for exactly one Protocol v1 block when mint conditions are satisfied

Reward interaction:

- creator reward metadata is committed into the minted block
- optional voter rewards are selected and settled through blocks
- duplicate reward IDs are rejected during block validation

This section describes the current mechanism only. It does not redefine the economics beyond what the implementation already freezes.

## 10. Protocol v1 blocks

### Deterministic certified mint ordering (Public Testnet v1)

When more than one certified submission is ready to mint, nodes compare the
following tuple in ascending lexicographic order and mint the first eligible
entry:

1. `content_hash`
2. `vote_hash`
3. `certificate_id`

Each component is the lowercase, 64-character SHA-256 hexadecimal value from
the originality certificate. The certificate must first pass the existing
certificate/submission, network, vote, and immutable-content validation rules.
`content_hash` binds the accepted immutable media; `vote_hash` binds the
finalized vote set; and `certificate_id` is derived from the canonical
certificate identity, including the submission identity, and is the
collision-resistant final tie-breaker. Consequently, valid distinct
submissions have a total order without consulting queue insertion position,
database row IDs, local timestamps, or node-local state.

Certification and content preparation may occur concurrently. Canonical mint
selection is nevertheless linear: each block is chosen from the ready set by
this tuple before the existing one-block mint path runs. This ordering rule is
consensus-affecting; it does not change eligibility validation or introduce an
atomic-commit/finality rule.

Protocol v1 accepted-media blocks use:

- `block_version = 1`
- `network_id = "zoidberg-public-testnet-v1"`
- domain `zoidbergchain/block/v1`

Consensus-hashed fields are:

- `block_version`
- `index`
- `previous_hash`
- `timestamp`
- ordered `transactions`
- `miner`
- `submission_id`
- `certificate_id`
- `content_hash`
- `content_id` when present
- `content_type`
- `mime_type`
- `media_hash`
- `media_bytes`
- `creator_wallet`
- `vote_hash`
- `approval_percentage`
- `decisive_vote_total`
- `minimum_votes_required`
- `approved_at`
- `originality_score`
- `reward_type`
- `reward_recipient`
- `reward_amount`
- `reward_source`
- `minted_at`
- ordered `native_transactions`
- ordered `voter_rewards`
- `transactions_hash` when present
- `meme_text` when `meme.text` is present

The domain envelope also binds:

- `protocol`
- `protocol_version`
- `network_id`
- `object_type="block"`

Persisted but non-hashed or compatibility-only fields include:

- `hash`
- `meme.encoded_image`
- `transaction_ids`
- `transaction_count`

Legacy-only block behavior:

- blocks without `block_version` are legacy blocks
- legacy blocks use legacy hash calculation
- legacy blocks do not satisfy MODEL A

Timestamp representation:

- block timestamps remain scalar numeric values in the persisted record
- canonical hashing normalizes those numeric values into deterministic decimal strings

Ordering:

- `transactions`, `native_transactions`, and `voter_rewards` preserve input order
- order is consensus-significant
- Protocol v1 does not sort those lists during hashing

## 11. MODEL A media permanence

MODEL A for Protocol v1 means:

- full accepted media bytes are persisted inside the Protocol v1 block record as `media_bytes`
- `media_bytes` are block-hash critical
- validation recomputes content integrity from embedded bytes and declared `mime_type`
- `content_hash` and `media_hash` must both match the embedded bytes
- auxiliary content storage is cache, index, and serving support; it is not the sole authoritative copy
- deleting auxiliary content storage does not destroy the authoritative media copy if the block still exists
- export/import and peer sync preserve the authoritative embedded media
- legacy blocks do not satisfy MODEL A

Canonical byte encoding uses the reserved bytes object:

```json
{
  "$type": "bytes",
  "$encoding": "hex",
  "$value": "<lowercase-hex-bytes>"
}
```

## 12. Native ZOID transfers

Native ZOID transfers are Layer 1 ZoidbergChain transactions and are not Ethereum/ERC-20 transactions.

Protocol v1 transfer identity uses:

- `transaction_version = 1`
- domain `zoidbergchain/native-transfer/v1`
- canonical network binding to `zoidberg-public-testnet-v1`

Signed fields are:

- `transaction_version`
- `from_address`
- `to_address`
- `amount`
- `fee`
- `nonce`
- `timestamp`
- `memo`

The signed envelope also binds:

- `domain`
- `network_id`
- `object_type="native-transfer"`
- `protocol`
- `protocol_version`
- `payload`

Transaction ID uses the same canonical transfer intent as the signed-message hash. Signature bytes and local status metadata are excluded.

Amount and fee representation:

- canonical decimal strings
- no scientific notation
- no negative values
- amount must be greater than zero
- up to 6 decimal places
- fee may be `0`
- nonzero fees are currently rejected by admission and block validation policy

Nonce semantics:

- initial nonce is `1`
- nonce is per sender wallet
- next nonce must be strict sequential
- pending accepted transactions reserve nonce slots
- settled transactions consume nonces durably from chain state

Timestamp semantics:

- ISO 8601 string input is required
- timezone offset is required
- values normalize to UTC `datetime.isoformat()` text
- `Z` normalizes to `+00:00`

Memo semantics:

- memo is signed and tx-ID-critical
- leading and trailing whitespace are trimmed
- blank-after-trim becomes `null`
- maximum length is `280`

Signer recovery and replay prevention:

- recovered signer must match `from_address`
- duplicate transaction IDs are rejected where applicable
- nonce reservation and settled-chain nonce state provide durable anti-replay protection
- network binding prevents replay onto another network

Block inclusion:

- native transfers may be included in certified accepted-media blocks
- transaction order in the block is consensus-significant
- Protocol v1 blocks revalidate signature, tx ID, nonce, balance, and fee policy before settlement
- versionless legacy transfers are not admitted into new Protocol v1 blocks

## 13. Peer protocol

Protocol v1 peer messages use:

- `peer_message_version = 1`
- `protocol_version = 1`
- domain `zoidbergchain/peer-message/v1`
- HMAC algorithm `hmac-sha256`

Message types are:

- `peer-registration`
- `submission`
- `vote`
- `certificate`
- `block`
- `native-transaction`
- `transaction-fetch`
- `mempool-summary`
- `content-metadata`
- `content-download`
- `chain-summary`
- `chain-blocks`

Authenticated envelope fields are:

- `domain`
- `message_type`
- `network_id`
- `nonce`
- `object_type="peer-message"`
- `payload`
- `peer_message_version`
- `protocol`
- `protocol_version`
- `sender_node_id`
- `timestamp`

Message ID:

- `sha256(protocol_v1_peer_envelope_bytes(...))`

Authentication:

- HMAC-SHA256 over the canonical peer envelope bytes
- transmitted in `X-ZOID-Signature`
- compared with `hmac.compare_digest(...)`

Replay protection:

- freshness window default: `300` seconds
- the same window is used symmetrically for old and future timestamps
- replay state is persisted in `peer_message_replay_state.json`
- the replay store keys on both `message_id` and `(sender_node_id, nonce)`
- replay state survives restart

Legacy peer auth behavior:

- when signed peer messages are enabled, Protocol v1 peer headers are required
- explicit Protocol v1 requests do not fall back to legacy peer auth
- when signed peer messages are disabled, the legacy `X-ZOID-Peer-Secret` path may still be used

Peer authentication never bypasses inner-object validation.

## 14. Genesis

Protocol v1 genesis uses:

- `genesis_version = 1`
- domain `zoidbergchain/genesis/v1`
- `network_id = "zoidberg-public-testnet-v1"`
- `timestamp = 1785542400`
- `previous_hash = 0000000000000000000000000000000000000000000000000000000000000000`
- `miner = "GENESIS"`
- `meme_text = "ZoidbergChain Public Testnet v1 Genesis"`
- `media_hash = "dfba5a7e5e8e5f5da047a2ed58660c9d52665c39f2793da90cba51419f8525c7"`
- `media_bytes` containing the exact original Zoidberg genesis meme bytes recovered from the pre-v1 genesis record
- `mime_type = "image/jpeg"`
- `content_type = "image"`
- total supply `1000000000`
- initial reward pool `100000000`

The previous media-less Public Testnet v1 genesis hash was superseded before launch. The network ID remains `zoidberg-public-testnet-v1` only because this correction happened pre-launch; after launch, changing a genesis under the same network ID is forbidden.

The Public Testnet v1 genesis block contains the exact original Zoidberg genesis meme bytes recovered from the pre-v1 genesis record. Genesis remains a special genesis object and is not a user submission, voted submission, originality certificate, or reward-earning accepted-media block.

Canonical genesis transactions, in exact order:

1. `GENESIS -> 034f355bdcb7cc0af728ef3cceb9615d90684bb5b2ca5f859ab0f0b704075871aa` for `790000000`
2. `GENESIS -> 02466d7fcae563e5cb09a0d1870bb580344804617879a14949cf22285f1bae3f27` for `100000000`
3. `GENESIS -> 023c72addb4fdf09af94f0c94d7fe92a386a7e70cf8a1d85916386bb2535c7b1b1` for `10000000`

Each genesis transaction also uses:

- `tip = 0`
- `signature = null`
- `payload_size_kb = 0`
- `created_at = 1785542400`

Genesis stores immutable media, but still omits normal accepted-media workflow fields:

- `block_version`
- `native_transactions`
- submission and certificate metadata

Validator membership is operational configuration, not genesis-hashed consensus state.

PUBLIC TESTNET V1 GENESIS HASH = 2b99e87f80e0e855ab98b3269b635be5415273f41d7d4bf1a2aeb8b277b13061

## 15. Chain validation and fork choice

Current fork-choice rule is:

1. prefer higher cumulative originality score
2. if scores tie, prefer higher chain height
3. if height ties, prefer lower latest block hash

Chains with a different genesis are rejected before fork choice during startup, import, migration, and peer chain-sync validation. `compare_chains_by_originality(...)` also rejects candidate chains whose genesis hash differs from the local chain root.

## 16. Confirmation and finality

Current Protocol v1 constants are:

- confirmation depth: `2`
- finality depth: `6`

Confirmation rule:

`confirmations = canonical_tip_height - block_height`

Finality rule:

- only canonical blocks can be confirmed or finalized
- confirmed means `confirmations >= 2`
- finalized means `confirmations >= 6`
- finality type is `operational_depth`
- finality scope is `policy_not_bft`

This finality is not BFT, Byzantine, or cryptographic irreversibility.

## 17. Reorg behavior

When chain selection changes:

- canonical, confirmed, and finalized status is recalculated from the selected chain
- reward-pool state is recomputed from the selected chain
- native transactions absent from the selected chain are reconciled from `settled` back to `validated_pending`
- submissions whose Protocol v1 mint block disappears are reconciled away from `minted`
- if a displaced submission still has a valid certificate, it returns to `approved` or `queued` depending on mint-queue presence

Current storage limitation:

- the node stores the selected chain, not a durable side-branch archive of all competing branches

## 18. Storage

The repository supports:

- JSON storage
- SQLite storage

Logical-equivalence requirement:

- both backends must preserve the same Protocol v1 chain, genesis, votes, certificates, transfers, and content metadata semantics
- persisted `media_bytes` must round-trip exactly
- canonical genesis must round-trip exactly

Consensus state includes:

- the selected chain
- Protocol v1 embedded media bytes inside blocks
- originality certificates
- votes used for certificate validation and lifecycle decisions
- native transaction records and settlement state relevant to chain-derived balances

Operational, security, or cache state includes:

- auxiliary content storage
- peer replay-state persistence
- peer lists
- export/import metadata

Export/import snapshots carry:

- `protocol_version`
- `network_id`
- `canonical_genesis_hash`
- `genesis_hash`
- `genesis_status`

Import rejects wrong-network or wrong-genesis snapshots for Public Testnet v1.

## 19. Sync

Protocol v1 sync behavior includes:

- block sync with embedded `media_bytes`
- vote sync
- certificate sync
- native transaction sync
- chain summary and chain block sync
- genesis validation before chain replacement
- inner-object revalidation after peer authentication

Current invariants:

- peer block sync can repopulate local content cache from embedded block bytes
- chain sync validates peer `network_name`, `network_id`, `protocol_version`, and `genesis_hash`
- wrong-genesis or wrong-network chains are rejected before fork choice
- peer authentication does not bypass vote, certificate, transfer, block, or content validation

## 20. Legacy compatibility

Legacy compatibility remains explicit and separate from canonical Public Testnet v1 behavior.

Legacy paths:

- legacy blocks without `block_version`
- legacy votes using human-readable signed messages
- legacy certificates without `certificate_version`
- legacy versionless native transfers and versionless tx IDs
- legacy peer auth using `X-ZOID-Peer-Secret` when signed peer messaging is disabled
- legacy direct block creation through `POST /add_block`

Public Testnet v1 treatment:

- canonical Protocol v1 accepted-media blocks require explicit Protocol v1 metadata
- new Protocol v1 votes, certificates, transfers, peer messages, and genesis do not silently fall back to legacy interpretation
- legacy direct block creation is a development-only compatibility path and is not the Public Testnet v1 mint path
- legacy genesis is rejected for Public Testnet v1 startup, import, migration, and chain sync

## 21. Reset policy

Reset policy is:

- legacy or mismatched local chain data must be reset explicitly before joining canonical Public Testnet v1
- reset is not automatic
- the same `network_id` with a different genesis is forbidden
- a future reset requires a new network identity and a new published canonical genesis and hash

Development-only reset endpoints remain disabled outside development mode.

## 22. Security invariants

Frozen security invariants are:

- expected signer matching for votes and native transfers
- network binding and domain separation for Protocol v1 objects
- nonce and replay protections for votes, transfers, and peer transport
- HMAC verification for peer messages
- durable replay-state persistence for peer transport
- embedded-media integrity checks for Protocol v1 blocks
- certificate and vote-set linkage checks
- public/admin separation
- fail-closed genesis validation

## 23. Known limitations

Current non-resolved limitations are:

- controlled validator set
- shared peer secret management and no per-peer key rotation protocol
- operational depth-based finality rather than BFT finality
- side branches are not durably persisted as a first-class alternate-branch store
- MODEL A increases chain storage growth because full media bytes are embedded in blocks
- legacy compatibility code is still present for non-canonical paths
- joining canonical Public Testnet v1 still depends on an operator reset/runbook when legacy or mismatched local data exists
