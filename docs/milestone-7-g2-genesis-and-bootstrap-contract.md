# Milestone 7 Task 7.17L — G2 genesis and application bootstrap contract

Date: 2026-10-26 (America/New_York).

**Specification and security analysis for review. Inactive proposed G2 format;
no launch approval, implementation, reset, keys, migration or deployment.**
This proposal closes the outer genesis representation and its authority/hash
dependency order. Full application-policy semantics and authenticated history
remain **BLOCKED**. A structurally complete test object below is deliberately
not a valid launch genesis or a complete application golden vector.

## 1. Repository prerequisites, evidence and scope

| Check before editing | Result |
| --- | --- |
| Expected/actual branch | `Compression-State-Bloat-and-Node-Economics` |
| HEAD | `4ce42c30e65f1d70131342b6b3f2a1503d186ded` |
| Separate Task 7.17K work | `efabce1` report/verification; HEAD `4ce42c3` implementation and regression tests |
| Index/worktree, including all untracked files | Completely clean (`git status --porcelain=v1 --untracked-files=all` empty) |
| Tracked K prerequisites | `isolated_bft717k/`, `tests/test_milestone_7_task_7_17k_validator_authority.py`, `verification/bft717k/`, [K report](milestone-7-bft-validator-authority-implementation.md) |
| Tracked I/H prerequisites | [I contract](milestone-7-bft-wire-and-signer-contract.md), `tests/fixtures/bft717j/vectors.json`, `verification/bft717j/oracle.cjs`; `verification/tendermint717h/` model/traces/results and H regression test |
| Instructions | No applicable ancestor/repository/docs `AGENTS.md` found; no delegation |

Read the [authority decision](milestone-7-validator-authority-and-quorum-decision.md),
[wire contract](milestone-7-bft-wire-and-signer-contract.md), K report,
[agreement decision](milestone-7-distributed-finality-protocol-decision.md),
[reviewer-history amendment](milestone-7-v2-reviewer-history-protocol-amendment.md),
[canonical schema](milestone-7-v3-canonical-schema-decision.md) and
[safety/remediation decision](milestone-7-finality-safety-and-remediation-decision.md).
Their historical claims do not upgrade current code or approve launch policy.

Only this new document and a reference/gate update to the authority decision
are deliverables. Verification scripts/data live under ignored `temp/task717l/`;
reproducible recipes and results are included here. No production, isolated
implementation, existing test, vector or schema file changes. No commit,
staging, push, merge or subsequent task. Task 7.17 remains blocked.

## 2. Current genesis, application and recovery audit

Classification: **I** immutable consensus input, **D** deterministic derived
state, **L** local deployment preference, **U** missing authority/decision.

| Subject and inspected source | Evidence, classification and deficiency |
| --- | --- |
| Genesis identity, [protocol_v1_genesis.py](../protocol_v1_genesis.py) | **I**, exact frozen v1 `2b99e87f80e0e855ab98b3269b635be5415273f41d7d4bf1a2aeb8b277b13061`. Payload is domain-enveloped with protocol/network by `canonical_domain_bytes`; SHA-256 covers those bytes, not the portable record's own `hash`. Record normalization maps `meme.text` to `meme_text` and canonical byte tags. This is not a G2 preimage. |
| Genesis media | **I**, frozen 57,343-byte JPEG, SHA-256 `dfba5a7e5e8e5f5da047a2ed58660c9d52665c39f2793da90cba51419f8525c7`; fixed text, timestamp 1785542400 and zero parent. No validator/reviewer/history authority fields in the closed v1 schema. The obsolete media-less v1 root is rejected. |
| Network, [protocol_v1.py](../protocol_v1.py), [config.py](../config.py) | **I** network `zoidberg-public-testnet-v1`, protocol 1. Legacy display alias `zoidberg-testnet` resolves locally. v1 normalization strips/lowercases; proposed G2 received bytes must not be repaired this way. Ports, peer URLs, database paths, node names/HMAC credentials are **L**, never validator authority. |
| Validators, `Blockchain.__init__`, [finality service](../services/finality_service.py) | **L/U**, environment or constructor roster is mutable, normalized/sorted/deduplicated. Live membership uses that roster; historical evidence includes its own roster and threshold. No genesis authorization or membership history. Allocation recipients/miner keys/HMAC peers are not implied validators. |
| Isolated authority, [manifest](../isolated_bft717k/manifest.py), [authority](../isolated_bft717k/authority.py) | Exact I M/C and full-key identity checks exist. Full M/D/synthetic G are independently pinned as test inputs; `genesis_authentication` always reports `INCOMPLETE_AUTHORITY`. Pins do not prove synthetic G contains M/D. No production resolver. |
| Supply/allocations, genesis and [native ledger](../services/native_ledger_service.py) | **I/D**, v1 total 1,000,000,000 ZOID; 100,000,000 reserve; unsigned `GENESIS` allocations 790,000,000 + 100,000,000 + 10,000,000 to three frozen compressed-key recipients. 900,000,000 spendable plus reserve equals supply. These are existing facts, not proposed G2 recipients. Ledger supports legacy identities as well as Wallets; this needs an explicit fresh-network projection, not a guessed address conversion/import. |
| Native transfer context, [transactions](../canonical_v3/transactions.py), [primitives](../canonical_v3/primitives.py) | Inert U10/T18 includes G/type/version; EIP-191 purpose envelope binds N/protocol. Money uses exact six-decimal units, zero fee, positive sequential sender nonce starting at 1, <=10 transfers/block and 98,304-byte aggregate. Aggregate uses ASCII-escaped JSON; genesis commitments use J. Format checks do not execute a ledger. |
| Rewards, [reward service](../services/reward_service.py), [block](../canonical_v3/block.py) | Active creator reward is 5 from reserve, with local reward/access configuration elsewhere. Isolated v3 fixes one five-field unsigned `REWARD_POOL` transfer of `5` to certified creator, zero tip/payload charge, no GENESIS entry, `voter_rewards=[]`. Format validity alone does not prove reserve sufficiency, unique issuance or eligibility. Environment flags/allowlists/wall-clock rewards are **L/U** if used as consensus decisions. |
| Bootstrap, [milestone5_policy.py](../milestone5_policy.py) | Hardcoded established-reviewer list is empty, not authenticated by genesis. Reviewer/reputation policy 1/2; five votes and >=1 established per dimension; epochs from finalized height in groups of five, probation/established quotas 5/25. These versioned constants are consensus-critical when used for validity, not operator preferences. |
| Reviewer authority, [eligibility](../services/reviewer_eligibility_service.py), [reputation](../reviewer_reputation.py) | Canonical finalized activity supports age/qualification (**D**), but locally marked accepted votes drive probation/promotion/quota; SQLite state/history and offense records drive penalties (**U** as independent consensus authority). Status labels, receipt timestamps and signed observations do not prove canonical acceptance or completeness. Offense verifier is still protocol-1-specific. No approved initial numeric reputation allocation exists. |
| Admission, [evidence](../canonical_v3/evidence.py), [history](../canonical_v3/history.py), [atomic store](../canonical_v3/atomic.py) | Technical safety, rights and originality/admissibility remain separate mandatory checks. History access explicitly trusts application acceptance; frozen journal has no active complete v2 implementation. Atomic storage cannot manufacture missing history authority. |
| Peer sync, [peer_chain_sync_service.py](../services/peer_chain_sync_service.py) | Checks network/genesis summaries; fetches full media blocks, certificates and originality evidence. Does not supply complete validator finality/history source inventory. Same-tip early exit can miss proof reconciliation. Peer authentication grants transport access, not consensus authority. |
| Recovery, [storage_tools.py](../storage_tools.py), `Blockchain._validate_persisted_finality_state`, [v3 finality](../canonical_v3/finality.py) | v1 import pins frozen genesis, and local finality durability repairs preserve retained evidence. Neither authenticates its historical roster from genesis. Inert proof checks accept external trusted validators/equivocators; observer exclusions can alter verdicts. SQLite/trust_context/backup metadata are not independent authority. |

Existing trust/circularity hazards are therefore: operator-selected membership;
self-declared historical proof sets; local accepted-vote/status/penalty authority;
local access/time/selection configuration; snapshot/import trust; and the empty
reviewer bootstrap requiring established votes before any media can establish
new reviewers. G-dependent bootstrap signatures, a manifest containing G when G
contains that manifest, a genesis containing its own finalized hash, a policy
containing A when A commits that policy, or a first certificate containing its
own containing block hash would introduce additional cycles. None is retained.
Legacy normalization/defaults must not silently authorize the new profile.

Current active identifiers are protocol1/genesis1, media-admission policy1
(`zoidberg-public-testnet-v1/media-admission/1`, semantic version `1.0.0`),
review policy1/vote2, reviewer policy1/reputation2 and admission certificate1.
The isolated canonical engineering family is protocol2/block3/certificate2/
vote3/review2, native2. Section 5's versions are proposed successors, not values
currently enforced by production. Native supply/reward, admission thresholds,
rights text and codec/resource bounds affect consensus validity; host paths,
URLs, transport credentials, UI labels and operational concurrency do not.
If an access allowlist or daily wall-clock quota is intended to affect consensus,
its full authenticated state/clock rules must be specified first, not imported
from a local preference.

## 3. Canonical primitives and closed proposed G2 representation

“Must” specifies this inactive proposal, subject to section 13 approval. The
outer format is closed; policy-source contents are separately typed dispatch
dependencies, explicitly blocked below. Closing the container cannot substitute
for freezing those contents.

`J` is sorted-key compact JSON, UTF-8, no BOM/newline/whitespace, duplicate keys,
floats/exponents/NaN/infinity, negative zero, invalid Unicode, normalization or
coercion; arrays preserve specified order. UInt is a JSON integer excluding
bool, 0..9,007,199,254,740,991. All G2 strings are printable ASCII; quote and
backslash have standard minimal JSON escapes. Canonical re-encoding must equal
received bytes. Decoded policy source JSON uses the existing Unicode J rules.
Unknown, missing, optional and null fields: **no optional fields; reject all
unknown/missing keys and every null** at each G2-defined level. Source-policy
null/unknown rules require that source's separately approved schema. No source
policy may override the outer G2 types or authorize executable code.

`H64` = 64 lowercase hex without prefix. `Wallet` = `0x` plus 40 lowercase hex.
`Key` = I's validated 33-byte compressed secp256k1 point as 66 lowercase hex.
`NID` = `[a-z0-9][a-z0-9-]{2,63}` exactly. `Application` =
`[A-Za-z0-9][A-Za-z0-9_.-]{2,63}` exactly, retained for native T18's `network`
context; it cannot replace NID. Money is canonical decimal text
`(0|[1-9][0-9]*)(\.[0-9]{0,5}[1-9])?`, <=32 ASCII bytes, no trailing fractional
zero, 0..1,000,000,000 ZOID; parse into integer millionths, never binary float.
Use checked wide integers/BigInt for sums (supply <=10^15 units).

