# Milestone 7 Task 7.14 — Isolated v2 admission evidence issuance

Date: 2026-10-20 (America/New_York). Protocol v2 / block v3 remain inactive.

## Repository verification and scope

- Branch: `Compression-State-Bloat-and-Node-Economics`.
- Starting HEAD: `b6c85ff11a6dd5fbc76db0a7335ff8579695488c`, separately committed
  Task 7.13, `integrate isolated v3 admission and block construction`.
- Initial worktree clean. No repository or ancestor `AGENTS.md` found.
- Before implementation, the existing Task 7.13 admission/construction and
  Task 7.10C schema/signing/canonical suites passed: **187 passed, 264.62 s**.
- Read the [closed schema](milestone-7-v3-canonical-schema-decision.md),
  [signing contract](milestone-7-v3-signing-and-domain-separation.md),
  [canonical implementation](milestone-7-v3-block-format-implementation.md), and
  [admission/construction report](milestone-7-v3-admission-and-block-construction.md).

Changes are limited to new `canonical_v3/issuance.py`, the additional offline
entry point in `canonical_v3/construction.py`, focused tests, a versioned golden
manifest, and this report. No historical test/vector, active source, configuration,
dependency, database schema, codec or production identity changes. No commit,
push, merge, deployment, reset, migration or subsequent task.

## Existing authoritative lifecycle

1. Upload operations in `services/content_coordination_service.py` accept exact
   image bytes or policy-canonical UTF-8 text after
   `media_technical_validation.validate_media_bytes`. SHA-256 of those accepted
   bytes is original-media identity. Filenames and compression are not identity.
2. `WalletAuthManager` supplies a signed submission challenge.
   `Blockchain.submit_signed_content_operation` verifies the creator's signature,
   submission/hash, media policy, technical digest and nonce. Review calls
   `require_valid_submitter_attestation`; technical acceptance alone grants no
   review or mint permission.
3. `Blockchain.cast_signed_submission_vote_operation` verifies the review
   challenge, dimension/choice, signer and context. Creator votes fail. An exact
   live retry is idempotent; conflicting same-dimension votes fail. Accepted and
   rejected signed observations and their lifecycle remain durable storage data.
4. `ReviewerEligibilityService` resolves earned probation/established status
   from finalized ancestry and durable history. `ReviewerReputationService`
   applies existing cooldown/suspension rules. Vote admission enforces existing
   daily/epoch quotas. Both dimensions of one submission consume one review
   participation; an already accepted other dimension is not a second quota
   charge. `status_at_reference` reconstructs historical status rather than
   trusting the producer's current status label.
5. `dual_review.verify_vote_record`, `tally` and `combined_review` verify signed
   inputs and derive two independent integer decisions. Each dimension needs
   five eligible votes, including one established reviewer, and a nonzero
   decisive denominator. Unsure counts toward quorum/participation, not approval.
6. `Blockchain.evaluate_submission` leaves unresolved reviews awaiting review;
   rejected/invalid admission is quarantined. Positive dual review freezes
   `build_admission_certificate`, which independently validates the complete
   source certificate. The existing v1 builder projects its historical fields
   and deduplicates identical records; new v2 issuance rejects all duplicates.
7. Submission persistence stores the frozen admission certificate. Peer/block
   verification rechecks its bytes, media, attestation, votes and reviewer
   history. Queue/manual-block, reward, duplicate claims and atomic commit
   checks still govern mining. Finality and canonical selection are separate
   authorities; a positive admission outcome is not finalized chain history.

No stage above is modified. Historical v1 certificates remain v1 evidence.

## Isolated issuance preconditions and trusted sources

`EvidenceIssuer` requires an existing `AdmissionAdapter` configured with explicit
`TestOnlyConfig(context, True)` and an adapter-issued `PreparedAdmission`.
The adapter already revalidates original bytes, technical observations and the
complete original v1 admission, including its original signatures. Hand-built
prepared objects and claimed original-media duplicates cannot enter issuance.

`technical_for` retains every accepted technical observation, replaces only
the new media-policy fields, and recomputes the technical digest **before** new
signatures are supplied. `attestation_from_signature` assembles the closed
attestation from a fresh signed payload and supplied signature.
`vote_from_signature` assembles the closed vote from exact signed message bytes,
a supplied signature and historical reference. Both reconstruct and verify the
approved signing bytes; neither contains a key or signs anything. Legacy
signatures cannot be relabelled or promoted.

Two required trusted harness dependencies receive the complete explicit
`Context`, including N/W/G and both policy digests:

