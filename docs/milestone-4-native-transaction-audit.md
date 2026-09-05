# Milestone 4, Task 4.1 — Native Transaction Durability, Propagation, and Reorg Audit

Date: 2026-09-05

## 1. Scope and repository baseline

This is an audit and implementation specification only. It does not implement
Milestone 4 protocol behavior, change a transaction or block format, or alter
runtime behavior.

- Branch: `Native-Transactions-Durable-Mempool-and-Reorg-Recovery`
- HEAD: `e27bdc26229cd0a7a4130d868d2cf732a410303f`
- HEAD description: `docs: complete Milestone 3 lifecycle benchmark and readiness report`
- The branch, `main`, `origin/main`, the remote Milestone 4 branch, and the
  completed Milestone 3 branch all pointed at this commit during preflight.
- The worktree was clean before this report was created. No unrelated changes
  were present.
- No commit or push was performed.

The audit inspected the implementation directly, including `native_transfer.py`,
`protocol_v1_native_transfer.py`, `protocol_v1_peer_message.py`, `block.py`,
`blockchain.py`, `storage.py`, `storage_migration.py`, `peer_sync.py`,
`services/native_ledger_service.py`, `services/native_mempool_service.py`,
`services/peer_transport_service.py`, `services/peer_chain_sync_service.py`,
`services/fork_choice_service.py`, `services/reward_service.py`,
`services/finality_service.py`, native and peer API routers, deployment examples,
Protocol v1 documents, storage documents, the Task 3.1 audit, the Milestone 3
release report, recent Milestone 3 commits, and the relevant tests.

Recent Milestone 3 history was inspected through `e27bdc2`, `ff4ab31`,
`01bae92`, `65ea1ab`, `436e51d`, `4f69f41`, and `7c960e2`. The resulting
architecture provides an atomic, expected-head-guarded certified block commit,
canonical uniqueness projections, idempotent certified commits, and persisted
known-validator quorum finality. Those protections do not yet cover native
transaction admission and peer delivery as independent durable operations.

## 2. Executive findings and prompt/implementation mismatches

The fixed project decisions match the current chain model: ZOID is native L1
value; user identity and transfer authorization use Ethereum-style addresses and
MetaMask `personal_sign`; certified original content creates blocks; one accepted
submission creates one block; full Model A media is embedded in Protocol v1
blocks; native transfers settle inside those blocks; and a configured validator
set supplies quorum finality.

The important current-state mismatches are:

1. A peer transaction can be acknowledged as accepted without being persisted.
   `receive_peer_transaction()` records and admits it in memory, then returns
   `accepted: true`; it does not call `save_blockchain()`.
2. SQLite is not a normalized transaction database. Pending native transactions
   and transfer intents are JSON arrays stored in `storage_sections.json_data`.
   The relational native-transaction claim table covers only transactions already
   embedded in the canonical chain.
3. Pending `tx_id` uniqueness and pending `(sender, nonce)` uniqueness are only
   application-enforced list checks. Neither is database-enforced.
4. Native transaction broadcast is manual. Local admission does not automatically
   gossip a transaction, a receiving peer does not relay it, and there is no
   durable outbox, retry worker, or per-peer delivery record.
5. The public transaction API exposes local internal statuses and calls an
   immediately accepted canonical transaction `settled`. It does not derive
   `CONFIRMED` or `FINALIZED` from the containing block. `included` is declared
   but is not written by the current implementation.
6. The old chain-replacement path preserves local transaction records and
   downgrades detached `settled` records to `validated_pending`, but does not
   resolve conflicts between a detached transaction and a different canonical
   transaction using the same sender nonce. It can therefore create conflicting
   live records until restart repair, and restart repair can retain the wrong
   record depending on list order.
7. Generic JSON and SQLite whole-document saves remain last-snapshot-wins across
   multiple processes. Milestone 3 fixed this for certified block commitment by
   using a lock/`BEGIN IMMEDIATE`, expected-head comparison, and one atomic
   mutation. Native submission, admission, peer receive, and chain adoption do
   not consistently use an equivalent transaction boundary.
8. Development defaults still use JSON, while the deployment example selects
   SQLite. Both must have defined semantics during migration, but only SQLite can
   provide the requested relational database constraints without an application
   lock and full-document validation substitute.

These are audit findings, not unrelated worktree problems, so Task 4.1 can
proceed without changing code.

## 3. Current transaction identity and authorization

### 3.1 Protocol v1 construction

A Protocol v1 native transaction is built from a canonical transfer intent with:

- `transaction_version = 1`
- normalized lowercase `from_address` and `to_address`
- normalized decimal-string `amount` and `fee`, with at most six decimal places
- strict positive integer-string `nonce`, initially `1`
- timezone-aware ISO-8601 `timestamp`, normalized to UTC text
- trimmed optional `memo`
- canonical `network_id`

