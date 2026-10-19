# Milestone 7 Task 7.10 — v3 Format Implementation Gate

Date: 2026-10-19 (America/New_York).

**Disposition: stopped at Step 2; production format implementation is blocked.**
This document records repository verification, field-budget analysis, precise
schema blockers, and focused baseline checks. It does not define a replacement
protocol, implement v3, or claim that Task 7.10 is complete.

The task requires stopping before introducing an incompatible production format
when required fields remain unbounded or proposed limits conflict. The numeric
proposal is internally consistent. However, the required native transaction
projection and decimal/tally adapter remain explicitly unresolved in Task 7.9;
current adapters retain unbounded fields and cannot supply a strict v3 schema.
Implementing those choices here as if already frozen would choose new consensus
preimages. No production serialization, codec adapter, or new block vectors are
introduced past that gate. This is a schema-definition blocker, not a claim that
an aggregate byte cap could never bound those objects.

## Repository verification

| Check | Observation |
| --- | --- |
| Branch | `Compression-State-Bloat-and-Node-Economics`, as requested |
| HEAD | `824afdb7063bfe68d2381066d575bd6e714f7a1f` |
| Task 7.9 | Separately committed at HEAD: `Milestone 7 Task 7.9: define v3 storage and block capacity architecture` |
| Initial worktree | Clean; `git status --short` produced no entries |
| Instructions | No `AGENTS.md` found in repository or ancestor directories |
| Final worktree | Only `?? docs/milestone-7-v3-block-format-implementation.md`; HEAD and branch unchanged; no source, dependency, fixture, policy, or schema changes |
| Git actions | No staging, commit, push, merge, branch change, or reset |

Read the [compression protocol](milestone-7-compression-protocol.md),
[codec security contract](milestone-7-codec-security-contract.md),
[capacity decision](milestone-7-v3-storage-and-capacity-decision.md),
[composition measurement](milestone-7-block-composition.md), and
[decoder conformance](milestone-7-decoder-conformance.md). Task 7.9 supplies the
new candidate budgets and keeps finality outside the canonical record. Its
section 8 explicitly makes schema/policy/vector freeze (unit 1a) a dependency of
the canonical parser/serializer/hash (unit 1b); section 9.2 still requires the
native projection, nulls, and decimal/tally adapter to be frozen.

Targeted code inspection covered `protocol_v1.py`, `block.py`,
`admission_certificate.py`, `dual_review.py`, `native_transfer.py`,
`protocol_v1_native_transfer.py`, `protocol_v1_submitter_attestation.py`,
`media_technical_validation.py`, the native aggregate in
`services/native_ledger_service.py`, and the strict/isolated codec boundaries.
No current network or database was opened for mutation.

## Required decisions before serialization

### Native transaction schema and nulls

`block.py:Block._consensus_native_transactions_v1` copies each entire record.
`Block._normalize_protocol_v1_value` retains arbitrary dictionary keys, drops
dictionary children whose value is `None`, and converts floats/Decimals to
strings. It is not a closed v3 projection. A read-only probe confirmed that an
unknown native field with 32,769 ASCII content bytes survives this adapter.
There is no applicable individual field limit for that extension in the adapter.

`native_transfer.py:NativeTransaction.to_dict` also includes `status`,
`created_at`, `updated_at`, `admitted_at`, `included_block_hash`,
`included_block_height`, `settled_at`, and `rejection_reason`, alongside signed
transaction fields and optional version/network fields. Task 7.9 expressly
prohibits treating this lifecycle projection as an arbitrary v3 extension.
Which exact fields are required, forbidden, optional, or nullable in the new
record has not been frozen. The block inclusion hash cannot be filled with the
current block hash inside its own preimage; lifecycle changes must not rewrite
immutable block bytes.

For example, the current normalization maps `{"memo":null}` to `{}`.
These are distinct JSON values and produce distinct native aggregates and block
hashes. V3 requires preserving *schema-permitted* nulls, but the native null
allowlist is unresolved. Reusing today's normalization, selecting only signing
fields, or copying all lifecycle fields would each make a different choice.

**Required resolution:** enumerate the complete v3 native record, every field's
type/range/byte bound, allowed nulls, ordering, immutable identity fields, and
protocol-v2 signing/message/transaction-ID adapter. Supply nonempty signed
vectors, including memo/null and Unicode cases, that pin both the native
ASCII-escaped aggregate and enclosing unescaped-Unicode block preimage. The
8,192-byte record and 96 KiB array caps can then be enforced on that schema;
they do not choose it.

### Admission summary decimal adapter

