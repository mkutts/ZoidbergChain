# Milestone 7 Task 7.17S — Isolated review journal cryptographic verification

Date: 2026-10-28, America/New_York. **Inactive, test-only verification.**

R717's exact laboratory signing bytes now have real secp256k1 public vectors,
Python verification and an independent JavaScript encoder/cryptographic oracle.
This establishes signature/canonical-byte checks and isolated test membership
and quorum structure. It does not authenticate a complete finalized journal,
implement Tendermint, establish trustworthy physical deadlines, approve source
policies or activate a schema. **Production journal and Task 7.17 remain BLOCKED.**

Every eligible vote authoritatively admitted before the agreed cutoff must count,
including negative and unsure votes. No producer-selected subset is introduced.
The media chain still requires one accepted original submission per media block;
this package cannot approve or produce a media block.

## 1. Git prerequisites and scope

| Before any edits | Observed result |
| --- | --- |
| Branch | `Compression-State-Bloat-and-Node-Economics` |
| HEAD | `afdffe52a32f955d35a5daa7872ee4cbc1748bf0` |
| Separately committed R | `cc0edfc` and HEAD `afdffe5`, both Task 7.17R commits |
| Index and full worktree, including untracked files | Empty `git status --porcelain=v1 --untracked-files=all` |
| R prerequisites | Report, `verification/review717r/`, schema/vectors and focused tests tracked and present |
| Earlier fixtures | J/I vectors, K authority code/fixtures and M G2 fixtures available and tracked |
| Instructions | No applicable ancestor/repository AGENTS.md found; no delegation |

Read R, I, J, K, M, the network-wide voting decision O and distributed-finality
decision G; inspected R's actual encoders/model/fixtures, I/J key recovery and
canonical JSON, K's manifest/authority/proof interfaces and M's remaining gates.
R sections 2–4 explicitly freeze enough **laboratory** bytes for the signing
cases below. Owner approval of those bytes for production is a separate gate.
O's older JSON vote proposal is not silently substituted for R's binary profile.

No production code, durable signer, operational secret, database/schema, runtime
configuration, chain state, launch genesis or networking changed. No staging,
commit, push, merge, migration, reset, deployment, activation or Task 7.17T.

## 2. Files and isolation

| Added path | Purpose |
| --- | --- |
| `verification/review717s/__init__.py` | Inactive package, no startup exports |
| `verification/review717s/verify.py` | R byte/signature, pinned membership, PV/proof/clock/checkpoint checks |
| `verification/review717s/history.py` | Restricted four-batch commitment audit; always incomplete history |
| `verification/review717s/fixtures.py` | Public evidence loading and independent local test pins |
| `verification/review717s/check.py` | Reproduce all retained public-vector outcomes |
| `verification/review717s/generate.py` | CLI-only disposable evidence producer; import raises ImportError |
| `verification/review717s/oracle.cjs` | Independent binary encoder, SHA-256, Keccak, secp256k1 recovery/ECDSA |
| `verification/review717s/measure.py` | Local size/cost measurements |
| `verification/review717s/audit.py` | Scope, artifact hashes and JUnit evidence checks |
| `verification/review717s/{vector-results,resource-results,validation}.json` | Machine-readable outcomes, timings and final verification inventory |
| `tests/fixtures/review717s_v1/vectors.json` | Public test identities, exact bytes, signatures and transcripts |
| `tests/test_milestone_7_task_7_17s_crypto.py` | Focused adversarial, interoperability and isolation checks |
| This document | Coverage, reproducibility and remaining gates |

