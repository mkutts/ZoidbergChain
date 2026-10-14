# Milestone 6 Task 6.9 — Model A byte integrity and reconstruction

Status: implemented on `Immutable-Media-Safety-and-Admission`
Scope: Public Testnet v1 current media blocks; no Task 6.10 frontend redesign

## Non-negotiable invariant

**THE BLOCKCHAIN STORED MEDIA BYTES ARE GROUND TRUTH.**

Given a finalized current media block, a conforming node can reconstruct the
exact accepted byte sequence from that block alone and verify every
media-integrity binding without an upload file, content cache, mutable
submission record, frontend flag, or database alias.

**TWO FILES THAT LOOK IDENTICAL BUT DIFFER BY ONE BYTE ARE DIFFERENT MEDIA FOR
INTEGRITY PURPOSES.**

Perceptual hashes, OCR, rendering equivalence, metadata-insensitive comparison,
and semantic/AI similarity are not Model A integrity rules.

## Versioned contract

| Item | Public Testnet v1 rule |
| --- | --- |
| Integrity contract | `zoidberg-public-testnet-v1/model-a-byte-integrity/1` |
| Contract version | `1` |
| Current block versions | embedded-media block `1`; admission block `2` |
| Hash algorithm | SHA-256 |
| Hash input | the exact accepted bytes embedded in `media_bytes` |
| Binary accepted bytes | the exact image upload bytes approved by Task 6.3 |
| Text accepted bytes | Task 6.3 canonical UTF-8: CRLF/CR → LF, then outer whitespace trim |
| Media length | `len(media_bytes)`; exactly derivable from the hash-committed payload |
| Media type | hash-committed `mime_type`; no filename inference during reconstruction |
| Media hash | `sha256(media_bytes)` |
| Content hash | intentionally equal to `media_hash` for current Model A media |

`media_hash` names the immutable block payload role. `content_hash` preserves
the submission/content/certificate identity used by the existing protocol.
They intentionally duplicate one SHA-256 value for current media blocks, and
verification requires both to equal the digest of the embedded bytes.

No new consensus field or block version was required. Adding a persisted length
or integrity-version field would change historical hashes. Length is already
unambiguous because the complete byte value is in the canonical hash input.
Unknown current media block versions fail closed.

## Accepted-byte source and admission binding

Task 6.3 returns `ValidatedMedia.raw_media_bytes`:

- JPEG/PNG/GIF/WebP: unchanged accepted upload bytes;
- `text/plain`: canonical Task 6.3 UTF-8 bytes.

The same bytes are stored in the content-addressed admission cache, bound by
`technical_evidence.raw_media_sha256` and
`technical_evidence.raw_media_byte_length`, signed by the Task 6.4 submitter
attestation, frozen into the Task 6.6 admission certificate, and passed to block
construction. No decode/re-save, metadata removal, resize, recompression, or
transcoding occurs.

For admission block version 2, independent verification checks:

1. exact certificate schema/version/network/policy identities;
2. certificate digest;
3. SHA-256 of the embedded bytes equals certificate `content_hash`;
4. technical-evidence digest, byte length, and SHA-256 identify the same bytes;
5. submitter attestation identifies the same submission/hash/evidence and has a
   valid signature;
6. frozen dual-review votes and certificate tallies are canonical and signed;
7. block `submission_id`, `certificate_id`, and `content_hash` match the
   certificate.

Normal node validation additionally resolves reviewer snapshots against the
canonical chain. The standalone verifier can recheck the frozen certificate's
internal snapshot consistency without consulting mutable submission state.

## Block and block-hash binding

`media_bytes` are serialized as the canonical bytes object:

```json
{"$type":"bytes","$encoding":"hex","$value":"lowercase hex"}
```

The full byte value, `media_hash`, `content_hash`, `mime_type`, `content_type`,
submission/certificate identities, and the complete version-2 admission
certificate are in `Block.consensus_payload_v1()`. The block hash is SHA-256 of
the canonical, domain-separated block envelope. Replacing bytes while retaining
the digest fails the direct SHA-256 check and the block hash. Replacing bytes
and digests fails certificate/technical-evidence bindings. Replacing all those
bindings still changes the block hash and finalized identity.