Define `S(b)=lowerhex(SHA256(b))`, `D(x)=S(J(x))`, and the **exact six-key**
envelope `E(purpose,payload,N,version)`:

```text
{domain:"zoidbergchain/"+purpose+"/v"+decimal(version),network_id:N,
 object_type:purpose,payload:payload,protocol:"zoidbergchain",protocol_version:2}
```

Version here selects the domain, never changes protocol_version=2. Only purposes
listed in this contract are permitted; implementations cannot accept arbitrary
purposes as genesis. `genesis` uses domain version 2; bootstrap purposes use 1.

The complete G2 file is exactly `J(E("genesis",P,N,2))`, **not** a portable
`{hash,envelope}` wrapper. External release metadata may carry G but is not part
of genesis. G2 defines `G=S(full_file_bytes)`; no field is removed or normalized.
The record is the exceptional immutable genesis at height zero, not a media
block, a new periodic control block, or a signed native transaction.

P has exactly these **17** fields:

| Field | Type/value/constraint |
| --- | --- |
| genesis_version | UInt exactly 2 |
| index | UInt exactly 0 |
| previous_hash | H64 exactly 64 zeros; not a missing-parent sentinel for later blocks |
| application | Application; approved release value, also policy/native context |
| initial_block_version | UInt exactly 4, candidate reconciled media/history family, not current block3 parser |
| consensus_message_version | UInt exactly 1, I proposal/vote grammar |
| validator_manifest | Full closed M, section 4; network equals envelope N |
| validator_set_commitment | H64 C, exactly D(M) |
| agreement_descriptor | Full closed I descriptor D_ag, with its exact constants/limits and registry digest below |
| agreement_profile_digest | H64 A = D(D_ag) |
| policy_registry | Full closed PR, section 5; no external source URLs |
| policy_registry_digest | H64 PD = D(PR), equals D_ag.application_policy_digest |
| reviewer_bootstrap | Full closed B0, section 6 |
| reviewer_bootstrap_digest | H64 BD = D(E("reviewer-bootstrap",B0,N,1)) |
| native_bootstrap | Full closed N0, section 7 |
| native_bootstrap_digest | H64 ND = D(E("native-bootstrap",N0,N,1)) |
| history_bootstrap | Full closed H0, defined below |

H0 has exactly `history_version,bootstrap_events,bootstrap_history_commitment,
initial_state,initial_state_commitment`. history_version=1; bootstrap_events=[]
is required. No imported signed events, penalties or prehistory are accepted.

```text
HB = {history_version:1,bootstrap_events:[]}
HD = D(E("history-bootstrap",HB,N,1))
S0 = {state_version:1,policy_registry_digest:PD,
      reviewer_bootstrap_digest:BD,native_bootstrap_digest:ND,
      bootstrap_history_commitment:HD}
SC = D(E("initial-state",S0,N,1))
H0 = {history_version:1,bootstrap_events:[],bootstrap_history_commitment:HD,
      initial_state:S0,initial_state_commitment:SC}
```

These are commitments to the clean initial projection, **not** a new Merkle
state tree or proof of later transition correctness. Initial finalized reference
is **derived after G** as `{block_height:0,block_hash:G}` under G2's genesis
exception; it has no Q4 and grants no authority at height 1. This reference is
never inserted back into P/H0/S0. There is no genesis timestamp/launch-clock,
signature, own hash, validator address list, local DB revision or unspecified
extension field. If launch requires genesis media or a wall-clock origin,
that requires a reviewed schema amendment before freezing this proposal.

## 4. Static validator authority and consensus namespace

M is exactly I/K's ten-field object:

```text
{domain:"zoidbergchain/validator-set/v1",membership_version:1,
 protocol:"zoidbergchain",protocol_version:2,network_id:N,
 authority_profile:"static-genesis-v1",validator_epoch:0,
 byzantine_fault_budget:1,required_quorum:3,validator_public_keys:[K0,K1,K2,K3]}
```

Received keys must already be strictly increasing unsigned compressed bytes;
reject duplicate keys **or derived IDs**, malformed/off-curve/infinite keys and
permutations. Authoring may sort unique inputs but must not silently deduplicate.
For decompressed `04||x32||y32`, identity is
`0x||lowerhex(last20(Keccak256(x32||y32)))`; Ethereum Keccak is not FIPS SHA3.
Recover the exact registered point and derived ID from every counted signature.
N is array length=4; f=1, q=3, equal weight. C hashes J(M) with its internal
domain; **no extra prefix, G, salt or delimiter**. N7/f2/q5 from F is not
accepted by this I-compatible profile; using it needs an amended descriptor.

Genesis verification checks full M, C, D_ag/A, network/protocol and every
cross-binding. Only subsequent equality to an independently approved pinned G
authorizes this set. A roster's signatures over itself prove control, not
approval. Pinning M alone cannot bind application policies or genesis.

Static epoch=0 for every historical height. Resolve historic membership from
the same verified G2, never current config, proof-embedded roster, token balance
or peer. Reject mixed/epoch1, wrong G/N/C/A and old versions. I's Q4 has 3..4
distinct ID-sorted matching precommits plus its scheduled signed proposal;
count q once per identity, retain high-S compatibility without added weight.
No observer-dependent equivocator removal, denominator reduction or retroactive
history reclassification. At N4/q3 two quorums overlap in >=2, at least one
honest within f. This arithmetic and cryptographic verification do **not** prove
correct locks/rounds/restarts, application validity or complete BFT safety.

The exact existing I namespace is:

```text
NS(K)={protocol:"zoidbergchain",protocol_version:2,network_id:N,
 genesis_hash:G,agreement_profile_digest:A,validator_epoch:0,
 validator_set_commitment:C,validator_public_key:K,validator_id:ID(K)}
namespace_id=D(NS(K))
```

NS is a signer-store namespace, not an invented new message envelope. I's
EIP-191 sign bytes still bind G/A/C/epoch/N/h/parent/round/step/H. SHA-256 object
IDs are distinct from Keccak256(EIP191-prefix || canonical-message) signing
digests. No signatures/launch keys are generated in this task.

One unavailable validator leaves three potential participants; a second
withholding/offline authority stalls. Timeouts never reduce q. Roster/key
rotation, removal, epoch advances and dynamic elections are unsupported, even
after compromise. Retain conflict evidence and halt on verified incompatible
finality. Recover a failed host only with safe exclusive signer custody and
nonrollbackable state; otherwise stop that signer. Extraordinary new-network
recovery needs separate owner-approved N/G, checkpoint/state-disposition and
retirement procedures. An administrator cannot rewrite the running roster or
reuse the old identity to bypass a halt. Static signatures are not forward
secure: cumulative later compromise of q keys can fabricate old-looking proofs.
Release pins alone cannot distinguish such forged history; archival witnesses/
trusted checkpoint changes require an explicit additional trust decision.

## 5. Policy registry: closed envelope, blocked semantic freeze

PR has exactly `domain,registry_version,network_id,policies`:
domain=`zoidbergchain/application-policy-registry/v1`, registry_version=1,
network_id=N. `policies` contains exactly the following ten entries in increasing
ASCII `policy_kind` order. Each entry has exactly
`policy_kind,policy_version,canonical_bytes`. canonical_bytes is a nonempty
even-length lowercase hex string encoding the **complete canonical J bytes** of
the policy object. Decode, strictly parse, re-encode and validate its registered
closed schema/version before semantic acceptance. Source digest is SHA-256 of
decoded bytes, not the hex text. Encoding as hex bounds and preserves Unicode
source bytes without embedding policy JSON under an incompatible ASCII encoder.

| policy_kind | Candidate policy_version | Source status |
| --- | ---: | --- |
| encoding | 1 | Existing bounded lossless codec profile; reconcile exact source object |
| history | 1 | **BLOCKED**: combined media-only event inclusion/order/completeness and clock |
| issuance | 1 | **BLOCKED**: exact ISSUE/claim permanence and source authority registry |
| media | 2 | Existing two-dimensional media family; full combined registry needs freeze |
| native | 2 | U10/T18, zero fee/reward reserve rules; full state-transition policy source needs freeze |
| reputation | 3 | **BLOCKED**: prospective objective offenses from complete history, not local observations |
| review | 3 | **BLOCKED**: cohort-selection/all-unsure decisions |
| reviewer | 2 | B0 and earned/penalty/quota semantics require approval and full source freeze |
| rights | 1 | Exact statement/ID and context must be frozen for the new network |
| technical | 1 | Deterministic media safety/codec limits and policy bytes must be reconciled |

The table reserves candidate dispatch versions; it does **not** approve the
unwritten inner schemas. G2 semantic authentication returns BLOCKED/incomplete
for an unsupported/unfrozen policy even when the enclosing byte hash matches a
test pin. A raw digest or a version label cannot replace source semantics.
All relevant constants must appear in frozen sources or an immutable versioned
schema they identify, including technical limits, rights text, quorum/threshold,
selection, reviewer age/promotion/quotas/penalties, clock/time checks, native
supply/reward/nonce rules and replay/claims. No local environment may override
them. Policies must contain no resulting G/A/SC, descendant hashes or signatures
whose context needs G. Runtime rules receive G as a verified context parameter.
They also cannot contain their enclosing PD, BD/ND/HD/J0 or any object/result
depending on the source's own digest. Reviewer sources must obtain grants from
the verified B0 at runtime, replacing the legacy hardcoded bootstrap list; they
must not embed a B0 digest that itself hashes those sources. Native sources
obtain allocations from verified N0 rather than importing a local ledger.
Every source's network/application binding, where its schema has one, must match
P/envelope. PD commits full PR; D_ag.application_policy_digest=PD.

B's old HP also contains `finality_policy_digest`. It cannot be populated with
A here: `HP -> PR -> PD -> D_ag -> A -> HP` would be circular. Its old FP
`ceil-two-thirds`/control-history semantics are incompatible with I, even though
the threshold happens to be three for N4. The exact alternatives for the policy
freeze are (a) retain a separately defined G/A-independent finality-policy source
with I's fixed profile constants and verify its consistency with D_ag (requiring
an explicit PR entry/schema amendment to retain its full bytes), or (b)
amend HP's closed field set to remove the old FP reference and use the already
genesis-bound D_ag as the sole agreement authority. Both require an explicit
prelaunch HP/schema amendment and new source vectors; neither is silently
selected. Embedding A/PD into any source in PR is forbidden by this envelope.

Exact remaining decisions: earliest-established-plus-first-fifteen exact set
with disclosed cohort lock, versus a separately specified rolling/replacement
or arbitrary-valid-subset rule; all-unsure stays unresolved (no approval), versus
a separately approved resolution/retry rule. Existing B proposes control blocks
and old FP counting; neither is inherited by this media-only I/Q4 contract.
History source schemas/order/clock and registry bodies must be reconciled after
those choices. Until then there is no complete launch-policy or application
golden vector, despite a fully computable outer G2 preimage.

## 6. Reviewer bootstrap authority and clean initial state

Retain B's **unchanged closed B0**:

