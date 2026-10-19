# Milestone 7 Task 7.10A — Canonical v3 Schema Decisions

Date: 2026-10-19 (America/New_York).

**Status: partially resolved; full Task 7.10 resumption is BLOCKED.** This is a
documentation and focused-verification task. Native projection, null handling,
closed admission evidence, exact rational summaries and commitment rules are
specified below. The user explicitly selected rational summary objects during
Task 7.10A; this amends the two decimal summary slots in Task 7.2 for the new
protocol only. Treatment of undomained legacy transfer signatures still needs
an explicit decision. No production
format, consensus adapter, migration, activation, reset, or deployment is added.

The [Task 7.10 report](milestone-7-v3-block-format-implementation.md) remains the
historical stop record. This decision refines its findings rather than changing
historical bytes. The [compression protocol](milestone-7-compression-protocol.md),
[security contract](milestone-7-codec-security-contract.md), and
[capacity decision](milestone-7-v3-storage-and-capacity-decision.md) remain the
architecture: MODEL A; protocol 2 / block 3 / encoding 1; identity/1 and zstd/1;
SHA-256 of accepted original bytes as media identity; encoded media and metadata
authenticated by the block commitment; no validator recompression.

## 1. Repository and authority

| Check | Result |
| --- | --- |
| Branch | `Compression-State-Bloat-and-Node-Economics` |
| HEAD | `4f16cd399fbfba1cdce3b9e8645554fba71fe447` |
| Separate Task 7.10 commit | HEAD, `Milestone 7 Task 7.10: document canonical serialization blockers` |
| Relevant previous commits | `824afdb` Task 7.9; `c8d9172` Task 7.8; `e5a3a77` Task 7.7 |
| Initial worktree | Clean |
| Applicable AGENTS.md | None found in repository or ancestors in this conversation; no repository copy found on recheck |
| Scope of changes | This new decision and a short current-status pointer in the Task 7.10 report |

These are specifications for an inert new format, not amendments to the active
v1/v2 blockchain. Task 7.9's proposed bounds are used together as validity
predicates for the design calculation; their launch approval and policy digest
freeze remain separate. New accepted bytes must never be normalized on receipt
or made valid by dropping unknown fields.

The important additional source finding is
`services/native_ledger_service.py:serialize_native_transaction_for_block`.
Unlike the broad `Block` dictionary normalizer examined in Task 7.10, this
function already selects the immutable native record. Its field set, together
with `protocol_v1_native_transfer.py`, resolves the projection without inventing
new transfer semantics. The stricter v3 parser still needs to enforce that set
and retain its explicit memo null.

## 2. Canonical primitives and context

Use `J(x)` for Task 7.2's compact UTF-8 canonical JSON, without BOM or trailing
newline. Keys sort lexicographically by Unicode scalar value; arrays preserve
their specified order. Schema keys are ASCII. Strings preserve scalar values,
including combining sequences; no NFC/NFKC, case folding, trimming or implicit
type conversion occurs during verification. Quotes/backslashes and C0 controls
use exactly Task 7.2's escapes; `/`, U+2028 and U+2029 are emitted directly.

Use `A(x)` only for the existing native aggregate: compact JSON with sorted keys
and **ASCII escaping**, including lowercase `\uXXXX` and surrogate pairs for
non-BMP scalars. `A` and `J` are intentionally different. No generic null-dropping
or tagged-binary transform is part of either function on these schema objects.

| Name | Exact type / rule |
| --- | --- |
| `N` | Frozen launch network ID, 3..64 ASCII characters, `[a-z0-9][a-z0-9-]{2,63}`, matched over the entire string; never default to the old network |
| `W` | Frozen application network name, 3..64 ASCII characters, `[A-Za-z0-9][A-Za-z0-9_.-]{2,63}` from `validators.py`; one value bound alongside N, not a caller-selected alias |
| `H64` / `ID32` | Exactly 64 / 32 lowercase ASCII hex characters |
| `Wallet` | Exactly `0x` + 40 lowercase hex characters, existing cryptographic wallet identity; exactly 42 bytes |
| `PublicKey` | Exactly 66 lowercase hex characters representing a valid compressed secp256k1 key under the existing miner/legacy validator |
| `UInt` | JSON integer, actual integer type excluding bool, 0..9,007,199,254,740,991; stricter field ranges below |
| `NonceInt` | ASCII decimal **string**, 1..9,007,199,254,740,991, no sign/leading zeros, 1..16 bytes |
| `OpaqueNonce` | String of 1..256 ASCII bytes from `[A-Za-z0-9_-]` |
| `TimeUTC` | Valid Gregorian date/time `YYYY-MM-DDTHH:MM:SS[.fraction]+00:00`, four-digit year 0001..9999, seconds 00..59, 1..6 fractional digits if present, <=32 ASCII bytes; zero fraction omitted, trailing fractional zeros removed |
| `Money` | Canonical nonnegative finite decimal string, <=32 ASCII bytes, <=6 fractional digits; see section 5 |
| `Sig65` | Exactly 65 decoded bytes in lowercase `0x` + 130 hex characters; r and s each 1..secp256k1 order-1, recovery byte exactly 27 or 28; full personal-sign recovery and signer checks remain mandatory |

The TimeUTC producer adapter first converts the instant to UTC, then renders
integer calendar/microsecond components. `Z`, offsets other than `+00:00`, zero
fractions, and redundant fractional zeros are noncanonical wire spellings.
This tightens today's `datetime.isoformat()` spelling but changes no instant.
No rounded time is accepted. A timestamp that cannot be represented in this
grammar is rejected before signing.

N and W are distinct existing concepts, not two independently negotiable chain
identities. Both must be fixed by the launch context; native records must match
both, while the signed envelope binds N. The examples use the same explicit
test value for both. A production launch value is not selected here.

All registered policy identifiers and statement text are fixed constants, never
user-defined strings. For concrete width accounting, the new media policy ID is
`N + "/media-admission/2"` (<=82 ASCII bytes); media policy version is 2. Review
policy version is 2 because bounded snapshots change that policy; its digest
binds N, the existing decision rules and new limits. Do not reinterpret either
old version-1 policy dictionary or its digest. Reviewer-policy and reputation
rule semantics remain the existing version-1 / version-2 rules respectively;
the new registry must bind those exact rule semantics and network context.
Changing their substance requires separately versioned policy review.

## 3. Native transaction decision

### 3.1 Exact record T — all 17 fields required, no optional fields

| Field | Type, bound and validation |
| --- | --- |
| `tx_id` | H64, recomputed as specified below |
| `transaction_type` | Exact `native_transfer` |
| `network` | Exact W, <=64 bytes |
| `transaction_version` | Integer exactly 2 |
| `protocol_version` | Integer exactly 2 |
| `network_id` | Exact N, <=64 bytes |
| `from_address`, `to_address` | Wallet; distinct; sender must match recovered signer |
| `amount` | Money, strictly positive, bounded by the launch supply and available balance |
| `fee` | Money, exactly `"0"` under the current fee policy |
| `nonce` | NonceInt; contiguous expected sender nonce in candidate ancestry |
| `timestamp` | TimeUTC, retained as signed transfer data; no local creation/receipt clock substituted |
| `memo` | Required **null or string**; null means no memo. String is nonempty, <=280 Unicode scalars and <=1,120 UTF-8 bytes, already trimmed under the frozen set below |
| `signature` | Sig65, full EIP-191 recovery/verification required |
| `signature_scheme` | Exact `personal_sign` |
| `signed_message` | String <=4,096 raw UTF-8 bytes, exactly UTF-8 decoding of the canonical envelope M below |
| `signed_message_hash` | H64, exactly SHA-256(M); also equals `tx_id` under existing native identity semantics |

This is the field set selected by the existing block-specific projection,
requiring its three version/network fields for the new protocol. It keeps
signature, canonical signing message, nonce, fee, timestamp and all transfer
identity data. It does **not** copy `NativeTransaction.to_dict()` wholesale.

Forbidden local/lifecycle fields are `status`, `created_at`, `updated_at`,
`admitted_at`, `included_block_hash`, `included_block_height`, `settled_at`,
`rejection_reason`, transfer-intent IDs, delivery errors, mempool arrival order
and local nonce reservations. They are not inputs to native transaction identity
or signed balance/nonce transitions. Their local reconstruction must use the
verified immutable transaction and canonical ancestry. In particular, the
included block hash is learned after block hashing and cannot occur in T.

For memo construction, freeze the current Python 3.13 whitespace set rather
than invoking an evolving Unicode classification: U+0009..000D, U+001C..001F,
U+0020, U+0085, U+00A0, U+1680, U+2000..200A, U+2028, U+2029, U+202F, U+205F,
U+3000. A pre-sign UI adapter strips only these edge scalars and maps an empty
result to null. Wire validators require the result already canonical. Interior
scalars remain exact; unsupported Unicode/surrogates reject. No text
normalization is applied. This preserves today's memo normalization while
making its platform-independent meaning explicit.

### 3.2 Native signed payload, message and ID

The closed payload U has exactly eight required keys:

```text
{amount, fee, from_address, memo, nonce, timestamp, to_address, transaction_version}
```