- `frozen_votes(ctx, submission_id, original_hash)` returns immutable canonical
  bytes of the **entire** authenticated selected v2 vote snapshot, in approved
  order, or `None` for unavailable history. Every selected vote must be supplied;
  even a still-qualifying subset fails. The issuer does not invent a production
  bounded-selection algorithm or discard unfavorable/oversized inputs.
- `reviewer_decision(ctx, vote)` returns a typed `ReviewerDecision(status,
  eligible)` or `None` for missing history. The trusted binding must establish
  the reference on the pinned chain ancestry, historical status, existing
  penalty and accepted-participation/quota rules. Uploaded `reviewer_eligible`
  or status fields are insufficient. The callback receives a detached vote and
  cannot mutate the verified certificate.

These are explicit offline authorities, not peer-provided booleans. Fixtures
use only symbolic `zoidberg-signing-vector-v2`, G=`a` repeated 64 times, and
policy digests `b`/`c` repeated 64 times. Their snapshots are deterministic test
oracles, not a new v2 production history service. No live source registration,
reviewer-signature issuance or certificate persistence is added.

## Closed schemas, canonical bytes and signing preimages

Reuse `canonical_v3/evidence.py` and the frozen schema without new wire fields:
technical evidence has 17 fields; attestation has 14 record fields and a 17-key
payload; each vote has 23 fields; each dimension tally has 14 fields.
The certificate has exactly these 18 required fields:

```text
certificate_version, network_id, submission_id, content_hash, creator_wallet,
policy_id, policy_version, policy_digest, technical_evidence_version,
technical_evidence, attestation_version, attestation, review_policy_version,
review_policy_digest, votes, originality, admissibility, certificate_digest
```

Version values are certificate=2, protocol=2, review policy=2, vote=3,
technical/attestation/statement=1, reviewer policy=1, reputation rules=2.
Unknown/missing/null/incorrectly typed fields reject. Text technical dimensions
remain required nulls. No additional producer signature or envelope is invented.

Let `J` be the frozen compact sorted-key UTF-8 JSON with exact scalar values.
All standalone byte inputs must already equal J; no repair/normalization occurs.
Attestation and vote signatures are canonical 65-byte secp256k1 `personal_sign`
signatures with recovery byte 27/28 and the existing high-S acceptance rule.

```text
H = SHA256(accepted_original_bytes)
technical.evidence_digest = SHA256(J(technical minus evidence_digest))

E_rights = {domain: "zoidbergchain/submitter-attestation/v2", network_id: N,
            object_type: "submitter-attestation", payload: closed_payload17,
            protocol: "zoidbergchain", protocol_version: 2}
M_rights = J(E_rights)
canonical_payload_digest = canonical_message_hash = SHA256(M_rights)

V = {domain: "zoidbergchain/community-review/v3", network_id: N,
     vote_version: 3, policy_version: 2, policy_digest: review_policy_digest,
     reviewer_policy_version: 1, reputation_rule_version: 2,
     wallet_address, submission_id, content_hash, dimension, choice,
     nonce, issued_at, expires_at}
M_vote = J(V)  # flat 15-key payload; no additional protocol_version/envelope
signed_message_hash = SHA256(M_vote)
vote_identity = SHA256(J({payload: V, signature: exact_supplied_Sig65}))

D_sign(M) = Keccak256(0x19 || ASCII("Ethereum Signed Message:\n")
                     || ASCII_decimal(len(M)) || M)

vote_set_digest = SHA256(J(wallet-sorted [{wallet, choice, identity, status}, ...]))
certificate_digest = SHA256(J(certificate minus certificate_digest))
```

Recovered signers must equal canonical wallets. The original H, submission and
creator/attestation binding must match the adapter's validated source. Both
policies, network, purpose, versions and exact technical digest are checked.
Vote identity additionally authenticates the supplied signature. Issue sorts
the complete input by `(dimension, voter_wallet_address, vote_identity)`;
received certificates with different order reject. Any repeated
`(dimension,wallet)`, including identical or high-S-equivalent votes, rejects.
Repeated offline issuance of the same complete inputs intentionally produces
the same bytes and commitment. It does not consume a live challenge or authorize
a second mint; durable challenge/canonical replay enforcement remains outside
this offline component.

The approved admission signing schemas bind N and policy context; they do
**not** contain a directly signed `genesis_hash`. No such field is added here.
G scopes the trusted snapshot/ancestry dependencies and the immutable verified
result's context; the bridge rejects a result from a different context and
reverifies its bytes/history. This is not a claim that admission signatures
alone distinguish two roots with reused N and identical policies. The frozen
contract forbids N reuse, and Task 7.10B directly binds G in native U10/T18.
A direct-G admission signing amendment would require an explicit new schema
decision rather than silently changing signed bytes in Task 7.14.

