# Task 11.5c: Bitcoin-Style Block Size Limit

## Summary

ZoidbergChain beta now adopts a Bitcoin-style hard serialized block ceiling:

- `MAX_BLOCK_SIZE_BYTES = 1_000_000`
- `MAX_CANONICAL_CONTENT_BYTES = 600_000`

These are protocol rules, not UI-only checks. A block larger than `MAX_BLOCK_SIZE_BYTES` is invalid everywhere, including minting and validation.

## Beta Content Model

For beta, each accepted submission must fit into a single block.

- Compression and canonicalization happen before hashing and before minting.
- The block stores canonical compressed content, not the original upload bytes.
- `content_hash` is the SHA-256 of the canonical compressed bytes embedded in the block.
- `original_content_hash` is the SHA-256 of the original uploaded bytes, when original bytes are available.

Each block now carries:

- `encoded_content`
- `compression_algorithm`
- `compression_version`
- `canonical_size_bytes`
- `original_size_bytes`
- `mime_type`
- `content_hash`
- `original_content_hash`

## Validation Rules

Validation now rejects blocks when any of the following is true:

- Serialized block size exceeds `1,000,000` bytes.
- Embedded canonical content exceeds `MAX_CANONICAL_CONTENT_BYTES`.
- Embedded content cannot be base64-decoded.
- Embedded canonical bytes do not match `canonical_size_bytes`.
- Recomputed SHA-256 of canonical bytes does not match `content_hash`.
- Recomputed SHA-256 of decompressed original bytes does not match `original_content_hash`.
- A legacy or non-canonical minting path is used without explicit migration.

This makes the chain itself the ground-truth record for what content was actually minted.

## Tradeoff

This beta rule intentionally favors decentralization and integrity over large media support today.

The upside:

- Smaller blocks are easier for future nodes to validate and replicate.
- The serialized chain remains the authoritative record.
- Validation is deterministic across minting and replay.

The cost:

- Some larger media will be rejected during beta.
- Passing the canonical content limit alone is not enough; the full serialized block must still fit under `MAX_BLOCK_SIZE_BYTES`.

## User Experience

If content cannot be compressed into a single safe block, minting should fail with a clear user-facing error. Multi-block media is not implemented yet.

## Future Strategy

Audio and video will likely require a later protocol strategy such as:

- content chunking
- Merkle-root commitments
- multi-block content manifests
- a specialized media layer

That work is intentionally deferred until after the beta chain rules are stable.