Each value equals the corresponding T value, including explicit null memo.
Define the exact six-key envelope and bytes:

```text
E_native = {"domain":"zoidbergchain/native-transfer/v2", "network_id":N,
            "object_type":"native-transfer", "payload":U,
            "protocol":"zoidbergchain", "protocol_version":2}
M = J(E_native)
T.signed_message = UTF8_decode(M)
T.tx_id = T.signed_message_hash = lowercase_hex(SHA-256(M))
```

This retains `calculate_protocol_v1_transaction_id`'s existing *meaning* under
the explicitly required new protocol domain: transaction identity excludes the
signature and mutable metadata. The signature authenticates M, not the text of
its SHA-256 hex ID. Neither `tx_id` nor signature occurs inside U, avoiding
self-reference. A second signature for identical U has the same transaction ID;
it does not create a second spend or nonce.

### 3.3 Lifecycle, ordering, duplicates and limits

Trace at HEAD: API/message construction -> `build_native_transaction` ->
`NativeTransactionValidationService.validate_identity` ->
`validate_admission_state` and durable mempool admission -> existing block
projection -> `validate_block_step` and block-order check -> settlement and
reconciliation in `NativeLedgerService`. Finality/reorg determines which history
and settlement remain authoritative; it does not mutate immutable T.

Retain current sender balance debits `amount + fee`, recipient credit `amount`,
fee-zero rule, and contiguous sender nonce starting at one. Sort included T by
`(from_address, integer(nonce), tx_id)` as the existing block sorter does.
Validators reject a differently ordered list rather than sorting it into a
different preimage. The local mempool may select candidates by admission time;
arrival time is not consensus data. Check balances/nonces in the resulting block
order against the predecessor state, preserving existing reward/transfer order.

Reject duplicate transaction IDs within a block and previously settled IDs on
the candidate ancestry. Reject duplicate `(from_address, nonce)`, stale/gapped
nonces, bad signatures, same sender/recipient, nonzero fee, and insufficient
balance. Preserve current mempool behavior: identical immutable replay is
idempotent; the same tx_id with conflicting immutable signed data is a conflict.
Do not silently deduplicate received arrays. Fork-local ID/nonce claims are
reconciled with canonical history and finalized anchors.

Each `len(J(T)) <= 8,192`, count <=10, and `len(J(list_T)) <=98,304` all apply.
The count/record maxima give the tighter array bound
`10*8192 + 9 + 2 = 81,931` bytes. These are **serialized** limits: memo/message
escaping and repeated message copies count. A local upload/mempool limit is not
an alternate consensus limit. No transaction truncation is permitted.

## 4. Missing, null, empty, zero and Unicode rules

| Input | Canonical rule |
| --- | --- |
| Missing required key | Reject, including a missing memo; never default fee, version, collection or metadata |
| Optional absence | Only explicitly enumerated optionals: image `meme_text`; legacy signature only if a future resolved legacy rule permits it. Absent is the sole no-caption representation |
| Explicit null | Only native memo and the four text technical-evidence dimension/frame/pixel fields listed below; every other field here forbids null |
| Empty string | Reject for all required strings and optional caption/memo; no null/empty/absent aliases on wire |
| Empty array | `native_transactions=[]` is valid; `voter_rewards=[]` is required. Other arrays obey their own minima: a qualifying certificate cannot have zero votes, and a reward-bearing block cannot have no reward transaction |
| Empty object | Not a valid transaction, descriptor, tally, attestation, certificate or finality proof; `{}` is only a JSON-level negative example |
| Zero | Integer `0` valid only in a field whose range permits it; `approved_at=0` required. Fee is the string `"0"`; amount cannot be zero |
| False | Actual bool only in enumerated tally boolean slots; required true reviewer eligibility cannot be false. Neither bool can satisfy an integer slot |
| Unknown field | Reject at every depth; no extension dictionaries or blacklist projection |
| Duplicate JSON key | Reject while parsing, before object construction can discard it; applies in signed-message strings when separately parsing those envelopes |
| Invalid UTF-8/BOM/surrogate | Reject; no replacement decoding, lone surrogate escapes, alternate encodings, or BOM |
| Unicode equivalents | Preserve exact scalars. `é` and `e` + combining acute are distinct contents; escaped `\u00e9` is not an alternate canonical J spelling of `é` |
| JSON number alternatives | Reject floats, exponent notation, `-0`, plus/leading zeros and out-of-range integers; decimal fields are strings |

Standalone records must equal their reserialization with J. A is an internally
computed native hash preimage, not an alternate accepted wire spelling.
Formatted outer transport may reconstruct J only after
strict duplicate/type/schema checks. Do not run the old `Block` null-dropping
normalizer, `str(value)`, `int(value)`, `.lower()` or `.strip()` to repair received
consensus objects. Pre-sign application adapters may canonicalize explicitly;
the resulting signed object is immutable.

Compatibility consequence: old block dictionaries can drop memo null even though
the signing payload includes it. New native records preserve it in both places,
changing new-protocol aggregate/block bytes deliberately. Historical v1/v2
parsing and hash rules stay exactly as they were.

## 5. Numeric decisions and exact rational summaries

### 5.1 Financial, time and integer domains

Use arbitrary-precision integer coefficients for financial values in millionths
of ZOID; native amounts have <=6 fractional decimal places, exactly as the
existing parser requires. Arithmetic on those coefficients is exact. No rounding
is permitted to turn an overprecision amount into a valid one. Existing supply,
reward, fee-zero and balance rules still bound values; today's constants are
1,000,000,000 total supply, 100,000,000 reward pool and creator reward 5. This
decision does not change those values or introduce voter/compression rewards.

The wire grammar for Money is `0` or `[1-9][0-9]*`, optionally followed by
`.` and one to six digits ending in a nonzero digit; no sign, exponent or leading
zeros, <=32 bytes overall. Require field-specific positivity/zero and launch
supply checks in addition to this lexical maximum. The lexical maximum alone is
less than 10^32 ZOID and less than 10^38 millionth-units; the current supply is a
much tighter economic bound. Never use host integer overflow or a Decimal
context to decide validity.

Pre-sign conversions: an actual integer is exact; bool is rejected. A finite
Decimal is read through its exact sign/coefficient/exponent, checking its input
precision before normalization as today's amount parser does. Strip redundant
decimal zeros using integer/string operations, not context-sensitive
`Decimal.normalize()`. Negative zero can normalize to `"0"` only at this
pre-sign boundary where zero is legal. Float is rejected, including integral
float `5.0`; the v3 producer must obtain reward `5` from the integer rule, not
from an old float-bearing block object. Wire `"-0"` and `"1.0"` always reject.

Examples: UI `Decimal("1.200000")` -> `"1.2"`; exact integer 5 -> `"5"`;
`"0.000001"` is a valid positive amount; `"0"` valid fee. Reject amount zero,
`"01"`, `"+1"`, `"1e0"`, numeric JSON `1.2`, float input, `"NaN"`, `"Infinity"`,
over-32-byte strings, insufficient balance, and more than six input fractional
digits (including `Decimal("1.0000000")`, as in the existing parser).

Block `timestamp`/`minted_at` are nonnegative canonical decimal strings of seconds,
<=6 fractional digits, integer part <=UInt maximum, <=32 ASCII bytes; construct
from integer microseconds without rounding a float. `approved_at` remains integer
zero. Existing time-validation meaning must be retained by later adapters.
`payload_size_kb`, legacy amount/tip strings and reward amounts obey the retained
decimal grammar/field budgets, but legacy signed transfer verification remains
blocked as explained in section 8. No local receipt/settlement time enters P.

### 5.2 Tally and reputation authority

The authoritative review quantities are integers: positive p, negative q,
unsure u, total t=p+q+u <=16 per dimension, established e<=t, and decisive
d=p+q. Preserve `t>=5`, `e>=1`, `d>0`, and `p*10000 >= d*7000` for approval.
Unsure votes count toward quorum and participation, not d. Preserve equal vote
weight, historical reviewer status, epoch/activity/rate-limit/cooldown/suspension
rules. `dual_review.tally` contains integer counts and boolean outcomes;
`milestone5_policy.py`, `reviewer_reputation.py`, and
`services/reviewer_eligibility_service.py` use integer rules/statuses, not a new
decimal reputation score. Offense history stays separately validated; no float
score or analytics probability is added to a certificate.

Potential conversion sites inspected: `AdmissionMintCertificateView` computes
`approval_percentage=p/d` as a float and aliases `originality_score` to it;
`block.py` converts float/Decimal through `Decimal(str(value))`; legacy rewards,
tips, amount and `payload_size_kb` can arrive as floats; production reward/time
paths use floats; `RewardService` uses Decimal normalization and millionth-unit
conversion with implicit context rounding. The old dynamic threshold/weighted
originality configuration is not the dual-review integer decision rule. V3 must
not accidentally import those legacy score calculations or inactive voter
reward planning into the frozen admission certificate path.

### 5.3 RESOLVED: exact rational objects, no canonical decimal percentages

The user selected integer numerator/denominator objects, reduced by GCD. This
explicitly supersedes the decimal-string type of **only** P.approval_percentage
and P.originality_score in Task 7.2 section 4.2 and their Task 7.9 decimal budget
rows. Monetary and timestamp fields keep their specified decimal-string types.
No production consumer changes in this task.

