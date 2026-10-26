# Milestone 7 Task 7.17K — Isolated static validator authority and proof verification

Date: 2026-10-26 (America/New_York). **Inactive, test-only cryptographic subset.**
Canonical membership, explicit fixture authority, proposal/vote authentication
and PV/Q4 verification are implemented. **Genesis authentication remains
INCOMPLETE_AUTHORITY.** Authenticated application identities, full finalized
ancestry and complete distributed consensus execution are not established.
No signature threshold returned here permits block finalization.

## 1. Repository verification and scope

Before editing:

| Check | Observed result |
| --- | --- |
| Branch | `Compression-State-Bloat-and-Node-Economics`, expected |
| HEAD | `0e1bd2c04a256cb790f005a0ad010225695fa28c` |
| Separate 7.17J implementation commit | `645921a`, isolated crash-safe signer subset |
| Separate 7.17J test/fixture commit | HEAD, `Milestone 7 Task 7.17J: include durable signer tests and fixtures` |
| Worktree/index including untracked files | Completely clean |
| Tracked prerequisites | `isolated_bft717j/{wire,signer,reducer,custody}.py`, schema, test and golden vectors; 7.17H model/check/replay/scenarios and retained traces/results |
| Minimal preflight | 27 passed, 98 deselected in 17.35 s: existing J suite selected with `-k 'frozen or replay'`, including I's signing/proof vectors |
| Instructions | No applicable ancestor/repository AGENTS.md found; no delegation |

Read the [authority decision](milestone-7-validator-authority-and-quorum-decision.md),
[wire contract](milestone-7-bft-wire-and-signer-contract.md),
[durable signer report](milestone-7-bft-durable-signer-implementation.md),
[protocol decision](milestone-7-distributed-finality-protocol-decision.md) and
[model report](milestone-7-tendermint-model-verification.md). Inspected existing
v1 genesis/config/validators, active proof validation, frozen canonical_v3
serialization/finality and wallet signature utilities. Active finality still
uses configured addresses and an embedded proof roster; neither supplies new
historical membership authority. Frozen v1 genesis has no membership field.

No production source, schema, key, launch genesis, runtime store, policy,
networking, migration, deployment, chain disposition or activation changed.
No Tendermint engine, dynamic membership, key rotation, signer expansion,
compression change, Task 7.17L or reviewer-history implementation was begun.
No commit, push, merge or index staging was performed.

## 2. Specified versus proposed boundary and blocker report

“Byte-exact” below means fixed for the authorized isolated 7.17I profile. It
does **not** mean owner-approved production consensus or launch configuration.

| Category | Exact established rule or remaining boundary |
| --- | --- |
| A: byte-exact isolated contract | I sections 2–4 and Appendix A: ten-field M; full compressed keys/derived IDs; J/M/C; closed D/A; exact E/Signed/PV/Q4; EIP-191 preimages; proposer selection, bounds, epoch and explicit parent references |
| B: parameterized test inputs | Synthetic G=`11` repeated 32 bytes, H=`aa` repeated 32 bytes, Y=`bb` repeated 32 bytes; D's synthetic policy digest=`55` repeated 32 bytes; task717i/j/k-test network namespace; public insecure scalars 1..5; random disposable J TestKey integration |
| C: still-proposed production amendments | Full versioned G2 with M/C/D/A/policies and authenticated release distribution; reconciled media/history block payload and hash dispatch; production N4/f1/q3, operators/keys/network, custody and activation |
| D: missing consensus-critical rules | Complete G2 hash envelope/domain/preimage and full immutable application/history policy/combined block schema; authenticated finalized application-prefix integration |

**Blocker:** G2's complete canonical payload and domain are not frozen. Hashing
a newly invented genesis object, partial authority object, or M/D/G tuple would
create an incompatible consensus format. No such format or hash is implemented.
The source-only `M -> C`, policy `-> D -> A`, future complete genesis `-> G`
dependency order remains intact. M and D do not contain resulting G or Q4.
The existing v1 genesis hash remains unchanged and cannot authenticate M.

The independently specified subset uses **separate explicit local fixture
pins** of full M, full D and synthetic G. This is deliberately stronger than
pinning a peer's claimed G alone, but supplies **no cryptographic evidence that
G commits M/D**. It is not an alternative production owner-signed bootstrap.
The supported isolated profile is I's N4/f1/q3 only, not F's N7 alternative or
authority-only A3/Q3 draft. No new quorum policy is introduced.

## 3. Deliverables

