# Milestone 5 release-readiness report

Date: 2026-09-12  
Scope: Task 5.9 only; integrated adversarial validation, cross-node consensus verification, release audit, and final Milestone 5 decision. No protocol redesign, policy-constant change, commit, or push.

## Release decision

**PASS WITH NON-BLOCKING RISKS — MILESTONE 5 COMPLETE**

Every Milestone 5 acceptance criterion passes after one narrowly scoped recovery fix: portable export/import now preserves validator finality attestations and finalized-block evidence. Before that fix, a fresh SQLite node could not import valid certificate-v3 state because the imported certificate's finalized reviewer and certificate references were absent. The fix changes no protocol rule, identity, threshold, or historical record interpretation.

This is a Public Testnet v1 decision for SQLite-backed nodes with the pinned originality runtime and consistently configured Protocol v1 validators. It is not a claim of global authorship/originality, proof of personhood, production-scale capacity, or mainnet readiness.

## Repository and scope verification

| Item | Verified value |
| --- | --- |
| Branch | `Proof-of-Originality-Security-and-Reviewer-Reputation` |
| HEAD before and after Task 5.9 | `b6cd456cf4a1af3bf774ed7bb6faa28956e9aa62` (`task 5.8 done`) |
| Initial worktree | clean |
| Task 5.8 committed | yes, `b6cd456 task 5.8 done` |
| Tasks 5.1–5.8 in history | `0b53f84` (5.1/5.2), `5b84776` (5.3), `5ec94a9` (5.4 files/report; commit subject is mislabeled `task 5.5 done`), `711830b` (5.5), `4ae367f` (5.6), `b16bc63` (5.7), `b6cd456` (5.8) |
| Unrelated initial changes | none |
| Final worktree | four intentional Task 5.9 paths modified/untracked; no unrelated changes |
| Commits/pushes made | none |

All eight Task 5.x implementation reports were inspected together with the current code, schema, routes, tests, corpus scripts, and Git history. The report does not rely on README status claims.

Task 5.9 changes are `storage_tools.py`, `tests/test_milestone_5_task_5_9_release_readiness.py`, this report, and `docs/roadmap.md`.

## Implementation inventory

| Area | Current owner | Durable/canonical state |
| --- | --- | --- |
| Versioned Milestone 5 policy | `milestone5_policy.py` | canonical policy JSON/digests; reviewer state tables reference versions |
| Originality pipeline and evidence validation | `originality.py`, `blockchain.py` | `originality_evidence_records`, `originality_evidence_matches`, minted-media index and current document projection |
| Durable votes and uniqueness | `storage.py`, `blockchain.py`, `protocol_v1_originality.py` | `durable_vote_records`; partial unique accepted-vote index |
| Reviewer qualification, probation, promotion, snapshots | `services/reviewer_eligibility_service.py` | `reviewer_states`, `reviewer_state_transitions`, durable accepted votes |
| Certificate v1/v2/v3 identity and validation | `originality_certificate.py`, `protocol_v1_originality.py` | certificate section plus `originality_certificate_evidence_bindings` |
| Reputation and offense proof | `reviewer_reputation.py`, `blockchain.py` | `reviewer_offense_records`, `reviewer_penalties`, `reviewer_rate_limit_excess_attempts` |
| Peer verification/synchronization | `peer_sync.py`, `api_routers/peer.py` | authenticated peer transport plus locally revalidated evidence |
| Finality and reorg handling | `services/finality_service.py`, `services/canonical_reorg_service.py`, `blockchain.py` | `finality_attestations`, `finalized_blocks`, reorg-invalidated evidence/bindings |
| Advisory collusion projection | `services/collusion_analytics_service.py`, `api_routers/access.py` | recomputed only; no consensus table or peer message |
| Migration, backup, export/import | `storage.py`, `storage_migration.py`, `storage_tools.py` | idempotent SQLite DDL and portable snapshots |
| Public/peer/operations routes | `api_routers/content.py`, `api_routers/access.py`, `api_routers/peer.py`, `api_routers/operations.py` | frozen 139-route contract |
| Adversarial corpora/benchmarks | `scripts/task_5_3_adversarial_corpus.py`, `scripts/task_5_8_adversarial_corpus.py`, `scripts/task_5_8_analytics_benchmark.py` | reproducible generated reports; no consensus mutation |

## Protocol versions, identities, and locked constants