Each summary is a closed object with exactly two required keys:

```text
{"denominator":d_reduced,"numerator":n_reduced}
```

Both values are actual JSON integers, excluding bool, float, string and null.
They represent a fraction in [0,1], not a percentage in [0,100]. Let p be the
originality tally's positive count and d its approval_denominator. If d>0,
g=gcd(p,d), n_reduced=p/g and d_reduced=d/g, with integer division only.
Require d_reduced>0, n_reduced>=0, n_reduced<=d_reduced and gcd=1. Zero is
**exactly 0/1** and one exactly 1/1. Received 2/6, 0/5 and 16/16 reject as
noncanonical rather than being silently reduced. Constructor reduction occurs
before signing/hashing; validators require the supplied reduced value already
to equal the integer tally derivation.

Authoritative p and d each range 0..16. For defined summaries d is 1..16;
reduced denominator is 1..16 and reduced numerator is **0..15** (the only way
to have raw p=16 with p<=d<=16 is 16/16, which reduces to 1/1). These tight
bounds, gcd=1 and n<=d all apply. Maximum canonical value size is 33 bytes,
attained by e.g. `{"denominator":16,"numerator":15}`; canonical key order is
denominator then numerator. There is no rounding, scale, exponent, negative
zero or decimal normalization in this representation.

Both block fields must contain the **same** normalized originality ratio,
preserving `AdmissionMintCertificateView.originality_score`'s current alias to
approval_percentage. The second field is not reinterpreted as the admissibility
ratio or the legacy weighted originality score. Admissibility still derives its
own integer approval decision from its own votes; no new ratio key is inserted
in its closed 14-field tally.

### 5.4 Undefined and zero-vote cases

| Underlying counts | Ratio / existing voting result |
| --- | --- |
| t=0, p=q=u=0, d=0 | Undefined: no rational summary is constructed; quorum=false, resolved=false, outcome=unresolved |
| t>=5, established>=1, all votes unsure, d=0 | Undefined even though quorum may be true; resolved=false, outcome=unresolved |
| p=0, d>0 | Defined canonical 0/1; quorum/status still checked independently. If quorum is satisfied this is a negative outcome, not an approved certificate |
| p>0, d>0 | Defined reduced p/d; normal quorum and integer threshold apply |

Undefined is an application/control result such as `UNDEFINED_NO_DECISIVE_VOTES`,
not a new canonical value. Never encode 0/0, null, an absent required summary,
NaN, or a fabricated 0/1 in a complete block to represent no decisive votes.
A qualifying admission certificate requires both dimensions resolved positively
and d>0, so a complete v3 block with no defined summary is invalid because its
certificate does not qualify. Interim tally objects may represent unresolved
counts exactly as today, without either top-level block summary. Presentation
can display "no decisive votes" outside canonical hashing. This preserves the
existing all-unsure and zero-vote behavior without relying on the legacy UI's
float-zero placeholder or triggering the old view's division by zero.
The separately discriminated genesis schema is not a media admission block and
does not fabricate a ratio or voting event to satisfy these non-genesis fields.

### 5.5 Integer comparisons and presentation boundary

Compare two defined ratios n1/d1 and n2/d2 by comparing n1*d2 and n2*d1.
For threshold 7000/10000, retain the existing authoritative test
p*10000 >= d*7000, with quorum and d>0 checked separately. In particular,
5/7 passes 70% because 50>=49, while 1/3 does not because 10<21. Equality is
exact; no float, Decimal context, epsilon, `math.isclose`, decimal display
rounding or percent string can decide consensus. Per-block cross-products are
small bounded integers; use exact integer arithmetic on every platform.

Human-readable decimals/percentages are presentation views derived from the
ratio, e.g. 5/7 may display as 71.43%. Display precision is not protocol data.
Those display values never replace or accompany the two canonical fields in P;
if returned by an API, they must be explicitly separated from its authoritative
record and cannot be accepted as consensus input.

### 5.6 Existing consumers and required later compatibility work

Targeted full-repository searches for both field names, plus the cumulative
score and their metadata/formatter callers, found the following runtime paths.
This is an adaptation inventory, not code changes or an automatic follow-on task.

| Existing consumer / producer | Required new-protocol compatibility change |
| --- | --- |
| `admission_certificate.py:AdmissionMintCertificateView` | New versioned view derives two reduced objects from integer tally counts; do not divide in Python or modify the old view for history |
| `blockchain.py:certificate_block_metadata`, `services/block_production_service.py` metadata handoff | Carry exact objects into new P, without float conversion; both fields bind the same originality tally |
| `block.py` constructor, from_dict, to_dict and consensus payload builders | Separate strict v3 object parser/serializer; retain every historical scalar/null-dropping rule only in the historical reader |
| `services/block_validation_service.py:validate_admission_block` expected-summary bindings and required-field checks | Validate exact keys/types/bounds/gcd and equality with recomputed ratios, not equality with a float-bearing view |
| `originality_certificate.py` dataclass, score calculation, issuance/validation/serialization | Legacy weighted-score and float certificate formats are a different authority/version; do not reinterpret their fields as the new ratio objects or transplant their digests |
| `protocol_v1_originality.py` canonical certificate payloads and score normalization | Preserve v1 decimal preimages; new code must not pass rational objects into its decimal string normalizer |
| `services/submission_originality_service.py:get_submission_votes`, `blockchain.py` legacy threshold/decision evaluation | Keep legacy display compatibility separate; new admission decisions use dual-review integer counters and cross-products, with explicit undefined d=0 handling |
| `services/reward_service.py` legacy rejection/approval threshold and score-derived decisions | Never use display floats to award/reject under the new protocol; retain fee/reward/voter-reward semantics and old history behavior |
| `services/mint_queue_service.py` queue enrichment | Expose versioned rational data or an explicit display view; do not feed formatted decimal score back into a candidate |
| `services/fork_choice_service.py`, `blockchain.py` cumulative-score facade | New-protocol score accumulation/comparison must use exact integers/rationals; old float sum and `round(...,8)` cannot consume objects |
| `services/peer_chain_sync_service.py` summary parsing, preliminary comparison, candidate scoring | Replace v2-context float casts/8-place rounding with versioned exact summary handling; peer hints do not replace recomputation from verified blocks |
| `peer_sync.py` certificate/block normalization, binding checks and local-score comparison | Add distinct new-context schema handling; never coerce a rational object with float, accept historical scalar certificates as v3 evidence, or use old isclose checks |
| `api_runtime.py:PeerCertificatePayload`, `PeerBlockPayload`, public certificate/submission lifecycle views and duplicate operations endpoints | Current float-typed request fields reject objects; use a new explicit versioned contract, authoritative record plus clearly derived display data, without changing historical endpoints implicitly |
| `api_routers/operations.py` chain summary, `api_routers/content.py` approval logs | Report exact summary types where consumed by peers, display/log decimals only as views; log formatting must not become hash input |
| `storage_tools.py` cumulative score metadata, export/import summaries | Current float(score) fails on objects; preserve canonical R and version exact metadata, or keep purely display metadata explicitly non-authoritative |
| `zoidbergcoin-ui/src/pages/Blockchain.vue`, `Dashboard.vue`: formatPercent, formatScore, block/certificate and cumulative-score displays | Current numeric coercion must become version-aware; derive a display percentage from n/d, handle undefined views explicitly, and never serialize the display back into canonical fields |

`storage.py`, storage migrations, reorg, peer/API block pass-through and restore
paths carry whole records indirectly rather than calculating these fields;
later integration must route them through the same new strict parser and retain
exact objects/bytes. Existing historical tests, `protocol_v1_golden_vectors.json`
and Task 7.7 projection scripts/results keep their old scalar values. Add
separate versioned rational fixtures rather than rewriting that evidence.

For an exact cumulative score, all possible per-block denominators divide
LCM(1..16)=720720. A later new-protocol adapter can accumulate integer
`score_units += n*(720720/d)` and compare those integers, preserving score-first,
then height, then existing hash tie-breaking. With UInt-bounded height this has
finite integer magnitude but can exceed JSON's safe-integer bound; the peer
summary wire representation needs a separately bounded versioned form, not the
per-block 0..15 numerator schema. Never add this derived accumulator to P.
Exact comparison can distinguish chains that the old 8-decimal rounding treated
as tied; this compatibility consequence must be explicit in new-network fork
choice/policy vectors before integration. Historical fork choice stays intact.

## 6. Closed evidence schemas

Only these objects occur in v3 admission evidence: accepted technical evidence,
submitter attestation, dimension-bound community votes, the two derived tallies,
and their admission certificate. Finality proofs are separately typed objects
outside R. No OCR dump, arbitrary reason map, unknown nested object, off-chain
URL, local error, or reputation analytics blob is an extension slot.

### 6.1 Accepted technical evidence — exactly 17 required fields