The signing message is canonical JSON for the domain-separated Protocol v1
envelope `zoidbergchain/native-transfer/v1`. The envelope binds protocol and
object identity, Protocol v1, canonical network ID, and the inner transfer
payload. The backend requires exact message equality, hashes it with SHA-256,
and recovers the signer through Ethereum signed-message recovery. The recovered
lowercase address must equal `from_address`.

The Protocol v1 `tx_id` is the SHA-256 domain hash of the same canonical transfer
intent. It includes the version, addresses, amount, fee, nonce, timestamp, memo,
network ID, object type, protocol, and protocol version. It excludes signature
bytes and all local lifecycle metadata. Consequently the current Protocol v1
`tx_id` equals `signed_message_hash`.

Shape validation rejects a wrong runtime network name, a wrong canonical network
ID, unsupported versions, malformed values, non-canonical IDs, or a `tx_id` that
does not match the reconstructed intent. Mempool admission additionally requires
Protocol v1, verifies the exact signing message and signature again, applies the
zero-fee policy, checks the strict next nonce, and checks available balance.

### 3.2 Legacy compatibility

Versionless legacy transfers use a human-readable signing message and a legacy
transaction hash that includes signature-bearing fields. They can still be read
and verified on the explicit compatibility path, but they cannot enter the live
Protocol v1 mempool or a new Protocol v1 block. Milestone 4 must not silently
reinterpret or recompute their identifiers.

## 4. Current persistence and acknowledgement boundaries

The facade owns in-memory `transfer_intents` and `native_transactions` lists.
`save_blockchain()` serializes the complete node state, including the selected
chain, wallets, content state, rewards represented by blocks, finality records,
transfer intents, and native transactions.

| Entry point | Mutation before response | Durable state before successful response |
|---|---|---|
| `POST /transfers/submit`, no admission | Adds matching transfer intent and native transaction as `signed_pending` | One whole-state save containing both records |
| `POST /transfers/submit`, with admission | First saves `signed_pending`, changes both records to `mempool`, then saves again | Whole state with `mempool` status and `admitted_at` if both saves succeed |
| `POST /transactions/{tx_id}/admit` | Validates and changes transaction/intent to `mempool` | One whole-state save before response |
| `POST /transactions/{tx_id}/broadcast` | Ensures local `mempool`, saves only if it changed, then synchronously contacts peers | Local record is normally durable first; no delivery state is durable |
| `POST /peers/transactions/receive` | Records `signed_pending`, admits to `mempool` | **Nothing**; accepted transaction exists only in process memory |
| `sync_transaction_from_peer()` / `sync_mempool_from_peer()` | Fetches, records, and admits | **Nothing** unless a later unrelated operation saves the whole state |
| Peer block receive | Appends validated block, settles its native transactions, reconciles submission/reward state | One whole-state save before accepted response |
| Certified local block commit | Selects, validates, includes, settles, applies rewards/submission state | One Milestone 3 atomic expected-head commit before response |
| Peer candidate-chain adoption | Replaces chain and reconciles in memory | One generic whole-state save before sync response |

For local transfer submission, the record persisted before acknowledgement is
the complete signed transaction plus lifecycle timestamps/fields and the paired
compatibility transfer intent. No balance is debited; final balance remains
chain-derived. When requested, the second persisted version also contains
`status = mempool` and `admitted_at`.

### 4.1 Where an acknowledged transaction can disappear

An acknowledged transaction can disappear in these concrete windows:

1. **Peer receive:** the route returns `accepted: true` without any save. A crash,
   restart, or state reload loses the transaction immediately.
2. **Pull-based peer sync:** the transaction and mempool entry are also only
   in memory. A restart loses them.
3. **Broadcast of an already-memory-only peer transaction:** the broadcast
   operation skips its save when status is already `mempool`; it can report peer
   results while the local record remains non-durable.
4. **Concurrent stale whole-document writers:** outside the Milestone 3 certified
   commit boundary, another process can persist an older complete snapshot after
   a transaction was acknowledged, removing it from either JSON or SQLite.
5. **JSON corruption recovery:** a transaction present only in the newest main
   file can be lost if the file becomes unreadable and recovery falls back to the
   previous `.bak`. The write fsyncs the temporary file but does not fsync the
   parent directory after rename.

There is also an uncertain-outcome window after a durable save succeeds but
before the HTTP response reaches the caller. Retrying the same Protocol v1
transaction is application-idempotent by `tx_id`, but only if the durable record
was not later overwritten by a stale writer.

## 5. JSON and SQLite behavior

### 5.1 JSON

JSON normalizes and writes the complete document to a temporary file, flushes and
fsyncs it, atomically replaces the main file, and maintains a latest-known-good
backup. Generic saves do not acquire the Milestone 3 commit lock. The lock and
expected-head check are used only through `atomic_commit_blockchain_document()`.

Before a JSON save, `canonical_document_claims()` scans the selected chain and
application-enforces unique canonical block heights/hashes, certified identities,
canonical native `tx_id` values, canonical `(sender, nonce)` pairs, and reward
IDs. JSON has no database indexes or constraints.

