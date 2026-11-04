# Milestone 7 Task 7.25 — Physical storage and network economics verification

Date: **2026-11-03, America/New_York**. Version 1, bounded measurement only.

**Original Milestone 7 development: COMPLETE WITH OWNER-APPROVED LIMITATIONS. Production/network: BLOCKED. Task 7.25 is ready for owner review and an owner-performed commit.** Milestone 7 can close for development with the limitations below; no public launch, protocol activation or distributed archival system is authorized.

## 1. Prerequisites and unchanged scope

Branch: `Compression-State-Bloat-and-Node-Economics`. Initial and final HEAD: `75281fe14342cd8b606fe6ebc469bd1435feec86`. Separate Task 7.24 commit is that HEAD, `Milestone 7 Task 7.24: document final acceptance and distributed archival architecture`. Initial worktree/index were completely clean, including untracked files. All 1,183 preexisting tracked files were present and hashed. All previous Milestone 7 reports, generators, manifests and evidence remain tracked and unchanged; generated media under ignored paths remain generated, not relabeled tracked inputs. No applicable AGENTS.md was found. No delegation was used.

Only this report and [verification/task725](../verification/task725/README.md) are added. Final status contains only these untracked deliverables; index/HEAD/branch and all preexisting tracked bytes are unchanged, recorded in [preservation.json](../verification/task725/preservation.json). No reset, clean, stash, stage, commit, push, merge, production DB/backup access, protocol/consensus/genesis/configuration change, WAL activation or Task 7.26/archive work.

Read the seven requested historical reports, source and frozen results. [source_versions.json](../verification/task725/source_versions.json) identifies inspected implementation boundaries. `canonical_v3/media.py` selects valid Zstd versus identity by complete descriptor size, verifies exact accepted originals and stores base64. `block.py` binds complete canonical bytes and signed certificates. `storage.py` uses a WITHOUT ROWID canonical BLOB table plus derived tables and four named secondary indexes. The existing Task 7.21 `DisposableStore` reuses actual inherited insert/get/index operations and the exact schema with DELETE/EXTRA initialization. The legacy initializer/backup verifier would enable WAL, so neither is invoked.

The active backup CLI exports a different v1 JSON application snapshot; it is not falsely reported as accepting this disabled v3 database. This study uses SQLite's actual consistent backup API and full byte-copy recovery at the isolated storage boundary. Active network handling accepts versions 1/2, so v3 transfer is explicitly simulated at the closest existing HTTP services and serialization boundary.

## 2. Workloads, identities and Balanced eligibility

| Workload | Originals | Legal R | Original-domain B (all) | Legal-record original B | Selected E B | Complete R B | Choices |
| --- | --- | --- | --- | --- | --- | --- | --- |
| historical36 | 36 | 36 | 6,093,910 | 6,093,910 | 5,285,229 | 8,241,301 | {'identity': 10, 'zstd': 26} |
| production34 | 34 | 34 | 11,521,163 | 11,521,163 | 11,002,892 | 15,798,621 | {'identity': 17, 'zstd': 17} |
| meme58 | 58 | 56 | 24,930,635 | 19,093,689 | 18,417,045 | 26,413,907 | {'identity': 25, 'zstd': 31} |
| balanced41 | 41 | 41 | 2,875,842 | 2,875,842 | 2,637,179 | 4,876,357 | {'identity': 14, 'zstd': 27} |

E includes codec framing; R is the entire stored canonical JSON block. Every record's MIME, source/accepted sizes and hashes, E, R, codec, block identity and cap inclusion/exclusion are in [workloads.json](../verification/task725/workloads.json). All 126 constructible primary records reproduce their exact frozen canonical SHA-256, not merely lengths. Balanced reuses 41 of those records; it is not another 41 independent originals. Meme coverage denominators retain all 58 originals. The JPEG 2,242,286-B and PNG 3,594,660-B texture originals exceed the frozen 2-MiB original cap: E/R/identity are unavailable, never fabricated. The separate 7.23 diagnostic is excluded only as originally declared. A separate golden native-transaction control tests transaction-index allocation and is excluded from economics.

