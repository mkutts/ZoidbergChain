# Milestone 5, Task 5.1: Current-state audit

Audit date: 2026-09-08.  This is an inspection and implementation-planning
artifact only; it makes no protocol change.

## Repository verification

| Check | Result |
| --- | --- |
| Current branch | `Proof-of-Originality-Security-and-Reviewer-Reputation` |
| HEAD | `9d7c1825048065b0446e70d86b90404821bcb6bc` (`task 4.10 done`) |
| Initial worktree | clean (`git status --short` produced no output) |
| Milestone 4 base | merged: `origin/Native-Transactions-Durable-Mempool-and-Reorg-Recovery`, its local branch, `main`, and this branch all resolve to `9d7c182` |
| Unrelated/uncommitted changes before audit | none |

The equal commit tips are direct repository evidence that the named Milestone 4
branch has been merged into this Milestone 5 base.  The only expected change at
the end of this task is this audit document.

## Current architecture and lifecycle

`Blockchain` remains the facade/aggregate owner.  It holds in-memory state,
loads/saves through `StorageBackend`, and delegates pieces of the lifecycle to
services.  JSON storage persists whole named sections atomically; SQLite also
stores those same sections as JSON in `storage_sections` (native transactions
are the notable relational exception introduced by Milestone 4).

| Transition | Current authoritative owner | Notes |
| --- | --- | --- |
| Upload content | `ContentCoordinationService.upload_binary_content` / `upload_text_content`, public `/content/*` routes | Calculates a payload/content hash and local cache metadata. |
| Create submission | `Blockchain.submit_*_content_operation` -> `ContentCoordinationService.submit_content` or `Blockchain.submit_existing_content` | Appends `Submission` in `pending`. |
| Automated originality | `Blockchain.evaluate_submission` -> `ContentCoordinationService.is_meme_original` | Not invoked at upload/submission time; evaluate endpoint may also supply an override boolean. |
| Eligibility gate | `/auth/wallet/vote-challenge` and vote route helpers | API-local `review_policy.py` plus access controls; not part of peer/block validation. |
| Signed vote | `WalletAuthManager.verify_vote_signature` -> `Blockchain.cast_signed_submission_vote_operation` -> `SubmissionOriginalityService.cast_submission_vote` | Challenge verification precedes appending the vote. |
| Tally / decision | `SubmissionOriginalityService.get_submission_votes`; `Blockchain.evaluate_submission` | `UNSURE` is excluded from decisive denominator. |
| Certificate | `OriginalityCertificate.from_approved_submission`, stored in `originality_certificates` | Created while pending, then submission moves to `approved`. |
| Mint queue / block | `MintQueueService` and `BlockProductionService` | A certificate is required for a Protocol v1 certified block. |
| Finality | `FinalityService` plus persisted attestation/finalized-block evidence | Confirmation/finality depth and validator quorum are separate from originality voting. |

The public evaluation and mint routes are rate-limited but are not admin-only;
development-only repair/reset/mint-block controls are separated in operations
routes.  Peer routes accept submission, vote, and certificate replication, but
do not turn the review policy into a consensus rule.

## A. Duplicate and originality pipeline

### What exists

* Binary upload uses `content.resolve_payload_hash` and persists a content hash,
  byte hash, MIME type, size and local content-cache record.  Signed submission
  references an already-uploaded `content_hash`/`content_id`; legacy
  `Submission.calculate_submission_content_hash` instead hashes file bytes,
  normalized supplied text, **and submitter**, so it is not a media-only
  identity.
* `utils.hash_image` opens media with Pillow and returns
  `str(imagehash.average_hash(img))`.  `ContentCoordinationService.is_image_unique`
  caches that value in process memory (`image_hashes`/`image_validation_cache`).
* `utils.extract_text` calls `pytesseract.image_to_string(..., config="--psm 11")`
  and normalizes whitespace, strips non-word characters, and returns the text.
  It is used by the legacy direct-image submission route only when no text was
  supplied.  `is_text_unique` lowercases, removes punctuation, and compares an
  in-memory `texts` list.
* `is_meme_original` performs exact equality of the average hash against only
  the in-memory cache, then calls text uniqueness.  There is no similarity
  score, Hamming-distance threshold, image crop/recompression handling, OCR
  comparison against historical records, or result category beyond boolean.
* Block production contains another legacy duplicate guard that compares image
  hash/text data while building a candidate.  It is not a pre-vote, durable
  originality pipeline and does not produce evidence.

### Scope, timing, determinism, persistence

