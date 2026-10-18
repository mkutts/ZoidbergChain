# Milestone 6 Task 6.10 — API and frontend lifecycle integration

Status: implemented on `Immutable-Media-Safety-and-Admission` without protocol redesign.

## Canonical lifecycle terminology

The public integration layer does not use a single `approved`, `safe`, `valid`,
or `rejected` flag as a media verdict. It distinguishes:

- **technical rejection**: exact bytes cannot enter the review pipeline;
- **attestation missing / invalid / valid**: the Task 6.4 rights and permanence
  statement is absent, invalid, or cryptographically valid;
- **originality pending / original / not_original / unsure**;
- **admissibility pending / admissible / not_admissible / unsure**;
- **report below threshold / threshold met**: additive pre-mint observations;
- **quarantined**: retained and inspectable, but unable to mint in the current
  review round; this is not deletion;
- **admission qualified**: the frozen current admission certificate is valid;
- **mintable / mint pending**: admission evidence is valid and queue-eligible;
- **minted / finalized**: an immutable block exists, with finality shown
  independently;
- **post-mint disputed**: the finalized-media warning threshold is met; finality
  and block bytes do not change;
- **media integrity verified / failed / unavailable**: byte-commitment status
  only, never a legality, safety, originality, admissibility, or dispute verdict;
- **legacy/pre-activation**: historical originality-only or unsigned records are
  not relabeled as current dual-admission-certified records.

## Derived public lifecycle read model

`GET /submissions/{submission_id}/lifecycle` is a public, rate-limited, read-only
route. It derives its response from durable submission, vote, report,
certificate, activation, block/finality, dispute, and embedded-media state. It
does not persist a duplicate lifecycle object and has no mutation path.

The response is:

```text
submission_id
lifecycle
  schema_version
  stage
  blocking_stage
  technical_validation
    status, outcome, reason_codes, evidence_version, evidence_digest
    media_hash, byte_length, detected_mime_type
  attestation
    requirement, status, valid, reason_code
    statement_id, statement_version, message_hash
  review
    mode, state, complete, qualified
    originality, admissibility
  reporting
    status, protocol_state, count, established_count
    threshold, established_threshold, threshold_met, reason_counts
  quarantine
    quarantined, reason, category, deletion, can_mint_current_round
  admission
    state, qualified, reason, certificate
  activation
    network_id, state, activation_height, first_enforced_height
    last_legacy_height, canonical_tip_height, canonical_tip_hash
    enforced_for_next_block
  mint
    state, eligible, queue_present, minted
  finality
    state, block_height, block_hash, canonical
    confirmations, confirmed, finalized
  post_mint_dispute
    status, count, established_count, threshold
    established_threshold, threshold_met, reason_counts
    block_remains_finalized
  media_integrity
    status, meaning, algorithm, sha256, byte_length
    contract_version, block_height, block_hash, download_url
  legacy
    pre_activation, certificate_scope, missing_fields_are_not_inferred
```

`GET /submissions` and `GET /submissions/{submission_id}` add this `lifecycle`
object without deleting any compatibility fields. The existing
`protocol_v1_lifecycle`, `admission`, flat status fields, certificate routes,
report routes, dispute routes, and block routes remain available.

The dedicated lifecycle route verifies Task 6.9 byte integrity by default for
one selected immutable block. Callers can use `verify_integrity=false` for a
metadata-only read. Embedded list summaries do not repeatedly hash large media;
they report integrity as unavailable until explicit verification or the exact
download route verifies it.

## Status mapping and blocking stage

The top-level stage follows finalized state first, then minted state, then the
existing Task 6.6 admission state. `post_mint_disputed` is additive to finalized
state. The blocking stage is one of `technical_validation`, `attestation`,
`community_review`, `quarantine`, or `activation`, or `null` when no current
prerequisite blocks progress.

Originality and admissibility retain their independent Task 6.5 tallies and
outcomes. `unsure` remains an abstention in its selected dimension and is never
converted to a negative vote. Reports are Task 6.7 observations and are never
converted to admissibility votes. Disputes are Task 6.8 finalized-media
observations and are never converted from reports.

Quarantine reasons are grouped for presentation as originality rejection,
admissibility rejection, invalid/tampered prerequisite, community-report
threshold, or other protocol reason. The exact durable reason remains exposed.

## Certificate and legacy presentation

Current certificate summaries expose certificate version and digest, media
hash, media-admission policy identity, technical-evidence binding, attestation
binding, and separate originality/admissibility results. They do not regenerate
the certificate and do not expose raw signatures in the lifecycle summary.

