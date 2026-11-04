# Milestone 7 Task 7.17J — Isolated durable validator signer

Date: 2026-10-26 (America/New_York). **Inactive, test-only, bounded safe subset.**
This implements durable signing guards and recovery, not a Tendermint agreement
engine. It does not establish production BFT readiness or authorize activation.

## 1. Prerequisites and scope

Before editing, branch was `Compression-State-Bloat-and-Node-Economics`, HEAD
`54303b0a1aa2b13a1dd3a8f6f7a304e70dd7c9e2`, the separate commit
`Milestone 7 Task 7.17I: specify BFT wire formats and durable signer contract`.
The index, worktree and untracked-file inventory were completely clean.
The tracked 7.17H model, regression tests, broken-lock and lost-signer-state
negative controls were present. The 7.17I documentation includes all 21 signing
vectors, five proof recipes and the two independent reproduction programs.
No applicable repository/ancestor AGENTS.md was found; no agents were delegated.

Read the [7.17I contract](milestone-7-bft-wire-and-signer-contract.md),
[protocol decision](milestone-7-distributed-finality-protocol-decision.md),
[authority decision](milestone-7-validator-authority-and-quorum-decision.md),
[model report](milestone-7-tendermint-model-verification.md) and
[7.17E durability report](milestone-7-finality-durability-implementation.md).
Inspected wallet_signatures, canonical_v3 primitives, active SQLite utilities
and the existing isolated/model/durability test patterns.

| Contract category | Implementation or explicit gate |
| --- | --- |
| A: specified and implementable | Closed wire parsing, personal-sign verification, unique slots, reserve/sign/store/release, immutable journal replay, local exclusion and fault recovery |
| B: synthetic parameters | Explicit test M/D/G, N4/f1/q3/epoch0, random disposable keys, pinned 7.17H Block flags and rollbackable witness emulator |
| C: agreement integration | Timer expiry, round catch-up, justified-proposal signing, late valid learning, finalized/application promotion and height advancement refuse `INCOMPLETE_AGREEMENT_CONTEXT` |
| D: external custody | Production key loading/storage, enforced nonrollbackable witness/HSM, cross-host fencing and operational recovery remain blocked |

Only height 1 / round 0 can create new slots. Parsing and independent crypto
verification support the full bounded message coordinates and valid-round
grammar; parsing a future message does not authorize its signing. No general
agreement scheduler, timeout implementation, decision processor or network loop
exists. The supported guards are a deliberately restricted subset of the frozen
reference, never a replacement consensus protocol.

## 2. Files and isolation

All delivered paths are new; no existing tracked source or vector is modified.

| Path | Purpose |
| --- | --- |
| `isolated_bft717j/__init__.py` | Inactive namespace with no startup hooks |
| `isolated_bft717j/wire.py` | Closed wire grammar, context, hashing, full-key signature/proof verification |
| `isolated_bft717j/reducer.py` | Trusted bounded guard checks and deterministic symbolic validation |
| `isolated_bft717j/custody.py` | Memory-only random TestKey, local OS owner lock, separate witness emulator, SQLite connection profile |
| `isolated_bft717j/signer.py` | Immutable journal, replay, reservation/sign/store/release and recovery |
| `isolated_bft717j/schema.sql` | Exact disposable signer SQL schema |
| `tests/test_milestone_7_task_7_17j_durable_signer.py` | Crypto, concurrency, crash, corruption and fault tests |
| `tests/fixtures/bft717j/vectors.json` | Unmodified output of 7.17I's embedded generator; only public/insecure test material |
| `verification/bft717j/oracle.cjs` | Verbatim independent JavaScript oracle from 7.17I Appendix B |
| `verification/bft717j/fault-results.json` | Machine-readable observed fault outcomes |
| `verification/bft717j/verification-results.json` | Final test inventory and artifact hashes |
| This document | Implementation contract, evidence and remaining gates |

The test checks that active tracked Python modules do not refer to this namespace
and that active finality, storage, wallet signatures, canonical_v3 and 7.17H
sources/fixtures remain identical to HEAD. There is no public API route or
automatic import. No live databases, validator membership, keys, deployments,
compression formats, chain disposition or history policies were changed.

## 3. Exact messages and cryptography

`J` reuses the unchanged v3 strict JSON parser and canonical serializer, adding
the consensus-only printable ASCII restriction. Received bytes must already
equal sorted-key compact UTF-8 JSON. Size and depth are bounded before JSON
construction; bounded byte sizes also bound token/container counts. Duplicate
keys, unknown/missing fields, floats, bool-as-integer, noncanonical escapes,
negative zero, BOM, invalid UTF-8, non-ASCII strings and unsupported versions
reject. Parsing never repairs input. Application block3 parsing is unchanged.