```text
{bootstrap_version:1,network_id:N,reviewer_policy_digest:RVP,
 reputation_rule_digest:REP,reviewers:[Wallet,...]}
```

RVP/REP are hashes of decoded reviewer/reputation policy sources in PR, not PD
or resulting G. reviewers is strictly Wallet-sorted, unique, <=128; whole B0
<=8,192 bytes. Reject uppercase, invalid spellings, duplicates, non-Wallets,
unknown/null state or reputation fields and noncanonical arrays. Genesis can
check spelling but cannot prove key control/organizational independence; actual
valid later signatures must prove the claimed signing identity. Prelaunch
proof-of-control/availability checks are operational approval evidence only.

bootstrap_version=1 means underlying `ESTABLISHED_REVIEWER` at height 0 for
each listed Wallet. Numeric reputation allocations are **absent, not caller
defaults**; no inherited score is required for this grant. Offenses, penalties,
participation receipts, quota usage, probation/promotion receipts, native
activity, submission/rights/vote/ISSUE claims all start empty. Qualification age
is not fabricated; the explicit grant bypasses earned promotion only. Unlisted
identities start NEW with no grant and empty history. Quota epoch at genesis is
0 under the proposed finalized-height clock; used=0, limit from approved policy
(B candidate 25 for established, 5 probationary). There is no initial active
penalty and no arbitrary initial offense count. BD commits B0 and these fixed
version-1 clean-bootstrap semantics; SC binds it to the rest of initial state.
Nonempty inherited scores/schedules/usage need a distinct approved import profile
with complete authenticated causes; legacy SQLite is insufficient.

Normal self-vote exclusion and two-dimensional admission remain mandatory:
>=5 distinct eligible noncreator votes per dimension, >=1 established each,
equal weight, decisive denominator positive, integer `100*positive >= 70*decisive`.
Unsure does not enter the decisive denominator; all-unsure cannot certify.
The same five can vote in both dimensions; one Wallet cannot count five times.
Full deterministic source/cohort approval remains BLOCKED. Grants confer no
balance, validator power, immunity or ability to bypass technical/rights checks.
Normal approved penalties mask status prospectively; expiry restores underlying
status, including grants. No discretionary administrator can add grants later.

At least five available noncreator grants are needed for the simplest first
media. Five total grants cannot review their own member's submission unless
another eligible noncreator exists. No actual group is selected here. Distinct
Wallets can share control; overlapping validator/reviewer operators can capture
admission and finality simultaneously. Audit common custody/infrastructure and
creator affiliations, not just key inequality. The existing identity self-vote
rule cannot detect one person using another key; no new Sybil oracle is claimed.
Loss/penalization/exhausted quota of enough reviewers can stop first or later
media. The B control-history rescue path is unavailable without approval; local
registrations/votes cannot establish authoritative replacements during a stall.
The envelope/defaults are specified; full reviewer/bootstrap application
validation remains **BLOCKED** on section 5's policies and section 9 history.

## 7. Native allocation and supply authority

N0 has exactly `native_state_version,network_id,total_supply,
initial_reward_pool,allocations`; version=1, network=N. Supply/pool are Money.
allocations is a Wallet-sorted strictly unique array of <=4,096 closed records
`{wallet_address:Wallet,balance:Money,next_nonce:"1"}`. Each balance is positive;
zero accounts are omitted, implicitly balance 0/next_nonce 1. No signed transfer,
recipient role, legacy compressed-key recipient or arbitrary initial nonce is
accepted here. ND hashes the exact native-bootstrap envelope, section 3.

Sum all balances and pool in integer millionths and require exact equality to
total_supply, nonnegative pool, and all quantities in range. There is no
unallocated/minted-later hidden balance. The reserve is separately accounted,
not a user Wallet or a second allocation. A genesis-only unsigned initialization
creates precisely those balances/reserve and initializes nonces once at h=0;
authority is approved G, not a `GENESIS` string or system signing secret.
No unsigned genesis allocation is accepted at h>=1.

Proposed deterministic representation does not select economic launch values.
The existing supply/reserve/5 ZOID reward are the compatibility baseline; changing
them needs a separate owner-approved economic decision. Selection of actual
recipients and balances is pending. A fresh Wallet-only representation is an
explicit versioned change from v1 compressed-key allocation identities; it
does not translate, confiscate or migrate old balances. Old-state disposition
and approval of this address representation remain launch gates.

From h=1 U10/T18 keeps direct G, N, protocol2, transaction/type/version2,
personal_sign and zero fees; native `network` must equal P.application. Sender
signature, distinct recipient, positive amount, exact next sequential nonce,
sufficient balance and transaction IDs/aggregate order must verify. Successful
inclusion consumes exactly that nonce; a local reservation does not. Never
accept legacy signatures through a fallback. v3's exact ASCII aggregate remains
separate from J envelope hashing. Replay order must match the final combined
block transition contract; unresolved interactions cannot be guessed by a node.

One accepted canonical media gives exactly one creator reward of 5 from reserve
under the current candidate, to certified creator, with zero tip/payload charge
and no proposer bonus/voter rewards. Require certificate/rights/claims, unique
submission/content issuance and reserve sufficiency; supply is conserved as
reserve decreases by reward and creator balance increases. No administrator
mint/REWARD_POOL debit bypass or arbitrary system transaction. Exhaustion when
remaining reserve<5 requires an explicit policy decision: current mandatory-5
projection stalls that candidate, or separately approve a versioned post-reserve
reward rule. This task selects neither a new reward nor inflation. A future
native policy must fix within-block reward/transfer ordering and exhaustion
semantics before complete replay can pass.

## 8. Noncircular dependencies and authenticated release pin

The exact calculation order is:

```text
approved N/application + policy source bodies + existing test/approved keys
  -> PR -> PD -> full I D_ag(PD) -> A
  -> source hashes RVP/REP -> B0 -> BD
  -> N0 -> ND
N + keys -> M -> C
N + empty bootstrap event list -> HB -> HD
PD + BD + ND + HD -> S0 -> SC -> H0
N/application + M/C + D_ag/A + PR/PD + B0/BD + N0/ND + H0 -> P
P + fixed six-field genesis envelope -> canonical G2 bytes -> G
G -> initial finalized ref (0,G); G + history-policy digest + BD -> J0
G + N/application -> native signing context
G + A + C + N + epoch0 + validator K/ID -> NS -> signer namespace ID
verified parent/state + complete media/native/certificate/events -> block H
G/A/C/N/H/parent/h/round/step -> I proposal/votes -> PV/Q4
```

J0 is B's post-genesis journal seed **only if** the reconciled history policy
adopts that journal: `D({domain:"zoidbergchain/reviewer-journal-genesis/v1",
protocol_version:2,network_id:N,genesis_hash:G,history_policy_digest:HP,
bootstrap_digest:BD})`, HP=hash(decoded history source). J0 is not written into
G2 and does not approve events, completeness or control blocks. A future changed
seed definition needs a new version; no partial-G or zero-G substitution.

Four different operations must not be confused: hash M to get C; embed full
M/C in G2 and recompute G; check structural/semantic G2 consistency; authenticate
G against an independently approved trust root. Only the last provides network
authorization. A malicious peer can replace every source/roster and recompute
all commitments; it still fails an honest node's pin.

Concrete proposed pin procedure (no new signing key or online enrollment):

1. Owner approves the exact reviewed genesis file and its lowercase G after
   independent offline recomputation, plus expected N/protocol/application/profile.
2. Operator obtains that tuple directly from the owner via an already authenticated
   out-of-band channel, verifies the owner's identity through that channel, and
   records G/N/profile locally in a read-only startup trust configuration. A
   version-controlled reviewed distribution may carry the same tuple only if its
   release provenance is authenticated independently of discovered peers.
3. Node requires an explicit pin before enabling this network. It never creates
   a pin from a peer, SQLite, first response, self-signature or matching majority
   of URLs. Fetch genesis from any source, bound its size, verify bytes and every
   cross-binding, then constant-equality compare computed G and N/profile to pin.
4. Wrong/missing pin refuses network authority; unknown policy/version remains
   unsupported/incomplete despite matching bytes. A config override cannot lower
   the rules. Pin changes require explicit owner-approved new-network/recovery
   review, not auto-update, TOFU or current validators signing their own replacement.

This chooses a precise manual authenticated-pin contract for review. The actual
owner channel, approved artifact, operators, N, application and G remain pending;
no existing authenticated release infrastructure is claimed implemented. A signed
release alternative needs separately pinned release keys/format/revocation and
rollback rules, and is not authorized by a downloaded public key in that release.
NID must never be reused across genesis roots: some retained rights-signature
contexts bind N without directly binding G. A new G with reused N could replay
those signatures even though native/BFT signatures directly bind G. Reject such
a release plan; approval must select a fresh network identifier as well as G.

## 9. Independent recovery and history completeness contract

Required archive: approved G2/full policy sources, every canonical media record
with original recoverable bytes, complete approved application events and
source records, all required Q4/authority bindings and retained contradictions.
An ID/root/certificate is not a substitute for source availability. Rebuildable
indexes include balances/nonces, reviewer status, penalties/quotas/participation,
claim tables, media lookups, peer cursors and SQLite row IDs. Private signer
reservations/locks/custody are a separate non-rebuildable safety obligation.

Fresh-node algorithm, conditional on the missing history/schema freeze:

1. Require the independently approved G/N/profile pin; load bounded canonical
   G2, recompute all source digests, PD, C/A, BD/ND/HD/SC and G; reject malformed
   or contradictory bytes. Require supported policy semantics, not merely hashes.
2. Resolve full M/epoch0 and decode N0/B0 into the exact clean projection. Compare
   SC; derive finalized `(0,G)`, empty claims and optional approved J0. No SQLite
   row or peer-provided established/accepted flag can change this state.
3. For each h=1..claimed target, obtain complete canonical block bytes, originals,
   application event inventory and required proofs. Require contiguous h and
   exact previous finalized hash (G for h1). Decode original media byte-for-byte,
   check SHA/size/codec/technical safety, rights, admission, native ledger and
   every source dependency under the exact combined profile.
4. Derive reviewer eligibility/quotas/selection/penalties at the authenticated
   parent and apply same-block ordered events only as approved. Later offenses
   must not retroactively rewrite finalized certificates. Verify signed inputs,
   canonical acceptance/rejection, replay ownership and ISSUE uniqueness. Missing
   rejected/unminted/other-target quota sources means **INCOMPLETE_HISTORY**, never
   zero usage/offenses. Off-chain signatures prove authorship, not inclusion.
5. Verify Q4 scheduled proposal and >=3 unique exact-key epoch0 precommits for
   G/N/A/C/h/parent/round/H using I/K grammar, plus complete block validity and
   finalized ancestry. No peer roster or local equivocator adjustment. Historical
   Q4 crypto success alone is not full-finality success. Distinct valid QCs for
   the same target are equivalent evidence; incompatible targets retain both,
   report conflict and halt rather than choose by originality score/arrival time.
