# Milestone 5, Task 5.4: certificate evidence binding and peer validation

Task 5.4 introduces originality certificate version 2. It binds the complete,
immutable Task 5.3 originality evidence record without activating earned
reviewer eligibility, probation, reputation penalties, the established-reviewer
quorum, or collusion analysis.

## Version strategy

Certificate interpretation is selected by `certificate_version`:

- absent: legacy certificate and legacy SHA-256 identity;
- `1`: frozen Protocol v1 certificate identity and validation;
- `2`: Milestone 5 evidence-bound certificate identity and validation.

Legacy and version-1 records are not rewritten, backfilled, or reinterpreted.
New certificates issued through the blockchain service use version 2. The lower
level constructor retains version 1 as its default so historical callers and
literal Protocol v1 vectors keep their original meaning.

## Version-2 schema

The canonical identity payload contains:

- `certificate_version`, `protocol_version`, and `network_id`;
- `submission_id`, `content_hash`, and `creator_address`;
- `originality_rule_version`, `originality_decision`,
  `originality_reference_height`, `originality_reference_block_hash`, and
  `originality_evidence_digest`;
- `minimum_valid_votes`, `approval_threshold_bps`, `total_valid_votes`,
  `original_votes`, `not_original_votes`, `unsure_votes`, and `vote_set_hash`;
- `certificate_reference_height`, `certificate_reference_block_hash`, and
  canonical decimal-string `issued_timestamp`;
- the existing deterministic `originality_score`;
- explicit nulls for `reviewer_policy_version`, `reputation_rule_version`,
  `reviewer_snapshot_reference_height`,
  `reviewer_snapshot_reference_block_hash`, `reviewer_snapshot_digest`,
  `minimum_established_votes`, and `established_vote_count`.

The null reviewer fields mean only “not activated in certificate version 2.”
They are part of the canonical payload and must all remain null. Tasks 5.5/5.6
must introduce a later certificate version before making those values mandatory;
they must not partially populate version 2.

Compatibility aliases remain in the serialized record (`creator_wallet`,
`vote_hash`, `vote_total`, `minimum_votes_required`, and floating-point
`approval_threshold`). Validation requires each alias to equal its canonical
version-2 field. `evidence_binding_status` is operational lifecycle state and is
not hashed; only `active` records validate. It cannot change the immutable
binding, and peer input cannot import an invalidated status as active evidence.

## Canonical identity

Version 2 uses the existing canonical protocol envelope and SHA-256 domain hash
for `originality_certificate`, with explicit certificate-version separation.
The identity builder normalizes the network and creator identities, lowercase
SHA-256 values, non-negative integers, and decimal strings. Threshold consensus
uses integer basis points (`7000` for the current 70% rule), never a platform
float. Dictionary insertion order, filesystem paths, local clocks, and local
runtime paths do not affect the result.

`issued_timestamp` is required because the locked certificate schema requires
it. Issuance derives it from the already canonical certificate-reference block
timestamp, rather than sampling a new local clock. Literal version-2 payload and
certificate-ID vectors protect this behavior.

## Evidence binding and validation

Issuance first promotes recoverable content to the Protocol v1 raw-byte content
identity, then obtains current certificate-profile evidence. It refuses missing,
malformed, unsupported, hard-rejected, or non-canonical evidence. The
certificate copies and hashes the exact rule version, decision, evidence digest,
and originality reference.

Validation does not trust stored booleans. It checks the certificate ID,
protocol/network, submission/content/creator aliases, integer threshold aliases,
vote totals, vote-set hash, current threshold behavior, originality score,
certificate reference, evidence reference, Rule v1 digest, evidence canonical
digest, media SHA-256, candidate schema/order, matched historical block
references, all exact/fuzzy results, reason codes, and final decision. It
recomputes the entire certificate-profile evidence record against the canonical
chain prefix ending at the committed originality reference. Specific matched
blocks remain only in that evidence record and are transitively committed by its
digest.

## Fuzzy-runtime portability decision

Certificate evidence uses the deterministic profile
`milestone-5-certificate-consensus-v1`:

- Pillow is required at exactly `12.3.0`;
- ImageHash is required at exactly `4.3.1`;
- image preprocessing, 64-bit average hash, and 64-bit difference hash are
  recomputed by every validator;
- Tesseract is never executed for this certificate profile;
- image OCR is canonically recorded as `UNAVAILABLE` with empty normalized text,
  producing the existing conservative `FUZZY_CHECK_INCOMPLETE` review flag.

A node with missing or different Pillow/ImageHash packages fails initialization
of the certificate consensus pipeline and cannot issue or validate Rule-v1 bound
evidence. Tesseract executable, trained-data, `TESSDATA_PREFIX`, and executable
path differences cannot affect version-2 evidence or validity. Tesseract remains
available only to non-consensus/advisory tooling. This retains the complete
evidence commitment: the canonical unavailable OCR result and runtime identity
are themselves inside the immutable evidence digest. Exact duplicates remain
the only automated hard reject; fuzzy results remain review-only.

