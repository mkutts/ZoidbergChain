# Protocol v1 Block Format

## 1. Block version

Protocol v1 accepted-media blocks are identified by `block_version: 1`.

Legacy blocks omit `block_version` and remain on the legacy hash/validation branch.

## 2. Network binding

Protocol v1 block hashes are bound to the canonical Public Testnet v1 network ID:

`zoidberg-public-testnet-v1`

The persisted block record stores that value in `network_id`. Validation rejects a different network ID, and the same logical payload hashes differently on a different network.

## 3. Canonical block domain

Protocol v1 block hashing uses:

`protocol_v1.canonical_domain_bytes(payload, object_type="block", network_id=network_id)`

The canonical domain envelope binds:

- `domain = "zoidbergchain/block/v1"`
- `protocol = "zoidbergchain"`
- `protocol_version = 1`
- `object_type = "block"`
- `network_id = "zoidberg-public-testnet-v1"`
- `payload = block.consensus_payload_v1()`

## 4. Exact Protocol v1 persisted block schema

Persisted Protocol v1 block records use the existing block dictionary shape plus explicit v1 fields:

| Field / path | Required for v1 | Notes |
|---|---:|---|
| `index` | Yes | Block height |
| `transactions` | Yes | Ordered list of reward and legacy block transactions |
| `previous_hash` | Yes | Previous block hash |
| `miner` | Yes | Block miner / validator identity |
| `meme` | Yes | Compatibility container |
| `meme.encoded_image` | Yes for current mint path | Base64 compatibility copy of stored payload bytes |
| `meme.text` | When text exists | Persisted copy of the accepted text/caption |
| `timestamp` | Yes | Scalar timestamp |
| `hash` | Yes | Persisted block hash |
| `block_version` | Yes | Must be `1` |
| `network_id` | Yes | Must be `zoidberg-public-testnet-v1` |
| `media_hash` | Yes | SHA-256 hash of authoritative embedded media bytes |
| `media_bytes` | Yes | Full immutable accepted media bytes |
| `submission_id` | Yes | Accepted submission identifier |
| `certificate_id` | Yes | Originality certificate identifier |
| `content_hash` | Yes | Canonical accepted-media hash for v1 blocks |
| `content_id` | No | Derived from `content_hash` when present |
| `content_type` | Yes | `text`, `image`, or `mixed` |
| `mime_type` | Yes | Declared MIME type |
| `creator_wallet` | Yes | Submission creator wallet |
| `vote_hash` | Yes | Current certificate vote hash |
| `approval_percentage` | Yes | Canonicalized numeric string in hash payload |
| `decisive_vote_total` | Yes | Non-negative integer |
| `minimum_votes_required` | Yes | Non-negative integer |
| `approved_at` | Yes | Scalar timestamp |
| `originality_score` | Yes | Canonicalized numeric string in hash payload |
| `reward_type` | Yes | Current reward classification |
| `reward_recipient` | Yes | Reward target |
| `reward_amount` | Yes | Canonicalized numeric string in hash payload |
| `reward_source` | Yes | Reward source identifier |
| `minted_at` | Yes | Scalar timestamp |
| `voter_rewards` | Yes | Ordered list, empty list allowed |
| `native_transactions` | Yes | Ordered list, empty list allowed |
| `transaction_ids` | No | Derived convenience list |
| `transaction_count` | No | Derived convenience count |
| `transactions_hash` | No | Included in the consensus payload when present |

## 5. Consensus-hashed fields

The Protocol v1 block hash commits to the canonical domain envelope and to the following payload fields exactly once:

- `block_version`
- `index`
- `previous_hash`
- `timestamp`
- `transactions`
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
- `transactions_hash` when present
- `native_transactions`
- `voter_rewards`
- `meme_text` when `meme.text` is present
- `network_id`, via the canonical domain envelope rather than the payload body

List order is consensus-significant for:

- `transactions`
- `native_transactions`
- `voter_rewards`

## 6. Persisted non-hashed fields

Persisted Protocol v1 block fields that are not themselves hashed are:

- `hash`
- `meme.encoded_image`

