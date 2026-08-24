# Protocol Content And Consensus

## Summary

ZoidbergChain beta now treats the blockchain as the ground truth for accepted content and originality decisions.

- Accepted content is stored on-chain inside the minted block.
- Off-chain content storage under `content/` is only a cache and convenience copy.
- Nodes must be able to validate accepted content from the block itself.
- Beta blocks use a hard serialized size ceiling of `1,000,000` bytes.

## Canonical Content Pipeline

The canonical pipeline is:

1. upload file or text
2. validate content type and size
3. canonicalize or compress into deterministic canonical bytes
4. compute `content_hash = SHA-256(canonical bytes)`
5. compute `original_content_hash = SHA-256(original uploaded bytes)` when original bytes are available
6. embed canonical content bytes in the minted block
7. validate blocks by recomputing the canonical hash from embedded content

For beta:

- Images and text are supported.
- Audio and video are not fully implemented yet.
- One accepted submission must fit into one block.

## Content Hash Definitions

- `content_hash`
  - SHA-256 of the exact canonical compressed bytes embedded in the block.
- `original_content_hash`
  - SHA-256 of the original uploaded bytes before canonical compression, when available.

New mintable content does not use the old legacy submission-derived hash model.

## Canonical Content Metadata

Minted blocks include canonical content metadata such as:

- `content_id`
- `content_hash`
- `original_content_hash`
- `content_type`
- `mime_type`
- `original_size_bytes`
- `canonical_size_bytes`
- `compression_algorithm`
- `compression_version`
- `encoded_content`
- `submission_id`
- `certificate_id`
- `creator_wallet`
- `vote_hash`
- `approval_percentage`
- `decisive_vote_total`
- `minimum_votes_required`
- `minimum_decisive_votes_required`
- `approved_at`
- `originality_score`

## Compression And Canonicalization

Beta canonicalization is deterministic.

- Binary content is canonicalized with deterministic gzip output.
- Compression metadata is stored in the block.
- The same accepted input and settings must produce the same canonical bytes.
- Text content uses deterministic byte encoding and deterministic canonical hashing.

Nodes must not rely on frontend-only compression or non-deterministic codecs.

## Size Limits

Current protocol limits:

- `MAX_BLOCK_SIZE_BYTES = 1_000_000`
- `MAX_CANONICAL_CONTENT_BYTES = 600_000`

Related limits are also centralized in config, including:

- original upload limits
- text content limits
- transaction-per-block limits

Why canonical content is smaller than the block limit:

- Binary data is embedded in JSON using base64.
- Block metadata, transactions, rewards, and certificate fields also consume serialized bytes.
- A canonical payload that fits its own limit can still be rejected if the final serialized block exceeds `1,000,000` bytes.

## Validation Rules

Nodes reject a block when:

- serialized block size exceeds `MAX_BLOCK_SIZE_BYTES`
- canonical embedded content exceeds `MAX_CANONICAL_CONTENT_BYTES`
- embedded content is malformed
- decoded canonical content length does not match `canonical_size_bytes`
- canonical bytes do not hash to `content_hash`
- decompressed original bytes do not hash to `original_content_hash`
- submission or certificate references are inconsistent
- minting lacks a valid originality certificate
- legacy non-canonical content attempts to mint without migration

This lets nodes validate accepted content from the block itself without trusting the off-chain cache.

## Strict Consensus

ZoidbergChain beta now uses decisive-vote quorum.

- `decisive_vote_total = original_votes + not_original_votes`
- `unsure_votes` are recorded but do not count toward quorum or finalization
- `required_decisive_votes = max(5, ceil(active_users_7d * 0.05))`
- `approval_percentage = original_votes / decisive_vote_total`
- approve only if:
  - `decisive_vote_total >= required_decisive_votes`
  - `approval_percentage >= 0.70`
- reject only after decisive quorum exists and approval is below threshold

Examples:

- `3 ORIGINAL + 0 NOT_ORIGINAL + 2 UNSURE` does not finalize if decisive quorum is 5.
- `4 ORIGINAL + 1 NOT_ORIGINAL` approves at 80%.
- `3 ORIGINAL + 2 NOT_ORIGINAL` rejects at 60%.

The voting window no longer allows `UNSURE` votes to finalize a submission by themselves.

## Existing Voting Rules Kept

These rules still apply:

- creators cannot vote on their own submissions
- one wallet cannot vote twice
- votes cannot be changed
- minting requires a valid originality certificate
- duplicate, hard-rejected, or otherwise invalid submissions cannot mint

## Legacy Content Policy

For pre-beta hardening:

- new submissions must use canonical upload-first content hashing
- legacy direct image content must not mint unless it is represented under the canonical content model
- off-chain legacy data should be migrated or reset before wider beta if needed

ZoidbergChain should not keep two active minting hash standards for new accepted content.

## Future Media Strategy

Larger media will likely require later protocol work such as:

- chunking
- Merkle-root commitments
- multi-block manifests
- specialized media compression
- a dedicated media layer

That work is intentionally deferred during beta so the chain rules stay simple, deterministic, and easier to validate.