### 5.2 SQLite

SQLite stores every logical section, including `transfer_intents` and
`native_transactions`, as JSON text in a row of:

- `storage_sections(section_name PRIMARY KEY, json_data NOT NULL, updated_at NOT NULL)`

It also rebuilds projection tables from the selected chain:

- `certified_commit_claims`, with unique submission, certificate, block hash,
  and block height claims;
- `canonical_native_transaction_claims`, with `tx_id PRIMARY KEY` and
  `UNIQUE(sender, nonce)`;
- `canonical_reward_claims`, with `reward_id PRIMARY KEY`.

`BEGIN IMMEDIATE` makes each SQLite save transactional and the Milestone 3
atomic commit holds the write lock while it rereads and compares the head.
Generic saves still load a whole snapshot outside that boundary and can later
overwrite a newer logical section. The canonical native claim table does not
contain pending transactions and cannot prevent duplicate pending records.

### 5.3 Current uniqueness answer

- Pending `tx_id` uniqueness: **application-level only**.
- Pending `(sender, nonce)` uniqueness: **application-level only**.
- Canonical-chain `tx_id` uniqueness: application-checked for JSON and
  database-enforced by a primary key in SQLite's derived claim table.
- Canonical-chain `(sender, nonce)` uniqueness: application-checked for JSON and
  database-enforced by a unique SQLite constraint in the derived claim table.

Restore code validates signatures and shape, removes duplicate transaction IDs,
and removes a later conflicting unavailable sender nonce. It then reconstructs
missing transfer intents. This is repair-by-list-order, not a durable concurrency
guarantee and not a safe resolution rule for reorg conflicts.

## 6. Current nonce and balance accounting

Nonce allocation is strict and sender-scoped. `get_next_nonce()` starts at `1`
and chooses the first value absent from both used and reserved sets.

- Used statuses: `included`, `settled`.
- Reserved statuses: `signed_pending`, `validated_pending`, `mempool`.
- Rejected, failed, and expired records do not reserve a nonce.
- Chain validation independently enforces contiguous sender nonces in block order
  and rejects duplicate `tx_id`, duplicate/low nonce, nonce gaps, nonzero fees,
  bad signatures, and overdrafts.

Final balance is recomputed from the selected chain. Pending outgoing reservation
is the sum of `amount + fee` for reserved records; pending incoming is display
only; `available_balance = final_balance - pending_outgoing`. There is no
persisted account-balance table. This avoids balance rollback writes during a
reorg, but correctness still depends on the pending transaction list containing
exactly one valid live claim per sender nonce.

The check and reservation are not atomic. Two processes can observe the same
next nonce and available balance, each append a transaction, and then race whole-
document saves. The result can be lost acknowledgement, conflicting reservations,
or last-writer-wins state.

## 7. Current transaction statuses and transitions

The declared native transaction statuses are:

`signed_pending`, `validated_pending`, `mempool`, `included`, `settled`,
`rejected`, `failed`, and `expired`.

There is also a separate `NativeTransferMessage` vocabulary: `draft`, `signed`,
`signed_pending`, `pending`, `rejected`, `included`, and `failed`. Persisted
compatibility transfer intents are not constrained to that vocabulary and in
practice mirror native transaction values such as `mempool` and `settled`. This
overlap is another reason to define one public projection over more precise
internal state instead of retaining two loosely enforced status lists.

The status updater has no transition matrix. It accepts any declared status after
shape validation (and preserves invalid terminal records through a compatibility
fallback), so the application does not enforce terminality or legal predecessors.
Observed production transitions are:

| Status | Current producer/meaning | Observed transitions |
|---|---|---|
| `signed_pending` | Locally submitted signed record; temporary first state for peer receive | `signed_pending -> mempool`; direct `-> settled` is possible when a received block already contains it |
| `validated_pending` | Detached previously settled transaction; compatibility demotion from mempool helper; temporary state when reconstructing a block transaction | `validated_pending -> mempool`, `-> settled`, or `-> rejected` |
| `mempool` | Local selectable mempool membership | idempotent `-> mempool`, `-> settled`, or `-> rejected` |
| `included` | Declared, treated as nonce-used and transaction-final by helper sets, and displayed by serializers; this is not validator-quorum finality | No current write path was found |
| `settled` | Present in the currently selected chain, with block hash/height and settlement time | `settled -> validated_pending` when its block leaves the selected chain; idempotent settlement in the same block |
| `rejected` | Failed explicit revalidation or was skipped during block construction | No normal recovery transition, but the unguarded settlement path can change it to `settled` if a valid canonical block contains it |
| `failed` | Declared compatibility terminal state | No current producer found |
| `expired` | Declared compatibility terminal state | No current producer found |

`transfer_intents` duplicate the transaction status for local transactions and
are updated when an intent exists. Peer-received and chain-reconstructed
transactions need not have an intent until restart repair creates one. The
transfer serializer always reports `settlement_state = non_final`, even for a
settled intent; the transaction serializer reports only `non_final` or `settled`
and does not consult block confirmation/finality.