The cache is populated by calls to `is_image_unique`/`is_text_unique`; a normal
submission merely persists the file/content object and does not register that
submission in those caches.  `evaluate_submission` calls `is_meme_original`
only when the caller did not pass `automated_originality_passed`.  Accordingly,
comparison is neither reliably against pending submissions nor reliably
against minted blocks; it is against current-process cache state.  A restart,
peer, or historical revalidation cannot reproduce a result.

Pillow decoding, ImageHash version/implementation, Tesseract executable,
language data and OCR output are node-environment dependent.  The code catches
OCR errors and returns `None`, while image hashing raises a generic input error.
Neither tool version nor normalized OCR input/output, perceptual hash, match
reference, threshold, algorithm/rule version, or decision evidence is stored.

### Required Milestone 5 gap

There is no required layered `PASS` / `FLAGGED_FOR_REVIEW` / `HARD_REJECT`
pipeline.  Exact cryptographic duplicates of minted media are not rejected
before voting.  Fuzzy matches cannot be shown to reviewers with historical
block references, and no adversarial corpus exists to justify a fuzzy
hard-reject threshold.  Historical originality decisions are not reproducible.

## B/C. Vote integrity and current tally

The core service prohibits a creator from voting (`voter == submission.submitter`),
checks a valid choice, forbids votes after an approved/queued/rejected/hard-
rejected/minted status or certificate, and finds an existing
`(submission_id, voter)` record before adding another.  That is application
logic only: JSON sections have no constraints, and SQLite has no relational
vote table or unique vote index.  A concurrent or malformed storage/peer write
can therefore bypass the intended one-wallet-one-vote invariant.

Signed API votes use a MetaMask `personal_sign` challenge.  Protocol v1's
canonical payload commits to `vote_version`, submission/content identity,
wallet, choice, nonce, issued and expiry timestamps, network ID/domain and
protocol version.  The verifier recovers the 0x wallet and checks all of those
bindings.  It marks an **in-memory** challenge used before a vote is stored;
challenges are pruned by local wall clock.  Challenge nonce/replay state is not
durable, is not replicated, and is not a database constraint.  A duplicate
vote is usually rejected by the one-voter check, but the system neither stores
an immutable vote ID/payload hash uniqueness rule nor records/evidences a
conflicting signed vote.  Identical retransmission is rejected as an already
cast vote rather than accepted idempotently.

The API has configured `RATE_LIMIT_VOTE` support, but rate limiting is a local
operational control.  Error mapping is generally 400 (404 for absent
submission; 401 for used/expired challenge).  Peer ingestion validates the
message path but cannot make local policy, nonce cache, and JSON persistence a
deterministic consensus admission rule.

Votes have numerical weight one in the tally today, but only incidentally:
there is no reviewer status/weight model at all.  `original`, `not_original`,
and `unsure` are counted; decisive total is original plus not-original;
approval is Python float division `original / decisive`, or zero.  `UNSURE`
does count toward `vote_total` and minimum-vote reach, but not the approval
denominator or current score.  There is no established-reviewer sub-quorum.

## D/E. Reviewer eligibility and active-user quorum

`review_policy.py` supports four modes: `open`, `allowlist`, `activity`, and
`hybrid`; denylist always wins.  `allowlist` requires an environment allowlist;
`activity` accepts when **any one** enabled threshold is met; `hybrid` accepts
either.  Persistent admin allowlist records in `allowlist_entries` can provide
a review/voting override, but regular policy allow/deny lists come from env.

| Eligibility input | Classification | Determinism concern |
| --- | --- | --- |
| Submission/vote/reward counts, settled transfers/balance | canonical-ish chain plus local submission/vote/reward state | Not a single canonical chain-state calculation; submissions/votes/rewards can differ across nodes. |
| `REVIEW_ELIGIBILITY_MODE`, allow/deny lists, thresholds, public label | node-local environment configuration | Two honest nodes can admit different reviewers. |
| Persistent admin allowlist/access-account state and override expiry | node-local persisted administrative state | Not chain committed or peer-consensus replicated; expiry uses wall time. |
| Account age, daily vote limit/current 24-hour window | wall-clock/local observation | Clock and local vote history cause disagreement. |
| Access-session and access-control checks | node-local auth/admin state | An API gate, not consensus state. |

The activity summary takes earliest local submission/vote/reward/transaction
timestamp, counts local records, uses current `time.time()` for age, and reads
the local native balance snapshot.  It has no `NEW -> PROBATIONARY ->
ESTABLISHED -> COOLDOWN/SUSPENDED` model.  Existing access-account suspension,
revocation, wallet binding and denylist/allowlist mechanics are beta access
controls, not deterministic reviewer reputation.