`admission_certificate.py:AdmissionMintCertificateView.approval_percentage`
returns Python `positive_votes / approval_denominator`; `originality_score`
returns the same float. Current `block.py:_normalize_decimal_string` subsequently
uses `Decimal(str(value))`. The v3 contract instead requires explicit canonical
decimal strings, forbids float inputs to canonical serialization, and introduces
no new rounding. Task 7.9 section 3.3 explicitly says a missing exact tally
adapter/vector is a freeze blocker.

A 5-positive/2-negative tally is above the existing 70% approval threshold and
within the proposed 16-vote dimension cap. The read-only view calculation yields
`0.7142857142857143` through today's float/string path; decimal division at
precision 28 yields `0.7142857142857142857142857143`. The exact rational has no
finite decimal expansion. Both displayed strings fit the proposed 32-byte limit
but commit different bytes. This calculation uses a view of tally counters,
not a fabricated qualifying certificate or signature.

**Required resolution:** pin the exact adapter and expected strings for every
permitted denominator, including recurring fractions, preserving the intended
existing tally semantics. Do not select an arbitrary decimal context, round to
monetary precision, or silently introduce a percentage scale. No claim is made
that the existing float arithmetic is nondeterministic on the tested runtime;
the unresolved issue is the approved conversion into the new strict format.

### Closed evidence and new signing context

`media_technical_validation.py:technical_evidence_identity` excludes six local
observation fields rather than selecting a closed set. Its digest includes other
supplied keys. `validate_technical_evidence` checks version/policy, acceptance,
media length/hash, and digest but does not enumerate every allowed key or bound
each extra value. The emitted accepted-evidence fields offer a basis for an
explicit schema; the exclusion helper alone is not that schema.

Existing certificate, review, and transfer validators pin the old context:
certificate version 1, protocol version 1, and review vote version 2. The v3
contract calls for certificate version 2, protocol version 2, review vote version
3, and fresh network/policy bindings. Current votes have no maximum frozen count
or reviewer nonce/message byte budget; a minimum quorum does not supply one.
Task 7.9 proposes those new ceilings and a changed snapshot policy, but the
corresponding policy digest, strict signing adapters, and new-context vectors do
not exist at HEAD.

These are additional freeze/integration requirements. No existing validator is
weakened to accept new versions, and no placeholder policy digest, production
network ID, signature, or certificate is invented. Missing launch identity alone
would not prevent local parameterized tests; it is not presented as the sole
reason for this stop.

## Verified budget arithmetic

Let `J` be the specified compact canonical UTF-8 JSON function, `B` the block
envelope, `P` its payload, and `R = J({"envelope":B,"hash":h})`.
Let `L = 4 * ceil(len(E)/3)` count only base64 payload string contents and
`O = len(R) - L`. All numbers below are **serialized bytes**, except where
explicitly labeled original or encoded payload bytes.

| Quantity | Proposed limit / exact calculation |
| --- | ---: |
| Original accepted image bytes | 2,097,152 |
| Original canonical text bytes | 262,144 |
| Encoded bytes E, before base64 | 2,097,152 |
| Base64 contents at encoded cap L | 2,796,204 |
| Remaining bytes under 3 MiB at that L | 349,524 |
| Certificate value `len(J(P.admission_certificate))` | 196,608 |
| Native array value `len(J(P.native_transactions))` | 98,304 |
| Remaining overhead, including all other values and structure | 32,768 |
| Sum of the three disjoint overhead budgets | 327,680 |
| Conditional maximum R: L + overhead | 3,123,884 |
| Complete record cap | 3,145,728 |
| Margin under complete record cap | 21,844 |

The encoded maximum has remainder two modulo three, so its base64 has one `=`.
Ceiling/padding cannot be omitted. The canonical portable wrapper adds exactly
87 bytes to `J(B)` for a 64-character hash; measuring just the envelope understates
the complete record. The Task 7.7 fixture maxima are not worst-case guarantees.

The three parent limits, **if actually enforced**, prove the conditional fit.
The current code does not enforce them. A valid record exactly at 3 MiB is
unreachable under these tighter simultaneous limits; an eventual C/C+1 test
must also account for rejection by the overhead/encoded caps. Do not fabricate
large signatures or certificates to make a boundary record appear valid.

### Descriptor and every proposed payload field

For a member named `k` whose canonical value has `v` bytes, its contribution
excluding containing-object braces/commas is `len(k) + 3 + v`. Add two braces and
one comma per member after the first for each nonempty object. This formula
accounts for every key and delimiter in the following inventory.