All populations are synthetic, equal-record coverage, with no observed production distribution. The historical source has 6,093,917 B versus 6,093,910 accepted B after its preexisting seven-byte text normalization. Later corpora's accepted/source domains match. Exact regenerated manifests, original commitments and frozen R hashes are checked before physical measurement. Frozen corpora and historical benchmarks are unchanged.

Balanced remains provisional/inactive: static images 262,144 B, animated GIF 524,288 B, canonical text 16,384 B, encoded 525,312 B (**513 KiB**), complete R 1,048,576 B. Single-frame GIF uses the static cap; animated WebP conservatively uses static MIME cap. The 41/58 inclusion matches Task 7.23. These are size gates, not proof of admission, demand or an activation decision.

Additional storage cycles reuse exact media/certificates, change only the unsigned header height and resulting block hash, and pass actual format/signature/strict-media checks on insertion. They are independent valid candidates for allocation experiments, not a fabricated selected/finalized chain, production traffic or authenticated ancestry. No BLOB deduplication or physical savings versus an identical JSON representation are assumed.

## 3. Actual SQLite growth, occupancy and marginal behavior

Reference: Windows AMD64, CPython 3.13.5, SQLite **3.49.1**, page size **4,096 B**, journal **DELETE**, synchronous **EXTRA (3)**. Package/compiler/OS details and compile flags are in [environment.json](../verification/task725/environment.json). No dependency was changed.

| Workload | Blocks | Canonical B | Main file B | Pages | Free pages | Gross DB overhead / R | Empty DB B |
| --- | --- | --- | --- | --- | --- | --- | --- |
| historical36 | 144 | 32,965,276 | 33,374,208 | 8148 | 0 | 1.240% | 49,152 |
| production34 | 136 | 63,194,548 | 63,639,552 | 15537 | 0 | 0.704% | 49,152 |
| meme58 | 224 | 105,655,779 | 106,311,680 | 25955 | 0 | 0.621% | 49,152 |
| balanced41 | 1312 | 156,045,206 | 159,113,216 | 38846 | 0 | 1.966% | 49,152 |
| native_index_control | 32 | 1,106,839 | 1,286,144 | 314 | 0 | 16.200% | 49,152 |

File length is page_count×page_size in these observations. Live allocated pages equal `(page_count−freelist_count)×page_size`; this is occupancy of allocated B-tree pages, **not** exact useful cell payload or absence of internal slack. Filesystem allocated bytes and sparse/compressed/reparse attributes are separately recorded. No measured file is sparse or compressed; no hardlink/reflink savings are credited. Host/VHD/storage-layer deduplication, thin provisioning and physical-device independence are not observable here.

Samples include empty, 1, 5, one/two/four corpus cycles; Balanced extends to 8/16/32 cycles (1,312 records). [sqlite.json](../verification/task725/sqlite.json) contains every sample, per-interval total and overhead marginal growth, SQLite settings and separate schemas. Fixed initialization is charged **once**, never multiplied per block. Final complete-cycle marginal overhead, net of the actual canonical bytes in that interval, supplies the projection coefficient:

| Workload | Largest measured n | Final marginal overhead B/block | Complete-cycle interval range B/block | One-time init B |
| --- | --- | --- | --- | --- |
| historical36 | 144 | 2498.097 | 2498.097–2612.500 | 49,152 |
| production34 | 136 | 2819.985 | 2819.985–3121.706 | 49,152 |
| meme58 | 224 | 2616.804 | 2616.804–2946.679 | 49,152 |
| balanced41 | 1312 | 2338.102 | 2219.951–2345.829 | 49,152 |

The range is observed full-cycle interval variation, not a confidence interval or a proven large-N bound. Prefix composition and whole-page allocation create steps; the small append-only sample does not establish multi-year behavior or deeper B-tree/fragmentation costs. Some first-record net-overhead increments are negative because already allocated initial pages gain payload; this is not negative file growth or evidence of compression. Those prefixes are excluded from extrapolation. Initialization dominates tiny samples, while complete-cycle marginal data/page/index growth is much smaller than the old assumed 10% index/page factor. Aged fragmentation remains a separately labeled 15% planning allowance. Header digit growth at millions of blocks and churn/forks require later measurement; none are silently claimed measured.