## 8. Current mempool behavior

The mempool is not a separate collection. It is the subset of
`native_transactions` whose status is exactly `mempool`.

Admission revalidates canonical identity, exact signed message, signer, Protocol
v1/network, zero-fee policy, strict next nonce, and available balance, then sets
`mempool` and `admitted_at`. Listing order is `admitted_at` (falling back to
updated/created time), sender, numeric nonce, and `tx_id`.

Block selection considers both `validated_pending` and `mempool`, sorts by
sender, nonce, and `tx_id`, rebuilds balances/nonces from the selected chain,
and sequentially simulates each candidate. It skips already-settled IDs, invalid
objects, unsupported legacy versions, wrong nonces, and overdrafts. A maximum
transaction count truncates selection.

During block acceptance, selected transactions become `settled`. Skipped
transactions other than `already_settled` become `rejected`. Explicit or startup
revalidation checks only records in `mempool`; invalid records become `rejected`.
Detached `validated_pending` records are not checked by that revalidation loop,
although they remain balance/nonce reservations and block candidates.

## 9. Current peer delivery and deduplication

### 9.1 Message construction and authentication

Manual broadcast serializes the transaction's canonical signed fields, version
tuple, and local status/timestamps, wraps it with origin node and runtime network,
then posts sequentially to every active peer at
`/peers/transactions/receive` with a three-second timeout.

With signed peer messages enabled, Protocol v1 authenticates a canonical HMAC-
SHA256 envelope with explicit message type `native-transaction`, canonical
network ID, sender node ID, timestamp, and random peer nonce. The receiver checks
message version, protocol version, message type, network, timestamp window,
message ID, HMAC, replay state, and claimed node identity. Inner transfer
validation remains mandatory. Legacy shared-secret authentication is an explicit
configuration alternative, not a per-request fallback.

Peer replay deduplication is transport-level. It persists accepted message IDs
and `(sender_node_id, peer nonce)` entries in a dedicated atomic JSON replay-state
file. Transaction-level deduplication is separately application-level by
`tx_id`; a duplicate returns accepted with `duplicate: true`. A different
transaction using the same live sender nonce returns HTTP 409.

### 9.2 Delivery semantics

There is no automatic gossip, relay, fanout queue, background retry, delivery
lease, durable acknowledgement, or peer catch-up scheduler. A manual broadcast:

- attempts each currently active peer once, synchronously and sequentially;
- labels any HTTP response below 400 as `sent`;
- defaults missing response field `accepted` to true;
- records the peer's duplicate/status fields only in the immediate response;
- catches transport request errors, but persists no failure for retry;
- returns `broadcasted: true` even if no peer accepted it;
- leaves the local mempool record intact on peer failure.

The mempool summary/fetch helpers can pull missing IDs from a peer, but they are
not a durable delivery protocol and their admitted records are not saved.

For a future retry, the logical delivery must continue to refer to the same
`tx_id`, while each HTTP attempt must generate a fresh peer timestamp, peer
nonce, message ID, and HMAC. Reusing the exact Protocol v1 peer envelope would
correctly fail replay protection.

## 10. Current block, fork-choice, and reorg behavior

Candidate chains are fetched from genesis, checked against advertised network,
Protocol version, genesis, height, and tip hash, and validated block by block.
Fork choice ranks valid same-genesis chains by cumulative originality score,
then height, then lower tip hash. The node stores only the selected chain, not a
durable side-branch set.

Milestone 3 certified local commits are atomic and expected-head guarded. Peer
candidate adoption is different: it replaces the in-memory chain, recomputes
reward pool state, reconciles submissions and native transactions, and performs
one generic whole-state save. Direct `Blockchain.replace_chain()` performs the
same core reconciliation but does not save by itself.

### 10.1 Transactions

For every locally stored `settled` transaction whose block hash is absent from
the new chain, reconciliation changes it to `validated_pending` and clears its
block hash, height, and settlement time. Transactions in the new chain are then
recorded if missing and marked `settled`.

This recovers an orphaned transaction as a reserved future block candidate, but
does not restore `mempool`, does not set a reorg reason/history, and does not
resolve a conflict when the new chain spends the same sender nonce with another
`tx_id`. Both records can remain live. On restart, list-order repair can discard
the new canonical record and retain the detached pending record, leaving
transaction lookup inconsistent with the chain.

### 10.2 Balances

Final balances are derived from the replacement chain, so orphaned transfers and
rewards stop affecting final balance and new canonical ones take effect. Pending
outgoing is independently derived from reserved records; unresolved detached
transactions can therefore reduce available balance even when a conflicting
canonical transaction has consumed their nonce.

### 10.3 Nonces

Block validity derives next nonce from canonical block order. API nonce state,
however, unions native-record used and reserved statuses. A detached settlement
becomes reserved. If the candidate contains a conflicting transaction at that
nonce, the old record is not rejected/superseded atomically, so reported
reservation detail can conflict with canonical consumption.