| New path | Purpose |
| --- | --- |
| `isolated_bft717k/__init__.py` | Inactive package; no startup hooks |
| `isolated_bft717k/manifest.py` | Closed M parser, local authoring, key/ID/commitment verification |
| `isolated_bft717k/authority.py` | Explicit local test pins, static resolution, incomplete genesis outcome, disposable cache |
| `isolated_bft717k/outcomes.py` | Separate outcomes and immutable guarantee dimensions |
| `isolated_bft717k/verifier.py` | Exact message/PV/Q4 core, historical incompleteness, authenticated equivocation/apparent conflicts |
| `isolated_bft717k/signer_fixture.py` | Narrow constructor gate into unchanged J Signer |
| `tests/test_milestone_7_task_7_17k_validator_authority.py` | Focused adversarial/regression coverage |
| `verification/bft717k/__init__.py`, `fixtures.py`, `measure.py` | Offline insecure evidence producers and reproducible measurements |
| `verification/bft717k/verification-results.json` | Sizes/costs, guarantee results, independent oracle, executed case inventory/source hashes |
| This document | Contract, blockers, results and review boundary |

One existing file is modified:
`tests/test_milestone_7_task_7_17j_durable_signer.py`. Its production-import
inventory now recognizes `isolated_bft717k/` as another inert test package, so
its existing prohibition on active imports of J remains correct after these
new files are committed. No signer assertion or frozen fixture was changed.
The new isolation test independently checks production imports and unchanged
J implementation, H model, vectors, canonical modules and active services.

## 4. Manifest representation, identities and commitment

M has exactly these required fields and values:

```text
{domain:"zoidbergchain/validator-set/v1", membership_version:1,
 protocol:"zoidbergchain", protocol_version:2, network_id:NID,
 authority_profile:"static-genesis-v1", validator_epoch:0,
 byzantine_fault_budget:1, required_quorum:3,
 validator_public_keys:[K0,K1,K2,K3]}
```

Actual integers exclude booleans/coercions. NID is 3..64 ASCII characters,
`[a-z0-9][a-z0-9-]{2,63}`. A key is exactly 66 lowercase hex characters, finite
SEC1 compressed secp256k1, prefix 02/03, x below the field prime and on curve.
Each key has weight one. N is array length, exactly four; no redundant count,
ID list, operator, endpoint or roster metadata fields are permitted.

```text
ID(K) = "0x" || lowerhex(last20(Keccak256(x32 || y32)))
C = lowerhex(SHA256(J(M)))
```

ID uses decompressed coordinates without the 04 prefix, and Ethereum Keccak,
not FIPS SHA3. Full recovered keys must match registered points, as well as
the derived identity. Duplicate keys and duplicate derived IDs reject. Actual
collision generation is infeasible here; a separate injection test exercises
the duplicate-ID guard while retaining four distinct public keys.

J is the unchanged strict canonical JSON primitive plus I's printable-ASCII
restriction: UTF-8, sorted object keys, compact separators, no newline/BOM,
floats, duplicate JSON keys, implicit coercion, noncanonical escapes or unknown
fields. Incoming bytes must equal J(parsed) exactly. Keys must already be
strictly increasing by compressed-key bytes; the parser never sorts input into
validity. Local `construct_manifest` sorts its four supplied keys without
deduplication and validates the result. All 24 construction orders give the
same frozen M/C. Manifest parsing is capped at 8,192 bytes and depth 32 before
curve checks. Hash raw canonical M bytes; domain is inside M, with no prefix,
delimiter, genesis hash or salt.

Frozen base C is
`6fb37df7e489c39287ea827d08f32467f84116d1e8758304d86672a6fd935518`.
The golden file and I document remain unchanged.

## 5. Genesis trust and static historical authority

The boundary deliberately separates four questions:

1. `Manifest` validates internal canonical shape/keys/ordering/IDs.
2. `resolve_authority` checks supplied C against SHA256 of canonical M.
3. Candidate full M/D/G/NID/C/A must exactly match an independently configured
   `TrustedTestAnchor`. A matching self-declared G or internally correct C is
   insufficient. Anchor creation is a trusted local harness operation, never
   a peer/cache deserialization operation; only task717i/j/k-test names are
   accepted. Production network names reject.
4. `genesis_authentication` always returns `INCOMPLETE_AUTHORITY`, with
   `genesis_authenticated=false`. There is no G2 parser, genesis hash derivation,
   release verifier or Boolean membership/genesis assertion accepted as authority.