## 4. Separate index accounting and retrieval observations

| Workload | Full − minimal B | Full − no secondary B | Drop-probe secondary B | Native index entries |
| --- | --- | --- | --- | --- |
| historical36 | 135168 | 77824 | 77824 | 0 |
| production34 | 131072 | 69632 | 69632 | 0 |
| meme58 | 180224 | 102400 | 102400 | 0 |
| balanced41 | 901120 | 548864 | 548864 | 0 |
| native_index_control | 81920 | 40960 | 40960 | 32 |

Minimal retains the exact same canonical BLOB/primary-key table and immutable triggers. Full-minus-minimal includes context/settings, derived block/transaction tables, secondary indexes and fixed schema: it is an **incremental schema footprint**, not a precise pure-index estimate. The no-secondary database retains all tables, primary/unique/FK/immutability semantics and removes only the four nonunique query indexes in a disposable comparison. Full-minus-no-secondary is actual file allocation difference with equivalent integrity semantics; page packing can make it differ from separately reclaimable index pages.

`dbstat` is unavailable. On a full disposable copy, dropping each secondary index without VACUUM leaves file length/page count fixed and directly measures its increment in freelist pages. This is the **marginal releasable allocation**, including any schema-page release; per-index pages are retained. WITHOUT ROWID primary B-trees combine keys/data and cannot be split precisely without changing layout. No required production index is removed. Primary and derived integrity, immutable update/delete, duplicate identity, BLOB type/size, SQLite integrity and foreign-key checks pass. All media-only populations have zero native transactions; the native control's transaction entries quantify a separate lower-coverage dimension, not a production transaction mix.

| Balanced blocks | Secondary aggregate file allocation B |
| --- | --- |
| 0 | 16384 |
| 1 | 16384 |
| 5 | 16384 |
| 41 | 32768 |
| 82 | 49152 |
| 164 | 81920 |
| 328 | 143360 |
| 656 | 274432 |
| 1312 | 548864 |

[index_growth.json](../verification/task725/index_growth.json) retains the equivalent aggregate secondary-file and live-page difference at **every** sample count for every workload, plus the full-minus-minimal schema footprint. Empty index roots are fixed overhead. At 1,312 Balanced blocks the per-index DROP probe releases height 110,592 B, previous-hash 212,992 B, original-hash 221,184 B and empty transaction-ID root 4,096 B, totaling **548,864 B**. The endpoint file difference agrees exactly in this run; no assertion of generic page-packing equality is needed.

The separate 32-record native control has **16.20% gross physical overhead**, versus 0.62–1.97% in the larger media populations. Its smaller records, one transfer per candidate, low sample count and BLOB/page quantization differ from the main corpora: this is **not** a pure 16.20% transaction-index charge. Its transaction-ID index grows to 12,288 B with 32 entries. Zero-transfer media coefficients and $100 results must not be generalized to transaction-heavy traffic; a realistic native-transfer mix remains part of operational economics qualification.

Warm-cache median query/BLOB-fetch timings, five batches, µs (observational, same SQL):

| Workload | Full PK µs | Minimal PK µs | Full height µs | No-secondary height µs |
| --- | --- | --- | --- | --- |
| historical36 | 13707.46 | 14869.45 | 765.76 | 934.16 |
| production34 | 19114.73 | 21969.74 | 954.32 | 997.38 |
| meme58 | 30411.01 | 27219.02 | 844.98 | 875.35 |
| balanced41 | 4135.67 | 4430.61 | 842.94 | 1247.98 |
| native_index_control | 630.33 | 1613.55 | 810.82 | 907.83 |

Full height queries use `block_height_idx`; comparison plans show a table scan without it. PK retrieval includes actual BLOB fetch. These small, warm, sequential local checks exclude crypto/decoder time and do not qualify concurrency, cold-cache IOPS, production latency or a restore SLA.

## 5. Consistent snapshots, full backups and recovery