| Fields | Exact type / constraint |
| --- | --- |
| `evidence_version` | Integer 1; retained emitted evidence format |
| `validator_id` | Exact `zoidberg-media-technical-validator/1` |
| `policy_id`, `policy_version`, `policy_digest` | Exact new media-policy ID, integer 2, and H64 registry digest |
| `outcome` | Exact `ACCEPT` |
| `reason_codes` | Exactly `["ACCEPTED_POLICY_METADATA"]` |
| `detected_media_type`, `detected_mime_type` | Matching pair: `plain_utf8_text`/`text/plain`, `jpeg`/`image/jpeg`, `png`/`image/png`, `gif`/`image/gif`, or `webp`/`image/webp` |
| `raw_media_byte_length` | UInt, 1..262,144 text or 1..2,097,152 image; equals media.original_size and length of reconstructed M |
| `raw_media_sha256` | H64, equals media.original_sha256 and SHA-256(M) |
| `raw_media_semantics` | `policy_canonical_utf8_text` for text, `exact_input_bytes` for image |
| `width_pixels`, `height_pixels` | Text: both required null. Image: integers 1..4,096 |
| `frame_count` | Text: required null. Image: integer 1..60, also subject to the frozen animation activation decision |
| `aggregate_decoded_pixels` | Text: required null. Image: integer 1..16,777,216, bound to validated image structure; do not assume varying frames equal width*height*count |
| `evidence_digest` | H64, SHA-256(J(the other 16 fields)) |

Complete J(evidence) <=8,192 bytes. This selects exactly the identity keys emitted
for successful technical validation, instead of reusing the current exclusion
projection as a parser. Forbid its six local observations explicitly:
`declared_mime_type`, `declared_mime_matches`,
`extension_matches_detected_type`, `safe_display_filename`, `staged_byte_length`,
`local_resource_defense_failure`. Every other unlisted key is equally forbidden.

Text M must already equal the existing accepted canonical bytes: strict UTF-8,
CRLF/CR -> LF and edge-strip using the frozen set in section 3.1, nonempty,
and existing control/type restrictions. Received media is checked, never
silently repaired. Hash/digest equality alone is not proof of MIME/container
safety; validators must enforce policy/evidence bindings and approved media
validation without turning local worker failure into consensus invalidity.

### 6.2 Submitter attestation — 14 required record keys

Retain exactly `_ATTESTATION_FIELDS` from `admission_certificate.py`:

```text
attestation_version, statement_id, statement_version, domain,
protocol_version, network_id, signature_scheme, signer_wallet, signature,
nonce, canonical_payload, canonical_payload_digest,
canonical_message, canonical_message_hash
```

The closed `canonical_payload` has exactly the existing 17 keys:

```text
attestation_version, statement_id, statement_version, statement,
wallet_address, submission_id, raw_media_sha256,
policy_id, policy_version, policy_digest,
technical_evidence_version, technical_evidence_digest,
nonce, issued_at, expires_at, network_id
```

Attestation/statement versions remain 1, technical evidence version remains 1;
protocol version is 2 and domain is `zoidbergchain/submitter-attestation/v2`.
Wallets, IDs, hashes, policy fields and nonce use section 2's exact types;
issued/expiry are TimeUTC with expiry later than issue. Outer/inner duplicate
fields must agree and signer_wallet equals creator_wallet. `signature_scheme`
is `personal_sign`, signature is Sig65. No local `verified_at` enters identity.

For byte-exact engineering examples, retain the existing pinned statement ID
`zoidberg-public-testnet-v1/submitter-rights-permanence/1` (56 ASCII bytes) and
statement version 1 with the exact 494-byte ASCII statement literal in
`protocol_v1_submitter_attestation.py:SUBMITTER_ATTESTATION_STATEMENT`. This is an
immutable statement label, not authority to use the old network or domain; the
new envelope and payload N/policy bindings are mandatory. No new legal wording
is invented. Replacing this engineering statement for launch remains the
existing owner decision and requires a new statement identifier/version and
rechecked vectors before signatures are collected.

The submitter signs J of the six-key protocol-v2 `submitter-attestation` domain
envelope whose payload is exactly canonical_payload and whose network_id is N.
`canonical_payload_digest` and `canonical_message_hash` both equal SHA-256 of
those envelope bytes, retaining current helper semantics despite the former's
name. The record's canonical_message must equal those exact UTF-8 bytes decoded
as text. The signed payload binds original H, policy and technical evidence
digest; the latter binds original length and MIME. It does not bind encoding E.
Complete record <=16,384 bytes; message <=8,192 raw UTF-8 bytes. Escaped copies
count toward the record cap.

### 6.3 Community vote — 23 required record keys

Retain exactly `_VOTE_FIELDS` from `admission_certificate.py`:

```text
submission_id, content_hash, voter, voter_wallet_address,
vote_type, dimension, vote_version, protocol_version, network_id,
signature_scheme, vote_signature, vote_message, vote_nonce,
signed_message_hash, vote_issued_at, vote_expires_at, vote_identity,
reviewer_policy_version, reputation_rule_version, reviewer_status,
reviewer_eligible, reviewer_status_effective_height,
reviewer_status_reference_block_hash
```

`voter` and `voter_wallet_address` are identical Wallet values and equal the
recovered signer; neither equals the creator. IDs/hashes use ID32/H64. Dimension
is exactly `admissibility` or `originality`; its vote_type is respectively
`admissible`/`not_admissible`/`unsure` or `original`/`not_original`/`unsure`.
vote_version=3, protocol_version=2, network_id=N, signature_scheme=personal_sign,
vote_signature=Sig65, vote_nonce=OpaqueNonce, issue/expiry=TimeUTC with expiry
after issue. reviewer_policy_version=1 and reputation_rule_version=2 denote the
retained rule semantics bound in the new registry. reviewer_status is exactly
`PROBATIONARY_REVIEWER` or `ESTABLISHED_REVIEWER`, reviewer_eligible is true,
reference height is UInt and reference hash is H64.

The closed signed payload V preserves the actual `dual_review.vote_payload`
fields, with new context and bounded spellings:

```text
domain="zoidbergchain/community-review/v3", network_id=N, vote_version=3,
policy_version=2, policy_digest=<new review-policy digest>,
reviewer_policy_version=1, reputation_rule_version=2,
wallet_address, submission_id, content_hash, dimension, choice,
nonce, issued_at, expires_at
```

This is a **flat** 15-key object, not a generic six-key domain envelope. Do not
add an implicit extra envelope or `protocol_version` key to V; the stored record
still requires protocol_version=2. Duplicate record fields equal V's values;
choice equals vote_type. `vote_message=UTF8_decode(J(V))`,
`signed_message_hash=SHA-256(J(V))`, and
`vote_identity=SHA-256(J({"payload":V,"signature":vote_signature}))`.

Existing eligibility/status references are certificate-authenticated metadata,
not additional fields secretly covered by the reviewer's signature. Validators
must resolve the stated reference height/hash on the candidate ancestry and
check eligibility, historical status, self-vote exclusion, applicable quota and
context under the retained reviewer rules. A producer cannot make an arbitrary
status true by signing or digesting it. Do not add new signed reference fields
without another explicit signed-payload decision.

Each complete vote <=4,096 serialized bytes; vote_message <=2,048 raw UTF-8
bytes. At most 32 votes total and 16 per dimension. Sort records by
`(dimension, voter_wallet_address, vote_identity)` in ascending order (thus
admissibility first). Reject any repeated `(dimension,wallet)`, even byte-identical
duplicates. The frozen snapshot must include its full selected vote set; no
filtering unfavorable votes or rebuilding a favorable subset to fit. The new
bounded snapshot selection/freeze policy must be bound in the review policy
before admission; this document does not invent a live selection algorithm.

### 6.4 Derived tallies — exactly 14 required fields each

```text
dimension, policy_version, policy_digest,
eligible_valid_votes, established_reviewer_votes,
positive_votes, negative_votes, unsure_votes, approval_denominator,
approval_threshold_bps, quorum_reached, resolved, outcome, vote_set_digest
```

policy_version=2 and digest is the new review-policy digest. Dimension and
outcome are the applicable fixed strings; unresolved is allowed only in an
intermediate tally, never in a qualifying certificate. Count fields are actual
integers 0..16; threshold is integer 7000; quorum_reached/resolved are actual
bools. Recompute every field from the frozen dimension's votes and section 5.2.
For each dimension sort by wallet and hash the exact projection:

```text
[{"wallet":wallet,"choice":vote_type,
  "identity":vote_identity,"status":reviewer_status}, ...]
vote_set_digest = SHA-256(J(projection))
```

No ratio float is inside these tallies. Each complete tally <=8,192 bytes.
The two top-level block summaries are the exact rational objects in section 5.3;
they are derived from originality counts and do not add keys to these tallies.

### 6.5 Admission certificate — exactly 18 required keys

```text
certificate_version, network_id, submission_id, content_hash, creator_wallet,
policy_id, policy_version, policy_digest,
technical_evidence_version, technical_evidence,
attestation_version, attestation,
review_policy_version, review_policy_digest,
votes, originality, admissibility, certificate_digest
```

certificate_version=2, network_id=N, media-policy version=2, review-policy
version=2, technical-evidence version=1, attestation version=1. Hashes/IDs/wallets
use the exact primitives above. Every repeated media identity, policy/version,
attestation signer, submission and vote binding must agree across the bundle
and block. Both tallies must qualify using the unchanged integer rules and
match a full recomputation. Digest is lowercase SHA-256 of J of the other 17
fields. There is no implicit extra certificate domain envelope and no new
producer signature; version, N and policy bindings are inside its preimage.
Complete certificate <=196,608 serialized bytes.