| Item | Value |
| --- | --- |
| Originality Rule | v1 |
| Originality evidence | v1 |
| Originality Rule v1 digest | `0be4f10129899a7da07da1fa5d07297b945d71065fc8474bcedb74a55dd497a5` |
| Certificate evidence profile | `milestone-5-certificate-consensus-v1` |
| Reviewer Policy | v1 |
| Reviewer Policy v1 digest | `ac6140446255e0d2a4f076f0d257a48d6a6a446dde2272a51568e8f020ee90eb` |
| Reputation Rule v1 | historical/inactive |
| Reputation Rule v1 digest | `9bfdfc196fd6d54796d699b513a550672b6e12d659b9dbb52f1e44b065be17fb` |
| Reputation Rule v2 | active |
| Reputation Rule v2 digest | `0605b0cbd81ee7f7dade23651f44d88473d752661470de0035925fdc5a1c7c12` |
| Offense evidence | v1 |
| Certificates | absent-version legacy, v1 historical, v2 evidence-bound historical/development, v3 active with finalized state |
| Vote weight | 1 for probationary and established reviewers |
| Review epoch | 5 finalized canonical blocks |
| Minimum wallet age | 3 review epochs |
| Creator qualification | 2 finalized/minted submissions |
| ZOID qualification | 5 finalized native transactions spanning at least 3 epochs |
| Mixed qualification | 1 finalized/minted submission plus 2 finalized native transactions |
| Probation | at least 3 epochs, at most 5 accepted votes/epoch, promotion after at least 10 valid probationary votes |
| Established rate limit | 25 accepted votes/epoch |
| Certificate-v3 quorum | 5 valid votes, including at least 1 established reviewer |
| Certificate-v3 approval | `original * 10000 >= (original + not_original) * 7000` |
| `UNSURE` | counts toward total valid quorum; excluded from decisive denominator |
| Equivocation escalation | 3-epoch cooldown, 10-epoch cooldown, then 25-epoch suspension |
| Self-vote escalation | 1-epoch cooldown, 3-epoch cooldown, then 25-epoch suspension |
| Rate-abuse proof/escalation | third unique excess attempt after proven quota exhaustion; then 1, 3, and 25 epochs |

Unknown rule/policy/certificate versions fail explicitly. No locked constant changed in Task 5.9.

## Acceptance traceability matrix

