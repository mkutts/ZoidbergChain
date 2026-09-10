# Milestone 5, Task 5.5: earned reviewer eligibility and probation

Task 5.5 activates Reviewer Policy v1 for live network reviewer decisions. It
does not change certificate version 2, enable an established-reviewer
certificate minimum, add reputation penalties, or add collusion analytics.

## Reviewer Policy v1

The versioned canonical policy contains these consensus values:

- `REVIEW_EPOCH_BLOCKS = 5`
- `MIN_WALLET_AGE_EPOCHS = 3`
- creator path: 2 finalized minted submissions
- ZOID path: 5 finalized native transactions spanning at least 3 epochs
- mixed path: 1 finalized minted submission plus 2 finalized native transactions
- probation: at least 3 epochs, at most 5 accepted votes per epoch, and at least 10 accepted probationary votes for promotion
- established rate: at most 25 accepted votes per epoch
- every eligible vote has integer weight 1

The policy is canonical JSON and part of the reviewer-policy SHA-256 identity.
Unknown versions fail. Environment variables cannot change these values.

## Epoch and finalized reference

The zero-based formula is `review_epoch = finalized_canonical_height // 5`.
The reference is the highest persisted quorum-finalized block that still
matches the canonical chain. Unfinalized head growth and shallow reorgs above
that block therefore do not affect reviewer age, qualification, quota, or
status. Existing fork choice and finality preservation remain authoritative;
Task 5.5 adds no fork-choice rule.

## Wallet origin and earned paths

The wallet origin is the earliest height at or below the finalized head at
which the wallet is either the creator of a canonical minted content block or
the sender/recipient of a canonical native transfer included in a block.
Wallet age is `(finalized_height - origin_height) // 5`. Local first-seen time,
MetaMask history, pending submissions, mempool records, balances, rejected
records, and wall clock are irrelevant.

Minted submissions are deduplicated by `submission_id`. Native activity is
deduplicated by `tx_id`. A self-transfer establishes canonical participation
for age, but is excluded from the earned native-transaction count. The ZOID
span is `last_activity_epoch - first_activity_epoch`; it must be at least 3.
If several paths qualify, the canonical order is creator, ZOID activity, mixed,
and all qualifying paths are also returned.

## State transitions and bootstrap

An earned wallet transitions `NEW -> PROBATIONARY_REVIEWER`; it cannot skip
probation. The durable reason contains the effective epoch, qualification path,
and a digest of the structured evidence; the transition stores the policy
versions and finalized height/hash in dedicated columns.

The network policy contains
`PUBLIC_TESTNET_V1_BOOTSTRAP_ESTABLISHED_REVIEWERS`. It is intentionally empty
because no approved addresses exist in the repository. Operators must add
approved normalized addresses in a reviewed reviewer-policy version change;
the legacy `REVIEW_ALLOWLIST_WALLETS` and admin override records are never
imported. A policy member transitions directly to `ESTABLISHED_REVIEWER` with
explicit `PUBLIC_TESTNET_V1_BOOTSTRAP_ESTABLISHED_REVIEWERS` provenance.

## Probation, promotion, and quotas

Accepted durable votes copy the reviewer-policy version, reputation-rule
version, status, and finalized reference. Replays retain one identity and one
quota use. Rejected/conflicting evidence records consume no quota. Vote choice
does not affect participation: minority and `unsure` votes count normally.

Promotion occurs only when the current epoch is at least three epochs after the
probation transition and at least ten accepted records were cast with
`reviewer_status=PROBATIONARY_REVIEWER`. The transition is idempotent and is
never applied to `COOLDOWN` or `SUSPENDED`. Those durable states remain
ineligible; Task 5.7 will define their automatic triggers.

## Canonical and local policy

`review_policy.py` remains a compatibility/operator service-access layer. Its
`open`, `allowlist`, `activity`, and `hybrid` modes, wall-clock activity
thresholds, denylist, daily limit, and admin overrides may make this node refuse
an API request. Outside development they cannot make a Reviewer Policy v1
ineligible wallet's vote valid. Development retains its legacy no-finality vote
path so old local fixtures and tools continue to work; those votes have null
reviewer fields and are not Reviewer Policy v1 votes.

The voter-reward compatibility filter still uses the local policy because
Task 5.5 does not redefine rewards. Certificate v2 continues to require all
reviewer/reputation/snapshot fields to be canonical nulls.

## Reviewer snapshots and peers

A snapshot commits to the reviewer-policy version, reputation-rule version,
finalized height/hash, review epoch, and a sorted selected reviewer list with
address, status, and nullable bootstrap provenance. Canonical JSON excludes
operational timestamps. `reviewer_snapshot_digest` is the canonical SHA-256
hash. Callers may snapshot only participating reviewers, avoiding a network-wide
wallet scan. Task 5.6 must introduce a later certificate version before binding
this digest.

Peer vote payloads may carry the five Reviewer Policy v1 snapshot fields. A
receiver recomputes status, quota, and the finalized reference from its own
canonical state and rejects a mismatch; peer assertions are not trusted.
Historical peer votes without these fields remain compatible.

## Persistence and migration

SQLite uses the Task 5.2 `reviewer_states`, `reviewer_state_transitions`, and
`durable_vote_records` tables. Task 5.5 adds query/transition behavior without a
destructive schema rewrite, so opening a Task 5.4 database is the idempotent
migration. Existing votes, certificates, originality evidence, native records,
and reviewer history are preserved; no legacy history is fabricated.

JSON can deterministically project current qualification from the chain, but it
does not provide relational transition history or durable accepted-vote quota
guarantees. It remains development compatibility and must not be advertised as
equivalent to SQLite.

## Remaining risks

- Bootstrap membership is empty pending an approved, versioned wallet list.
- Self-transfer exclusion is intentionally narrow; broader anti-farming and collusion analysis are deferred.
- Exceptional finalized rollback follows the existing recovery path; it is not a normal shallow-reorg condition.
- Certificate quorum and snapshot binding remain Task 5.6 work and must use a new certificate version rather than populating certificate-v2 null fields.
