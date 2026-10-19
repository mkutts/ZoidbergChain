# Milestone 7 Task 7.10B — Signing, Domain Separation and Replay Protection

Date: 2026-10-19 (America/New_York).

**Decision: one versioned signed user-transfer path, plus narrowly defined
unsigned protocol records.** For the new protocol, use native-transfer signing
version 2 with the existing secp256k1 personal-sign scheme, an explicit genesis
hash and transaction type in its signed payload. Reject both old native signing
formats and legacy `Transaction` user transfers. The old `transactions` array
becomes exactly one unsigned creator-reward record in a non-genesis media block.
Genesis allocations remain separately authenticated by the trusted genesis.

This is a specification, not an implementation or activation. It resolves the
legacy-signing design gate in [Task 7.10A](milestone-7-v3-canonical-schema-decision.md)
and deliberately refines its provisional native preimage before launch. It does
not modify historical signatures, balances, active consensus, genesis, database
schema, codecs, or original-media identity. No real launch identity or signing
key is generated. Task 7.10 is not resumed automatically.

## 1. Repository verification and scope

| Check | Result |
| --- | --- |
| Branch | `Compression-State-Bloat-and-Node-Economics` |
| HEAD | `ca1ac9ecbb666f0d5c86e627db7eee154f35dea0` |
| Separate Task 7.10A commit | HEAD, `Milestone 7 Task 7.10A: define canonical schema and exact rational tallies` |
| Relevant previous commits | `4f16cd3` Task 7.10 blocker report; `824afdb` Task 7.9 capacity decision |
| Initial worktree | Clean |
| Instructions | No repository AGENTS.md found; ancestor check earlier in this conversation found none |
| Changes | This new document and necessary signing/status amendments to the two schema/blocker reports |

Read the [schema decision](milestone-7-v3-canonical-schema-decision.md),
[blocker report](milestone-7-v3-block-format-implementation.md),
[compression protocol](milestone-7-compression-protocol.md), and
[storage/capacity decision](milestone-7-v3-storage-and-capacity-decision.md).
Inspection was limited to their signing, identity, admission, mempool,
validation, reward, finality and genesis dependencies and focused tests.

All source references below identify the inspected HEAD, not a hypothetical
new implementation. Current protocol version remains 1; its media admission
blocks use block version 2. The proposed protocol 2 / block 3 is not active.

## 2. Existing signing audit

There are three relevant historical user-transfer representations, not one.

