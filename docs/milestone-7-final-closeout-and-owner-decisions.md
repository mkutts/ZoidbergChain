# Milestone 7 Task 7.24 — Final compression closeout and owner decisions

Date: **2026-11-03, America/New_York**. Documentation and bounded verification only.

**Task 7.24 documentation/handoff: COMPLETE. Original Milestone 7 acceptance: INCOMPLETE. Production/network activation: BLOCKED.** The metadata exception and accounting interpretation below resolve specific decisions, not every outstanding original requirement. Distributed archiving is future work and is not a new condition for accepting the original compression/economics milestone.

## 1. Repository prerequisites and authority

| Check before writes | Result |
| --- | --- |
| Branch | `Compression-State-Bloat-and-Node-Economics` |
| HEAD | `ff17d9299327c09ac19cbd9c8370a72419dc8b9e` |
| Separate Task 7.23 commit | HEAD, `Milestone 7 Task 7.23: evaluate meme-first launch compression and size limits` |
| Index/worktree, including untracked files | Clean |
| Prior Task 7.24 commit/deliverables | None found in local available Git history or worktree |
| Tracked prerequisites | All 1,172 preexisting tracked files present; includes 48 `docs/milestone-7-*`, 102 benchmark files and 253 verification files |
| Applicable AGENTS.md | None found in ancestors, repository root or affected documentation/verification directories; no delegation |

[preflight.json](../verification/task724/preflight.json) records HEAD, branch, initial index digest, request digest and every preexisting tracked-file SHA-256. Tracked generators/manifests, fixtures, audit results, economics JSON/CSV and benchmark evidence remain tracked and unchanged. Ignored generated media are not relabeled tracked evidence.

Authority is the owner's supplied Task 7.24 request, including its complete Step 10. It explicitly approves the MODEL A clarification, complete-canonical no-expansion interpretation and exception for the measured below-15% metadata target. Balanced is a **provisional planning profile**, not an activated policy. The referenced earlier Task 7.24 prompt was not separately supplied; this report covers the requirements enumerated in the supplied request and retains unresolved Task 7.22/7.23 findings rather than inventing additional waivers.

Only this report, the [archive proposal](zoidbergchain-distributed-complete-block-archiving-proposal.md) and `verification/task724/` are added. No production/application/validator/consensus code, limits, format, historical evidence, database, genesis or deployment changes. No staging, reset, stash, clean, commit, push or merge. No live peers, pruning, replication or new milestone work.

## 2. Owner decisions and their limits

| Decision | Recorded disposition | Does not authorize or demonstrate |
| --- | --- | --- |
| MODEL A | Each complete finalized media block contains all media bytes and canonical reconstruction information; node retention may differ | Archive implementation, eternal availability or standalone proof of finality |
| Balanced meme-first | Provisional preferred planning profile from Task 7.23 | Production limits, activation height, decoder distribution or a measured optimal traffic mix |
| No expansion | Compare the complete canonical representation against the same original in identity encoding with identical nonmedia context | Universal raw `E<=M`, `R<=M`, physical-allocation monotonicity or a new received-block consensus rejection rule |
| Below-15% metadata target | **FAIL — OWNER-APPROVED EXCEPTION** for this compression closeout, preserving required signed evidence | A passing measurement, removal of votes/signatures, padding, smaller-media exclusions or a waiver of R2/R3/R4 |
| Distributed historical retention | Owner-approved architectural direction; replication/pruning proposal remains INACTIVE | Approved membership, custody threshold, operator policy, incentives or network protocol |
| Community compression/rewards | Future, unactivated workstream | Running submissions, adopting codecs, promising/funding/paying rewards or lowering caps |

Historical reports correctly describe decisions as unapproved at their own dates. They are not rewritten. This report records the later, narrowly scoped owner decisions.

## 3. Precise MODEL A contract

**A complete finalized ZoidbergChain media block must contain the complete losslessly encoded media object and the canonical information needed to reconstruct the exact original bytes from that block alone. The original-byte cryptographic hash must verify.** “Original” means the accepted original-byte domain; existing text canonicalization before admission remains explicitly distinguished from submitted source bytes. Task 7.23 text already has matching source/accepted bytes; the earlier 36-object corpus has a documented seven-byte source normalization.