| Payload field(s) | Canonical value byte ceiling under Task 7.9 |
| --- | ---: |
| `block_version` | 1 (`3`) |
| `index` | 16 |
| `previous_hash` | 66 including string quotes |
| `timestamp`, `minted_at` | 34 each, including quotes |
| `transactions` | 16,401: sixteen 1,024-byte records, fifteen commas, two brackets |
| `native_transactions` | 98,304 parent cap; ten 8,192-byte records would give the tighter 81,931 |
| `transactions_hash` | 66 |
| `miner` | 68 |
| `submission_id` | 34 |
| `certificate_id`, `vote_hash` | 66 each |
| `creator_wallet`, `reward_recipient` | 44 each |
| `content_type` | 7 |
| `approval_percentage`, `originality_score`, `reward_amount` | 34 each; exact tally strings unresolved |
| `decisive_vote_total`, `minimum_votes_required` | 2 each as a conservative ceiling under the 16-vote dimension cap; current minimum is smaller |
| `approved_at` | 1 (`0`) |
| `reward_type` | 20 (`"meme_mining_reward"`) |
| `reward_source` | 13 (`"reward_pool"`) |
| `voter_rewards` | 2 (`[]`) |
| `admission_certificate` | 196,608 parent cap; closed new-context schema unresolved |
| `media` | L + 231 for identity, L + 227 for zstd |
| Optional `meme_text` | 6,002 including quotes; 1,000 control scalars can require six escaped bytes each while fitting the 4,096-byte raw UTF-8 cap |

The descriptor's eight required fields are `encoding_version`, `codec_id`,
`codec_version`, `original_size`, `stored_size`, `mime_type`, `original_sha256`,
and `payload`. At maximum size widths and a ten-character allowed MIME, empty
payload accounting is exactly 231 identity bytes or 227 zstd bytes. The complete
`"media":value` member is 239 or 235 bytes plus L. This is analytic accounting
with the payload contents subtracted, not a valid empty-media fixture.

The envelope adds fixed domain/protocol/object/version members and a network ID
of at most 64 ASCII content bytes. Using every value ceiling above, identity at
2 MiB, the optional worst-escaped caption, a 64-byte network ID and both parent
array/certificate caps gives an intentionally conservative accounting ceiling:

```text
J(P)       <= 3,114,900
J(B)       <= 3,115,096
R          <= 3,115,183
S_rest     <=    24,067 < 32,768
```

These widths need not be jointly attainable. In particular the native parent
cap exceeds the sum of its record/count maxima. This calculation shows no
arithmetic contradiction in the proposed *top-level* budget; it does not supply
the missing nested field registry or prove that current admissible evidence can
be represented within it.

### Nested budgets and signatures

| Component | Proposed constraints, all applied together |
| --- | --- |
| Frozen votes | At most 32 total / 16 per dimension; each complete vote <=4,096 bytes; message <=2,048 raw UTF-8 bytes; bounded nonce, times, references and identities |
| Submitter attestation | Complete value <=16,384 bytes; message <=8,192 raw UTF-8 bytes; repeated escaped payload/message copies count |
| Technical evidence | Complete closed value <=8,192 bytes; accepted reason/type/size/hash/policy and applicable nullable image/text fields must be frozen |
| Originality/admissibility tallies | Each complete value <=8,192 bytes; counters bounded by votes and equality with derived tally required |
| Personal-sign signatures | Exactly 65 decoded bytes, canonical lowercase `0x` + 130 hex characters; 132 content bytes / 134 JSON value bytes |
| Certificate signature subset | At most 33 such signatures including submitter: 4,356 content bytes / 4,422 quoted value bytes; already inside certificate cap |
| Native signatures | At most ten: 1,320 content bytes, already inside native array cap |
| Legacy signatures | Raw 64-byte ECDSA, canonical padded base64 of 88 characters; at most fifteen optional signed records plus unsigned mandatory reward, 1,320 content bytes already inside legacy array |
| Monetary strings / integer strings | <=32 ASCII decimal bytes / <=16 ASCII digit bytes respectively, with six-fractional-digit monetary precision and field ranges; precision alone never bounds magnitude |
| Signing nonces / evidence times | 1..256 allowed ASCII bytes / <=32 canonical UTC ASCII bytes |
| Native memo / signed message | <=280 scalars and 1,120 raw UTF-8 bytes / <=4,096 raw UTF-8 bytes; repeated escaped copies count |
| Parsing | Depth <=32 including portable record/envelope; duplicate and unknown keys, invalid Unicode, coercion and noncanonical standalone bytes reject |
| Finality | Zero bytes in R; separate proposed <=128 validators, <=1,536-byte attestations and <=262,144-byte complete proof |