| Path and exact source | Signed bytes, algorithm and ID |
| --- | --- |
| [`transaction.py:45`](../transaction.py#L45), `sign_transaction`; [`transaction.py:69`](../transaction.py#L69), `is_valid` | UTF-8 of Python `f"{sender}{recipient}{amount}{tip}"`, with no separators. secp256k1 ECDSA-SHA1. Signature is 64-byte raw r||s, standard base64 (88 characters). `Transaction.to_dict` contains no native-style tx_id; this legacy pool does not acquire the native transaction-ID contract merely by inclusion in a block. |
| [`wallet.py:10`](../wallet.py#L10), raw/DER helpers at 21/26, `sign_data` at 105 and `verify_signature` at 118 | Existing compressed public keys and exact 32-byte scalar loader; raw 64-byte r/s converted to DER for OpenSSL verification. The wallet helper also uses ECDSA-SHA1 for that historical path. |
| [`native_transfer.py:713`](../native_transfer.py#L713), versionless branch of `build_transfer_signing_message` | LF-joined human-readable message shown below, personal_sign with secp256k1/EIP-191 Keccak-256. It binds an application network name, amount, fee, nonce, timestamp and optional memo, but no protocol version or genesis hash. |
| [`native_transfer.py:312`](../native_transfer.py#L312), `_canonical_transaction_fields_legacy`; ID dispatch at [`native_transfer.py:461`](../native_transfer.py#L461) and 484 | A versionless native ID is SHA-256 of compact sorted **ASCII-escaped** JSON of the canonical legacy native fields, including signature, signed_message and signed_message_hash. It is distinct from both plain Transaction (no such ID) and versioned native identity. |
| [`protocol_v1_native_transfer.py:50`](../protocol_v1_native_transfer.py#L50), payload; envelope at 84; message at 115; identity at 167/179 | Version-1 native U has amount, fee, from_address, memo (explicit null allowed), nonce, timestamp, to_address, transaction_version. M is canonical UTF-8 J of the six-key `zoidbergchain/native-transfer/v1` envelope with network_id and protocol_version=1. personal_sign authenticates M; SHA-256(M) is both message ID and tx_id, excluding signature. |

The exact versionless native message is `"\n".join(lines)` with these ordered
lines; include `Memo: ...` only when the normalized memo is nonempty:

```text
ZoidbergChain Native Transfer

Action: <action>
Network: <network>
From: <from_address>
To: <to_address>
Amount: <amount>
Fee: <fee>
Nonce: <nonce>
Timestamp: <timestamp>
[Memo: <memo>]

This authorizes a native ZOID transfer on ZoidbergChain.
This is not an Ethereum/ERC-20 transfer.
```

Square brackets are explanatory, not signed bytes. Joining the actual lines
adds no final LF. This is not the envelope used by versioned native transfers.

### Verification and state boundaries

| Source | Actual responsibility / relevant limitation |
| --- | --- |
| [`api_routers/native.py:63`](../api_routers/native.py#L63), legacy add route; [`blockchain.py:5090`](../blockchain.py#L5090), `add_transaction`; `validate_transaction` at 5116 | Legacy construction/signature and balance checks; the plain Transaction path has no signed nonce, network, genesis or transaction-signing version. |
| [`native_transfer.py:60`](../native_transfer.py#L60), wallet recovery; `verify_transfer_signature` at 809 | Recover from `encode_defunct(text=message)` and require expected normalized sender Wallet. Message SHA-256 is not the cryptographic personal-sign digest. |
| [`services/native_transaction_validation_service.py:71`](../services/native_transaction_validation_service.py#L71), identity; admission at 126; block step at 168 | Reconstruct exact versioned M; check versions/network/message hash/tx_id/sender signature, then contiguous nonce, fee zero, duplicate ID/sender-nonce and available balance. Current mempool explicitly requires version-1 native transfers, so it does not automatically accept every historical native representation. |
| [`services/native_mempool_service.py:32`](../services/native_mempool_service.py#L32), validation and selection at 39 | Uses authoritative ledger checks and sender/nonce/ID ordering, then selects the block projection. |
| [`services/native_ledger_service.py:166`](../services/native_ledger_service.py#L166), projection; aggregate at 174; immutable replay at 307/315; admission at 318 | Selects immutable native fields and binds durable replay to immutable signed data. Native aggregate is SHA-256 of A(ordered exact records); lifecycle state is separate. |
| [`services/block_validation_service.py:106`](../services/block_validation_service.py#L106), native validation; certificate/reward at 222; candidate at 298; admission block at 318 | Checks aggregate/order and ledger transitions, certificate/reward bindings, block preimage/linkage and ancestry. Candidate handling calls `Transaction.is_valid`, which by itself returns true for GENESIS/REWARD_POOL sentinels; this shortcut is not sufficient authority for a new unsigned record. |
| [`services/block_production_service.py:159`](../services/block_production_service.py#L159) | Constructs fixed creator reward, checks duplicate certification and sufficient reward pool; current creator reward is 5. Admission certificates do not receive legacy voter rewards. |
| [`admission_certificate.py:135`](../admission_certificate.py#L135), builder; validation at 165 | Frozen media/admission evidence authenticates original content and creator, not an arbitrary transfer or implicit producer signature. Its digest excludes only its own digest field. |
| [`protocol_v1_finality.py:42`](../protocol_v1_finality.py#L42); [`services/finality_service.py:76`](../services/finality_service.py#L76) and 151 | Distinct finality envelope/purpose, signer membership, exact height/hash and validated quorum proof. Finality does not retrospectively give an undomained transfer signature its missing network binding. |
| [`protocol_v1_genesis.py:182`](../protocol_v1_genesis.py#L182), allocations; payload at 197; bytes/hash at 215/223; record at 243 | Frozen unsigned bootstrap allocations are authenticated by the separately fixed genesis payload/hash. Current v1 G is a frozen constant checked against canonical recomputation, not a newly selected launch identity. |

### Replay findings

Plain Transaction signatures do not bind nonce, network, chain/genesis,
protocol, transaction type, payload_size_kb or created_at. `amount` and `tip`
are concatenated without boundaries: text pairs `1,23` and `12,3` produce the
same numeric suffix `123` with fixed identities. `1.0` versus `1` can instead
change a signature preimage for the same intended numeric amount. No collision
in SHA1 or block hashing is needed for these encoding/replay observations.

Versionless native messages provide more binding (including a nonce and network
name), but lack explicit protocol/genesis separation. Version-1 native envelopes
already provide network/protocol/object-purpose binding and enforce nonces;
they should not be described as having the plain Transaction vulnerability.
They do not directly bind a genesis hash. Reusing their network identity on a
reset would leave the signature itself unable to distinguish the two roots.

Current authorization of unsigned system records depends on complete genesis or
certificate/reward/block rules. A sender sentinel alone is never enough. No
claim is made that every current endpoint already enforces the new stricter rule.

## 3. Strategy comparison and selected architecture

| Strategy | Benefit | Cost / disposition |
| --- | --- | --- |
| A: retain historical user-transfer formats with restricted compatibility; add protected transfers | Less client conversion work | Multiple ID/signature rules and a downgrade surface; plain historical transfers still cannot be safely accepted as new-network spends. Not selected. System rewards were already unsigned, so there is no reward signature to preserve. |
| B: one new versioned user-transfer profile, explicit unsigned protocol projections | Existing native nonce/balance rules and personal_sign scheme, exact domains, no fallback | **Selected.** New-network user transfers are native_transfer version 2 only. The old transactions array is reward-only. Old signing helpers remain historical readers, not new validators. |
| C: retain two user-transfer families and invent a second domain-separated ECDSA legacy envelope, or rely only on fresh N without direct G | Could keep compressed-key user-transfer APIs or save a hash field | A second envelope and account/nonce policy are unnecessary; N-only protection additionally depends on never reusing a label. Not selected. |

This is an explicit prelaunch amendment of Task 7.2's optional legacy user
transfers and Task 7.10A's provisional native preimage. It is not backward
compatibility inside the new chain. Existing native wallets keep their existing
personal-sign key mechanism and must authorize fresh new-context messages.
Legacy compressed keys can still have their independently specified historical
or miner roles; no automatic conversion of their balances/ownership to a Wallet
is invented. New genesis allocations and the disposition of old state remain
separately reviewed launch decisions.

There is no requirement to preserve old pending transfers or signatures as
valid new-network transactions after the permitted development reset. Preserve
supported old readers/exports for archives; re-admit under the new context only
with fresh authorization. This task performs no reset or conversion.
In particular, do not translate old legacy tips into native fees or new rewards;
fee remains zero and a new native amount must be freshly authorized.

## 4. Exact new native signing contract

Let P=2 be protocol version and S=2 the native transaction signing/schema
version. The existing field `transaction_version` carries S; do not add a second
`signing_version` alias. P and S are separate concepts even though both are 2.
Let N be network ID, W its fixed application name, and G the frozen genesis hash.

### Record T: 18 required keys

Retain every Task 7.10A native field and add required `genesis_hash`:

```text
amount, fee, from_address, genesis_hash, memo, network, network_id, nonce,
protocol_version, signature, signature_scheme, signed_message,
signed_message_hash, timestamp, to_address, transaction_type,
transaction_version, tx_id
```

| Field group | Exact constraint |
| --- | --- |
| `transaction_type` | `native_transfer`, the sole signed user-transfer type in this launch |
| `transaction_version`, `protocol_version` | Actual integers 2, excluding bool/float/string |
| `network_id`, `network` | Exactly frozen N and W; no alias, trim or case repair |
| `genesis_hash` | Exactly 64 lowercase ASCII hex characters, equal to the configured trusted G and signed U value |
| `from_address`, `to_address` | Distinct canonical Wallets from Task 7.10A; sender equals recovered signer |
| `amount`, `fee` | Canonical finite Money strings, <=32 bytes / <=6 fractional places; amount>0 and bounded by supply/balance, fee exactly `"0"` |
| `nonce` | Canonical ASCII integer string 1..9,007,199,254,740,991, <=16 bytes, contiguous per sender |
| `timestamp` | Exact Task 7.10A TimeUTC, <=32 ASCII bytes |
| `memo` | Required null or nonempty already canonical string, <=280 scalars / 1,120 UTF-8 bytes; Task 7.10A's frozen edge-trim set applies before signing only |
| `signature_scheme`, `signature` | Exactly `personal_sign` and canonical Sig65: lowercase 0x + 130 hex characters, 1<=r,s<curve order, recovery byte 27/28; successful recovery required. No new low-S restriction |
| `signed_message` | Exactly UTF8_decode(M) below, <=4,096 raw UTF-8 bytes |
| `signed_message_hash`, `tx_id` | Equal 64-character lowercase SHA-256(M) |

All fields are required, no extras allowed. No local status, created/updated
clock, settlement/inclusion hash or arbitrary extension enters T. A missing G
does not select an old parser. A stale tx_id cannot be repaired on receipt.

### Payload U: exactly ten required keys

```text
amount, fee, from_address, genesis_hash, memo, nonce, timestamp,
to_address, transaction_type, transaction_version
```

Each equals its T value, including explicit memo null and the same G. The two
additions to Task 7.10A's eight-key payload are G and transaction_type. Both are
deliberate consensus-preimage changes, not permissive optional extensions.

### Exact signing bytes M

```text
E = {"domain":"zoidbergchain/native-transfer/v2", "network_id":N,
     "object_type":"native-transfer", "payload":U,
     "protocol":"zoidbergchain", "protocol_version":2}
M = J(E)
```

E has exactly these six keys. Use Task 7.2/7.10A J: compact sorted unique-key
JSON, UTF-8 without BOM/newline, scalar Unicode without normalization, prescribed
escaping, array order preserved, no floats/coercion, closed nested schemas.
The outer domain is a fixed purpose/protocol literal, not a user-provided tag
or a string assembled from an unsupported version. N/G/P/S/type must match the
active immutable profile before signature/ledger acceptance.

W stays a fixed redundant application label, not a separately signed chain ID;
validators require the trusted N->W mapping. The actual cryptographic chain
binding is N plus G. No numeric Ethereum chain ID, EIP-155 recovery value,
EIP-712 schema or new curve/hash algorithm is introduced.

### Cryptographic verification

```text
D_sign = Keccak-256(0x19 || ASCII("Ethereum Signed Message:\n")
                     || ASCII_decimal(len(M)) || M)
```

Length is UTF-8 **bytes**, not characters. Use the existing secp256k1 personal-sign
verification/recovery mechanism and require the recovered Wallet equals
from_address. The signature authenticates M with its EIP-191 prefix, not the
ASCII tx_id or SHA-256 digest. Do not add an extra SHA256/Keccak pass or accept
a raw ECDSA-SHA1/base64 signature as a fallback.

As fixed in Task 7.10A, the curve order is
`fffffffffffffffffffffffffffffffebaaedce6af48a03bbfd25e8cd0364141`.
An application adapter can canonicalize recovery byte 0/1 to 27/28 before
forming an immutable record, but those aliases are invalid wire encodings.
Different mathematically valid r/s signatures remain different authenticated
record data; duplicate ID/nonce rules prevent double spending. This retains
existing high-S acceptance rather than silently adding a cryptographic rule.

This is the one launch profile (P=2,S=2,type=native_transfer). Unknown type,
version, scheme, envelope purpose or missing fields reject before a legacy
fallback can run. A future profile requires an explicit new specification,
registry activation and vectors; a library update never authorizes it.

## 5. IDs, block hashing and dependencies

```text
tx_id = signed_message_hash = lowercase_hex(SHA-256(M))
transactions_hash = lowercase_hex(SHA-256(A(ordered exact native T records)))
block_hash = lowercase_hex(SHA-256(J(protocol-v2 block envelope)))
```

Retain the existing versioned-native ID format (64 lowercase hex); only the
explicit new preimage changes. A and J remain distinct: native aggregate A
uses ASCII escaping, enclosing block J uses unescaped Unicode. Neither a
signature nor a local lifecycle field is an input to tx_id. Reordering object
insertion order does not change M/ID; changing N,G,P,S,type, sender, receiver,
amount, fee, nonce, time or memo changes the signed bytes and commitment.

Signature bytes are included in T, its aggregate and the block commitment.
Two valid signatures for the same M therefore keep one tx_id but may change
block bytes/hash. Within a block/ancestry reject repeated ID and sender-nonce;
preserve current immutable-payload conflict and mempool reservation semantics.
Same sender/nonce with changed amount is a conflict, not a second allowed spend.

G is a **past** immutable root. No tx_id, native aggregate, future block hash,
admission certificate digest or finality signature occurs in U. Certificates
authenticate original media/creator, block h authenticates certificate/T/E, and
separate finality signatures authenticate height/h/N. Finality cannot rewrite h.
New native signatures cannot be used as submitter, community review, finality,
block or genesis authorization because their object schemas/domains differ.

## 6. Exact unsigned exceptions

### Non-genesis media block: exactly one creator reward Q

P.transactions is exactly `[Q]`. Q has five required keys and no signature key:

```text
{"amount":"5", "payload_size_kb":"0", "recipient":P.creator_wallet,
 "sender":"REWARD_POOL", "tip":"0"}
```

J sorts the keys; the displayed spacing is explanatory. The unchanged launch
reward rule is 5 ZOID. Q.recipient must equal the validated certificate creator,
P.reward_recipient and the existing reward-eligibility result; P.reward_amount
must be `"5"`, reward_type=meme_mining_reward, reward_source=reward_pool, and
voter_rewards must be `[]`. Changes to economic rules require separate policy
review, not an arbitrary value in an unsigned record.

A candidate producer constructs Q from frozen admission evidence and predecessor
state. Validators independently verify the complete certificate, media/H/type,
submission/certificate/reward duplicate claims, reward recipient/amount and
sufficient reward pool under the unchanged ledger rules. Debit the existing pool
once; do not create new supply, a fee top-up, voter reward or compression bonus.
The complete block commitment and consensus/finality authenticate Q in context.
There is no implicit producer signature or special secret signing key for Q.

Sender text alone grants no authorization: Q is forbidden as a mempool/native
user transfer; REWARD_POOL is not a Wallet; native_transfer always requires
Sig65; a second Q, wrong recipient/amount, signature/null field, unknown key,
legacy signed transfer or unsigned user transfer makes the media block invalid.
Do not call the old sentinel shortcut as the new acceptance rule. Any party may
relay a completely valid block; that does not authorize arbitrary pool debits.

Q is 126 serialized bytes with its 42-byte Wallet, and `[Q]` is 128. It remains
inside the existing 1,024-byte record/S_rest allocation; count is narrowed from
the earlier <=16 reward/legacy allowance to **exactly one**. Native user count
remains <=10. Q has no standalone spend ID or nonce; reward claims derive from
the authenticated submission/certificate and containing block. Never put the
containing block hash into Q to try to identify it before hashing.

### Genesis-only allocations

The other unsigned exception is the fixed allocation set inside the separately
discriminated, reviewed genesis object (`object_type=genesis`, index 0 and its
own frozen schema). Authority is recomputation/equality with trusted G and exact
approved allocation/supply data, not merely sender=`GENESIS`. No GENESIS record
is accepted in a non-genesis block or user-transfer API. No ordinary signed
transfer referring to G is placed inside the preimage that creates G.

Existing v1 genesis projections (including their null signatures) remain
historical rules, not an alternate new reward representation. The actual new
genesis schema/state and allocation values are pending a separate authorized
bootstrap task; none are generated here. Their own limits are separate from
the complete non-genesis media record budget. No general unsigned issuance,
administrative transfer, faucet or arbitrary system-type exception is added.

## 7. Immutable launch identity and avoiding a genesis cycle

| Fixed protocol constant | Exact value / purpose |
| --- | --- |
| Protocol/name, block, media versions | zoidbergchain / 2, media block 3, media encoding 1 |
| User transaction signing/schema version | S=2 in transaction_version; protocol_version=2 separately |
| User transaction type / scheme | native_transfer / personal_sign |
| Native purpose | zoidbergchain/native-transfer/v2, object_type=native-transfer |
| Other purposes, kept separate | zoidbergchain/block/v2, genesis/v2, submitter-attestation/v2, finality-attestation/v2; community review uses its specified flat zoidbergchain/community-review/v3 context |

| Deployment-specific immutable input | Format and binding |
| --- | --- |
| N | 3..64 lowercase ASCII characters under Task 7.10A network-ID grammar; choose a new reviewed value for every fresh launch/reset; do not reuse the old public-testnet ID |
| W | One frozen application network name, matching Task 7.10A grammar, <=64 bytes, bound to N; not a second independently negotiated chain |
| G | 64 lowercase hex characters, SHA-256 of J of the approved new protocol-v2 genesis envelope, excluding its portable hash field; locally trusted and independently recomputed from exact genesis data |
| Policy/registry/genesis definition | Frozen schemas, signing profile, codecs, limits, rational rules, policies, statement and validator trust context committed by the reviewed genesis/launch data |

No additional numeric chain ID is needed: the cryptographic chain identity is
the pair **(N,G)**. N prevents ordinary cross-network confusion; G also prevents
replay when an environment mistakenly reuses N with a different root. Reusing N
is still forbidden launch practice because other admission contexts also bind N.
W and display names never override N/G. A SHA-shaped peer-provided value is not
proof of a trusted genesis.

Generate/distribute the identity in this order in a later authorized launch:

1. Freeze protocol rules, policy/registry digests, N/W and the reviewed genesis
   inputs. A registry may specify the rule "transaction genesis_hash equals the
   trusted root" but must not embed the not-yet-computed G into its own genesis
   preimage. No self-referential digest requirement is introduced.
2. Serialize the approved new genesis envelope and compute G. Verify it through
   an independent serialization/hash check, supply/allocation validation and
   frozen vectors. No ordinarily signed G-dependent transfer is used to form it.
3. Package the exact genesis bytes, N/W/G and supported versions/profile registry
   in the reviewed launch artifact. A post-genesis manifest may contain G, but
   its G-containing digest must not be retroactively inserted into that same
   genesis. Distribute through a reviewed authenticated release/configuration
   channel; its operational route still needs launch-owner selection. This task
   creates no distribution-signing key or new trust system.
4. Independent nodes receive the artifact through an authenticated/trusted
   distribution route, pin expected N/G/profile data locally, recompute genesis
   identity, and compare the same fingerprints before accepting peers/history.
   Peer handshakes/imports must match both N and G and versions; peers cannot
   choose or update a node's trust anchor merely by advertising one.

The actual N, W, G, genesis allocations/time and registry/policy digests remain
explicitly **PENDING launch approval**. The examples below are test-only symbolic
contexts, not generated launch identities or genesis state. Current v1 genesis
bytes/hash are not copied into the new context. A later reset needs its own
explicit authorization, old-state disposition and archived supported reader.

## 8. Replay threat model and rejection rules

| Attempt | Required result |
| --- | --- |
| Same payload/signature on another N | Different M/tx_id; reject network/context or expected-signer binding |
| Same N with different G | Different M/tx_id; reject trusted-G equality or expected-signer binding before ledger acceptance |
| Different P or S | Unsupported profile rejects; changed bytes cannot reuse the old commitment |
| Different transaction type/purpose/object | Exact schema/type/domain checks reject; no fallback to another signature scheme |
| Change sender/receiver/amount/fee/nonce/time/memo | Recomputed M/ID and signature/record equality checks expose the change |
| Rewrite T metadata but keep signed_message | Duplicate field equality/context checks reject, even if an attacker recomputes a block hash |
| Reuse ID or sender nonce after settlement | Ancestry/nonce checks reject; changing a signature does not authorize another spend |
| Replay in an alternate fork | Validate against that branch's state and finalized anchors; a valid transfer may exist on mutually exclusive forks but cannot settle twice on one canonical ancestry |
| Supply old plain/base64 signature, versionless native message, native version 1 or Task 7.10A's provisional U8 | Reject representation/version/closed-schema/context; never invoke historical validation as a fallback |
| Submit a well-formed Q as an unsigned user transfer or add a second reward | Wrong API/type/context or exact-count/reward-rule rejection; sentinel alone is not authority |
| Transcode media and reuse finality | Original H may stay equal, but changed block bytes/hash need fresh finality authorization; original-media duplicate/reward claims remain binding |

Keep deterministic malformed/unsupported/signature/context failures separate
from local decoder resource failures. A worker timeout/OOM/crash never makes a
previously valid transfer consensus-invalid or permits skipping its checks.

## 9. Canonical byte examples

These are draft vector material (`task-7.10b-signing-v1`), not accepted full
blocks or deployed identities. The existing published all-11 test key in
`tests/test_protocol_v1_golden_vectors.py:62` is reused; no key is generated or
rotated. Its Wallet is `0x19e7e376e7c213b7e7e7e46cc70a5dd086daff2a`.
N=W=`zoidberg-signing-vector-v2` and G=`a` repeated 64 are **test-only** symbolic
inputs, with no generated genesis. Raw JSON lines have no final newline.

### Base transfer message M (527 UTF-8 bytes)

```json
{"domain":"zoidbergchain/native-transfer/v2","network_id":"zoidberg-signing-vector-v2","object_type":"native-transfer","payload":{"amount":"1","fee":"0","from_address":"0x19e7e376e7c213b7e7e7e46cc70a5dd086daff2a","genesis_hash":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","memo":null,"nonce":"1","timestamp":"2026-10-19T00:00:00+00:00","to_address":"0x2222222222222222222222222222222222222222","transaction_type":"native_transfer","transaction_version":2},"protocol":"zoidbergchain","protocol_version":2}
```

SHA-256(M), tx_id and signed_message_hash are all `e68931c52c88865a0ad5f73edee11b36d57887c1f953898ab0f052d86ac4f425`.

EIP-191 prefix hex is `19457468657265756d205369676e6564204d6573736167653a0a353237` (ASCII decimal byte count `527`); Keccak-256(prefix || M) is `d3d5f4b99cc7731c90ef167fc2e26931692c7d2c7746c03145d183e9d312b911`.

The canonical fixed-test-key signature is `0x3e43acc3a2b3f91b50f1cafedd3efdc9d1a22d3a1e58c367e9100ac3db3a327859c4080577c91dc0fc251b9216f04d1d7c83c10de66c1f5d773bca8d7550fa321b`.

### Exact single-field mutations

For each row, parse the exact base object, replace only the stated JSON path with the listed exact value, then apply J. The table completely defines the changed preimage; no other field, whitespace or newline is added. Reusing the base signature fails the expected sender recovery in all thirteen rows; fixed-version/type/fee/context rules may reject earlier.

| Vector | Replaced path | New value | UTF-8 bytes | SHA-256(M_changed) |
| --- | --- | --- | ---: | --- |
| network | `network_id` | `"zoidberg-signing-other-v2"` | 526 | `bb46f35d4d03946220e5427aa800d0947260b06c1093cfeeb405e9bc6711d4e7` |
| protocol | `protocol_version` | `1` | 527 | `8540d7ac175fdee3667841c07c33c506f7c3e4424e647dc0efdac71a11f9cf0e` |
| signing-version | `payload.transaction_version` | `1` | 527 | `e3642ab311b8e334120c35fd964700c6cf2da30b41a3826313feb331654a2999` |
| genesis | `payload.genesis_hash` | `"b" repeated 64 times` | 527 | `cb35653050fa50bcbb4c7a8ffeaac0479a4cc6caac38b3fa21f88a23549f2a31` |
| sender | `payload.from_address` | `"0x3333333333333333333333333333333333333333"` | 527 | `0bdfecdf6722357cbb1bc5677849f18adf01ead4387c8a56c913301ee798cc2b` |
| receiver | `payload.to_address` | `"0x3333333333333333333333333333333333333333"` | 527 | `265fda3bd5f518d4a9c41e98621cfbafbabbdd5e71f5d5976c08e568b5a3a756` |
| amount | `payload.amount` | `"2"` | 527 | `f271772258b1904dca68f9943c2a16ce1e5e75791d4d3050fba50108bf40db11` |
| nonce | `payload.nonce` | `"2"` | 527 | `8c9b1465c0297505262a48f9a92aff2a48f739d4c957c287626b12899fac2915` |
| transaction-type | `payload.transaction_type` | `"meme_mining_reward"` | 530 | `12d023aed3372fe39a3b0bbcfb68314aa2342c7e57a18a9e88f060d4e849d609` |
| purpose-domain | `domain` | `"zoidbergchain/finality-attestation/v2"` | 532 | `73405126a94a1d6239017af1a5f40019577b0b300ccaa7ea039baced051ef396` |
| object-type | `object_type` | `"finality-attestation"` | 532 | `721dd317f136a21d0ef38655616b8691099e9d625b706e52d2eac11a5e155795` |
| memo | `payload.memo` | `"é"` | 527 | `3f3e1ce405b160c8db70f9f4f0e2cacd425545cd926988da226a836258eb84e6` |
| fee | `payload.fee` | `"1"` | 527 | `588f19e60e301402c25a23285498c8489affcd0d7d36db6c122c239a3c6f19d4` |

For the memo mutation, `"é"` occupies four JSON UTF-8 bytes (two quote bytes plus c3 a9), replacing the four ASCII bytes `null`. Its byte length remains 527, while its character count decreases. A signer using character count instead of UTF-8 byte count computes the wrong EIP-191 digest.

A fresh authorization of the memo variant uses the same published test key
and the exact changed M from the table, with SHA-256/tx_id
`3f3e1ce405b160c8db70f9f4f0e2cacd425545cd926988da226a836258eb84e6`. Its canonical signature is
`0x0586d1f945c7f013133d82464f0f2f82b6a0247ae8e201e080d0ab240be20a0c0f3c2566b369533bf8309cf3ea2ddf5c694991a3217f1e7c3b26add689f21abe1b` and EIP-191 Keccak digest is
`747c2a7f29c10c86c73cfd59de8f90b46fb2f09fabb77127b9bc7e43c09d100e`. The correct prefix still contains `527`;
using character count `526` produces a different digest. Recovery and separate
OpenSSL verification succeeded for the fresh signature. This does not make the
base signature reusable or permit both different payloads to spend sender nonce
1 on one ancestry.

Update T's memo, message, signature and both ID fields consistently to construct
this exact Unicode record. J(T_unicode) is `1402` bytes, SHA-256
`e1a50c86247ecfa8ac565a904c4a5f6060a115879c0354d6423863ec97fbdb94`. A([T_unicode]) is
`1412` bytes, SHA-256
`8470f3890d60264e088c7569e103c05c9db81ffa1066f9257da42e281cac6940`. For its exact A preimage, use the
same canonical array but replace each of its two literal U+00E9 scalars (memo
and embedded message) with ASCII `\u00e9`. Both hashes are diagnostics of the
stated representations; tx_id remains the SHA-256 of M.

### T, ID determinism, signature tampering and older profile rejection

Construct T from exactly the 18 fields in section 4: copy every U field, set network/network_id to the stated test N, protocol_version=2, signature_scheme=personal_sign, signature to the base signature, signed_message to the exact base JSON line, and tx_id/signed_message_hash to its displayed SHA-256. This uniquely determines every record byte without a placeholder signature.

| Representation | Exact recipe | Bytes | SHA-256 of supplied bytes |
| --- | --- | ---: | --- |
| native-record | J(T) | 1400 | `6f4133b41f9cc2b9833e6d826baf7578727e5ef9f9bd6db23d9177cf25ea94a7` |
| native-aggregate | A([T]); all base scalars are ASCII, so also J([T]) here | 1402 | `c49dfa7b2ff2ac4c42d799a02589da551d12dc0c89588d019cba6c3f0ea5b70a` |
| pre-7-10b-payload-negative | J(base envelope after deleting U.genesis_hash and U.transaction_type) | 408 | `8ef7a96b9183267cd5fdc8053e9d69838def493ccc714fb01e72fbc912ba2057` |
| unsigned-native-negative | J(T after deleting signature) | 1253 | `a94ec8dfde969962c721f4caec4636a4d2980c34b001bb40d15a607b4d80c699` |
| same-transfer-high-s-record | J(T with s replaced by curve_order-s and recovery byte 27/28 flipped) | 1400 | `28d55f0b52ba3b9b08078cb2181128268d89a630b77139ae53f1dca981a17c0b` |

The U8 row is an invalid pre-7.10B profile even though its old signature might mathematically verify over its own bytes. The missing-signature T row is an invalid user transfer, not a system transaction. Neither triggers historical validation fallback.

The high-S counterpart is a different valid signature over the **same** M. Wallet recovery agrees, tx_id remains the displayed e68931...f425, while J(T) has the different checksum shown above. Two copies cannot both spend because ID and sender nonce are unchanged. The checksum of J(T) is not the native transaction ID.

For a reproducible tamper, change the first raw byte of the base signature from `3e` to `3f`, leaving all other bytes unchanged. The expected signer check fails. The frozen protocol-v1 native signature in `tests/fixtures/protocol_v1_golden_vectors.json` still verifies over its old message but fails against this new M; adding a `0x` prefix cannot turn it into new-context authorization. A plain Transaction's 88-character base64 raw signature is not even the new Sig65 representation, and its old message lacks required context.

### Correct unsigned reward projection, not a user-transfer authorization

```json
{"amount":"5","payload_size_kb":"0","recipient":"0x19e7e376e7c213b7e7e7e46cc70a5dd086daff2a","sender":"REWARD_POOL","tip":"0"}
```

UTF-8 length `126`; diagnostic SHA-256 `9c1090e2ec45fd8f225c876eda36f586ec84bdace1a33ce5b037f390bdd89f85`.

```json
[{"amount":"5","payload_size_kb":"0","recipient":"0x19e7e376e7c213b7e7e7e46cc70a5dd086daff2a","sender":"REWARD_POOL","tip":"0"}]
```

UTF-8 length `128`; diagnostic SHA-256 `583a3816e1a702e6edb44ed264cace2e403873c610eaa3a984938bbea16ef23e`.

This Q is only valid as the one reward inside a fully validated media block whose certificate/creator/ledger bindings agree. No qualifying certificate or accepted block is fabricated for this example. Submitting the same bytes as a native transfer or changing its recipient/amount cannot authorize an unsigned user spend.


Every mutation is an explicit generic byte-preimage probe. It does not register
another type/version or make fee 1 valid. A changed network/genesis can be valid
only in its independently trusted context with fresh authorization. SHA values
shown for Q and record representations are reproducibility diagnostics, not new
protocol transaction IDs for unsigned rewards.

Independent checks used Python json/hashlib, Node's separate JSON writer and
SHA-256, and .NET SHA256. The base literal's bytes and EIP-191 prefix were
checked explicitly; eth-account recovery and an OpenSSL ECDSA verification over
the manually constructed Keccak digest agreed. This is independent checking of
these examples, not independent full consensus or decoder implementation
conformance. No encoder, real signer, new key, chain state or deployment is used.

## 10. Capacity impact

The signature remains 65 decoded bytes / 132 textual content bytes / 134 quoted
JSON value bytes. T adds one G member; U adds G and the fixed transaction type.
With canonical field grammar these add **119 bytes to M**, **127 bytes to its
quoted escaped copy**, and **209 bytes to J(T)** including T's own G. ID/hash
strings stay 64 characters. No certificate, finality or block-envelope field is
added, and there is no new producer signature.

| Quantity | Recalculated bound |
| --- | ---: |
| Maximum native M, using all scalar width limits and 280 worst-escaped C0 memo scalars | 2,296 bytes, below 4,096 |
| Maximum J(T), same conservative widths including quoted M and Sig65 length | 5,258 bytes, below unchanged 8,192 |
| Native array using retained count/record caps | 10*8,192+11 =81,931, below 98,304 parent cap |
| Certificate bound, unchanged from Task 7.10A | 172,901, below 196,608 |
| Retained residual overhead cap | 32,768 |
| Maximum base64 contents at 2 MiB E | 2,796,204 |
| Recomputed retained-cap ceiling | **2,796,204+172,901+81,931+32,768 =3,083,804** |
| Complete record limit / remaining margin | **3,145,728 / 61,924** |

The 5,258-byte value is analytic width accounting, not a fabricated signed
maximum-size transaction. Quote/control escaping is counted twice where M is
embedded as a string. For one memo scalar, an ordinary scalar costs at most
four UTF-8 bytes, a quote/backslash costs two in J(U), and a long-escaped C0
scalar costs six. In T, that worst C0 scalar contributes six directly and seven
through the escaped M copy. Thus 280 long-escaped controls bound both copies;
no other variable field permits quotes/backslashes or arbitrary extensions.
Some scalar-width combinations are economically impossible (e.g. a 32-digit
amount under the current supply), making the bound conservative.

A(T) is a derived hash preimage, not additional stored block bytes. Non-BMP
memo scalars expand under ASCII escaping: valid-schema A(T) is conservatively
bounded by 8,338 bytes and A(ten records) by 83,391, while J(T)'s worst case is
the C0 case above. Preserve J versus A exactly and bound/validate the record and
message before dependent hashing allocations; do not charge A's extra Unicode
escapes to canonical R or silently replace A with J.

The new native fields consume already reserved per-record/array bytes; they
do not increase those caps. The reward-only decision additionally narrows the
old 16,401-byte reward/legacy array ceiling to 128 bytes. Keeping Task 7.10A's
other scalar ceilings and using actual fixed P.reward_amount `"5"` rather than
a 34-byte generic quoted decimal reduces residual width from 24,065 to
`24,065-16,401+128-31 =7,761`. With the retained native/certificate caps this
gives the stronger conservative complete-record bound **3,058,797 bytes**.
Using 5,258 per native record would bound its array by 52,591 and the same
calculation by 3,029,457; neither is claimed as a measured maximal valid block.

The older disjoint 320 KiB parent-budget proof still gives 3,123,884 with 21,844
bytes margin. The portable hash wrapper's 87 bytes, 231-byte identity descriptor
overhead, caption escaping, headers, rational summary objects, field names and
commas are all included through the same S_rest definition. Finality contributes
zero bytes inside R and retains its separate bounded proof budget. Signatures
already inside records/certificates are not counted again. No media, encoded,
transaction, overhead or 3 MiB cap is increased or relaxed.

Full mandatory identity-record reservation before certification and exact
child/parent/complete-record enforcement at every later acceptance boundary
remain required. Do not rely on compression to fit an otherwise admitted object,
and do not fabricate signatures or certificates to fill a boundary test.

## 11. Existing focused checks and required future regressions

```powershell
.\.venv\Scripts\python.exe -B -m pytest tests/test_protocol_v1.py tests/test_protocol_v1_golden_vectors.py tests/test_protocol_v1_native_transfers.py tests/blockchain/test_task_3_5_validator_quorum_finality.py::test_validator_quorum_is_ceiling_of_two_thirds -q --tb=short -p no:cacheprovider
# 73 passed in 3.50s
```

These selected existing tests use published fixed test identities or pure quorum
counts. No account-generation helper is invoked by the selected cases. They
verify the historical baseline; they do not execute a new production validator.
No new test files, production signing module or version-controlled fixture
manifest are added here; the new work is documentation and example verification.

| Future vector/regression | Required assertion and boundary |
| --- | --- |
| Preimage stability and independent serialization | Exact U10/E/M bytes, record field order, strict types/null/Unicode, independently checked SHA/Keccak/signature; never use only freshly self-generated expected hashes |
| Cross-network and genesis replay | N change and G change separately alter commitments; trusted anchor mismatch rejects at wallet/mempool/block/sync/import; no peer-selected context |
| Protocol/signing/type replay | P,S,type,purpose/object mutations and old U8/V1/versionless/raw legacy messages reject without downgrade |
| Signature behavior | Correct signer, wrong signer, malformed r/s/v, canonical recovery-byte spelling, tampered bytes and high-S-equivalent valid signature; stable ID with nonce deduplication |
| Transaction ID and aggregate | Reordered object insertion keeps ID; changed signed field changes ID; signature excluded from ID but included in A(records)/block; Unicode J/A distinction retained |
| Mempool | Wrong/missing G, legacy route, unsigned native, stale/future/duplicate nonce/ID, immutable conflict, insufficient balance and nonzero fee reject atomically |
| Block inclusion | Exact one Q, certificate/creator/pool bindings, optional native sorting/count/bytes, correct IDs/aggregate, duplicate claims and full signature verification |
| Unauthorized unsigned records | Extra Q, null/present signature, changed recipient/amount/type, GENESIS outside genesis, arbitrary unsigned native/faucet and sentinel spoofing reject |
| Export/import/restart | Preserve exact G/M/signature/ID/T/R; no float normalization, re-signing, transcoding or old-context promotion; partial restore does not authorize balances |
| Peer interoperability | Independently configured nodes pin the same N/G/profile and reproduce IDs/validity; wrong genesis despite same label rejects; no acceptance from advertised fingerprints alone |
| Activation/history | Before explicit activation keep v1 readers unchanged; new context permits only this profile; historical fixtures retain hashes; unsupported upgrades fail closed |
| Genesis/finality/certificate | Recompute approved genesis and trusted set, prevent self-reference, old-context certificates reject, finality targets exact h/height/N, separate proof never rewrites R |
| Capacity/adversarial | At/one-over field/message/record/array/block budgets, worst escaping, strict base64/decoder outcomes and local-failure separation through all actual boundaries |

## 12. Handoff, migration implications and remaining gates

Verification record: 73 selected existing tests passed. All 23 specified
preimages matched Python and independent Node JSON serialization/SHA-256,
with .NET SHA256 confirming their hashes. Thirteen base-signature mutation
replays and a frozen version-1 signature failed the new expected-signer check;
base, high-S-equivalent and freshly authorized Unicode signatures passed
recovery and separate OpenSSL verification. The Unicode example explicitly
checks 527 UTF-8 bytes versus 526 characters. Analytic message/record/array/block
accounting was independently recalculated, including the retained 3,083,804-byte
and tightened 3,058,797-byte record bounds. These are example/specification
checks, not execution of an unimplemented production v3 acceptance path.

Documentation checks passed for exact embedded JSON/hashes, mutation recipes,
local links/source-line bounds, UTF-8/final newline, fenced blocks and whitespace,
`git diff --check`, and the untracked report's `git diff --no-index --check -- NUL`
check. Final worktree is only the two modified schema/blocker reports and this
new untracked report; branch/HEAD remain unchanged and nothing is staged.

The signing rule is now specified for review: native U10/T18, N/G/P/S/type
binding, personal_sign, SHA-256(M) ID, reward-only Q and genesis-only unsigned
allocations. No essential cryptographic algorithm or legacy compatibility
alternative is silently left to a runtime library. Task 7.10A's old U8 examples
are historical prelaunch byte examples, not an additional accepted profile.
They must not coexist with U10 under S=2 in a launched network. S=2 has not been
activated; this refinement changes no existing network's version-1 history.

**The signing design gate no longer prevents isolated Task 7.10 format work.**
After review of these specification amendments, that task can use an explicit
immutable fixture context to implement/test the nonactivating format; actual
launch N/W/G values are not needed for inert byte/schema tests. It must reject
missing contexts and must not turn example values into production defaults.
This report does not resume it automatically or claim implementation readiness
for an active network.

Still pending before a real launch are the approved genesis/allocations and
state/key/wallet disposition; exact launch N/W/G and policy/registry digests;
snapshot/statement/animation/safety policy approval; exact peer summary/fork
choice adapters for rational values; all actual signing/admission/ledger/block,
storage/sync/import/export/API/finality integrations and independent vectors;
and existing decoder audit/work/state/platform/worker/media-isolation gates.
Actual reset, migration and activation require their separate authorization and
verified old archives. No old tx_id/signature, settled balance or finalized
block is converted merely by changing a version label.

Remaining review approvals concern adopting this prelaunch narrowing and
genesis/type binding, plus those deployment/security policies and actual
identifiers. They do not justify accepting an undomained legacy spend while
waiting. No production signing, consensus change, database migration, chain
reset, deployment, new signing key, commit, push or merge occurs here.
