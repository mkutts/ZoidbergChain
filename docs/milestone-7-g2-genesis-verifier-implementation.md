# Milestone 7 Task 7.17M — isolated G2 envelope verifier

Date: 2026-10-27 (America/New_York).

**Test-only reference implementation of the inactive 7.17L proposal.** A matching
independent test pin yields `VALID_ENVELOPE_INCOMPLETE_POLICY`, never complete
semantic genesis validity or production consensus authority. No production
genesis, chain state, consensus, signer transition, activation or deployment is
changed. Task 7.17 reviewer-history implementation remains blocked.

## 1. Repository prerequisites and scope

Initial branch: `Compression-State-Bloat-and-Node-Economics`.
Initial HEAD: `f309c9dd89bdb39b066200d7b0c930ab5481abe2`, separately committed
Task 7.17L (`Milestone 7 Task 7.17L: specify G2 genesis and bootstrap commitments`).
Index and worktree were completely clean, including untracked files, according
to `git status --porcelain=v1 --untracked-files=all`.

K implementation/tests are tracked (`isolated_bft717k/` and its regression
suite, commits `efabce1`/`4ce42c3`). I vectors/oracle, J implementation/tests,
and H model/tests/traces remain available and unchanged. No applicable ancestor
or repository `AGENTS.md` was found. No delegation was used.

Read the [L proposal](milestone-7-g2-genesis-and-bootstrap-contract.md),
[authority decision](milestone-7-validator-authority-and-quorum-decision.md),
[K implementation report](milestone-7-bft-validator-authority-implementation.md),
[I wire contract](milestone-7-bft-wire-and-signer-contract.md),
[v3 schema decision](milestone-7-v3-canonical-schema-decision.md), and
[reviewer-history amendment](milestone-7-v2-reviewer-history-protocol-amendment.md).
Inspected existing canonical primitives, v1 genesis preimages/allocations,
native ledger boundaries, K manifest/authority and I agreement/context code.
Earlier documents remain historical proposals where superseded by L.

New files:

- `isolated_g2717m/{__init__,verifier,authority_adapter}.py`
- `tests/test_milestone_7_task_7_17m_g2_genesis.py`
- `tests/fixtures/g2717m_v1/vectors.json`
- `verification/g2717m/{__init__,fixtures,measure}.py`
- `verification/g2717m/oracle.cjs`
- `verification/g2717m/verification-results.json`
- This report.

Modified existing files: only the J and K regression suites, one isolation
allowlist line each, to classify `isolated_g2717m/` as another isolated test
package once committed. No signer, quorum, manifest, historical vector, model,
canonical_v3 or production code/assertion is relaxed. The new isolation test
also scans nonignored untracked Python files, so this boundary is tested before
the later owner-performed commit.

## 2. Field-by-field contract boundary

A = exact representation/digest/bounds; B = closed outer representation with
unapproved semantics; C = launch-selected value with specified type/rule;
D = unresolved consensus representation/preimage. Mixed labels below separate
the representation from its authority. No production schema is adopted here.

| Required payload field | Classification and implemented boundary |
| --- | --- |
| genesis_version | A: UInt exactly 2 |
| index | A: UInt exactly 0 |
| previous_hash | A: lowercase H64, exactly zero |
| application | C: exact Application grammar and independent pin match |
| initial_block_version | A/B: UInt 4; does not implement block4 |
| consensus_message_version | A: UInt 1 |
| validator_manifest | A/C: exact I/K ten-field M, four valid ordered keys/IDs; actual operators unapproved |
| validator_set_commitment | A: SHA256(J(M)) |
| agreement_descriptor | A/B: exact I descriptor/constants/limits, application policy authority incomplete |
| agreement_profile_digest | A: SHA256(J(descriptor)) |
| policy_registry | B/D: exact PR1/ten candidate dispatch entries and canonical source bytes; inner schemas unresolved |
| policy_registry_digest | A: SHA256(J(PR)) |
| reviewer_bootstrap | B/C: exact closed B0, ordered Wallet grants, policy source binding; launch grants/semantics unapproved |
| reviewer_bootstrap_digest | A: exact reviewer-bootstrap domain envelope hash |
| native_bootstrap | B/C: exact closed N0, positive balances/nonce/supply arithmetic; launch economics unapproved |
| native_bootstrap_digest | A: exact native-bootstrap domain envelope hash |
| history_bootstrap | A/B: empty HB, exact S0/H0 and commitments; no later history correctness |

