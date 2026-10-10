# Milestone 6 Task 6.6 — frozen admission and pre-mint quarantine

Status: Task 6.6A adds the owner-selected, height-based network activation rule. Deployment must fix the same height on every node before Public Testnet block acceptance resumes.

## Compatibility and owner decisions

Tasks 6.1–6.5 are separate commits. Task 6.1 describes content-safety admission before originality review, while Task 6.5 allows two independent review dimensions after technical validation and attestation. Task 6.5's signed review policy v1 still contains `activation: inactive_owner_decision_required`; its admissibility governance remains provisional. Task 6.6A resolves the block-height activation decision without changing that signed review policy identity.

**POLICY TODO — OWNER DECISION REQUIRED:** final prohibited-content definitions and jurisdiction; final admissibility authority/quorum; appeals, recusal, and reviewer welfare; Task 6.7 report trigger policy. This task does not implement reporting, post-mint disputes, broader media-integrity work, or the frontend redesign.

## Task 6.6A activation boundary

The fixed `activation_height` is the **first** height requiring version 2 media blocks with a valid frozen admission certificate. Height `activation_height - 1` is the **last** height eligible for historical version 1 rules. Genesis remains height 0. The configured height is an integer of at least 1; a new genesis-only network may select height 1. Historical version 1 blocks below the boundary retain their bytes, hashes, and validation rules. Full-chain validation, local acceptance, peer block ingestion, chain synchronization, and reorg candidate validation all apply the same height rule. A peer cannot relabel a post-activation block as legacy.

`admission_activation.py` stores a versioned record containing network ID, canonical genesis hash, and activation height in `admission-activation-v1.json` under the node data directory. The blockchain document stores a second copy as an immutable witness; JSON and SQLite both retain it. A conflicting, missing, or malformed configuration fails startup after the witness has been persisted. The height is read once into each blockchain instance and passed to block validation; it is never recalculated from the tip on restart. A change or removal detected during new-block acceptance also fails closed. The peer chain summary advertises the height and skips peers with a conflicting value before fork choice or chain import.

If activation is unset, development nodes report `pre_activation`. `ENVIRONMENT=testnet` or `production` reports `misconfigured` and rejects new Public Testnet-valid block production and candidate-chain acceptance until a height is configured. Existing chain history remains readable so the operator can determine the tip. The read-only `/status` payload shows the network, canonical tip, configured height, last legacy height, and `pre_activation` / `active` / `misconfigured` state. The peer chain summary includes `admission_activation_height`.

### Deployment procedure

Stop block producers and peer ingestion on all nodes. Confirm the canonical chain tip and common genesis/network identity. Against the first node's intended `NODE_DATA_DIR`, run `python -m scripts.configure_admission_activation --show`, then `python -m scripts.configure_admission_activation --next-block`. The command validates the stored chain and fixes `activation_height = canonical_tip_height + 1`. Record the returned integer. On every other node, use the **same** value with `python -m scripts.configure_admission_activation --height H`; do not independently recompute `--next-block` on peers. Restart nodes, run `--show` on each, and compare `/status` and peer chain summaries. A second configuration with a different height is rejected. If any node has already advanced to or past H without the matching fixed record, configuration is rejected rather than retroactively blessing that history.

Pending pre-activation submissions receive no mint exemption at H. A queued originality-only submission is removed from the queue on restart and cannot mint after activation. Its old certificate remains readable. A still-unminted legacy submission can request a signed challenge with its existing `submission_id`, attach the signed attestation at `/submissions/{id}/admission-attestation`, and then complete Task 6.3–6.6 dual review. This transition preserves the submission ID, clears old queue eligibility, and requires a new frozen admission certificate before version 2 minting.

## Lifecycle

Current attested submissions distinguish `technical_rejected`, `awaiting_attestation`, `invalid_attestation`, `policy_mismatch`, `awaiting_review`, `review_unresolved`, `review_rejected_originality`, `review_rejected_admissibility`, `review_qualified`, `admission_qualified`, `mintable`, `quarantined`, and `minted` through the `admission` API field. The durable submission status also has `quarantined`. Staged content exists before a submission and remains subject to Task 6.3 technical validation; its pre-submission waiting period is not stored as a submission record. Historical unsigned submissions report `legacy_pre_activation`.