| # | Requirement | Implementation owner/module | Persistence | Test/audit evidence | Observed result | Status |
| ---: | --- | --- | --- | --- | --- | --- |
| 1 | Exact duplicate rejection before voting | `originality.py`, `Blockchain.evaluate_prevote_originality` | evidence/index tables; submission status | Task 5.3 plus Task 5.9 integrated lifecycle | exact minted bytes became `HARD_REJECTED` before any vote | PASS |
| 2 | Deterministic originality rule versioning | `originality.py` | rule version/digest in evidence | Task 5.3 golden digest and environment-isolation tests | identical v1 digest; unknown versions fail | PASS |
| 3 | Immutable evidence | `storage.py` | append-only evidence revisions and one-current index | Task 5.3 history/reorg/restart tests | old revisions retained; current revision unique | PASS |
| 4 | Evidence digest | `originality.py` | `canonical_evidence_digest` | Task 5.3 mutation/order tests | canonical recomputation matched; mutation failed | PASS |
| 5 | Cross-node evidence validation | `peer_sync.py`, `originality.py` | peer-revalidated evidence and media | Task 5.4 peer transfer; Task 5.9 reconstruction | independent validation and identical digest | PASS |
| 6 | Fuzzy review-only behavior | `originality.py` | evidence reason/match rows | Task 5.3 corpus; Task 5.9 derivative | fuzzy derivative flagged, never hard-rejected | PASS |
| 7 | Deterministic reviewer eligibility | `ReviewerEligibilityService` | reviewer state/history plus chain/votes | Task 5.5 two-node tests; Task 5.9 | same canonical state produced same class/status | PASS |
| 8 | Bootstrap mechanism | `milestone5_policy.py`, eligibility service | versioned policy provenance | Task 5.5 bootstrap test and code audit | only canonical policy grants bootstrap; current set empty | PASS |
| 9 | Strong probation | eligibility service | state transitions and accepted votes | Task 5.5; Task 5.9 | no earned-user bypass; duration and vote count both required | PASS |
| 10 | Promotion | eligibility service | state transition history | Task 5.5 restart test; Task 5.9 | 10 votes without duration did not promote; complete proof did | PASS |
| 11 | Rate limits | eligibility service, SQLite atomic admission | durable votes | Task 5.5 atomic quota and Task 5.7 hardened proof | 5/25 limits and reject-only first two excess attempts held | PASS |
| 12 | Vote weight = 1 | policy and tally/certificate code | vote records/snapshot | Task 5.5/5.6 plus code audit | one wallet contributed one unweighted vote | PASS |
| 13 | Fixed total quorum | `milestone5_policy.py`, certificate/evaluation | certificate v3 | Task 5.6 expiry/quorum boundaries | fewer than five never certified, including after expiry | PASS |
| 14 | Established-reviewer quorum | certificate v3 validation | snapshot/certificate binding | Task 5.6; Task 5.9 | one established vote required and reconstructed | PASS |
| 15 | Integer approval threshold | policy helper and certificate validator | `approval_threshold_bps` | Task 5.6 integer boundary/golden tests | 7000-bps integer comparison used | PASS |
| 16 | Self-vote rejection | vote operation/reputation validator | rejected vote/offense/penalty rows | Task 5.6 normalization, Task 5.7 public path, Task 5.9 | normalized creator self-vote rejected and evidenced | PASS |
| 17 | One-wallet-one-vote | SQLite partial unique index and vote handlers | `durable_vote_records` | Task 5.2, peer-vote tests, Task 5.9 replay | one accepted row per submission/wallet | PASS |
| 18 | Replay handling | vote identity/storage/reputation service | durable vote identity | Task 5.2/5.7 and Task 5.9 | identical signed replay was idempotent, quota-neutral, non-penalizing | PASS |
| 19 | Conflicting-vote evidence | vote operation and reputation service | rejected durable vote plus offense | Task 5.7 public/peer tests; Task 5.9 | second choice did not count; one canonical incident retained | PASS |
| 20 | Reputation rule versioning | `milestone5_policy.py` | versions in votes/offenses/certificates | Task 5.7 digest/history tests | v1 remains inactive; v2 active; unknown fails | PASS |
| 21 | Equivocation penalties | `reviewer_reputation.py` | offense/penalty/state transition tables | Task 5.7 escalation; Task 5.9 | deterministic 3/10/25 schedule and grouping | PASS |
| 22 | Self-vote penalties | reputation service | offense/penalty tables | Task 5.7 escalation; Task 5.9 | deterministic 1/3/25 schedule | PASS |
| 23 | Rate-abuse penalties | reputation service | quota votes, excess attempts, offense/penalty | Task 5.7 peer proof; Task 5.9 | quota and three unique excess identities required | PASS |
| 24 | Cooldown/suspension/restoration | reputation plus eligibility services | penalty/state history | Task 5.7 lifecycle tests | maximum active end retained; underlying class restored | PASS |
| 25 | Canonical offense evidence | `reviewer_reputation.py` | evidence digest/offense ID | Task 5.7 tamper tests; Task 5.9 | signatures, creator, reference, epoch, grouping and IDs recomputed | PASS |
| 26 | Peer offense verification | `Blockchain.receive_reviewer_offense_evidence`, peer route | local validated offense/penalty | Task 5.7 peer-rate test; Task 5.9 imported-node replay | peer state commands not trusted; proof reconstructed locally | PASS |
| 27 | Reviewer snapshot | eligibility service | certificate-bound digest/reference | Task 5.5/5.6; Task 5.9 | source/reconstructed-node snapshot digest identical | PASS |
| 28 | Certificate-v3 commitments | certificate/protocol modules | certificate and binding table | Task 5.6 and expanded Task 5.9 tamper matrix | evidence, policy, rule, snapshot, quorum, tally, vote-set, references and ID enforced | PASS |
| 29 | Historical certificate compatibility | certificate version dispatch | historical certificate rows unchanged | Task 5.4/5.6/5.7 | legacy/v1/v2 retain historical semantics | PASS |
| 30 | Collusion analytics isolation | analytics service and read-only routes | no consensus persistence | Task 5.8 plus Task 5.9 before/after state comparison | alerts changed no chain/vote/status/penalty/certificate state | PASS |
| 31 | Adversarial corpus reporting | Task 5.3/5.8 scripts | generated report only | scripts rerun in Task 5.9 | TP/TN/FP/FN reproduced and limitations retained | PASS |

## Cross-node deterministic consensus audit

Two independent SQLite-backed instances were exercised by the integrated Task 5.9 scenario. The source was restarted, exported, imported into a fresh target, and the target was restarted as a `Blockchain` node with the same validator set.