6. Commit verified sources, cursor, application transition and derived indexes
   atomically, publishing after durable success. On crash recover the old or new
   complete verified prefix; partial writes cannot create accepted transitions.
   Missing source/proof refetches or stops at last complete prefix. Sync must
   reconcile proof/source inventories even when tips match.
7. Snapshot imports are accelerators only: bind exact G/N/profile versions,
   h/hash, policy digests and replay/journal commitment; rederive from verified
   sources or a locally already fully verified prefix and compare state. Without
   an approved authenticated state-root/snapshot proof protocol, a remote
   snapshot's own digest/QC is not proof of its balances/status/absence of events.
   Wrong G/version/hash rejects; stale prefix cannot roll back retained finalized
   anchors. Rebuild corrupted indexes from archive; missing archive stays incomplete.
8. A coherent but old prefix is detectable as stale only relative to a retained
   verified newer anchor or authenticated newer target. G alone cannot prove the
   freshest height under isolation/eclipse. Do not invent a wall-clock freshness
   guarantee. New validators additionally need safe private signer recovery;
   replaying public chain data cannot prove no hidden past signatures existed.

**Exact next dependency:** freeze the combined block4 MEDIA schema and hash
preimage, event source inventory (REGISTER/VOTE/ISSUE plus authenticated
objective-offense causes), deterministic order/inclusion and duplicate rules,
cohort/all-unsure policy, penalty/quota clock and native/reward ordering. Reconcile
B's old FP/control-history assumptions with I's immediate-finalized-parent Q4
and media-only constraint; produce complete independent replay vectors. No
reviewer-history event journal is implemented or approved here. Until this is
done, steps 3–8 cannot claim complete independent application recovery.

## 10. One-media-per-block, idle periods and deadlocks

G2's proposed height-zero administrative exception requires owner approval,
especially because current v1 contains a meme. At every later height exactly
one accepted media submission is required; retain the 3 MiB complete MEDIA-BLOCK
cap. No empty media, dummy accepted media, native-only/control block or separate
authoritative event chain is introduced. B's idle control-block proposal is
explicitly not adopted by this document.

| Situation | Progress/authority under the constrained proposal |
| --- | --- |
| No accepted media | Genesis remains finalized anchor, or current finalized tip stays fixed. No next canonical event or height/epoch advance. Wall time/round timers may pass but create no application history. |
| Pending registration/rights | A relay can verify/queue signed drafts locally. Registration/claims become authoritative only through a future approved valid canonical event. Pending status is not consensus participation. |
| New reviewer/promotion | Local eligibility can be projected from existing authenticated prefix; new participation/promotion causes need canonical inclusion. No height-age/epoch advancement without media. Cannot use the resulting same-block promotion to supply its own missing parent-established seat. |
| Offense detected | Retain signed evidence and refuse local relay if appropriate. Global penalty/quota effect waits for approved canonical inclusion/clock. No retroactive mutation or local blacklist denominator change. Evidence inclusion/censorship remains a history-policy gate. |
| Validator disappears | N/q/epoch unchanged. Three compatible validators may progress with valid media; two cannot. No emergency unilateral roster rewrite. |
| Policy/quota boundary | Epoch derives from finalized height, not wall time or BFT round. Reaching the next height requires valid media under the approved parent policy; exhausted quotas/penalized grants can deadlock that transition. Policies are immutable in this static profile; no implicit policy epoch upgrade. |

Bootstrap shortage, all-unsure/negative fixed cohort, total reviewer unavailability,
quota exhaustion, penalties, reserve exhaustion or validator loss can stall.
Native transfers also wait for media inclusion; funded users cannot rely on an
idle native-only route to earn established status. Choices are explicitly accept
these media-only limits, or separately approve a control-history/clock/economic
amendment; neither is solved by inserting new records here. Local pending or
wall-clock changes are never consensus authority while waiting.

## 11. Byte-level examples and independent checks

Appendices supply exact full canonical preimages and expected SHA-256 values.
All identities/keys are **reused public insecure I fixtures**, not new operators
or launch credentials. The native zero-supply/empty-allocation case tests encoding
and conservation only; it selects no launch economics. The two-reviewer list is
below first-media capacity. Every policy source is test-only `{}` (hex `7b7d`),
which fails the required semantic policy schemas. Thus the complete G2 object
is an **outer-envelope/commitment vector**, not a positive launch or application
golden vector. It must never receive a full genesis-authentication PASS.

Negative cases use the exact mutations in Appendix C. Rehashing altered bytes
does not confer approval; two layers of rejection are distinguished: internal
cross-binding/schema failure and mismatch to the unchanged externally pinned G.
State reconstruction here verifies only the defined clean genesis projection;
no journal/reviewer transition or complete application finality is claimed.

## 12. Size, resources and economics

Propose a **separate 1,048,576-byte complete canonical G2 cap**, rather than B's
provisional 3 MiB genesis ceiling. It is an explicitly unapproved versioned
amendment for an administrative genesis with no media/imported history. The
MEDIA-BLOCK cap remains 3,145,728 bytes; unused genesis space grants no media
capacity and genesis bytes are not per-media overhead.

| Component | Proposed cap / accounting |
| --- | --- |
| Complete G2 | 1,048,576 bytes, pre-scan before parsing |
| M / D_ag | Existing I 8,192 / 4,096 bytes; N4 M actual maximum 603, D_ag 892 |
| Full PR | 65,536 J bytes total, ten entries, <=8,192 decoded bytes/source (<=16,384 hex characters); all sources still share the total cap |
| B0 | <=128 reviewers, <=8,192 bytes; sorted Wallet strings cost 45 bytes each plus fixed wrapper |
| N0 | <=4,096 allocations, <=786,432 bytes; <=32-byte Money; each record <=132 bytes under field widths, giving <541 KiB plus fixed wrapper |
| H0 and all remaining envelope/scalars/delimiters | <=16,384 bytes jointly, measured as G2 length minus J(M), J(D_ag), J(PR), J(B0), J(N0); includes embedded commitments, application, wrapper and every residual delimiter |
| Nesting | <=32 containers, using I/canonical parser depth convention |
| Total component budgets | 8,192+4,096+65,536+8,192+786,432+16,384 = 888,832 bytes, below the independent global cap |
| Post-genesis Q4/PV | I parsing ceilings 16,384/12,288; K maximum-width actual Q4 q3/q4 4,632/5,632, four/five signature recoveries including proposal |

Bounds apply simultaneously, not as permission to exceed a tighter component
or global limit. Decode at most limit+1 bytes from streams; validate lengths,
counts/depth/duplicate keys and source hex before curve/crypto work. Genesis
has four point checks/identity derivations, hashes and bounded linear state
initialization, no validator-signature quorum or code execution. Source-policy
semantic validation also needs approved bounded schemas. Hex doubles policy
source bytes; it is deliberate bounded transparency, not compression evidence.
Full policy-source fit is unmeasured and remains a freeze gate: if all required
bodies cannot fit the registry budget, revise the versioned caps explicitly;
never omit rules or replace bodies with trusted local configuration to fit.

Bootstrap traffic is full genesis once plus `sum(block_bytes + proof_bytes +
required external source_bytes)` through target, plus retries/transport. Replay
is O(retained bytes + accepted events + transfers + signature verifications),
with indexes for duplicate/claim checks; a naive full-prefix rescan per block
would be quadratic and is not a required algorithm. No measured replay CPU or
launch throughput is claimed. At the Q4 ceiling, one million media decisions
need <=16.384 GB additional canonical Q4 bytes, excluding media/events/SQLite,
and up to five signature recoveries per retained proof. This is an arithmetic
upper allowance, not observed disk growth. Genesis <1 MiB cannot resolve the
permanent MODEL A archival growth: originals, event sources, proofs, indexes,
copies/backups and peer bandwidth accumulate. No pruning authority, storage
price, token value or revised native economics is implied.

## 13. Version amendments and owner decisions

| Versioned proposal | Exact compatibility boundary / approval required |
| --- | --- |
| G2 genesis schema/domain | New genesis_version2, protocol2 six-field envelope, SHA-256 of entire canonical file; no v1 normalization/record-hash reuse. Approve administrative height-zero exception, application field, 1 MiB cap and Wallet allocation representation. |
| I M/D/NS and Q4 | Reuse byte grammars unchanged, membership1/agreement1/message1/epoch0/Q4 proof4. N4/f1/q3 and static permissioned model still need owner approval. Do not revive F's A3/Q3 or B's old FP semantics. |
| Registry/bootstrap commitments | New closed PR1, native-state1, history-bootstrap1/initial-state1; unchanged B0 version1/domain. These are prelaunch proposals never implemented, not silent additions to deployed v1. Approve exact bytes/types/caps and freeze inner policy bodies before production acceptance. |
| B history-genesis integration | Replace its proposed seven-field reviewer_history_genesis and Wallet-only validator list with P's M/C, D_ag/A, PR/PD, B0/BD and H0 fields. Do not accept both layouts under G2. Replace provisional genesis cap explicitly. J0 remains post-G and conditional; control blocks/old FP are not inherited. |
| Application versions | Candidate block4/certificate3/vote4/review3/reviewer2/reputation3/history1, native2, technical/rights/encoding1. Combined block4 payload/hash and policy schemas remain BLOCKED; current block3 is an archived laboratory profile. This task does not assign a new block hash field or activate that candidate. |
| Deployment/legacy disposition | Choose actual N/application/G, operator/key independence/custody, reviewers, allocations/reserve and authenticated distribution; approve old-state treatment and activation separately. No launch values, migration/reset or retrospective upgrade of old trust-based finality. |

Owner/security review must also approve cumulative key-compromise assumptions,
static halt/emergency tradeoff, quorum topology, media-only idle limits versus
a distinct future control-history proposal, cohort/all-unsure alternatives,
objective offense/inclusion/penalty/clock rules, issuance permanence, reward
exhaustion and ordering, local relay-control versus consensus policy boundary,
full recovery/source retention and signer fencing/power-loss operating profile.
Unresolved source semantics are protocol blockers; selecting actual recipients,
operators and amounts is a separate deployment-value gate. Neither is solved by
test fixtures. No subsequent task is started by this recommendation.

## 14. Implementation-readiness matrix and smallest next task

PASS below is explicitly scoped evidence, not approval or production readiness.