D includes source-policy closed schemas, combined block4 hash/preimage, history
source completeness/order/clock, cohort/all-unsure choices, and native
reward/exhaustion ordering. None is invented. D does **not** prevent hashing
L's exact outer container with included canonical source bytes as uninterpreted
policy sources: L explicitly publishes that incomplete-policy example. All
12 literal example preimages and published SHA256/lengths were checked before
implementation; none was contradictory or rewritten. `{}` is preserved only
as L's negative semantic fixture, never substituted for a missing policy.

## 3. Canonical envelope and parsing

Exactly `J(E("genesis", P, N, 2))` is accepted. E has exactly six keys:
`domain,network_id,object_type,payload,protocol,protocol_version`.
Domain is `zoidbergchain/genesis/v2`, object_type is `genesis`, protocol is
`zoidbergchain`, protocol_version is integer 2. P has precisely the 17 fields
above. Every G2-defined nested object is closed; all fields are required and
all outer null values reject. No portable hash wrapper, timestamp, signature,
own hash, finalized reference, local state, URL or extension dictionary exists.

J is compact sorted-key UTF-8 JSON. Received bytes must exactly equal the
canonical re-encoding; no repair, trimming, sorting of received arrays, case
folding, normalization, implicit conversion or missing-field defaults.
Duplicate keys, trailing data/newlines, nonminimal escapes, BOM, invalid UTF-8,
surrogates, floats/exponents/nonfinite numbers/negative zero and out-of-range
integer tokens reject. UInt excludes bool. All outer strings are printable
ASCII; decoded source JSON retains existing Unicode J rules and exact scalar
order. Unicode equivalents have distinct bytes and identities.

Source bytes are nonempty even-length lowercase hex, decoded at most once per
source. Each must be a complete canonical JSON object, <=8192 bytes. The registry
has exactly ten kind/version pairs in ASCII order: encoding1, history1,
issuance1, media2, native2, reputation3, review3, reviewer2, rights1, technical1.
These are reserved dispatch versions, not approved policy implementations.
Unknown source fields/nulls cannot be semantically classified without the
missing schemas; they never produce full validity. Explicit source context
fields are cross-checked; explicit descendant/dependency field names are
conservatively rejected as described in section 5. No generic source blob
is promoted to an approved policy.

The frozen canonical_v3 implementation is reused without modification. Outer
size/token/container/depth prescans run before JSON tree allocation. Existing
strict parsing authenticates exact spelling and rejects duplicate keys. Each
outer file is parsed once; each policy source once. Only bounded M bytes are
reparsed by the existing K boundary; agreement is compared to I's exact
descriptor encoding. The optional authority adapter intentionally repeats
existing K validation rather than weakening it.

## 4. Commitments and independent pin

Let S(b) be lowercase SHA256 of raw bytes, D(x)=S(J(x)). No hidden prefix,
delimiter, salt, removed field, zero-G substitution or alternate hash is used.

| Commitment | Exact recomputation |
| --- | --- |
| C | D(full included M) |
| PD | D(full included PR including source hex bytes) |
| A | D(full included agreement descriptor); its application_policy_digest must equal PD |
| reviewer/reputation source digests | S(actual decoded respective canonical source bytes) |
| BD | D(E("reviewer-bootstrap",B0,N,1)) |
| ND | D(E("native-bootstrap",N0,N,1)) |
| HD | D(E("history-bootstrap",{history_version:1,bootstrap_events:[]},N,1)) |
| SC | D(E("initial-state",S0,N,1)); S0 binds PD/BD/ND/HD, state_version=1 |
| G | S(entire exact received canonical genesis file) |

Declared H64 commitments must match actual included content and every S0/H0
cross-binding. Hash mismatches have their own outcome, distinct from malformed
representation. A self-consistent replacement policy/manifest/bootstrap still
changes G and fails the unchanged independent pin.