`StaticTestAuthority` stores immutable anchor bytes and returns fresh parsed
contexts. `resolve_member` checks exact ID/key and integer epoch zero; there is
no current-admin-roster argument. All historical h/round coordinates in I's
bounds use these same keys/C/A/epoch. Later equivocation never removes a key,
changes the denominator or invalidates previously verified certificates.

The optional 1,852-byte base cache is a **local disposable storage format**,
not a consensus/genesis/signing format. It stores canonical full M/D and context
bindings with a cache version/kind. Every reopen requires a separately supplied
anchor, bounds the read, strict-parses and revalidates everything. Rehashing a
changed roster and retaining the same G cannot defeat independent pins.
Truncated, missing, oversized, modified, foreign-anchor or noncanonical caches
fail closed as local storage failures, without repair or membership fallback.
Writes use a temporary file, flush/fsync and atomic replace; replacement failure
preserves the previous file. No authority database, migration, rollback witness
or authoritative finality store is introduced. A fresh-process test reopens the
cache and re-verifies the frozen proof under the original fixture pins.

## 6. Messages, signatures, quorum and evidence

The implementation reuses J's unchanged exact envelope/signature verifier.
Common payload fields are `{agreement_profile_digest,block_height,genesis_hash,
message_version,parent_hash,round,validator_epoch,validator_id,
validator_set_commitment}`. Votes add `{block_hash,step}`; proposals also add
`valid_round`. Envelope fields are `{domain,network_id,object_type,payload,
protocol,protocol_version}`; Signed is `{envelope,signature,signature_scheme}`.
Purpose domains, protocol2/message1, G/A/C/epoch0, h/round bounds and scheduled
proposal key are checked. Proposal hashes cannot be null. Vote nil is exactly
JSON null; zero H64 remains a supplied non-nil identity, not a real block.

For m=J(E), verify Sig65 r/s/v bounds and exact recovered registered key over:

```text
Keccak256(0x19 || ASCII("Ethereum Signed Message:\n") || ASCII(decimal(len(m))) || m)
```

The newline is one 0a byte. No double prefix, digest-as-message, personal-sign
fallback, address normalization or caller-provided message string exists.
Mathematically valid high-S signatures remain accepted, with no extra weight.

PV is exactly `{certificate_version:1,commitment:T,votes:[Signed,...]}`;
Q4 is exactly `{proof_version:4,commitment:T,proposal:SignedProposal,
precommits:[Signed,...]}`. T is the corresponding vote payload minus ID.
PV uses prevotes and may certify nil. Q4 uses non-nil precommits and requires
the matching scheduled signed proposal, same h/r/H/P and all context fields.
Its proposal vr syntax is checked without inventing a recursive old-PV/history
requirement. Q4 does not prove private locking discipline.

Canonical proofs contain 3..4 distinct, authorized, ID-sorted voters; every
vote payload must equal T plus its ID. Duplicate identities/signature variants,
contradictory same-slot entries, mixed rounds/epochs/phases/parents/targets and
proof-selected rosters reject the entire offered wrapper. Undersized wrappers
with otherwise valid entries report `INSUFFICIENT_QUORUM`; they are not valid
canonical PV/Q4. A missing/null Q4 signed proposal reports incomplete data and
does not set `quorum_structure_valid`. Unknown extra fields still reject.
PV/Q4 byte caps are 12,288/16,384; Signed/envelope caps are 2,304/2,048; depth
32 and at most four vote entries are checked before signature work.

`compare_messages` authenticates both inputs before diagnosing retransmission
or equivocation at the same namespace/ID/h/r/purpose. H, parent and vr are not
part of the slot key. Different phases/rounds do not count as same-slot faults.
`compare_quorums` independently verifies both Q4s before comparing same-height
targets. Compatible subsets/signature variants/legitimate rounds are accepted
as compatible metadata. A same-height different target reports **conflicting
test signature thresholds**, with no claim either block is valid/finalized.
X/Y golden fixtures deliberately exceed honest signing discipline. Callers
retain both exact input proofs; this stateless component performs no fault
latch, fork choice, authority update or signing action. Cross-height comparison
requires unavailable verified ancestry and reports incomplete data.

## 7. Historical guarantees and signer integration

Every result has explicit separate dimensions:

| Requested guarantee | This implementation |
| --- | --- |
| A: authenticated static membership | Yes, relative to independently pinned **local test M/D/G**, never genesis-derived authority |
| B: valid exact signatures/quorum structure | Yes, when the result explicitly reports the relevant guarantees |
| C: authenticated block/parent identity | No: signed H/P claims and matching parent references are checked, but combined B hash/policy is unresolved |
| D: full finalized ancestry | No: no authenticated G2, complete application records/policies or versioned finalized prefix |
| E: complete distributed execution | No: a QC does not prove all lock/prevote/timer/private-state transitions |