| Gate | Status | Evidence and remaining condition |
| --- | --- | --- |
| A. Validator manifest canonicalization | **PASS — isolated N4 subset** | I/K ten-field canonical M, curve/order/ID and exact SHA-256 checks already implemented; unchanged regression and independent fixture checks. Permissioned launch/operator approval pending. |
| B. G2 genesis serialization | **PARTIAL** | Closed outer representation, exact dependency graph/caps and cross-language byte vectors here. No parser implementation, approved complete inner policy schemas or complete application golden package. |
| C. G2 genesis authentication | **PARTIAL** | Noncircular full-byte commitment and exact external pin procedure specified. Test pins are not approved releases; K still returns INCOMPLETE_AUTHORITY. Semantic policy freeze, authenticated launch artifact and implementation absent. |
| D. Application bootstrap validation | **BLOCKED** | Clean B0/N0/S0 envelope/defaults specified; policy sources, reviewer choices, economic compatibility/ordering and launch values are not approved. |
| E. Fresh-node authenticated recovery | **BLOCKED** | Algorithm/source requirements specified; full combined history schema, complete event authority, proof/source sync and replay absent. SQLite/source-only fixtures cannot close it. |
| F. Production validator deployment | **BLOCKED** | Model/I/K subsets do not supply engine/signer refinement, safe custody, adversarial multi-host verification, operator approval or activation. |
| G. Reviewer-history Task 7.17 resumption | **BLOCKED** | Requires finality foundation plus approved selection/admission/history/clock/issuance policies and independent replay vectors. No journal implementation authorized. |

Smallest safe next implementation task, **only after separate instruction and
approval of this outer schema**: an inert bounded G2 envelope/commitment verifier
using reused public fixture identities. Verify closed structure, every source
hash/cross-binding and explicit external test pin; return separate structural,
pin-match and policy-semantic outcomes, preserving INCOMPLETE_AUTHORITY for
unapproved/unsupported policy bodies. Test self-consistent foreign genesis,
duplicate/malformed fields, size limits, cycles and wrong pin; no production
loader, signer/engine integration or automatic K authority upgrade. If complete
application authentication is required next, the prerequisite is a narrowly
scoped policy/combined-history specification decision first. Task 7.17M is not
started or assigned here.

## 15. Executed verification and final repository state

Results and exact recipes follow in the appendices. Verification establishes
byte arithmetic and preserved isolated behavior; it does not establish owner
approval, semantic bootstrap validity, full recovery or distributed BFT safety.


Executed on Windows with CPython 3.13.5 and Node.js v22.17.0:

- Unchanged K authority and H model suites: **155 passed in 8.34 s**, no
  failures/errors/skips (`temp/task717l/regression.xml`).
- I frozen signing/proof/JavaScript oracle regression: **27 passed, 98 deselected
  in 16.71 s**, no failures/errors/skips (`temp/task717l/wire.xml`); original
  fixture/oracle unchanged. Together with K/H, **182 existing cases passed**.
- Independent Python/JavaScript construction: **12 canonical objects**, exact
  bytes/lengths/SHA-256 agree; **10 mutated inputs** have independently matching
  bytes/lengths/SHA-256, all differing from the pinned base G.
- Focused scratch diagnostics using existing strict JSON, M and I Context:
  10 mutation/pin cases, four lexical rejection cases and two epoch-type cases
  pass. A self-consistent foreign application passes the fixture's internal
  checks and still fails the external pin. All `{}` policy sources remain
  semantically BLOCKED. This is not a complete new G2 parser test suite.
- Recomputed the unchanged v1 frozen genesis hash from actual payload/media:
  section 2's hash, 57,343 media bytes and allocations+reserve=1,000,000,000
  all match; no chain database was opened.

Final branch/HEAD equal section 1. Index unchanged/empty; final worktree has
exactly the new untracked contract and the unstaged authority-decision link/gate
addition. Only those two documentation paths are deliverables. Ignored scratch
files are not launch artifacts. UTF-8/no BOM, final newline, whitespace, local
links, all literal preimages/hash tables and extracted reproduction recipes
passed verification. The original authority-decision body is byte-equivalent
after removing its 14-line follow-up (ignoring checkout line endings).
`git diff --check` passes. Documentation is ready
for review and a later owner-performed commit as an explicitly partial proposal.

## Appendix A. Literal canonical preimages and expected SHA-256

Every fenced JSON line is the complete hash preimage, without the fence or
newline. Lengths count UTF-8 bytes. B0/N0/N1/HB/S0 row names denote their
**domain envelopes**; PR/M/DA/NS/J0 are hashed directly. G2 is the full genesis
file, and its row's hash is the test genesis identity G. `rebuilt` is only a
diagnostic projection, not an additional consensus object/state hash. Empty
omitted diagnostic fields are governed by section 6's clean-state rules.
N1 is a separate standalone allocation-encoding fixture using an existing
public test Wallet, illustrative balance `1`, no launch allocation and no
effect on the full zero-supply G2 fixture. It also satisfies conservation.

| Preimage | Bytes | Expected SHA-256 |
| --- | ---: | --- |
| B0 | 511 | `42064d0346197420df9ef6b35d3769bba0ca933e95c54e59fbb6f5994553bb94` |
| DA | 892 | `2ca3a90d2d1d7bb9535da7d201981e1fb44613633a76f4a6433390b4b82a3c9b` |
| G2 | 4318 | `0b1b932a7d6cfb0fed6cec2019724b0b0bf6ab13b0516e8d60d63ddbfa25ee94` |
| HB | 212 | `e520ea6baf1db8caf4de876c68c0376834a27944c2d3f44c7d545fbf190132c9` |
| J0 | 363 | `5b6b9bf604f3e2ea7196b1fabf2260fa3a9447e1ea044066dbd849d29d623884` |
| M | 552 | `6fb37df7e489c39287ea827d08f32467f84116d1e8758304d86672a6fd935518` |
| N0 | 284 | `0b517284e1d7b2bbf34ef28401eeac545751b6a1a7be057acf712a37aca56518` |
| N1 | 378 | `1e2e98b4e0495796e1142f94492ece6385723cf2bf00838c325984d148857fa9` |
| NS | 520 | `a78428636e2eff7fc6c83d3d8619606922374e28390d0ca0832dbef86539cc6d` |
| PR | 823 | `87a9dad4d24b200ecfc1033e9e182aee1813a3ab771e6c8382099308f70624ca` |
| S0 | 558 | `e2c758c1d42dc7c6a975a07e907b7ed96798fb4b3d24da21f1150db573eafcb6` |
| rebuilt | 466 | `fbf7d2331e3e4da4fac95482b7c9885612d21d40a5b7688f47aa2770321a233c` |

### B0

```json
{"domain":"zoidbergchain/reviewer-bootstrap/v1","network_id":"task717i-test","object_type":"reviewer-bootstrap","payload":{"bootstrap_version":1,"network_id":"task717i-test","reputation_rule_digest":"44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a","reviewer_policy_digest":"44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a","reviewers":["0x2b5ad5c4795c026514f8317c7a215e218dccd6cf","0x7e5f4552091a69125d5dfcb7b8c2659029395bdf"]},"protocol":"zoidbergchain","protocol_version":2}
```

### DA

```json
{"agreement_version":1,"application_policy_digest":"87a9dad4d24b200ecfc1033e9e182aee1813a3ab771e6c8382099308f70624ca","authority_profile":"static-genesis-n4-f1-q3-v1","domain":"zoidbergchain/bft-agreement/v1","limits":{"agreement_bytes":4096,"block_bytes":3145728,"commit_proof_bytes":16384,"envelope_bytes":2048,"manifest_bytes":8192,"max_depth":32,"max_round":2147483647,"max_uint":9007199254740991,"prevote_certificate_bytes":12288,"proposal_bundle_bytes":3160400,"round_evidence_bytes":8192,"signed_bytes":2304},"parent_profile":"immediate-finalized-v1","proposer_profile":"height-minus-one-plus-round-mod-four-v1","protocol":"zoidbergchain","protocol_version":2,"reference":"arxiv:1807.04938v3/Algorithm1","rule_selection":"printed-lines-1-67","signer_profile":"reserve-sign-store-release-v1","timeout_profile":"linear-1000ms-plus-1000ms-per-round-v1","wire_profile":"bft-ascii-json-v1"}
```

### G2

```json
{"domain":"zoidbergchain/genesis/v2","network_id":"task717i-test","object_type":"genesis","payload":{"agreement_descriptor":{"agreement_version":1,"application_policy_digest":"87a9dad4d24b200ecfc1033e9e182aee1813a3ab771e6c8382099308f70624ca","authority_profile":"static-genesis-n4-f1-q3-v1","domain":"zoidbergchain/bft-agreement/v1","limits":{"agreement_bytes":4096,"block_bytes":3145728,"commit_proof_bytes":16384,"envelope_bytes":2048,"manifest_bytes":8192,"max_depth":32,"max_round":2147483647,"max_uint":9007199254740991,"prevote_certificate_bytes":12288,"proposal_bundle_bytes":3160400,"round_evidence_bytes":8192,"signed_bytes":2304},"parent_profile":"immediate-finalized-v1","proposer_profile":"height-minus-one-plus-round-mod-four-v1","protocol":"zoidbergchain","protocol_version":2,"reference":"arxiv:1807.04938v3/Algorithm1","rule_selection":"printed-lines-1-67","signer_profile":"reserve-sign-store-release-v1","timeout_profile":"linear-1000ms-plus-1000ms-per-round-v1","wire_profile":"bft-ascii-json-v1"},"agreement_profile_digest":"2ca3a90d2d1d7bb9535da7d201981e1fb44613633a76f4a6433390b4b82a3c9b","application":"task717i-test","consensus_message_version":1,"genesis_version":2,"history_bootstrap":{"bootstrap_events":[],"bootstrap_history_commitment":"e520ea6baf1db8caf4de876c68c0376834a27944c2d3f44c7d545fbf190132c9","history_version":1,"initial_state":{"bootstrap_history_commitment":"e520ea6baf1db8caf4de876c68c0376834a27944c2d3f44c7d545fbf190132c9","native_bootstrap_digest":"0b517284e1d7b2bbf34ef28401eeac545751b6a1a7be057acf712a37aca56518","policy_registry_digest":"87a9dad4d24b200ecfc1033e9e182aee1813a3ab771e6c8382099308f70624ca","reviewer_bootstrap_digest":"42064d0346197420df9ef6b35d3769bba0ca933e95c54e59fbb6f5994553bb94","state_version":1},"initial_state_commitment":"e2c758c1d42dc7c6a975a07e907b7ed96798fb4b3d24da21f1150db573eafcb6"},"index":0,"initial_block_version":4,"native_bootstrap":{"allocations":[],"initial_reward_pool":"0","native_state_version":1,"network_id":"task717i-test","total_supply":"0"},"native_bootstrap_digest":"0b517284e1d7b2bbf34ef28401eeac545751b6a1a7be057acf712a37aca56518","policy_registry":{"domain":"zoidbergchain/application-policy-registry/v1","network_id":"task717i-test","policies":[{"canonical_bytes":"7b7d","policy_kind":"encoding","policy_version":1},{"canonical_bytes":"7b7d","policy_kind":"history","policy_version":1},{"canonical_bytes":"7b7d","policy_kind":"issuance","policy_version":1},{"canonical_bytes":"7b7d","policy_kind":"media","policy_version":2},{"canonical_bytes":"7b7d","policy_kind":"native","policy_version":2},{"canonical_bytes":"7b7d","policy_kind":"reputation","policy_version":3},{"canonical_bytes":"7b7d","policy_kind":"review","policy_version":3},{"canonical_bytes":"7b7d","policy_kind":"reviewer","policy_version":2},{"canonical_bytes":"7b7d","policy_kind":"rights","policy_version":1},{"canonical_bytes":"7b7d","policy_kind":"technical","policy_version":1}],"registry_version":1},"policy_registry_digest":"87a9dad4d24b200ecfc1033e9e182aee1813a3ab771e6c8382099308f70624ca","previous_hash":"0000000000000000000000000000000000000000000000000000000000000000","reviewer_bootstrap":{"bootstrap_version":1,"network_id":"task717i-test","reputation_rule_digest":"44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a","reviewer_policy_digest":"44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a","reviewers":["0x2b5ad5c4795c026514f8317c7a215e218dccd6cf","0x7e5f4552091a69125d5dfcb7b8c2659029395bdf"]},"reviewer_bootstrap_digest":"42064d0346197420df9ef6b35d3769bba0ca933e95c54e59fbb6f5994553bb94","validator_manifest":{"authority_profile":"static-genesis-v1","byzantine_fault_budget":1,"domain":"zoidbergchain/validator-set/v1","membership_version":1,"network_id":"task717i-test","protocol":"zoidbergchain","protocol_version":2,"required_quorum":3,"validator_epoch":0,"validator_public_keys":["0279be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798","02c6047f9441ed7d6d3045406e95c07cd85c778e4b8cef3ca7abac09b95c709ee5","02e493dbf1c10d80f3581e4904930b1404cc6c13900ee0758474fa94abe8c4cd13","02f9308a019258c31049344f85f89d5229b531c845836f99b08601f113bce036f9"]},"validator_set_commitment":"6fb37df7e489c39287ea827d08f32467f84116d1e8758304d86672a6fd935518"},"protocol":"zoidbergchain","protocol_version":2}
```