This is intentionally conservative. A later rule that wants consensus OCR must
content-address the executable, language data, and preprocessing runtime, then
use a new originality-rule/certificate version.

## Peer transfer and revalidation

Authenticated peer traffic adds:

- `POST /peers/originality-evidence/receive` for an evidence record, canonical
  media bytes, and MIME type;
- `GET /peers/originality-evidence/{evidence_digest}` for explicit retrieval;
- `originality_evidence` transfer entries in chain-sync responses.

Version-2 certificate and certified-block broadcasts send evidence first, then
the certificate, then the block. Submission broadcasts include evidence/media
when available. Chain sync stores and revalidates evidence before certificates
and validates certificates before adopting the candidate chain.

The transfer also carries the related submission and vote set so a node learning
about certified content through a block can establish every prerequisite. The
receiver authenticates the peer with the existing peer controls, validates the
submission and historical/versioned vote shapes, validates the evidence
schema/digest and rule version, verifies media bytes, proves either the current
raw-media hash or the historical composite submission hash, rebuilds the
canonical chain-prefix index, recomputes the complete evidence record, and only
then persists it. The subsequently received certificate independently recomputes
the vote-set hash. An identical evidence digest is idempotent. A current evidence
revision already bound to an active certificate cannot be replaced. Unsupported,
malformed, mismatched, or non-canonical evidence fails deterministically.

## Missing media

Media bytes are mandatory for version-2 validation. A remote reference,
peer-provided certificate, or locally stored evidence record is insufficient by
itself. Broadcast and chain sync carry canonical bytes; retrieval fails if the
serving node cannot recover them. The receiving node stores verified bytes under
their SHA-256 content identity before accepting the certificate. Missing bytes
therefore block certification/validation and can never be interpreted as a clean
fuzzy result.

## Reorg behavior

Both the originality reference and certificate reference must remain canonical.
The existing canonical reorg service removes detached current evidence and marks
dependent version-2 certificates `invalidated_by_reorg`. For an unminted
submission it clears the certificate link, removes queued mint work, returns an
approved/queued submission to pending, and deterministically recomputes evidence
at the new head. The old certificate remains historical but cannot validate
against the replacement digest. Existing finality rules still decide whether a
candidate branch may detach finalized history; Task 5.4 adds no fork-choice or
finality rule.

## Persistence and migration

SQLite adds `originality_certificate_evidence_bindings`, keyed by certificate
ID, with immutable submission/content/evidence/originality-reference and
certificate-reference columns plus mutable binding status. Its supporting
submission/status index and table creation use `IF NOT EXISTS`, so upgrade from a
Task 5.3 database and repeated startup are idempotent. Existing certificate JSON
records remain authoritative compatibility input and legacy rows are retained.

Task 5.3 evidence history stays immutable. A pre-certificate raw-content
promotion may replace the current projection while preserving the old row as a
non-current, non-reorg revision, but only while no active version-2 certificate
binds the old digest. Once bound, the relationship cannot be replaced.
The JSON-to-SQLite migration now carries `originality_evidence` alongside
certificates, preventing an active version-2 binding from being separated from
its required evidence during backend conversion. Backup, portable export, and
import state sections likewise include originality evidence, so their
round-trips retain the certificate's validation prerequisite.

## Compatibility regression found during verification

The pre-Task-5.4 long-chain benchmark assumed that registering a certificate's
generic remote content reference could safely rewrite an existing content MIME
type. That was false once certificate validation required the locally verified
media a second time: a verified `text/plain` payload was changed to
`application/octet-stream`, so lookup used the wrong file extension and
reported the media as missing. Peer certificate receipt now preserves the MIME
type of an existing content object in both the chain-sync store and public peer
wrapper. This does not relax missing-media validation; it prevents verified
media metadata from being destroyed between two mandatory validations.

## API visibility

Existing certificate/submission reads expose the version-2 fields. Certificate
serialization also reports `originality_evidence_retrievable`, allowing clients
to distinguish a commitment from currently retrievable evidence. Matched prior
blocks remain available through the existing submission evidence read and the
authenticated peer evidence retrieval route; they are not duplicated into the
certificate.

## Remaining risks and later-task boundary

- Pillow and ImageHash upgrades are protocol migrations, not routine dependency
  bumps, while Rule v1/version 2 remains active.
- Consensus OCR is deliberately disabled, reducing fuzzy recall until a
  content-addressed OCR rule is designed.
- Version 2 retains the current minimum-vote/percentage behavior. It makes no
  claim about established reviewer counts.
- Task 5.5 must consume a canonical reviewer snapshot and introduce a later
  certificate version rather than assigning meaning to version-2 nulls.
- Operational peer availability still affects when evidence/media arrives, but
  never whether incomplete data is accepted as valid.