| Workload | Restored blocks | Source B | Snapshot B | Full backup B | Destination increment B | Workspace over live+snapshot B | Peak all four B |
| --- | --- | --- | --- | --- | --- | --- | --- |
| balanced41 | 1312 | 159,113,216 | 159,113,216 | 159,113,216 | 159,113,216 | 318,226,432 | 636,452,864 |
| historical36 | 144 | 33,374,208 | 33,374,208 | 33,374,208 | 33,374,208 | 66,748,416 | 133,496,832 |
| meme58 | 224 | 106,311,680 | 106,311,680 | 106,311,680 | 106,311,680 | 212,623,360 | 425,246,720 |
| production34 | 136 | 63,639,552 | 63,639,552 | 63,639,552 | 63,639,552 | 127,279,104 | 254,558,208 |

Every consistent SQLite online-backup snapshot and every uncompressed full backup is **1.000000×** its source in this run. Four retained backups therefore require exactly four measured backup sizes at the tested population, rather than the old assumed 0.95 factor. Copy sizes are not retention-policy measurements.

Full backup and restore use exclusive streaming writes, fsync each 1-MiB chunk and verify whole-file SHA-256, separate file identities and compression/sparse attributes. Snapshot is a standalone database, not a dependent CoW layer. Copies remain on the same volume and share a device/failure domain; no independent remote archival durability is inferred. Daily snapshot refresh, four monthly uploads and four remotely retained full copies are still modeled operational policies.

The measured restore procedure retains live DB + snapshot + staged full backup + restored DB. Monotone, fsynced file-length observations give the actual copy high water. One new destination is one source-sized increment, but workspace above normal live+snapshot retention is **two source-sized copies** (staged backup plus destination). The revised local forecast funds both. RAM/OS buffers and unobserved underlying storage allocation are outside that file-workspace measurement; no VACUUM/decompression workspace or provider snapshot service is claimed tested.

Every recovered database is reopened by a **fresh Python process** with the explicit trusted fixture context. Actual inherited `get` independently parses/verifies canonical/signature/index bindings and runs the real isolated decoder for every stored record. The decoder output used by that get is observed directly to avoid redundant second decoding. Block set, exact canonical SHA-256, original byte length and original-byte SHA-256 match the independently frozen/reconstructed commitments; SQLite integrity/FKs and derived/orphan counts pass. The parent also retrieves and compares every canonical byte string against its pre-backup original. Initial corpus reconstruction compared actual original bytes directly. No original/media cache is supplied to recovery. Selected/finality counts remain zero: internal identity/reconstruction does not establish canonical finalized membership. Details: [backup_recovery.json](../verification/task725/backup_recovery.json).

After completing all SQLite measurements and the first historical recovery, the development run was interrupted to eliminate a redundant second parent decode. `measure.py --copies-only` continues from the same measured source databases into a new disposable copy directory; the parent comparison now uses read-only SQL, while the fresh child still fully verifies every record. [copy_execution.json](../verification/task725/copy_execution.json) records byte-identical source-file hashes before/after and the bounded continuation. The whole fresh-recovery process bound is 1,200 seconds; per-object decoder limits are unchanged. This is a recorded development interruption, not a hidden failure or timeout.

## 6. Measured transfer: real framing, simulated v3 service

| Workload | Blocks | Canonical B | Send bodies B | Application excess B | Request HTTP B | ACK stream B | Sender / R | Fresh history response B |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| historical36 | 36 | 8,241,301 | 10,614,785 | 2,373,484 | 45,516 | 10,440 | 1.293522× | 9,376,875 |
| production34 | 34 | 15,798,621 | 18,040,367 | 2,241,746 | 42,995 | 9,860 | 1.144616× | 16,871,178 |
| meme58 | 56 | 26,413,907 | 30,105,757 | 3,691,850 | 70,820 | 16,240 | 1.142450× | 28,180,155 |
| balanced41 | 41 | 4,876,357 | 7,579,256 | 2,702,899 | 51,837 | 11,890 | 1.564917× | 6,169,511 |

Counts above cover all unique legal records per workload, not expanded storage cycles. Propagation uses the **actual** `PeerBroadcastService.broadcast_block`: first a separate certificate POST, then a block wrapper containing another certificate plus the complete block (which already contains its certificate). This duplicated evidence and requests' actual JSON spacing/escaping are charged. Optional external originality-evidence transfers are absent/unqualified, not asserted free in a future protocol. The receiver authenticates real fixture HMAC headers, canonicalizes the received map back to exact R, verifies signed canonical identity and reconstructs original media through the disabled service.

