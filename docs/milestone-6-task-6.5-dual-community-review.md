# Milestone 6 Task 6.5 — dual community review

Status: dual-review implementation complete; admission activation remains **POLICY TODO — OWNER DECISION REQUIRED**.

## Scope and compatibility

Public Testnet v1 attested submissions carry two independent signed vote streams: `originality` and `admissibility`. Historical votes without a dimension remain originality-only. The original vote domain and certificates v1–v3 remain readable. Historical records are never relabeled as admissibility votes. The existing originality threshold is preserved. `REPORT` is not a review vote; collaborative reporting is deferred to Task 6.7.

The Task 6.1 target lifecycle places content safety before originality review. Task 6.5 permits the two community questions to be answered separately after technical validation and submitter attestation. Neither answer implies the other. This does not activate admission or public minting. Task 6.6 and the owner must define the final admission transition and block evidence.

## Policy and exact tally

The canonical `dual_community_review` policy is version 1 on `zoidberg-public-testnet-v1`. Its digest is the canonical JSON hash of `review_policy()` in `dual_review.py`. It references Milestone 5 reviewer policy version 1 and uses the existing probation, established, cooldown, suspension, epoch, and vote-limit model. Each review dimension has one valid vote per reviewer and submission. Two dimensions of the same submission consume one reviewer participation for daily and epoch quotas and promotion counts.

| Dimension | Positive | Negative | Abstention |
| --- | --- | --- | --- |
| Originality | `original` | `not_original` | `unsure` |
| Admissibility | `admissible` | `not_admissible` | `unsure` |

For **each** dimension independently, the counted vote set requires at least 5 eligible valid votes, including at least 1 established reviewer. `UNSURE` counts toward the five and consumes one reviewer participation, but is absent from the approval denominator. Let `P` be positive votes and `N` negative votes. The dimension resolves positive when quorum holds, `P + N > 0`, and `P × 10,000 >= (P + N) × 7,000`. It resolves negative when quorum holds, `P + N > 0`, and that inequality fails. Otherwise it is unresolved. All-`UNSURE` is unresolved. This is an explicit provisional reuse of the certificate-v3 originality quorum for admissibility; final safety authority and quorum remain an owner decision.

The canonical tally sorts records by normalized reviewer address and signed identity, deduplicates a reviewer within a dimension, and hashes a sorted vote-set projection. Conflicting duplicates in a frozen set fail. No database row order or arrival timestamp enters the tally digest. The `review_evidence_digest` binds the policy digest, submission and media hash, technical-evidence digest, attestation-message hash, and both dimension tallies, including their vote-set digests, counts, thresholds, and outcomes. `review_complete` means both dimensions resolved, including negative outcomes. `review_qualified` means both resolved positively and the stored submitter attestation validates against the accepted media and Task 6.3 technical evidence. It does not mean minting is activated.

## Signed vote and persistence

New votes use version 2 and canonical JSON domain `zoidbergchain/community-review/v2`. The signed payload binds network ID, review policy version and digest, reviewer and reputation policy versions, wallet, submission ID, accepted-media hash, dimension, choice, nonce, issued time, and expiry. The signed message is verified against the wallet and live challenge. Its identity hashes the exact canonical payload and normalized signature. Reusing an originality signature for admissibility, or changing a choice, submission, media hash, network, or dimension, invalidates the message/identity. A retry with the identical signed message and signature returns the existing vote; a conflicting same-dimension vote is rejected and remains eligible for existing equivocation handling.

Votes remain in the `votes` storage section as separate records. SQLite `durable_vote_records` adds a `dimension` column, defaulting historical rows to `originality`, and its accepted-vote uniqueness index uses `(submission_id, voter_address, dimension)`. The migration is additive and repeated startup is safe. Existing record identities and certificate versions are unchanged. Peer messages carry version and dimension, reconstruct the canonical signed message, enforce the same reviewer snapshot and per-dimension uniqueness, and reject unknown versions or dimensions.

## Certification and activation

The API exposes legacy originality counts and votes, separate admissibility votes, and a `dual_review` object with both tallies, `review_complete`, `review_qualified`, `review_state`, and a deterministic evidence digest. The states distinguish `legacy_originality_only`, `incomplete_dual_review`, and `resolved_dual_review`. The reviewer screen asks two independent questions with separate `UNSURE` answers. Current attested submissions cannot create an originality-only certificate or use one for a new mint or peer certificate admission; `evaluate` reports dual-review qualification without moving such a submission to the mint queue. This fail-closed boundary prevents certificate v3 from being mistaken for a full Milestone 6 certificate. General certificate validation remains available for historical chain records, and historical certificates remain readable through their originality-only API scope. `get_qualified_dual_review_evidence` produces a qualified proof only when both dimensions and the attestation pass; `validate_qualified_dual_review_evidence` compares it against the current signed vote set and prerequisites, rejecting changed votes or attestation. The dual-review digest is a deterministic view of the currently accepted vote set; it is not yet a frozen, mint-consumable certificate.

**POLICY TODO — OWNER DECISION REQUIRED:** final prohibited-content definitions and jurisdiction, safety reviewer authority/quorum/conflicts/recusals/welfare, the admission activation height, treatment of in-flight submissions, and the final dual-review certificate/block binding. Task 6.6 owns the admission and mint transition. Task 6.7 owns reporting. No activation height is set here.