### 10.4 Creator rewards

Creator reward records are derived from reward metadata/transactions in the
selected chain. Replacing the chain removes orphaned creator rewards from API
views and balance calculation and adds candidate-chain rewards. The reward pool
is recomputed from the selected chain. No independent creator-reward row needs
rollback, but generic chain adoption is not one expected-head-guarded database
transaction.

### 10.5 Voter rewards

Settled voter reward records are likewise derived from `voter_rewards` embedded
in selected blocks and disappear/reappear with chain selection. Pending voter
reward eligibility is recalculated from retained submission/vote/certificate
state and the selected chain's settled reward IDs. Reconciliation does not keep
an explicit orphan/recredit ledger; deterministic IDs and chain derivation are
the current protection.

### 10.6 Finality metadata

`finality_attestations` and `finalized_blocks` are persisted separately from the
chain. Fork choice rejects any candidate that omits or changes a persisted
finalized height/hash, so finalized blocks cannot be reorged by the current
selection path. Candidate chains may extend those exact anchors.

Attestations for non-finalized blocks are not pruned when an unfinalized branch
is replaced. They remain stored but are ignored when deriving another block's
state. Finalization evidence is validated against the canonical chain on restart.
This is safe for the finalized anchor but leaves stale noncanonical attestation
data without an explicit lifecycle.

## 11. Recommended durable lifecycle

One overloaded status should not represent validation, mempool membership,
canonicality, finality, and peer delivery. The recommended model has three
separate state machines.

### 11.1 Transaction lifecycle

Recommended durable internal transaction states:

1. `PENDING_VALIDATED`: canonical identity, signature, network, nonce claim, and
   funds reservation were committed atomically. This is the first state eligible
   for API acknowledgement.
2. `CANONICAL_INCLUDED`: the transaction is in the selected chain. Its block
   identity and position are authoritative; balances and consumed nonce derive
   from that chain.
3. `REJECTED`: validation or policy made the transaction ineligible before
   inclusion. Store a stable reason and rejection time.
4. `SUPERSEDED`: a reorg or canonical conflicting nonce means this otherwise
   valid transaction can no longer claim that nonce. This is distinct from an
   intrinsically invalid transaction.

`RECEIVED_UNCOMMITTED` may be used as an in-process stage but must never be
returned as accepted. `FINALIZED` should be a derived transaction view from the
containing block rather than a freely mutable transaction row status. Mempool
membership should be a separate admission field or table with states such as
`READY`, `DEFERRED`, and `NONE`, not the canonical transaction lifecycle field.

Recommended public lifecycle:

- `PENDING`: valid, durable, and not canonical.
- `INCLUDED`: canonical but below confirmation depth.
- `CONFIRMED`: canonical and at or above confirmation depth, without quorum
  finality.
- `FINALIZED`: containing canonical block has persisted valid quorum evidence.
- `REJECTED`: maps internal `REJECTED` and `SUPERSEDED`, with a reason/category.

If compatibility requires only `PENDING / CONFIRMED / FINALIZED / REJECTED`, map
canonical-but-unconfirmed transactions to `PENDING` and expose `canonical=true`,
block identity, and confirmation count. Adding `INCLUDED` is clearer and matches
the already declared vocabulary without claiming premature confirmation.

Legal transitions should be enforced, not inferred from arbitrary string writes:

- `PENDING_VALIDATED -> CANONICAL_INCLUDED`
- `PENDING_VALIDATED -> REJECTED`
- `PENDING_VALIDATED -> SUPERSEDED`
- `CANONICAL_INCLUDED -> PENDING_VALIDATED` only after a reorg and only if the
  nonce is free on the new canonical chain
- `CANONICAL_INCLUDED -> SUPERSEDED` when the new chain canonically consumes the
  same sender nonce with another transaction
- public confirmation/finality advances or retreats only as allowed by the
  containing block; persisted finalized anchors never retreat

### 11.2 Block acceptance/finality lifecycle

Keep this derived from selected chain and finality evidence:

`NONCANONICAL/UNKNOWN -> CANONICAL_UNCONFIRMED -> CONFIRMED -> FINALIZED`.

An unfinalized canonical block may become `ORPHANED`. A finalized block may not
become orphaned through valid fork choice. Transaction public state must be
projected from this lifecycle rather than copying finality into a transaction
status string.

### 11.3 Peer-delivery/outbox lifecycle

Create one durable delivery record per `(tx_id, peer_node_id)`:

- `QUEUED`
- `IN_FLIGHT` with a renewable lease
- `ACKNOWLEDGED` only after a valid 2xx body explicitly says `accepted: true`
- `RETRY_WAIT` with attempt count, last error, and `next_attempt_at`
- `DEAD_LETTER` after the configured terminal policy
- `CANCELLED` if the transaction becomes rejected/superseded before delivery