`verify_bytes(raw, trusted_pin=...)` and `verify_file(path, trusted_pin=...)`
require the keyword explicitly. A local immutable `TrustedGenesisPin` binds
G, N, application, protocol2 and static N4/f1/q3 profile. H64/grammar/profile
are validated when constructing that local configuration. Pins are restricted
to K's existing `task717[ijk]-test` namespace and suffixes; no public-network
pin or actual launch identity is embedded. This deliberately narrow adapter
does not widen K's accepted network namespaces.

The genesis cannot supply a trusted pin for itself. An explicit None reports
`INCOMPLETE_AUTHORITY`; a dict/string/self-declared pin is refused. G is compared
with constant-time digest equality after internal checks. Different G/N/
application/profile rejects. A caller can deliberately construct a new test pin
from foreign input, but then that caller has changed its trust assumption; no
cryptographic API can authenticate the caller's provenance decision. There is
no TOFU, network fetching, release signer, cache pin discovery or production
configuration path.

## 5. Dependency order and circularity

Source bytes -> PR/PD -> descriptor/A; reviewer/reputation source digests ->
B0/BD; native bootstrap -> ND; network and keys -> M/C; empty HB -> HD;
PD/BD/ND/HD -> S0/SC/H0; complete P/E -> canonical file -> G.
Only **after** G may consumers derive finalized `(0,G)` and consensus signing
context. These post-G objects are excluded from genesis. NS/J0/rebuilt rows
retained from L are independent diagnostic vectors, not newly accepted genesis
fields or a reviewer journal implementation.

Closed outer schemas reject self hash, finalized-reference, signature and
descendant additions. Source diagnostics reject explicitly named G/A/PD/SC/
bootstrap dependency fields and mismatched explicit network/application fields,
recursing through the bounded source object. This conservative test filter is
not an invented policy schema or an exhaustive semantic cycle detector:
unfrozen source languages could conceal or rename dependencies. Such contents
remain unapproved and incomplete even with a matching pin. No source expression,
signature, external reference, code or policy transition is evaluated. Complete
semantic acyclicity requires the owner-approved closed policy schemas. This
limitation cannot make byte hashing circular because actual source bytes are
fixed leaves; it prevents promotion of that hash result to policy authority.

## 6. K authority integration and clean bootstrap

`bind_test_authority` always rechecks exact full G2 bytes and independent pin;
it accepts no peer manifest, cache, precomputed Result or membership override.
Only a matching incomplete-policy envelope can supply its exact committed M/D/G
to an existing K `TrustedTestAnchor` and `resolve_authority`. Test membership
checks enforce exact keys/derived identities, epoch0 and N4/f1/q3. Duplicate
keys or IDs, noncurve keys, unsorted/oversized rosters and foreign membership
reject. A foreign manifest cannot retain the same pinned G2 identity.

The returned pair retains the G2 incomplete-policy result. K's own
`genesis_authentication` still returns `INCOMPLETE_AUTHORITY`; quorum/history
results are unchanged. The adapter does not open or extend J's signer. J's
height1/round0 guard and custody limitations remain unchanged. Cache regression
reopens under explicit K pins and rejects a foreign pinned context; G2 exposes
no cache-based authority shortcut.

B0 verifies exact version/network, strictly ordered unique canonical Wallets,
<=128 entries, and reviewer/reputation source hashes. Version1 means the fixed
height-zero underlying established grant. Explicit numeric reputation/status,
usage, offense, penalty, participation and receipt fields are forbidden by the
unchanged closed B0. They cannot be added to satisfy an apparent request for
extra zero-valued fields: L represents clean state by version1 and empty HB,
with no inherited activity. Tests reject these fields even when empty.
This verifier does not manufacture later reviewer activity or policy rules.

N0 verifies exact version/network, strictly Wallet-sorted unique accounts,
<=4096 entries, positive canonical Money balances, and next_nonce exactly string
`"1"`. Money is converted to exact integer millionths; each quantity <=10^15
units and allocation sum + separately counted pool must equal total supply.
No float, exponent, redundant zeros, legacy key recipient, initial nonce change
or hidden balance is accepted. Python wide integers avoid overflow. This is
conservation of a test representation, not approval of recipients, supply,
rewards or token economics. The separate published N1 allocation fixture is
tested without changing the zero-supply golden G2.

## 7. Typed results and remaining incomplete cases