Reconstruction must not require an external media URL, separately hosted original file, another historical media block, proprietary central server or fragments outside the retrieved complete block. Any media-specific dictionary, side information or model data necessary for reconstruction must be inside that block. Public, immutable historical codec specifications and maintained implementations are software dependencies, not an external per-object media store. New codecs must preserve block-local data closure.

A node may retrieve a complete block from another participant. Different nodes may retain different complete historical blocks. These are two independent properties:

* **A — media reconstruction:** self-contained data in the retrieved complete block, decoded under its historical normative codec/version, with exact size and original-byte hash checks.
* **B — canonical finalized membership:** authenticated block commitment and inclusion under a trusted chain anchor. This may require canonical headers, validator-set history, finality certificates/proofs or a separately approved authenticated checkpoint protocol.

A random standalone block can demonstrate internal reconstruction consistency; it does not prove its own canonical finality. A malicious block can carry a different payload and matching self-declared hash. Property B must bind the expected commitment before its media can be accepted as canonical. Complete media retention does not prove permanent future retrievability; cryptographic hashes prove integrity against authenticated commitments, not continued availability.

The existing isolated complete-record design satisfies the audited media data-closure boundary. Fixture certificates and explicit test snapshots do not establish production historical authority. No hash-only or URL replacement is introduced. See the proposal for format invariants and independent-node verification.

## 4. Provisional Balanced profile and cap reconciliation

| Planning quantity | KiB | Exact bytes | Status |
| --- | --- | --- | --- |
| Static original, JPEG/PNG/WebP | 256 | 262,144 | Provisional |
| Animated GIF original | 512 | 524,288 | Provisional |
| Accepted canonical text original | 16 | 16,384 | Provisional |
| Encoded payload, including codec frame | **513** | **525,312** | Separate provisional encoded gate |
| Complete canonical record | 1,024 | 1,048,576 | Provisional; not today's active block cap |

**513 KiB is not 512 KiB.** Task 7.23 reserves an additional 1 KiB above the largest original cap: `min(2 MiB, max(original caps)+1 KiB)`. The original GIF bound applies before outer lossless encoding; the encoded bound applies to its stored codec stream. Identity fits. The existing selector can choose slightly larger raw encoded bytes when complete canonical bytes shrink; its retained 104→105 counterexample explains the distinction. For that selector, strict shrink and base64 groups bound raw expansion to at most two bytes; 1 KiB is a rounded reservation, not a measured required expansion or permission for arbitrary compressor growth. Received alternate encodings still need independent encoded, complete-size and validity gates under any future approved policy.

Using the unchanged inactive-v3 component budgets:

`4*ceil(525312/3) + 196608 certificate + 98304 native array + 32768 rest = 1028096 B`.

The 1,048,576-B complete cap leaves **20,480 B** beyond that conservative bound. All three reservations are disjoint; rest already includes remaining framing. New finality/journal/proof fields are not free headroom: remeasure and seek separate version/policy approval. This is an analytic sufficient serialization bound, not proof that every combination of maximal fields is constructible.

**Unresolved cap decisions:** final production approval and version/height; explicit separate encoded gate; animation classification (single-frame GIF static, animated WebP conservatively static in the study); supported platform resource bounds; any later evidence/proof additions. No evidence justifies silently changing 513 to 512 KiB. Current policy remains 262,144-B images and canonical text and a 524,288-B serialized non-genesis block bound; inactive v3 remains 3 MiB complete / 2 MiB encoded and image / 256 KiB text. These refer to different policy/version boundaries.

Balanced size-only coverage is **41/58 = 70.69%**; measured equal-admitted mean complete R is **118,935.536585 B** (118,936 rounded). It is not a launch admission probability or a universal affordability claim. Technical admission, dimensions, animation, pixel and decoder limits are independent of the size predicate.

## 5. Reconcile 58 originals, 56 selected encodings and trial counts

Task 7.23 has **58 primary originals**, all kept in coverage denominators and native codec trials. Two fixed-dimension high-entropy originals exceed the unchanged 2 MiB frozen original cap:

| Original | Bytes | Outcome |
| --- | --- | --- |
| `jpeg-texture-1280` | 2,242,286 | No constructible frozen complete record |
| `png-texture-1280` | 3,594,660 | No constructible frozen complete record |

Thus **56 primary objects have legal complete selected records/encodings**, with **31 Zstd / 25 identity** choices. They are not 56 compressed successes: identity is a valid selected encoding. No record, metadata percentage or reconstruction timing is fabricated for the two over-cap originals. Their exclusion from canonical-record statistics is explicit and does not remove them from the 58-original coverage denominator.