Transport attempts and transaction state are independent. A transaction remains
valid and pending while one peer delivery waits for retry. Duplicate peer
acceptance is a successful acknowledgement. HTTP success without a valid body is
not an acknowledgement.

## 12. Proposed Milestone 4 invariants

### 12.1 DATABASE-LEVEL invariants

These must be implemented as SQLite schema constraints/transactions for the
production backend, not only checked by Python:

1. `native_transactions.tx_id` is the primary key and immutable.
2. Canonical signed identity fields are `NOT NULL` where required; version,
   lifecycle, amount representation, and nonce representation have `CHECK`
   constraints appropriate to the normalized stored form.
3. A dedicated live nonce-claim table has primary key `(sender, nonce)` and a
   unique foreign key to `tx_id`. Pending reservation and canonical consumption
   replace each other inside one transaction; two live claims cannot commit.
4. A transaction row, transfer-intent compatibility row, nonce claim, mempool
   row, and initial outbox fanout are committed atomically before API acceptance.
5. Mempool membership has `tx_id PRIMARY KEY/FK`, a constrained admission state,
   deterministic admission sequence/time, and no row for rejected, superseded,
   or finalized-ineligible transactions.
6. Canonical inclusion has foreign keys to transaction and block identity, a
   unique `(block_hash, transaction_index)`, and exactly one canonical inclusion
   per `tx_id`.
7. Outbox has `UNIQUE(tx_id, peer_node_id)`, constrained delivery status,
   nonnegative attempt count, next-attempt/lease fields, and durable last result.
8. Transition/audit rows are append-only and uniquely ordered per transaction or
   carry a monotonic version used for compare-and-swap updates.
9. Canonical head replacement, inclusion projection, nonce claims, mempool
   recovery, reward projections, and reorg transitions commit in one
   `BEGIN IMMEDIATE` transaction with expected-head/version validation.
10. Existing canonical claim constraints for block heights, certificates,
    canonical transaction IDs/nonces, and reward IDs remain enforced.
11. Finality evidence remains unique by height and must reference the exact
    canonical block. A canonical replacement cannot delete/change a finalized
    anchor.
12. Foreign keys are enabled and migrations are transactional, versioned, and
    idempotent. Startup refuses a partially migrated schema.

JSON cannot provide relational database-level guarantees. If retained for
development/export, it must provide semantic parity through a process-safe lock,
expected document version, complete invariant validation, fsync/atomic replace,
and deterministic recovery. Public deployment should use SQLite as already shown
in the deployment example.

### 12.2 APPLICATION-LEVEL invariants

1. Protocol v1 signing bytes, `tx_id`, network binding, amount/fee/nonce rules,
   block transaction serialization, transaction ordering, and signature recovery
   remain unchanged unless a separately versioned protocol change is approved.
2. No API or peer route returns accepted until the transaction and its live nonce
   and funds reservations are durable.
3. Every ingress path calls one idempotent durable admission operation; API,
   peer receive, pull sync, restart recovery, and reorg recovery cannot maintain
   separate partial implementations.
4. Same `tx_id` plus identical immutable content is idempotent. Same `tx_id` plus
   different immutable content is corruption/conflict. Same live sender nonce
   plus different `tx_id` is a deterministic conflict.
5. Available balance is computed from one canonical snapshot plus committed live
   outgoing reservations. Pending incoming never increases spendable balance.
6. Mempool selection revalidates against the expected canonical head and applies
   deterministic sender/nonce/`tx_id` order. Selection alone does not settle.
7. Block commit atomically changes inclusions, nonce claims, mempool membership,
   transaction lifecycle, rewards, submissions, and canonical head.
8. Reorg recovery deterministically classifies every detached transaction:
   requeue when still valid and nonce-free; keep canonical when present on the
   new chain; mark `SUPERSEDED` when its nonce is canonically consumed; reject or
   defer when balance/policy no longer permits it. It never leaves two live nonce
   claims.
9. Public status is derived from transaction lifecycle plus containing block
   state. `CONFIRMED` and `FINALIZED` are never aliases for local mempool or mere
   canonical acceptance.
10. An outbox record is created in the same commit as local admission. Delivery
    retries are at-least-once; receiver processing is idempotent by `tx_id`.
11. Every retry creates a fresh Protocol v1 peer envelope while preserving the
    same logical transaction/delivery identity.
12. A peer acknowledgement is valid only when authenticated transport succeeded
    and a schema-valid body explicitly confirms the expected `tx_id` and
    `accepted: true` (including duplicate acceptance).
13. Peer delivery failure never rolls back a valid local transaction. Transaction
    rejection/supersession cancels outstanding delivery safely.
14. Restart reconstructs identical canonical balances, nonces, lifecycle views,
    mempool ordering, and eligible outbox work for JSON and SQLite.
15. All transition functions are explicit and reject illegal predecessors;
    direct arbitrary status string updates are removed from operational paths.

## 13. Protocol v1 compatibility constraints

Milestone 4 durability work can be backward-compatible because status, admission
timestamps, database rows, and delivery attempts are local metadata excluded
from the Protocol v1 `tx_id` and block transaction payload.

