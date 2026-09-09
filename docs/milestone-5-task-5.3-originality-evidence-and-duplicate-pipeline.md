# Milestone 5, Task 5.3: originality evidence and duplicate pipeline

## Scope and claims

Task 5.3 adds a versioned pre-vote screen. It does not change reviewer
eligibility, reviewer reputation, quorum, certificate identity/shape, or
collusion analytics. It does not use a semantic model and does not prove global
originality. A result means only that the listed checks, against the canonical
minted-media history at the recorded reference block, produced the listed
evidence.

## Originality Rule v1

`originality.py` is the network-defined source. Rule v1 has a canonical
Protocol v1 JSON representation and SHA-256 digest:

`0be4f10129899a7da07da1fa5d07297b945d71065fc8474bcedb74a55dd497a5`

Unknown versions fail explicitly. No environment variable changes a v1
threshold. The fixed outcomes are `PASS`, `FLAGGED_FOR_REVIEW`, and
`HARD_REJECT`.

- SHA-256 of the complete immutable media bytes is mandatory. An equal hash in
  a prior certified canonical media block is
  `HARD_REJECT / EXACT_MINTED_CONTENT_DUPLICATE`.
- Average hash (`8x8`, 64 bits) flags at Hamming distance 8 or less.
- Difference hash (`9x8` sampling, 64 output bits) flags at Hamming distance 10
  or less.
- Normalized-text set Jaccard similarity flags at 4/5 or greater, provided the
  text has at least 12 characters and three distinct tokens and is not one of
  the rule's fixed generic phrases.
- Perceptual, OCR, and near-duplicate evidence can only flag in v1. No fuzzy
  result can hard-reject.
- A failed or unavailable applicable fuzzy check is recorded and conservatively
  flags review; it is never represented as “no match.”
- Identical pending/unminted submissions are outside this rule. Existing
  pending-submission deduplication remains a separate compatibility concern.

Canonical genesis artwork is not an accepted media submission and is excluded
from the minted-media duplicate corpus. A canonical block enters that corpus
only when it has both a submission ID and certificate ID.

## Media and text normalization

Rule v1 accepts JPEG, PNG, GIF, WebP, and UTF-8 plain text. Pillow decodes image
bytes; only frame zero participates. EXIF orientation is applied before other
processing. Transparent images are converted to RGBA, composited over opaque
white, then converted to RGB. Opaque images are converted directly to RGB.
Color-profile conversion is not performed. ImageHash performs its documented
LANCZOS resizing for the fixed 64-bit average/difference hashes.

OCR receives the same oriented, white-composited RGB image converted to
grayscale, autocontrasted, and thresholded at integer value 160. Tesseract is
invoked with `--psm 11 --oem 1 -l eng`. Text is NFKC-normalized, case-folded,
has every Unicode punctuation character replaced by a space, and has Unicode
whitespace collapsed to single ASCII spaces. Plain text follows the same text
normalization without Tesseract.

The image decode result is `FAILED` on malformed media. OCR distinguishes
`UNAVAILABLE`, `FAILED`, successful empty/non-meaningful output, and successful
meaningful normalized text. Non-image layers are `NOT_APPLICABLE`.

Public Testnet deployments must install the pinned Python packages in
`requirements-originality.txt`. OCR-compatible deployments require Tesseract
5.x and English trained data. OCR output is known to depend on the Tesseract
binary/trained-data build; therefore OCR is prohibited from hard rejection in
v1, its status is explicit, and absent/failed OCR triggers human review. A
future rule that needs stronger cross-platform OCR equivalence must distribute
and identify the executable and trained-data digest.

## Candidate retrieval and scaling

The canonical minted-media feature index stores SHA-256, average hash,
difference hash, normalized-text hash/text, MIME type, height, and block hash.
SQLite records the index head and a digest over ordered records. A head mismatch
or digest mismatch causes a deterministic rebuild from immutable block media.
JSON rebuilds an in-process compatibility index and does not claim equivalent
durable guarantees.

Fuzzy lookup uses a deterministic BK-tree over 64-bit Hamming distance. Records
are inserted and returned in canonical `(hash, height, block hash)` order. This
avoids permanent feature-by-feature scans for image queries. Expected lookup is
sublinear for distributed hashes, with worst-case linear behavior for a
pathological dense corpus. Exact SHA-256 lookup is indexed by SQLite. Rebuild is
linear in canonical minted media and is an optimization recovery operation;
the chain remains the source of truth.