The common payload is exactly `{agreement_profile_digest,block_height,
genesis_hash,message_version,parent_hash,round,validator_epoch,validator_id,
validator_set_commitment}`. Votes add `{block_hash,step}`; proposals also add
`valid_round`. Proposal `step=propose`, hash non-null, scheduled compressed key;
vote `step=prevote|precommit`, hash H64 or explicit null. Missing hash never means
nil. Height is 1..9007199254740991, round 0..2147483647, valid_round -1 or below
the proposal round. Epoch is exactly integer zero.

Envelope keys are exactly `{domain,network_id,object_type,payload,protocol,
protocol_version}`. Protocol is zoidbergchain, protocol_version=2,
message_version=1. Purpose pairs are `zoidbergchain/bft-proposal/v1` / bft-proposal
and `zoidbergchain/bft-vote/v1` / bft-vote. Signed keys are exactly
`{envelope,signature,signature_scheme}`, scheme personal_sign. Closed PV, Q4 and
RE wrappers verify strict sender order, distinct keys, quorum/commitment context
and constituent signatures. Q4 validation here is its **crypto core only**;
it cannot promote finality or assert complete application/genesis validation.

For raw message m=J(E), message_id=SHA256(m). Prefix is byte 19 hex, ASCII
`Ethereum Signed Message:`, one LF byte, ASCII decimal byte_length(m).
The signing digest is Ethereum Keccak256(prefix||m), using exactly one EIP-191
prefix. The adapter calls existing `Account.sign_message(encode_defunct(primitive=m))`.
Verification recovers the registered full compressed secp256k1 key and its
derived Ethereum ID. r/s/v bounds and lowercase spelling are strict. Mathematical
high-S variants remain valid, but do not replace the first durable signature.
No legacy signing helper, address normalization, CR/LF coercion, fallback scheme
or signature over diagnostic SHA256 text is accepted.

`TestKey` creates a fresh Account in memory; no production key-loading API or
key file exists. Multiprocess fixtures pass disposable key objects through
trusted local IPC, never disk or command-line arguments. Python object privacy
is conventional, not a hardware boundary. The fixture's scalar integers 1..5
are the explicitly public, insecure 7.17I vector material, not operational keys.

## 4. Exact durable schema and logical records

The complete executable SQL is [schema.sql](../isolated_bft717j/schema.sql).
There are six tables, without a migration or production-storage dependency:

| Table | Exact columns and constraints |
| --- | --- |
| authority | singleton INTEGER PK CHECK=1; namespace, manifest, agreement, test_catalogue BLOB NOT NULL |
| blobs | digest TEXT PK CHECK length=64; kind TEXT NOT NULL constrained to the contract BlobRef kinds; raw BLOB NOT NULL |
| events | sequence INTEGER PK CHECK>0; event_id TEXT NOT NULL UNIQUE FK blobs.digest; state_id TEXT NOT NULL FK blobs.digest |
| head | singleton INTEGER PK CHECK=1; record BLOB NOT NULL |
| slots | namespace_id TEXT, height INTEGER CHECK>0, round INTEGER CHECK>=0, purpose TEXT CHECK propose/prevote/precommit, slot_id TEXT FK blobs.digest; all NOT NULL; composite PK(namespace_id,height,round,purpose) |
| outbox | namespace_id TEXT,height INTEGER,round INTEGER,purpose TEXT,signed_id TEXT; all NOT NULL; same composite PK; signed_id UNIQUE FK blobs.digest; coordinate FK slots |

The private records use the exact 7.17I section 6 logical keys:

* NS: `{protocol,protocol_version,network_id,genesis_hash,
  agreement_profile_digest,validator_epoch,validator_set_commitment,
  validator_public_key,validator_id}`; namespace_id=SHA256(J(NS)).
* State: `{state_version,namespace_id,revision,fence_generation,height,round,
  phase,started,locked,valid,finalized,applied,inbox_tip,markers_tip,pending_slot,fault}`.
* Lock/valid: `{block_hash,round,proposal_id,prevote_certificate_id}`. Unset is
  null/-1/null/null. Genesis finalized is `{height:0,block_hash:G,proof_id:null}`;
  applied is `{height:0,block_hash:G}`. These anchors cannot advance here.