Legacy certificates, votes, attestations, technical extensions and missing
versions are rejected by the new parser, not inferred or re-signed. Historical
readers retain their old context/rules. A new submission must collect fresh
new-domain signatures even when the original media H is unchanged.

### 6.6 Validator consensus/finality evidence — outside R

The inspected chain's authenticated consensus votes are its validator finality
attestations. Admission community votes are a different authority. Do not invent
a second block-producer signature or an extra canonical consensus-vote array.

The exact finality record has nine required keys, matching `FinalityService`:
`attestation_version`, `validator_address`, `block_height`, `block_hash`,
`network_id`, `domain`, `signature_scheme`, `signature`, `message`.
For the new domain use attestation_version=2,
domain=`zoidbergchain/finality-attestation/v2`, network_id=N, Wallet, UInt height,
H64 block hash, personal_sign, Sig65, message <=1,024 raw UTF-8 bytes, record
<=1,536 serialized bytes. Its signed payload has exactly attestation_version,
validator_address, block_height, block_hash; sign J of the protocol-v2 six-key
`finality-attestation` envelope. The target must be the exact verified block on
the selected ancestry, and the recovered signer must be a trusted validator.

The separate proof's exact eight keys are `block_height`, `block_hash`,
`network_id`, `domain`, `attestation_version`, `validator_set`, `required_quorum`,
`attestations`. Validators are a sorted unique nonempty Wallet list of <=128;
quorum is integer `(2*n+2)//3`; attestations sort by validator address, at most
one counted per validator, all targeting the same height/hash/context. Retain
the existing exclusion of equivocating validators and reject incomplete,
duplicate or inconsistently ordered proofs. The claimed set must match the
authenticated launch/ancestry set, not become trusted merely because it is
embedded in the proof. Complete proof <=262,144 bytes. Equivocation/offense
history is separate typed state/transport, not an unbounded proof extension or
an in-record R field. Preserve finalized-history detachment protection.

## 7. Signatures and exact dependency graph

For personal_sign, the cryptographic digest is **Keccak-256**, not the SHA-256
message identifier stored in records:

```text
signing_digest = Keccak-256(0x19 || ASCII("Ethereum Signed Message:\n")
                          || ASCII_decimal(len(M)) || M)
```

Length counts UTF-8 bytes, not Unicode characters. Verify the secp256k1
signature/recovery against the expected wallet using the existing personal-sign
scheme. The secp256k1 order is
`fffffffffffffffffffffffffffffffebaaedce6af48a03bbfd25e8cd0364141`.
Sig65 fixes the personal-sign recovery-byte spelling to 27/28, matching the
existing signer output. A pre-freeze application adapter may map recovery byte
0/1 to 27/28 without changing the signed message; wire 0/1 and chain-ID-style
recovery bytes reject. This narrows accepted encoding aliases for the new
version and does not rewrite historical signatures or vote identities. No
low-S restriction is added: existing mathematically valid r/s values still
require successful recovery. Multiple cryptographically valid signatures of
the same message are distinct supplied signatures, not alternate JSON spellings;
ID/nonce and dimension/wallet duplicate rules prevent double counting. Pin
canonical recovery-byte and high-S checks in implementation vectors before security sign-off;
do not silently choose a new signing scheme from a decoder/library exception.

```text
original M -> H, technical body -> evidence_digest
technical digest + H + policy/submission/creator -> submitter message/signature
H + submission + dimension/choice + new review context -> vote signatures/IDs
bounded ordered votes -> integer tallies and vote_set_digest
technical evidence + attestation + ordered votes/tallies -> certificate_digest
U -> native message -> tx_id and signature -> T -> A(ordered_T) -> transactions_hash
descriptor(E,H,metadata) + complete certificate + T + other P -> J(B) -> block h
verified h + height + N + validator -> finality signatures -> separate proof
```

No certificate field includes the future containing block hash. Reviewer status
references identify already available historical blocks. Native T contains no
current inclusion hash. Finality is created after h and is outside R. Original
H is exactly SHA-256(accepted M), with no MIME/domain/size prefix; J(B) commits
exact base64 E and decoding metadata. Different valid encodings preserve H but
change the block commitment. Retained blocks cannot be reencoded or reuse
old-hash finality signatures.

## 8. Additional BLOCKED rule: legacy signed transfers

Task 7.2 carries reward/legacy transaction payloads in `transactions`; Task 7.9
bounds them at 16 records including the mandatory reward, <=1,024 bytes each.
Their proposed closed keys remain `sender`, `recipient`, `amount`, `tip`,
`payload_size_kb`, with signature only for a signed legacy transfer. Reward
sender is `REWARD_POOL`, reward recipient is the creator Wallet, reward amount
is the unchanged rule, tip/payload_size_kb zero, and signature absent. No GENESIS
transaction belongs in a non-genesis media block. Optional signed legacy
records use existing validated PublicKey identities and canonical 64-byte raw
ECDSA signatures in 88-character padded standard base64.

However `transaction.py:sign_transaction` / `is_valid` authenticate only:

```text
UTF8(sender + recipient + str(amount) + str(tip)), ECDSA-SHA1
```

There is no N, protocol domain, nonce or payload_size_kb binding. Two networks
with those same four values give exactly the same preimage. The spelling of
numeric application values (`1.0` versus canonical `"1"`) can also change the
old signature preimage. Reusing that verifier in a fresh protocol would violate
this task's cross-protocol replay requirement; silently domain-enveloping it
would change the existing signature semantics. Merely changing a block domain
does not give its embedded undomained transfer signature replay protection.

| Alternative requiring a decision | Consequence |
| --- | --- |
| Keep only the unsigned mandatory reward in this legacy array; carry user transfers exclusively as the already domain-separated native records | Minimal new cryptographic surface, but explicitly narrows Task 7.2's optional legacy transfer allowance; owner/protocol amendment required |
| Specify a new bounded network/domain-separated legacy transfer signature format and its numeric preimage | Preserves a second transfer path, but needs an explicit version/schema/signing change and test identities/vectors, beyond a silent serialization repair |
| Retain old signature verification unchanged | Does not satisfy the requested replay separation; not accepted by this decision |

No alternative is adopted. The 16-record budget remains a conservative capacity
reservation, not a claim that a complete safe legacy signing contract exists.
No omission of native fee, nonce, signature or other signed fields is proposed
to fix this legacy-path conflict.

## 9. Capacity proof with closed components

Retain the proposed independent bounds: original images <=2,097,152 bytes,
canonical text <=262,144, encoded E <=2,097,152, complete canonical R
<=3,145,728. Size eligibility alone is not admission. Full accepted M remains
reconstructible from on-chain E/descriptor, without external bytes/dictionaries.

For an object with k members of ASCII names n_i and canonical value lengths v_i:
`size = 2 + (k-1) + sum(len(n_i)+3+v_i)`; an empty object is two bytes.
Array size is two brackets + sum of complete value lengths + intervalue commas.
These formulas include every key, quote, colon, delimiter and wrapper. Raw
message byte caps and scalar counts are not substituted for serialized lengths.

| Component | Maximum serialized contribution / accounting |
| --- | ---: |
| Base64 contents at E cap | `4*ceil(2097152/3) = 2,796,204` |
| Descriptor with payload contents subtracted | 231 identity / 227 zstd bytes; `"media":value` member adds eight more bytes |
| Native records | 10*8,192 + 11 = 81,931, inside 98,304 parent budget |
| Vote array | 32*4,096 + 33 = 131,105 |
| Submitter record | 16,384, including signature and repeated escaped message/payload |
| Technical evidence | 8,192 |
| Two tallies | 16,384 combined |
| Complete certificate scalar fields, names, delimiters and digest beyond its five nested values | 836 |
| Derived full certificate bound | **172,901**, inside 196,608 parent cap |
| Reward/legacy array reserved ceiling | 16*1,024 + 17 = 16,401, counted in S_rest; signed legacy semantics remain blocked |
| Optional image caption value | <=6,002 including quotes: 1,000 worst-escaped C0 scalars can fit the separate 4,096 raw-UTF-8-byte cap |
| Header, other scalars, media descriptor, envelope, portable hash wrapper, caption, legacy array and all residual delimiters | S_rest <=32,768; updated top-level width enumeration gives <=24,065 |
| Finality fields in R | **0**; separate proof <=262,144 |

Certificate calculation uses all 18 fields in section 6.5. Its 13 scalar fields
have quoted value widths: version=1, N=66, submission=34, content H=66,
creator=44, policy ID=84, policy version=1, policy digest=66, technical version=1,
attestation version=1, review version=1, review digest=66, certificate digest=66.
The other five values are evidence 8,192, attestation 16,384, votes 131,105 and
two tallies at 8,192 each. Applying the formula yields exactly 172,901. Field
width maxima may be conservative and need not be jointly achievable.