### HB

```json
{"domain":"zoidbergchain/history-bootstrap/v1","network_id":"task717i-test","object_type":"history-bootstrap","payload":{"bootstrap_events":[],"history_version":1},"protocol":"zoidbergchain","protocol_version":2}
```

### J0

```json
{"bootstrap_digest":"42064d0346197420df9ef6b35d3769bba0ca933e95c54e59fbb6f5994553bb94","domain":"zoidbergchain/reviewer-journal-genesis/v1","genesis_hash":"0b1b932a7d6cfb0fed6cec2019724b0b0bf6ab13b0516e8d60d63ddbfa25ee94","history_policy_digest":"44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a","network_id":"task717i-test","protocol_version":2}
```

### M

```json
{"authority_profile":"static-genesis-v1","byzantine_fault_budget":1,"domain":"zoidbergchain/validator-set/v1","membership_version":1,"network_id":"task717i-test","protocol":"zoidbergchain","protocol_version":2,"required_quorum":3,"validator_epoch":0,"validator_public_keys":["0279be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798","02c6047f9441ed7d6d3045406e95c07cd85c778e4b8cef3ca7abac09b95c709ee5","02e493dbf1c10d80f3581e4904930b1404cc6c13900ee0758474fa94abe8c4cd13","02f9308a019258c31049344f85f89d5229b531c845836f99b08601f113bce036f9"]}
```

### N0

```json
{"domain":"zoidbergchain/native-bootstrap/v1","network_id":"task717i-test","object_type":"native-bootstrap","payload":{"allocations":[],"initial_reward_pool":"0","native_state_version":1,"network_id":"task717i-test","total_supply":"0"},"protocol":"zoidbergchain","protocol_version":2}
```

### N1

```json
{"domain":"zoidbergchain/native-bootstrap/v1","network_id":"task717i-test","object_type":"native-bootstrap","payload":{"allocations":[{"balance":"1","next_nonce":"1","wallet_address":"0x7e5f4552091a69125d5dfcb7b8c2659029395bdf"}],"initial_reward_pool":"0","native_state_version":1,"network_id":"task717i-test","total_supply":"1"},"protocol":"zoidbergchain","protocol_version":2}
```

### NS

```json
{"agreement_profile_digest":"2ca3a90d2d1d7bb9535da7d201981e1fb44613633a76f4a6433390b4b82a3c9b","genesis_hash":"0b1b932a7d6cfb0fed6cec2019724b0b0bf6ab13b0516e8d60d63ddbfa25ee94","network_id":"task717i-test","protocol":"zoidbergchain","protocol_version":2,"validator_epoch":0,"validator_id":"0x7e5f4552091a69125d5dfcb7b8c2659029395bdf","validator_public_key":"0279be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798","validator_set_commitment":"6fb37df7e489c39287ea827d08f32467f84116d1e8758304d86672a6fd935518"}
```

### PR

```json
{"domain":"zoidbergchain/application-policy-registry/v1","network_id":"task717i-test","policies":[{"canonical_bytes":"7b7d","policy_kind":"encoding","policy_version":1},{"canonical_bytes":"7b7d","policy_kind":"history","policy_version":1},{"canonical_bytes":"7b7d","policy_kind":"issuance","policy_version":1},{"canonical_bytes":"7b7d","policy_kind":"media","policy_version":2},{"canonical_bytes":"7b7d","policy_kind":"native","policy_version":2},{"canonical_bytes":"7b7d","policy_kind":"reputation","policy_version":3},{"canonical_bytes":"7b7d","policy_kind":"review","policy_version":3},{"canonical_bytes":"7b7d","policy_kind":"reviewer","policy_version":2},{"canonical_bytes":"7b7d","policy_kind":"rights","policy_version":1},{"canonical_bytes":"7b7d","policy_kind":"technical","policy_version":1}],"registry_version":1}
```

### S0

```json
{"domain":"zoidbergchain/initial-state/v1","network_id":"task717i-test","object_type":"initial-state","payload":{"bootstrap_history_commitment":"e520ea6baf1db8caf4de876c68c0376834a27944c2d3f44c7d545fbf190132c9","native_bootstrap_digest":"0b517284e1d7b2bbf34ef28401eeac545751b6a1a7be057acf712a37aca56518","policy_registry_digest":"87a9dad4d24b200ecfc1033e9e182aee1813a3ab771e6c8382099308f70624ca","reviewer_bootstrap_digest":"42064d0346197420df9ef6b35d3769bba0ca933e95c54e59fbb6f5994553bb94","state_version":1},"protocol":"zoidbergchain","protocol_version":2}
```

### rebuilt

```json
{"accounts":[],"claims":[],"finalized_ref":{"block_hash":"0b1b932a7d6cfb0fed6cec2019724b0b0bf6ab13b0516e8d60d63ddbfa25ee94","block_height":0},"offenses":[],"participation":[],"penalties":[],"reviewers":[{"quota_used":0,"underlying_status":"ESTABLISHED_REVIEWER","wallet_address":"0x2b5ad5c4795c026514f8317c7a215e218dccd6cf"},{"quota_used":0,"underlying_status":"ESTABLISHED_REVIEWER","wallet_address":"0x7e5f4552091a69125d5dfcb7b8c2659029395bdf"}],"reward_pool":"0"}
```

## Appendix B. Reproduction recipes

Save the next two tagged blocks as `temp/task717l/vectors.py` and
`temp/task717l/vectors.cjs`. The Python program constructs its own objects and
emits a JSON record; the JavaScript program independently reconstructs every
object/mutation (with deliberately different object insertion order) and compares
the Python record. Neither reads a production store or generates/signs keys.
These are fixture constructors, not general untrusted-input parsers.

```powershell
.\.venv\Scripts\python.exe -B temp/task717l/vectors.py | Set-Content -Encoding utf8 temp/task717l/vectors.json
node temp/task717l/vectors.cjs temp/task717l/vectors.json
```