References identify historical blocks only. Neither signatures nor certificate
contain their future containing block hash. Certificate/media/native evidence
precede block hashing; finality signs the later block hash separately. No cycle.

## Exact tally and rational behavior

For each dimension independently: `p` positive, `n` negative, `u` unsure,
`t=p+n+u`, `e` established, `d=p+n`. All arithmetic is bounded integer arithmetic.
Quorum is `t>=5 and e>=1`; positive resolution requires `d>0` and
`p*10000 >= d*7000`. No new reputation rule, weight or threshold is introduced.
The existing canonical tally derivation is reused and every supplied tally is
recomputed during verification.

Both block summaries retain the same reduced originality fraction:
`{numerator: p/gcd(p,d), denominator: d/gcd(p,d)}`. Five of seven is exactly
5/7; two decisive positives plus three unsure votes is exactly 1/1 with quorum.
No float or decimal rounding enters evidence or block bytes. Zero decisive
votes, including all-unsure, have no rational summary and cannot yield a
certificate. Nonreduced, incorrect or bool-valued block summaries reject.

## Construction bridge and size checks

`issue` produces an immutable `VerifiedCertificate(context, certificate_bytes)`.
Its accessors return fresh objects. `verify` accepts bounded canonical bytes,
checks the complete certificate and original/technical bindings, and rechecks
both trusted sources independently of the construction state.

`BlockConstructionBridge.construct_issued` requires the same issuer/adapter,
checks result context and **reverifies** certificate bytes and history. A
hand-built result wrapper is not an acceptance shortcut. Missing/incomplete
issuance returns `IncompleteConstruction`; otherwise the existing `construct`
performs its unchanged parent/ledger/reward/reviewer checks, complete block
serialization, component budgets and strict isolated original reconstruction.
The previous explicit-certificate construction entry point remains available
for its existing offline tests; no active route calls either entry point.

The same certificate works under identity/1 and zstd/1: original H and certificate
digest remain equal while encoded descriptor/block hashes differ. Required
certification is never dropped for optional native transfers. The tests also
exercise maximum 262,144-byte text under identity, ten real signed transfers,
the 612,121-byte reservation, and retry with no optional transfers after an
invalid optional selection. The unchanged analytic maximal-image reservation
is 3,058,797 bytes, leaving 86,931 bytes below 3 MiB. Complete certificate cap
is 196,608 bytes, vote cap 4,096 bytes, attestation cap 16,384 bytes. The per
dimension vote cap 16 and total cap 32 remain mandatory. Synthetic C-1/C/C+1
final-size gates are identified as instrumentation, not valid 3 MiB records.
The current application image limit remains 256 KiB; it is not raised to 2 MiB.

## Failure classifications

| Result | Meaning |
| --- | --- |
| `IncompleteEvidence` / `IncompleteConstruction` | Absent fresh attestation/votes, unresolved dimension (quorum/established/decisive requirements), missing authenticated snapshot or historical reviewer decision. No certificate/record. |
| `IntegrationError(INVALID_CANONICAL, code)` | Malformed/oversized/legacy input, bad signature/context/identity, duplicate/conflicting vote, self-vote, omitted selected vote, ineligible/mismatched reviewer, negative resolved review, incorrect tally/digest/canonical representation or budget failure. |
| `IntegrationError(LOCAL_FAILURE, code)` | Trusted lookup exception or invalid callback contract, unexpected local operation failure. Exception causes retained; never silently accepted or downgraded. |
| Existing adapter failure | Unissued/claimed original or invalid source admission remains `INVALID_ADMISSION`; worker/lookup failures retain existing local/incomplete classifications. |

During issuance an insufficient review is incomplete. A supplied complete
certificate falsely claiming qualification is invalid. Present invalid inputs
are checked before returning missing-other-input results. Missing trusted
history cannot become affirmative eligibility. No local error is persisted in
canonical evidence or treated as a production consensus verdict.

## Golden vectors and verification

`tests/fixtures/milestone_7_v2_issuance_v1/manifest.json` freezes the existing
Task 7.10C positive fixture as an immutable external issuance oracle; the old
fixture is unchanged. It records source checksum, complete certificate length
and checksum, body commitment, technical checksum, exact 5/7 ratio, and all 15
manual EIP-191 Keccak digests (creator plus fourteen signed dimension votes).

The issuer recreates the closed attestation/vote records from supplied signed
inputs and reproduces the **31,552-byte** certificate byte for byte:

```text
SHA256(complete_certificate) = cffca5d8239e47644b77f43baf7412c620e83a7cf291f4278ba3ff2c3df7edf5
certificate_digest          = 91d514aa80c2c7fd24835aff551788b2882f7d7e8f2e05cd31fc7bfd036de8a2
```