No signatures are fabricated to populate a maximum-sized certificate. Their
actual canonical 132-character content lengths are already inside the relevant
record caps: at most 33 personal signatures in a certificate including submitter,
ten native signatures and fifteen optional legacy signatures in their arrays.
Do not add those subsets twice. Null text dimensions and signatures' quotes
are already included. Repeated signed JSON strings require escaping again and
count toward each enclosing record cap.

Using only the existing disjoint parent budgets, with L the base64 contents:

```text
S_cert   <=196,608
S_native <= 98,304
S_rest   <= 32,768
O = len(R)-L = S_cert+S_native+S_rest <=327,680
len(R) <=2,796,204+327,680 =3,123,884 <3,145,728
margin =21,844
```

Using the closed certificate/count bounds above and the same S_rest cap gives
the tighter conservative ceiling **3,083,804**, leaving **61,924 bytes** under
3 MiB. Independently, retaining the full certificate parent allowance and the
Task 7.10 top-level scalar widths but tightening the native array and replacing
each 34-byte quoted decimal summary ceiling with its 33-byte rational object
ceiling gives **3,098,808**. The residual bound similarly decreases from 24,067
to 24,065. These are different conservative bounds, not claimed measured maximal
valid blocks. The generic 3,123,884 proof remains sufficient after this explicit
summary schema amendment; the new rational values are fully counted. Changing
any schema or limit again requires recounting.

The portable wrapper is exactly 87 bytes beyond J(B), including its 64-character
hash. Max-size identity payload has one base64 padding `=`. Zstd's descriptor is
four bytes shorter than identity but E can expand; producers must compare entire
records, validators verify supplied E without recompression. The 320 KiB budget
is sufficient; **no increase or relaxation of the 3 MiB cap is proposed**.

Every child, collection and parent cap applies together; combinations exceeding
one are not permitted representations. Mandatory frozen evidence must fit an
identity reservation before certification. There is no guarantee every current
unbounded historical certificate or every size-eligible upload can fit. Optional
transactions are omitted/deferred when necessary; never truncate evidence,
votes, signatures, caption or media. A mathematically valid 3 MiB boundary
record is unreachable under the tighter simultaneous caps; tests must account
for earlier sub-budget rejections rather than fabricate a signature to pad it.

Outside R, 128*1,536 +129 =196,737 attestation-array bytes and 128*44+129=5,761
validator-array bytes leave ample room for the eight-key proof scalars/wrapper
inside 262,144. The 16 MiB / 64-record page limits include such separate proofs
and wrappers; no whole-chain response or unbounded offense-history list is
authorized by the per-block proof.

## 10. Byte examples and verification

The examples below are draft vector material for a later resumed Task 7.10,
not new accepted full blocks. JSON lines give exact UTF-8 bytes with no newline.
Their lengths and SHA-256 values were checked with Python and separately with
Node JSON serialization/hash and .NET SHA256; selected decimal/UTF-8 bytes were
also compared to hand-written literals. This is independent example checking,
not independent complete consensus/decoder implementation conformance.

The test network/name is exactly `zoidberg-schema-vector-v2`; it is not a launch
default. The public test key is the already published all-`11` 32-byte key in
`tests/test_protocol_v1_golden_vectors.py`; its wallet is
`0x19e7e376e7c213b7e7e7e46cc70a5dd086daff2a`. No real key is generated,
accessed, rotated or deployed. Only this known disposable identity is used in
the native example. Examples do not establish a funded sender or admit a block.

### Exact small JSON and media preimages

**empty** — Required empty native collection; also the empty native aggregate preimage.

```json
[]
```

UTF-8 length `2`; SHA-256 `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945`.

**null** — Memo field projection with explicit null; not a complete transaction.

```json
{"memo":null}
```

UTF-8 length `13`; SHA-256 `bdae6862019d5e4f237ae5471788cdaf3f90e42c759b24e2b6c5b05deece7b44`.

**absent** — Absent memo projection; valid JSON but invalid as a native transaction.

```json
{}
```

UTF-8 length `2`; SHA-256 `44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a`.

**legacy-decimal-summary-negative** — Old scalar 4/5 summary projection;
valid JSON but invalid for the new v3 rational field types.

```json
{"approval_percentage":"0.8","originality_score":"0.8"}
```

UTF-8 length `55`; SHA-256 `47a4048c0675b1f2cba5903d7c840cfd94c7b7159100ccf8b8250710883521f5`.

**media-identity** — Frozen `identity-1.json`: original accepted text is the one byte `61` (`a`).

```json
{"codec_id":"identity","codec_version":1,"encoding_version":1,"mime_type":"text/plain","original_sha256":"ca978112ca1bbdcafac231b39a23dc4da786eff8147c4e72b9807785afee48bb","original_size":1,"payload":"YQ==","stored_size":1}
```

UTF-8 length `223`; SHA-256 `7ee377e5bb1c7aa281895f2452de3f8c2e628e15140d7eed0c11fc15e08640ea`.

**media-zstd** — Frozen `zstd-single-fcs1.json`: same original byte/hash; 14-byte raw-block Zstd frame, not a producer compression preference.

```json
{"codec_id":"zstd","codec_version":1,"encoding_version":1,"mime_type":"text/plain","original_sha256":"ca978112ca1bbdcafac231b39a23dc4da786eff8147c4e72b9807785afee48bb","original_size":1,"payload":"KLUv/SQBCQAAYVtujKk=","stored_size":14}
```

UTF-8 length `236`; SHA-256 `83f34eb6bedced5e6756b8c19723f8dd29dfc25640e4e70e9fb072ef4e2026ad`.

The Zstd payload decodes from base64 to exact hex `28b52ffd2401090000615b6e8ca9`. No encoder reproduction is required; it is a framing-valid encoding that is larger than identity and therefore a validator-positive / producer-identity-preference example.

### Signed native examples and multiple-transaction aggregate

**native-message-1** (M1):

```json
{"domain":"zoidbergchain/native-transfer/v2","network_id":"zoidberg-schema-vector-v2","object_type":"native-transfer","payload":{"amount":"1","fee":"0","from_address":"0x19e7e376e7c213b7e7e7e46cc70a5dd086daff2a","memo":null,"nonce":"1","timestamp":"2026-10-19T00:00:00+00:00","to_address":"0x2222222222222222222222222222222222222222","transaction_version":2},"protocol":"zoidbergchain","protocol_version":2}
```

UTF-8 length `407`; SHA-256 / tx_id / signed_message_hash `778fa78b8820ebb04506eb895670130ff26716a783ed9da69ae4d6ac6a962ae7`.

EIP-191 Keccak digest `1a7496fba6cf15eadf27280534b234bbc5cf25e5bfde76c230817331c70f6dc1`.

Canonical test signature `0x01d45de7659cde4a4e1b83993ec25b69b80476a21b3d3b2fedbe033bc42eb3ff76faa12245dde3f9631e3a262fdfdeee0f65f9524fd46ba6ca1b3de151c1cbe91c`.

**native-message-2** (M2):

```json
{"domain":"zoidbergchain/native-transfer/v2","network_id":"zoidberg-schema-vector-v2","object_type":"native-transfer","payload":{"amount":"2","fee":"0","from_address":"0x19e7e376e7c213b7e7e7e46cc70a5dd086daff2a","memo":"é","nonce":"2","timestamp":"2026-10-19T00:00:00+00:00","to_address":"0x2222222222222222222222222222222222222222","transaction_version":2},"protocol":"zoidbergchain","protocol_version":2}
```

UTF-8 length `407`; SHA-256 / tx_id / signed_message_hash `73e8025af454c2d052652b5f8a6759a346fcb51353886a96dd8fc9da48e5790f`.

EIP-191 Keccak digest `3fc1a69fb3964ff681fe1d4a3058fcfd3de0963c4de789691c66308e48d78739`.

Canonical test signature `0x2a48c4eb69a23efa6a847d1b7e809cba51d6ce039ce7e99f4d7dd957826a86dc086241135b4a6c68896ffa0c4e6c5f90ad95efd1aea22079a9593963695741331b`.

Construct T1 and T2 with **exactly** section 3.1's 17 keys: copy their corresponding U values, set network=W and network_id=N to the stated test value, both version integers=2, transaction_type=`native_transfer`, signature_scheme=`personal_sign`, tx_id and signed_message_hash to the displayed SHA-256, signed_message to the exact corresponding JSON line above, and signature to its displayed test signature. This recipe uniquely defines every byte of each complete record without an unchecked signature placeholder.

| Preimage | Exact construction | UTF-8 bytes | SHA-256 |
| --- | --- | ---: | --- |
| J(T1) | Defined above; no defaults | 1188 | `66476168629a57b85fe3aa7c7b351d37001f8d050c1c10653cc27836bc8d05c1` |
| J(T2) | Defined above; no defaults | 1190 | `dc36cea183183deaee7973443ede6ed905b33e2a05bb5c5485a140267f57b75d` |
| J([T1,T2]) | Defined above; no defaults | 2381 | `2d601ade4dbf8a6de74deddee828dc506aa59fe20914cc0984ffabf072402f2c` |
| A([T1,T2]) | Defined above; no defaults | 2389 | `4f78636f0d7d531869b52ec85ea1ce089b545c37f714538c3175281b96a35bd2` |
| M1 with domain v1 and both protocol/transaction version integers 1 | Defined above; no defaults | 407 | `19c43e878fb0a47890ed3c46bca468b9d51eb6c4dee80cce0f2a3a9549479d2a` |