The dynamic quorum is `max(MIN_VOTE_FLOOR, ceil(active_users *
ACTIVE_USER_PERCENT_FOR_MIN_VOTES))`; current defaults are lookback 7 days,
floor 5, 5%, threshold 70%, and 24-hour window.  `StorageBackend.count_active_users`
uses a local current UTC clock and local submissions/votes plus pending and
chain transactions whose `created_at` is within the window; it excludes
GENESIS/REWARD_POOL.  Callers are `Blockchain.get_active_users`,
`get_voting_threshold`, `/active-users`, `/voting-threshold`, evaluation, and
certificate construction.  Float approval and process-time active-user counts
mean two nodes can calculate a different required count and approval outcome.

This directly conflicts with the locked policy: quorum must use fixed constants
(including an established-reviewer minimum), not active population; approval
must be deterministically represented without float ambiguity.

## F. Reputation and access controls

Search found no reviewer-reputation score, status transition record, automatic
objective misconduct penalty, equivocation evidence, reviewer cooldown, or
reviewer suspension.  Existing similarly named controls are:

* `access_accounts` statuses and admin suspend/reactivate/revoke endpoints;
* persistent `allowlist_entries` with active/inactive/revoked state;
* environment denylist and daily vote cap;
* rate limits and review eligibility checks; and
* voter-majority rewards, which can re-check eligibility at payout time.

None constitutes the required reviewer state machine, and no collusion
analytics exists.  In particular, the current design should not reinterpret a
minority/finally unsuccessful vote or replayed identical signed payload as
misconduct.

## G. Certificates

Protocol v1 certificates have version/protocol/network identity, submission,
content hash/content ID, creator wallet, vote totals by type, decisive total,
float approval percentage and threshold, minimum votes, issuer node, approval
time, vote-set hash, and derived originality score.  Certificate ID is a
SHA-256 canonical-domain hash over a selected canonical identity payload.
The vote hash canonicalizes/sorts wallet plus choice and rejects duplicate
voters.  Certificate validation checks bindings, versions/network, count
arithmetic, approval threshold, score and recomputed certificate ID.  It does
not revalidate the signed vote payloads, reviewer eligibility/status, vote
timestamps, or original evidence.

Certificates are serialized inside the `originality_certificates` state section
and linked by `submission.certificate_id`; certified block metadata carries a
subset (certificate/submission/content/creator/vote hash, approval/counts,
approval time and score).  It supports loading and validation but lacks a
durable revalidation recipe for external originality tools.

Missing target commitments are `originality_evidence_digest`, originality-rule
version, reviewer-policy version, reputation-rule version, fixed quorum
parameters, established reviewer count/requirement, reviewer-status snapshot
or reference, and deterministic chain references.  Historical matched block
hashes must instead live in immutable evidence records, not directly here.

## H. Persistence and migration implications

Current named structures are `submissions`, `content_objects`, `votes`,
`originality_certificates`, `mint_queue`, `access_accounts`,
`allowlist_entries`, `audit_logs`, chain and finality sections.  No originality
evidence/reviewer-state/violation/equivocation tables exist.  JSON backend
would need versioned, canonical records plus atomic uniqueness enforcement;
SQLite should use relational durable tables with unique keys for media hash,
submission-voter identity, signed-vote identity/payload hash, evidence IDs and
reviewer transitions rather than more whole-section JSON.

Recommended new records: immutable per-submission `originality_evidence`
(algorithm/rule versions, inputs/digests, outcome and matched canonical block
hashes); reviewer status-transition and objective violation/evidence records;
immutable accepted vote records and idempotent replay index; and certificate
policy/status snapshot references.  Migration must preserve legacy
submissions/certificates as explicitly legacy/unverifiable, not invent evidence
or retroactively change certificates.  Hash/canonicalization versions must be
supported during reads and block validation.

## I. API surface and boundary observations

Public/developer surface includes `/content/upload`, `/content/text`,
`/submit_content`, submission listing/detail/evaluate/votes/certificate,
`/certificates/{id}`, `/active-users`, `/voting-threshold`, mint queue/mint,
`/review/policy`, wallet challenge/verify/submission/vote challenge, access
status/request/override request, and peer submission/vote/certificate/content
sync/broadcast routes.  Admin surface includes allowlist CRUD/revoke/reactivate,
access-account suspend/reactivate/revoke and audit-log routes.  Operations has
development reset, certificate repair and mint-blocking routes.

Privileged beta access lifecycle is separated under `/admin` and development
operations.  However, `/submissions/{id}/evaluate` and public mint endpoints
can advance protocol lifecycle (subject to rate limits) and evaluation accepts
`automated_originality_passed` from the request.  That is a route-boundary
concern: originality decision input and certification/mint authority must be
determined by consensus-valid records, not a public local boolean.