Seven native configurations give **406 primary codec trials (58×7)**. One separately declared raw-expansion diagnostic gives seven more, **413 total**; the diagnostic never reweights primary statistics. The manifest therefore has **59 samples including the diagnostic**. Native roundtrip success is separate from strict historical codec-profile validity: the near-2-MiB GIF's alternate Zstd-3 frame is INVALID (`frame/block_count`), and the actual selector uses valid identity fallback. Brotli sizes are comparisons, not accepted v3 encodings. Counts from Task 7.21 are a different population: 70 format plus 58 current-policy bridge records, **128** persisted/fresh-process recovered records.

## 6. Complete-canonical no-expansion interpretation

Let M be accepted original bytes, E encoded bytes including framing, B=`4*ceil(E/3)` base64 content, D the complete descriptor and R the complete canonical record. Compare against identity for the **same original and identical certificate/transaction/header context**. The normal producer selects a strictly smaller valid compressed D, otherwise verified identity; its selection yields `R_selected <= R_identity` because the remaining canonical context and record-hash width are fixed. Independent received-byte validation does not recompress.

The retained diagnostic has M=104, E=105, B=140 for both candidates, D **363→359**, and Task 7.23 R **33,331→33,327**. Task 7.22's distinct fixed context is **33,330→33,326**; the one-byte context difference is preserved. Raw `E<=M` fails, while complete canonical bytes shrink by four. The owner accepts the latter comparison as the no-expansion interpretation. `R<=raw M` and guaranteed smaller SQLite allocation are not claimed. Validators may accept otherwise valid alternate larger encodings under the frozen rules; this local producer preference is not a newly approved consensus constraint.

## 7. Metadata target: explicit exception, unchanged FAIL

Metadata N=`R−B`; percentages are `100*N/R`, including descriptor/framing and every signed certificate, vote, attestation, header and transaction field. B is base64 content only. Base64 expansion `B−E` is separately charged; charging it as metadata makes percentages worse. Equal-record nearest-rank percentiles are not interchangeable with a canonical-byte-weighted share.

| Population | Legal records | p50 % | p95 % | Worst % | Equal-record mean % | Individually <15% |
| --- | --- | --- | --- | --- | --- | --- |
| Frozen historical | 36 | 85.97237 | 99.60381 | 99.85557 | 70.81241 | 6/36 |
| Task 7.20 new | 34 | 54.70902 | 99.80752 | 99.81935 | 53.05444 | 12/34 |
| Task 7.23 primary legal records | 56 of 58 originals | 57.32356 | 99.46054 | 99.96385 | 48.46198 | 19/56 |
| Balanced admitted subset | 41 of 58 originals | 77.28692 | 99.46054 | 99.96385 | 61.52426 | See underlying rows |

**Criterion C remains FAIL, with an explicit owner-approved exception.** Required evidence is retained. Smaller selected media can increase metadata share even as R decreases; padding, dropping tiny media or removing signatures would not demonstrate attainment. Task 7.20's 7.14017% canonical-byte share does not overturn its 54.70902% p50. This exception resolves Task 7.22 R1 for closeout accounting; it does not change a historical result or waive representativeness, measurement or integration requirements.

## 8. Preserve the full three-year economics baseline

Milestone 7's three-year node models assume **full historical retention per modeled node**, under stated media-only traffic and capacity assumptions. They remain valid as that conditional baseline. Three years are **36 months / 1,095 days**, with 100 / 1,000 / 10,000 blocks/day, or 109,500 / 1,095,000 / 10,950,000 records. These are not distributed-archive simulations.

Preserved evidence includes the [original Task 7.8 JSON](../benchmarks/milestone_7_task_7_8_results.json), [monthly CSV](../benchmarks/milestone_7_task_7_8_monthly.csv), [Task 7.22 corrected scenarios](../verification/task722/economic_scenarios.json), [cost formulas](../verification/task722/cost_formulas.json), [month-36 costs](../verification/task722/month36_costs.csv), [historical projections](../verification/task722/historical_economics.json), [sensitivity scenarios](../verification/task722/sensitivity_scenarios.json), and [Task 7.23 complete economics](../benchmarks/task723_v1/economics.json). Nothing is replaced by the following compact Balanced extract.