| Outcome | Meaning |
| --- | --- |
| INVALID_GENESIS_STRUCTURE_OR_CANONICAL_BYTES | Invalid exact bytes, closed shape, scalar/version, resource cap or structural bootstrap |
| INVALID_COMPONENT_COMMITMENT | A declared component/source/state hash does not match included bytes |
| WRONG_PINNED_GENESIS_OR_NETWORK | Wrong independent local pin or fully coherent foreign context |
| INCOMPLETE_AUTHORITY | No independent expected identity supplied |
| VALID_ENVELOPE_INCOMPLETE_POLICY | Canonical structure, component commitments and independent test pin all match; semantics unapproved |
| LOCAL_IO_FAILURE | Local file cannot be read, including permission/missing file |
| LOCAL_VERIFICATION_RESOURCE_FAILURE | Memory/provider/OS resource failure, not cryptographic invalidity |

Result flags separately report envelope structure, component commitments and
matched test pin. Full semantic validity and production authorization are
read-only false properties. No complete-valid outcome exists. Result and adapter
binding refuse implicit Boolean conversion. Errors return no usable authority.

Outstanding requirements include all ten source schemas/approvals, reviewer
selection/cohort/all-unsure and participation rules, objective offense authority,
complete media/history source inventory and clock, combined block4 preimage,
native reward ordering/exhaustion, actual launch choices, independent operators,
release trust distribution and explicit state-disposition/activation approval.
Correct hashes do not approve any of these.

## 8. Size and parser resource enforcement

| Item | Test-only enforced bound |
| --- | ---: |
| Complete genesis | 1,048,576 bytes; local reads at most cap+1 |
| M / agreement descriptor | 8,192 / 4,096 canonical bytes |
| PR / decoded source | 65,536 / 8,192 bytes; exactly ten sources |
| B0 / reviewers | 8,192 bytes / 128 entries |
| N0 / allocations | 786,432 bytes / 4,096 entries |
| Remaining G2 bytes after five components | 16,384 bytes jointly |
| Container depth | 32; decoded source depth independently 32 |
| Outer generic maxima before allocation | 17 object members / 4,096 array entries / 16,384 encoded string-content bytes |

All limits apply simultaneously. The six component budgets sum to 888,832
bytes, already below 1 MiB; actual fixed schemas tighten this further. Therefore
no valid 1 MiB envelope is claimed. Tests distinguish exact-1-MiB input rejection
for invalid structure from cap+1 rejection for size, plus exact PR cap/one-over,
source8192/8193, reviewer128/129, allocation4096/over, and depth32/33. No padding
field or media-block 3 MiB allowance is introduced.

Parsing/hashing performs bounded linear passes over input, small fixed-schema
key sorting and bounded source parsing. Reviewer ordering uses a bounded
set/sort; allocations use a linear previous-Wallet check. Four manifest key
checks/ID derivations occur per direct verification; no validator signatures or
application policy code execute. Memory is O(input bytes + decoded source/tree
and serialization copies), not streaming O(1). Source hex doubles encoded bytes.
Prescans reject enormous strings/counts/depth before tree allocation and curve
work. No unbounded peer reader exists. Native crypto memory and process-wide
concurrency limits remain outside these local parser measurements.

## 9. Vectors, measurements and historical regression

Versioned fixtures retain the **unchanged** 12 literal L preimages/lengths/
hashes and ten exact negative mutation recipes/hashes. The independent JavaScript
oracle is L Appendix B's independently authored construction, copied unchanged
below a provenance comment; it reconstructs all objects rather than trusting
the Python verifier's output. It matches all 12 canonical objects and all ten
mutated inputs byte-for-byte and by SHA256.

Golden G2: 4,318 bytes,
`0b1b932a7d6cfb0fed6cec2019724b0b0bf6ab13b0516e8d60d63ddbfa25ee94`.
M remains I's `6fb37df7e489c39287ea827d08f32467f84116d1e8758304d86672a6fd935518`.
No frozen expected result was regenerated to accommodate implementation output.

Focused suite: **184 passed**, no failures/errors/skips. Includes all requested
pin/content/canonical mutation classes, changed internally rebound sources,
incomplete reviewer/native policies, foreign membership/cache, exact limits,
Unicode, explicit circularity diagnostics, operational failures, and K adapter
quorum verification. A focused test initially passed K verifier arguments in
the wrong order; correcting the test call resolved it without protocol changes.