Identical results were observed for Originality Rule identity, evidence digest, exact-duplicate status, fuzzy review-only outcome, Reviewer Policy identity, review epoch, qualification, probation/established status, reviewer snapshot digest, Reputation Rule identity, offense IDs, penalty status/end, certificate-v3 vote-set hash/ID, and certificate validity. The imported rate-abuse offense was independently revalidated against the target's accepted quota history and returned idempotent duplicate acceptance.

Canonical sorting/golden tests cover Python mapping/list order; reference heights/hashes replace wall-clock inputs for consensus state; certificate OCR is deterministically unavailable; and request order is removed from canonical vote/offense sets. No process cache, local filesystem enumeration order, arbitrary environment threshold, or request-arrival ordering changed a tested consensus result.

## Fresh-node reconstruction and recovery

The scenario reconstructed chain/media metadata, originality evidence, reviewer states/transitions, accepted votes, reviewer snapshots, certificates, offenses, penalties, finality attestations, and finalized-block evidence in a fresh SQLite database. The target passed storage integrity, reproduced the source evidence/snapshot/certificate identities, kept the exact duplicate hard-rejected, retained cooldown state, and validated the historical certificate after later penalties.

Finding and fix: `storage_tools._load_state`, `_write_state_to_backend`, and `import_storage` previously omitted `finality_attestations` and `finalized_blocks`. Import therefore failed correctly when certificate-v3 referenced missing finality. Task 5.9 added those two sections to the portable snapshot schema and regression scenario. No historical data is fabricated.

Physical SQLite backup/reopen, portable backup/export/import, JSON-to-SQLite migration, and idempotent schema startup remain covered by the storage and milestone suites. JSON remains a development compatibility backend; Public Testnet v1 Milestone 5 durability requires SQLite.

## Adversarial findings

### Exact-duplicate attack matrix

| Path/attempt | Result |
| --- | --- |
| Local low-level submission | canonical pre-vote evaluation produced `HARD_REJECT` |
| Public HTTP submission | route delegates to the same facade operation; route/lifecycle tests confirm no later evaluate/mint bypass |
| Peer submission/evidence | peer handler recomputes against local canonical media before acknowledgement; tampered or mismatched evidence fails |
| Legacy submission evaluated later | `ensure_current_originality_evidence` screens before vote/evaluate/certificate transition |
| Restart/recovery | hard-rejected status and immutable evidence survived restart |
| Post-sync/fresh node | reconstructed target retained the same hard rejection/evidence |
| Vote/certificate/queue/block attempts | vote and queue rejected; no certificate; hard-rejected mint path rejects |

Only an exact SHA-256 match to previously certified canonical minted media hard-rejects. Pending-submission matching remains outside Originality Rule v1.

### Fuzzy originality corpus

| Layer | TP | TN | FP | FN |
| --- | ---: | ---: | ---: | ---: |
| Exact hard reject | 3 | 15 | 0 | 0 |
| Fuzzy review flag | 8 | 4 | 2 | 1 |

JPEG recompression, resize, small crop, brightness/color changes, metadata-only changes, same normalized text, and the OCR-preserving edit flagged. Border addition remained the observed false negative. Same-template materially different text and the posterized/visually similar meaningful alteration accounted for the two diagnostic false positives. Generic phrases on unrelated imagery did not flag. Thresholds were not tuned during Task 5.9.

### Vote integrity and reviewer lifecycle

Creator address case normalization, public/peer equivalence, replay idempotency, rejected conflicting evidence, one equivocation incident per reviewer/submission/content group, deterministic escalation, quota consumption, accepted-quota proof, three unique excess attempts, replay exclusion, and peer reconstruction all passed.

The focused lifecycle tests cover `NEW -> PROBATIONARY_REVIEWER -> ESTABLISHED_REVIEWER -> COOLDOWN -> restored class -> SUSPENDED -> restored class`. The integrated scenario covered earned probation, promotion, active cooldown, restart, and historical certificate validity. Versioned bootstrap grants behave as established and cannot be sourced from local allowlists. Unfinalized changes do not affect finalized epochs; multiple penalties use the maximum active end and cannot shorten ineligibility.

### Certificate-v3 adversarial audit

Validation failed deterministically for wrong evidence digest/reference, hard-rejected evidence, wrong snapshot digest, fake established count, wrong reviewer/reputation versions, altered quorum constants/approval threshold, incomplete or extra vote sets, altered choice, legacy/null-field votes, ineligible/penalized historical reviewers, wrong certificate reference, altered tallies/vote-set hash, and wrong certificate ID. A reviewer penalized only at a later finalized snapshot did not invalidate the earlier valid certificate. Historical v1/v2 certificates retained their version-specific rules.