Tests use independent standard-library JSON/SHA preimages and manual EIP-191
prefix construction. All fifteen signatures additionally verify through
OpenSSL-backed ECDSA with the published fixture scalars, independently of the
issuer's Ethereum wallet-recovery path. No newly invented signature or padded
fake vote fills a vector or capacity boundary.

Final verification on Windows with the repository `.venv`:

| Selection | Result |
| --- | --- |
| Pre-edit Task 7.13 + Task 7.10C baseline | **187 passed, 264.62 s** |
| Initial focused issuance selection, before record-builder and additional capacity tests | **49 passed, 77.00 s** |
| Final Task 7.14 + Task 7.13 + Task 7.10C + Task 7.11 + Task 7.12 selection | **319 passed, 272.62 s** |
| Historical Milestone 6 attestation/review/admission, Milestone 5 eligibility/certificates/reputation, originality certificates, certificate blocks and v1 protocol selections | **239 passed, 105.45 s** |

The final canonical selection includes **all 60 new Task 7.14 cases**. Its
JUnit report is disposable `temp/task714-final-results.xml`. Baseline and
initial focused runs overlap the final selection and must not be added as
distinct coverage. The two final selections cover **558 passing cases** with
no skips or failures. Full-repository testing and cross-platform execution
are not claimed.

The sandboxed historical run was stopped at the previously documented
TestClient loopback-socket stall. The expanded canonical run was moved to the
same API-capable host environment because it includes Task 7.12's HTTP case.
Both final selections ran there with unchanged assertions and isolated test
state; no sandbox or decoder restriction was weakened in source. Process-local
TEMP/TMP points to `temp/task714-runtime` and test state stays under `temp/`.

Reproduce the focused and final canonical selection from the repository root
in an API-capable test environment:

```powershell
New-Item -ItemType Directory -Force temp/task714-runtime | Out-Null
$env:TEMP=(Resolve-Path temp/task714-runtime).Path
$env:TMP=$env:TEMP
.\.venv\Scripts\python.exe -B -m pytest tests/test_milestone_7_task_7_14_issuance.py -q --tb=short --basetemp=temp/task714-focused-recheck
.\.venv\Scripts\python.exe -B -m pytest tests/test_milestone_7_task_7_14_issuance.py tests/test_milestone_7_task_7_13_admission.py tests/test_milestone_7_task_7_10c_v3.py tests/test_milestone_7_task_7_11_storage.py tests/test_milestone_7_task_7_12_image_admission.py -q --tb=short --basetemp=temp/task714-canonical-recheck
.\.venv\Scripts\python.exe -B -m pytest tests/test_milestone_6_task_6_4_submitter_attestation.py tests/test_milestone_6_task_6_5_dual_review.py tests/test_milestone_6_task_6_6_admission.py tests/test_milestone_5_task_5_5_earned_reviewer_eligibility.py tests/test_milestone_5_task_5_6_certificate_v3.py tests/test_milestone_5_task_5_7_reviewer_reputation.py tests/submissions/test_originality_certificate.py tests/blockchain/test_certificate_block_validation.py tests/test_protocol_v1.py tests/test_protocol_v1_golden_vectors.py tests/test_protocol_v1_native_transfers.py tests/test_protocol_v1_originality_votes.py tests/blockchain/test_protocol_v1_block_format.py tests/blockchain/test_protocol_v1_genesis.py -q --tb=short --basetemp=temp/task714-historical-recheck
```

Python syntax, all five files' UTF-8/trailing-whitespace/final-newline checks,
manifest JSON parsing and `git diff --check` pass. Starting branch and HEAD
remain unchanged. The worktree has only the intended unstaged construction
change and four untracked deliverables (issuer, tests, manifest and report).
No active module imports the isolated package, verified by the nonactivation
tests. Historical assertions and vectors are unchanged. Active v1/v2 behavior
and consensus/finality remain unchanged within the tested regression scope.

## Remaining production activation requirements

No Task 7.14 implementation blocker is identified within the frozen contract.
Production activation still needs approved N/W/G and immutable policy/statement
registry; authenticated v2 full-snapshot selection and reviewer history/quota
bindings; fresh user-authorized signing/client/challenge and durable replay
integration; approved image-policy sizing; queue/manual-block and atomic
original/submission/certificate/reward claims; reviewed decoder/platform
containment; and explicit consensus/finality, networking and persistence
integration. The offline source callbacks and candidates grant none of those
authorities. No real production certificate is issued by this task.

**Task 7.14 is ready for review and a later authorized commit.** No commit was
performed; production activation and subsequent tasks were not started.