| Balanced blocks/day | Year-3 canonical GiB | Local capacity GiB including reserve/snapshot/recovery | Month-36 USD budget / storage / cloud | Full 36-month USD budget / storage / cloud |
| --- | --- | --- | --- | --- |
| 100 | 12.129 | 57.338 | 21.08 / 46.08 / 49.47 | 741.72 / 1,641.72 / 1,630.69 |
| 1,000 | 121.290 | 499.585 | 47.22 / 55.22 / 163.68 | 1,139.07 / 1,816.62 / 3,611.32 |
| 10,000 | 1,212.902 | 4,922.047 | 359.80 / 235.11 / 1,408.05 | 6,984.61 / 5,058.30 / 27,161.82 |

All three illustrative hosts are below $100/month at 100/day, only budget/storage at 1,000/day, none at 10,000/day. Totals sum 36 monthly bills, not 36 times the final bill. Results depend on the synthetic admitted mean and inherited illustrative USD rates, not a current regional purchase quote or capacity/IOPS/CPU qualification. Task 7.24 performs no price refresh or new provider recommendation. All A/C/control workloads and 54 Task 7.23 sensitivity cases remain available; lower caps do not imply smaller average accepted R or lower cost for an unchanged workload.

The model charges primary bytes, assumed index/page overhead and fragmentation, operational reserve, snapshots, remote retained backups, recovery workspace, propagation, backup uploads and expected bootstrap/restore egress. Separate physical index attribution and actual network workloads remain incomplete. Historical WAL observations are preserved; no WAL runner or production database is opened.

Future distributed economics must separately measure per-validator historical reduction, assigned partial-archive storage, full-archive cost, aggregate replicated storage, redundancy/replacement, retrieval/repair/rebalance traffic, challenges, snapshots/backups, incentives, minimum independent operators and reviewer-journal storage where applicable. Three complete copies do not divide aggregate network cost by three. No new savings are credited without simulation. Full archives and recovery copies can add to the replication baseline. Media-only forecasts exclude future journal/failed-review traffic and external authority/finality evidence unless explicitly included; combined affordability remains unproven.

## 9. Original acceptance findings and remaining work

The [Task 7.22 original matrix](../verification/task722/acceptance_matrix.json) remains the historical baseline. [findings.json](../verification/task724/findings.json) records the later decisions, counts and reconciliations.

| Original requirement(s) | Final Task 7.24 finding |
| --- | --- |
| MODEL A | PASS for audited block-local media design/recovery; canonical finality and indefinite availability are separate |
| 1, 8, A — codec comparison, representative metadata/compressible-content evidence | Comparisons and reproducible measurements exist; **PARTIAL** representativeness. Synthetic meme stress coverage is not independent real-media/human-text/code deployment evidence |
| 2, 3, 6, E — metadata, exact reconstruction, adaptive application behavior | **PASS in completed isolated development; PARTIAL original application acceptance.** Disabled bridge stores/reconstructs exact bytes, but active accepted-media compression is absent and acceptance of this boundary has not been explicitly resolved |
| 4 — three-year rates | PASS as a bounded full-retention model at all three rates |
| 5 — physical media/database/index/snapshot/backup/traffic measurement | **PARTIAL**: canonical partitions and historical DB/backup observations exist; separate physical-index/snapshot and real-transfer measurements remain unresolved |
| 7 — realistic already-compressed-media expectations | PASS: small gains, expansions and identity fallback reported; unsupported video receives no claimed result |
| 9, D — full accounting / conditional $100 or disclosed misses | PASS under stated assumptions; regional quote, tier feasibility and operational throughput unverified |
| B — no expansion | PASS in isolated normal producer under the explicit complete-canonical-versus-identity interpretation; active application boundary remains unresolved; raw counterexample retained |
| C — below-15% metadata target | **FAIL — OWNER-APPROVED EXCEPTION**, not a measurement PASS |
| F — reproducibility | PASS within recorded environments and bounded replays; no new Linux/native-security/universal portability credit |

Task 7.22 R1 is resolved by the explicit metadata exception; R5 is resolved as an accounting interpretation, with its raw-payload failure retained. **R2 remains open:** bounded provenance-cleared representative content or an explicit limitation acceptance. **R3 remains open:** explicitly accept completed disabled integration as the original development boundary, or separately authorize the required reviewed application integration; no public activation is inferred. **R4 remains open:** bounded separate physical-index/snapshot/backup/recovery and actual transfer measurements, or an explicit limitation acceptance. This task neither performs those new measurement campaigns nor invents their waivers.

