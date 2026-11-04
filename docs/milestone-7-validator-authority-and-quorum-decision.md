# Milestone 7 Task 7.17F — Validator authority and quorum decision

**Task 7.17L follow-up (2026-10-26):** The
[G2 genesis and bootstrap contract](milestone-7-g2-genesis-and-bootstrap-contract.md)
specifies a closed proposed outer genesis envelope, noncircular M/C and
policy/D/A bindings, clean reviewer/native bootstrap commitments, independent
release-pin rules and conditional historical recovery. Exact Python/JavaScript
envelope vectors do not authenticate an approved launch genesis. Current gates:
**PASS** for I/K's isolated N4 manifest canonicalization; **PARTIAL** for proposed
G2 serialization/authentication; **BLOCKED** for complete application bootstrap,
fresh-node recovery, production deployment and Task 7.17 resumption. K still
returns `INCOMPLETE_AUTHORITY`. Inner policy/combined-history schemas, owner
approval and launch distribution remain unresolved. No production genesis,
consensus, roster, policy activation or implementation changes occur here. The
original F analysis/status below remains a historical proposal.

Date: 2026-10-24 (America/New_York).

**Specification for owner review, not an approved launch configuration or an
implemented consensus protocol.** Recommend an initially static, independently
operated, permissioned public testnet with **N=4, f=1, q=3**. This document fixes
a candidate membership encoding and authority-verification interface for review.
It does not establish that the current or proposed network is BFT-safe.
Distributed agreement, safe signer transitions, activation and reviewer-history
implementation remain **BLOCKED**.

## 1. Repository prerequisites and scope

- Expected/actual branch: `Compression-State-Bloat-and-Node-Economics`.
- Starting HEAD: `82f8a49efe1c9f1bb7ec5f69e3e5562f7dddecd8`, separate commit
  `Milestone 7 Task 7.17E: repair local finality durability and atomic voting`.
- Initial index/worktree clean. Task 7.17E's
  [report](milestone-7-finality-durability-implementation.md) and
  [targeted tests](../tests/test_milestone_7_task_7_17e_finality_durability.py)
  exist and are tracked in that commit. No unexpected Git state encountered.
- Read [7.17C](milestone-7-finality-and-history-dependency-audit.md),
  [7.17D](milestone-7-finality-safety-and-remediation-decision.md), 7.17E and the
  [7.17B amendment](milestone-7-v2-reviewer-history-protocol-amendment.md).
  Current source takes precedence over older implementation claims.
- No applicable ancestor/repository/docs `AGENTS.md`; no delegation.
- Deliverables: this document and a reference/gate-status addition to 7.17D.
  No production/test/fixture/vector changes, membership/quorum/signing changes,
  migration, activation, reset, deployment, commit, push or merge. No next task
  begins. Disposable verification artifacts are in ignored `temp/`.

In sections 4–8, **must** describes the proposed inactive contract only. All new
names and versions are candidate schema reservations requiring approval.

## 2. Current authority audit

Authority classes: **A** authenticated by approved genesis/finalized protocol
state; **B** locally configured and not independently verifiable; **C** derived
reproducibly from authenticated history; **D** unresolved. A signature verifies
the covered identity/bytes; it does not authorize a self-selected roster.

