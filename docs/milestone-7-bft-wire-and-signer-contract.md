# Milestone 7 Task 7.17I — BFT wire schemas and crash-safe signer contract

Date: 2026-10-26 (America/New_York). **Specification and targeted verification
only.** All requirements below describe a proposed, inactive profile. They do
not approve membership, change active consensus, activate canonical v3, create a
production signer, migrate a database, reset a chain or authorize deployment.

The byte grammar and private-state contract are precise enough for a separately
authorized **isolated, test-identity prototype**. Production signing, the
production agreement engine, public-testnet activation and Task 7.17 reviewer
history remain **BLOCKED**. Section 13 separates these gates. Actual operators,
keys, network/genesis identity and application/history policy are not selected.
Bounded 7.17H exploration is evidence, **not a formal correctness proof**.

## 1. Verified starting point and evidence

| Prerequisite independently checked before edits | Result |
| --- | --- |
| Branch | `Compression-State-Bloat-and-Node-Economics` — expected |
| HEAD | `5a8e32136d7703c4537ef96a8769fac43d06773c` |
| Index and worktree, including all untracked paths | Completely clean |
| Separate 7.17H model commit | `e64337cda01a511cefa075c92b25df14f803901f` |
| Separate 7.17H regression-test commit | HEAD, `Milestone 7 Task 7.17H: include Tendermint model regression tests` |
| Model and tests | `verification/tendermint717h/{model,check,replay,scenarios}.py`; `tests/test_milestone_7_task_7_17h_tendermint_model.py`, tracked and present |
| Retained verification | Report, summary, validation, six seeds and twenty scenario/negative-control traces, tracked and present |
| Negative controls | `trace-removed_lock_check.json`, `trace-lost_signer_state.json`, preserved without edits |
| Repository instructions | No applicable repository/ancestor `AGENTS.md` found; no delegation |
| Authorized persistent changes | This document; reference and current gate summary only in 7.17G |

Read the [protocol decision](milestone-7-distributed-finality-protocol-decision.md),
[authority/quorum decision](milestone-7-validator-authority-and-quorum-decision.md),
[model report](milestone-7-tendermint-model-verification.md),
[safety/remediation decision](milestone-7-finality-safety-and-remediation-decision.md),
[durability implementation](milestone-7-finality-durability-implementation.md) and
[canonical schema decision](milestone-7-v3-canonical-schema-decision.md). The
7.17D pre-repair findings are historical; 7.17E/source define current durability.

| Current code inspected | What it actually provides / adaptation required |
| --- | --- |
| `protocol_v1_finality.py`, `services/finality_service.py`, `wallet_signatures.py` | Active one-phase height/hash attestations, configured address membership and personal-sign recovery; no BFT signer or round engine. Input coercion/address normalization are not new-profile parsing rules. |
| `protocol_v1_genesis.py`, `validators.py` | Frozen genesis has no authenticated BFT roster. A syntactically valid public-key string is not authority. |
| `blockchain.py`: finality submission, persisted-state validation and cache publication | 7.17E transaction/reread/commit-before-publish discipline; does not supply private lock state, genesis membership or contiguous parent finalization. |
| `storage.py`: `_preserve_finality`, `_connect`, `atomic_update_blockchain_document` | Durable receiver vote/QC preservation and `BEGIN IMMEDIATE`, DELETE/EXTRA, busy timeout; no signer tables or copied-key fencing. Never reuse its unfinalized-vote reorg deletion for signer slots. |
| `canonical_v3/{primitives,block,media,transactions,finality,storage,admission}.py` | Inert closed block3, canonical hashing, original reconstruction, protected transactions, caller-trusted finality and isolated storage. These frozen modules remain unchanged and cannot parse the proposed combined block profile. |
| `codec_prototype/{isolated_decoder,strict_decoder}.py` | Bounded isolated reconstruction; local worker failure is distinct from deterministic invalidity. It is not full application admission or production isolation approval. |
| `verification/tendermint717h/model.py` | Symbolic authentication, atomic transitions and collision-free values; no actual wire, SQLite, hardware counter or cryptographic assurance. |