`verify_history` first checks the Q4, then checks any supplied closed
FinalizedRef `{block_height,block_hash}` (<=113 bytes) against exactly h-1/P,
with height0/G special case. The reference is not itself finality. Missing
block/parent data is explicit; even supplied bytes/reference yield incomplete
history while G2/combined application semantics remain unfrozen. No arbitrary
SHA256(B), new block envelope or SQLite reconstruction substitutes for them.
All returned genesis, block/parent, full ancestry and execution flags remain
false. Results refuse implicit Boolean conversion so callers must inspect
the outcome and particular guarantee instead of treating an object as finality.

`open_test_signer` checks fixture authority and exact key/ID membership before
constructing the original J Signer with that authority's pinned context.
It has no caller-context/membership override and adds no signing implementation.
J still owns reservation/sign/store/release, exact retries, journal replay,
fencing and unsupported-transition refusal. Tests sign a proposal, refuse a
conflicting signed slot, restart/replay byte-identically without invoking the
key, reject changed C, reject an absent signer before any store creation, and
refuse higher-height/round requests. All 125 original J checks pass. The
height1/round0 restriction and witness-emulator limitations are unchanged.

## 8. Failure classifications and later state-machine handling

| Outcome | Meaning / obligation for a future real engine |
| --- | --- |
| `INVALID_MEMBERSHIP_MANIFEST` | Deterministically malformed canonical M; reject it, do not derive authority |
| `WRONG_TRUSTED_GENESIS_OR_NETWORK` | Fixture root/context mismatch, including wrong C/A; reject that namespace, do not adopt peer pins |
| `INVALID_CRYPTOGRAPHIC_PROOF` | Malformed wrapper/signature/slot/phase/parent reference; reject offered proof, retain independently authenticated messages where applicable |
| `INSUFFICIENT_QUORUM` | No valid certificate; wait/collect distinct authorized evidence, never lower q |
| `INCOMPLETE_AUTHORITY` | Genesis bootstrap verification unavailable; cannot authorize production consensus |
| `INCOMPLETE_PROPOSAL_OR_ANCESTRY_DATA` | Missing required sources or unresolved schemas; fetch/wait or remain gated, do not finalize or call media objectively invalid |
| `LOCAL_STORAGE_FAILURE` | Unreadable/corrupt/wrong-anchor cache or write failure; stop local use/reload from independent sources under the same pins, never rewrite membership |
| `LOCAL_VERIFICATION_RESOURCE_FAILURE` | Memory/provider/OS resource failure; remain locally unavailable and retry under operational policy, not protocol-invalid |
| `VALID_AUTHENTICATED_TEST_MESSAGE` / `VALID_AUTHENTICATED_TEST_QUORUM_PROOF` | Only the expressly reported fixture/crypto guarantee; real transition guards/full application/parent verification remain necessary |
| Authenticated test equivocation/apparent quorum conflict | Preserve authentic inputs, keep static membership; a future finalized-conflict latch needs both complete validated branches plus durable evidence/fault handling |

No outcome executes a Tendermint transition here. A future engine must follow
the exact reference guards, preserve locks and sources, and commit complete
decision/application/fault state before publication. Operational unavailability
does not become deterministic media invalidity. Later static-key compromises
can forge historical signatures; these signatures are not forward secure.

## 9. Measurements and reproducible verification

Measured with CPython 3.13.5 on Windows 11, using only disposable files and the
existing dependencies. Timings are medians of 15 sequential verifications,
including test-context revalidation, parsing and signature recovery. All size
rows below use actual correctly signed cryptographic fixtures; their H/G values
are synthetic and do not assert real genesis/application records.

| Object | Base fixture bytes | Actual maximum-width bytes | Signature recoveries at maximum |
| --- | ---: | ---: | ---: |
| M / D | 552 / 892 | 603 / 892 | 0 |
| PV q3 | 3,334 | 3,583 | 3 |
| PV N4 | Not retained at base width | 4,581 | 4 |
| Q4 q3 / N4 | 4,300 / 5,225 | 4,632 / 5,632 | 4 / 5 (proposal plus votes) |