Completed isolated work includes codec/strict decoder, canonical format/evidence, adaptive production, durable isolated storage/recovery and disabled service integration. Production gates remain independently blocked: approved version/height transition, authenticated authority and finality/history integration as applicable, independent decoder/security review, supported-platform qualification, historical decoder distribution, validator adoption and capacity/recovery validation. Existing BFT/static-authority/G2/reviewer-journal laboratories do not constitute a deployed complete authority chain. Their future completion is not retroactively required for benchmark acceptance.

## 10. Future handoffs — no implementation or activation

Recommend the unnumbered future milestone **Distributed Complete-Block Archiving and Safe Pruning**, specified in the [architecture proposal](zoidbergchain-distributed-complete-block-archiving-proposal.md). It uses complete-block replication, independently operated partial/full archives, authenticated retrieval, provisional three-copy placement, custody verification, periodic audits, repair and fail-closed pruning. Work packages A–K and their prerequisite graph are recommendations, not work begun.

The earlier [roadmap Task 12](roadmap.md#task-12---content-compression-storage-strategy-and-chain-bloat-prevention) still describes hash-only/off-chain large-media storage. For this handoff, the owner's newer explicit MODEL A contract supersedes that conflicting direction. A future roadmap reconciliation must preserve complete media in each canonical media block; retaining an older roadmap paragraph does not approve URL/hash-only replacement. No conflicting milestone number is assigned and the existing roadmap is not rewritten here.

Community lossless compression innovation/rewards remain a separate future workstream, preserving [Task 7.23 section 9](milestone-7-meme-first-launch-sizing-recommendation.md#9-future-community-codec-framework--proposed-inactive): normative versioned decoding, historical compatibility, bounded resources, independent cross-platform/security review, public/withheld corpus controls, net complete-canonical accounting and reward anti-gaming. This later MODEL A clarification tightens data closure: any per-object dictionary/setup bytes must be block-local, not in another media block. Codec approval, cap changes, reward policy/funding and activation are separate decisions. No arbitrary submitted code is executed and no reward is promised.

## 11. Bounded verification and final decisions

[README.md](../verification/task724/README.md) gives exact replay commands. The new verification reads tracked evidence, rechecks cap/base64/component arithmetic, all 58/56/413 counts, identity comparisons, metadata percentiles and three-year extraction; reruns Task 7.23's existing read-only independent checker; validates local Markdown links; and verifies every preexisting file, index, HEAD and branch. Focused existing analytical tests are rerun without enabling application/network/DB paths. Results and exclusions are in [findings.json](../verification/task724/findings.json), [tests.json](../verification/task724/tests.json) and [preservation.json](../verification/task724/preservation.json). No distributed retrieval, replica survival, custody or pruning test has run: the twelve proposal tests are future acceptance gates.

Fresh results: **14 analytical tests passed**, zero failed/skipped/deselected; **1,350 independent Decimal monthly checks**, **210 historical checksum entries across five manifests**, **30 local Markdown file links**, and **1,172 unchanged preexisting tracked files**. Git index, branch and HEAD are unchanged. An initial new verification-runner attempt checked generated links before creating their targets; only that new runner's sequencing was corrected, as recorded in `verification/task724/development-notes.json`, and the complete verification passed. No historical source or assertion was repaired for this task.

Historical results remain historical: Task 7.22 recorded 1,030 passed / 197 skipped / 2 deselected; Task 7.23 recorded 289 passed and one excluded live-API initialization test. Neither is reported as a fresh Task 7.24 suite. Linux, full API/load, independent native security and WAL qualification remain outside this bounded documentation verification.

**Verdict A — Original Milestone 7 development/acceptance closeout: INCOMPLETE.** The specific metadata exception and canonical interpretation are recorded; R2/R3/R4 remain materially unresolved beyond those decisions. No MODEL A violation was found in the retained complete-block design. Future archive implementation is not the reason for this verdict.

**Verdict B — Production/network activation: BLOCKED.** No future storage-distribution function is implemented or approved for activation.

**Owner-performed commit readiness:** the Task 7.24 documentation/evidence package is ready for review and a separate owner-performed commit after its recorded verification passes. It is not a declaration that Milestone 7 is accepted. The final worktree intentionally contains only the two new reports and `verification/task724/`; all are unstaged, and no commit/push is performed.