`meme.text` is persisted for compatibility, but Protocol v1 hashes the explicit derived `meme_text` value instead of hashing the whole `meme` dictionary.

## 7. Derived/cache-only fields

Fields that are derived, cached, or API-summary-only rather than part of the immutable consensus payload are:

- `transaction_ids`
- `transaction_count`
- API summary fields such as `media_embedded`, `media_size_bytes`, `storage_status`, and `download_url`

These values may be recomputed from authoritative block/content state and do not affect the Protocol v1 block hash.

## 8. Media byte representation

Protocol v1 persists embedded media bytes as the Task 2 canonical bytes object:

```json
{
  "$type": "bytes",
  "$encoding": "hex",
  "$value": "..."
}
```

Rules:

- exact keys: `$type`, `$encoding`, `$value`
- lowercase hexadecimal
- no line wrapping
- reversible with no text decoding
- identical bytes after JSON and SQLite round trips

The canonical serializer now reserves that exact object shape so raw user dictionaries cannot collide with real byte values.

## 9. Content hash rules

For Protocol v1 minted blocks:

- `media_bytes` are authoritative
- `mime_type` is declared metadata used for deterministic validation
- `media_hash` is the SHA-256 hash of the authoritative embedded payload bytes
- `content_hash` is also required to match the same authoritative embedded payload bytes

Hashing rules:

- `text/plain`: decode as UTF-8, normalize with the existing text validator, hash the normalized UTF-8 bytes
- binary MIME types: hash the raw bytes

Validation recomputes the payload hash from `media_bytes` plus the declared `mime_type`, without MIME sniffing, and requires the recomputed hash to match both `media_hash` and `content_hash`.

Before a new originality certificate is issued, the submission is promoted onto a verified canonical content object so new Protocol v1 certificates and blocks use the same accepted-media hash.

## 10. Certificate linkage

Task 4 freezes certificate interpretation without changing the Protocol v1 block field layout.

The block remains bound to the originality decision through:

- `submission_id`
- `certificate_id`
- `content_hash`
- `content_id` when present
- `creator_wallet`
- `vote_hash`
- `approval_percentage`
- `decisive_vote_total`
- `minimum_votes_required`
- `approved_at`
- `originality_score`

Compatibility and validation rules:

- new certificates created through the normal certificate flow are Protocol v1 certificates
- Protocol v1 certificate IDs and vote hashes now come from canonical Task 2 domain-separated payloads
- legacy versionless certificates remain explicit legacy objects with their original IDs
- Protocol v1 blocks may reference either an explicit legacy certificate record or an explicit Protocol v1 certificate record
- block validation dispatches on the actual stored certificate version and never silently reinterprets a legacy certificate ID as Protocol v1

Task 4 does not change the Protocol v1 block payload schema, and the existing Task 3 golden block vectors remain unchanged.

## 11. Native transaction ordering

Task 5 freezes the native-transfer representation used inside Protocol v1 blocks.

Protocol v1 block rules are now:

- `native_transactions` are hashed in persisted order
- transaction order is not rewritten or sorted
- reversing order changes the block hash
- each Protocol v1 native transaction snapshot retains explicit `transaction_version`, `protocol_version`, and `network_id` when present
- Protocol v1 block validation dispatches native transaction checks by explicit transaction version
- versionless legacy native transactions are not eligible for new Protocol v1 block inclusion
- `transaction_ids` and `transaction_count` remain convenience metadata
- `transactions_hash`, when present, is included in the v1 consensus payload

## 12. Timestamp representation

Protocol v1 does not serialize Python `datetime` objects.

Persisted time fields remain scalar timestamps:

- `timestamp`
- `approved_at`
- `minted_at`

For canonical hashing, those scalar numeric values are converted to normalized decimal strings before serialization, so float formatting differences cannot change the block hash.

## 13. Numeric representation

No raw Python floats or `Decimal` objects are allowed into the Protocol v1 canonical payload.

Consensus-critical numeric values are normalized to plain decimal strings with:

- no exponent notation
- no trailing zeroes
- `0` instead of `-0`
- no `NaN`
- no `Infinity`

This applies to values such as:

- `timestamp`
- `approved_at`
- `minted_at`
- transaction amounts/tips when they appear in canonical payloads
- `approval_percentage`
- `originality_score`
- `reward_amount`