```python task717l-python
"""Offline envelope arithmetic only; deliberately invalid application policies."""
import copy
import hashlib
import json

def J(x):
    return json.dumps(x, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()

def S(b):
    return hashlib.sha256(b).hexdigest()

def D(x):
    return S(J(x))

def E(kind, payload, version=1):
    return dict(domain=f'zoidbergchain/{kind}/v{version}', network_id=N,
                object_type=kind, payload=payload, protocol='zoidbergchain', protocol_version=2)

N = 'task717i-test'
pubs = [
    '0279be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798',
    '02c6047f9441ed7d6d3045406e95c07cd85c778e4b8cef3ca7abac09b95c709ee5',
    '02e493dbf1c10d80f3581e4904930b1404cc6c13900ee0758474fa94abe8c4cd13',
    '02f9308a019258c31049344f85f89d5229b531c845836f99b08601f113bce036f9']
ids = ['0x7e5f4552091a69125d5dfcb7b8c2659029395bdf',
       '0x2b5ad5c4795c026514f8317c7a215e218dccd6cf']
M = dict(domain='zoidbergchain/validator-set/v1', membership_version=1,
         protocol='zoidbergchain', protocol_version=2, network_id=N,
         authority_profile='static-genesis-v1', validator_epoch=0,
         byzantine_fault_budget=1, required_quorum=3, validator_public_keys=pubs)
versions = dict(encoding=1, history=1, issuance=1, media=2, native=2,
                reputation=3, review=3, reviewer=2, rights=1, technical=1)
PR = dict(domain='zoidbergchain/application-policy-registry/v1', registry_version=1,
          network_id=N, policies=[dict(policy_kind=k, policy_version=v, canonical_bytes='7b7d')
                                 for k, v in sorted(versions.items())])
limits = dict(agreement_bytes=4096, block_bytes=3145728, commit_proof_bytes=16384,
              envelope_bytes=2048, manifest_bytes=8192, max_depth=32, max_round=2147483647,
              max_uint=9007199254740991, prevote_certificate_bytes=12288,
              proposal_bundle_bytes=3160400, round_evidence_bytes=8192, signed_bytes=2304)
DA = dict(agreement_version=1, application_policy_digest=D(PR),
          authority_profile='static-genesis-n4-f1-q3-v1', domain='zoidbergchain/bft-agreement/v1',
          limits=limits, parent_profile='immediate-finalized-v1',
          proposer_profile='height-minus-one-plus-round-mod-four-v1', protocol='zoidbergchain',
          protocol_version=2, reference='arxiv:1807.04938v3/Algorithm1',
          rule_selection='printed-lines-1-67', signer_profile='reserve-sign-store-release-v1',
          timeout_profile='linear-1000ms-plus-1000ms-per-round-v1', wire_profile='bft-ascii-json-v1')
B0 = dict(bootstrap_version=1, network_id=N, reviewer_policy_digest=D({}),
          reputation_rule_digest=D({}), reviewers=sorted(ids))
N0 = dict(native_state_version=1, network_id=N, total_supply='0',
          initial_reward_pool='0', allocations=[])
N1 = dict(native_state_version=1, network_id=N, total_supply='1',
          initial_reward_pool='0', allocations=[dict(wallet_address=ids[0], balance='1', next_nonce='1')])
HB = dict(history_version=1, bootstrap_events=[])
BE, NE, HE = E('reviewer-bootstrap', B0), E('native-bootstrap', N0), E('history-bootstrap', HB)
S0 = dict(state_version=1, policy_registry_digest=D(PR), reviewer_bootstrap_digest=D(BE),
          native_bootstrap_digest=D(NE), bootstrap_history_commitment=D(HE))
SE = E('initial-state', S0)
H0 = dict(history_version=1, bootstrap_events=[], bootstrap_history_commitment=D(HE),
          initial_state=S0, initial_state_commitment=D(SE))
P = dict(genesis_version=2, index=0, previous_hash='0'*64, application='task717i-test',
         initial_block_version=4, consensus_message_version=1, validator_manifest=M,
         validator_set_commitment=D(M), agreement_descriptor=DA, agreement_profile_digest=D(DA),
         policy_registry=PR, policy_registry_digest=D(PR), reviewer_bootstrap=B0,
         reviewer_bootstrap_digest=D(BE), native_bootstrap=N0, native_bootstrap_digest=D(NE),
         history_bootstrap=H0)
G2 = E('genesis', P, 2)
G = D(G2)
NS = dict(protocol='zoidbergchain', protocol_version=2, network_id=N, genesis_hash=G,
          agreement_profile_digest=D(DA), validator_epoch=0, validator_set_commitment=D(M),
          validator_public_key=pubs[0], validator_id=ids[0])
J0 = dict(domain='zoidbergchain/reviewer-journal-genesis/v1', protocol_version=2,
          network_id=N, genesis_hash=G, history_policy_digest=D({}), bootstrap_digest=D(BE))
projection = dict(accounts=[], reward_pool='0', reviewers=[dict(wallet_address=w,
                  underlying_status='ESTABLISHED_REVIEWER', quota_used=0) for w in sorted(ids)],
                  claims=[], offenses=[], penalties=[], participation=[], finalized_ref=dict(block_height=0, block_hash=G))
objects = dict(M=M, PR=PR, DA=DA, B0=BE, N0=NE, N1=E('native-bootstrap', N1), HB=HE, S0=SE, G2=G2,
               NS=NS, J0=J0, rebuilt=projection)
rows = {name: dict(bytes=len(J(x)), sha256=D(x), preimage=J(x).decode()) for name, x in objects.items()}
negative = {}
def mutation(name, target, field, value, reason):
    g = copy.deepcopy(G2)
    at = g
    for key in target:
        at = at[key]
    at[field] = value
    raw = J(g)
    assert S(raw) != G
    negative[name] = dict(bytes=len(raw), sha256=S(raw), path=target+[field], value=value, reason=reason)

mutation('wrong-manifest', ['payload','validator_manifest'], 'required_quorum', 2, 'INVALID_MANIFEST; PIN_MISMATCH')
mutation('wrong-network', [], 'network_id', 'task717i-test-b', 'NETWORK_CROSS_BINDING; PIN_MISMATCH')
mutation('malformed-reviewer', ['payload','reviewer_bootstrap'], 'reviewers', ['0xBAD'], 'INVALID_WALLET; PIN_MISMATCH')
mutation('duplicate-reviewer', ['payload','reviewer_bootstrap'], 'reviewers', [ids[0],ids[0]], 'DUPLICATE_WALLET; PIN_MISMATCH')
mutation('tampered-policy-version', ['payload','policy_registry','policies',0], 'policy_version', 2, 'UNSUPPORTED_POLICY_VERSION; DIGEST_MISMATCH; PIN_MISMATCH')
mutation('wrong-validator-epoch', ['payload','validator_manifest'], 'validator_epoch', 1, 'STATIC_EPOCH; PIN_MISMATCH')
mutation('unknown-field', ['payload'], 'genesis_hash', G, 'CLOSED_SCHEMA; PIN_MISMATCH')
mutation('null-reviewers', ['payload','reviewer_bootstrap'], 'reviewers', None, 'TYPE; PIN_MISMATCH')
# A completely self-consistent foreign root: change only a valid deployment application.
mutation('self-consistent-foreign-root', ['payload'], 'application', 'task717i-other', 'PIN_MISMATCH even after internal checks')
# Same logical object with a noncanonical newline is not repaired before hashing.
raw = J(G2) + b'\n'
negative['noncanonical-newline'] = dict(bytes=len(raw), sha256=S(raw), suffix_hex='0a', reason='NONCANONICAL; PIN_MISMATCH')
assert rows['M']['sha256'] == '6fb37df7e489c39287ea827d08f32467f84116d1e8758304d86672a6fd935518'
assert len(J(dict(wallet_address='0x'+'f'*40,balance='1'*32,next_nonce='1'))) <= 132
print(json.dumps(dict(objects=rows, mutations=negative), sort_keys=True, indent=2))
```

```javascript task717l-javascript
// Independent fixture construction and SHA-256, not a generic G2 parser.
const fs=require('node:fs'), crypto=require('node:crypto'), assert=require('node:assert/strict');
function J(x){if(x===null||typeof x!=='object')return JSON.stringify(x);
 if(Array.isArray(x))return '['+x.map(J).join(',')+']';
 return '{'+Object.keys(x).sort().map(k=>JSON.stringify(k)+':'+J(x[k])).join(',')+'}';}
const S=x=>crypto.createHash('sha256').update(x,'utf8').digest('hex'), D=x=>S(J(x));
const N='task717i-test';
function E(kind,payload,version=1){return {domain:`zoidbergchain/${kind}/v${version}`,
 network_id:N,object_type:kind,payload,protocol:'zoidbergchain',protocol_version:2};}
const pubs=[
 '0279be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798',
 '02c6047f9441ed7d6d3045406e95c07cd85c778e4b8cef3ca7abac09b95c709ee5',
 '02e493dbf1c10d80f3581e4904930b1404cc6c13900ee0758474fa94abe8c4cd13',
 '02f9308a019258c31049344f85f89d5229b531c845836f99b08601f113bce036f9'];
const ids=['0x7e5f4552091a69125d5dfcb7b8c2659029395bdf','0x2b5ad5c4795c026514f8317c7a215e218dccd6cf'];
const M={validator_public_keys:pubs,required_quorum:3,byzantine_fault_budget:1,
 validator_epoch:0,authority_profile:'static-genesis-v1',network_id:N,protocol_version:2,
 protocol:'zoidbergchain',membership_version:1,domain:'zoidbergchain/validator-set/v1'};
const versions={technical:1,rights:1,reviewer:2,review:3,reputation:3,native:2,media:2,issuance:1,history:1,encoding:1};
const PR={policies:Object.keys(versions).sort().map(policy_kind=>({canonical_bytes:'7b7d',
 policy_version:versions[policy_kind],policy_kind})),network_id:N,registry_version:1,
 domain:'zoidbergchain/application-policy-registry/v1'};
const DA={wire_profile:'bft-ascii-json-v1',timeout_profile:'linear-1000ms-plus-1000ms-per-round-v1',
 signer_profile:'reserve-sign-store-release-v1',rule_selection:'printed-lines-1-67',
 reference:'arxiv:1807.04938v3/Algorithm1',protocol_version:2,protocol:'zoidbergchain',
 proposer_profile:'height-minus-one-plus-round-mod-four-v1',parent_profile:'immediate-finalized-v1',
 limits:{signed_bytes:2304,round_evidence_bytes:8192,proposal_bundle_bytes:3160400,
 prevote_certificate_bytes:12288,max_uint:9007199254740991,max_round:2147483647,max_depth:32,
 manifest_bytes:8192,envelope_bytes:2048,commit_proof_bytes:16384,block_bytes:3145728,agreement_bytes:4096},
 domain:'zoidbergchain/bft-agreement/v1',authority_profile:'static-genesis-n4-f1-q3-v1',
 application_policy_digest:D(PR),agreement_version:1};
const B0={reviewers:[...ids].sort(),reputation_rule_digest:D({}),reviewer_policy_digest:D({}),network_id:N,bootstrap_version:1};
const N0={allocations:[],initial_reward_pool:'0',total_supply:'0',network_id:N,native_state_version:1};
const N1={allocations:[{wallet_address:ids[0],balance:'1',next_nonce:'1'}],initial_reward_pool:'0',total_supply:'1',network_id:N,native_state_version:1};
const HB={bootstrap_events:[],history_version:1};
const BE=E('reviewer-bootstrap',B0),NE=E('native-bootstrap',N0),HE=E('history-bootstrap',HB);
const S0={bootstrap_history_commitment:D(HE),native_bootstrap_digest:D(NE),reviewer_bootstrap_digest:D(BE),policy_registry_digest:D(PR),state_version:1};
const SE=E('initial-state',S0), H0={initial_state_commitment:D(SE),initial_state:S0,bootstrap_history_commitment:D(HE),bootstrap_events:[],history_version:1};
const P={history_bootstrap:H0,native_bootstrap_digest:D(NE),native_bootstrap:N0,
 reviewer_bootstrap_digest:D(BE),reviewer_bootstrap:B0,policy_registry_digest:D(PR),policy_registry:PR,
 agreement_profile_digest:D(DA),agreement_descriptor:DA,validator_set_commitment:D(M),validator_manifest:M,
 consensus_message_version:1,initial_block_version:4,application:N,previous_hash:'0'.repeat(64),index:0,genesis_version:2};
const G2=E('genesis',P,2), G=D(G2);
const NS={validator_id:ids[0],validator_public_key:pubs[0],validator_set_commitment:D(M),validator_epoch:0,
 agreement_profile_digest:D(DA),genesis_hash:G,network_id:N,protocol_version:2,protocol:'zoidbergchain'};
const J0={bootstrap_digest:D(BE),history_policy_digest:D({}),genesis_hash:G,network_id:N,
 protocol_version:2,domain:'zoidbergchain/reviewer-journal-genesis/v1'};
const rebuilt={accounts:[],reward_pool:'0',reviewers:[...ids].sort().map(wallet_address=>({wallet_address,
 underlying_status:'ESTABLISHED_REVIEWER',quota_used:0})),claims:[],offenses:[],penalties:[],participation:[],finalized_ref:{block_height:0,block_hash:G}};
const expected=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
const objects={M,PR,DA,B0:BE,N0:NE,N1:E('native-bootstrap',N1),HB:HE,S0:SE,G2,NS,J0,rebuilt};
for(const [name,value] of Object.entries(objects)){
 assert.equal(J(value),expected.objects[name].preimage,name+' bytes');
 assert.equal(Buffer.byteLength(J(value)),expected.objects[name].bytes,name+' length');
 assert.equal(D(value),expected.objects[name].sha256,name+' SHA256');
}
const cases={
 'wrong-manifest':[['payload','validator_manifest','required_quorum'],2],
 'wrong-network':[['network_id'],'task717i-test-b'],
 'malformed-reviewer':[['payload','reviewer_bootstrap','reviewers'],['0xBAD']],
 'duplicate-reviewer':[['payload','reviewer_bootstrap','reviewers'],[ids[0],ids[0]]],
 'tampered-policy-version':[['payload','policy_registry','policies',0,'policy_version'],2],
 'wrong-validator-epoch':[['payload','validator_manifest','validator_epoch'],1],
 'unknown-field':[['payload','genesis_hash'],G],
 'null-reviewers':[['payload','reviewer_bootstrap','reviewers'],null],
 'self-consistent-foreign-root':[['payload','application'],'task717i-other']};
for(const [name,[path,value]] of Object.entries(cases)){
 const changed=structuredClone(G2);let at=changed;
 for(const k of path.slice(0,-1))at=at[k];at[path.at(-1)]=value;
 assert.equal(S(J(changed)),expected.mutations[name].sha256,name);
 assert.equal(Buffer.byteLength(J(changed)),expected.mutations[name].bytes,name+' length');
 assert.notEqual(D(changed),G);
}
assert.equal(S(J(G2)+'\n'),expected.mutations['noncanonical-newline'].sha256);
assert.equal(Buffer.byteLength(J(G2)+'\n'),expected.mutations['noncanonical-newline'].bytes);
assert.equal(J(rebuilt),expected.objects.rebuilt.preimage);
console.log('PASS: 12 independently constructed canonical objects/hashes and 10 mutation bytes/hashes; genesis projection only; no semantic policy/launch acceptance');
```