An unresolved review is waiting, not rejected. A negative result in either dimension, invalid or missing required attestation, invalid technical evidence, or policy mismatch sends a current pending submission to quarantine when evaluated. Quarantine is terminal for this review round: the submission and its evidence remain inspectable, it is removed from the mint queue, and the admin unblock-minting path does not change its status. Finalized blocks are never quarantined or altered. A later appeal/review round needs its own protocol-defined transition.

## Admission certificate v1

`admission_certificate.py` defines the canonical certificate body and SHA-256 canonical JSON digest. It binds network ID, submission ID, exact content hash, creator wallet, Task 6.2 policy ID/version/digest, Task 6.3 technical evidence identity projection and version, Task 6.4 signed attestation and version, Task 6.5 review-policy version/digest, signed vote records with reviewer reference heights and hashes, and separate originality/admissibility tallies including quorum, established-reviewer count, threshold, outcomes, and vote-set digests. The technical projection excludes declared MIME, display filename, local resource observations, and other Task 6.3 non-identity fields. The attestation's local `verified_at` observation is excluded from certificate identity. Vote ordering is by dimension, reviewer wallet, and signed vote identity; local row order and vote arrival times are excluded.

Issuance requires accepted media bytes, valid technical evidence, valid signed attestation, valid dimension-bound signed votes, an established reviewer in each five-vote quorum, and positive outcomes in both dimensions. The certificate copies the exact vote set and validation evidence. Later votes do not mutate it. Reviewer status is checked against each vote's referenced finalized snapshot, so later reputation changes do not rewrite the certificate. Unknown versions or mismatched policy digests fail validation.

`admission_qualified` means this frozen evidence validates. `mintable` means it also has a current queued submission and locally verifiable accepted bytes. Queue insertion and atomic block commit revalidate the certificate. Restart revalidates queued current submissions once and quarantines stale rows. The atomic commit performs the same checks under the existing storage transaction and head compare-and-swap. A failed pre-commit check persists a quarantine reason in a separate storage transaction. The current path cannot use a legacy originality-only certificate.

## Block and peer binding

Admission block version 2 embeds the full frozen certificate and complete Model A accepted media bytes. The block hash covers both. Block validation independently checks the certificate digest, media hash, technical evidence, attestation signature and identity, both signed vote sets and reviewer snapshots, quorum, policy and network identity, and all copied block metadata. Peer block and chain-import paths accept version 2 only after these checks. Version 1 historical blocks below activation retain their original hash and validation rules. Version 1 at or above activation is rejected before legacy certificate validation can authorize it.

## Storage and API

The certificate, admission state, and quarantine reason live in each submission record, so JSON and SQLite section storage round-trip without a relational schema migration. The `/submissions` and `/submissions/{id}` responses include `admission`. The submission-certificate route returns the dual-admission artifact for current submissions and labels legacy originality certificates separately. The frontend shows review pending, quarantined, admission qualified, mint pending, and minted distinctly. No public force-admit or force-unquarantine endpoint was added.

Development-only unsigned submissions retain their explicit requirement marker and do not become Public Testnet admission-certified. Direct legacy block construction cannot pass an activated block-height validator.

## Known release limits

- The owner has approved height-based activation, but each deployment must persist the same tip-plus-one height on every node before Public Testnet block acceptance. Final admissibility policy authority remains unresolved; existing review policy v1 is explicitly provisional and signed as inactive.
- Peer reviewer-snapshot verification depends on the peer's finalized-chain and reviewer-state data. Cross-node tests with genuine finalized reviewer histories are still required.
- Task 6.6 did not change package versions. The requested live `npm audit` on 2026-10-10 reported four high-severity packages: Axios 1.18.0 (GHSA-vh66-26gq-q6x8, GHSA-9fr6-4gfg-395g, GHSA-c29m-xwm3-cm6r, GHSA-mghh-pgcx-3jjj, GHSA-x97p-jq2g-jp4f, GHSA-3pq3-5fj3-cg6v, GHSA-542g-h47m-68v8, GHSA-j8rh-479h-cp32, GHSA-4hqw-qxg8-jxx2, GHSA-m8m8-qj5v-23w3, GHSA-44g4-m2mj-wpvx, and GHSA-r4gj-5m52-g5wh), Vue 3.5.13 / `@vue/server-renderer` 3.5.13 (GHSA-g2v6-rqmx-r4w6), and `source-map-js` 1.2.1 (GHSA-68fv-2mgg-jv7q). These are release/security remediation items outside Task 6.6. `pip check` passed. The Python security audit could not run under the managed permission profile; automatic approval review rejected sending the local package inventory to public PyPI.