The exact A preimage is the J array with each of its two literal `é` scalars (one memo, one embedded signed_message) replaced by ASCII `\u00e9`. The array order is T1 then T2 by sender/nonce. `transactions_hash` MUST be the A hash, not the J hash. M2 is still 407 bytes: replacing four-byte ASCII `null` with the two-quote plus two-UTF-8-byte value `"é"` preserves byte length; it does not preserve character count.

The old-domain example deliberately keeps the same test N to isolate protocol/domain separation. Its old-message hash differs, and M1's signature does not recover the expected signer over those changed bytes. Changing N or the payload likewise invalidates the expected signer binding. This is verification of context binding, not acceptance of a historical transaction on the test network.

### Evidence ordering and certificate context

This is the exact derived tally vote-set projection (not a complete vote array or qualifying certificate). Wallet order fixes the preimage; the displayed identities are explicit projection inputs, not fabricated signature evidence.

```json
[{"choice":"original","identity":"1111111111111111111111111111111111111111111111111111111111111111","status":"ESTABLISHED_REVIEWER","wallet":"0x19e7e376e7c213b7e7e7e46cc70a5dd086daff2a"},{"choice":"original","identity":"2222222222222222222222222222222222222222222222222222222222222222","status":"PROBATIONARY_REVIEWER","wallet":"0x2222222222222222222222222222222222222222"}]
```

UTF-8 length `374`; SHA-256 `4bb6e2c638ed99f7b09b7817e0cc580af2f431768d70c8444955baf47ff40d98`. Reversing the array changes its digest; full record order must additionally group by dimension as specified above.

```json
{"certificate_version":1,"network_id":"zoidberg-schema-vector-v2"}
```

UTF-8 length `66`; SHA-256 `e5beddf8dec7b8175cff3445da34830868ed4ebd74989f15269d652f599a9504`.

```json
{"certificate_version":2,"network_id":"zoidberg-schema-vector-v2"}
```

UTF-8 length `66`; SHA-256 `6e8bbb5aa4d5453ba7ef7b461fd9861b47866f44f44fcdbbe6fbdc7d0daf781d`.

These two **incomplete, invalid certificate projections** demonstrate that the version/network bytes participate in the digest. They are not positive certificate vectors. A full certificate hash is SHA-256(J(the exact complete 17-key body)); no unspecified certificate domain prefix or producer signature may be added. Complete positive certificate/block vectors remain pending the unresolved policy/legacy decisions and must use real test signatures satisfying the entire closed schema.


### Rational summary vectors selected for v3

These are versioned draft rational/count vectors (`task-7.10a-ratio-v1`), checked independently as described below. RATIO_VALID means the ratio schema alone is valid; 1/3 and 0/1 do not imply a qualifying admission outcome. Both zero-decisive-vote cases produce no rational value.

**ratio-five-sevenths** — RATIO_VALID. Ratio-level positive; certificate quorum/outcome is a separate check.

```json
{"denominator":7,"numerator":5}
```

UTF-8 length `31`; SHA-256 `dc8dc4b48ae383b7b5077c7a78b3de8822afc8e16b675d35e9a98accb9b9f678`.

**ratio-one-third** — RATIO_VALID. Ratio-level positive; certificate quorum/outcome is a separate check.

```json
{"denominator":3,"numerator":1}
```

UTF-8 length `31`; SHA-256 `70ddc0b5143b1ded7d3c08f91cb09d9a7fdcb8402cc7c8501c7e53a9b20dffdc`.

**ratio-zero** — RATIO_VALID. Ratio-level positive; certificate quorum/outcome is a separate check.

```json
{"denominator":1,"numerator":0}
```

UTF-8 length `31`; SHA-256 `78b35a451de9a90fdb84ebfdcfdad79e22b58018a910e3bd93607bcf30ec5424`.

**ratio-one** — RATIO_VALID. Ratio-level positive; certificate quorum/outcome is a separate check.

```json
{"denominator":1,"numerator":1}
```

UTF-8 length `31`; SHA-256 `f45adc7eb6dfb04416b26678cb9afb54169e325c6a7e9bbfbf3dd14e621315df`.

**ratio-max-width** — RATIO_VALID. Ratio-level positive; certificate quorum/outcome is a separate check.

```json
{"denominator":16,"numerator":15}
```

UTF-8 length `33`; SHA-256 `9603c10d25ad2e956a69f2212c7f39c959c435ca57da7e9bf5d88d7782219a7c`.

**ratio-both-summary-fields** — SUMMARY_PAIR_VALID. Both summaries equal the original positive/decisive ratio; block/certificate still require full validation.

```json
{"approval_percentage":{"denominator":7,"numerator":5},"originality_score":{"denominator":7,"numerator":5}}
```

UTF-8 length `107`; SHA-256 `8f5cc0a66d097cbed0906a8db9fb297a5b7ad7955a5ab04488c212c2f02a559f`.

**ratio-zero-vote-counts** — UNDEFINED_NO_DECISIVE_VOTES. Positive intermediate count projection, not a ratio object or qualifying block; no summary is produced.

```json
{"approval_denominator":0,"eligible_valid_votes":0,"established_reviewer_votes":0,"negative_votes":0,"outcome":"unresolved","positive_votes":0,"quorum_reached":false,"resolved":false,"unsure_votes":0}
```

UTF-8 length `200`; SHA-256 `092f52af66568cfb5296ae8e6f3e53f94468b0954f307138bf3b156662f0e80d`.

**ratio-all-unsure-counts** — UNDEFINED_NO_DECISIVE_VOTES. Positive intermediate count projection, not a ratio object or qualifying block; no summary is produced.

```json
{"approval_denominator":0,"eligible_valid_votes":5,"established_reviewer_votes":1,"negative_votes":0,"outcome":"unresolved","positive_votes":0,"quorum_reached":true,"resolved":false,"unsure_votes":5}
```

UTF-8 length `199`; SHA-256 `729c2bb125dd49e36a3e31d155972d698a4886e9fd4e8a581f7bfe0a0b18153b`.

| Negative vector | Exact input bytes (ASCII) | SHA-256 of supplied bytes | Rejection |
| --- | --- | --- | --- |
| ratio-zero-denominator | `{"denominator":0,"numerator":0}` | `cf35c0f75ea19bdb5fbb3881ff9d1c4c1f4317e980a4bba22dcc8deb2b5c13f6` | undefined / nonpositive denominator |
| ratio-unreduced | `{"denominator":6,"numerator":2}` | `682e4f7b04e22d7ef8d0611745a2fa9801b837bb85233c30e7329d044ab314e9` | GCD not one |
| ratio-unreduced-zero | `{"denominator":5,"numerator":0}` | `39f39691fbe75c17abf2855ee02229a121824c47a4d783170de818b8463e2010` | zero must be 0/1 |
| ratio-negative-denominator | `{"denominator":-7,"numerator":5}` | `294f85142ec81b40a3ff782d8c4a0887d28894b2868acb8a2c9037971699e075` | negative range |
| ratio-float | `{"denominator":7,"numerator":5.0}` | `18d224a7a21fc5cbf8393fbd54e420ef7369184fe28d1e1a89b95963aff4d742` | float type |
| ratio-boolean | `{"denominator":7,"numerator":true}` | `99f086815870a9df6ccb7218816e788c810233f6ba749800299d9c69680c9ec7` | bool type |
| ratio-string | `{"denominator":7,"numerator":"5"}` | `3c69e93081468b43b0cd19780bd7e613a0b09cab0012a604f68ba01bbc17c71b` | string type |
| ratio-denominator-over | `{"denominator":17,"numerator":1}` | `96a998a2e7f17ff231d0e1078d7e9380b00f4e92117358a0d7ac9cdac5bc272a` | voting limit |
| ratio-numerator-over | `{"denominator":16,"numerator":16}` | `39511669ad999ab792284bae955a09bd16e2aff9347ef13b6a61028a65db6dac` | range and noncanonical one |
| ratio-missing-field | `{"numerator":5}` | `d73823e1dea353da6f53bd9c2bd94b2088e6b1b3cac279a92d0ed715737ffdec` | missing denominator |
| ratio-unknown-field | `{"denominator":7,"extra":0,"numerator":5}` | `349afc50d6e9053d224713a8d3917150ad7c7672bc3c72495d0711b89f823615` | unknown key |
| ratio-negative-zero | `{"denominator":1,"numerator":-0}` | `f46f7e8165cf4c8e6de434335bc177431c548e9f9aa20e63cffc37c6eea3ed9c` | noncanonical numeric token |
| ratio-nan | `{"denominator":7,"numerator":NaN}` | `75d51f19c4fd9be3b41ced1b29c18ea278e7bf14823fba7e3f8963768518c09e` | not JSON |
| ratio-infinity | `{"denominator":7,"numerator":Infinity}` | `3fb8739d5700332b579633f1492cb5ee892fc93d759ec6a8afbc421a734b1668` | not JSON |