* Slot: `{slot_version,namespace_id,height,round,purpose,payload_hex,message_id,
  status,signature,before_revision,after_revision,evidence,block_record_id,
  validation_id,fence_generation}`. Status is reserved/signature=null or
  signed/Sig65. Before/after revisions always identify the original reservation.
* Receipt: `{record_version,previous,signed_id}`. Marker:
  `{record_version,previous,height,round,kind,status}`. Supporting inputs and own
  produced signed messages are retained in append-linked receipts. Initial
  non-proposer start records an armed propose marker; no expiry API is enabled.
* Event: `{record_version,namespace_id,sequence,previous,rule,before_state,
  after_state,evidence,slot}`. Head:
  `{record_version,namespace_id,sequence,event_id,state_id}`.
* BlobRef: `{kind,digest}`, sorted/distinct and at most 16 per evidence list.
  Both reservation and SIGN_STORED events contain a slot BlobRef for their
  exact immutable version. Earlier versions remain stored.

State/slot/record versions are 1. INIT commits revision1 from revision0; every
following safety mutation increments exactly once. Event and state are
content-addressed without circular pointers. Slots and outbox are derived
indexes and must exactly match replay. No parent, value, request ID, signature,
generation or evidence status is added to the signed-slot uniqueness key.

Recovery verifies SQLite integrity/foreign keys, pinned authority, all raw blob
hashes, all event/revision links, exact canonical schemas, supported reducer
outputs, evidence sources, signatures, receipts, markers, pending slot and
outbox/index equality. Rehashing a forged lock does not bypass reducer replay.
Missing rows/sources, invalid signatures, damaged files or unsupported events
disable signing. There is no delete/prune/reset/repair API. A damaged journal
cannot safely accept a new FAULT event; it stays unavailable rather than trying
to repair itself. Fault-accepting/finality-conflict processing is gated with
the absent agreement adapter; the supported reducer keeps State.fault=null.

## 5. Guard/evidence and lock boundaries

The trusted bootstrap catalogue pins exact 7.17H Block objects: id, height,
parent and six Boolean flags. It is not request evidence and cannot be replaced
on reopen. A request selects a known block; the reducer recomputes the exact
TestValidation record specified by 7.17I from the pinned object. All flags true
means VALID; a complete false flag means INVALID. Missing fixture data means
INCOMPLETE_DATA, never fabricated invalidity. Production application validity,
source-history completeness and decoder outcomes are not implemented here.
Mutating a returned parsed catalogue cannot change the pinned validity inputs.

| Enabled guard | Required evidence and durable effect |
| --- | --- |
| START proposer | Initial h1/r0, scheduled key, valid fixture, vr=-1; reserve exact proposal and mark started |
| START other validator | Initial h1/r0; persist started and armed propose marker; no signature |
| L22 fresh proposal | Authenticated scheduled proposal, vr=-1, complete pinned block; sign H only if valid and lock predicate passes, otherwise nil; record prevote once and phase |
| L36 non-nil precommit | Prevote phase, current authenticated proposal/full valid block, three distinct matching authenticated prevotes; lock+valid pair and polka/precommit once markers committed atomically with reservation |
| L44 nil precommit | Prevote phase, three matching authenticated nil prevotes; reserve nil and advance phase; preserve lock and valid fields |

No caller can supply State, Event, TestValidation, lock/unlock or valid-round
assertions to the signing interface. Supporting proposal/PV signatures are
independently checked. An unresolved reservation blocks all successor local
transitions; an exact retry completes only its retained bytes and sources.
An exact signed retry can return the stored result from an earlier phase.
Conflicting slot bytes reject CONFLICTING_SLOT. Foreign contexts reject before
key use, and reopening cannot rebind a key to another genesis/network/set/profile.

L28, timer expiry, L34/L47 timer arming, L49 finalization, L55/L65 round start,
late valid learning and height/application advance are gated. No arbitrary
unlock is possible. L44's preservation is implemented, but **reachable nil votes
after an earlier-round lock cannot be exercised by this bounded signer**.
The unchanged 7.17H tests cover that reference scenario abstractly. They are not
evidence of a durable round-change implementation. Slot uniqueness alone does
not imply Tendermint safety.

## 6. Transactions and release

1. Strictly parse and check identity/context. Hold the object's queue mutex and
   the identity's enforced local OS lock for all key operations.
2. BEGIN IMMEDIATE, replay authoritative state/indexes and reconcile witness.
   Refuse conflicting slots or unavailable guards. Reserve exact bytes with all
   immutable evidence, phase/once/lock/valid changes, pending slot, state/event/head.