## Evidence and digest

The current document projection contains one evidence record per submission.
SQLite persists immutable revisions in `originality_evidence_records` and
matched prior blocks in `originality_evidence_matches`. A partial unique index
allows one current revision per submission. Reorg-invalidated revisions remain
in history and are marked operationally; their canonical evidence JSON and
digest are not rewritten.

The canonical evidence contains:

- evidence and originality-rule versions plus the rule digest;
- submission ID and full-media SHA-256;
- originality reference height and block hash;
- exact, perceptual, OCR, and near-duplicate statuses/results;
- canonically ordered matched block/content references and integer metrics;
- sorted reason codes and final pre-vote decision; and
- `canonical_evidence_digest`.

The digest is Protocol v1 canonical JSON SHA-256 over every field above except
the digest itself and operational `observed_at`. Candidate lists have explicit
ordering. No local timestamp, mapping iteration order, floating-point value,
filesystem path, OCR raw text, or exception text participates.

## Historical reference and reorg behavior

The reference is captured immediately after submission construction and content
resolution, before voting, using the then-current canonical tip. Later chain
growth does not mutate that record. Before a vote or certificate operation, the
reference is checked against the block at its recorded height.

Canonical-chain adoption removes only evidence whose exact height/hash pair is
no longer canonical. SQLite marks the old revision reorg-invalidated. Before
the reorg operation returns, each affected unminted submission is recomputed
against the winning chain and persisted. If a stale-fork exact match disappears,
the submission returns to `pending`; if a new exact match appears, it becomes
hard-rejected. Finality rules continue to prohibit detaching finalized history.

## Lifecycle and API

New local and peer submissions are screened before their creation operation is
acknowledged. Legacy records without evidence are screened on their first vote,
evaluation, or certificate attempt. A hard reject moves to `hard_rejected`, is
removed from the mint queue, cannot vote, and cannot receive a certificate.
`PASS` and `FLAGGED_FOR_REVIEW` remain pending and can vote under unchanged
Task 5.2 reviewer/quorum compatibility behavior.

`GET /submissions/{submission_id}/originality-evidence` is a public read-only
route. Submission responses also include an evidence summary. Full evidence
exposes matched canonical block hashes/heights, content hashes, and metrics but
never local paths or executable details. The legacy evaluation boolean cannot
override a canonical hard reject; `false` remains a conservative compatibility
rejection input.

## Migration and storage guarantees

SQLite startup idempotently creates evidence, match, index, and index-metadata
tables. Existing Task 5.2 reviewer/vote rows and all document sections are
preserved. Existing submissions are not assigned fabricated historical
evidence; they are evaluated before the next voting/certificate transition.

JSON stores the current evidence projection and validates its digest/reference,
but it has no relational immutable revision history, uniqueness constraint, or
durable feature index. Public Testnet v1 nodes requiring Task 5.3 durability
must use SQLite.

## Focused adversarial corpus observations

Run `python scripts/task_5_3_adversarial_corpus.py`. The controlled corpus is
small and diagnostic, not a threshold-justification corpus.

| Layer | TP | TN | FP | FN |
| --- | ---: | ---: | ---: | ---: |
| Exact hard reject | 3 | 15 | 0 | 0 |
| Fuzzy review flag | 8 | 4 | 2 | 1 |

JPEG recompression, resize, small crop, brightness/color changes,
metadata-only changes, same normalized text across different visuals, and an
OCR-preserving edit flagged. A border-added variant was the fuzzy false
negative. Same-template materially different text and a posterized meaningful
derivative were intentionally counted as fuzzy false positives because they
still crossed visual thresholds. Generic phrases on unrelated imagery and the
no-text unrelated case did not flag. These borderline results are why v1
forbids fuzzy hard rejection; thresholds were not tuned to make this corpus
perfect.

## Remaining risks and Task 5.4 input

- Pillow decoder/ImageHash behavior must be tested against the exact pinned
  deployment wheels on every supported platform.
- Tesseract/trained-data builds are not yet content-addressed.
- BK-tree worst-case lookup is linear, and rebuild is linear by design.
- Remote peer submissions can record unavailable fuzzy layers until full media
  is locally present; reviewers can see that incomplete state.
- Task 5.4 should bind the evidence digest, rule version, and reference into the
  next certificate version and reject legacy/unverifiable evidence explicitly.
  It must not promote current fuzzy thresholds to hard-reject rules.