Normative agreement reference: [Buchman/Kwon/Milosevic, arXiv:1807.04938v3,
Algorithm 1](https://arxiv.org/pdf/1807.04938v3), printed page 6, lines 1–67.
Use its printed rules, not a different Tendermint/CometBFT variant. Assumptions:
authenticated unforgeable messages, common static authority, at most f faulty
power, collision-resistant value identity, atomic honest transitions and stable
application validity. Termination additionally needs eventual synchrony,
redistribution of messages known to correct processes, increasing waits, fair
processing and available valid input. Real validation/durable storage must
eventually complete. Outages and cloned/stale signers consume the fault budget.
No partition/asynchrony or input-free termination is promised.

## 2. Canonical primitives, contexts and closed version registry

This profile specializes equal power to **N=4, f=1, q=3**, pending owner approval.
7.17F's alternative N7/f2/q5 is not accepted by this profile. Membership is static,
epoch zero for the network lifetime. No removal, denominator change or epoch
advance follows evidence, time, height, restart or an administrative configuration.

`J(x)` is compact UTF-8 JSON, sorted ASCII object keys, array order preserved,
no BOM, whitespace or trailing newline. All strings in consensus and private
metadata below are restricted ASCII; they have no normalization or implicit
coercion. String quotes/backslashes escape as `\"`/`\\`; control characters
cannot occur in these fields. Every listed key is required, unknown keys reject,
duplicate JSON keys reject before construction, and received bytes must equal
`J(parsed)` exactly. Integer tokens use decimal without plus, leading zeros,
fraction, exponent or negative zero. Floats, booleans in integer fields,
NaN/infinity, invalid UTF-8, unpaired surrogates and noncanonical escapes reject.
Application block/source JSON retains its own canonicalization, not ASCII-only
consensus restrictions. Pre-scan size/depth/count limits before allocation/crypto.

| Type | Exact rule |
| --- | --- |
| UInt | Actual JSON integer, excluding bool, 0..9,007,199,254,740,991 (`U`) |
| Height | UInt 1..U; genesis anchor height is exactly 0 |
| Round | Integer 0..2,147,483,647 (`R`), retaining 7.17G's narrower bound |
| ValidRound | Integer -1, or 0..round-1; -1 means no valid-value justification |
| H64 | Exactly 64 lowercase hexadecimal ASCII characters, no `0x` |
| ID | Exactly `0x` followed by 40 lowercase hex characters |
| Key | 66 lowercase hex, valid finite SEC1 compressed secp256k1 point, prefix 02/03 |
| NID | 3..64 ASCII characters matching `[a-z0-9][a-z0-9-]{2,63}` over the entire string |
| Sig65 | `0x` + 130 lowercase hex; decoded r32, s32, v1; 1<=r,s<n; v=27/28 |
| HashOrNil | H64 or JSON `null`; null is required for nil, never missing/empty/zero hash |

`n=fffffffffffffffffffffffffffffffebaaedce6af48a03bbfd25e8cd0364141` is the
secp256k1 group order. A 64-zero H64 is still a supplied hash; it never means nil
and cannot authorize a nonexistent block. No wrapped integer or saturation may
produce another slot. Round, height, revision or counter exhaustion stops signing;
the mathematical infinite-run termination claim does not extend beyond these
finite limits. Compute proposer index as `((h-1)%4 + r%4)%4`, without overflowing
an intermediate sum in a limited-width implementation.

Closed version registry for this proposal:

| Object | Version / dispatch |
| --- | --- |
| Manifest M | membership_version=1, protocol_version=2, static-genesis-v1 |
| Agreement descriptor D | agreement_version=1, protocol_version=2 |
| Proposal / vote | message_version=1, protocol_version=2, new purpose domains |
| Prevote certificate PV | certificate_version=1, contains prevotes only |
| Commit proof Q4 | proof_version=4, contains scheduled proposal and precommits |
| Round evidence RE | evidence_version=1, wrapper over existing message types |
| Private journal | state/slot/record version 1, never a network consensus phase |

These versions do not reinterpret active v1, isolated block3/v2 finality, or
7.17F's authority-only A3/Q3 draft. No negotiation/downgrade to old signatures.

### 2.1 Manifest, agreement descriptor and noncircular commitments

M has exactly the following ten fields (same encoding as 7.17F):

```text
{domain:"zoidbergchain/validator-set/v1", membership_version:1,
 protocol:"zoidbergchain", protocol_version:2, network_id:NID,
 authority_profile:"static-genesis-v1", validator_epoch:0,
 byzantine_fault_budget:1, required_quorum:3,
 validator_public_keys:[K0,K1,K2,K3]}
```

Keys must arrive in strictly increasing unsigned compressed-key byte order.
Reject duplicates, invalid points and duplicate derived IDs; do not sort or
deduplicate received input into validity. Each has weight one. Decompress
`04||x32||y32`; `ID(K)="0x"||lowerhex(last20(Keccak256(x32||y32)))`.
`C=lowerhex(SHA256(J(M)))`. Keep full M on chain in the proposed G2 authority
field. C/M are not signed by their own alleged validators to bootstrap authority.
Only independently approved pinned genesis can authorize them.

D has exactly the fields and literals in Appendix A's descriptor, except
`application_policy_digest` is the H64 commitment to the future complete approved
immutable application/history policy registry. `limits` is the exact closed
twelve-field object there; numerical constants
are fixed, not configurable per request. `A=lowerhex(SHA256(J(D)))`. D commits
this document's versioned grammar, printed-rule selection, proposer/parent,
timeout and signer contracts by the exact profile identifiers shown. Any change
to those contracts requires a new identifier/version and vectors, not editing
the meaning under an old A. Retain D and its full policy sources alongside M.

The fixture uses policy digest `55` repeated 32 bytes; this is an explicit
synthetic input, not a hash of approved launch policy. Actual policy registry,
full G2 genesis serialization/domain and combined media/history block remain
BLOCKED for production. No approved G is fabricated here. Dependency order is:

```text
M -> C; complete application policy -> application_policy_digest -> D -> A
complete future genesis including M/C/D/A/policy -> G
canonical application block envelope -> H -> signed proposal/votes -> PV/Q4
```

M and D contain neither resulting G nor Q4. D need not include C: G binds both,
and messages sign G/C/A directly. G2 must commit full D and M and verify their
digests, not just accept supplied strings. An owner-signed external manifest
would be an alternative bootstrap trust requiring a separate decision/schema;
it is not this profile. Network reset needs a new approved NID/G and custody
retirement procedure; no reset is performed.

Policy-registry bytes committed through D must also be independent of resulting
G/A and descendant block/proof identities. Runtime validation can take pinned G
as a context parameter without embedding it in that pre-genesis policy digest.
A launch policy requiring a transitive self-reference is a G2/A freeze blocker,
not permission to substitute a partial genesis hash.

## 3. Exact consensus message inventory

Define the common **nine-field** payload K:

```text
K = {agreement_profile_digest:A, block_height:h, genesis_hash:G,
     message_version:1, parent_hash:P, round:r, validator_epoch:0,
     validator_id:ID, validator_set_commitment:C}
```

All hashes are H64. h/r have the bounds above. P is the actual finalized
parent's canonical identity at h-1; for h=1 it is G. Epoch must be integer zero.
Every field is required, non-null; receiving a foreign parent/context never
changes the signer's slot namespace.

```text
ProposalPayload = K + {block_hash:H, step:"propose", valid_round:vr}
VotePayload     = K + {block_hash:H_or_null, step:"prevote"|"precommit"}
E = {domain:Dpurpose, network_id:NID, object_type:Opurpose,
     payload:ProposalPayload|VotePayload,
     protocol:"zoidbergchain", protocol_version:2}
Signed = {envelope:E, signature:Sig65, signature_scheme:"personal_sign"}
```

`+` denotes disjoint object union, not byte concatenation. Proposal H is
non-null. Votes have exactly eleven payload fields; proposals twelve. There is
no optional timestamp, nonce, claimed public key, caller-supplied message string,
set list, next round or hidden signature payload.

| Purpose | Dpurpose | Opurpose |
| --- | --- | --- |
| Proposal | `zoidbergchain/bft-proposal/v1` | `bft-proposal` |
| Prevote or precommit | `zoidbergchain/bft-vote/v1` | `bft-vote` |

Only the scheduled proposer may authenticate a proposal; key order is M's order,
not address order. Vote signatures recover the exact full registered key AND its
derived ID. Context binds NID, G, protocol/message versions, A, C, epoch, h, r,
purpose, explicit H/nil and parent. Changing any field changes sign bytes.

### 3.1 Application data and supporting proof wrappers

Let T be a vote payload with exactly `validator_id` removed (ten fields).

```text
PV = {certificate_version:1, commitment:T_with_step_prevote,
      votes:[Signed,...]}
Q4 = {proof_version:4, commitment:T_with_step_precommit_and_nonnull_H,
      proposal:SignedProposal, precommits:[Signed,...]}
ProposalBundle = {proposal:SignedProposal, block:B, valid_round_proof:PV_or_null}
RE = {evidence_version:1, messages:[Signed,Signed]}
FinalizedRef = {block_height:UInt, block_hash:H64}
```

PV/Q4 arrays contain 3..4 entries in strictly increasing ID order, unique IDs;
every payload equals T plus that entry's ID. RE contains exactly two messages
from distinct IDs, ordered by ID, at the same full context/h/parent/higher round;
kinds may differ. It supplies f+1 evidence for line 55, not a signed round-change
vote. A process may construct RE from any qualifying two of its actual log
messages. No aggregate wrapper has its own producer signature or validator set.
PV can certify nil for line 44; only non-nil PV backs `valid_round`. Its votes
are authenticated even without block data; using it to lock requires proposal
and complete validity. RE carries no recursively nested block/PV/Q4.

B is the canonical application record object, not a JSON string or base64
encoding of the full record. Its exact serialized canonical bytes/hash must be
verified under the selected application profile. Embedded serialization must
preserve those bytes, including application Unicode; no double encoding or
unsigned rewrite. Bundle vr=-1 requires null proof; vr>=0 requires a non-nil PV
at vr, for the same H/h/P/NID/G/A/C/epoch. Missing required PV makes the complete
bundle incomplete, not a fabricated proof or proof of invalid media.

**Separate authenticated message admission from transition evidence.** A valid
SignedProposal can enter the reference message log without B or its old PV.
Likewise authenticated votes can be logged before data. Line 28 waits for actual
vr prevotes. Lines 36 and 49 do not add a requirement to validate the proposer's
old vr justification: they use their own current-round prevotes or same-round
precommits, proposal and `valid(B)`. RE/line55 never waits for application data
or PV. Requiring a complete bundle before counting any future-round message
would change the model/reference and can break catch-up. Receiving constituent
signed metadata or an already logged quorum satisfies the corresponding evidence;
a redundant malformed offered wrapper rejects as a wrapper, never erases valid
independently authenticated log messages.

Q4's signed proposal must match T's h/r/H/P/context, scheduled key and valid
vr range. Q4 does **not** embed its proposal's old PV or recursive lock history.
The paper's decision criterion needs proposal plus q matching precommits and
valid complete value. Full locking evidence is private safety/accountability
history, not an additional historical commit predicate invented here.

FinalizedRef is a closed ancestry **reference**, not a quorum assertion or new
signed phase: height 0 must name G, height>=1 must resolve to verified B/Q4 at that
height and the complete finalized prefix. The message/namespace supplies its
NID/G/A/C/epoch context; a naked foreign reference is not counted. No nullable
field or omitted height/hash exists. It serializes as J, is at most 113 bytes,
and its diagnostic ID is SHA256(J(FinalizedRef)); there is no independent
signature preimage. Deduplicate by `(context,height,H)`; a conflicting unsigned
reference alone cannot latch a fault. Authenticate/validate both full proofs
before reporting conflicting finality. Parent in a message means exactly
`FinalizedRef(block_height=h-1,block_hash=P)`, not any ancestor at a lower height.
Retain referenced block/proof/ancestry sources for archival verification.

### 3.2 Authentication, duplication, equivocation and retention

Before any state transition: strict parse/limits/version, pinned NID/G/A/C and
epoch, authorized full key/ID and signature, allowed h/r/parent, purpose and
proposal schedule/vr. Then evaluate the precise guard with the necessary actual
authenticated evidence and application result. Persist evidence before using it
to justify a released signature. Noncurrent-height traffic may be stored in a
bounded fetch spool; it cannot advance an unfinalized-parent height.

Identity for retransmission is `(full namespace,ID,J(E))`, not signature bytes.
Different valid ECDSA signatures of the same E add zero weight; retain the first
canonical Signed record and any independently needed evidence. Equivocation is
different E bytes at the same `(namespace,ID,h,r,purpose)` slot, including changed
vr on a proposal or nil versus H on a vote. Different rounds or vote phases are
not automatically equivocation. Parent, H and vr are **not** part of the slot
key. Malformed/unauthenticated claims are neither votes nor fault evidence.

Keep conflicting authenticated messages. A Byzantine ID can count once for X
and once for Y in separate predicates, but only once per predicate, wildcard
threshold or RE. Do not exclude it from static authority or rewrite an already
verified proof because of later local evidence. Offered PV/Q4/RE with duplicate,
unsorted, invalid or mixed entries rejects whole; independently collected good
votes can construct a different valid certificate.

Retain M/D/approved genesis/policies and all finalized B/Q4 and authenticated
source history for the network's archival lifetime. Keep the first sufficient
compatible proof plus authentic conflicting proof/evidence; alternative compatible
subsets need not all be archived by every observer. Validators retain every own
reserved/signed slot and all lock/valid/decision/round dependencies initially
without pruning. Received logs supporting recovery stay durable; reference
height reset clears the active logical log, not the archival records. No bounded
lifetime total is promised under Byzantine traffic or indefinite nil rounds.
Caches may be evicted only after proving their sources remain retrievable and
no enabled transition loses required evidence. Pruning is a separate review.

## 4. Exact signing and object-hash preimages

Let `m=J(E)` as raw bytes and `L=byte_length(m)`. Define:

```text
prefix = 0x19 || ASCII("Ethereum Signed Message:\n") || ASCII(decimal(L))
personal_preimage = prefix || m
signing_digest = Keccak-256(personal_preimage)
message_id = lowerhex(SHA-256(m))
signed_id = lowerhex(SHA-256(J(Signed)))
pv_id = lowerhex(SHA-256(J(PV)))
proof_id = lowerhex(SHA-256(J(Q4)))
round_evidence_id = lowerhex(SHA-256(J(RE)))
```

Here `\n` is one byte 0a; decimal(L) has no leading zeros and is not a fixed
width number. The prefix has no trailing delimiter before m. Use Ethereum
Keccak, not FIPS SHA3-256. The [EIP-191 personal-sign
definition](https://eips.ethereum.org/EIPS/eip-191) supplies this transformation.

The existing `eth_account.messages.encode_defunct(primitive=m)` performs the
personal-message prefixing; `Account.sign_message` then hashes/signs that
SignableMessage. Passing `message_id` text, a hex representation of m, a JSON
string containing m, or already-prefixed bytes is a different signature. Never
prefix twice. `encode_defunct(text=m.decode('ascii'))` is equivalent for this
ASCII profile. `wallet_signatures.py` currently converts CR/LF, coerces values
and normalizes addresses; strict grammar runs first and no such mutation is
permitted in a new-profile verifier. Existing helper behavior is not canonical
parsing. No production helper is modified here.

Verify r/s bounds, v spelling, signature recovery and exact full key. Preserve
existing mathematical high-S acceptance (`s -> n-s`, flip v); no extra quorum
weight, no replacement signature on exact retry. A producer can use deterministic
ECDSA but successful retry identity relies on storing the first signature.

Canonical block H remains SHA256 of the exact version-dispatched block envelope,
not SHA256 of B including its portable hash field. Original-media hash is SHA256
of original bytes. M/C, D/A, message IDs, signed IDs and certificate IDs have
different typed preimages; never accept a diagnostic SHA256 ID as an EIP-191
digest or infer finality from a matching untyped digest. Application hashes are
not changed to make them look like consensus messages. Q4 is produced after H,
outside H's preimage; child validity binds parent **identity**, not one particular
compatible encoding/proof_id of the parent's certificate. This avoids cycles
and incompatible children when sufficient proof signer subsets differ.

## 5. Algorithm/model/contract correspondence and discrepancies

Full printed guards remain normative; this is a traceability map, not a replacement
algorithm. The extra durability steps refine an atomic rule, not new phases.

| Algorithm 1 lines / 7.17H action | Inputs and check | Durable effect / permitted output |
| --- | --- | --- |
| 1–10 / initial, L10 | Approved test/launch namespace, finalized genesis | h=1/r=0, unset lock/valid; initialized journal before key access |
| 11–21 / start | Scheduled proposer; retained valid value/PV or valid getValue | Preserve locks; proposal at vr or non-proposer propose timer |
| 22–27 / L22 | Fresh proposal/data; validity; no lock or same value | Reserve prevote H if guard succeeds, otherwise nil; phase=prevote |
| 28–33 / L28 | Proposal, q actual prevotes at vr; `LR<=vr or L=H` | Same output discipline; bare vr is insufficient |
| 34–35 / L34 | q distinct current-round prevoters, any values; correct phase | Persist once flag and armed prevote timer; no signature |
| 36–43 / L36 | Current proposal/data and q same-value prevotes | In prevote: lock, valid state and H precommit reservation atomically; in precommit: late valid learning only |
| 44–46 / L44 | q current-round nil prevotes; prevote phase | Nil precommit/phase, preserve lock and valid state |
| 47–48 / L47 | q current-round precommit senders, any values | Once flag and precommit timer, independent of phase |
| 49–54 / L49 | Proposal plus q same-round non-nil precommits; valid B; any round | Durable decision/parent before reset, next h/round 0; no new commit-vote phase |
| 55–56 / L55 | Two distinct senders at one identical higher round, any message kinds | Durable round start, retained locks/valid values and old messages |
| 57–60 / L57 | Armed current propose timeout and propose phase | Nil prevote/phase; preserve lock |
| 61–64 / L61 | Armed current prevote timeout and prevote phase | Nil precommit/phase; preserve lock |
| 65–67 / L65 | Armed current precommit timeout | r+1 start, preserve locks; stop on R exhaustion |

`Model.{authenticated,relevant,weight,proposals,validity,start,local}` supplies
the corresponding inputs/guards. `emit/put` atomically publish and update own
log; section 7 refines that boundary. `Node.once/timers/log/data/decisions` map
to durable records below. `invariant_errors/edge_errors` remain unchanged.

Source discrepancies and adaptation decisions:

1. Paper prose describes a strictly newer justification; printed line29 uses
   `lockedRound<=vr`. This contract and model preserve **<= including equality**.
   Replacing it with `<` requires a distinct reviewed/modelled variant, not a
   serializer fix. No unresolved equality choice is left to implementers.
2. Printed line21 arms propose timeout only in the non-proposer branch. Preserve
   this in restart replay too. Arming a proposer timer would be a separate
   pacemaking refinement. With no valid getValue input the proposer is quiescent;
   no empty block, guessed timeout or unconditional liveness claim is supplied.
3. Model phases/IDs/context/authentication are symbolic and transitions atomic.
   Exact JSON/crypto, finite bounds, durable refinement and genesis authentication
   are new obligations, not things already verified by 7.17H. Bound exhaustion
   stops; it is not the model's search cutoff and does not wrap.
4. Proposal metadata/full data/PV fetch are separate. Adding a global vr-proof
   requirement to line36/49, or requiring full media for line55, is **BLOCKED**
   as a different agreement rule. Alternatives: retain this reference behavior,
   or separately specify/model/prove the stronger variant. This contract selects
   the former; no hidden restriction is introduced by ProposalBundle.
5. Model records complete decisions and clears the logical log. Physical archive
   and private slot retention are retained by refinement. Timer rearm after a
   crash delays progress but never synthesizes an unarmed timeout or signs twice.
6. Combined media block4/G2/application history are not frozen. Alternatives are
   a separately approved single combined schema, or a separately versioned
   alternative profile with new vectors. Treating closed block3 as extensible or
   choosing between incompatible block4 drafts by arrival order is **BLOCKED**.

No additional consensus-critical guard mismatch between printed Algorithm 1 and
the primary 7.17H model was found. This is an inspection result, not an independent
proof of either. The reference's zero-time steps require an eventually responsive
real implementation; repeated crashes/resource failure can defeat liveness.

Timeout profile proposed here is integer `1000 + 1000*r` milliseconds for each
of propose/prevote/precommit, reset by height. It fixes increasing waits for
isolated conformance; it is not a benchmark-derived production latency setting.
Only reference-armed timers can expire. Recovered armed-but-unconsumed timers
restart a full interval using a monotonic clock; consumed timers never refire.
Persist expiration and its effect before output. Stale h/r/phase expirations
stutter. Repeated recovery delays termination; stable uptime is a liveness premise.
Finite timer APIs must split long waits without early expiry or numeric wrap.

## 6. Minimal durable safety state and exact logical records

This is a **logical durable format**, not an SQL migration or a new production
API. A later isolated implementation must preserve these canonical BLOBs and
constraints; physical table/index layout can vary without changing the meaning.
Use J for metadata; raw block/message/source bytes are stored as BLOBs, not
re-normalized JSON strings. No private key bytes belong in these records.

Namespace NS is exactly:

```text
{protocol:"zoidbergchain", protocol_version:2, network_id:NID,
 genesis_hash:G, agreement_profile_digest:A, validator_epoch:0,
 validator_set_commitment:C, validator_public_key:Key, validator_id:ID}
namespace_id = lowerhex(SHA256(J(NS)))
SlotKey = {height:Height, round:Round, purpose:"propose"|"prevote"|"precommit"}
```

The signed-slot uniqueness key is `(namespace_id,height,round,purpose)`. The key
custody ledger must also pin which namespace(s) that key may serve: changing
NID/G/A/C is not an administrative route to bypass reservations. NS already
includes full key and ID. **Never add parent, value, valid_round, request ID,
peer, signature, fence generation or validation status to the uniqueness key.**

All metadata below is closed; IDs/digests are H64, counters UInt, nullable fields
must appear. `revision` starts zero and increases by one on each committed safety
mutation; `fence_generation` is a positive UInt from external custody. Status
strings are the exact enumerations shown. Local state has no consensus signature.

| Record | Exact fields / types |
| --- | --- |
| BlobRef | `{kind,digest}`; kind one of `block,signed,pv,q4,manifest,agreement,policy,validation,slot,receipt,marker,state,event,fault`; digest SHA256 of exact stored raw bytes |
| LockOrValid | `{block_hash,round,proposal_id,prevote_certificate_id}`; unset is `{block_hash:null,round:-1,proposal_id:null,prevote_certificate_id:null}`; otherwise H64/R/H64/H64 and complete B, proposal and non-nil PV sources must exist |
| Anchor | `{height,block_hash,proof_id}`; genesis `{height:0,block_hash:G,proof_id:null}`, otherwise verified H64 Q4 reference at exact height |
| Applied | `{height,block_hash}`; genesis or prefix at/below finalized anchor |
| State S | `{state_version:1,namespace_id,revision,fence_generation,height,round,phase,started,locked,valid,finalized,applied,inbox_tip,markers_tip,pending_slot,fault}`; phase `propose,prevote,precommit`; started bool; locked/valid above; inbox_tip/markers_tip H64 or null; pending_slot SlotKey or null; fault H64 or null referring to fault record |
| Slot row | `{slot_version:1,namespace_id,height,round,purpose,payload_hex,message_id,status,signature,before_revision,after_revision,evidence,block_record_id,validation_id,fence_generation}`; payload_hex exactly lowercase hex of J(E), <=4096 characters; status `reserved` or `signed`; signature null iff reserved else Sig65; evidence 0..16 distinct BlobRefs sorted by `(kind,digest)`; block_record_id/validation_id H64 or null |
| Receipt | `{record_version:1,previous,signed_id}`; previous H64 or null, signed_id SHA256(J(Signed)); immutable append-linked active log, including own produced signatures |
| Marker | `{record_version:1,previous,height,round,kind,status}`; kind `propose,prevote,precommit,polka`; status `armed,expired,once`; `polka` only `once`, propose only armed/expired; prevote/precommit once and timer state as required |
| Event | `{record_version:1,namespace_id,sequence,previous,rule,before_state,after_state,evidence,slot}`; sequence positive UInt, previous null only for initial event; state IDs H64; evidence as above; slot SlotKey or null; rule one of `INIT,FENCE,RECEIVE,START,L22,L28,L34,L36,L44,L47,L49,L55,L57,L61,L65,SIGN_STORED,APPLIED,FAULT` |
| Head | `{record_version:1,namespace_id,sequence,event_id,state_id}`; one authoritative atomically updated pointer, event_id/state_id H64 |
| Fault | `{record_version:1,namespace_id,code,evidence}`; code `conflicting_finality,corrupt_state,stale_state,fence_lost`; evidence 0..16 BlobRefs; immutable latch, no automatic clear |

BlobRef's digest of B is SHA256 of complete raw B, distinct from block H (hash
of its envelope). Resolve both and compare. Slot `block_record_id` and
`validation_id` are required non-null for a proposal/non-nil vote and may be
null for nil; the evidence still identifies proposal/quorum/timer rule inputs.
Validation records refer to the complete application input/source revision and
deterministic result; their production subgrammar is **BLOCKED on the application
profile**, not a generic caller-supplied `valid:true`. An isolated prototype uses
7.17H's explicit test Block flags/pinned synthetic context; no production media
validity follows. Public policy/source formats remain their separately versioned
application grammars; a BlobRef cannot invent authority.

For that isolated prototype only, a TestValidation record is exactly
`{record_version:1,profile:"task717h-symbolic-v1",namespace_id,height,parent_hash,
block_hash,block_record_id,source_revision,protocol,canonical,original,admission,
transactions,resources,result}`. Context/hash fields have the types above;
source_revision is UInt, the six flags are actual bool, and result is one of
`VALID,INVALID,INCOMPLETE_DATA,INCOMPLETE_AUTHENTICATED_HISTORY,
LOCAL_DECODER_FAILURE,LOCAL_STORAGE_FAILURE`. VALID requires all six flags true
and complete locally available inputs; complete input with a false flag is
INVALID. Incomplete/local outcomes do not assert an objective false flag.
This entire test profile must be rejected by any future production dispatcher.

S is content-addressed before the Event is built; S has no event_id. Build
`before/after S -> Event -> Head`, so event/state hashes do not refer to themselves.
Rows, receipt/marker chains, referenced evidence, resulting S, event and Head
update commit atomically. Initial before_state equals the initialized revision-0
S, INIT commits revision1. `sequence` equals resulting S.revision. An event's
previous points to the prior event; every revision is accounted for. Status
changes retain immutable original payload/evidence and journal before/after
states, not destructive replacement of history. Missing sequence, pointer,
source, slot or unverifiable signature is corruption/unavailable; no repair by
empty initialization. The two local revisions for reserve and SIGN_STORED are
not two separate reference votes.

Reservation and SIGN_STORED Events each include a `kind:"slot"` BlobRef for the
exact new immutable Slot row version in their evidence. This makes the event
digest commit to the reserved payload and produced signature, rather than merely
the slot coordinates. Keep both row versions; a lookup index is derived from
validated event history. Slot before_revision/after_revision name the reservation
transition and remain unchanged when signature/status is appended. The
SIGN_STORED Event has its own consecutive before/after state revisions. Verify
`lowerhex(SHA256(bytes_from_hex(payload_hex))) == message_id`; strict-parse those
bytes as E and match its namespace and slot coordinates. When signed, require
the exact retained E/signature/Signed receipt/outbox to match that row.

Required invariants:

- At one height, rounds never decrease; phase advances propose->prevote->precommit
  within a round, or resets to propose only on a valid StartRound. No new older
  slot may be created; an existing exact signed retry is separate from new signing.
- Locked state changes only through current-round line36 while in prevote.
  Valid state learns through line36 in prevote or precommit; nil, timeout and
  round change never clear either. Paired value/round/evidence updates are atomic.
- Once markers and sent/received log dependencies survive restart. No replay
  executes a once-only rule twice or substitutes a new signature for reserved nil.
- Parent anchor is the unique durable finalized h-1; at height advance finalize
  the decision first, then reset lock/valid state. Anchor never regresses/conflicts.
  New height signing waits until the application's exact parent prefix is durably
  applied; applied may lag finalized but cannot contradict it.
- A pending reservation blocks **all subsequent local reference transitions**
  until its exact signed message is durably materialized in own log/outbox, or
  the signer halts. Incoming bytes may spool without executing rules. This avoids
  an interleaving where an unsigned reserved message is counted as an authentic
  vote or an old transition overwrites newer learned state.
- Every mutable Head/state/slot update rereads inside one serialized transaction
  and compares expected revision/fence. Snapshot reads before BEGIN do not authorize
  signing. Local uniqueness and the external fence both apply to identical retries.

All of NS, Head, state/events, slots (including unresolved reservations),
lock/valid/round/timer/once evidence, full supporting immutable B/policies,
highest finalized anchor, fault latch and fencing receipt are safety-critical.
Peer scores, indexes, decoded/verified caches, transport acknowledgement counts,
retry queues and parsed manifests are performance data if underlying sources and
durable outbox can rebuild them. Losing wall-clock deadlines merely delays safe
rearming; losing whether a timer was armed/consumed is safety-relevant.

## 7. Write-before-release, transactions and crash behavior

Choose **reserve, then sign, then persist signed message, then release**. Do not
offer a second interchangeable sign-first path in the first implementation.
Serialize one authority's reference transition queue and enforce custody even
when two independent processes call it. Authentication of a caller is not proof
that the requested transition is safe.

### 7.1 Common sequence

1. Acquire/verify exclusive enforced custody and current nonrollbackable witness;
   require no safety fault. Stage immutable verified inputs; a source is durable
   only when its bytes/refs are in the journal's atomic store or independently
   guaranteed immutable archive with an explicitly reviewed availability contract.
2. `BEGIN IMMEDIATE`; reread Head, fence and slot. Exact existing signed bytes
   can return the retained signature after outcome/fence checks. Different bytes
   in any reserved/signed slot reject `CONFLICTING_SLOT`. A reserved exact retry
   can finish only that message. A new request must satisfy its reference guard.
3. Atomically reserve exact m, record necessary input evidence, resulting phase,
   lock/valid/once changes, pending_slot and revision/event. Commit with durability.
   No signature has yet been generated, returned, logged or transmitted.
4. Advance the external witness to this **exact committed event/state digest**
   and authorize only its reserved payload under the active generation. Withhold
   key use if the witness cannot confirm. The witness is not an advisory lease.
5. Produce a signature only for retained m; keep it private. Verify its exact key
   and bytes. Under a new serialized transaction, persist signature, status=signed,
   own log Receipt, deterministic outbox content J(Signed), clear pending_slot,
   and SIGN_STORED event/revision. Commit before exposure, then witness that head.
6. Only the stored outbox bytes can be returned/published. Retransmit idempotently;
   lost acknowledgement cannot authorize another value or signature variant.
   Transport publication/ack bookkeeping can lag; the message may have escaped
   as soon as step6 starts, regardless of its delivery flag.

The signing-authority boundary includes the trusted reducer, private storage and
restricted HSM/signing-service response path. Internal signature delivery must
not expose bytes to consensus callers, peers, general logs or unrelated wallet
clients before step 6. A remote device that publishes its raw response outside
this boundary cannot satisfy the store-before-release contract.

The external witness/key service must implement compare-and-advance over
`(key,namespace,generation,sequence,event_id,state_id)` and refuse a different
digest at the same sequence, a lower sequence, stale generation or a key request
without the authorized reservation. Exact sequence increments are reconciled
from the retained hash-linked events; a witness ahead of local verified history
means stale recovery, never permission to skip the gap. A DB head ahead of the
witness can advance it only by replaying the complete unique validated continuation
under exclusive custody. An arbitrary greater counter from disk is not sufficient.
Non-signing safety transitions use the same durable event/witness ordering;
reconcile the complete current head before executing a successor transition.
No atomic transaction with hardware is claimed; uncertain cross-system outcomes
halt until both sides agree. Loss of availability is preferable to ambiguous
permission. The concrete nonrollbackable service/HSM implementation and operating
trust remain a production owner gate in section 8.

The trusted safety reducer is inside the signing-authority boundary and checks
events, guards and evidence itself. An untrusted consensus caller cannot obtain
a signature by constructing a purported Event or supplying `valid:true`. A
counter-only HSM does not replace that reducer. On an authorized restart/ownership
transfer, the witness first revokes the old generation and proves the exact
current head; a FENCE event records the new generation without changing any
slot bytes, lock, round or anchor. Reconcile the new head with the witness before
key access. Pending slots retain their original generation as audit metadata;
only the identical payload can be reauthorized by the new active generation.
No predecessor generation can resume signing. A partially completed fence
transfer follows the same unknown-outcome refusal/reconciliation rule.

### 7.2 Operation-specific atomic boundaries

| Operation | Before signing or making state externally usable |
| --- | --- |
| A. Proposal | Reserve scheduled h/r/H/vr; retain complete valid B/parent and selected getValue or prior valid-value proposal/PV. Reproposal preserves B/H, creator and rewards. Durably preserve retained W/WR and round start. |
| B. Prevote | Fresh/justified guard, lock predicate and actual PV sources or armed timeout; reserve H or explicit nil and phase. Invalid complete proposal can yield nil; missing/local failure is not objective invalidity. |
| C. Precommit | Non-nil: current proposal/full validity and q current PV, new L/LR and W/WR and once flag committed **with reservation**. Nil: nil-PV or expired armed prevote timer, phase committed, old lock/valid state retained. |
| D. Round/lock/late-valid | Journal current round/phase, catch-up/timer inputs and once markers before successor signing. Late W/WR update after nil precommit does not replace lock or emit another precommit. No timer/nil unlock. |
| E. Publish | Persist exact signature, own authentic message-log entry and outbox plus all safety inputs/state before any external signature byte. Retry returns identical stored bytes. |
| F. Finalize/promote | Independently verify B/Q4/ancestry/application; commit signer decision/anchor and sources before height reset/next signatures. Receiver commits complete decision, selected finalized prefix, ledger/applied cursor and publication work before finality acknowledgement. |

Separate signer/chain/reviewer databases have no shared transaction. The signer
owns enough immutable inputs to recover every safety choice. Receiver promotion
uses an idempotent decision ID `(namespace,h,H)` and write-before-publish. If
receiver applied state lags a durable signer decision, recover/replay exact
sources before next-height signing. A receiver ahead of a restored private signer
does not repair missing private slots. In both directions verify identity and
monotonic cursors; ambiguous or incompatible state withholds signing/finality.

### 7.3 Failure matrix

| Failure window | Required result |
| --- | --- |
| Before/during reservation commit | Release nothing. Reopen/recover authoritative store and reconcile witness. If no reservation was committed, a new request still needs its current guard; an uncertain absence is not a rollback conclusion. |
| Reservation durable, crash before signing | Slot remains irrevocably bound. Complete the identical reserved message using retained state/evidence or stop. Never free/reuse it for a conflict. |
| Signature generated, crash before SIGN_STORED | No external byte may have escaped. Resume only same m; a new private deterministic signature may be generated if none was durably retained. If hardware already retained a signature, reuse it. Never claim this is a released-message retry until durable storage exists. |
| SIGN_STORED committed, crash before publication | Return exact stored Sig65/m on recovery and publish outbox. Do not recreate/re-sign it. |
| Published, acknowledgement lost or process killed | Assume publication occurred. Retry exact stored signature. Publication flags cannot prove non-release. |
| Busy/locked | Bounded local retry (30,000 ms busy timeout per operation); no successful release before known commit, no new slot from stale read. A COMMIT busy can leave the transaction active; explicitly reconcile it, not blindly BEGIN again. |
| Disk full, I/O error, damaged/missing rows | Stop key use/release; classify local unavailable. Preserve committed reservations/evidence. Do not delete rows, downgrade sync, switch to memory or initialize empty state. |
| COMMIT or witness acknowledgement uncertain | Withhold all output. Reopen using a fresh owned connection, validate complete journal/dependencies and witness. Return retained result only on agreement; otherwise halt. An exception does not prove rollback. |
| Unexpected shutdown/restart | Validate namespace/full authority, events/revisions, slots/signatures, evidence, lock/valid sources, finalized/applied cursors and witness/fence; rearm only proven pending timers. Block key access throughout recovery. |
| Old backup or cloned DB | Reject if behind/different from authoritative witness; public Q4 sync cannot establish absence of hidden old signatures. No live failover from a backup without custody and exact state continuity. |

Initial durable operating profile: local SQLite **DELETE journal** and
`synchronous=EXTRA` (3), read back on every owned connection; foreign_keys=ON,
busy_timeout=30000, explicit close, one connection per thread/transaction,
`BEGIN IMMEDIATE` before authoritative reads. Refuse unexpected journal modes;
do not silently convert an existing store. This follows the existing 7.17E
discipline, not isolated v3's WAL profile. WAL requires a separate reviewed
SQLite-version/filesystem/backup contract; no known WAL refusal is bypassed.
[SQLite transactions](https://www.sqlite.org/lang_transaction.html) describe
single-writer and busy semantics; [synchronous
settings](https://www.sqlite.org/pragma.html#pragma_synchronous) explain EXTRA's
additional rollback-journal directory synchronization. Correct local locks and
truthful filesystem/device flushes are assumptions. Process-kill tests alone
cannot certify power-loss durability, network shares or copied-key exclusion.

## 8. Exclusive custody, rollback limits and authorized recovery

SQLite uniqueness protects writers sharing **the same authoritative store**.
Two copied databases each have an empty/conflict-free local slot and can sign
opposite messages with one copied key. A filesystem lock cannot fence a second
host holding exported key bytes. A lease that expires while an old process can
still access a key also cannot revoke signing power.

Production requirements:

- One active signing authority per full validator key, including every path
  capable of raw/personal signing. No wallet, admin console or fallback process
  may bypass reservation/safety state. Operator/peer authentication is separate
  from authority to use the key.
- An enforced local OS lock plus DB transaction serializes same-host callers;
  a key-enforcing nonrollbackable external authority or reviewed HSM-backed
  counter/state witness fences generations and digests across restoration.
  The key service must refuse stale owners and bind the exact reservation;
  checking a counter and later calling an unfenced wallet is insufficient.
- A counter must commit state identity, not merely a number; alternative states
  can have the same revision. Its own backup, recovery, operator access and
  cumulative compromise assumptions are part of the security boundary. Restoring
  the authority and key to the same old snapshot defeats rollback protection.
- Stale, lost or unverifiable private state disables signing even if all public
  blocks/Q4 are available. Full sync cannot reconstruct an unpublished vote,
  unresolved reservation or private lock transition. Restore only exact complete
  state proven current by the witness, with the prior owner irreversibly fenced.
- Recovery authorization is an audited owner/custody procedure to recover that
  proven state or permanently disable the key. It cannot approve signing a
  conflict, rewrite locks, clear reservations or lower a high-water mark.
  If state is lost, halt that identity. Remaining three correct responsive
  members may continue only within the declared fault assumptions; another
  Byzantine/outage can halt the network. No automatic membership/key replacement.
- Key replacement, authority recovery without full state, retirement and network
  reset need a separately approved protocol/launch decision. Epoch1 is rejected
  in this static profile even if all current members sign it. New NID/G, isolated
  stores and retirement of old signing permissions are needed for an approved
  reset; new keys are preferable. Old historical verifiers/evidence remain.
- Unsupported: multi-host shared-key deployments, copied wallet backups used as
  hot failover, shared/network-filesystem SQLite as fencing, local-only counters
  marketed as rollback proof, and best-effort leases with exportable keys.

**Stale-state detection cannot be guaranteed solely by data that can be rolled
back together with the signing key.** Without an external nonrollbackable trust
anchor the honest premise must explicitly exclude rollback/cloning; it cannot
be called robust prevention. Owner must select/fund the authority/HSM/counter,
custody boundary, availability/recovery policy and real power-loss/fencing tests.
An isolated test prototype can emulate this witness to test refusal logic; that
does not provide hardware or production rollback guarantees.

## 9. Historical Q4 and ancestry verification

Start from independently approved pinned full genesis G2, not a downloaded
proof's roster. Validate genesis syntax/hash/release authority, M/C, D/A and all
application policies. For this profile `(G,epoch 0,C)` always resolves to M's four
keys, even for old heights. Current config, reviewer epochs and later misconduct
do not rewrite historical authorization. Historical other-version proofs use
their original explicitly dispatched trust/semantics; no retroactive BFT claim.

For each consecutive h from 1 through the claimed finalized prefix:

1. Bound/strict-parse B/Q4 and version/context. Obtain complete B, parent prefix,
   policy/media/admission/reviewer/native sources; recompute H from the canonical
   application envelope, and actual h/P. Missing sources -> INCOMPLETE; local
   read/decode/store error -> UNAVAILABLE; do not pretend the prefix is final.
2. Verify the stable application predicate on B and the exact durable finalized
   h-1 application state. P must equal G at h1, else the verified parent's H.
   No gaps, provisional-parent substitution or score/length tie breaking.
3. T binds this G/A/C/NID/protocol/epoch/h/r/P/non-nil H and precommit purpose.
   Recover scheduled proposal's full key and match all shared fields; check vr
   syntax, without requiring a recursive old PV transcript. Verify every Sig65
   over its exact EIP-191 m. Invalid offered entry rejects the whole proof.
4. Count three or four strictly ordered distinct authorized IDs/keys with payloads
   exactly T plus ID. Different signature spellings, repeated identities, mixed
   phase/round/parent/network/genesis/set and proof-declared authority never add
   weight. A valid q of another target cannot authenticate missing B.
5. Check compatibility with every known finalized anchor. Same H with alternative
   sufficient subsets/signatures or legitimate rounds is compatible; retain the
   first sufficient proof locally. Same-height different H or incompatible
   verified ancestry is a safety fault. Independently validate both proofs and
   required sources before latching; a peer's unverified claim cannot halt us.
6. Durably retain B/Q4/sources/prefix and decision/fault state before publication.
   A conflict retains both proofs/ancestries in an append-only fault record and
   stops authoritative advancement/signing in that context. Do not choose by
   arrival order, lower hash, score, longer fork, peer count or admin deletion.

After restart, recover authoritative prefix/applied cursors and verify source
and proof linkage before serving authoritative finality or signing. Resume fetch
of missing proposal data/proofs separately from selected-tip synchronization;
same-tip peer inventory is not evidence that all Q4/sources were acquired.

A Q4 establishes **authorized signatures**, not a transcript proof that all
signers used correct locks or ever saw the necessary prevotes. Agreement relies
on at most f faulty keys and correct durable state-machine discipline among the
rest. Quorum overlap plus that discipline excludes incompatible decisions;
overlap alone does not. Later accumulation of enough static private keys can
forge historical certificates: these signatures are not forward secure.

## 10. Application validity and operational failure boundary

Future adapter interface is conceptually
`validate(candidate_raw, pinned_context, finalized_parent_state, source_bytes)`.
It returns VALID with immutable input/result identity; INVALID with a deterministic
code; INCOMPLETE_DATA; INCOMPLETE_AUTHENTICATED_HISTORY; LOCAL_DECODER_FAILURE;
or LOCAL_STORAGE_FAILURE. No exceptions/local deadlines are coerced to INVALID.
Only a complete deterministic VALID result permits non-nil voting/decision.
Invalid complete data follows the reference's nil branch; incomplete/unavailable
data is awaited/fetched while ordinary armed nil timeouts remain eligible.

| Required check | Fixed-input obligation / existing reusable boundary |
| --- | --- |
| Finalized parent | Consecutive h and exact P; all parent application transitions durably applied; no mutable provisional fork selection |
| Network/genesis/profile | Pinned NID/G/M/C/D/A/epoch, full policy registry and explicit application version dispatch |
| Canonical block/hash | Closed bytes, sizes/child budgets, canonical envelope hash H; `canonical_v3.block.parse_record` is useful for block3 fixtures, not an amended block4 parser |
| Original media | Complete on-chain encoded bytes, approved identity/zstd descriptor, exact original length/hash and byte-for-byte reconstruction; no external dictionary/URL-only availability or validator recompression |
| Isolated safety checks | Approved bounded codec plus deterministic MIME/container/technical limits; `reconstruct_record_media` alone does not prove image/admission validity |
| Admission and reviewer history | Full signed admission evidence, immutable parent-bound eligibility/cohort/quota/source replay and issuance authority; local labels/cache observation order are insufficient; unresolved policy stays BLOCKED |
| Native transactions/rewards | U10/T18 genesis/type/domain signatures, ordered native aggregate, nonce/balance/claims and exact permitted creator reward projection; no undomained transfers or proposer reward invention |
| Resource limits | Complete B<=3,145,728; original/encoded images<=2,097,152; text<=262,144; certificate<=196,608, native<=98,304, residual<=32,768, counts and codec work limits together |

Keep deterministic structural limits independent of machine speed: JSON depth 32,
identity/zstd profile 1, decoded/stored lengths above, zstd window<=262,144 and
blocks<=64 plus the frozen sequence-verifier work bounds. Full codec profile
remains the frozen isolated profile; no arbitrary codecs. Local worker defaults
currently are 128 MiB, CPU 5 s, READY wall 10 s, startup 5 s, global concurrency 2.
These are explicit **operational** controls, not consensus-invalid time limits;
exhaustion/unavailability abstains/fails locally. Different scheduling cannot
change `valid(B,parent)`. Production isolation and intended-platform measurements
are still required. Queue quotas/backpressure may throttle unauthenticated
traffic, but cannot discard a required lock or falsely invalidate missing data.

Bind a validation token to exact NID/G/A/C/h/P/H, raw B digest, source/policy
revision and result. Cache only immutable validated inputs; completed work at
an obsolete step cannot produce a second vote. Timestamp/admission expiry must
use an approved stable immutable-parent policy, not current wall time or round
duration. Bootstrap, exact cohort/all-unsure, issuance and clock rules remain
unresolved application amendments; this document supplies no substitute.

## 11. Capacity, persistent state and resource arithmetic

For an ASCII-key object with k members and value widths v_i:
`size=2+(k-1)+sum(len(key_i)+3+v_i)`; arrays contribute brackets, values and
commas. Analytical maximum-width inputs are **not fabricated valid signatures
or blocks**. Use NID64, h=U, r=R, vr=R-1, fixed-width hashes/IDs/signatures;
epoch/version remain literal small integers. These widths are conservative
where simultaneous key/signature constraints reduce attainability.

| Object | Maximum canonical bytes from closed widths | Parsing ceiling |
| --- | ---: | ---: |
| M, four keys / NID64 | 603 | 8,192 |
| D | 892 | 4,096 |
| Proposal E / Signed | 835 / 1,030 | 2,048 / 2,304 |
| Prevote E / Signed | 802 / 997 | 2,048 / 2,304 |
| Precommit E / Signed | 804 / 999 | 2,048 / 2,304 |
| Nil prevote / precommit E | 740 / 742 | 2,048 |
| Nil prevote / precommit Signed | 935 / 937 | 2,304 |
| PV, q3 / N4 | 3,583 / 4,581 | 12,288 |
| Q4, q3 / N4 | 4,632 / 5,632 | 16,384 |
| RE, one scheduled proposal plus one precommit | 2,066 | 8,192 |
| ProposalBundle incl B at 3 MiB, Signed and N4 PV | 3,151,382 | 3,160,400 |
| Round-change network message | None — no fourth signed phase | RE or individual messages above |

All ceilings apply together; a wrapper never permits a child to exceed its own
grammar cap. Bundle scaffold is 43 bytes; its worst width is
`3,145,728+1,030+4,581+43=3,151,382`. No JSON quoting/escaping expansion of B as
a string is allowed. Conservative child-cap sum is also within the bundle
ceiling. Nil replaces a quoted H64 (66 bytes) with `null` (4), saving 62; PV nil
also saves 62 in commitment and each vote.

Consensus proof bytes inside B: **zero** (PV, Q4, RE and signed slots are
separately authenticated and retained). 7.17G's proposed new in-payload
`consensus_context={agreement_profile_digest:A,validator_epoch:0,
validator_set_commitment:C}` adds exactly **230 bytes** including outer member
name, colon and one comma. It requires a new closed block payload/hash preimage;
frozen block3 rejects it. With only that extension, the old disjoint conservative
bound `3,123,884+230=3,124,114` leaves 21,614 under 3 MiB. It must still fit the
residual 32,768 sub-budget: reserve 230 there, not outside it. The tighter existing
bound `3,058,797+230=3,059,027` is illustrative, not approval of a combined history
schema. Unfrozen 7.17B history fields may consume more. **Recompute the entire
combined block4 capacity and residual proof before production**; neither this
margin nor a 7.17B historical estimate certifies that different layout. The
3 MiB complete-media cap and MODEL A are unchanged.

Private durable records have conservative fixed **metadata caps**, excluding
referenced immutable content: NS 1,024; State 8,192; Slot 16,384; Event 16,384;
Receipt/Marker/Head 1,024 each; Fault 4,096. Evidence<=16 refs per Slot/Event; they
reference complete linked log roots to larger quorums/source history, never
truncate dependencies. Payload hex<=4,096 bytes is inside Slot's cap. Reserve
one pending transition at a time. The snapshot contains roots instead of an
unbounded inline log; per-record bounds do not bound total journal size.

Independent-field width arithmetic gives conservative metadata bounds NS571,
State1,446, Slot6,381, Event2,049, Receipt177, Marker181, Head286 and Fault1,713
bytes, all below their caps. These deliberately combine individual maximal
field widths even when their status/phase coupling cannot occur; they are not
valid-state/signature fixtures. The Slot bound uses the full 4,096-character
payload_hex allowance rather than assuming only a typical message length.

Per completed local signing operation, reserving and SIGN_STORED need at most
two Slot versions, two State versions, two Events, one Receipt, two Head images,
one durable Signed outbox and at most four Marker versions:
`2*16384 + 2*8192 + 2*16384 + 1024 + 2*1024 + 2304 + 4*1024 = 91,392`
metadata bytes before DB pages/index/journal/fsync/backups. Proposal+two votes
at a proposer in one round is at most 274,176 for these operations; two votes
182,784. Additional receives, round/late-valid/finalize events and immutable
sources are extra, explicitly counted by their records. A transition with no
signature adds at most one State+Event+Head and needed receipts/markers/source
refs; it is not free because its outbox is empty.

The finite R bound gives a deliberately loose own-slot ceiling per height:
`2*(R+1)+(R+1)/4 = 4,831,838,208` (two votes each round, proposer one round
in four). At the conservative operation budget above that is at most
441,591,357,505,536 metadata bytes (401.625 TiB), excluding incoming evidence,
source data and other events. This astronomical arithmetic bound is not a
storage allocation, expected workload or liveness claim: an implementation must
stop on resource/numeric exhaustion while preserving safety state. The admission,
gossip and retention operating budget still requires owner review/measurement.

An illustrative maximal source set for one proposed value is one complete B
(3,145,728), one proposal(1,030), eight distinct vote messages
(`4*997+4*999=7,984`), N4 PV(4,581) and N4 Q4(5,632): **3,164,955 bytes**,
plus full policy/history source dependencies. This is a bounded chosen set,
not a global per-height worst case: different proposals, equivocations, rounds,
log events, retries and source history have **no small per-decision bound**
from these one-round figures. Finite numeric limits eventually force a halt;
they are not an economical retention policy.
Content addressing avoids duplicating B per slot but does not remove the duty to
retain/fetch it. Do not claim one small last-signature row is all required state.

For archival decisions, one full B plus maximal closed-width Q4 is 3,151,360
bytes/height, before policy/source/index/backups. At 1,095,000 illustrative media
(1,000/day over three 365-day years), Q4 alone at 5,632 is 6,167,040,000 bytes;
at the 16,384 parser ceiling it is 17,940,480,000. Optional full honest-round
transcript per value adds proposal 1,030 + votes 7,984 + PV 4,581=13,595 if independently
retained in addition to Q4; sharing blobs can reduce duplication. Byzantine
equivocation archives and nil-round private journals need explicit operational
budgets; finite numeric exhaustion halts rather than permitting safety pruning.
These are arithmetic ceilings/scenarios, **not measured performance**, throughput,
latency, realistic mean sizes, disk amplification or power-loss certification.

## 12. Golden vectors, verification and future implementation tests

Appendix A fixes complete synthetic contexts, real public test keys, exact
messages, signatures, byte/hash results and certificate construction. The
private scalars 1..5 are public test constants only, never live keys. G=`11`*32
is a synthetic input; H=`aa`*32 and Y=`bb`*32 are symbolic application identities.
They do not claim valid media/genesis bytes. Positive signature and Q4
**cryptographic-core** examples are not positive complete-chain/application
finality examples; those are BLOCKED until the combined schema/policy freeze.

Two independently written implementations were used: Python stdlib sorted JSON
and SHA256, `eth_account`/`eth_keys`/`eth_hash` for signatures/digests; Node sorted
recursive serialization and native SHA256/ECDH, a standalone BigInt Keccak-f1600
implementation, and standalone BigInt secp256k1 recovery/verification. Node builds
its own M/D/payloads, rather than hashing only Python's serialized strings; it
does not import a production serializer or use Python as its crypto oracle.
Signatures generated by Python are independently verified, not independently
generated with matching nonce output. The Keccak empty-input known answer also
matches. Results/reproduction are appended after the literal vectors.

Declarative signer/crash vectors (expectations, **not tests of an implemented
durable signer**) use Appendix A's exact prevote message `mPV`/signature `sPV`:

| Vector | Ordered durable facts / request | Required outcome |
| --- | --- | --- |
| Signed retry | Slot(namespace,h1,r0,prevote) stores mPV/sPV; same mPV requested | Return identical sPV and J(Signed); do not generate a signature or change weight |
| Conflicting request | That slot reserved/signed for H=aa*32; request Appendix A conflicting-prevote H=bb*32 | CONFLICTING_SLOT even when different request ID, parent or generation is supplied; preserve original row |
| Crash before sign | Reservation includes mPV and resulting phase; no signature | Only complete mPV or halt; reservation never expires into a free slot |
| Crash before publication | Signed row and outbox contain exact mPV/sPV; publication not acknowledged; restart | Verify fence/journal then publish those exact bytes; no new signing |
| Uncertain commit | Commit/witness outcome cannot be read reliably | UNAVAILABLE; no signature or successful acknowledgement |
| Stale recovery | Restored Head(sequence41,event X) while witness(sequence43,event Y) cannot be replayed from local evidence | STALE_STATE, key use disabled even after all public Q4 fetched |
| Same sequence divergence | Local sequence43/event Z differs from witness sequence43/event Y | STALE_STATE, never choose by greater block height or matching counter alone |
| Q4 core verification | Appendix A X scheduled proposal + three distinct matching precommits | Crypto core valid; complete finality remains conditional on real B/genesis/application/ancestry |
| Same-height conflict | Independently verified Appendix A X/Y Q4 cores plus hypothetical complete valid source prefixes | Compare different H at same context/h; retain both, fault latch; generated fixture deliberately signs both and exceeds honest f premise |

Future isolated acceptance must exercise real disposable SQLite/fenced-test-key
processes at every reserve/sign/store/release/round/late-valid/finalize/witness
window in section7, including actual kills, competing callers/processes,
database busy/full/damaged/missing/ambiguous outcomes and stale/cloned restores.
Compare traces to unchanged 7.17H guards. In particular: hidden commits, equality
at vr=LR, unequal locks, justified switching, nil lock retention, late valid
learning without lock, old-round decisions, same-higher-round distinct-sender
catch-up, duplicate/high-S votes, proposal/PV/data fetch ordering, obsolete worker
results/timers, replay once flags and sequential durable parent promotion.
Enforced real custody and intended-filesystem power-loss tests are later gates.

Keep both 7.17H negative controls reproducibly failing agreement under their
explicit weakened/lost-state premises. Do not relax a reference guard or hide
a counterexample to make a future signer test green. Protocol-specific engine,
network and complete application tests require separate authorization.

## 13. Remaining amendments, owner decisions and readiness

| Gate | Status | Evidence / limits and approvals still needed |
| --- | --- | --- |
| A. Wire-schema contract ready | **PASS — isolated parameterized contract** | Closed M/D/E/Signed/PV/Q4/RE, exact types/preimages/caps and independently checked synthetic vectors. No claim that G2/combined application schema or launch policy is approved. |
| B. Isolated signer prototype ready | **PASS — specification only, test identities** | Exact slots/state/evidence, serialized reservation/sign/store/release, conservative recovery and test witness contract; can use model flags and synthetic G/policies. A separately authorized task may implement it, with all acceptance tests above. No implementation begins here. |
| C. Production signer ready | **BLOCKED** | No implemented/tested durable signer, real enforced nonrollbackable custody, filesystem power-loss review or independently reviewed safety refinement. Full G2/policy/combined schema, operators and owner approval remain open. |
| D. Production BFT state machine ready | **BLOCKED** | No engine/adapter/gossip/proof-sync implementation or independent adversarial conformance review; bounded model is insufficient. Native versus reviewed-engine route and all application/history rules need decisions. |
| E. Public-testnet activation ready | **BLOCKED** | All prior production gates, approved independent N4/f1/q3 operators/keys/NID/G and release trust, explicit state disposition/activation and operating approval absent. Task 7.17 remains blocked. |

PASS is not authorization to run a subsequent task. Owner decisions still needed:

1. Approve the independent permissioned/static N4/f1/q3 fault model, cumulative
   key-compromise assumption, printed Algorithm1 variant and implementation route/
   independent review funding. Alternatives need separately versioned modelling.
2. Approve complete application/reviewer bootstrap, exact cohort/all-unsure,
   issuance/source completeness, timestamp/admission and media-only history rules.
   No preliminary/unreviewed media, empty/control blocks or clock fix is inserted.
3. Freeze one full G2 and policy registry and one reconciled combined media/history
   payload, including consensus_context and exact new hash/version/domain dispatch;
   prove all parent/child/residual capacity budgets under 3 MiB with full valid vectors.
   Current block3 cannot be extended. 7.17B block4 and this proposal are not two
   acceptable grammars under one version. Actual G and policy digest remain pending.
4. Approve finalized-parent/decision-priority integration and archival source/
   conflict retention, proof synchronization and safe application promotion.
5. Choose enforceable key custody, nonrollbackable witness/counter, stale-backup
   refusal, lost-state halt/emergency policy and deployment filesystem guarantees.
   Replacing keys or resuming after lost state is not an epoch/config edit.
6. Choose actual independent operators/keys, network/genesis/release distribution,
   historical state disposition and explicit future activation/launch approvals.

Proposed next **minimal separate** implementation task: an inert, test-identity
serializer/verifier and single-key journal prototype against this parameterized
contract, disposable explicit paths, model-flag validity and an injectable
external-witness test double. Require exact vectors plus multi-process/crash
acceptance before considering production adaptation. No node imports, production
keys/store access, network consensus loop, history implementation, migration or
activation. This suggestion neither starts nor authorizes Task 7.17J.

Task 7.17I is ready for review and a later owner-performed commit as a
specification/targeted-verification deliverable; unresolved production/application
gates are intentional and explicit. No commit, push, merge or later task occurs.

## Appendix A. Literal test contexts and complete vector recipes

<!-- TASK717I-GOLDEN-VECTORS -->

These are complete construction recipes: substitute the literal values below,
apply only the named field mutations, then serialize with J. No ellipsis or
placeholder occurs in the resulting signed bytes. Every signature below is real
test ECDSA. The complete verification programs are embedded in Appendix B so
reproduction does not depend on retaining disposable files.

Test key scalars are the 32-byte big-endian encodings of integers 1..5. They are
public, insecure constants. M contains scalars 1,2,4,3 in compressed-key order;
scalar 5 appears only in the alternate-set input. All examples use height 1,
epoch 0, round 0, parent=G, H=aa repeated 32 bytes unless their row says otherwise.

| Scalar | Compressed key | ID |
| ---: | --- | --- |
| 1 | `0279be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798` | `0x7e5f4552091a69125d5dfcb7b8c2659029395bdf` |
| 2 | `02c6047f9441ed7d6d3045406e95c07cd85c778e4b8cef3ca7abac09b95c709ee5` | `0x2b5ad5c4795c026514f8317c7a215e218dccd6cf` |
| 3 | `02f9308a019258c31049344f85f89d5229b531c845836f99b08601f113bce036f9` | `0x6813eb9362372eef6200f3b1dbc3f819671cba69` |
| 4 | `02e493dbf1c10d80f3581e4904930b1404cc6c13900ee0758474fa94abe8c4cd13` | `0x1eff47bc3a10a45d4b230b5d10e37751fe6aa718` |
| 5 | `022f8bde4d1a07209355b4a7250a5c5128e88b84bddc619ab7cba8d569b240efe4` | `0xe1ab8145f7e55dc933d51a18c793f901a3a0b276` |

Base M, exact J bytes (no newline inside the preimage):

```json
{"authority_profile":"static-genesis-v1","byzantine_fault_budget":1,"domain":"zoidbergchain/validator-set/v1","membership_version":1,"network_id":"task717i-test","protocol":"zoidbergchain","protocol_version":2,"required_quorum":3,"validator_epoch":0,"validator_public_keys":["0279be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798","02c6047f9441ed7d6d3045406e95c07cd85c778e4b8cef3ca7abac09b95c709ee5","02e493dbf1c10d80f3581e4904930b1404cc6c13900ee0758474fa94abe8c4cd13","02f9308a019258c31049344f85f89d5229b531c845836f99b08601f113bce036f9"]}
```

`C = 6fb37df7e489c39287ea827d08f32467f84116d1e8758304d86672a6fd935518`.

D, exact fourteen-field object including its closed twelve-field limits object:

```json
{"agreement_version":1,"application_policy_digest":"5555555555555555555555555555555555555555555555555555555555555555","authority_profile":"static-genesis-n4-f1-q3-v1","domain":"zoidbergchain/bft-agreement/v1","limits":{"agreement_bytes":4096,"block_bytes":3145728,"commit_proof_bytes":16384,"envelope_bytes":2048,"manifest_bytes":8192,"max_depth":32,"max_round":2147483647,"max_uint":9007199254740991,"prevote_certificate_bytes":12288,"proposal_bundle_bytes":3160400,"round_evidence_bytes":8192,"signed_bytes":2304},"parent_profile":"immediate-finalized-v1","proposer_profile":"height-minus-one-plus-round-mod-four-v1","protocol":"zoidbergchain","protocol_version":2,"reference":"arxiv:1807.04938v3/Algorithm1","rule_selection":"printed-lines-1-67","signer_profile":"reserve-sign-store-release-v1","timeout_profile":"linear-1000ms-plus-1000ms-per-round-v1","wire_profile":"bft-ascii-json-v1"}
```

`A = e11a24a8784901b160173ec2a15b6113aa22678d852ae8109f84cd4706331e0d`; `G = 1111111111111111111111111111111111111111111111111111111111111111`.

Base prevote E, exact mPV=J(E), **727 bytes**:

```json
{"domain":"zoidbergchain/bft-vote/v1","network_id":"task717i-test","object_type":"bft-vote","payload":{"agreement_profile_digest":"e11a24a8784901b160173ec2a15b6113aa22678d852ae8109f84cd4706331e0d","block_hash":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","block_height":1,"genesis_hash":"1111111111111111111111111111111111111111111111111111111111111111","message_version":1,"parent_hash":"1111111111111111111111111111111111111111111111111111111111111111","round":0,"step":"prevote","validator_epoch":0,"validator_id":"0x7e5f4552091a69125d5dfcb7b8c2659029395bdf","validator_set_commitment":"6fb37df7e489c39287ea827d08f32467f84116d1e8758304d86672a6fd935518"},"protocol":"zoidbergchain","protocol_version":2}
```

For every case, begin from this base E and apply this complete mutation map;
paths are relative to E. A key not listed is retained exactly. No replacement
of one hex substring elsewhere is implied. Then sort object keys with J.

| Case | Exact mutations from base |
| --- | --- |
| proposal | `{"domain":"zoidbergchain/bft-proposal/v1","object_type":"bft-proposal","payload.step":"propose","payload.valid_round":-1}` |
| prevote | `{}` |
| precommit | `{"payload.step":"precommit"}` |
| nil-prevote | `{"payload.block_hash":null}` |
| nil-precommit | `{"payload.block_hash":null,"payload.step":"precommit"}` |
| round-one-prevote | `{"payload.round":1}` |
| justified-proposal | `{"domain":"zoidbergchain/bft-proposal/v1","object_type":"bft-proposal","payload.round":1,"payload.step":"propose","payload.valid_round":0,"payload.validator_id":"0x2b5ad5c4795c026514f8317c7a215e218dccd6cf"}` |
| network-b | `{"network_id":"task717i-test-b","payload.validator_set_commitment":"c1a3521be5435cae728afdf5fc6b7ba97d842419e07873da13f3a1efd2bbcc14"}` |
| genesis-b | `{"payload.genesis_hash":"2222222222222222222222222222222222222222222222222222222222222222","payload.parent_hash":"2222222222222222222222222222222222222222222222222222222222222222"}` |
| set-b | `{"payload.validator_set_commitment":"6e47544dbe60babc8485a457af33695a2ef0e1782a942394b606633926d47a8d"}` |
| conflicting-prevote | `{"payload.block_hash":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"}` |
| conflicting-proposal | `{"domain":"zoidbergchain/bft-proposal/v1","object_type":"bft-proposal","payload.block_hash":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","payload.step":"propose","payload.valid_round":-1}` |
| precommit-key-2 | `{"payload.step":"precommit","payload.validator_id":"0x2b5ad5c4795c026514f8317c7a215e218dccd6cf"}` |
| precommit-key-3 | `{"payload.step":"precommit","payload.validator_id":"0x6813eb9362372eef6200f3b1dbc3f819671cba69"}` |
| precommit-key-4 | `{"payload.step":"precommit","payload.validator_id":"0x1eff47bc3a10a45d4b230b5d10e37751fe6aa718"}` |
| conflicting-precommit-key-1 | `{"payload.block_hash":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","payload.step":"precommit"}` |
| conflicting-precommit-key-2 | `{"payload.block_hash":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","payload.step":"precommit","payload.validator_id":"0x2b5ad5c4795c026514f8317c7a215e218dccd6cf"}` |
| conflicting-precommit-key-3 | `{"payload.block_hash":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","payload.step":"precommit","payload.validator_id":"0x6813eb9362372eef6200f3b1dbc3f819671cba69"}` |
| prevote-key-2 | `{"payload.validator_id":"0x2b5ad5c4795c026514f8317c7a215e218dccd6cf"}` |
| prevote-key-3 | `{"payload.validator_id":"0x6813eb9362372eef6200f3b1dbc3f819671cba69"}` |
| prevote-key-4 | `{"payload.validator_id":"0x1eff47bc3a10a45d4b230b5d10e37751fe6aa718"}` |

### A.1 Message bytes, digests and signatures

For each row below, personal_preimage is the exact prefix hex followed by the
raw ASCII bytes of that row's canonical E. Prefix is
`19457468657265756d205369676e6564204d6573736167653a0a` followed by ASCII
decimal(length); for base length 727 the complete prefix is
`19457468657265756d205369676e6564204d6573736167653a0a373237`.
Proposal, precommit and nil preimages differ exactly by their mutation rows;
the programs check their full bytes, lengths, prefix and digests independently.

| Case | len(m) | SHA256(m), message_id | Keccak256(prefix+m), signing_digest |
| --- | ---: | --- | --- |
| proposal | 752 | `8c128259015331ab9af6e38fa13bdf8e6bad5adf675dc01c16e0cb8917d1d456` | `fe6437f6cdfd66be5ddf5f14be962feb4bedac624da9d430eb55a3622f7eda87` |
| prevote | 727 | `61dc09f1cca96983b99acc83247925482041beaa9a82ffab013f515d8aaee2d3` | `741e46ea64b0f977b9fbed8f745c56f8701c0b9657d77ffc0b351defd5ba361a` |
| precommit | 729 | `2904aa247410a48a54b111e75907af6454a65bcc0f3a803db9b0b3ada1cc3220` | `f85e74c3a2c2049d1b93c3a89b2861acaee96af552fe4e3c3ca4a92e1c783cc8` |
| nil-prevote | 665 | `dab885a2e2a8227247505d655f728e9873d0a60bf1c0c980cc56decb7761c2c4` | `7fc0f423002897617c7935ee15de65cade6fbff06585064b113ee091e86a7236` |
| nil-precommit | 667 | `77131b2d78f8688a659daa8db1fadbb5d15925e33d67bfa004fd1fdb2159050d` | `e5058917bedffe466b56c7f959b193b7f24032beaa84dc9c862844c611d5ec87` |
| round-one-prevote | 727 | `b181a850ab31eea5914a5257eb1fb102bb1378004a950b33c5cfcefe4f12268e` | `7a2b50ec36bddd7b5052b5c46b659e0e110493a13a17634521d4e37e79587baf` |
| justified-proposal | 751 | `06eda4c936fb7447cde73f35397aef0368a2a8eb8686b73277547766b49bef26` | `04a533329eb04d973c104e0c6225685a080df594d958f7da794766caef16ab78` |
| network-b | 729 | `c29db1d223236c3ef965bd65b730400e206a8fb752e43358fbf7edba8c07b1d6` | `45cf874d94704da60e3899b2f51854167af3e8c6427ce5c97a7b65912e8e7421` |
| genesis-b | 727 | `3493b33722ffc145896a3f7b1aae55d71675f4af8f2e5646e591105a50aedeae` | `1f7384f42631472cef1fe496cddf6218d4682b3fb5c376b11b9db94230e83262` |
| set-b | 727 | `a957ce9d389124faf4e080e3756f7c2d02cd456cf967cf9c8a19314c16baa62b` | `8a1c1e5eace4df1bfafd3651b329a2d8885923fe7d9be5635f372454d91518d9` |
| conflicting-prevote | 727 | `178405dcf109cb4e44ac943c7938f3b6bc0c35374a3c196cf5163ef21ef063ee` | `566cfc238ec7718584000449a3fcabeb2bcb826c8e6d545c9ff2271e94a714e6` |
| conflicting-proposal | 752 | `69dd24066766d05cbd4b792426ecc0ff0e05908031cb1c7ceef045b7ee988ecc` | `1b27b74ff11c972e137ff5e3f2d0d552f3b1cad8f6bcd2084c3350379563dc26` |
| precommit-key-2 | 729 | `2ec75669de30ed5bd68d8bddd3a1db8718dd18072d01dbf8fe01482320965341` | `3776dfc36ce42f4a940c8c89faf17daee2f54b4b70f76bdea3102a23ec02f242` |
| precommit-key-3 | 729 | `e77d2fd2d11f4e7152f14b3e5a8c8ce21bbc46824f7ce45b1cfe925dfd3dcd06` | `28b03a2d49b3ef9ab050def8d40816bccdcc2d1accd78a01a24f1dac2d490f9f` |
| precommit-key-4 | 729 | `bc9a4c78c8d6d0b26974fbd629683afcbe27d27a27486cd4e315197b0ac7ae46` | `4bf1e6292ffc66ef3e99fb89cc09167aac17d19e461e2064e8f63406ecaefdab` |
| conflicting-precommit-key-1 | 729 | `55d5a7754cdaefb01980a97a773d8e43b9957fb0f38eb8031a336d9039db6891` | `23055c1f4845698b19f383c5ef7af271c4b79e85459d6331b97b28378a5d5dc2` |
| conflicting-precommit-key-2 | 729 | `d23571b2456543f38e905ea4eeeac1009d2cb385c576b941e26e83adcee7d7c5` | `1068d123637f44e86efa6b3da15ff97491754e931e5998269271a0690fb1abc6` |
| conflicting-precommit-key-3 | 729 | `d42d95d5bb12b66bdef0c8ad79d3227fad65bd4afda63e95f597c3bd7924da54` | `94fb38b78cd1a0ace4469c210f1927785d367f586714f04f9b8d58ffc143d7ae` |
| prevote-key-2 | 727 | `ead40e0929fbbbf90f4635480a07db9ecb77b1a0ac22fe040bd9949d21d3d29b` | `d5a933af9444572a4ec83190e91e2a9ddc76c9739e2956476328269118effa99` |
| prevote-key-3 | 727 | `3f5945673167c939ce009013876dc498b87972f700ef8c267b4bd74679af6bba` | `09590ed70689412ddbdd3723a7096cd6f60c0b6bde95c13cfdc44fe8813e946d` |
| prevote-key-4 | 727 | `33fedd0ebf857ced36278301dac25e72377ef7f00dcab95ea4d945413d666203` | `a62625b81112ef5951be2b4dda832e169f77df0616f3c4ffcfecb2b9d23f30c3` |

The full Signed record is exactly
`{envelope:E,signature:signature_from_row,signature_scheme:"personal_sign"}`.
The base row's signature is sPV for the declarative crash/retry vectors.

| Case | Signature (r32/s32/v1) | len(J(Signed)) | SHA256(J(Signed)) |
| --- | --- | ---: | --- |
| proposal | `0x231426ac6aa087ca3fed84a85d949d7f8bebf9bea647861393732a7756f9ab257ed3d141cf079511a8a164b9e83dc12e8fcddab59265c71e104efe9e0670541b1b` | 947 | `e0c14b62bd8f3b1d26222c9bcbfbca634657da471260734eaf3aa160172b8085` |
| prevote | `0xa2ad4144e11687fcfaf1049551b34054e891268814b0d812c38b7e47fbc5c0964823383911f40f0cf8a20db7478f877a26fc23d124d3d56f045c1a7972f94f451c` | 922 | `eb5b273b9ee4015dd7d7baad90a234baa1b106d98933c674cfd1e89daadbe983` |
| precommit | `0xbe3197f0623638e90b0aea8c3ccd254fedee367f5a032ce0ef16729944dc07cc0a47efac91da26ea6eb5e77eb62c1fc464c33a7c9f52a11a0d2869e48d268b141b` | 924 | `e91a786f426a49665431cc339cdcf53b11c69f04e2d985aafb51484ac3c6d5a4` |
| nil-prevote | `0x1994c1b8fcd9d5f8edd5fbabd94d3a0587db9068ca910bb9d6cac8701017aabb6a22d5c682026aeec2393c35e6e10721a24d2efd7b1237ecb432652e308be9281c` | 860 | `a1abc3b7d37311be00bd2c5c55ed9482ed235a2c9522a29d7c570cd28a3d1291` |
| nil-precommit | `0xe4b0fb5114b50432935b828aa006609f7b064392d02ac8af901f4f16d76ac0cc5912513e8753ea9a22b5a8c5bf09cbc66ca429fb2d18fabbc9eba73089f512e61c` | 862 | `f9891da3927378fc0bc43401ee368292b6bb4e06c11e5915f15ea56631925446` |
| round-one-prevote | `0x8e63c3700675a8e6fa609745615549529b6643f0060fb39a77c073be60395de03053168f529fc8a8d1e64a6a5f0f145a1a621cba0b244a8216aa42b9c192ac9d1c` | 922 | `e9a63ce320eae44a4ac2a854180fc4e77230705034296b39f2a78a739c00c8cb` |
| justified-proposal | `0xb58f3bdbb9db90e42a05ca7743fc441e0d525a356bf69a5dff0bc48d9667817320fb58718d7fa7e32769f6e607fe09607153c8ed617315008ac396ced786fa301c` | 946 | `e033330652c5fbf8957e2d1cfa1c4c474c7d29aefc923ed1020067eb35508b35` |
| network-b | `0x9a30d3730d7d895bddc91c1e898e2e3980438ae734cbf36a8cc5f031299f30ad73607d6e5b8978608c546cf26b386ea15980b16c45b4ae051458d952ca1049d31c` | 924 | `090f28f4129356de1cceda42398a7bfcbb87e0cad8ebf840f87d000ecfb9b52a` |
| genesis-b | `0xccb584a8d6d764d7113ce00f9fcb2503e3b9db1c035263f5ac7870f812c1e2032f480ca08a5f4338b970928bb5b9f24fd0795b13461540c9eb031e38da6a69501c` | 922 | `87e225138a29d3c21e70b3df5b7ab5c8f59c559e5749bd218a32bb4d04af4a66` |
| set-b | `0x24735d2587c02122020f4399758aa88a21507ae3ed91d7b8eee9f67e9350dc870cd16f1977f429bd254a8d53f077cf48963d0b0c3fba20667fcf6d37bdd2bf1d1b` | 922 | `b9a6d68160b44cc67242aadf633565bd1ecf7049b5f0a7969e8c3348815353b5` |
| conflicting-prevote | `0x7bda87ef72279df261e1d94e1c928cf72176b00ac78912029c6409a3749c51dd6cef88b885e92a8ddddb2033e475125208d7af6d80d8ebd30723722a2ef378511c` | 922 | `95a81dfca410fbf096fd7db31b25aece46e9803c107cdd00d9e08292f7118fc9` |
| conflicting-proposal | `0xf1be31a5205cb3ec8c52d6df0049175b9d180bb8e803145bc4c84b7ecd4c3e1d420e93b91962e45443fafc8b16a0a5d472103af30c599d31f98b25e526ad3bdb1c` | 947 | `43a9d434b6fd39eab6c4516cf2f5e1444ed1a0337e4bfa0bbc6bfe07660e5abb` |
| precommit-key-2 | `0x8dba606bddf88b2a3d7ea4c02114ab756602be804567d297df19479ad06bcb3d1a7f4c3cf0627e827408b0b0c26dda9d0b5a04f9577a2603bd6fc77309eb98e81b` | 924 | `768287a0394744dc94d59732107032661ae115eadd9348ead59d84c88647c033` |
| precommit-key-3 | `0x38764bedfa4ca37233f9a64b8de943b223edaea446b79cae2fe2b9e68f59d9ad3a1528b6c38b847ff7f1f763f6f41bb875d437015a7ff130ceee9ab6906db86c1b` | 924 | `dd4c60b30b2586a7e30a6a969bb83c2fa996579c6811ffea5a929bd47447d918` |
| precommit-key-4 | `0xb9ac34586e292c8148c847a5d92513571dd22c425fa1aac07758f4048baf994365da90455b7fa27274efb296981b79742e372a60c59e035cda056a8e6d330ae81c` | 924 | `b94b6de8c94a3863aeb6c320a778e89f44648f1e191e5d1be753236065a76cff` |
| conflicting-precommit-key-1 | `0xbea7d007306d25ad13e632fa28bba4a9c67ca6caa584f5b5edfa93ee2cb7dde13d618cce4b941acacc7a0b795c0669fff05bd6bdbb3fca0a61caf697a04885c01b` | 924 | `950e406975ee98cce2fe1802342f95ed6716e3cd4f3e56a3ce59f94bdfb771a2` |
| conflicting-precommit-key-2 | `0x30127860f18fbcd22b6481741fc65be67f2bc9806f56b1b8b3b70bfd86f6139b5b816b23178014d4b7d16c3eda9739c0f9d149d357bec2ac8d1631f3ca8d76d41b` | 924 | `797d47dc30e659b5d01a54835d5ebd34946ede273d29eaff51d88d761c7f5ec8` |
| conflicting-precommit-key-3 | `0x98b63432b65ffe2c812ce47ccd61a82d5c3ae232473193763a098ab1b67cf221025ad339fc60a550a10f98827afe10a518a1a4342b15a01394e20ffd9264ca101c` | 924 | `4c4c9bc4da8294ca6d69876457b9cb2d110f627fe09990ef484597302df97c8f` |
| prevote-key-2 | `0x9227cce4020ae8d14501ca688b0e5b5104b4b0c560ad2d0c3186d99d6d09f9643bd4df5b62b6ae18d477b638399d32f32c2bf493cafac8d4d488e640ab7394c61b` | 922 | `011a3805a72abbb93df25d00e680924c5807efdf78f6a73eb0f36345900c943c` |
| prevote-key-3 | `0x49670e7d9b3c34d63141c9dac33c4c7080094adaee9d5e1ef6786bf43c5894bb0e20d3f39076645b8ff1c6ad4763e8d855dcd53027e33e8bf1e14bc6023871161b` | 922 | `58e46be0a7372b68c8d3072c3943153b2ad96e4ef1f6027f9531cc80440820de` |
| prevote-key-4 | `0xc84f6f6362c81f0be56f5cbd457733a4fef86ed8bc65af81a0372ca722fae1e6000be82dca6f9848b6eaa8dcb199875d372b102d0c2cf26766d4a3e7d891311f1c` | 922 | `95f5be20a5ac0c9377e41c02448e34e45203d4c7f5e4b34ed1e322515fb7489e` |

### A.2 PV, commit and future-round proof bytes

Use exactly section 3.1's closed wrappers, sorting votes/precommits/RE by ID,
and the exact Signed records above. `commitment` is the corresponding vote
payload with only validator_id removed; it includes no substituted envelope.

| Object | Complete construction | Bytes | SHA256(J(object)) |
| --- | --- | ---: | --- |
| pv | certificate_version=1; T=base prevote minus ID; votes prevote, prevote-key-2, prevote-key-3 | 3334 | `d5313ae807328192574bc79c53d7fa26b1b3b26ce8f6262a82b7b98d7466d581` |
| q4-x | proof_version=4; T=precommit minus ID; proposal; precommits precommit, precommit-key-2, precommit-key-3 | 4300 | `e872d640fd2ce9991e9e54f25bc204a07d92644442a96c80ddeeaacc3dc15895` |
| q4-y | proof_version=4; T=conflicting-precommit-key-1 minus ID; conflicting-proposal; precommits conflicting-precommit-key-1, -2, -3 | 4300 | `454a7d341eb07906fd3ff74f170a6f7ad7cafef75d5232ed1f46a15fbd1988c5` |
| q4-x-four | q4-x with precommit-key-4 also included, strict ID order | 5225 | `82a4f1a91a95755a64729cf945bd6897a9a89855258baaaffaf5424deb07c302` |
| re | evidence_version=1; messages round-one-prevote, justified-proposal, strict ID order | 1905 | `abdd6e6e78dc2772c0579b7e6d25287a9449b87fd802ff9e91838a19702edcbb` |

The alternate network input recomputes M with NID=task717i-test-b and C=
`c1a3521be5435cae728afdf5fc6b7ba97d842419e07873da13f3a1efd2bbcc14`.
The alternate set uses public scalars 1,2,3,5, with canonical key order and C=
`6e47544dbe60babc8485a457af33695a2ef0e1782a942394b606633926d47a8d`.
The alternate genesis changes G and the height 1 parent to 22 repeated 32 bytes.
D/A remain the explicit synthetic policy context. No actual new network is created.

X/Y proof signatures intentionally demonstrate hypothetical same-height conflict
detection after independent cryptographic verification. Signing both with the
same test identities is **not** a legal honest reference execution within f=1.
The four-signer X proof is compatible with the three-signer X proof. Repeated
identity/mixed-round/invalid-signature variants reject. High-S `(n-s,flip(v))`
recovers the same key and remains the same message/one vote; signed_id can differ.

### A.3 Byte-exact declarative recovery/retry assertions

NS is exactly the section6 namespace with the base context and scalar1 key;
its ID is SHA256(J(NS)). Each line below is one exact canonical fixture, not
a serialized real signer database or claim of implemented recovery. Event IDs
are explicit synthetic witness inputs; message IDs resolve to the full literal
E/signature rows above. Both languages independently construct these assertion
bytes; expected outcomes remain future signer acceptance requirements.

```json
{"case":"retry","db_event_id":"2222222222222222222222222222222222222222222222222222222222222222","db_sequence":43,"expected":"return_exact_stored","namespace_id":"d5f80ef285820d97d2e3553bd5e59a43f3be2cfa13df6e62b4b6ab179e798254","publication":"unknown","request_message_id":"61dc09f1cca96983b99acc83247925482041beaa9a82ffab013f515d8aaee2d3","slot":{"height":1,"purpose":"prevote","round":0},"stored_message_id":"61dc09f1cca96983b99acc83247925482041beaa9a82ffab013f515d8aaee2d3","stored_signature":"0xa2ad4144e11687fcfaf1049551b34054e891268814b0d812c38b7e47fbc5c0964823383911f40f0cf8a20db7478f877a26fc23d124d3d56f045c1a7972f94f451c","witness_event_id":"2222222222222222222222222222222222222222222222222222222222222222","witness_sequence":43}
```

```json
{"case":"conflict","db_event_id":"2222222222222222222222222222222222222222222222222222222222222222","db_sequence":43,"expected":"CONFLICTING_SLOT","namespace_id":"d5f80ef285820d97d2e3553bd5e59a43f3be2cfa13df6e62b4b6ab179e798254","publication":"unknown","request_message_id":"178405dcf109cb4e44ac943c7938f3b6bc0c35374a3c196cf5163ef21ef063ee","slot":{"height":1,"purpose":"prevote","round":0},"stored_message_id":"61dc09f1cca96983b99acc83247925482041beaa9a82ffab013f515d8aaee2d3","stored_signature":"0xa2ad4144e11687fcfaf1049551b34054e891268814b0d812c38b7e47fbc5c0964823383911f40f0cf8a20db7478f877a26fc23d124d3d56f045c1a7972f94f451c","witness_event_id":"2222222222222222222222222222222222222222222222222222222222222222","witness_sequence":43}
```

```json
{"case":"crash-before-publication","db_event_id":"2222222222222222222222222222222222222222222222222222222222222222","db_sequence":43,"expected":"publish_exact_stored","namespace_id":"d5f80ef285820d97d2e3553bd5e59a43f3be2cfa13df6e62b4b6ab179e798254","publication":"not_started","request_message_id":"61dc09f1cca96983b99acc83247925482041beaa9a82ffab013f515d8aaee2d3","slot":{"height":1,"purpose":"prevote","round":0},"stored_message_id":"61dc09f1cca96983b99acc83247925482041beaa9a82ffab013f515d8aaee2d3","stored_signature":"0xa2ad4144e11687fcfaf1049551b34054e891268814b0d812c38b7e47fbc5c0964823383911f40f0cf8a20db7478f877a26fc23d124d3d56f045c1a7972f94f451c","witness_event_id":"2222222222222222222222222222222222222222222222222222222222222222","witness_sequence":43}
```

```json
{"case":"stale-state","db_event_id":"1111111111111111111111111111111111111111111111111111111111111111","db_sequence":41,"expected":"STALE_STATE","namespace_id":"d5f80ef285820d97d2e3553bd5e59a43f3be2cfa13df6e62b4b6ab179e798254","publication":"unknown","request_message_id":"61dc09f1cca96983b99acc83247925482041beaa9a82ffab013f515d8aaee2d3","slot":{"height":1,"purpose":"prevote","round":0},"stored_message_id":"61dc09f1cca96983b99acc83247925482041beaa9a82ffab013f515d8aaee2d3","stored_signature":"0xa2ad4144e11687fcfaf1049551b34054e891268814b0d812c38b7e47fbc5c0964823383911f40f0cf8a20db7478f877a26fc23d124d3d56f045c1a7972f94f451c","witness_event_id":"2222222222222222222222222222222222222222222222222222222222222222","witness_sequence":43}
```

```json
{"case":"same-sequence-divergence","db_event_id":"3333333333333333333333333333333333333333333333333333333333333333","db_sequence":43,"expected":"STALE_STATE","namespace_id":"d5f80ef285820d97d2e3553bd5e59a43f3be2cfa13df6e62b4b6ab179e798254","publication":"unknown","request_message_id":"61dc09f1cca96983b99acc83247925482041beaa9a82ffab013f515d8aaee2d3","slot":{"height":1,"purpose":"prevote","round":0},"stored_message_id":"61dc09f1cca96983b99acc83247925482041beaa9a82ffab013f515d8aaee2d3","stored_signature":"0xa2ad4144e11687fcfaf1049551b34054e891268814b0d812c38b7e47fbc5c0964823383911f40f0cf8a20db7478f877a26fc23d124d3d56f045c1a7972f94f451c","witness_event_id":"2222222222222222222222222222222222222222222222222222222222222222","witness_sequence":43}
```

## Appendix B. Reproduction and verification results

The following programs are **disposable specification oracles**, not a production
parser, application validator, signer journal, consensus engine or service. The
certificate-core checks assume these constructed test contexts; they do not
replace the complete verifier in section 9. Python signs public test constants;
Node independently reconstructs messages/proofs/widths and verifies full keys.

Save the two code blocks as `temp/task717i-reproduce/vectors.py` and
`temp/task717i-reproduce/independent.cjs`, then run from repository root:

```powershell
.\.venv\Scripts\python.exe -B temp/task717i-reproduce/vectors.py
node temp/task717i-reproduce/independent.cjs
```

Use existing project dependencies only; no package installation or live key is
needed. Programs output only to their own directory. Expected JSON vector bytes
and digest/signature tables above are the independent review target.

```python task717i-vector-generator
"""Disposable specification calculations; no node/signer/database imports."""
import copy
import hashlib
import json
from pathlib import Path
from eth_account import Account
from eth_account.messages import encode_defunct
from eth_keys import keys
from eth_hash.auto import keccak

OUT = Path(__file__).resolve().parent
def j(v):
    return json.dumps(v, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('ascii')
def sha(b):
    return hashlib.sha256(b).hexdigest()
def key(i):
    return keys.PrivateKey(i.to_bytes(32, 'big'))
def pub(i):
    return key(i).public_key.to_compressed_bytes().hex()
def addr(i):
    return key(i).public_key.to_checksum_address().lower()
def manifest(network='task717i-test', members=(1,2,3,4)):
    return dict(domain='zoidbergchain/validator-set/v1', membership_version=1,
        protocol='zoidbergchain', protocol_version=2, network_id=network,
        authority_profile='static-genesis-v1', validator_epoch=0,
        byzantine_fault_budget=1, required_quorum=3,
        validator_public_keys=sorted(pub(i) for i in members))
M = manifest()
C = sha(j(M))
D = dict(domain='zoidbergchain/bft-agreement/v1', agreement_version=1,
    protocol='zoidbergchain', protocol_version=2,
    reference='arxiv:1807.04938v3/Algorithm1', rule_selection='printed-lines-1-67',
    authority_profile='static-genesis-n4-f1-q3-v1',
    proposer_profile='height-minus-one-plus-round-mod-four-v1',
    parent_profile='immediate-finalized-v1', wire_profile='bft-ascii-json-v1',
    timeout_profile='linear-1000ms-plus-1000ms-per-round-v1',
    signer_profile='reserve-sign-store-release-v1',
    application_policy_digest='55'*32,
    limits=dict(max_uint=9007199254740991, max_round=2147483647, max_depth=32, manifest_bytes=8192,
        agreement_bytes=4096, envelope_bytes=2048, signed_bytes=2304,
        prevote_certificate_bytes=12288, commit_proof_bytes=16384,
        block_bytes=3145728, proposal_bundle_bytes=3160400,
        round_evidence_bytes=8192))
A = sha(j(D))
def envelope(step='prevote', i=1, h=1, r=0, value='aa'*32, vr=-1,
             network='task717i-test', genesis='11'*32, commitment=C):
    p = dict(agreement_profile_digest=A, block_height=h, genesis_hash=genesis,
        message_version=1, parent_hash=genesis, round=r, validator_epoch=0,
        validator_id=addr(i), validator_set_commitment=commitment,
        block_hash=value, step=step)
    purpose = 'bft-proposal' if step=='propose' else 'bft-vote'
    if step == 'propose': p['valid_round'] = vr
    return dict(domain=f'zoidbergchain/{purpose}/v1', network_id=network,
        object_type=purpose, payload=p, protocol='zoidbergchain', protocol_version=2)
def signed(e, i):
    raw=j(e)
    result=Account.sign_message(encode_defunct(primitive=raw), private_key=i.to_bytes(32,'big'))
    sig='0x'+bytes(result.signature).hex()
    digest=keccak(b'\x19Ethereum Signed Message:\n'+str(len(raw)).encode('ascii')+raw)
    assert bytes(result.message_hash)==digest
    s=bytes.fromhex(sig[2:]); recovered=keys.Signature(s[:64]+bytes([s[64]-27])).recover_public_key_from_msg_hash(digest)
    assert recovered.to_compressed_bytes().hex()==pub(i)
    return dict(envelope=e, signature=sig, signature_scheme='personal_sign')
cases = {}
def add(name, i=1, **kw):
    e=envelope(i=i,**kw); s=signed(e,i); raw=j(e)
    prefix=b'\x19Ethereum Signed Message:\n'+str(len(raw)).encode('ascii')
    cases[name]=dict(envelope=e, preimage_ascii=raw.decode(), byte_length=len(raw),
        message_id=sha(raw), prefix_hex=prefix.hex(), signing_digest=keccak(prefix+raw).hex(),
        signed=s, signed_id=sha(j(s)), signed_length=len(j(s)), expected_key=pub(i))
add('proposal',step='propose')
add('prevote')
add('precommit',step='precommit')
add('nil-prevote',value=None)
add('nil-precommit',step='precommit',value=None)
add('round-one-prevote',r=1)
add('justified-proposal',step='propose',i=2,r=1,vr=0)
add('network-b',network='task717i-test-b',commitment=sha(j(manifest('task717i-test-b'))))
add('genesis-b',genesis='22'*32)
add('set-b',commitment=sha(j(manifest(members=(1,2,3,5)))))
add('conflicting-prevote',value='bb'*32)
add('conflicting-proposal',step='propose',value='bb'*32)
for i in (2,3,4): add(f'precommit-key-{i}',step='precommit',i=i)
for i in (1,2,3): add(f'conflicting-precommit-key-{i}',step='precommit',i=i,value='bb'*32)
for i in (2,3,4): add(f'prevote-key-{i}',i=i)
def commitment(e):
    p=copy.deepcopy(e['payload']); del p['validator_id']; return p
def proof(value='aa'*32, members=(1,2,3)):
    ss=[signed(envelope(step='precommit',i=i,value=value),i) for i in members]
    return dict(proof_version=4, commitment=commitment(ss[0]['envelope']),
        proposal=signed(envelope(step='propose',value=value),1),
        precommits=sorted(ss,key=lambda s:s['envelope']['payload']['validator_id']))
PV=dict(certificate_version=1, commitment=commitment(envelope()),
    votes=sorted([signed(envelope(i=i),i) for i in (1,2,3)],key=lambda s:s['envelope']['payload']['validator_id']))
RE=dict(evidence_version=1,messages=sorted([cases['round-one-prevote']['signed'],cases['justified-proposal']['signed']],key=lambda s:s['envelope']['payload']['validator_id']))
proofs={'pv':PV,'q4-x':proof(),'q4-y':proof('bb'*32),'q4-x-four':proof(members=(1,2,3,4)),'re':RE}
proof_rows={n:dict(value=p,byte_length=len(j(p)),digest=sha(j(p))) for n,p in proofs.items()}
hi=9007199254740991
wide=envelope(step='propose',h=hi,r=2147483647,vr=2147483646,network='n'*64)
wide_s=dict(envelope=wide,signature='0x'+'ff'*64+'1b',signature_scheme='personal_sign')
wide_pc=copy.deepcopy(wide_s); wide_pc['envelope']['domain']='zoidbergchain/bft-vote/v1'; wide_pc['envelope']['object_type']='bft-vote'; wide_pc['envelope']['payload']['step']='precommit'; del wide_pc['envelope']['payload']['valid_round']
wide_pv=copy.deepcopy(wide_pc); wide_pv['envelope']['payload']['step']='prevote'
def wide_cert(kind,n):
    if kind=='pv': return dict(certificate_version=1,commitment=commitment(wide_pv['envelope']),votes=[wide_pv]*n)
    return dict(proof_version=4,commitment=commitment(wide_pc['envelope']),proposal=wide_s,precommits=[wide_pc]*n)
wide_manifest=manifest('n'*64)
cc=dict(agreement_profile_digest=A,validator_epoch=0,validator_set_commitment=C)
sizes=dict(manifest=len(j(wide_manifest)),agreement=len(j(D)),proposal_envelope=len(j(wide)),
    proposal_signed=len(j(wide_s)),prevote_envelope=len(j(wide_pv['envelope'])),
    prevote_signed=len(j(wide_pv)),precommit_envelope=len(j(wide_pc['envelope'])),precommit_signed=len(j(wide_pc)),
    pv3=len(j(wide_cert('pv',3))),pv4=len(j(wide_cert('pv',4))),
    q4_3=len(j(wide_cert('q4',3))),q4_4=len(j(wide_cert('q4',4))),
    round_evidence= len(j(dict(evidence_version=1,messages=[wide_s,wide_pc]))),
    context_extension=len(j(dict(consensus_context=cc)))-1,
    proposal_bundle=3145728+len(j(wide_s))+len(j(wide_cert('pv',4)))+len(b'{"block":,"proposal":,"valid_round_proof":}'))
data=dict(manifest=M,validator_set_commitment=C,agreement=D,agreement_profile_digest=A,
    keys=[dict(scalar=i,public_key=pub(i),validator_id=addr(i)) for i in (1,2,3,4,5)],
    cases=cases,proofs=proof_rows,sizes=sizes)
NS=dict(protocol='zoidbergchain',protocol_version=2,network_id='task717i-test',
    genesis_hash='11'*32,agreement_profile_digest=A,validator_epoch=0,
    validator_set_commitment=C,validator_public_key=pub(1),validator_id=addr(1))
def scenario(name,expected,request='prevote',db_sequence=43,db_event='22'*32,publication='unknown'):
    return dict(case=name,namespace_id=sha(j(NS)),slot=dict(height=1,round=0,purpose='prevote'),
        stored_message_id=cases['prevote']['message_id'],stored_signature=cases['prevote']['signed']['signature'],
        request_message_id=cases[request]['message_id'],db_sequence=db_sequence,db_event_id=db_event,
        witness_sequence=43,witness_event_id='22'*32,publication=publication,expected=expected)
data['namespace']=NS
data['scenarios']={
    'retry':scenario('retry','return_exact_stored'),
    'conflict':scenario('conflict','CONFLICTING_SLOT',request='conflicting-prevote'),
    'crash-before-publication':scenario('crash-before-publication','publish_exact_stored',publication='not_started'),
    'stale-state':scenario('stale-state','STALE_STATE',db_sequence=41,db_event='11'*32),
    'same-sequence-divergence':scenario('same-sequence-divergence','STALE_STATE',db_event='33'*32),
}
(OUT/'vectors.json').write_bytes(json.dumps(data,indent=2).encode()+b'\n')
print(json.dumps(dict(C=C,A=A,sizes=sizes),indent=2))
```

```javascript task717i-independent-oracle
// Disposable independent byte/crypto oracle. No node, database, wallet or consensus service.
const fs = require('node:fs');
const crypto = require('node:crypto');
const assert = require('node:assert/strict');
const v = JSON.parse(fs.readFileSync(__dirname+'/vectors.json','utf8'));
function J(x) {
  if (x===null) return 'null';
  if (Array.isArray(x)) return '['+x.map(J).join(',')+']';
  if (typeof x==='object') return '{'+Object.keys(x).sort().map(k=>JSON.stringify(k)+':'+J(x[k])).join(',')+'}';
  if (typeof x==='number') assert(Number.isSafeInteger(x)&&!Object.is(x,-0));
  return JSON.stringify(x);
}
const sha=x=>crypto.createHash('sha256').update(x).digest('hex');
const mask=(1n<<64n)-1n;
const rc=[1n,0x8082n,0x800000000000808an,0x8000000080008000n,0x808bn,0x80000001n,0x8000000080008081n,0x8000000000008009n,0x8an,0x88n,0x80008009n,0x8000000an,0x8000808bn,0x800000000000008bn,0x8000000000008089n,0x8000000000008003n,0x8000000000008002n,0x8000000000000080n,0x800an,0x800000008000000an,0x8000000080008081n,0x8000000000008080n,0x80000001n,0x8000000080008008n];
const rot=[0,1,62,28,27,36,44,6,55,20,3,10,43,25,39,41,45,15,21,8,18,2,61,56,14];
const rol=(x,n)=>((x<<BigInt(n))|(x>>BigInt(64-n)))&mask;
function keccak(input) {
  const rate=136, b=Buffer.alloc(Math.ceil((input.length+1)/rate)*rate); input.copy(b);
  b[input.length]^=1; b[b.length-1]^=128;
  const a=Array(25).fill(0n);
  for(let off=0;off<b.length;off+=rate) {
    for(let i=0;i<17;i++) a[i]^=b.readBigUInt64LE(off+i*8);
    for(const r of rc) {
      const c=Array.from({length:5},(_,x)=>a[x]^a[x+5]^a[x+10]^a[x+15]^a[x+20]);
      for(let y=0;y<5;y++) for(let x=0;x<5;x++) a[x+5*y]^=c[(x+4)%5]^rol(c[(x+1)%5],1);
      const z=Array(25).fill(0n);
      for(let y=0;y<5;y++) for(let x=0;x<5;x++) z[y+5*((2*x+3*y)%5)]=rol(a[x+5*y],rot[x+5*y]);
      for(let y=0;y<5;y++) for(let x=0;x<5;x++) a[x+5*y]=(z[x+5*y]^((~z[(x+1)%5+5*y])&z[(x+2)%5+5*y]))&mask;
      a[0]^=r;
    }
  }
  const out=Buffer.alloc(32); for(let i=0;i<4;i++) out.writeBigUInt64LE(a[i],8*i); return out;
}
assert.equal(keccak(Buffer.alloc(0)).toString('hex'),'c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470');
const P=0xfffffffffffffffffffffffffffffffffffffffffffffffffffffffefffffc2fn;
const N=0xfffffffffffffffffffffffffffffffebaaedce6af48a03bbfd25e8cd0364141n;
const G=[0x79be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798n,0x483ada7726a3c4655da4fbfc0e1108a8fd17b448a68554199c47d08ffb10d4b8n];
const mod=(x,n=P)=>(x%n+n)%n;
function pow(a,b,n=P){let r=1n;for(a=mod(a,n);b;b>>=1n,a=a*a%n)if(b&1n)r=r*a%n;return r;}
const inv=(a,n=P)=>pow(a,n-2n,n);
function add(a,b){
  if(!a)return b;if(!b)return a;
  if(a[0]===b[0]&&mod(a[1]+b[1])===0n)return null;
  const s=a[0]===b[0]?mod(3n*a[0]*a[0]*inv(2n*a[1])):mod((b[1]-a[1])*inv(b[0]-a[0]));
  const x=mod(s*s-a[0]-b[0]);return[x,mod(s*(a[0]-x)-a[1])];
}
function mul(a,k){let r=null;for(;k;k>>=1n,a=add(a,a))if(k&1n)r=add(r,a);return r;}
const hex32=x=>x.toString(16).padStart(64,'0');
function recover(sig,digest){
  assert(/^0x[0-9a-f]{130}$/.test(sig));const r=BigInt('0x'+sig.slice(2,66)),s=BigInt('0x'+sig.slice(66,130)),vv=parseInt(sig.slice(130),16);
  assert(r>0n&&r<N&&s>0n&&s<N&&(vv===27||vv===28));
  const x=r;assert(x<P);let y=pow(mod(x*x*x+7n),(P+1n)/4n);assert.equal(mod(y*y),mod(x*x*x+7n));
  if(Number(y&1n)!==vv-27)y=P-y;
  const R=[x,y];assert.equal(mul(R,N),null);
  const q=mul(add(mul(R,s),mul(G,mod(-BigInt('0x'+digest),N))),inv(r,N));assert(q);
  // Check verification independently of the recovered-point equation.
  const w=inv(s,N),pt=add(mul(G,mod(BigInt('0x'+digest)*w,N)),mul(q,mod(r*w,N)));assert(pt&&mod(pt[0],N)===r);
  return (q[1]&1n?'03':'02')+hex32(q[0]);
}
function pub(i){const e=crypto.createECDH('secp256k1');e.setPrivateKey(Buffer.from(hex32(BigInt(i)),'hex'));return e.getPublicKey('hex','compressed');}
function address(i){const e=crypto.createECDH('secp256k1');e.setPrivateKey(Buffer.from(hex32(BigInt(i)),'hex'));return '0x'+keccak(e.getPublicKey().subarray(1)).subarray(12).toString('hex');}
function manifest(network='task717i-test',members=[1,2,3,4]){return {validator_public_keys:members.map(pub).sort(),required_quorum:3,byzantine_fault_budget:1,validator_epoch:0,authority_profile:'static-genesis-v1',network_id:network,protocol_version:2,protocol:'zoidbergchain',membership_version:1,domain:'zoidbergchain/validator-set/v1'};}
const C=sha(J(manifest()));assert.equal(C,v.validator_set_commitment);assert.equal(J(manifest()),J(v.manifest));
const D={protocol_version:2,protocol:'zoidbergchain',domain:'zoidbergchain/bft-agreement/v1',agreement_version:1,
reference:'arxiv:1807.04938v3/Algorithm1',rule_selection:'printed-lines-1-67',authority_profile:'static-genesis-n4-f1-q3-v1',
proposer_profile:'height-minus-one-plus-round-mod-four-v1',parent_profile:'immediate-finalized-v1',wire_profile:'bft-ascii-json-v1',timeout_profile:'linear-1000ms-plus-1000ms-per-round-v1',
signer_profile:'reserve-sign-store-release-v1',application_policy_digest:'55'.repeat(32),
limits:{max_uint:9007199254740991,max_round:2147483647,max_depth:32,manifest_bytes:8192,agreement_bytes:4096,envelope_bytes:2048,signed_bytes:2304,
prevote_certificate_bytes:12288,commit_proof_bytes:16384,block_bytes:3145728,proposal_bundle_bytes:3160400,round_evidence_bytes:8192}};
assert.equal(J(D),J(v.agreement));const A=sha(J(D));assert.equal(A,v.agreement_profile_digest);
function envelope({step='prevote',i=1,h=1,r=0,value='aa'.repeat(32),vr=-1,network='task717i-test',genesis='11'.repeat(32),commitment=C}={}){
  const p={step,block_hash:value,validator_set_commitment:commitment,validator_id:address(i),validator_epoch:0,round:r,parent_hash:genesis,message_version:1,genesis_hash:genesis,block_height:h,agreement_profile_digest:A};
  const purpose=step==='propose'?'bft-proposal':'bft-vote';if(step==='propose')p.valid_round=vr;
  return {protocol_version:2,protocol:'zoidbergchain',payload:p,object_type:purpose,network_id:network,domain:`zoidbergchain/${purpose}/v1`};
}
const specs={proposal:{step:'propose'},prevote:{},precommit:{step:'precommit'},'nil-prevote':{value:null},'nil-precommit':{step:'precommit',value:null},
'round-one-prevote':{r:1},'justified-proposal':{step:'propose',i:2,r:1,vr:0},'network-b':{network:'task717i-test-b',commitment:sha(J(manifest('task717i-test-b')))},'genesis-b':{genesis:'22'.repeat(32)},'set-b':{commitment:sha(J(manifest('task717i-test',[1,2,3,5])))},'conflicting-prevote':{value:'bb'.repeat(32)},'conflicting-proposal':{step:'propose',value:'bb'.repeat(32)}};
for(const i of [2,3,4]){specs[`precommit-key-${i}`]={step:'precommit',i};specs[`prevote-key-${i}`]={i};}
for(const i of [1,2,3])specs[`conflicting-precommit-key-${i}`]={step:'precommit',i,value:'bb'.repeat(32)};
const verifiedCache=new Map();
function verify(s){const cacheKey=J(s);if(verifiedCache.has(cacheKey))return verifiedCache.get(cacheKey);const raw=Buffer.from(J(s.envelope),'ascii'),prefix=Buffer.from('\x19Ethereum Signed Message:\n'+raw.length,'ascii'),digest=keccak(Buffer.concat([prefix,raw])).toString('hex');const key=recover(s.signature,digest);verifiedCache.set(cacheKey,key);return key;}
for(const [name,spec] of Object.entries(specs)){
  const expected=v.cases[name],raw=Buffer.from(J(envelope(spec)),'ascii'),prefix=Buffer.from('\x19Ethereum Signed Message:\n'+raw.length,'ascii');
  assert.equal(raw.toString(),expected.preimage_ascii);assert.equal(raw.length,expected.byte_length);assert.equal(sha(raw),expected.message_id);assert.equal(prefix.toString('hex'),expected.prefix_hex);
  assert.equal(keccak(Buffer.concat([prefix,raw])).toString('hex'),expected.signing_digest);
  assert.equal(verify(expected.signed),pub(spec.i||1));assert.equal(sha(J(expected.signed)),expected.signed_id);assert.equal(Buffer.byteLength(J(expected.signed)),expected.signed_length);
}
function core(q){
  const t=q.commitment,ss=q.precommits,ids=ss.map(s=>s.envelope.payload.validator_id);assert(t.block_hash!==null&&t.step==='precommit');
  assert(ss.length>=3&&ss.length<=4);assert.equal(new Set(ids).size,ids.length);assert.deepEqual(ids,[...ids].sort());
  const {validator_id:discard,...pp}=q.proposal.envelope.payload;
  const sorted=manifest().validator_public_keys,proposer=sorted[(pp.block_height-1+pp.round)%4];assert.equal(verify(q.proposal),proposer);
  assert.equal(pp.step,'propose');assert(pp.valid_round===-1||(pp.valid_round>=0&&pp.valid_round<pp.round));
  const {valid_round:ignore,step:also,...common}=pp;const {step:omit,...target}=t;assert.equal(J(common),J(target));
  for(const s of ss){const {validator_id,...fields}=s.envelope.payload;assert.equal(J(fields),J(t));assert(sorted.includes(verify(s)));assert.equal(validator_id, '0x'+keccak(Buffer.from(mul(G,BigInt(v.keys.find(k=>k.public_key===verify(s)).scalar)).map(hex32).join(''),'hex')).subarray(12).toString('hex'));}
  return t.block_hash;
}
function commitment(e){const {validator_id,...t}=e.payload;return t;}
const sigFor=(name)=>({signature_scheme:'personal_sign',signature:v.cases[name].signed.signature,envelope:envelope(specs[name])});
const sortID=a=>a.sort((x,y)=>x.envelope.payload.validator_id.localeCompare(y.envelope.payload.validator_id));
const independentPV={votes:sortID(['prevote','prevote-key-2','prevote-key-3'].map(sigFor)),commitment:commitment(envelope()),certificate_version:1};
const independentQ=(conflict=false,four=false)=>({proof_version:4,proposal:sigFor(conflict?'conflicting-proposal':'proposal'),commitment:commitment(envelope({step:'precommit',value:(conflict?'bb':'aa').repeat(32)})),precommits:sortID((conflict?['conflicting-precommit-key-1','conflicting-precommit-key-2','conflicting-precommit-key-3']:['precommit','precommit-key-2','precommit-key-3',...(four?['precommit-key-4']:[])]).map(sigFor))});
const independentRE={evidence_version:1,messages:sortID(['round-one-prevote','justified-proposal'].map(sigFor))};
const independentProofs={pv:independentPV,'q4-x':independentQ(),'q4-y':independentQ(true),'q4-x-four':independentQ(false,true),re:independentRE};
for(const [name,row] of Object.entries(v.proofs)){assert.equal(J(independentProofs[name]),J(row.value));assert.equal(sha(J(independentProofs[name])),row.digest);assert.equal(Buffer.byteLength(J(independentProofs[name])),row.byte_length);if(name.startsWith('q4'))core(row.value);}
function rejected(f){assert.throws(f);}
const duplicate=structuredClone(v.proofs['q4-x'].value);duplicate.precommits[1]=duplicate.precommits[0];rejected(()=>core(duplicate));
const mixed=structuredClone(v.proofs['q4-x'].value);mixed.precommits[0].envelope.payload.round=1;rejected(()=>core(mixed));
const badSignature=structuredClone(v.proofs['q4-x'].value);badSignature.precommits[0].signature='0x'+'00'.repeat(65);rejected(()=>core(badSignature));
const high=structuredClone(v.cases.prevote.signed),sig=high.signature;high.signature=sig.slice(0,66)+hex32(N-BigInt('0x'+sig.slice(66,130)))+(sig.endsWith('1b')?'1c':'1b');assert.equal(verify(high),pub(1));assert.equal(J(high.envelope),J(v.cases.prevote.envelope));
assert.notEqual(core(v.proofs['q4-x'].value),core(v.proofs['q4-y'].value));
assert.equal(core(v.proofs['q4-x'].value),core(v.proofs['q4-x-four'].value));
let contextMutations=0;
for(const [where,name,value] of [['envelope','network_id','task717i-other'],['payload','genesis_hash','33'.repeat(32)],['payload','validator_set_commitment','44'.repeat(32)],['payload','agreement_profile_digest','66'.repeat(32)],['payload','parent_hash','77'.repeat(32)],['payload','message_version',2],['payload','validator_epoch',1],['payload','step','precommit']]){
  const mutated=structuredClone(v.cases.prevote.signed);(where==='payload'?mutated.envelope.payload:mutated.envelope)[name]=value;
  assert.notEqual(verify(mutated),pub(1));contextMutations++;
}
// Independent maximum-width reconstruction, not cryptographically valid certificates.
const wideE=envelope({step:'propose',h:9007199254740991,r:2147483647,vr:2147483646,network:'n'.repeat(64)});
const wideS={envelope:wideE,signature:'0x'+'ff'.repeat(64)+'1b',signature_scheme:'personal_sign'};
const wideVote=step=>({envelope:envelope({step,h:9007199254740991,r:2147483647,network:'n'.repeat(64)}),signature:wideS.signature,signature_scheme:'personal_sign'});
const wpv=wideVote('prevote'),wpc=wideVote('precommit');
const width=x=>Buffer.byteLength(J(x));
const pvn=n=>({certificate_version:1,commitment:commitment(wpv.envelope),votes:Array(n).fill(wpv)});
const qn=n=>({proof_version:4,commitment:commitment(wpc.envelope),proposal:wideS,precommits:Array(n).fill(wpc)});
const sizes={manifest:width(manifest('n'.repeat(64))),agreement:width(D),proposal_envelope:width(wideE),proposal_signed:width(wideS),prevote_envelope:width(wpv.envelope),prevote_signed:width(wpv),precommit_envelope:width(wpc.envelope),precommit_signed:width(wpc),pv3:width(pvn(3)),pv4:width(pvn(4)),q4_3:width(qn(3)),q4_4:width(qn(4)),round_evidence:width({evidence_version:1,messages:[wideS,wpc]}),context_extension:width({consensus_context:{agreement_profile_digest:A,validator_epoch:0,validator_set_commitment:C}})-1,proposal_bundle:3145728+width(wideS)+width(pvn(4))+43};
assert.deepEqual(sizes,v.sizes);
const NS={validator_id:address(1),validator_public_key:pub(1),validator_set_commitment:C,validator_epoch:0,agreement_profile_digest:A,genesis_hash:'11'.repeat(32),network_id:'task717i-test',protocol_version:2,protocol:'zoidbergchain'};
assert.equal(J(NS),J(v.namespace));
const scenarioSpecs={retry:['return_exact_stored','prevote',43,'22','unknown'],conflict:['CONFLICTING_SLOT','conflicting-prevote',43,'22','unknown'],'crash-before-publication':['publish_exact_stored','prevote',43,'22','not_started'],'stale-state':['STALE_STATE','prevote',41,'11','unknown'],'same-sequence-divergence':['STALE_STATE','prevote',43,'33','unknown']};
for(const [name,[expected,request,sequence,event,publication]] of Object.entries(scenarioSpecs)){
  const x={case:name,namespace_id:sha(J(NS)),slot:{height:1,round:0,purpose:'prevote'},stored_message_id:sha(J(envelope())),stored_signature:v.cases.prevote.signed.signature,request_message_id:sha(J(envelope(specs[request]))),db_sequence:sequence,db_event_id:event.repeat(32),witness_sequence:43,witness_event_id:'22'.repeat(32),publication,expected};
  assert.equal(J(x),J(v.scenarios[name]));
}
console.log(JSON.stringify({cases:Object.keys(specs).length,proofs:Object.keys(v.proofs).length,sha256:'all match',keccak:'all match',full_key_recovery:'all match',context_mutations:contextMutations,maximum_widths:'all match',high_s:'same message/key',duplicate_mixed_bad_signature:'rejected',same_height_conflict:'detected',scope:'certificate crypto core only; no application/genesis validation'},null,2));
```

### B.1 Executed checks and honest limits

- Python 3.13.5, eth-account 0.13.7 and Node.js22.17.0;
  **21** independently reconstructed sign-byte/SHA256/Keccak/full-key cases;
  **5** reconstructed proof objects (PV, three Q4 variants, RE), all byte/hash
  comparisons matched; all closed-width capacity calculations matched in both languages.
  Five declarative crash/retry/stale-state fixture byte strings also matched;
  this checks the specification examples, not an implemented signer.
- Eight altered contexts/purposes with the unchanged base signature failed the
  expected full-key binding; high-S identity/dedup equivalence matched. Duplicate
  signer, mixed-round and malformed-signature Q4 variants rejected; same-height
  X/Y conflict and compatible X subsets distinguished. No measured performance,
  full parser fuzzing, application/genesis acceptance or crash-signer execution claimed.
- Preserved regression selection: **110 passed, 5 failed** on initial run
  in 21.08 s. All five failures were existing media-worker WinError5 access errors
  using the host default temporary folder. Repeating exactly that five-case
  lifecycle file with TEMP/TMP pointed to a disposable workspace directory gave
  **5 passed in 3.57 s**. Thus all 115 selected cases passed across the two runs;
  this is not a claim that the first run was green. No application/test code
  or worker isolation policy changed. The 42 model cases include source-hash
  checking and replay of every retained trace/seed, including both negative controls.
- Default full BFS was not rerun: retained 7.17H evidence and unchanged source
  hashes plus current focused replay tests are the targeted model verification.
  Prior bounded 203,860 states/576,902 edges remain historical bounded evidence,
  not a fresh exhaustive result or formal proof.
- No actual durable signer, production engine, multihost test, power-loss test,
  approved launch genesis or complete positive application-finality vector exists.
  The crash/retry/stale-state rows specify future expected behavior, not passed tests.

Regression reproduction, with the required workspace temporary directory:

```powershell
New-Item -ItemType Directory -Force temp/task717i-repeat-runtime | Out-Null
$env:TEMP=(Resolve-Path temp/task717i-repeat-runtime).Path
$env:TMP=$env:TEMP
.\.venv\Scripts\python.exe -B -m pytest tests/test_milestone_7_task_7_17h_tendermint_model.py tests/test_milestone_7_task_7_17e_finality_durability.py tests/test_milestone_7_task_7_17c_finality_audit.py tests/blockchain/test_task_3_5_validator_quorum_finality.py tests/blockchain/test_task_3_6_public_finality_status.py tests/blockchain/test_protocol_v1_lifecycle_finality.py -q --tb=short --basetemp=temp/task717i-repeat-tests
```

Disposable execution evidence: `temp/task717i/{vectors.json,python-results.txt,
independent-results.txt,regressions.xml,lifecycle-repeat.xml}`. These are ignored
working files, not extra committed deliverables; literal vectors and both
oracles are retained in this document. No original 7.17H evidence changed.

<!-- TASK717I-FINAL-VERIFICATION -->

Final repository/document verification (2026-10-26): branch and HEAD remain
`Compression-State-Bloat-and-Node-Economics` /
`5a8e32136d7703c4537ef96a8769fac43d06773c`. Index is clean. The only working-tree
changes are this new untracked document and the unstaged sixteen-line reference/
gate addition in `milestone-7-distributed-finality-protocol-decision.md`.
Production code, frozen canonical modules, model, traces and existing tests are
unchanged. `git diff --check`, UTF-8/newline/whitespace/fence/local-link checks,
all literal vector-table comparisons and extraction/source equality passed.
Both embedded oracles were extracted into a separate disposable directory and
rerun successfully: 21 messages, five proof objects, eight signature-context
mutations, five declarative recovery assertion constructions and independent
maximum-width calculations. No extra tracked verification files, dependency
changes, signer implementation, commit, push, merge, deployment, reset,
activation or subsequent task were performed. Ready for specification review
and a later owner-performed commit, with section 13's production gates intact.