3. COMMIT the reservation. Reopen on a fresh owned connection, validate complete
   history, and reconcile its exact head with the separate test witness.
4. The trusted signer authorizes only that reserved digest at the active
   generation, then privately produces and verifies the signature.
5. A second BEGIN IMMEDIATE reloads and checks the same reservation/head/fence.
   Persist a new signed Slot version, authentic own Receipt, exact J(Signed)
   outbox, cleared pending slot and SIGN_STORED state/event/head. COMMIT.
6. Reopen, replay and witness that committed head. Only retained outbox bytes can
   be returned or passed to the publication callback. Lost acknowledgement
   returns the identical bytes on retry, with no new key invocation/history edit.

No signature bytes are passed to fault hooks before publication. A local error
after reservation/signing withholds output and makes the object unavailable;
explicit validated recover or a new exclusive owner is required. CryptoFailure
is separate from SQLite errors and symbolic INVALID. COMMIT failure is not
assumed to mean rollback; a fresh recovery distinguishes absent/reserved/signed
outcomes. Connection cleanup rolls back any still-active transaction and closes
it, including actual COMMIT-busy behavior. No connection is reused after failure.

## 7. Ownership, witness and impossible guarantees

LocalOwner holds a nonblocking Windows byte-range lock (POSIX flock fallback)
in a shared explicit custody directory, keyed by the full compressed public key.
Independent objects/processes sharing that authority conflict immediately.
SQLite write transactions and an object mutex serialize independent connections
and concurrent callers. Locks do not expire. Process death releases the OS lock.
All cooperating owners must use the same custody directory and local filesystem.

The separate **rollbackable TestWitness** pins namespace/full key and stores
generation plus exact Head. Its singleton table is:
`(singleton INTEGER PRIMARY KEY CHECK(singleton=1),namespace TEXT NOT NULL,
public_key TEXT NOT NULL,generation INTEGER NOT NULL,head BLOB NOT NULL)`.
Reconcile checks the stored head against the exact retained journal prefix before
advancing through its validated continuation. Behind/divergent histories refuse.
On explicit reopen, claim advances the generation and the journal appends FENCE
without changing locks, values, anchors or pending reservation bytes. Pending
slots retain their original generation. Interrupted claims may leave a generation
gap; a new exclusive owner can fence again while preserving the exact history.
An existing owner cannot adopt another or lower generation through recover.

Tests demonstrate stale signer-only restoration rejection, same-head generation
revocation and exact pending recovery under a new process owner. Joint rollback
of signer and witness permits a conflicting signature in the deliberate
negative-control test. This is an observed limitation, not a rollback-resistance
pass. A copied custody directory/key on another machine likewise evades local
exclusion. The Python key adapter is trusted test code with exportable memory;
it is not an enforced remote key service. No multi-host/production failover,
nonrollbackability, physical power-loss or arbitrary-filesystem guarantee is made.

## 8. SQLite operating profile

Observed: CPython 3.13.5, SQLite **3.49.1**. Both signer and test-witness stores
require existing DELETE journal mode, synchronous=EXTRA (3), foreign_keys=ON and
busy_timeout=30000 ms, all read back. Adversarial busy tests explicitly use 1 ms
on disposable instances. Connections are owned by one operation/thread, use
normal SQLite thread restrictions, close explicitly and are never shared.
Authoritative reads/mutations use BEGIN IMMEDIATE. Bootstrap is explicit, refuses
existing signer/witness state and uses exclusive file creation. Recovery uses
mode=rw, so missing databases are never silently recreated.

The signer does not enable WAL or convert an existing journal. A disposable
foreign-mode fixture checks refusal; the existing affected-WAL-runtime guard is
also regression-tested. No WAL crash verification is claimed. Local locking,
SQLite rollback-journal recovery and truthful OS/device flushes are assumed;
process termination is not a physical power-loss test. There is no atomic
transaction across signer and witness files: uncertain cross-file outcomes
withhold signing until validated reconciliation succeeds.

## 9. Verification and reproduction