## Appendix C. Exact mutations and negative expected results

Each path is applied to a deep copy of Appendix A's parsed G2; replace the
specified value, retaining every other field and dependent digest, then hash J
of the result. The newline case appends one byte `0a` to the base canonical
preimage. The independently approved pin stays the base G throughout. Reasons
name required rejection layers; scratch diagnostics check the relevant fixture
constraints/pin inequality, not a production error-code API.

| Case | Bytes | Expected SHA-256 | Required result |
| --- | ---: | --- | --- |
| duplicate-reviewer | 4318 | `5a310bfdb69961a97b05311e0add4fef680f5c866e403e126c117988bdc5b2ba` | DUPLICATE_WALLET; PIN_MISMATCH |
| malformed-reviewer | 4236 | `d2e855078095c16939b60e40a8ff8a4298d9653060a5b36379c4e80c683729a7` | INVALID_WALLET; PIN_MISMATCH |
| noncanonical-newline | 4319 | `0d2f92d05f401c11e9188986d20fddd6e178d56fc249dcb6a55e59ef9416bdf4` | NONCANONICAL; PIN_MISMATCH |
| null-reviewers | 4231 | `e643856de2d387a077cdd2db3970491c13ea4b1eaa1f078df1f45130cd9aa559` | TYPE; PIN_MISMATCH |
| self-consistent-foreign-root | 4319 | `a24f7a8ffcd7afe5a2a98015a0d67afa7132640556996df225bcabf8f8520c3f` | PIN_MISMATCH even after internal checks |
| tampered-policy-version | 4318 | `a9aa9efc336e4a66a6ab7aa3f9f67d1d0ef7a7afedbcfb25bf7b11e01662cb08` | UNSUPPORTED_POLICY_VERSION; DIGEST_MISMATCH; PIN_MISMATCH |
| unknown-field | 4400 | `de2c6aa0066ad8852cbe775cb8d7f39ceca18c701d813e9cf3d856ac75a04bf6` | CLOSED_SCHEMA; PIN_MISMATCH |
| wrong-manifest | 4318 | `9f000270f9b8df3085f400823cab6b44dd78df97a1c7528ee76a435300bc4622` | INVALID_MANIFEST; PIN_MISMATCH |
| wrong-network | 4320 | `99db440b77796009592ab59990afd3320a12118b9c86c10a7967aa79dc303530` | NETWORK_CROSS_BINDING; PIN_MISMATCH |
| wrong-validator-epoch | 4318 | `11f7b6d64492a493a1b8040c3eb64a6f04e7cafcb2a83e700ce6ad5102c4c7b3` | STATIC_EPOCH; PIN_MISMATCH |

Exact path/value recipes (integers in a path are zero-based array indices):

```json
{"duplicate-reviewer":{"path":["payload","reviewer_bootstrap","reviewers"],"value":["0x7e5f4552091a69125d5dfcb7b8c2659029395bdf","0x7e5f4552091a69125d5dfcb7b8c2659029395bdf"]},"malformed-reviewer":{"path":["payload","reviewer_bootstrap","reviewers"],"value":["0xBAD"]},"noncanonical-newline":{"suffix_hex":"0a"},"null-reviewers":{"path":["payload","reviewer_bootstrap","reviewers"],"value":null},"self-consistent-foreign-root":{"path":["payload","application"],"value":"task717i-other"},"tampered-policy-version":{"path":["payload","policy_registry","policies",0,"policy_version"],"value":2},"unknown-field":{"path":["payload","genesis_hash"],"value":"0b1b932a7d6cfb0fed6cec2019724b0b0bf6ab13b0516e8d60d63ddbfa25ee94"},"wrong-manifest":{"path":["payload","validator_manifest","required_quorum"],"value":2},"wrong-network":{"path":["network_id"],"value":"task717i-test-b"},"wrong-validator-epoch":{"path":["payload","validator_manifest","validator_epoch"],"value":1}}
```

Additional executed lexical diagnostics reject duplicate JSON object key
`{"x":1,"x":1}`, float `{"x":1.0}`, negative zero `{"x":-0}` and UTF-8 BOM
followed by `{}`. Epoch `true` and epoch `2` reject through existing K/I checks.
The base M commitment matches frozen I's
`6fb37df7e489c39287ea827d08f32467f84116d1e8758304d86672a6fd935518`.
Only D_ag's application_policy_digest changes from I's synthetic `55...55`
input; its exact fourteen-field grammar/limits remain unchanged. Existing
Context accepts M/new D_ag/computed test G as a parameterized I context; that
does not cause K to treat test G as an approved authenticated genesis.

The genesis reconstruction example verifies ND/BD/HD/PD/SC, initializes the
two underlying established grants with zero usage and no offenses/penalties/
participation/claims, an empty account map and zero reserve, then derives `(0,G)`.
The separate N1 fixture initializes exactly one test account at nonce 1 and
balance 1. Neither claims that subsequent reviewer/native transitions replay.

For complete reproducibility, the focused scratch diagnostic is included next.
Save as `temp/task717l/check.py`; run from the repository root with
`.\.venv\Scripts\python.exe -B -m temp.task717l.check` after the recipes above.
Its fixture equality checks are intentionally narrow; it is verification of
these examples rather than a candidate production G2 implementation.

```python task717l-diagnostics
"""Focused diagnostics, not a reusable/complete G2 parser or semantic validator."""
import contextlib
import copy
import io
import json
import re
import runpy
from pathlib import Path
from canonical_v3.primitives import parse, closed, wallet, decimal_units
from isolated_bft717j.wire import Context
from isolated_bft717k.manifest import Manifest

with contextlib.redirect_stdout(io.StringIO()):
    v = runpy.run_path('temp/task717l/vectors.py')
J,D,E,N = [v[k] for k in ('J','D','E','N')]
G2,G = v['G2'], v['G']

def check(x):
    # Deliberately limited to this fixture and named mutation families.
    closed(x, 'domain network_id object_type payload protocol protocol_version')
    p=x['payload']; closed(p, v['P'].keys())
    assert x['domain']=='zoidbergchain/genesis/v2' and x['object_type']=='genesis'
    assert x['network_id']==N and x['protocol']=='zoidbergchain' and x['protocol_version']==2
    m=Manifest(J(p['validator_manifest']))
    assert m.value['network_id']==N and p['validator_set_commitment']==m.commitment
    ctx=Context(m.raw, J(p['agreement_descriptor']), D(x))
    assert p['agreement_profile_digest']==ctx.A
    pr=p['policy_registry']; assert pr['network_id']==N
    assert p['policy_registry_digest']==D(pr)==p['agreement_descriptor']['application_policy_digest']
    assert [(z['policy_kind'],z['policy_version']) for z in pr['policies']]==sorted(v['versions'].items())
    for entry in pr['policies']:
        raw=bytes.fromhex(entry['canonical_bytes']); assert J(parse(raw))==raw
    b=p['reviewer_bootstrap']; closed(b,v['B0'].keys()); ws=b['reviewers']
    assert type(ws) is list and len(ws)<=128
    for w in ws: wallet(w)
    assert ws==sorted(set(ws)) and b['network_id']==N
    assert b['reviewer_policy_digest']==b['reputation_rule_digest']==D({})
    assert p['reviewer_bootstrap_digest']==D(E('reviewer-bootstrap',b))
    nb=p['native_bootstrap']; closed(nb,v['N0'].keys())
    total=decimal_units(nb['total_supply']); pool=decimal_units(nb['initial_reward_pool'])
    assert sum(decimal_units(a['balance']) for a in nb['allocations'])+pool==total
    assert p['native_bootstrap_digest']==D(E('native-bootstrap',nb))
    h=p['history_bootstrap']; assert h==v['H0']
    assert D(E('initial-state',h['initial_state']))==h['initial_state_commitment']
    assert J(parse(J(x),limit=1048576))==J(x)

check(G2)
assert D(G2)==G
negative=v['negative']; rejected=0
for name,row in negative.items():
    if 'path' in row:
        x=copy.deepcopy(G2); at=x
        for key in row['path'][:-1]: at=at[key]
        at[row['path'][-1]]=row['value']
        try:
            check(x)
        except (AssertionError,ValueError):
            assert name!='self-consistent-foreign-root'
        else:
            assert name=='self-consistent-foreign-root'
        assert D(x)!=G
    else:
        try: parse(J(G2)+b'\n',limit=1048576)
        except ValueError: pass
        else: raise AssertionError('accepted noncanonical bytes')
    rejected+=1
# Lexical failures where parsing must reject before object construction.
for raw in (b'{"x":1,"x":1}', b'{"x":1.0}', b'{"x":-0}', b'\xef\xbb\xbf{}'):
    try: parse(raw)
    except ValueError: pass
    else: raise AssertionError(raw)
for bad in (True, 2):
    x=copy.deepcopy(G2); x['payload']['validator_manifest']['validator_epoch']=bad
    try: check(x)
    except (AssertionError,ValueError): pass
    else: raise AssertionError('epoch accepted')
assert len(J(G2))<=1048576
rest=len(J(G2))-sum(len(J(v[k])) for k in ('M','DA','PR','B0','N0'))
assert rest<=16384
assert G2['payload']['history_bootstrap']['initial_state']==v['S0']
assert v['projection']['accounts']==[] and len(v['projection']['reviewers'])==2
assert sum(decimal_units(a['balance']) for a in v['N1']['allocations'])==decimal_units(v['N1']['total_supply'])
# The fixture has no semantic policy authority and cannot support first media.
assert all(bytes.fromhex(e['canonical_bytes'])==b'{}' for e in v['PR']['policies'])
assert len(v['B0']['reviewers'])<5
print(f'PASS: {rejected} mutation/pin diagnostics, 4 lexical failures, 2 epoch-type failures; residual={rest}; policy semantics BLOCKED')
```