All maximum widths exactly match I section 11. NID64, maximum height/round and
valid_round are used with valid scheduled-proposer signatures. Proof ceilings
remain 12,288/16,384. Maximum-width PV q3/N4 median times were 36.8285/47.7596 ms;
Q4 q3/N4 were 50.9451/61.3608 ms. Base Q4 q3 was 48.9510 ms. Traced Python peak
allocations were 36,561..44,946 bytes across the measured fixtures. These are
not process RSS or total native crypto memory. `signature_checks` counts entry
authentication attempts; on these valid fixtures each is exactly one signature
recovery. Local cache content is 1,852 bytes, excluding filesystem allocation;
authority database bytes are zero. Full-node throughput, node economics,
production isolation and multi-host performance are unmeasured.

Final tests: **336 passed, zero failures/errors/skips**:

| Selection | Passed |
| --- | ---: |
| New 7.17K focused/adversarial suite | 113 |
| Existing J signer including I frozen vectors/independent JS | 125 |
| H model, retained source/trace replay and negative controls | 42 |
| E finality durability | 36 |
| Legacy quorum/status/lifecycle | 20 |

The frozen independent JavaScript oracle independently reconstructs M/D and
message/proof objects and checks **21 messages and five proof objects**,
including SHA256, Keccak, full-key recovery and maximum widths. It is copied
unchanged into a disposable directory along with the unchanged golden fixture.
The new tests also check all four frozen PV/Q4 objects directly. No expected
vector was rewritten. The focused suite initially rejected a mistakenly
65-character maximum-width test network; correcting the fixture to the specified
64 characters resolved the failure without relaxing parsing rules.

Adversarial coverage includes every requested category: order-independent local
construction; duplicate keys/IDs; malformed keys/types/canonical bytes; wrong
network/genesis/protocol/root/C/A; self-asserted peer authority; exact-full-key
signature impersonation; zero/one/two versus three distinct voters; duplicate
and high-S weight inflation; equivocation; mixed epochs/rounds/phases; nil and
zero-hash handling; wrong/missing parent/proposal; authentic apparent conflicts;
fresh-process restart; corrupt/rehashed foreign cache; absent signer; signed-slot
replay; and legacy finality nonregression. Local memory and cache-write faults
remain operational failures. Conflicting QCs do not certify engine safety.

Reproduce from the repository root:

```powershell
.\.venv\Scripts\python.exe -B -m pytest tests/test_milestone_7_task_7_17k_validator_authority.py -q --tb=short --basetemp=temp/task717k-focused --junitxml=temp/task717k-focused.xml
New-Item -ItemType Directory -Force temp/task717k-runtime | Out-Null
$env:TEMP=(Resolve-Path temp/task717k-runtime).Path
$env:TMP=$env:TEMP
.\.venv\Scripts\python.exe -B -m pytest tests/test_milestone_7_task_7_17j_durable_signer.py tests/test_milestone_7_task_7_17h_tendermint_model.py tests/test_milestone_7_task_7_17e_finality_durability.py tests/blockchain/test_task_3_5_validator_quorum_finality.py tests/blockchain/test_task_3_6_public_finality_status.py tests/blockchain/test_protocol_v1_lifecycle_finality.py -q --tb=short --basetemp=temp/task717k-regression --junitxml=temp/task717k-regression.xml
.\.venv\Scripts\python.exe -B -m verification.bft717k.measure --iterations 15 --junit temp/task717k-focused.xml --junit temp/task717k-regression.xml --output verification/bft717k/verification-results.json
```

The JSON retains executed case names, outcome dimensions, hashes, sizes and
observations; disposable JUnit XML and runtime stores are under ignored temp/.
No full-repository, production engine, physical-power-loss or live-network test
is claimed. Measurements vary; byte widths and golden commitments do not.

## 10. Remaining owner/security gates and review readiness

Production requires approval/freeze of full G2 serialization/domain/hash and
authenticated release pins; complete policy registry and reconciled combined
application/history block schema/hash dispatch; actual independent N4/f1/q3
operators/keys/NID/G and cumulative compromise assumptions; custody with real
nonrollbackable enforcement and filesystem/power-loss review; full agreement
implementation/refinement, synchronization, archival/conflict persistence,
adversarial multi-process/host tests and independent security review. Reviewer
bootstrap/cohort/all-unsure/issuance/timestamp/media-only-history decisions and
explicit activation/state-disposition approval remain separate blockers.

**Ready for review and a later owner-performed commit of this bounded isolated
subset.** The full requested genesis-authenticated authority guarantee remains
incomplete, and full historical ancestry/distributed consensus/production
readiness remain blocked. Final branch and HEAD match section 1; the sole
existing-file edit and new files are unstaged, with the index unchanged.