## Reorg/finality audit

Originality evidence, certificate reference, reviewer snapshot, and certificate bindings are checked by exact height/hash. Stale unfinalized bindings are invalidated and recomputed through the existing canonical-reorg service; finalized history remains protected by the established fork-choice/finality boundary. Reviewer qualification and penalties derive from finalized epochs, so shallow unfinalized forks cannot cause epoch/status oscillation. Task 5.9 added no fork-choice rule.

## API and security boundary audit

- Public reviewer endpoints are read-only; there is no public reputation/status mutation route.
- Analytics endpoints are GET-only, return `non_consensus: true`, and invoke a read-only projection.
- Peer submission, vote, evidence, certificate, offense, and block routes retain peer authentication/registration/network checks.
- Peer offense payloads carry evidence, not state commands; local validation derives any penalty.
- Admin and development operations remain in their dedicated authenticated/environment-gated routers.
- Originality/content APIs omit local filesystem paths; peer metadata ignores supplied local paths.
- Environment allowlists can refuse or permit local API access but cannot create canonical reviewer eligibility or bootstrap provenance.
- The frozen route contract parses as valid JSON with 139 rows and matches the generated OpenAPI operation set.

## Consensus configuration audit

| Classification | Inputs | Finding |
| --- | --- | --- |
| CONSENSUS VERSIONED | Originality Rule v1; Reviewer Policy v1; Reputation Rules v1/v2; offense evidence v1; certificate v1/v2/v3; fixed v3 quorum and 7000-bps threshold | canonical modules/digests; no environment override |
| LOCAL ACCESS POLICY | `REVIEW_ELIGIBILITY_MODE`, review allow/deny lists, local activity thresholds, daily local review cap, `REQUIRE_ACCESS_FOR_VOTES`, HTTP vote/evaluate/mint rate limits | may refuse local service; cannot grant or alter v3 consensus validity |
| DEVELOPMENT-ONLY | development vote tooling, no-finality compatibility issuance/evaluation, dev repair/reset routes | not a Public Testnet v1 consensus path; environment-gated |
| LEGACY HISTORICAL | dynamic active-user quorum (`MIN_VOTE_FLOOR`, active-user percentage), floating `ORIGINALITY_APPROVAL_THRESHOLD`, certificate v1/v2 semantics | retained only for historical/no-finality compatibility; v3 ignores dynamic quorum and uses integer policy |
| DEPLOYMENT-CRITICAL NETWORK CONFIG | `PUBLIC_TESTNET_V1_VALIDATOR_ADDRESSES` | pre-existing Protocol v1 finality validator set; recorded in finality evidence and must be identical across the deployment |
| UNSAFE / BLOCKING | none found for Milestone 5 v3 validity | no untracked originality/reviewer/quorum/reputation/certificate environment override found |

Voter-reward environment settings affect optional reward planning, not certificate-v3 vote weight, reviewer eligibility, quorum, or originality validity; reward metadata remains independently checked by the existing block/ledger tests.

## Dependency reproducibility

| Dependency/runtime | Required | Observed | Consensus behavior |
| --- | --- | --- | --- |
| Pillow | 12.3.0 | 12.3.0 | exact match required by `certificate_fuzzy_runtime_identity()` |
| ImageHash | 4.3.1 | 4.3.1 | exact match required by the same guard |
| pytesseract wrapper | 0.3.13 | 0.3.13 | pinned; not executed for certificate consensus |
| Tesseract executable/trained data | not a certificate-v1 consensus input | not installed/on PATH | deterministically represented as unavailable/review-only |

`requirements-originality.txt` pins all three Python packages. A Pillow/ImageHash mismatch raises before certificate-bound fuzzy evaluation. Tesseract is never silently executed in the current certificate profile; a future OCR-consensus rule would need content-addressed executable and trained-data identity.

## Collusion analytics isolation and corpus

| Observation | Result |
| --- | ---: |
| True-positive suspicious cases | 3 |
| True-negative clean cases | 2 |
| False-positive alerts | 0 |
| False-negative cases | 0 |

These are synthetic corpus observations, not real-world detection guarantees. The integrated scenario captured chain, votes, certificates, reviewer states, offenses, and penalties before and after analysis and proved byte-for-byte logical equality. Alerts are not stored in consensus tables or transferred between peers; deleting/recomputing them cannot alter validity.