Final test totals and hashes are in
[verification-results.json](../verification/bft717j/verification-results.json).
Observed fault cases are in
[fault-results.json](../verification/bft717j/fault-results.json).
Final results: **381 passed, zero failures/errors/skips**: 125 focused tests;
36 Task 7.17E durability tests; 42 Task 7.17H model tests; 119 v3 canonical tests;
21 v1 golden/freeze/originality tests; 37 historical/active-finality tests; and
one affected-runtime WAL-refusal test. The last selection intentionally deselects
48 other atomic-certification cases; those are not counted as executed.
The focused suite verifies the byte tables and signatures against the unchanged
7.17I document, not just regenerated implementation expectations. It also runs
the verbatim independent JavaScript oracle in a disposable directory: **21
signing messages and five proof objects match**, including SHA256, Keccak,
full-key recovery, maximum widths, context mutations and high-S behavior.

Real parent-driven child termination covers before reservation COMMIT, after
reservation, after signing, before signature COMMIT, after signature COMMIT,
before publication, after publication/before response, and during the paired
lock/valid write. Additional precommit crash cases prove a committed lock/valid
pair survives the reservation/signature windows and supports only exact recovery.
An external observer captures actual published bytes for acknowledgement-loss
replay comparison. No child private-key files are written.

Fault tests include actual SQLITE_FULL, SQLITE_BUSY and denied COMMIT/SQLITE_AUTH
at both reservation and signature persistence, injected I/O failure, ambiguous
COMMIT/witness acknowledgements, concurrent duplicate/conflicting requests,
two-process signing attempts, stale backups, repeated recovery, revoked owners,
missing stores/sources, physical header corruption, forged rehashed lock state,
foreign authority restores and unexpected journal mode. Height/round/unlock/
late-valid/finalize/timeout adapters are tested to reject before writes; **there
is no implemented height-advance crash test**. No unimplemented scenario is
counted as exercised agreement behavior.

Reproduce from the repository root using fresh disposable basetemps:

```powershell
New-Item -ItemType Directory -Force temp/task717j-runtime | Out-Null
$env:TEMP=(Resolve-Path temp/task717j-runtime).Path
$env:TMP=$env:TEMP
$env:BFT717J_RESULTS=(Join-Path $PWD 'verification/bft717j/fault-results.json')
.\.venv\Scripts\python.exe -B -m pytest tests/test_milestone_7_task_7_17j_durable_signer.py -q --tb=short --basetemp=temp/task717j-repeat-focused --junitxml=temp/task717j-repeat-focused.xml
Remove-Item Env:BFT717J_RESULTS
.\.venv\Scripts\python.exe -B -m pytest tests/test_milestone_7_task_7_17e_finality_durability.py tests/test_milestone_7_task_7_17h_tendermint_model.py tests/test_milestone_7_task_7_10c_v3.py tests/test_protocol_v1_golden_vectors.py tests/test_protocol_v1_freeze_consistency.py tests/test_protocol_v1_originality_votes.py -q --tb=short --basetemp=temp/task717j-repeat-regressions
.\.venv\Scripts\python.exe -B -m pytest tests/test_milestone_7_task_7_17c_finality_audit.py tests/blockchain/test_task_3_5_validator_quorum_finality.py tests/blockchain/test_task_3_6_public_finality_status.py tests/blockchain/test_protocol_v1_lifecycle_finality.py -q --tb=short --basetemp=temp/task717j-repeat-active
.\.venv\Scripts\python.exe -B -m pytest tests/test_milestone_7_task_7_16_atomic.py -k affected_wal_runtime_is_refused -q --basetemp=temp/task717j-repeat-wal-guard
```

The 7.17H broken-lock/lost-state counterexamples remain tracked and unchanged.
Their expected failures and symbolic model passes are not proof of production
signer or distributed agreement safety. Earlier focused runs exposed a reserved
pytest parameter name and a tamper fixture blocked by a foreign key. Those test
setups were corrected without weakening safety assertions or changing vectors.

## 10. Readiness and final repository state

The bounded isolated prototype is ready for review and an owner-performed commit
of this scope; the final verification report is green. This is
partial Task 7.17J completion with explicit safety gates, as authorized by the
request; it is not completion of a general-purpose Tendermint signer.

Remaining blockers: independently reviewed full agreement reducer/refinement;
timer/round/late-valid/finalized-and-applied advancement adapters and their crash
tests; complete G2/combined application/history validity policies; selected
operators and approved NID/G; enforced production custody/nonrollbackable fencing;
filesystem/power-loss review; and separate activation approval. The reviewer-
history integration gate remains blocked. No Task 7.17K work begins.

Branch and HEAD remain the starting values. Final changes consist only of the
new files listed in section 2, untracked/unstaged; index and previously tracked
files remain unchanged. No commit, push, merge, production signing, consensus
activation, schema migration, chain reset or deployment was performed.