Certificate scope is `current_dual_admission` or
`legacy_originality_only`. Missing historical admissibility, attestation, or
current-policy fields remain absent; the API does not fabricate them.

## Activation, finalized media, and integrity

`/status` continues to expose Task 6.6A activation state. `/chain/summary` now
also includes the complete `admission_activation` object so public/operator UI
can show configured activation height, canonical tip, first enforced height,
last legacy height, and `pre_activation`, `active`, or `misconfigured` state.

Public block summaries now add certificate scope, a byte-integrity presentation
object, and the post-mint dispute overlay for finalized media. The dashboard's
explicit **Verify Exact Bytes** action calls the single-submission lifecycle
route on demand, so routine refreshes do not repeatedly hash large media. Exact bytes are
served only by `GET /blocks/{block_hash}/media`, which performs Task 6.9
verification and returns the original embedded bytes without decode/re-encode,
resizing, recompression, or browser image transformation.

## Auth and signed-action UX

Public read-only routes require no wallet, peer, or admin credentials. Review
votes, reports, disputes, and their challenges retain verified-wallet and
review/access eligibility checks. Peer receive/sync routes retain peer
authentication. Admin and development mutation routes are unchanged. Task 6.10
adds no public mutation or activation control.

Before requesting `personal_sign`, the frontend validates:

- submitter attestation: statement/domain, network, policy, technical evidence,
  selected wallet, selected media hash, canonical message, and expiry;
- originality/admissibility vote: action-specific v2 domain, network, review
  policy identity/digest, reviewer policy, wallet, submission, media hash,
  dimension, choice, canonical message, and expiry;
- community report: report domain/network/policy, wallet, submission, media
  hash, reason, canonical message, and expiry;
- post-mint dispute: dispute domain/network/policy, wallet, submission, exact
  finalized height/hash, media hash, reason, canonical message, and expiry.

The Task 6.4 permanence statement is unchanged. The UI explicitly separates
staging from submission, admission, minting, and finality.

## Frontend presentation and request behavior

The Dashboard shows separate technical validation, attestation, originality,
admissibility, report, quarantine, admission, activation, mint/finality,
integrity, dispute, and legacy/certificate-scope labels. Report and Dispute have
separate reason selectors and explicit button text. Quarantine copy says the
item is pre-mint, cannot mint in the current round, and is not deleted.

Status is conveyed with text as well as color. Choice controls keep associated
question text and explicit button labels. Long hashes wrap, the existing mobile
breakpoint stacks detail grids and actions, and exact-byte downloads are normal
keyboard-accessible links.

The Dashboard consumes embedded lifecycle, report, certificate, dispute, and
integrity summaries. It no longer performs per-submission report/certificate
requests or per-block dispute requests during routine refresh. Vote records are
still fetched once per visible pending submission because the current-wallet
duplicate-vote UI needs the signed record; there is no request per individual
vote. Integrity bytes are not downloaded or rehashed during render.

## Error model

Signed protocol operations continue to return established HTTP status codes and
Task 6.4 machine-readable attestation reason codes where defined. The frontend
maps invalid/expired signature challenges, wrong wallet/network/policy, duplicate
or conflicting action, reviewer ineligibility, quarantine, finalized-state
mismatch, activation misconfiguration, integrity failure, and legacy/current
mismatch to stable user-facing messages. Internal stack traces, filesystem
paths, database details, private keys, admin secrets, and peer credentials are
not included in the lifecycle summary.

## Compatibility and unchanged consensus behavior

All response changes are additive. No vote, report, or dispute threshold;
reviewer reputation rule; admission certificate byte; activation-height rule;
block hash; integrity contract; finality rule; or dispute-consensus separation
changed. No deletion, takedown, appeal, unquarantine, or re-review transition was
added.

## Remaining policy/owner decisions

The following remain **POLICY TODO — OWNER DECISION REQUIRED**:

- final prohibited-content definitions, jurisdiction, and production legal text;
- final admissibility authority/quorum, conflicts, recusals, and reviewer welfare;
- appeal, unquarantine, adjudication, and new-review-round mechanics;
- false-report/dispute treatment and evidence-retention/abuse bounds;
- presentation suppression or legal response for disputed finalized media.

## Dependency findings carried forward

Task 6.10 does not change dependency versions. The known npm findings remain:
Axios high-severity findings, Vue / `@vue/server-renderer` findings, and
`source-map-js` findings. The Task 6.10 live authoritative audit again reports
4 high, 0 critical, across `axios`, `vue` / `@vue/server-renderer`, and
`source-map-js`. These unresolved findings carry into Task 6.11.