Nested caps are subsets of their parents, not extra overhead allowances. No
in-record finality proof or extra producer signature is specified. An original
media size cap alone cannot guarantee an admissible submission will fit:
mandatory identity-record reservation with the exact frozen evidence and
worst-width future header/reward values is still required before certification.

## Canonical representation and commitments to retain

The approved *specified*, not implemented, structure is:

```text
H = lowercase_hex(SHA-256(M))
B = {"domain":"zoidbergchain/block/v2", "network_id":N,
     "object_type":"block", "payload":P,
     "protocol":"zoidbergchain", "protocol_version":2}
h = lowercase_hex(SHA-256(J(B)))
R = J({"envelope":B,"hash":h})
```

`P` has exactly the required fields inventoried above and conditionally the
nonempty image caption. Its `media` is the eight-key encoding-version-1 object.
Text has no separate caption/raw-text copy. No old media aliases or `meme`
compatibility object enter P. N must ultimately be the frozen launch ID.

`J` sorts keys lexicographically by Unicode scalar value, preserves array order
and scalar text without normalization, emits compact UTF-8 with no BOM/newline,
and uses the specified JSON escaping. Integers exclude booleans/floats and obey
safe-integer and field-specific ranges. Decimal values are explicit strings.
Duplicate keys, invalid UTF-8/surrogates, unknown keys and noncanonical standalone
serialization reject. Required metadata has no defaults.

The eight descriptor fields are authenticated by `J(B)`, including exact strict
padded base64 E, codec/profile, MIME, original hash, and both sizes. Changing E
or metadata changes the preimage (or makes the record invalid). H hashes only
accepted original bytes, excluding MIME and all encoding metadata; different
valid encodings of identical M retain H. Validators never recompress to compute
identity. The portable `hash` field is outside its own preimage, the certificate
digest excludes its own digest field, and finality signs the resulting block
identity separately. No circular producer signature is introduced.

The native aggregate retains a distinct existing preimage: ordered exact native
records serialized with sorted keys, compact separators, **ensure_ascii=True**,
then SHA-256. It must not silently use unescaped-Unicode J instead. Empty array
SHA-256 is `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945`.
The original SHA-256 of accepted text `hello` is
`2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824`.
Both hashes were checked with Python hashlib and independently with .NET SHA256.
They are reference checks, not new complete v3 block golden vectors.

## Codec boundary and security gates

No codec integration was implemented after the Step 2 stop. The future isolated
adapter must use only identity/1 and zstd/1. The existing benchmark producer
profile is Zstd level 3, window_log 18, checksum/content size enabled, no
dictionary and one thread. Compare complete canonical candidate records against
identity and retain compression only when smaller; encoded payload size alone
is insufficient. This preference must not reject a valid but larger zstd record.

Use `codec_prototype/isolated_decoder.py:IsolatedDecoder` as the existing offline
worker boundary for controlled experiments, not direct native decompression in
the parent. Its outcomes are `VALID`, `INVALID`, and
`INDETERMINATE_LOCAL_FAILURE`. The future adapter must verify descriptor types,
strict base64/pad bits/count, MIME-specific original cap, exact reconstruction,
size/SHA-256 and admission MIME/evidence bindings. A codec-layer `VALID` result
does not by itself certify MIME/container safety or accept a block. The current
prototype's generic 2 MiB original limit does not enforce the future 256 KiB text
cap on behalf of a format layer.

Timeout, OOM, crash, cancellation, saturation, missing platform controls and
cleanup uncertainty remain local failures with no usable media result or vote;
they are never converted into protocol invalidity. Validators must never
recompress, accept verified prefixes, or substitute identity after decode failure.

Existing activation gates remain: independent decoder/sequence-verifier review,
complete native work/state/stack/error-path bounds, independent implementation
and supported platform agreement, audited worker filesystem/network/credential
confinement, parent-death/cleanup and aggregate resource controls, and the
separately documented image-admission worker failure. Those are not asserted to
prevent all inert local format tests; the unresolved format choices above are
the reason production format work stopped here.

## Verification and reproducibility

Focused existing checks ran on the project environment without changing fixture
bytes or generating expected results from a new implementation:

```powershell
.\.venv\Scripts\python.exe -B -m pytest tests/test_protocol_v1.py tests/test_protocol_v1_golden_vectors.py -q --tb=short -p no:cacheprovider
# 51 passed in 3.45s

.\.venv\Scripts\python.exe -B -m pytest tests/test_milestone_7_task_7_6_decoder.py::test_manifest_and_all_fixture_bytes_are_frozen tests/test_milestone_7_task_7_6_decoder.py::test_versioned_golden_vectors tests/test_milestone_7_task_7_6a_sequences.py::test_v2_fixture_inventory_and_hashes tests/test_milestone_7_task_7_6a_sequences.py::test_sequence_golden_vector -q --tb=short -p no:cacheprovider
# 154 passed in 1.76s
```

The second command verifies the two existing codec fixture inventories/manifests
and replays all 117 v1 plus 35 v2 codec fixtures with the current strict adapter.
These are offline codec-layer checks, not newly approved block/MIME/certificate
vectors or worker production-readiness tests. There are no new Task 7.10 positive
or negative block vectors, complete-record boundary tests, or producer adapter
tests because the required preimage schema remains unresolved.

Reproduce the core capacity and recurring-ratio calculations without creating
certificates or signatures:

```powershell
@'
import base64
from decimal import Decimal, localcontext
from admission_certificate import AdmissionMintCertificateView
from block import _normalize_decimal_string, Block
b = 2_097_152
l = 4 * ((b + 2) // 3)
assert len(base64.b64encode(bytes(b))) == l == 2_796_204
assert l + 196_608 + 98_304 + 32_768 == 3_123_884
assert 3_145_728 - (l + 327_680) == 21_844
view = AdmissionMintCertificateView({'originality': {
    'positive_votes': 5, 'approval_denominator': 7}})
print(_normalize_decimal_string(view.approval_percentage,
                                field_name='approval_percentage'))
with localcontext() as ctx:
    ctx.prec = 28
    print(format(Decimal(5) / Decimal(7), 'f'))
assert Block._normalize_protocol_v1_value(
    {'memo': None}, field_name='native_transactions[0]') == {}
assert Block._normalize_protocol_v1_value(
    {'extra': 'x' * 32769}, field_name='native_transactions[0]')['extra'] == 'x' * 32769
'@ | .\.venv\Scripts\python.exe -B -
```

The accounting formula and per-field table above reproduce the conservative
3,115,183-byte top-level ceiling without constructing placeholder certificates.
Documentation checks passed for UTF-8/final newline, local relative links,
trailing whitespace, fenced blocks, the complete top-level field inventory,
`git diff --check`, and `git diff --no-index --check -- NUL
docs/milestone-7-v3-block-format-implementation.md` for the untracked file.
The full repository suite and image-admission integration tests were not
run; no v3 interoperability or complete-block acceptance is claimed.

## Later integration boundaries — none performed here

| Boundary | Required later connection |
| --- | --- |
| Submission/admission | Validate original M, freeze closed new-context evidence/caption, reserve complete mandatory identity bytes before certification; recheck if evidence changes |
| Block production | Build bounded immutable P, choose and verify exact E, compare whole records, pack optional transactions within every child/parent budget, then preserve R |
| Consensus validation | One strict parser/hash/size path at every entry point; isolated decode, exact M/H/MIME/evidence and signed ledger/reward/ancestry checks; withhold action on local failure |
| Voting/finality | Fresh context signatures on height/hash/network, separate bounded proofs, unchanged quorum semantics, no rewriting R at finalization |
| SQLite | Immutable authoritative R BLOB plus derived indexes and separate mutable state; atomic media/submission/certificate/reward claims and reorg handling; separate later schema work |
| Peer synchronization | Preserve E/R, negotiate frozen context, bounded incremental pages by both count and response bytes, verify links/ancestry and decode through the common boundary |
| Export/import | Preserve exact canonical history, launch identity and required separate proofs; bounded parsing/archive expansion, staged full verification and atomic restore |
| API retrieval | Serve only fully verified M with original MIME/length/H/block identity; explicit encoded/summary views; no partial or unverified response on local failure |
| Reset/genesis | Separately authorized fresh network/genesis/policy/registry and state disposition; archive supported old history, collect fresh signatures and explicitly activate only after gates close |

Current v1/v2 production, hashing, active network, database schema and policy
remain unchanged because no runtime source changed. Historical serialization
and golden controls passed as reported; this does not claim that the active
admission integration suite or a new v3 history path was exercised.

Only this blocker/budget report is ready for review. **Task 7.10 is not complete
or ready for an implementation commit.** Resolve the native field/null registry,
exact decimal adapter, closed evidence/signing context and their reviewed
vectors before resuming the requested isolated implementation. No next task,
deployment, migration, reset, or production activation is begun.