## Performance observations

| Workload | Observed result |
| --- | --- |
| Originality deterministic Hamming index | 10,000 records built in 0.0194s; 1,000 radius-8 queries in 3.8044s (262.9 queries/s) |
| Originality scaling characteristic | deterministic BK-tree; typical pruning, pathological dense corpus may degrade to linear; index rebuild is linear |
| Reviewer/vote SQLite workload | 200 reviewer states plus 3,000 durable votes written in 12.8674s; full read in 0.0226s; restart plus full read in 0.0213s |
| Collusion analytics | 200 reviewers, 3,000 votes, 200 submissions; 3,202 advisory alerts in 0.0669s |
| Integrated lifecycle | complete 41-block scenario passed in 5.99s; the certificate-commitment tamper expansion passed in 24.32s; the final rerun including direct invalid vote-set cases passed in 6.87s |

These are local diagnostic measurements, not capacity claims. No obvious Public Testnet correctness blocker appeared. The main scaling risks are worst-case fuzzy lookup/rebuild, per-vote SQLite write overhead, historical status ancestry scans, and quadratic pair generation per submission in collusion analysis.

## Verification record

All pytest runs used workspace-local base temporary directories.

| Gate | Result | Runtime |
| --- | --- | ---: |
| New Task 5.9 integrated/adversarial scenario | 1 passed | 6.87s final expanded rerun |
| Tasks 5.3–5.8 focused suites | 69 passed | 7.10s |
| Task 5.9 + storage export/import + reputation regression | 40 passed | 18.41s |
| Protocol/golden vectors | 68 passed | 0.77s |
| Peer/two-node suites | 112 passed | 13.62s |
| Reorg/finality suites | 39 passed | 3.08s |
| Storage/migration/export/import plus Task 5.2 | 100 passed | 18.56s |
| Complete API suite | 445 passed | 59.82s |
| Definitive full backend suite | **1,152 passed** | **707.01s (11m47s)** |
| Originality and collusion corpus scripts | reproduced expected reports | completed |
| Collusion scale benchmark | 200 reviewers / 3,000 votes / 200 submissions | 0.0669s |

Python compilation passed for root modules, routers, services, scripts, and tests, and the two changed Python files passed a final explicit compilation check. The repository hygiene/security script passed. All 12 tracked JSON fixtures parsed successfully; the unchanged 139-row route contract also passed its exact contract test. `git diff --check` passed; Git emitted only informational LF-to-CRLF working-copy warnings.

## Remaining non-blocking risks

1. Fuzzy originality has observed false positives and a border-addition false negative. This is acceptable only because Rule v1 is review-only for fuzzy results.
2. Collusion alerts can mistake correlated honest behavior and cannot detect private coordination with no observable linkage. They remain advisory.
3. The canonical bootstrap-established reviewer set is empty. Earned established reviewers can satisfy the protocol, while operational launch planning may still choose to version an approved bootstrap list.
4. SQLite is mandatory for the claimed durable vote/evidence/reputation constraints; JSON remains development compatibility only.
5. Peer offense delivery can be order-dependent operationally: rate-abuse proof must arrive after the peer has the canonical accepted quota history. Failure is safe and retryable, not a validity shortcut.
6. Validator-set configuration and pinned Pillow/ImageHash wheels must match across Public Testnet nodes. Startup/runtime guards reject malformed validator settings and originality dependency mismatches.
7. Historical reviewer reconstruction scans canonical ancestry; fuzzy index rebuild is linear; collusion pair generation is quadratic within each submission. These are monitored scale risks, not observed correctness failures at the tested sizes.
8. Tesseract OCR is intentionally unavailable in certificate consensus. This reduces detection coverage but prevents platform-specific OCR from splitting consensus.

## Final acceptance criteria

All twenty final acceptance criteria pass: exact duplicates are rejected before voting; deterministic reviewer eligibility/weight, vote integrity, auditable penalties, originality-bound certificates, measured FP/FN reporting, fuzzy review-only semantics, immutable evidence, multiple qualification paths, strong probation, one-wallet-one-vote, fixed/established quorum, v3 state binding, objective canonical offenses, non-penalizing replay, historical status reconstruction, alert-only analytics, independent peer validation, deterministic non-destructive migration/recovery, and the complete relevant backend suite.

**PASS WITH NON-BLOCKING RISKS — MILESTONE 5 COMPLETE**