Historical selection: **558 passed in 121.43 seconds**, no failures/errors/skips:
K113, J125 (including I signing/proof/independent-JavaScript vectors), H42,
E36, canonical_v3 and selected v1/native/genesis/block/finality regressions.
v1, legacy/v2 and inert v3 hash/signing behavior remains unchanged within this
selection; all corresponding source/fixture paths have no diff from HEAD.
The actual frozen v1 genesis is independently recomputed by the measurement
recipe and remains
`2b99e87f80e0e855ab98b3269b635be5415273f41d7d4bf1a2aeb8b277b13061`.
No full-repository, production-node, power-loss or multi-host run is claimed.

The [machine-readable evidence](../verification/g2717m/verification-results.json)
records all executed test names/statuses, environment, fixtures, hashes,
component sizes, direct-verifier timing and traced Python peak allocations.
Final local measurements (median of seven verifications, memory measured
separately with tracing):

| Case | Bytes | Median ms | Peak traced Python bytes |
| --- | ---: | ---: | ---: |
| Published L envelope | 4,318 | 4.5211 | 22,543 |
| Bounded large representation | 476,926 | 163.9330 | 2,708,030 |

The generated 476,926-byte case uses 4096 allocations, 128 reviewers and three
8192-byte sources; it is a representation stress test with incomplete policy,
not a launch fixture. Timings vary; traced allocations exclude caller buffers,
native crypto and process RSS. Adversarial count/depth/string/size cases retain
separate rejection measurements. Historical J/K test-only keys created by their
unchanged regression harnesses are temporary; no production keys are generated.

Reproduce from repository root (disposable outputs remain under ignored temp):

```powershell
.\.venv\Scripts\python.exe -B -m pytest tests/test_milestone_7_task_7_17m_g2_genesis.py -q --tb=short --basetemp=temp/task717m-focused --junitxml=temp/task717m-focused.xml
New-Item -ItemType Directory -Force temp/task717m-runtime | Out-Null
$env:TEMP=(Resolve-Path temp/task717m-runtime).Path
$env:TMP=$env:TEMP
.\.venv\Scripts\python.exe -B -m pytest tests/test_milestone_7_task_7_17k_validator_authority.py tests/test_milestone_7_task_7_17j_durable_signer.py tests/test_milestone_7_task_7_17h_tendermint_model.py tests/test_milestone_7_task_7_17e_finality_durability.py tests/test_milestone_7_task_7_10c_v3.py tests/test_protocol_v1.py tests/test_protocol_v1_golden_vectors.py tests/test_protocol_v1_freeze_consistency.py tests/test_protocol_v1_native_transfers.py tests/blockchain/test_protocol_v1_genesis.py tests/blockchain/test_protocol_v1_block_format.py tests/blockchain/test_task_3_5_validator_quorum_finality.py tests/blockchain/test_task_3_6_public_finality_status.py tests/blockchain/test_protocol_v1_lifecycle_finality.py -q --tb=short --basetemp=temp/task717m-regression --junitxml=temp/task717m-regression.xml
node verification/g2717m/oracle.cjs tests/fixtures/g2717m_v1/vectors.json
.\.venv\Scripts\python.exe -B -m verification.g2717m.measure --iterations 7 --junit temp/task717m-focused.xml --junit temp/task717m-regression.xml --output verification/g2717m/verification-results.json
```

## 10. Security limits and delivery state

This closes only the technical test-envelope/commitment-to-independent-pin gap.
It cannot prove authentic provenance of a caller-provided pin, policy approval,
key control/organizational independence, valid token economics, complete history,
honest consensus execution, freshest tip, safe custody or recovery under
cumulative key compromise. Source dependency diagnostics are not full policy
validation. Production must not treat the positive incomplete outcome or the
returned K fixture authority as genesis/launch authorization.

The isolated subset is ready for review and a later owner-performed commit.
Full semantic genesis authentication, public-testnet readiness, reviewer-history
implementation and activation remain **BLOCKED** on the decisions above.
Final branch/HEAD are unchanged from section 1; the index remains empty and all
listed additions/edits are unstaged. No commit, push, merge, reset, migration,
production signing, deployment or later task was performed.