Text block validation now explicitly requires that embedded bytes already equal
the Task 6.3 canonical byte sequence. It does not accept noncanonical text merely
because re-canonicalizing it produces a declared digest.

## Independent verification and reconstruction

`media_integrity.verify_media_block(block)` performs deterministic verification
from immutable block data. `Blockchain.verify_block_media_integrity(...)` adds
canonical-chain and optional finality checks. The result is computed; no
mutable “mark verified” field exists.

Strict reconstruction is available through
`Blockchain.reconstruct_immutable_media(...)` using exactly one of:

- block hash;
- block height;
- submission ID linked to its minted block.

It verifies the block before returning `bytes`. It never reads an upload path,
content object, or cache. `recover_block_media_bytes` retains its historical
cache fallback only for legacy compatibility and is not the Task 6.9 path.

Writing reconstructed bytes to disk, if an operator chooses to do so, must use
binary mode and an extension derived only from the block-bound MIME type. The
bytes must be rehashed after writing. Local paths and original filenames are not
protocol identity.

## Storage, restart, migration, and export

JSON and SQLite both persist the chain's canonical lowercase-hex bytes object.
JSON parsing and SQLite section parsing preserve it losslessly; malformed hex,
odd-length hex, truncation, altered bytes, or altered digests fail current-media
verification.

Portable export/backup verifies every current media record before producing a
snapshot. Import verifies current media before writing the target. JSON→SQLite
migration verifies both source and migrated records. Portable export/import is
the supported SQLite→JSON and cross-backend path. Exact media bytes, media hash,
block hash, certificate digest, and finalized identity survive these paths.

Node restart reconstructs blocks with `Block.from_dict` and validates the full
chain. Media are not regenerated from submissions. Corrupt current media makes
startup fail closed.

## Peer transport and chain sync

Peer JSON carries the canonical bytes object; arbitrary binary data is never
Unicode-decoded. Decoding requires exact keys, the `hex` encoding marker,
lowercase hex, and an even-length value. Peer chain fetches request
`include_media_bytes=true`.

Block receive, gossip, bootstrap fetch, candidate-chain comparison, chain
replacement, and reorg validation all run block hash/media/certificate checks
before acceptance. Retransmission serializes the exact same byte sequence.
Malformed transport encoding and any digest or byte alteration fail closed.

## API

Public block summaries expose block height/hash, submission ID, media hash,
content hash, MIME type, derived media length, integrity-contract version,
SHA-256 identity, finality/canonical state, and the exact media download path.

`GET /blocks/{block_hash}/media` verifies the immutable block and returns the
exact bytes for both images and text. It does not use a text decode/re-encode
path. Response headers include the block hash, media SHA-256, and computed
integrity result. Verification failure returns a conflict response.

## Overlay immutability

Task 6.7 reports, Task 6.8 disputes, presentation flags, reputation, and API
status are additive state outside the block consensus payload. Adding or
reordering those observations cannot change `media_bytes`, `media_hash`, or the
block hash. Verification reads the block, not those overlays.

## Tamper behavior

Focused tests reject one-bit flips, truncation, append, byte reorder, media
swap, noncanonical text, media-hash-only changes, content-hash-only changes,
certificate hash changes, technical digest/length changes, malformed hex, peer
alteration, and corrupted import/migration snapshots. Recompression,
transcoding, image metadata edits, and container changes necessarily change at
least one byte and therefore follow the same deterministic failure rule.

## Legacy compatibility and performance

Historical blocks are not rewritten and historical hashes are unchanged.
Version-1 embedded-media blocks retain their external originality-certificate
semantics but receive exact byte/hash/block-hash checks. Legacy blocks without a
current `block_version` remain readable and are not falsely upgraded to the
Task 6.9 contract.

Normal status, report, dispute, and unrelated storage operations do not scan or
rehash the chain. Hashing occurs at block acceptance/validation, explicit
integrity verification or download, startup validation, export/import, and
migration. The verifier hashes a media payload once. There is no whole-chain
media rescan for ordinary API status or overlay updates.

## Compatibility implications

- no block reset or historical rehash;
- no storage schema migration;
- no off-chain ground-truth dependency;
- existing content caches remain optional presentation/performance aids;
- current malformed/noncanonical media that never satisfied the documented
  contract now fail earlier at verification/import boundaries.