The following must not change without a new protocol version or freeze update:

- canonical transfer signing message and domain;
- transaction identity fields and hash algorithm;
- signature recovery semantics;
- canonical network ID resolution;
- block-embedded native transaction schema and ordering;
- chain validation, originality fork-choice ranking, Model A media commitment,
  and validator finality evidence semantics.

Peer compatibility needs care. Existing `native-transaction` requests are
already authenticated over their exact body. The receiver can become durable and
idempotent without changing that body. A richer acknowledgement may be additive,
but senders must validate it conservatively. Any new delivery ID placed inside
the authenticated body, new route/message type, or changed canonical peer
payload requires an explicit compatibility design and may require a peer-message
version change. Outbox retry must never reuse a previously accepted peer nonce.

Legacy versionless transactions remain readable but must not gain Protocol v1
mempool eligibility. Migration must preserve stored legacy IDs rather than
recomputing them under Protocol v1.

## 14. Exact implementation plan for Tasks 4.2–4.10

The repository does not currently contain named Task 4.2–4.10 specifications.
The following is the recommended numbered decomposition and dependency order for
the remaining milestone.

### Task 4.2 — Normalize durable transaction storage

- Add schema versioning and normalized SQLite transaction, nonce-claim, mempool,
  inclusion, transition, and outbox tables with the constraints in section 12.
- Add repository methods that operate inside a caller-owned database transaction.
- Build an idempotent JSON-section-to-row migration and parity export path.
- Do not change Protocol v1 transaction bytes or IDs.
- Add schema, constraint, rollback, migration, and identical-replay tests.

### Task 4.3 — Atomic admission and reservation

- Replace list-based check-then-append with one durable admission command used by
  local submit, explicit admit, peer receive, and pull sync.
- Atomically validate the expected canonical head/account view, insert or resolve
  the transaction, claim `(sender, nonce)`, reserve outgoing funds, create the
  compatibility intent, and return only after commit.
- Add concurrent same-ID, same-nonce, and overspend tests across processes and
  both supported storage modes.

### Task 4.4 — Enforce lifecycle and public projections

- Introduce explicit transition functions and separate transaction, mempool, and
  canonical block/finality state.
- Migrate legacy status strings deterministically and retain read compatibility.
- Derive public `PENDING/INCLUDED/CONFIRMED/FINALIZED/REJECTED` from the new state
  and containing block; correct transfer-intent settlement projection.
- Add transition-table, API compatibility, confirmation, and finality tests.

### Task 4.5 — Durable mempool and restart recovery

- Make mempool membership durable, independently queryable, deterministically
  ordered, and bound to the current canonical state version.
- On startup, revalidate every live pending state, not only old `mempool` strings;
  release invalid reservations and record stable reasons.
- Add crash-after-admission, restart, stale-head, capacity, ordering, and
  JSON/SQLite equivalence tests.

### Task 4.6 — Transaction outbox and automatic propagation

- Create per-peer outbox entries atomically with admission and when active peer
  membership requires new fanout.
- Add a bounded worker/operation that leases due rows and sends existing Protocol
  v1 `native-transaction` messages with fresh authentication data per attempt.
- Keep manual broadcast as an operator-triggered enqueue/flush compatibility API,
  not the source of truth.
- Add enqueue atomicity, crash-before-send, crash-after-send, and no-peer tests.

### Task 4.7 — Acknowledgement, retry, and deduplication

- Define and validate the peer acknowledgement schema, including exact `tx_id`,
  accepted/duplicate result, receiver state, and stable rejection reason.
- Implement bounded exponential backoff with jitter, retry classification,
  leases, attempt history, dead-letter handling, and metrics.
- Preserve transport replay protection by regenerating peer envelopes; preserve
  transaction idempotency by retaining `tx_id`.
- Add lost-response, duplicate-delivery, timeout, malformed-2xx, 4xx terminal,
  5xx retry, lease-expiry, and multi-peer isolation tests.

### Task 4.8 — Atomic block inclusion and transaction finality views

- Extend the Milestone 3 certified commit transaction to consume normalized
  mempool/nonce claims and write canonical inclusion rows atomically.
- Make peer block acceptance use an equivalent expected-head durable command.
- Derive confirmations/finality from the containing block and keep finality
  evidence separate from transaction delivery.
- Add inclusion replay, commit fault injection, peer/local equivalence, and
  finalized transaction API tests.

### Task 4.9 — Atomic reorg recovery and canonical projection replacement

- Replace ad hoc reconciliation with one expected-head candidate-adoption
  transaction that rebuilds inclusions, balances/nonces (or their verified
  projections), rewards, submissions, mempool, and live reservations.
- Deterministically requeue, defer, reject, or supersede detached transactions;
  resolve sender-nonce conflicts in favor of the new canonical chain.
- Prune or mark noncanonical non-finalized attestations while preserving finalized
  anchors and exact evidence.