The measured sender excess over R is **56.49% Balanced**, **29.35% historical**, **14.25% full legal meme** and **14.46% production-like**, before the model's separate contingency; ACKs are additional. Balanced bounded-history responses add **26.52%** over canonical bytes. Fixed certificate/wrapper charges explain this meaningful workload variance. A large-object corpus ratio cannot substitute for the smaller Balanced mean, and this application excess is not a packet-overhead measurement. All **346** exchanges complete without application failure in the permitted measurement pass. The sideband certificate POST measures framing only; the embedded certificate is cryptographically validated as part of the canonical block. No active v1 certificate admission or v3 network acceptance is claimed.

For each workload, actual `PeerChainSyncService.fetch_blocks` performs single historical, bounded eight-block and fresh bounded-history GETs. Starlette's real JSONResponse serializer emits the source-derived `blocks/certificates/originality_evidence` wrapper. Returned records match exact sent canonical bytes and are independently reconstructed. Fresh history includes all declared records; it excludes genesis/summary/handshake, reviewer/authority/finality proof acquisition and adoption. It is **not a measured fresh production node bootstrap**. The current service fetches whole remaining history; no pagination or archive protocol is implemented.

[transfer.json](../verification/task725/transfer.json) retains each exchange: canonical payload, request/response bodies, application excess, HTTP request/response framing, authentication-header subset and checksums. Auth bytes are already inside HTTP framing and are never double-counted. HTTP stream octets are observed; TCP/IP/link framing, TLS and TCP retransmissions are **unobserved/null**, not invented zeroes. HTTP is unencrypted loopback, sequential, uncompressed, unchunked, no application retries/redirects. One connection per exchange. Ephemeral port digits can change request header lengths by up to two bytes on replay. Application payloads/checksums have no tolerance.

ACKs use the harness's explicitly synthetic `accepted/integration_status` response, serialized by real Starlette; they are not an approved active-v3 response contract. Their octets are measured for that fixture, and their use in a future bill remains part of the simulated-boundary assumption. Request wrappers/history response structure come from the existing services/source, while all claims of active acceptance remain blocked.

The first restricted Windows loopback precheck failed with WinError 10013 before transmitting a payload; the identical permitted local-only test passed. The complete transfer pass runs with local-connection permission. Both development outcomes and any restricted main-run attempt are preserved. No public peer or active HTTP route is contacted/registered. This satisfies the requested **explicit simulated-transfer alternative**, not v3 network activation or production P2P qualification.

## 7. Three-year projection and measured-versus-assumed split

36 months = 1,095 days, normal month lengths with February fixed to 28 days. Rates imply 109,500 / 1,095,000 / 10,950,000 retained complete records. One GiB = 2³⁰ B. Main scenario is equal-admitted Balanced mean R **118,935.536585 B**. All nodes retain full history in these scenarios; distributed allocation receives no savings credit.

| Blocks/day | Canonical GiB | Primary P GiB | Snapshot GiB | Recovery W GiB | Headroom H GiB | Local GiB | Remote backups GiB | Bootstrap GiB |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 100 | 12.129 | 15.187 | 15.187 | 30.374 | 8.620 | 69.367 | 60.747 | 18.414 |
| 1000 | 121.290 | 142.868 | 142.868 | 285.736 | 39.397 | 610.870 | 571.473 | 184.142 |
| 10000 | 1212.902 | 1419.682 | 1419.682 | 2839.364 | 347.174 | 6025.901 | 5678.727 | 1841.416 |

Full monthly series for all four workloads, three rates and three hosts (36 scenarios) plus 54 Balanced sensitivities are in [projections.json](../verification/task725/projections.json); [month36.csv](../verification/task725/month36.csv) contains all final bills/capacities. Historical full-retention datasets remain available for comparison. Their complete canonical bytes and actual measured coefficients replace guessed physical overhead; historical small/large analytical scenarios are preserved unchanged rather than relabeled measured.