| Authority source / question | Implemented behavior and classification |
| --- | --- |
| Who configures validators? | **B.** The operator controlling environment/startup selects `PUBLIC_TESTNET_V1_VALIDATOR_ADDRESSES`; an embedding application can pass `Blockchain(..., validator_set=...)`. The attribute is mutable. No consensus election/governance authorizes changes. [Parser](../config.py#L296), [constructor](../blockchain.py#L267). |
| Keys and identities | **B authorization; cryptographic identity checked.** A lowercase Ethereum-style `0x` plus 40 hex address, recovered from secp256k1 EIP-191 `personal_sign`, not a full registered public key. Miner keys, genesis allocation recipients, reviewers, peer IDs and peer HMAC credentials are separate roles. Balances confer no finality membership. [Verifier](../services/finality_service.py#L76), [signing](../protocol_v1_finality.py). |
| How nodes obtain the live set | **B.** Constructor input or imported configuration, sorted and silently deduplicated. Default and tracked `.env.example` roster are empty. No authenticated set discovery or proof of network-wide agreement; matching config files do not prove approved membership. |
| Genesis authority | **A for existing genesis content/identity; D for membership.** Frozen v1 hash `2b99e87f80e0e855ab98b3269b635be5415273f41d7d4bf1a2aeb8b277b13061` authenticates media, allocations and supply, but its closed fields contain no validator roster, epoch or finality-policy authority. Allocation keys are not implied validators. [Payload](../protocol_v1_genesis.py#L197), [closed fields](../protocol_v1_genesis.py#L60). |
| Can all nodes prove the same set? | **D.** Chain compatibility checks network/genesis, but that genesis does not commit membership. Signing a common network ID does not establish a common approved validator set. |
| Lifetime changes | **B/D.** Config/restart/constructor changes can select another live set, with no authenticated activation height or transition. Old proofs retain their embedded sets. No approved static enforcement or dynamic registry exists. |
| Removal or compromise | **D.** A local edit changes live vote admission, not historical authority elsewhere. Locally observed equivocation is discounted during counting; it supplies no governance, rotation or revocation rule. No slashing/on-chain emergency authority exists. |
| Live attestation identity binding | Address, height/hash, network, protocol 1, attestation version 1 and `zoidbergchain/finality-attestation/v1` are signed via a canonical envelope. Parent is transitively bound by validated block hash. No direct genesis, membership commitment/epoch, agreement policy, round or step is signed. Authorization remains **B**. |
| Active finality proofs | **B/D.** Eight-field record includes its own `validator_set` and `ceil(2N/3)` threshold. `validate_finalization_evidence` checks signatures against that embedded list, not an authenticated historical set. [Proof verification](../services/finality_service.py#L151). |
| Persistence/restart | **B/D for roster authority.** `_validate_persisted_finality_state` checks signatures and exact canonical height/hash, never genesis-authenticated membership. 7.17E preserves evidence without upgrading its trust source. [Loader](../blockchain.py#L2839), [storage guard](../storage.py#L191). |
| Inert protocol-2/block-3 authority | **B/D.** Its verifier requires equality to external `trusted_validators`, but the caller supplies that trust. `V3Store` retains caller validators/equivocators as `trust_context`; storage does not authenticate them. Observer-specific exclusions can change the verdict. [Proof](../canonical_v3/finality.py#L35), [store](../canonical_v3/storage.py#L367). |
| Reconstructed historical authority | **D for membership. C only for facts actually committed under an authenticated prefix.** Blocks permit reproducible target hashes/ancestry, not recovery of a roster never committed there. Trusted snapshot imports retain proof sections, not independent membership authority. No C-class historical validator-set reconstruction exists today. |
| Sync/fork choice | Network/genesis-checked sync fetches blocks, originality certificates/evidence, not finality proofs or authority. Same-tip sync may stop without proof reconciliation. Originality score/height/hash ordering cannot resolve conflicting QCs. Reorg guards local finalized anchors; 7.17E prevents stale-writer erasure. [Fetch](../services/peer_chain_sync_service.py#L104), [fork choice](../services/fork_choice_service.py), [reorg](../services/canonical_reorg_service.py#L225). |

The 7.17C self-declared one-key historical proof witness remains relevant at a
local/import trust boundary; it is not a demonstrated unauthenticated remote
injection endpoint. There is no production finality signer or complete
proposal/lock/round-change engine. No populated owner-approved operational
validator roster is established by inspected tracked configuration. Three test
accounts or two node facades are test topologies, not launch assignments. No
private runtime roster or operational keys were needed for this audit.

## 3. Trust model and quorum/fault proof

The candidate is **permissioned**: approved independent operators control a
finite unweighted roster. Nodes verify membership from an owner-approved genesis
distributed through an authenticated release process. Peers cannot nominate the
trust root. No staking, proof of work, token weighting, validator election or
permissionless admission is proposed.

Let V be the SAME authenticated set at both verifiers, N=|V|, f the maximum
Byzantine identities and q the distinct authorized signatures per decision.
For two size-q subsets A and B:

```text
|A intersect B| = |A|+|B|-|A union B| >= max(0,2q-N) = I
same-context exclusion requires I > f, equivalently 2q > N+f
participation despite f withholding requires q <= N-f
floor((N+f)/2)+1 <= q <= N-f; feasible iff N >= 3f+1
```

The lower bound is attained by maximizing disjoint portions outside the
intersection. Larger QCs only increase overlap and contain a size-q pair. The
exclusion argument assumes unforgeable signatures AND honest signers unable to
authorize conflicting decisions under complete agreement rules across rounds,
heights and restarts. Quorum mathematics does not supply those rules.

| Topology | N | f | q | I | Safety: 2q > N+f | Participation: q <= N-f | Crash-only unavailable capacity N-q |
| --- | ---: | ---: | ---: | ---: | --- | --- | ---: |
| A: three, current threshold, one Byzantine | 3 | 1 | 2 | 1 | 4 > 4: **false** | 2 <= 2: true | 1 |
| A alternative: unanimity | 3 | 1 | 3 | 3 | 6 > 4: true | 3 <= 2: **false** | 0 |
| Three with honest/crash-only signing | 3 | 0 | 2 | 1 | 4 > 3: true | 2 <= 3: true | 1 |
| B: recommended candidate | 4 | 1 | 3 | 2 | 6 > 5: true | 3 <= 3: true | 1 |
| C: larger candidate | 7 | 2 | 5 | 3 | 10 > 9: true | 5 <= 5: true | 2 |
| Existing single-key development/test possibility | 1 | 0 | 1 | 1 | 2 > 1: true | 1 <= 1: true | 0 |
| Two-key supported local configuration | 2 | 0 | 2 | 2 | 4 > 2: true | 2 <= 2: true | 0 |
| Tracked default/sample, disabled finality | 0 | 0 | 0 computed | n/a | Not a usable quorum | Explicitly cannot finalize | n/a |

For N3/q2, `{A,B}` and `{B,C}` intersect only in B: Byzantine B signs both X
and Y; honest A/C sign their separate target. For N4/q3, `{A,B,C}` and
`{A,B,D}` attain I=2, leaving an honest common signer with f=1. For N7/q5,
`{A,B,C,D,E}` and `{A,B,C,F,G}` attain I=3, leaving one with f=2. Two Byzantine
keys at N4 or three at N7 can occupy the entire minimum intersection. Without
honest signing discipline, even the same quorum can sign both targets.

Crash and Byzantine allowances are not additive: with b Byzantine identities
withholding and c OTHER offline validators, progress needs `q<=N-b-c`; exclusion
needs `2q>N+b`. N4/f1 cannot promise progress with one ordinary outage PLUS a
different withholding Byzantine validator. Crash-only capacity is participation
capacity, not proof of agreement or an additional Byzantine allowance.

| Topology | Partition, synchrony and operational implications |
| --- | --- |
| Three/q2 | A 2+1 component can gather signatures, but one equivocator defeats exclusion. q3 stalls under any outage. Three independent operators still cannot deliver f1 safety AND availability. |
| Four/q3 | A 3+1 component can potentially progress; 2+2 cannot. Four independent signing authorities/operating organizations are needed; shared administrator/key custody/hosting must not defeat the one-fault budget. One maintenance outage consumes all unavailable capacity. |
| Seven/q5 | A 5+2 component can potentially progress; 4+3 cannot. More operators, hosts, backups, monitoring, proof/signature work and traffic; two total unavailable authorities, not two outages plus two Byzantine withholding faults. |
| Empty/one/two/current tests | Empty cannot finalize, one has no redundancy, two-key unanimity has no outage margin. Multiple processes on one host or under shared control do not establish operator independence. Three test accounts do not demonstrate Byzantine tolerance. |

The existing [two-node finality test](../tests/integration/test_two_node_consensus_verification.py#L462)
uses TWO independent databases but THREE validator accounts and q=2; its
healthy-order convergence therefore has the N3 row's fault limitations. The
7.17E durability suite instead uses four test validators/q3 for its storage
checks. Neither harness identifies independent launch operators.

Safety must hold during arbitrary delay/partition; no timeout reduces q or V.
Conditional liveness requires eventual synchrony: after an unknown GST, enough
honest validators communicate, validate available full MODEL A media/proofs and
durably sign within finite bounds, with fair scheduling and a proved round/
proposer mechanism. q available compatible signers is necessary, not sufficient.
Before GST, without valid admitted media, or with excessive unavailability,
there is no finite progress promise. Independence is an audited operational
assumption, not a public-key property. No hosting prices/operators are selected.

## 4. Canonical static manifest and exact commitment

Reuse strict canonical JSON J from frozen v3 primitives: UTF-8, sorted object
keys, compact comma/colon separators, no BOM/newline, floats, duplicate object
keys, invalid Unicode, coercion or normalization. UInt is an actual integer
(not bool), range 0..9,007,199,254,740,991. Strings below are ASCII; H64 is
exactly 64 lowercase hexadecimal characters without `0x`.

M is a closed object with EXACTLY these **ten** fields:

| Field | Exact candidate rule |
| --- | --- |
| domain | `zoidbergchain/validator-set/v1` |
| membership_version | integer 1 |
| protocol | `zoidbergchain` |
| protocol_version | integer 2, inactive candidate family, never active protocol 1 |
| network_id | approved new ID matching `[a-z0-9][a-z0-9-]{2,63}` exactly |
| authority_profile | `static-genesis-v1` |
| validator_epoch | integer 0 throughout this network's lifetime |
| byzantine_fault_budget | integer f, matching selected topology |
| required_quorum | integer q, verified against topology, never caller-selected |
| validator_public_keys | array of canonical full compressed secp256k1 public keys |

K is 33-byte SEC1 compressed form, exactly 66 lowercase hex without `0x`, prefix
`02` or `03`, a finite valid secp256k1 point. Decompress to `04 || x32 || y32`:

```text
validator_id(K) = "0x" || lowerhex(last20(Keccak-256(x32 || y32)))
```

Use Ethereum Keccak-256, not FIPS SHA3-256 or SHA-256. Addresses are derived,
not alternative key registration. Signature verification must recover the exact
registered public point AND its ID, so an address collision cannot authorize
another key. Reject duplicate keys OR derived identities; never silently dedup.
An authoring tool sorts a unique input list by unsigned key bytes (equivalently
lowercase hex lexical order). Received arrays must already have that strict
order; reject permutations rather than accepting a different commitment for
the same set. N is array length; no redundant count/address/operator/endpoint
fields exist.

Propose initial allowed `(N,f,q)` exactly `(4,1,3)` or `(7,2,5)`, recommending
the former. Both have `N=3f+1`, `q=2f+1`, within the existing inert 128-validator
resource ceiling. Reject all other sizes, empty sets and mismatched budgets/
thresholds in this candidate public profile. Generalizing this whitelist is
separate profile review, not a config edit. Section 3's other sizes describe
existing possibilities, not additional proposed launch choices.

Bound received J(M) to 8,192 bytes and JSON depth to 32 before curve checks;
the fixed strings, network length and seven-key maximum also bound its actual
canonical width. These are candidate authority-parser limits, not changed
runtime settings or approval of any future agreement proof's resource budget.

```text
C = lowerhex(SHA-256(J(M)))
```

Hash canonical bytes, not hex/base64/a filename/object repr. The domain is IN
J(M); there is no hidden prefix, delimiter or salt. Retain full canonical M in
genesis on chain, not only C or a URL. A local `(G,epoch,C)->keys/IDs` cache is
disposable.

## 5. Genesis/protocol binding and schema amendment

The present closed v1 genesis and frozen non-genesis block 3 cannot accept a
new authority field. Propose a distinct **G2 genesis schema**, genesis_version 2,
protocol_version 2, requiring this exact new closed field in BOTH its canonical
hashed payload and its wire record:

```text
validator_authority = {"manifest": M, "validator_set_commitment": C}
```

G2 must also authenticate a required `agreement_profile_digest` H64 and its full
canonical agreement descriptor in the approved policy registry. It must commit
complete selected signing/decision/ancestry/round rules. Its exact descriptor
grammar and the complete G2 launch layout/registry composition are **BLOCKED**
pending agreement and launch-schema reviews. This specifies the precise required
membership extension, not unspecified allocation/policy/media launch fields.

G must hash the ENTIRE canonical new genesis payload including authority and
agreement policy, under its separately versioned genesis envelope/domain. Exact
complete G2 bytes/hash cannot be published or implemented before that complete
schema is frozen. Do not patch the frozen v1 hash, infer v1 already authenticates
C, hide C in meme text/miner/nonce/policy strings, or include a finality QC in its
own target hash preimage. An independently owner-signed manifest outside genesis
is an alternative extra bootstrap trust requiring explicit approval; the
recommended source-only design authenticates membership in genesis.

Avoid circularity: M binds network/protocol/profile/keys/f/q but contains NO
resulting G. Compute `M -> C -> complete G2 -> G`; signatures then bind BOTH G
and C. Copying M into another genesis preserves C, but old signatures fail the
direct G check. Pinned G authenticates chosen M; C alone does not identify a
unique genesis. Genesis cannot bootstrap its own authority by a self-certified QC.

For every h>=1, use `(epoch=0,C,V from G)`. Height 0 is the trusted validated
genesis anchor, not a quorum-elected authority. Membership epochs never follow
wall time, reviewer epochs, rounds, height intervals or restarts. Epoch 1 rejects
in this profile even with every current validator's signature.

The owner release must pin full G2/hash, new network ID, versions, f/q, complete
agreement policy and authenticated distribution procedure. Real keys/operators,
hosting, actual NID/G, activation/state disposition and any allocations are
**PENDING**. A peer claiming matching hashes or a local config file is not approval.

## 6. Signature/certificate authority interface

Existing nine-field attestations and eight-field proofs lack required context.
Propose separate inactive **A3/Q3**, attestation/proof version 3; retain existing
v1 and inert v2 formats. These labels activate neither protocol 2 nor block 3
nor the 7.17B block-4 proposal.

Exact authority-only commit bytes are J(E), with closed structures:

```text
E = {domain:"zoidbergchain/finality-authority/v1",
     network_id:NID, object_type:"finality-authority", payload:P,
     protocol:"zoidbergchain", protocol_version:2}
P = {agreement_profile_digest:A, attestation_version:3,
     block_hash:H, block_height:h, genesis_hash:G, parent_hash:PARENT,
     round:r, step:"commit", validator_epoch:0,
     validator_id:ID, validator_set_commitment:C}
A3 = {envelope:E, signature_scheme:"personal_sign", signature:Sig65}
```

NID is the network string, not count N. A/G/H/PARENT/C are H64, h UInt>=1,
r UInt>=0 and ID the derived canonical address. No supplied message string can
override J(E). Sig65 is `0x` plus 130 lowercase hex encoding r32||s32||v1,
1<=r,s<curve order, v=27/28. Preserve existing inert acceptance of valid high-S
signatures; variants add no vote. Recover the exact full key from:

```text
Keccak-256(0x19 || ASCII("Ethereum Signed Message:\n")
           || ASCII(decimal(len(J(E)))) || J(E))
```

Here `\n` is ONE byte 0a; the decimal byte length has no leading zero. SHA-256
of J(E) is a diagnostic message ID, not the EIP-191 signing digest. Cross-purpose
native/reviewer/timeout and old finality signatures cannot be relabeled here.
All context is signed, not just held in filenames/caches.

Q3 is exactly `{proof_version:3, commitment:T, attestations:[A3,...]}`, where T
has exactly P's fields EXCEPT validator_id. Every attestation P equals T plus
its ID. V/q come from G/M, not proof claims. Require q..N entries sorted strictly
by derived ID, no repeated IDs. Full keys need not repeat because genesis retains
them. This is an authority interface, not a distributed commit algorithm.

**Agreement semantics remain BLOCKED.** Step `commit`, round r and a policy
digest do not make signing safe. The selected engine must specify permissible
commit predicates and necessary prepare/lock/timeout/view messages/justifications.
If it needs additional commit fields or proof bodies, explicitly amend A3/Q3
and regenerate examples BEFORE freezing an implementation interface. No empty
generic justification or timeout-based unlocking rule is authorized. Membership
encoding is concrete for review; full agreement proof grammar is not frozen.

### 6.1 Deterministic verification

1. Strict-parse closed canonical structures and bounded lengths before costly
   crypto. Match approved protocol/authority/proof versions, NID, G, full
   agreement descriptor/digest and epoch 0. Recompute M/C from G; reject a peer's
   substituted manifest even when its own selected keys sign it.
2. Validate full target bytes/hash/h/parent and complete hash-linked ancestry
   through G. T's parent equals the target's actual parent. Preserve all earlier
   verified finalized anchors. Enforce MODEL A reconstruction, admission, ledger
   and application rules; a signature cannot substitute for full original media
   or community review.
3. Apply the selected agreement's proof/round/commit/ancestry predicate from
   genesis-authenticated policy. This is currently unspecified and blocks
   treating the envelope alone as a finality decision. Immediate finalized-parent
   versus a proved pipelined/gapped rule remains an owner/agreement choice;
   current production permits gaps and unfinalized parents.
4. Verify EACH entry's common fields equal T; verify exact EIP-191 bytes,
   signature, full registered point and derived ID membership. Reject the WHOLE
   Q3 on invalid/unauthorized signature, malformed entry, duplicate/unsorted ID,
   mixed target/parent/round/step/epoch/NID/G/protocol/C/A. Do not filter malformed
   offered QCs into an accepted subset or mix contexts into one quorum.
5. Count each authorized ID once for that exact commitment. Valid votes below
   q are partial evidence, not finality. An aggregator may deduplicate verified
   retransmissions by `(context,ID,exact canonical message)` before constructing
   Q3. Duplicate IDs inside an offered Q3 reject even with distinct valid signatures.
6. A QC proves authorized signatures; finality promotion additionally requires
   step 3 and durable commit. Different signer subsets/signature variants for
   the SAME decision are compatible, not conflicting blocks; retain the first
   canonical local proof. Same-target commits in different rounds are compatible
   only under the selected agreement's rules.

Retain authenticated conflicting individual votes as evidence. The selected
engine defines forbidden conflicts across steps/rounds/heights; differing round
votes are not automatically equivocation. Historical QC verdicts must depend
on authenticated bytes/policy, not local exclusion inventories. Later misconduct
does not remove a static member, alter the denominator or retroactively revoke QCs.

Two independently verified finality proofs for distinct blocks at one height,
or incompatible finalized ancestry across heights, trigger a safety fault:
durably retain BOTH proofs/ancestries and a fault latch, stop authoritative
advancement/signing for that context, permit diagnostic/source reads. Arrival
order, score, lower hash, longer chain and admin edits cannot choose a winner.
Invalid inputs reject; missing dependencies are incomplete; local I/O errors
are unavailable. An unverified peer claim must not trigger the fault latch.
Evidence/latch storage remains future work, not a 7.17E feature.

### 6.2 Limits of the overlap argument

Candidate QCs share at least one honest validator within f, but durable protocol
rules must prevent that signer authorizing incompatible decisions. Stolen/cloned
keys count as Byzantine regardless of operator intent. Bound compromised keys
over all historical contexts still usable, not merely simultaneously online
operators: accumulating enough old static keys can forge alternative history.
Ordinary signatures have no forward security. No checkpoint shortcut or
forward-secure scheme is silently assumed.

Sign-once per height does not prove cross-height ancestry: a hidden QC can
authorize another branch. Sign-once without round recovery can permanently stall
on a 2+2 N4 split even with all nodes available. A timer/higher round does not
justify unlocking a possibly committed value. Durable lock, round-change and
ancestry rules, not merely unique received-vote rows, must enforce safety.

## 7. Historical membership and recovery

The future fresh-node/source-only sequence is:

1. Obtain approved G2/hash through authenticated owner release, not a peer-selected
   root. Validate complete schema/content/hash, policy registry and full genesis
   original media; pin NID/protocol/G.
2. Strictly verify M, curve keys/derived IDs, ordering/duplicates, topology,
   epoch and C, plus genesis authority and agreement policy equality. Local
   config may select connections/one's key; roster/f/q overrides refuse that profile.
3. At every finalized h>=1 derive V(h)=V(0), epoch(h)=0, C(h)=C(0). No dynamic
   registry, per-height snapshots or administrator-supplied historical sets are
   needed for initial static membership.
4. Fetch full contiguous block/original ancestry and required separate Q3 and
   agreement evidence. Independently apply section 6 at each required boundary.
   Reject wrong historical epoch/member/context. Reconcile proof inventory even
   for identical tips; bounded versioned proof/authority sync is still missing.
5. Missing required genesis manifest, proof, policy, original or ancestry makes
   that claimed prefix INCOMPLETE: fetch elsewhere or withhold authoritative
   finality/history. Never assume empty membership, default q or implicit QC from
   depth/status. Never fabricate individual ancestor QCs from a descendant QC;
   ancestor-finality inference must be explicit in the selected engine.
6. Detect verified incompatible finality, including across heights, as section 6
   requires. Evidence must survive a rejected advancement transaction. Fail
   locally closed if evidence persistence is unavailable.
7. After restart, reread immutable sources and pinned G/M, revalidate QCs/trust/
   ancestry, then rebuild caches/cursors. Reuse 7.17E's commit-before-publication
   and uncertain-outcome discipline. Corruption rejects/quarantines/refetches;
   do not silently initialize empty finality after loss. A fresh node cannot
   detect a wholly substituted older valid history without external high-water
   knowledge; no rollback oracle is claimed.

Canonical authority sources are full approved genesis/M/policies, complete
blocks/originals and required separate authenticated decision proofs. QCs stay
outside their own block hash to avoid circularity but are required retained
protocol proof records, independently retrievable. An opaque trusted database
is insufficient. Parsed key maps, proof indexes, membership caches, high-water
views and reviewer projections are derived and rebuildable. Private signer
reservations/locks are DIFFERENT safety facts: a released vote may never form a
QC, so public history cannot reconstruct them. Lost signer history disables
signing even when chain/membership verification succeeds.

## 8. Emergency and upgrade policy

| Event at N4/f1/q3 | Required behavior and tradeoff |
| --- | --- |
| One validator offline | Three remaining can meet participation if all cooperate on an admissible decision; full agreement is still needed for progress. Repair the same authority with intact safe state. Never lower q. This consumes all unavailable capacity. |
| Key lost | Treat as unavailable; a new key is unauthorized. Lost signing history also disables an existing key until safe fenced recovery is justified. No deletion/reset-and-resign or cloned stale backup. Three remaining may progress. |
| Equivocation/compromise | Counts toward Byzantine budget; retain evidence and alert operators, restrict local key use/relay as appropriate. No retroactive removal, QC rewrite, denominator reduction or validator suspension inferred from reviewer penalties. With one Byzantine withholding, all three honest validators must remain available. |
| Two offline | Two cannot reach q3; finality halts. Read/receive/verification may continue. Recover original safe signing authorities or choose a separately approved recovery path; no admin/timeout downgrade. |
| Replacement/rotation | No in-place rotation in this profile. Safely restore SAME authority, or approve a versioned network restart. Live authenticated transitions require a larger separate protocol. Never install a running-chain allowlist override. |
| Testnet reset | Requires separate explicit owner approval/runbook, new NID AND new approved genesis/hash, release artifacts, state disposition, preserved old proofs/MODEL A archive and isolated storage/signer namespaces. New keys recommended; reuse needs custody/context review. No reset here. |
| Conflicting verified QCs / beyond-f compromise | Fail stop advancement/signing and retain evidence. Restart/trusted recovery is a NEW trust decision, not a repair of historical safety. Old proofs do not retrospectively become BFT-safe. |
| Future dynamic membership | Separate approved profile defines transition authority, old/new sets/digests/epochs, exact activation anchor, pending locks/votes and unique handoff proof, including any joint quorum and cross-epoch safety/liveness. Old signatures remain interpreted at their original authority. No such machinery is implied here. |

At N7/f2/q5, two unavailable leave five; three halt participation. Byzantine
withholding and ordinary outages share that allowance. An operator's compromise
claim does not automatically revoke membership. Removing a member and recomputing
a smaller denominator creates a different protocol.

For this initial milestone prefer explicitly approved **versioned network
restart** over emergency dynamic membership: simpler historical trust and no
unsafe handoff, at the cost of disrupted identity, balances, pending submissions,
continuity and links. The owner must decide old-state export and archive retention.
Authenticated transitions could preserve continuity but require complete
governance, cross-epoch proof, recovery and historical verification. Neither
alternative is approved here; an outage is not implicit reset permission.

## 9. 7.17E, versioning and reviewer-history compatibility

| Component | Reuse / later requirements |
| --- | --- |
| Received-finality durability | Reuse 7.17E locked durable read/validate/union/count, immutable first proof, monotonic ancestry, concurrent writer serialization, exact authenticated-message retry, commit-before-cache/ack and uncertain-outcome fail-closed recovery. Receiver reliability does not supply authority/signer safety. |
| Authority-aware persistence | No migration now. Future proof/source references must bind `(protocol,NID,G,A,epoch,C)` and immutable manifest/policy equality. A proof-embedded roster cannot grant authorization. Current guards need new schema adapters, not blind reuse of old field assumptions. |
| Later constraints | Unique authoritative `(context,height)->target`, ancestry guards, immutable source/proof references and append-only conflict evidence/fault latch. Received-vote identities include context/round/step/ID/target so conflicting evidence can coexist. Relational indexes are optional if serialized procedural constraints guard EVERY writer. Exact SQL is later work. |
| Signer reservations | Namespace includes protocol/NID/G/agreement policy/epoch/C/key ID, exact sign bytes, round/step/target/parent and safety justification. Config/context changes cannot erase earlier decisions. Unique received votes are not reservations. Exclusive fenced ownership, release sequencing, lock retention and stale-backup defenses remain necessary. |
| Operating profile | Reuse supported local SQLite DELETE/EXTRA, explicit transaction/connection ownership and failure discipline where appropriate. No settings change, WAL bypass, cross-machine or cross-DB atomicity claim. Physical power loss/backup/key recovery needs its own validation. |
| Reviewer authority chain | Approved G/M -> safe agreement/finality -> one verified durable finalized prefix -> authenticated event order/acceptance -> deterministic historical reviewer replay. C authorizes validators, not reviewer grants, eligibility or private receipt time. |
| 7.17B amendment | Its FP must explicitly incorporate C/epoch/f/q and the full agreement. Retained finality/v2 messages cannot encode direct G/C/epoch/round/step/A. A3/Q3 requires a later explicit amendment and renewed vectors/resource limits; dependent FP/HP hashes must be regenerated in that new profile. Existing 7.17B bytes are not replaced here. |
| Remaining history gates | Safe finality/ancestry, proof/source sync, complete replay sources, bootstrap grants, finalized-parent choice, no-media clock/control records, preliminary media admission, exact cohort/all-unsure behavior and global ISSUE ownership remain unresolved. Task 7.17 is not resumed. |

New G2 authority/policy schema and A3/Q3 signing/proof domains need separate
approval, implementation, vectors and activation. Membership fields do not
inherently change non-genesis block hashes: proofs are separate and G anchors
authority. Frozen block 3, media descriptors, C2/V3 review evidence, native
formats, original bytes and golden vectors remain untouched. History P4/C3/V4
is another proposed schema. Old v1/inert v2 signatures cannot become A3 by
reinterpretation. Dispatch by approved historical profile/anchor; old peers
unable to validate required new proofs remain incomplete/refuse that profile.

## 10. Exact byte examples and independent checks

These four PUBLIC curve arithmetic test points are not operational validator
keys, operator assignments or allocations. No private key was generated, loaded
or used in these arithmetic checks. Never use these known test points as live
authority. Repeated aa/bb/cc hashes below are synthetic encoding inputs, not a
valid genesis, agreement descriptor or block. The vote is unsigned and proves
no finality/agreement safety.

Exact J(M), **567 ASCII/UTF-8 bytes**; the display newline is NOT part of it:

```json
{"authority_profile":"static-genesis-v1","byzantine_fault_budget":1,"domain":"zoidbergchain/validator-set/v1","membership_version":1,"network_id":"zoidberg-authority-vector-v1","protocol":"zoidbergchain","protocol_version":2,"required_quorum":3,"validator_epoch":0,"validator_public_keys":["0279be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798","02c6047f9441ed7d6d3045406e95c07cd85c778e4b8cef3ca7abac09b95c709ee5","02e493dbf1c10d80f3581e4904930b1404cc6c13900ee0758474fa94abe8c4cd13","02f9308a019258c31049344f85f89d5229b531c845836f99b08601f113bce036f9"]}
```

```text
C = cb533c2c24bee22c38b16e5d1639e737be338c99e8e9fa895e75ec101c781869
```

In that key order the derived IDs are:

```text
0x7e5f4552091a69125d5dfcb7b8c2659029395bdf
0x2b5ad5c4795c026514f8317c7a215e218dccd6cf
0x1eff47bc3a10a45d4b230b5d10e37751fe6aa718
0x6813eb9362372eef6200f3b1dbc3f819671cba69
```

Exact unsigned J(E), **765 ASCII/UTF-8 bytes**:

```json
{"domain":"zoidbergchain/finality-authority/v1","network_id":"zoidberg-authority-vector-v1","object_type":"finality-authority","payload":{"agreement_profile_digest":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","attestation_version":3,"block_hash":"cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc","block_height":1,"genesis_hash":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","parent_hash":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","round":0,"step":"commit","validator_epoch":0,"validator_id":"0x7e5f4552091a69125d5dfcb7b8c2659029395bdf","validator_set_commitment":"cb533c2c24bee22c38b16e5d1639e737be338c99e8e9fa895e75ec101c781869"},"protocol":"zoidbergchain","protocol_version":2}
```

```text
SHA-256(J(E)) = 9b26622038b9add5e3474c4ee125f2e1d8747d6655acc0c8003a0914f937d871
EIP-191 prefix hex = 19457468657265756d205369676e6564204d6573736167653a0a373635
Keccak-256(prefix || J(E)) = 0c198fc1fd525a7cb765df518f721ff158e55b1cf2508f6c266c4279e8f5fb40
```

Reproduce from literal JSON lines: Python
`json.dumps(obj,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode('utf-8')`
then `hashlib.sha256(raw).hexdigest()`. JavaScript recursively sorts object keys,
uses JSON.stringify for scalar/key spelling and comma/colon joins, then
`crypto.createHash('sha256').update(Buffer.from(text,'utf8')).digest('hex')`.
Reverse object insertion order before canonicalizing; add no newline. Plain
JSON.stringify does not sort keys. This restricted ASCII/integer example is not
full Unicode/parser cross-language conformance.

Actual CPython and Node.js checks independently reconstructed both canonical
serializations and SHA-256 hashes. Node OpenSSL and Python cryptography also
decoded/recompressed all four public points. Address derivation and EIP-191
Keccak were computed in Python, **not independently checked in another language**;
those remain future vector obligations. No signed golden package was approved
and no existing golden vector was modified.

Exhaustively checked **469 ordered quorum pairs** for `(N,q)=(3,2),(3,3),(4,3),
(7,5),(1,1),(2,2)`, confirming all minimum overlaps with attaining witnesses.
Separately enumerated all f=0..N-1 and q=1..N for N=1..128: feasibility iff
`N>=3f+1`, minimum feasible q `(N+f)//2+1`. These are set/hash diagnostics, not
new implemented consensus/security tests.

## 11. Future security tests and golden-vector plan

All rows are FUTURE acceptance requirements, not new tests implemented/run here.

| Family | Positive / negative oracle |
| --- | --- |
| Membership bytes | Exact M/C independently agrees. Different source insertion orders sort identically; permuted received key arrays reject. Reject duplicate keys/IDs, invalid/off-curve/infinite/noncompressed keys, uppercase, extra/missing/duplicate fields, floats/bools, wrong f/q/N and empty roster. |
| Genesis binding | Full approved G2 authenticates M/C/policy. Changing key/C/network/protocol/profile rejects pinned G. Same M at another G rejects old votes. Missing manifest/policy is incomplete; admin replacement cannot repair authority. |
| Signature/identity | Registered key/ID succeeds. Unauthorized valid key, substituted ID, wrong purpose/domain, malformed r/s/v, SHA3 for Keccak and SHA-256 for EIP-191 reject. Valid signature variants/high-S add no weight. |
| Context/quorum | q unique authorized entries can pass only after agreement verification; q-1 remains partial. Duplicate ID/signature rejects offered QC; relay retry deduplicates. Mixed epochs/rounds/steps/targets/parents/A/C/protocol/NID/G reject; epoch1 always rejects. |
| Byzantine overlap | N4/q3 and N7/q5 overlap 2/3; within f every pair shares an honest identity. A QC may include one Byzantine N4 or two N7 signers; no verifier must guess who is faulty. Beyond bound, conflicting QC witnesses must be detected/retained/halted, not claimed prevented. Keep N3/q2/f1 negative witness. |
| Agreement/conflicts | Hidden commit/prepare QCs, incompatible cross-height finality without same-height double-sign, cross-round locks and view-change traces preserve approved protocol invariants. Invalid allegations do not latch; two verified incompatible decisions retain both and halt; same-target variants remain compatible. |
| Offline/partition | N4 one unavailable leaves participation capacity; two stall. N7 two leave capacity; three stall. Combine withholding with separate crashes and 3+1/2+2, 5+2/4+3 partitions, delay/duplicates/healing. Full protocol must converge after its synchrony assumptions hold; q online alone is no liveness oracle. |
| History/restart/sync | Separate fresh databases recover epoch0/C/V from G and validate required inventory, including same-tip sync. Wrong historical member/epoch/context rejects. Missing original/proof/policy is incomplete; corruption fails closed/refetches; cache rebuild reproduces verified cursor. |
| Signer/storage | Future signer tests kill pre/post reservation/sign/release, race processes, inject unknown commit/busy/full/I/O, clone/fencing and stale backup: no forbidden signature. Retain 7.17E receiver concurrency/commit checks and add authority/conflict reference checks. Published QCs cannot recover lost signer decisions. |
| Admin/emergency | Local config/DB/peer changes cannot substitute membership or lower q; no automatic revocation. New-network votes reject old context and vice versa; test reset isolation without resetting live state. Future transitions need separate old/new-epoch vectors. |
| Reviewer/resources | Complete agreement/authority/history proofs fit approved new caps; oversized inputs reject before crypto. Same finalized prefix independently replays identically; missing sources never imply zero penalties/usage; full MODEL A reconstruction remains mandatory. |

Future golden package: full genesis/policy bodies, M/C, point-to-ID vectors,
signature bytes/EIP-191 digests independently checked in two languages, A3/Q3
or explicitly amended engine proofs, field-mutation failures, partial/mixed/
conflicting proofs, restart transcripts and bounded resource accounting. Retain
old vectors with historical dispatch. Recalculate signing/message/proof caps
after agreement selection; old inert 1,024/1,536-byte finality and 262,144-byte
proof caps do not establish that the unspecified new engine fits.

## 12. Focused verification and final scope

Windows CPython **3.13.5**, SQLite **3.49.1**. Only existing targeted finality/
durability regressions ran, with workspace TEMP/TMP and disposable databases.
Ordinary test accounts do not provision operational validators.

```powershell
$env:TEMP=(Resolve-Path temp/task717f-runtime).Path
$env:TMP=$env:TEMP
.\.venv\Scripts\python.exe -B -m pytest tests/test_milestone_7_task_7_17e_finality_durability.py tests/test_milestone_7_task_7_17c_finality_audit.py tests/blockchain/test_task_3_5_validator_quorum_finality.py tests/blockchain/test_task_3_6_public_finality_status.py tests/blockchain/test_protocol_v1_lifecycle_finality.py -q --tb=short --basetemp=temp/task717f-finality --junitxml=temp/task717f-finality.xml
```

**73 passed in 19.06 s; no failures, errors or skips.** Evidence:
`temp/task717f-finality.log`, `.xml`: 36 current 7.17E durability cases,
17 preserved 7.17C diagnostics and 20 active quorum/status/lifecycle cases.
Historical defect cases use version-pinned pre-repair methods where documented;
passing them does not claim those repaired defects persist in production or
that distributed safety is achieved.

Arithmetic/byte evidence: `temp/task717f-arithmetic-python.log`,
`temp/task717f-arithmetic-node.log`; scratch JSON is unsigned. No broad suite,
external service or live chain store was used. Final scope/document checks are
recorded below.

Final branch/HEAD remain as section 1. Final index is unchanged with no staged
changes; worktree has exactly this new untracked document and the unstaged
15-line reference/status addition to 7.17D. Removing that addition reproduces
the original 7.17D body exactly. UTF-8/no BOM, final newline, all local document
links, literal JSON byte/hash checks and `git diff --check` pass. Source, tests,
schemas and existing golden vectors remain unchanged. No commit/push/merge.

## 13. Owner decisions and readiness

| Decision / gate | Status |
| --- | --- |
| Independent permissioned model | Recommended; **owner approval required**, including independence/common-control, key custody and cumulative historical compromise assumptions. No permissionless claim. |
| N/f/q and whitelist | Recommend **4/1/3**; evaluated larger alternative **7/2/5**. Both are proposals, not approved launch settings. N3/f1 cannot satisfy both inequalities. |
| Membership encoding | Static genesis M/C, epoch0, exact key identity/order/count and no live rotation specified for review, not implemented/activated. |
| Genesis/release | Complete G2/policy registry, agreement descriptor, actual NID/G/keys/operators and authenticated release distribution **PENDING/BLOCKED**. No launch allocations assigned. |
| Agreement and signer grammar | **BLOCKED** until complete reviewed distributed protocol, commit predicates, lock/round/view rules and finalized-parent or proved pipelined choice. Approve/amend A3/Q3 for that engine. Equations alone do not close this gate. |
| Emergency continuity | Approve static halt tradeoff, separately decide any restart/state disposition. No admin rewrite, automatic revocation or dynamic transition authority. |
| Storage/recovery/sync | 7.17E local durability reusable and regressions pass. Authority validators, fault latch, safe signer/fencing and proof/source sync remain future work. |
| Reviewer history | **BLOCKED** on full finality foundation and separately approved 7.17B history/admission/clock/selection/issuance semantics. No Task 7.17 resumption. |

**Task 7.17F documentation is ready for review and commit as a proposal** with
the named unresolved gates retained. No commit is made here.

**Can durable signer work proceed?** The authority namespace, membership
commitment, fault assumptions and reservation/release persistence requirements
can inform a separately authorized signer specification. A complete BFT signer
adapter/state machine is **not implementation-ready**: agreement selection,
lock/round/ancestry predicates, engine message/proof grammar and owner approval
remain prerequisites. A protocol-independent inert persistence specification
could be scoped separately without inventing commit/unlock rules; it is not
begun here. No live signer or anti-equivocation implementation is authorized.