The NaN/infinity rows are hashes of malformed supplied input, not canonical JSON hashes. These fixtures distinguish lexical/type/range/normalization failure from an unresolved but valid intermediate tally. The 152 defined p,d input pairs for 1<=d<=16 all reduce to bounded ratios; integer threshold equivalence and all 23,104 pairwise comparisons were checked against Python Fraction and independently with JavaScript BigInt/GCD. Zero-vote and all-unsure outcomes were compared to the existing pure tally function using counter-only inputs, not signature-bearing accepted evidence. No production tally is changed.

### Negative examples and boundary recipes

| Input / recipe | Expected result |
| --- | --- |
| Native T without memo, or memo `""` | Invalid required-field/nonempty rule; cannot alias explicit null |
| `{"memo":null,"memo":null}` | Duplicate-key rejection before dict construction |
| `{"nonce":true}`, `{"nonce":1}`, `{"nonce":"01"}` | Wrong exact type / noncanonical nonce; only canonical digit string permitted |
| Amount `"1.0"`, `"1e0"`, `"-0"`, `"NaN"`, `"Infinity"` | Noncanonical/nonfinite numeric representation |
| `{"memo":"\u00e9"}` as standalone J bytes | Noncanonical escaping; exact J is UTF-8 `7b226d656d6f223a22c3a9227d` |
| `{"memo":"\ud800"}` or invalid UTF-8 byte `ff` | Invalid Unicode/UTF-8 rejection |
| Extra `status` on T or extra field inside technical evidence | Closed-schema rejection, even if hashes are recomputed |
| SHA-256 ID correct but signature for old protocol/domain, wrong signer or changed nonce | Signature/context rejection |
| Sig65 with uppercase hex, wrong prefix/length, or wire recovery byte 0/1; noncanonical legacy base64 | Representation rejection before signature recovery |
| Vote records reversed from required dimension/wallet order, duplicate dimension/wallet, or unknown reviewer status | Ordering/duplicate/identity rejection; do not sort/deduplicate into acceptance |
| Certificate context-only projection, `{}`, missing certificate version, old certificate version | Invalid incomplete/legacy certificate; digest equality never supplies missing fields |
| Bad base64 `YR==`, missing/excess padding, URL alphabet, whitespace | Descriptor rejection; `YR==` decodes to `a` in permissive decoders but has nonzero pad bits |
| Encoded/original count mismatch, wrong original H, unknown profile, truncated/checksum-bad/trailing Zstd data | Deterministic descriptor/frame/integrity rejection through approved decoder boundary |
| Worker timeout/OOM/crash/cancel/missing controls | Indeterminate local failure, never protocol-invalid or usable partial media |

Versioned boundary recipes avoid huge copied literals: (a) maximum native nonce
is ASCII `9007199254740991` (16 bytes); next integer 9007199254740992 rejects;
(b) max OpaqueNonce is `a` repeated exactly 256 times, its JSON string value is
258 bytes, one more rejects; (c) memo of U+0000 repeated 280 times has 280 raw
UTF-8 bytes and a J string value of 1,682 bytes (`"` + `\u0000` repeated 280 +
`"`), one more scalar rejects; (d) U+1F600 repeated 280 has 1,120 raw UTF-8 bytes,
same value length plus two quotes under J, and 3,362 under ASCII escaping;
(e) caption U+0000 repeated 1,000 has a J value of 6,002; (f) E at 2 MiB has
2,796,204 base64 content bytes, one byte more E rejects independently of R.
These are field/serialization probes, not fabricated valid certificates or
claims of technically admissible NUL media. The later implementation must add
child/parent at/one-over and all permitted ratio vectors against these recipes.

Boundary hashes below are over the exact J **string value**, including its two
quotes, not a containing field member. They were matched independently with
Node's JSON string writer and SHA-256:

The separate Unicode object projection with exact UTF-8 bytes
`7b226d656d6f223a22c3a9227d` has length 13 and SHA-256
`3bb20d581a022f63926569a56716b23860666567518a3a1f1c3c35b660e8aa4f`.
It is a memo projection, not a complete native record.

| Boundary recipe | Serialized bytes | SHA-256 |
| --- | ---: | --- |
| `"9007199254740991"` | 18 | `c9b6149ddff7d8ecb9e6de99f01b5742a0df39a5b4c8be4a31b65d4add22ba84` |
| `a` repeated 256 | 258 | `b836e815e3c2961cf71a8ba03486aec54101b1538e8b19874ad216b90127f795` |
| U+0000 repeated 280 | 1,682 | `bcfcd5848e2b8dc064e02ee75e0d7e517ab6591611076b7ad776240068688dd2` |
| U+1F600 repeated 280 | 1,122 | `033a3e64d74f87e37806650d6df6b89d836ccf5b97f64b7c54037c69113086d8` |
| U+0000 repeated 1,000 | 6,002 | `47adc79d06c99870c4ef505c6d2b3514ca27579d42a31e03258af86f22be7061` |

## 11. Focused checks and implementation handoff

Baseline regression commands/results and example checks are recorded below.
The full repository suite, live mempool/finality/admission path and independent
Zstd decoder were not executed. Current tests remain historical-protocol tests;
they cannot certify the unimplemented new format.

```powershell
.\.venv\Scripts\python.exe -B -m pytest tests/test_protocol_v1.py tests/test_protocol_v1_golden_vectors.py tests/test_protocol_v1_native_transfers.py tests/test_native_transfer.py -q --tb=short -p no:cacheprovider
# 108 passed in 1.27s

.\.venv\Scripts\python.exe -B -m pytest tests/blockchain/test_task_3_5_validator_quorum_finality.py::test_validator_quorum_is_ceiling_of_two_thirds tests/blockchain/test_task_3_5_validator_quorum_finality.py::test_validator_configuration_normalizes_duplicates_and_rejects_malformed_entries tests/test_milestone_5_task_5_7_reviewer_reputation.py::test_reputation_rule_v1_is_preserved_and_v2_is_active_and_deterministic tests/test_milestone_5_task_5_7_reviewer_reputation.py::test_identical_or_same_choice_votes_do_not_prove_equivocation -q --tb=short -p no:cacheprovider
# 10 passed in 0.77s
```

The examples can be reproduced from the exact literals/formulas above using
sorted compact JSON (`ensure_ascii=False` for J, true only for A) and SHA-256
of UTF-8 bytes. Personal-sign signatures are over EIP-191 Keccak bytes, not the
SHA-256 ID. The fixed-key native examples were recovered with eth-account and
also verified as ECDSA over the manually computed EIP-191 digest with OpenSSL
through cryptography. Old-domain replay failed the expected signer check.
No encoder was run to reproduce the frozen Zstd bytes. These checks do not
establish algorithmically independent decoder agreement or production security.

Verification environment: CPython 3.13.5, Node v22.17.0, existing project
eth-account/cryptography and Windows .NET SHA256. In total, 118 focused existing
tests passed; 17 JSON/media/native/context preimages and 22 rational/count
positive/negative supplied-byte examples matched across hash implementations.
The rational-domain and pairwise checks use integer arithmetic only. Five
boundary-value hashes, the exact 33-byte ratio ceiling and the frozen memo
whitespace set were checked separately. The two frozen descriptor examples
reconstruct the same original `a` through the current strict offline adapter.
No new backend or package was installed.

Final documentation checks passed for all 19 literal JSON lines and their
displayed hashes, the 39 supplied-example hash references, the 18 runtime/UI
consumer-file inventory, exact component-size arithmetic, local links, UTF-8,
final newline, fenced blocks and trailing whitespace. `git diff --check` and
`git diff --no-index --check -- NUL docs/milestone-7-v3-canonical-schema-decision.md`
passed. Final worktree contains only the modified historical report pointer and
this new untracked decision; branch/HEAD are unchanged and nothing is staged.

Before a separately authorized Task 7.10 resumption:

1. Port the selected rational rule and all p,d/count/undefined examples into
   independently checked implementation fixtures; both summaries must agree
   with the original integer tally, without float/context-dependent conversions.
2. Resolve the optional legacy signed transfer path versus replay separation;
   explicitly amend the carried-forward allowance or specify its new version.
3. Freeze the bounded snapshot selection/approval and complete new policy
   registry/digests, N/W and intended statement/animation/safety launch choices.
   Do not use placeholder values as a production context. Reviewer/reputation
   semantic rule versions do not grant an adapter permission to reuse an old
   network's historical state.
4. Then implement the strict inert schema/parser/serializer/hash and isolated
   media adapter, porting these positive/negative examples into versioned golden
   fixtures with independently checked complete preimages. Do not wire existing
   permissive Block.from_dict/current canonical builders into the new path.
5. Include canonical/null/Unicode/signature/context, parent/child budget,
   certificate/tally binding, original-H invariance and same-M/different-E block
   vectors. Inert test fixture contexts must be explicit and distinct from launch.
6. Retain all existing decoder independent-audit/work/state/platform/worker and
   media-admission isolation gates. Local resource failures withhold validation;
   compression fallback and watchdogs are not new validity rules.

**Task 7.10 cannot safely resume as a complete specified block-format task yet.**
This design report is reviewable with explicit blocked decisions. It authorizes
no automatic implementation, signing-context activation, database change,
network reset, deployment, commit, push, merge, or subsequent task.
