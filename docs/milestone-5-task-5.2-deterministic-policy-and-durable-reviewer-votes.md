# Milestone 5, Task 5.2: deterministic policy and durable reviewer/vote foundation

## Scope and repository base

This task is based on branch `Proof-of-Originality-Security-and-Reviewer-Reputation`
at `9d7c1825048065b0446e70d86b90404821bcb6bc` (`task 4.10 done`).  The Task 5.1
audit remained intentionally uncommitted and was not modified.

Task 5.2 adds foundations only.  It does not activate the Milestone 5 reviewer
state machine, fixed certificate quorum, reputation penalties, originality
pipeline, collusion analysis, or final certificate schema.

## Network policy definitions

`milestone5_policy.py` is the network-defined source for reviewer policy v1 and
reputation rules v1.  Both definitions use the shared Protocol v1 canonical JSON
serializer and SHA-256 canonical hash.  Lookup is explicit by integer version;
unknown versions fail instead of falling back.

Reviewer policy v1 freezes the following decided semantics:

- five reviewer status names;
- numerical vote weight `1`;
- the canonical bootstrap-established wallet set;
- reserved fields for earned-admission paths and fixed/integer quorum rules.

Reputation rules v1 freeze objective-protocol-violations-only automatic
penalties, with penalties disabled and their rules reserved for Task 5.6.
Collusion analytics are explicitly alert-only.

No numeric admission or certificate thresholds were invented.  Reserved fields
are present in the canonical policy so later tasks can fill a new policy version
without changing persistence columns.

The Public Testnet v1 bootstrap-established set is deliberately the literal
empty set.  No approved wallet list exists in the repository.  Adding a wallet
therefore requires an explicit reviewer policy version change; a local
`REVIEW_ALLOWLIST_WALLETS` value cannot alter this canonical set.

## Consensus policy versus operator compatibility policy

The existing `review_policy.py` environment configuration remains the live
API/operator eligibility gate during this compatibility task.  It is not
represented as, or relabeled as, Milestone 5 consensus policy.  Environment
changes cannot change the bytes or digests of reviewer policy v1 or reputation
rules v1.

Votes accepted through the current compatibility gate store null reviewer
policy version, reputation version, and reviewer-status snapshot values.  This
means “not evaluated under the Milestone 5 deterministic policy,” rather than
fabricating a v1 decision.  A later task can switch admission to the canonical
policy and populate all three fields together.

## SQLite reviewer state

`reviewer_states` stores one current row per normalized Ethereum address:

- current status;
- reviewer/reputation versions;
- consensus-effective block height and block hash;
- canonical bootstrap grant flag;
- operational creation/update timestamps.

`reviewer_state_transitions` is append-only by `(reviewer_address,
transition_sequence)` and preserves old/new status, both policy versions,
canonical height/hash, bootstrap flag, reason, and an operational observation
timestamp.  Height and hash must both be null or both be present.  Operational
timestamps are never treated as consensus-effective transition inputs.

Initialization and transition APIs reject invalid addresses, statuses,
unsupported versions, malformed canonical references, and bootstrap flags not
authorized by the selected policy.  Task 5.2 deliberately does not constrain
which non-bootstrap semantic transition follows another; that belongs to the
later state-machine task.

## SQLite durable vote evidence

`durable_vote_records` is an immutable-evidence-oriented companion to the
existing `votes` compatibility section.  It retains submission/content/voter
identity, vote choice, complete Protocol v1 signed payload metadata, signature,
canonical vote identity, accepted/rejected lifecycle, reviewer policy/status
snapshot columns, and the source record.

For a signed Protocol v1 vote, `vote_identity` is SHA-256 over canonical JSON
containing:

1. the existing canonical Protocol v1 vote signing envelope;
2. normalized `personal_sign` scheme; and
3. the normalized 65-byte signature.

No competing vote payload serializer was introduced.  Optional `0x` signature
prefix and hexadecimal case normalize to the same identity.  Any stored
identity is recomputed and checked on ingestion.

The partial unique index `one_accepted_vote_per_submission_wallet` enforces at
most one accepted vote for `(submission_id, voter_address)`.  An identical
signed replay resolves to the existing evidence row.  A different signed vote
for the same pair is retained as a rejected `conflicting_counted_vote` row, so
future equivocation analysis has both signatures while only one can count.

Normal signed-vote handling still performs the existing signature verification
before durable admission.  The public route, vote choices, and duplicate-vote
error behavior are unchanged.

## Migration and legacy semantics

SQLite startup uses idempotent `CREATE TABLE/INDEX IF NOT EXISTS` statements.
It projects every existing compatibility vote into `durable_vote_records`
without deleting or rewriting `storage_sections.votes`.

An old vote lacking the full signed Protocol v1 fields is stored with:

- `identity_status = legacy_unverifiable`;
- `vote_identity = NULL`; and
- a stable `legacy:<sha256>` evidence key over its existing record and list
  position.

This preserves the data and makes the missing proof explicit.  It does not
manufacture a nonce, signature, content hash, policy version, or reviewer state.
Reopening the database is idempotent.  JSON-to-SQLite migration also triggers
the same projection when the migrated document is saved.

The normalized constraints are provided by the SQLite backend.  The JSON
backend remains a development compatibility backend: its existing vote list
still survives restart, but it cannot provide relational counted-vote or
conflicting-evidence guarantees.  Deployments requiring Task 5.2 durability
must use SQLite.

## Fields reserved for Tasks 5.3–5.7

- originality evidence and `originality_rule_version`;
- fixed minimum valid/established vote counts and integer approval threshold;
- earned admission thresholds and state transition rules;
- objective violation definitions, cooldowns, and suspension penalties;
- certificate and block commitments to policy/evidence/status snapshots;
- alert-only collusion analytics.

## Task 5.3 implications

Task 5.3 should build exact/fuzzy originality evidence independently of the
reviewer tables.  It should use a separate versioned `originality_rule_version`
and immutable evidence digest, leave fuzzy results review-only until a corpus
justifies stronger treatment, and avoid migrating certificate identities until
the later certificate task.  It should also require SQLite wherever durable
evidence uniqueness is consensus-relevant, matching the boundary established
here.

## Verification

The Task 5.2 test module covers canonical policy bytes/digests, environment
isolation, reviewer restart/history and invalid combinations, durable signed
vote replay/conflict/restart, the live signed-vote path, cross-node identity,
signature normalization/binding, and idempotent pre-Task-5.2 migration.

Verification completed on 2026-09-08 (America/New_York):

- Task 5.2 module: `9 passed`;
- focused native-recovery regression plus Task 5.2: `11 passed`;
- originality/reviewer/vote/certificate, Protocol v1, storage/migration,
  two-node, finality, and native regression selection: `295 passed`;
- full backend suite with a workspace-local pytest base temp: `1081 passed`;
- Python compile checks: passed;
- `git diff --check`: passed (Git emitted only line-ending conversion warnings).