Measured inputs are original/R/E identities, one-time initialization, final complete-cycle marginal overhead and its interval range, snapshot/full-backup ratio, recovery-file coexistence, and actual application/HTTP transfer sizes at the simulated service boundary. Projection is an **extrapolation**, not physical measurement of three years. All prices, weights, retention/upload frequency, 1-GiB nonmedia reserve, 15% aged fragmentation, 20% operational reserve, 1.45× monthly write reserve, fixed 5-GiB headroom, eight outgoing peers, one incoming propagation, 20% traffic contingency, and one bootstrap/restore served per year remain assumptions. The 1.45 factor is retained workspace planning, not WAL use or measurement. The 20% traffic contingency is not a fabricated packet count.

The model charges primary `P=1GiB+init+N*(mean_R+marginal_overhead)+.15*C`; snapshot S=P; recovery W=2P; operational `H=.20P+1.45*monthly*(R+overhead+.15R)+5GiB`; local capacity `P+S+W+H`. Four measured 1× full backups are priced remotely, with four P-sized uploads/month. Propagation uses actual sender/ACK means at eight peers, then 1.20 assumed contingency. Bootstrap uses measured per-record canonical+certificate+array bytes and **one** fixed collection/HTTP charge; small-batch initialization is not multiplied per block. The bootstrap quantity is the server response/egress; its GET request is measured separately and ingress is assumed free. Yearly expected bootstrap and restore service are priced as monthly 1/12 fractions. Backup upload protocol framing remains unmeasured and uncredited. Baseline reserve/fragmentation applied to copied P are conservative model allowances, not newly measured application-state bytes.

Sensitivity cases vary complete-cycle marginal range, remove aged fragmentation, increase traffic contingency, double peers and retain twelve backups. They expose model dependence; their range is not a probability interval or universal workload cap. Four workloads' full-retention comparisons are in the CSV; no actual production weights, long-term fragmentation, cold storage throughput, administrative cost or future proof/journal/archive traffic is asserted measured.

## 8. Updated month-36 hosting economics and $100 target

Historical [Task 7.22 USD inputs](../verification/task722/economic_inputs.json) and [pricing review](../verification/task722/pricing_review.json) are deliberately reused, with no provider recommendation or fabricated current quote: budget $20 compute /160 GiB included /$0.05 extra GiB /$0.006 backup GiB /$0.01 egress GiB; storage-focused $45 /500 /$0.02 /$0.006 /$0.01; cloud $40 /160 /$0.10 /$0.05 /$0.09. Each assumes 4 vCPU/8 GiB but does not qualify them. The budget/cloud/storage labels describe illustrative pools, not purchasable verified regional plans. Disk uses the inherited ceil-to-GiB marginal billing rule; transfer allowances, taxes/currency and tier premiums are not invented.

| Blocks/day | Host | Prior 7.23 | Updated | Total Δ $ | Storage + recovery Δ | Backup Δ | Transfer Δ | vs $100 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 100 | budget_vps | $21.08 | $21.05 | -0.03 | -0.06 | +0.02 | +0.02 | BELOW |
| 100 | mainstream_cloud | $49.47 | $49.22 | -0.25 | -0.54 | +0.16 | +0.14 | BELOW |
| 100 | storage_focused | $46.08 | $46.05 | -0.03 | -0.06 | +0.02 | +0.02 | BELOW |
| 1000 | budget_vps | $47.22 | $52.48 | +5.26 | +4.93 | +0.18 | +0.15 | BELOW |
| 1000 | mainstream_cloud | $163.68 | $172.20 | +8.53 | +5.67 | +1.48 | +1.37 | ABOVE |
| 1000 | storage_focused | $55.22 | $57.15 | +1.93 | +1.60 | +0.18 | +0.15 | BELOW |
| 10000 | budget_vps | $359.80 | $412.04 | +52.24 | +48.95 | +1.76 | +1.53 | ABOVE |
| 10000 | mainstream_cloud | $1408.05 | $1492.52 | +84.47 | +56.01 | +14.73 | +13.73 | ABOVE |
| 10000 | storage_focused | $235.11 | $254.26 | +19.15 | +15.86 | +1.76 | +1.53 | ABOVE |