The only previously tracked modification is a reference/gate notice in
[R's report](milestone-7-review-journal-wire-and-closure-contract.md).
All existing code, tests and frozen historical vectors remain unchanged.
The focused isolation test also inventories nonignored untracked Python files.
No active module imports S. Neither verifier nor fixture loader imports the
generator; ordinary import of that generator fails before key generation.
This is a source/API guard, not a claim that malicious Python code cannot execute
a script. The CLI is deliberately capable of signing contradictory test objects
and must never serve as a durable or production signer.

## 3. Exact signing contracts

Let `enc` be the unchanged ordered binary encoder in
[R wire.py](../verification/review717r/wire.py), with the closed registry in
[R schema.json](../tests/fixtures/review717r_v1/schema.json).
`unsigned(X)=enc(X)[:-65]`, excluding exactly the final signature field.
`Ctxt` is the following concatenation, in order:

```text
network:NID || genesis:B32 || protocol:U16=1 || instance:B32 ||
validators:B32 || membership:U64=0 || policy:B32
```

NID is one length byte, 3..64 matching ASCII bytes and zero padding to a 64-byte
block. B widths are raw bytes, not hexadecimal text. Integers are big-endian;
U64 <=2^53-1, round <=2^31-1, valid_round signed int32. Unknown fields, enum,
version, nonzero reserved fields/padding, truncation and trailing bytes reject.
JSON is only fixture display: its strict adapter rejects duplicate keys before
construction, noncanonical received bytes, unknown fields, malformed integers,
floats, bool-as-int and excessive depth/size. It never signs the JSON display.

| Signed record | Exact unsigned fields after Ctxt | Entire input to Keccak256 |
| --- | --- | --- |
| OPEN | submission B16, original B32, creator B20, key B33, media_height U64, media_hash B32, base_height U64, base_hash B32, eligibility_root B32, inventory B32, nonce B16, attempt U8=0 | `EIP191("ZCRJ717R\0user-OPEN\0" || unsigned(OPEN))` |
| VOTE | sid B32, submission B16, original B32, creator B20, key B33, media_height U64, media_hash B32, base_height U64, base_hash B32, deadline U64, dimension U8, choice U8, nonce B16, sequence U8=0 | `EIP191("ZCRJ717R\0user-VOTE\0" || unsigned(VOTE))` |
| MESSAGE | height U64, parent B32, round U32, value B32, nil U8, step U8, validator U8, valid_round int32, justification B32 | `"ZCRJ717R\0consensus\0" || unsigned(MESSAGE)` |
| TIME_SAMPLE | No embedded Ctxt; validator U8, reading U64 | `"ZCRJ717R\0time\0" || enc(Ctxt) || height:U64 || parent:B32 || sequence:U64 || unsigned(TIME_SAMPLE)` |

Here `\0` denotes literal NUL, not slash/text characters.
`EIP191(M)=0x19 || ASCII("Ethereum Signed Message:\n") || ASCII(decimal(len(M))) || M`,
with exactly one LF and no leading zero in length. Consensus/time use the raw
Keccak digest, with **no** personal-sign wrapper. `preimage_hex` in each vector
contains the entire input to Keccak; `preimage_sha256` is diagnostic and never
substitutes for that signing digest. `hex`/`sha256` cover the complete signed record.
The exact Keccak-input widths are OPEN513, VOTE491, MESSAGE337 and TIME_SAMPLE274
bytes, including purpose and the user-only EIP-191 prefix where applicable.

All four purposes use secp256k1 ECDSA `r32||s32||v1`, exactly 65 bytes, no `0x`
on wire, `1<=r<n`, `1<=s<=floor(n/2)`, v exactly 27/28. Require the entire
recovered compressed finite key, not just an asserted address. Derive wallet as
last20(Keccak256(uncompressed x32||y32)); OPEN must match its creator. VOTE's
reviewer is derived from its key, independent of the submission creator.
Signing uses the installed eth_keys RFC6979 implementation with memory-only
disposable random keys; signatures retained in the vectors are fixed public data.

Reuse I's curve, Keccak, key/Wallet derivation, r/s/v and canonical-display
conventions where compatible. R deliberately changes binary framing, validator
raw-digest domains and low-S acceptance. I's historic high-S acceptance stays
unchanged; R's equivalent high-S variant rejects in both implementations.
No new signature scheme, fallback, production version or general signer is added.

## 4. User-vote coverage and static validator authority

Both dimensions (0 originality, 1 admissibility) and all choices (0 positive,
1 negative, 2 unsure) verify. The verifier requires independently supplied exact
submission/original/creator/media/base bindings plus SID, deadline and dimension
for VOTE, or eligibility_root/inventory for OPEN. It verifies signed context,
key and signature; it does not infer eligibility, admission or quota from them.
Correctly signed foreign-context/session/submission/dimension vectors reject
against the intended local pins, as do mutations retaining an old signature.

S uses K's unchanged `TrustedTestAnchor`, `resolve_authority`,
`StaticTestAuthority` and `resolve_member` for the local static manifest. Only
the new **test manifest's** four sorted full keys authorize indices 0..3;
epoch=0, N4/f1/q3, equal weight, no membership transitions. Network and manifest
SHA-256 match K's pinned context. S independently pins R Ctxt and bootstrap.
Test values are network `task717k-test-journal`, G=`11`*32, instance=`22`*32,
policy=`44`*32, bootstrap=`55`*32. C is SHA256 of the full new public manifest.
These symbolic pins do not assert a hash preimage for an approved descriptor.

M's G2 verifier continues to produce `VALID_ENVELOPE_INCOMPLETE_POLICY` for its
retained profile. It has no complete journal amendment; S does not insert new
fields into that envelope or claim G authenticates this manifest/journal policy.
K's local test authority is B only within those explicit independent test pins.
Production G2 membership and policy authentication remain blocked.

## 5. Validator messages and quorum limitations

Proposals, prevotes, precommits, explicit nil votes, PV and PROOF are supported
for bounded standalone coordinates, including a round-one justified proposal
with its complete matching round-zero PV. Height/parent/round/step/value/nil
must match expected coordinates. At height1 the parent is the independently
derived J0. Proposer is `(height-1+round)%4` in sorted manifest-key order.
Votes require valid_round=-1/zero justification; proposals require -1/zero or
a prior round and the matching complete nonnil PV. Nil=1 requires zero value
and a nonproposal phase. Nonnil never means missing proposal data.

PV requires exactly three sorted distinct matching prevotes (including nil PV).
PROOF requires the scheduled signed proposal, its exact full bounded batch bytes,
and exactly three sorted distinct matching nonnil precommits. Full body hashing
binds the ordered events and header; missing body/proposal bytes never succeeds.
Wrong epoch/C/instance/phase/value, unauthorized keys, duplicate/contradictory
signers and correctly signed mixed-round aggregation reject.

Success is `VALID_MESSAGE_ONLY` or `VALID_QUORUM_STRUCTURE_ONLY`, with separate
flags. Three matching precommits do not prove Tendermint locking, honest custody,
application validity, global decision or finalized ancestry. Standalone signatures
at later coordinates do not demonstrate valid round/height transitions. J's
height1/round0 durable signer and all custody state remain byte-for-byte unchanged.

## 6. OPEN, admission, CLOSE, tally, checkpoint and media boundaries

The restricted laboratory audit accepts exactly four complete batch/proof units:
OPEN; START/EPOCH; ten ADMISSIONs with five adjacent PARTICIPATION controls;
CLOSE/EPOCH. It is deliberately not the general R application engine. It checks
context, J0, parent chain, previous-state transcript commitments, complete ordered
event frames, all time/user/consensus signatures, start/deadline/epoch references,
admission locators/status against explicit fixture eligibility pins, vote fold,
dual tally arithmetic, logical boundary and exact materialized CLOSE page.

Each dimension has three positive, one negative, one unsure and one established
participant: total5, decisive4, ratio3/4, laboratory outcome PASS. These local
arithmetic results are named `fixture_*`, not authoritative eligibility or media
approval. A signed pending negative vote is verified but adds no count, slot,
charge or fold entry. All ten admitted fixture votes remain in both tallies.

OPEN is user-signed; START, ADMISSION, PARTICIPATION, EPOCH, CLOSE and TALLY have
no separate signing authority in R. Their exact bytes are authenticated through
the containing batch value and its signed consensus messages. CHECKPOINT is an
unsigned commitment to Ctxt/height/batch/proof. MEDIA is an unsigned exact
cross-history reference. No invented CLOSE, tally, checkpoint or media signature
is generated. The audit checks the actual CLOSE event ID/locator, checkpoint's
actual proof ID, submission/original/creator, complete counts/fold/tallies and
the independently supplied media parent/next height.

Replacing CLOSE with an old signature breaks the batch commitment. A second
public negative transcript has **fresh valid signatures and a structurally valid
quorum** over a false CLOSE count; quorum crypto succeeds, replay rejects
`replaced_close_page_or_tally`. This is a direct A/B/C versus D/E control.

Even with all four batches present, the result is **INCOMPLETE_HISTORY**.
Missing prefix/body/proof also fails with INCOMPLETE_HISTORY or a structural
rejection, never media PASS. Complete authoritative history cannot be supplied
by a caller boolean. The remaining prerequisites are journal-aware G2 authority,
complete approved source/eligibility/application validation, trusted physical
time and correctly executed agreement. `complete_finalized_history`,
`agreement_execution_verified` and `physical_time_trusted` always remain false.
Signed timestamps establish who attested to readings, not their accuracy,
freshness, durable monotonicity, or a trustworthy real deadline.

## 7. Public interoperability vectors and negative controls

There are **75 signed-record rows: 65 expected signature acceptances and 10
expected rejections**. The public fixture also contains four complete canonical
batch proofs, nonnil/nil PV, a justified round-one proof and the signed false-CLOSE
proof: eight proof objects. Duplicate signed time rows intentionally demonstrate
identical bytes/signatures for identical preimages. There are no private scalars,
seeds, operational keys or secret files. CLI regeneration selects new random
identities and replaces this *new S* public fixture; it is not used in tests.
Retained public bytes/signatures and their verification are deterministic and
independently reproducible without private material. Frozen older vectors stay
unchanged. Reproducing signing identities from a committed seed would violate
this task's no-private-material requirement and is deliberately unavailable.

Python uses eth_keys/eth_utils. JavaScript independently reconstructs every
record, preimage, batch and proof from the closed schema, hashes with Node
SHA-256, computes Keccak in JavaScript and recovers/verifies secp256k1 points
with BigInt arithmetic. It also derives public wallets using independent point
decompression. The arithmetic implementation is ported from I's independent JS
oracle, with R's low-S rule; it never calls Python or a Python crypto library.
It checks the fold, nil/round proofs, wrong purposes, high-S, duplicate signers,
mixed rounds and fresh correctly signed false CLOSE. The output is retained in
the final machine-readable validation record.

| Required negative control | Evidence |
| --- | --- |
| Modified signed payload / choice | Every immutable user field and changed choice rejects |
| Wrong dimension / session / submission | Mutated and freshly signed foreign bindings reject |
| Wrong network / G2 genesis / journal | Context mutations and correctly signed foreign vectors reject |
| Wrong signature purpose | OPEN/VOTE swap, raw/personal mismatch, media/journal domain replay reject |
| Wrong validator epoch / set commitment | Nonzero reserved membership bytes and mismatched C reject |
| Duplicate signer inflation / contradictory votes | Duplicate identity never counts twice |
| Mixed rounds | Real signed round-one precommit cannot join round-zero proof |
| Missing proposal bytes | No full body/proposal means no proof acceptance |
| Missing journal evidence | No complete laboratory prefix means INCOMPLETE_HISTORY |
| Replaced CLOSE page | Old commitment and freshly signed false count both rejected |
| Wrong media parent | Exact independent media anchor comparison rejects |
| Cross media/journal signature replay | Both directions tested with historical and R signatures |
| Unknown fields / duplicate JSON keys | Closed nested shapes, strict parser and canonical byte checks reject |
| Malformed canonical encoding | Padding/version/epoch/truncation/trailing/integer failures reject |
| Correctly signed nonfinalized vote | Signature valid; fixture tally/fold unchanged |

Scalar-zero, invalid v, tampered signatures, high-S, invalid compressed points,
oversized signed objects, missing PV justification and batch work budgets are
also covered. No protocol rule is changed to obtain acceptance.

## 8. Local resources

Sizes are exact: OPEN530, VOTE508, MESSAGE383, TIME_SAMPLE74, PV1150,
PROOF1533, HEADER544, CHECKPOINT275 and MEDIA862 bytes. The four transcript
batches are 1093,706,6381,845 bytes. The mixed third batch has ten user votes,
five participation controls, three time signatures and four consensus signatures:
17 signature checks. The test batch cap remains **262,144 bytes** and the media
block cap **3,145,728 bytes**; S adopts no production limit. Batch+external proof
has maximum263,677 bytes. R regressions retain cap-1/cap/cap+1 transport tests;
no semantically valid cap-sized application batch is claimed.

Measured on this Windows host with CPython3.13.5, warm repetitions, milliseconds:

| Operation | Samples | Median |
| --- | ---: | ---: |
| Signed user vote | 30 | 5.620 |
| Signed OPEN | 20 | 5.919 |
| Quorum proof plus body parsing/hash | 15 | 78.402 |
| Mixed batch, 17 checks | 10 | 194.523 |
| Wrong but well-shaped signature | 30 | 5.004 |
| Malformed zero signature | 30 | 0.711 |
| Oversized signed-object rejection | 30 | 0.004 |

Raw samples, p95, extrema, environment and exact sizes are retained in
[resource-results.json](../verification/review717s/resource-results.json).
These include repeated pinned-authority/key validation; no throughput claim,
CPU budget adoption, remote latency, network benchmark, target-hardware campaign
or source-policy/decoder worst-case bound follows. Oversized exact-width records
reject before crypto; JSON display is capped at8192 bytes and depth32. Complete
source/PV work metering and physical-time availability remain separate R gates.

## 9. Verification and reproduction

```powershell
.\.venv\Scripts\python.exe -B -m verification.review717s.check
node verification/review717s/oracle.cjs
.\.venv\Scripts\python.exe -B -m verification.review717s.measure
.\.venv\Scripts\python.exe -B -m pytest tests/test_milestone_7_task_7_17s_crypto.py -q --tb=short --basetemp=temp/task717s-focused-final --junitxml=temp/task717s-focused-final.xml
```

Focused final suite: **154 passed**. Required regressions: **753 passed** across
R, Q, P, J, K, M, historical v1 golden signatures/canonical bytes and v3 signing/
canonical-format tests. **907 total final cases, zero failures, errors, skips or
timeouts.** The initial focused run passed153 cases before adding the fresh
signed false-CLOSE test; it is superseded, not added to the total. This was not
a whole-repository test run. Independent agreement/model executions, production
source-policy validation, multi-host networking/custody, physical deadline trust
and deployment are excluded by scope, not silently reported as passing tests.

Full commands, per-module counts, case inventory/hashes, initial/final Git state,
independent oracle results and preservation hashes are recorded in
[validation.json](../verification/review717s/validation.json).

## 10. Remaining gates and readiness

| Gate | Status |
| --- | --- |
| Exact isolated signing preimages and public interoperability | READY FOR REVIEW |
| Isolated user verification and local static quorum crypto | READY FOR REVIEW |
| Independently pinned production journal G2/manifest/descriptors | BLOCKED; M has no complete journal amendment |
| Production schema/version and binary profile approval | PENDING owner approval |
| Raw-digest custody integration and separate stream signer state | BLOCKED; J remains height1/round0 and personal-sign only |
| Independent Tendermint engine/refinement and adversarial campaign | BLOCKED; signature checks are not agreement execution |
| Physical clock error/freshness/monotonicity/oracle policy | BLOCKED external predicate |
| Rights, technical, qualification, reputation and full history policy | UNSUPPORTED / owner approval and exact source schemas required |
| Retry, quota/service epoch/closure policy, complete combined media schema | PENDING owner approval; no rule activated |
| Operators, launch keys/genesis, archival/restore/custody/activation | Separate owner/security approvals required |

No supported laboratory signing case needed an invented preimage. Signing cases
outside R's four specified purposes are stopped: there is no standalone CLOSE,
tally, checkpoint, admission or media signing contract. Production descriptor
source schemas, G2 journal authority, combined media hash and honest durable
transition APIs remain unresolved; S does not manufacture substitutes.

The isolated cryptographic package is **ready for review and an owner-performed
commit**. Task 7.17S's cryptographic laboratory scope is delivered, with explicit
partial results for authoritative history and agreement. Production journal
implementation, protocol activation and overall Task7.17 remain **BLOCKED**.
Branch/HEAD are unchanged; final index remains empty. The only tracked edit is
the R reference notice; the named new S files are untracked and ready to inspect.