- Add reorg matrices for same transaction, conflicting nonce, changed balance,
  creator rewards, voter rewards, pending outbox, restart, and finalized-anchor
  rejection.

### Task 4.10 — End-to-end hardening and rollout

- Extend the real two-node harness across JSON/SQLite source-target combinations,
  restarts, dropped acknowledgements, peer outages, duplicate sends, and reorgs.
- Add process-kill/fault-injection coverage at admission, outbox lease/send/ack,
  block commit, and candidate adoption boundaries.
- Add migration dry-run/integrity tooling, deployment checks requiring SQLite for
  public testnet, outbox/retry observability, and operator recovery documentation.
- Run the focused and full backend suites plus the real two-node verification;
  freeze the final public/API compatibility contract before rollout.

## 15. Existing test coverage and remaining gaps

Current tests cover canonical transaction construction and golden vectors,
signature/network/nonce/balance validation, local admission and revalidation,
block selection/inclusion/settlement, invalid block rejection, peer auth and
transaction idempotency, manual partial broadcast failure, mempool summary/fetch,
chain fork choice, candidate-chain reconstruction of settled transactions,
JSON/SQLite helpers and rollback, mixed-backend two-node flows, restart chain
catch-up, atomic certified commit, creator/voter rewards, and validator quorum
finality/finalized-anchor rejection.

Important gaps are peer-receive durability, restart after peer admission, pending
database uniqueness, concurrent admission, lost-update prevention, durable
outbox/retry/ack, malformed-success acknowledgement, automatic gossip, detached
transaction conflict handling, reorg restoration of the mempool, stale
attestation lifecycle, atomic peer chain adoption, and transaction-level public
confirmation/finality.

## 16. Baseline commands and results

Targeted native-transfer, storage, peer-sync, fork/reorg, finality, and integration
baseline:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_native_transfer.py tests\test_protocol_v1_native_transfers.py tests\api\test_native_transfer_api.py tests\api\test_native_transaction_block_inclusion_api.py tests\api\test_native_account_api.py tests\api\test_peer_transaction_sync_api.py tests\api\test_peer_block_sync_api.py tests\api\test_chain_sync_api.py tests\services\test_task_8_native_ledger_mempool_reward_services.py tests\services\test_task_10_peer_network_services.py tests\storage tests\config\test_storage_backend_config.py tests\integration\test_two_node_storage_backends.py tests\integration\test_two_node_native_transfer_verification.py tests\integration\test_two_node_consensus_verification.py tests\blockchain\test_protocol_v1_lifecycle_finality.py tests\blockchain\test_task_3_5_validator_quorum_finality.py tests\blockchain\test_task_3_6_public_finality_status.py
```

Result: **294 passed in 38.46 seconds**.

The first full-suite invocation used the documented command:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Result: **1006 passed, 6 setup errors in 126.00 seconds**. All six were the same
environmental `PermissionError: [WinError 5]` while pytest tried to scan the
host directory `C:\Users\mattk\AppData\Local\Temp\pytest-of-mattk`; no test body
failed. The affected tests were:

- `tests/api/test_task_11_router_architecture.py::test_importing_application_and_routers_creates_no_repository_root_state`
- `tests/services/test_access_admin_services.py::test_service_records_round_trip_through_json_and_sqlite_storage`
- `tests/test_legacy_secp256k1_compatibility.py::test_wallet_round_trip_uses_temporary_storage_only`
- `tests/test_milestone_2_architecture.py::test_imports_do_not_create_repository_root_runtime_state[protocol_v1]`
- `tests/test_milestone_2_architecture.py::test_imports_do_not_create_repository_root_runtime_state[blockchain]`
- `tests/test_milestone_2_architecture.py::test_imports_do_not_create_repository_root_runtime_state[api]`

The unchanged full suite was rerun with a writable isolated pytest base:

```powershell
.\.venv\Scripts\python.exe -m pytest --basetemp 'C:\Users\mattk\.codex\visualizations\2026\09\05\01a0722f-c947-72c1-9e5a-8f747eed3fe6\pytest-task-4-1-baseline'
```

Result: **1012 passed in 130.60 seconds**. The backend baseline is therefore
green; the first result was a host temp-directory permission issue, not a broken
repository baseline.

## 17. Files changed and remaining risks

The only intended repository change for Task 4.1 is this document:

- `docs/milestone-4-native-transaction-audit.md`

No production code, protocol object, API behavior, storage schema, test, commit,
or remote branch was changed.

Remaining risks before Task 4.2 include acknowledged peer transaction loss,
multi-process stale-snapshot overwrites, non-atomic pending nonce/balance claims,
no delivery recovery, reorg nonce conflicts, public status ambiguity, continued
JSON runtime use, migration complexity for repaired/legacy records, and the need
to evolve peer acknowledgements without breaking the frozen Protocol v1 message
contract. The controlled validator-set and linear one-content-block commit
throughput risks from Milestone 3 also remain, but are outside Task 4.1 behavior.