There is no duplicate-inspection API and no reviewer-reputation/status API.

## J. Tests and gap matrix

Existing relevant tests include `tests/submissions/test_community_voting.py`,
`test_originality_certificate.py`, `test_hard_rejection.py`,
`test_approval_logic.py`, `tests/api/test_review_policy_api.py`, signed-vote
protocol/golden-vector tests, certificate block validation, lifecycle/finality,
storage backend and peer vote/certificate sync tests.  They provide useful
regression coverage but not the Milestone 5 policy proof.

| Acceptance criterion / adversarial case | Current coverage | Gap |
| --- | --- | --- |
| Exact duplicate rejected before voting | Hard-rejection and legacy duplicate pieces only | No durable minted-media hash index or pre-vote test. |
| Same canonical state => same reviewer eligibility/weight | Mode/allowlist/activity API tests | No two-node canonical-state test; env/time/local-state inputs violate it. |
| Duplicate/self/replayed votes deterministic | Self/duplicate app tests; signed challenge tests | No durable idempotent replay or concurrent/peer replay test. |
| Reputation penalties/cooldowns auditable | Access/admin audit tests only | No reviewer reputation/violation lifecycle. |
| Certificate originality-rule version | Certificate/golden-vector coverage | Field and validation absent. |
| Corpus false positives/negatives | None | No corpus, metrics, or threshold justification. |
| Fresh wallets / coordinated identical votes / creator-linked votes | Creator self-vote only | Missing Sybil, coordination and linkage tests. |
| Recompression, resize/crop/border, OCR-preserving edits, template reuse | None | Missing media corpus and expected classifications. |
| Conflicting signed votes | Duplicate vote only | Missing evidence/review of two distinct valid signatures from one wallet. |

## Recommended Tasks 5.2+ order and decomposition changes

1. Freeze a versioned, integer/rational canonical policy and data model first:
   fixed quorum constants, reviewer statuses, objective violations, deterministic
   record IDs, vote semantics and migration/version strategy.  Do not layer this
   atop active-user quorum or env-only policy.
2. Add durable canonical reviewer status/eligibility snapshots and vote records,
   with database constraints and idempotent identical-replay behavior before
   enforcing any new reviewer policy.
3. Build the versioned originality evidence pipeline and exact minted-media
   index.  Implement exact hard reject before opening voting; retain fuzzy
   results as evidence-backed review flags only.
4. Establish the adversarial media corpus and reproducible tool/container
   versions before selecting any fuzzy hard-reject threshold.
5. Upgrade certificate/block commitments and validation to reference the new
   evidence digest, rule versions, fixed quorum and reviewer snapshot.  Then
   migrate/mark legacy records and add peer/block revalidation.
6. Add only objectively provable equivocation penalties and their audit trail;
   keep analytics alert-only.  Finally expose narrowly scoped inspection/status
   APIs and retire public lifecycle overrides.

The planned Task 5.2 should be split if it currently combines data-model,
eligibility, duplicate tooling and certificate work: durable deterministic
policy/state must precede both duplicate decisions and certificate changes.

## Verification record

Commands run (with the documented repository interpreter) and results:

| Command | Result | Runtime |
| --- | --- | --- |
| `./.venv/Scripts/python.exe -m pytest tests/submissions/test_community_voting.py tests/submissions/test_originality_certificate.py tests/submissions/test_hard_rejection.py tests/submissions/test_approval_logic.py tests/api/test_review_policy_api.py tests/test_protocol_v1_originality_votes.py tests/blockchain/test_certificate_block_validation.py tests/blockchain/test_active_users.py -q` | 78 passed, 0 failed, 0 skipped | 5.80s |
| `./.venv/Scripts/python.exe -m pytest tests/test_protocol_v1_golden_vectors.py tests/test_protocol_v1_freeze_consistency.py tests/blockchain/test_protocol_v1_lifecycle_finality.py tests/integration/test_two_node_consensus_verification.py -q` | 26 passed, 0 failed, 0 skipped | 3.09s |
| `./.venv/Scripts/python.exe -m compileall -q blockchain.py submission.py review_policy.py originality_certificate.py protocol_v1_originality.py services api_routers storage.py` | passed | no output |
| `git diff --check` | passed | no output |

The first documented command attempted with the system `python` could not run
because `C:\\Python313\\python.exe` has no `pytest`; this is an environment
dependency issue, not a repository test failure.  The repository `.venv`
command above is the documented normal command and established the baseline.
No test was modified to make a result pass.  Final worktree status contains
only this untracked audit artifact.