## 14. Reward representation

Task 3 preserves the existing reward model.

Protocol v1 hashes the current reward metadata deterministically:

- `reward_type`
- `reward_recipient`
- `reward_amount`
- `reward_source`
- ordered `voter_rewards`

Task 3 also adds a duplicate certified-submission guard so the normal mint path cannot issue the same accepted-media reward twice.

## 15. Block hash calculation

Protocol v1 block hashes are calculated as:

`sha256(block.consensus_payload_v1_bytes())`

where `consensus_payload_v1_bytes()` is the canonical domain envelope produced from the explicit v1 payload helper.

Legacy blocks continue to use the existing legacy hash assembly:

- legacy: `Block.calculate_hash_legacy()`
- Protocol v1: `Block.calculate_hash_v1()`

Legacy blocks are never silently reinterpreted as Protocol v1 blocks.

## 16. Validation rules

Protocol v1 block validation checks:

- explicit `block_version == 1`
- expected `network_id`
- previous-hash linkage
- canonical block hash
- required `media_bytes`
- well-formed `media_hash`
- well-formed `content_hash`
- deterministic `mime_type` and `content_type`
- recomputed embedded-media hash matches both declared hashes
- required certificate metadata and current certificate rules
- existing block/native-transaction validation rules
- unchanged transaction order

Peer receive validation applies the same payload checks before chain acceptance.

## 17. Legacy block compatibility

Legacy compatibility rules are explicit:

- a block without `block_version` is legacy
- legacy blocks continue to verify with the legacy hash function
- loading existing stored legacy chains does not rewrite old block records
- new certified accepted-media blocks use Protocol v1 hashing and embedded media

Do legacy pre-v1 blocks satisfy MODEL A?

`NO`

## 18. Storage behavior

Storage round trips are explicit and deterministic:

- JSON and SQLite persist Protocol v1 blocks through `Block.to_dict()`
- `media_bytes` are stored in the canonical bytes-object form
- reload uses `Block.from_dict()` to restore exact bytes
- export/import includes the persisted chain document, so embedded media survives backup round trips

The auxiliary content store remains useful for caching, indexing, serving, and deduplication, but it is no longer the only immutable copy for Protocol v1 blocks.

## 19. Peer-sync behavior

Protocol v1 peer sync transmits enough block data to validate the full accepted media:

- peer block fetch requests include `include_media_bytes=true`
- Task 6 peer transport authenticates block messages with `message_type = "block"` inside the Protocol v1 peer-message envelope
- received blocks are normalized through `Block.from_dict()`
- receiving nodes validate the embedded media directly from the block payload
- receiving nodes can repopulate the local content cache from the embedded bytes alone
- peer authentication does not bypass block/media/certificate/native-transaction validation

Public list APIs may omit `media_bytes` by default and return summary flags instead, but that is view-layer behavior only.

## 20. MODEL A compliance

For Protocol v1, the full accepted media bytes are part of the immutable persisted blockchain record and are committed to by the block hash.

That means a node can recover the accepted media from `media_bytes` inside the block record even if the auxiliary content cache has been deleted.

Legacy pre-v1 blocks do not satisfy MODEL A.

## 21. Remaining limitations

Task 3 and Task 4 still do not yet freeze or migrate:

- genesis semantics
- finality/lifecycle semantics

Task 6 freezes peer-message transport in [docs/protocol-v1-peer-messages.md](/C:/Users/mattk/ZoidbergChain/docs/protocol-v1-peer-messages.md).

Vote signing and originality certificate identity are frozen in [docs/protocol-v1-originality-and-votes.md](/C:/Users/mattk/ZoidbergChain/docs/protocol-v1-originality-and-votes.md).
Native-transfer signing and tx IDs are frozen in [docs/protocol-v1-native-transfers.md](/C:/Users/mattk/ZoidbergChain/docs/protocol-v1-native-transfers.md).

The legacy direct block-creation path still exists for legacy blocks and should be reviewed in a later lifecycle-hardening task, but it does not mint Protocol v1 accepted-media blocks without certificate-backed metadata.