Δ is a sequential additive attribution: prior Task 7.23 formula → measured SQLite **and two-copy recovery** basis → measured 1× backup ratio → measured simulated transfer basis. R/population, prices and other default assumptions are held fixed in that comparison. These deltas are caused by measured coefficients **inside an assumption-driven extrapolation**, not invoices or three-year observed savings. The storage/recovery term deliberately includes the larger recovery coexistence requirement; the backup term includes retained backup and expected restore-transfer effects. Each line sums to the total delta, with only display rounding. The new full-meme comparator is the prior formula applied to that corpus, explicitly distinguished from an already published bill.

Original representative-corpus economics, preserved and compared transparently:

| Blocks/day | Host | Original 7.8 | Frozen-v3 7.22 | Physical update | Δ vs 7.8 $ |
| --- | --- | --- | --- | --- | --- |
| 100 | budget_vps | $21.82 | $22.02 | $21.93 | +0.11 |
| 100 | mainstream_cloud | $55.99 | $57.71 | $56.93 | +0.94 |
| 100 | storage_focused | $46.82 | $47.02 | $46.93 | +0.11 |
| 1000 | budget_vps | $43.18 | $79.37 | $88.67 | +45.49 |
| 1000 | mainstream_cloud | $205.95 | $291.59 | $304.05 | +98.11 |
| 1000 | storage_focused | $62.67 | $73.72 | $76.90 | +14.23 |
| 10000 | budget_vps | $322.78 | $680.94 | $773.84 | +451.06 |
| 10000 | mainstream_cloud | $1837.60 | $2686.60 | $2810.81 | +973.20 |
| 10000 | storage_focused | $265.00 | $419.93 | $451.72 | +186.73 |

The 7.8 column uses its original 211,172-B context and incomplete local-copy pricing; the 7.22 frozen-v3 column uses 228,925.027778 R and corrected local capacity. Thus the entire difference versus 7.8 is **not** a measured-physical delta: canonical context, snapshot/workspace accounting and historical workload assumptions also changed. Balanced has a different admitted synthetic population; comparing it to 7.8 does not prove compression alone reduced cost. Original 7.8 JSON/monthly CSV and all 7.22/7.23 results remain byte-identical.

All three Balanced hosts are arithmetically below $100 at 100/day; only budget/storage are below at 1,000/day; none are below at 10,000/day. These misses remain explicit under the original acceptance contract. The CSV records every host/rate/workload verdict. No claim that all nodes cost below $100/month. The 100/day local requirement fits both included-capacity assumptions, while 1,000/day and 10,000/day exceed both 160 and 500 GiB and need actual expansion/tier quotes. In particular, the prior Balanced 1,000/day local estimate of 499.585 GiB barely fit the assumed storage-focused pool; the new two-copy recovery reserve moves it above 500 GiB. Historical Task 7.22 noted provider attachment/minimum/capacity and snapshot coverage restrictions; these are not refreshed contractual limits. Multi-TiB local requirements, compute/IOPS, backup/snapshot windows, bootstrap memory/pagination and restore time are unqualified. The blended storage host is unspecified. A low modeled bill cannot establish tier availability or production service capacity.

**Known service-boundary limitation:** even the 100/day three-year Balanced history contains 12.129 GiB of canonical bytes before duplicate certificates or JSON object expansion. The existing whole-history response plus `response.json()` therefore cannot load that projected history as one in-memory response on the assumed 8-GiB hosts. This is an inference from actual source and projected sizes, **not** a measured out-of-memory event. Reviewed bounded paging/streaming or another qualified retrieval procedure is required before production; none is implemented here. Cheap modeled bills do not fund an implicitly free memory/tier upgrade. This remains a production blocker, not a silently waived feasibility claim or a new activation.

## 9. Regression, reproduction and preservation

| Group | Passed | Failed | Skipped | Deselected | Time bound s | Actual s |
| --- | --- | --- | --- | --- | --- | --- |
| canonical | 119 | 0 | 0 | 0 | 360 | 35.04 |
| codecs | 386 | 0 | 0 | 0 | 360 | 56.00 |
| persistence | 43 | 0 | 0 | 0 | 360 | 84.52 |
| historical_arithmetic | 33 | 0 | 0 | 0 | 360 | 13.54 |
| physical | 13 | 0 | 0 | 0 | 360 | 6.78 |

Final focused suite: **594 passed, 0 failed, 0 skipped, 0 deselected, 0 timeouts**. Initial loopback precheck: one environmental failure, then one permitted pass, separately recorded and not hidden in final-suite totals. No Linux/macOS containment qualification or unsafe WAL tests. Legacy WAL storage/backup and crash suites are deliberately outside collection, not claimed passing or counted as pytest deselections.

Supplementary development runs record **6 passes, 1 initial environmental failure, 0 skips, 10 deselections and zero timeouts**. The deselections belong to the three-test physical-control precheck. [all_test_attempts.json](../verification/task725/all_test_attempts.json) reconciles these with the final suite; aggregate attempt counts include repeated executions of the same nodes and are not unique test counts. Every initial failure remains recorded after its successful permitted rerun.

New tests independently reconcile page/index/transfer/cost arithmetic, frozen hashes, recovery workspace and finality boundaries; real identity/Zstd snapshot/copy/reopen and corrupted-commitment controls execute; a small real loopback pass and invalid-block control execute. Existing frozen canonical, adaptive decoder/sequence/isolation, safe persistence/restart and historical economics/reproduction guards also run. Exact argv, actual node outcomes, bounds and logs are in `*_outcomes.json`, `*_tests.txt`, [tests_execution.json](../verification/task725/tests_execution.json). [development_notes.json](../verification/task725/development_notes.json) retains initial environmental probes and development-only runner changes.

Exact reproduction commands, fresh-directory restrictions, environment requirements and full evidence map are in [README.md](../verification/task725/README.md). Inputs replay exactly in this run; no second full long-running physical measurement is falsely claimed. Three independent schema variants, drop probes, full recovery and independent arithmetic checks supply the recorded crosschecks. `compare.py` checks a future fresh full replay, excluding timings and the documented ephemeral-port request-header difference. Six historical checksum manifests and all preexisting tracked-file hashes are verified, with new evidence frozen in [checksums.sha256](../verification/task725/checksums.sha256). No historical observation or benchmark result is overwritten.

## 10. Original acceptance and separate production verdict

| Owner decision / remaining finding | Task 7.25 disposition |
| --- | --- |
| Provisional Balanced caps | INACTIVE; no configuration or protocol activation |
| Below-15% metadata | Measured **FAIL**, explicit Task 7.24 owner exception retained; no padding/removal/exclusion workaround |
| No-expansion comparison | Complete selected canonical record vs same-context identity, as owner chose; no universal raw E≤M or monotone SQLite claim |
| Disabled adaptive integration | Current Task 7.25 Step 10 expressly accepts this boundary for development completion; production stays inactive |
| Real-world representative qualification | Current instruction retains it as a **public-launch requirement**, not supplied by synthetic coverage |
| Physical-economics gap R4 | Resolved sufficiently for bounded development: actual schema/copies/recovery plus directly counted real-framed simulated transfer and qualified extrapolation |
| $100 target | Conditional passes and misses transparently documented; no new waiver needed or assumed |
| Distributed complete-block archive | Future/unstarted; no pruning/placement/replication implementation or discounted network cost |
| Canonical finalized membership / future history | Not established by standalone fixtures; authority/finality/reviewer interfaces and historical support remain separate production gates |

**Original Milestone 7: COMPLETE WITH OWNER-APPROVED LIMITATIONS.** This changes the historical INCOMPLETE finding because the present request explicitly resolves the disabled-development boundary and keeps real-world qualification at launch, while this task supplies the missing bounded physical-economics evidence. The original objective permits transparent affordability misses. Metadata remains a measured FAIL under the already approved exception. No new material technical failure is silently waived.

**Production/network: BLOCKED.** Real-world content/traffic qualification, independent security and supported-platform decoder review, approved v3 limits/version/height, authenticated authority/finality/reviewer history, real network/service throughput and regional hosting/backup capacity quotes remain outstanding. Packet/TLS/loss overhead and future journal/archive traffic require their own evidence. The future archival architecture is not a prerequisite newly imposed on original compression closeout and is not begun.

**Task 7.25 is ready for owner review and commit. Milestone 7 development can now close with these documented limitations.** No commit or production activation is performed.
