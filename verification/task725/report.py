"""Render the Task 7.25 report from measured evidence, without historical writes."""
import json
from pathlib import Path
import statistics

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
GIB=1024**3


def read(name):
    return json.loads((HERE/name).read_bytes())


def table(headers,rows):
    return '\n'.join(['| '+' | '.join(headers)+' |','| '+' | '.join(['---']*len(headers))+' |',
                      *['| '+' | '.join(map(str,row))+' |' for row in rows]])


def main():
    before=read('preflight.json');w=read('workloads.json');db=read('sqlite.json')['populations']
    backup=read('backup_recovery.json')['populations'];net=read('transfer.json');econ=read('projections.json');tests=read('tests_execution.json')
    counts=tests['counts'];names=['historical36','production34','meme58','balanced41']
    assert set(g['group'] for g in tests['groups'])=={'canonical','codecs','persistence','historical_arithmetic','physical'}
    assert all(g['exit']==0 for g in tests['groups']) and tests['timeouts']==0 and counts.get('failed',0)==0
    assert read('copy_execution.json')['source_databases_unchanged']
    for name in names:
        assert backup[name]['verification']['blocks']==db[name]['full']['observations'][-1]['blocks']
        assert backup[name]['verification']['fresh_process'] and backup[name]['verification']['original_commitments']
    probes=[p for p in read('development_notes.json')['initial_checks'] if 'passed' in p]
    supplemental={k:sum(p.get(k,0) for p in probes) for k in ('passed','failed','skipped','deselected')}
    rows=[]
    for name in names:
        t=w['totals'][name];legal_original=sum(r['original_bytes'] for r in w['rows'][name] if r['record_bytes'] is not None)
        rows.append([name,t['originals'],t['legal_records'],f"{t['original_bytes']:,}",f'{legal_original:,}',f"{t['encoded_bytes']:,}",f"{t['canonical_bytes']:,}",str(t['choices'])])
    workloads=table(['Workload','Originals','Legal R','Original-domain B (all)','Legal-record original B','Selected E B','Complete R B','Choices'],rows)
    rows=[];indexrows=[];latencies=[]
    for name in names+['native_index_control']:
        s=db[name];first=s['full']['observations'][0];last=s['full']['observations'][-1]
        rows.append([name,last['blocks'],f"{last['canonical_bytes']:,}",f"{last['logical_bytes']:,}",last['page_count'],last['free_pages'],f"{100*last['database_overhead_bytes']/last['canonical_bytes']:.3f}%",f"{first['logical_bytes']:,}"])
        indexrows.append([name,s['file_differences']['full_minus_minimal'],s['file_differences']['full_minus_no_secondary'],s['secondary_pages']['secondary_allocation_bytes'],s['full']['index_entries']['transaction_id_idx']])
        full=s['full']['retrieval'];no=s['no_secondary']['retrieval'];minimal=s['minimal']['retrieval']
        latencies.append([name,f"{statistics.median(full['primary_key_ns_per_get'])/1000:.2f}",f"{statistics.median(minimal['primary_key_ns_per_get'])/1000:.2f}",f"{statistics.median(full['height_ns_per_get'])/1000:.2f}",f"{statistics.median(no['height_ns_per_get'])/1000:.2f}"])
    sqlitetable=table(['Workload','Blocks','Canonical B','Main file B','Pages','Free pages','Gross DB overhead / R','Empty DB B'],rows)
    indextable=table(['Workload','Full − minimal B','Full − no secondary B','Drop-probe secondary B','Native index entries'],indexrows)
    no_secondary={r['blocks']:r for r in db['balanced41']['no_secondary']['observations']}
    indexgrowthtable=table(['Balanced blocks','Secondary aggregate file allocation B'],[
        [r['blocks'],r['logical_bytes']-no_secondary[r['blocks']]['logical_bytes']] for r in db['balanced41']['full']['observations']])
    latencytable=table(['Workload','Full PK µs','Minimal PK µs','Full height µs','No-secondary height µs'],latencies)
    rows=[]
    for name in names:
        c=econ['coefficients'][name];rows.append([name,c['measured_blocks'],f"{c['overhead_per_block']:.3f}",f"{c['overhead_range'][0]:.3f}–{c['overhead_range'][1]:.3f}",f"{c['initial_db_bytes']:,}"])
    slopetable=table(['Workload','Largest measured n','Final marginal overhead B/block','Complete-cycle interval range B/block','One-time init B'],rows)
    rows=[]
    for name,r in backup.items():
        size=r['source']['logical_bytes'];workspace=r['recovery']['peak_directory_bytes']-r['snapshot']['logical_bytes']
        rows.append([name,r['verification']['blocks'],f'{size:,}',f"{r['snapshot']['logical_bytes']:,}",f"{r['backup']['bytes']:,}",f"{r['recovery']['additional_workspace_bytes']:,}",f'{workspace:,}',f"{r['peak_including_live_source_bytes']:,}"])
    backuptable=table(['Workload','Restored blocks','Source B','Snapshot B','Full backup B','Destination increment B','Workspace over live+snapshot B','Peak all four B'],rows)
    rows=[]
    for name in names:
        p=net['populations'][name];ex=[r for r in net['exchanges'] if r['label']==name+':propagation']
        canonical_bytes=p['canonical_bytes'];body=sum(r['request_body_bytes'] for r in ex)
        http=sum(r['request_http_framing_bytes'] for r in ex)
        rows.append([name,p['n'],f'{canonical_bytes:,}',f'{body:,}',f'{body-canonical_bytes:,}',f'{http:,}',f"{p['propagation_acknowledgment_bytes']:,}",f"{p['propagation_stream_ratio']:.6f}×",f"{p['historical_response_bytes']:,}"])
    transfertable=table(['Workload','Blocks','Canonical B','Send bodies B','Application excess B','Request HTTP B','ACK stream B','Sender / R','Fresh history response B'],rows)
    rows=[]
    for s in econ['scenarios']:
        if s['workload']!='balanced41' or s['profile']!='budget_vps':continue
        m=s['month36'];rows.append([s['blocks_per_day'],f"{m['canonical_bytes']/GIB:.3f}",f"{m['primary_database_bytes']/GIB:.3f}",f"{m['snapshot_bytes']/GIB:.3f}",f"{m['recovery_workspace_bytes']/GIB:.3f}",f"{m['operational_headroom_bytes']/GIB:.3f}",f"{m['local_capacity_bytes']/GIB:.3f}",f"{m['backup_retained_bytes']/GIB:.3f}",f"{m['bootstrap_once_bytes']/GIB:.3f}"])
    balancedtable=table(['Blocks/day','Canonical GiB','Primary P GiB','Snapshot GiB','Recovery W GiB','Headroom H GiB','Local GiB','Remote backups GiB','Bootstrap GiB'],rows)
    costrows=[];histrows=[]
    for c in econ['comparisons']:
        row=[c['blocks_per_day'],c['profile'],f"${c['prior_same_population_usd']:.2f}",f"${c['updated_usd']:.2f}",f"{c['delta_usd']:+.2f}",f"{c['measured_storage_and_recovery_basis_delta']:+.2f}",f"{c['measured_backup_ratio_delta']:+.2f}",f"{c['measured_simulated_transfer_basis_delta']:+.2f}",'BELOW' if c['updated_usd']<100 else 'ABOVE']
        if c['workload']=='balanced41':costrows.append(row)
        if c['workload']=='historical36':histrows.append([c['blocks_per_day'],c['profile'],f"${c['original_task78_representative_usd']:.2f}",f"${c['prior_same_population_usd']:.2f}",f"${c['updated_usd']:.2f}",f"{c['delta_vs_original_task78']:+.2f}"])
    costtable=table(['Blocks/day','Host','Prior 7.23','Updated','Total Δ $','Storage + recovery Δ','Backup Δ','Transfer Δ','vs $100'],costrows)
    historicaltable=table(['Blocks/day','Host','Original 7.8','Frozen-v3 7.22','Physical update','Δ vs 7.8 $'],histrows)
    testtable=table(['Group','Passed','Failed','Skipped','Deselected','Time bound s','Actual s'],[[g['group'],g['counts'].get('passed',0),g['counts'].get('failed',0),g['counts'].get('skipped',0),g['deselected'],g['timeout_seconds'],f"{g['elapsed_seconds']:.2f}"] for g in tests['groups']])
    text=f'''# Milestone 7 Task 7.25 — Physical storage and network economics verification

Date: **2026-11-03, America/New_York**. Version 1, bounded measurement only.

**Original Milestone 7 development: COMPLETE WITH OWNER-APPROVED LIMITATIONS. Production/network: BLOCKED. Task 7.25 is ready for owner review and an owner-performed commit.** Milestone 7 can close for development with the limitations below; no public launch, protocol activation or distributed archival system is authorized.

## 1. Prerequisites and unchanged scope

Branch: `{before['branch']}`. Initial and final HEAD: `{before['head']}`. Separate Task 7.24 commit is that HEAD, `Milestone 7 Task 7.24: document final acceptance and distributed archival architecture`. Initial worktree/index were completely clean, including untracked files. All {len(before['tracked_sha256']):,} preexisting tracked files were present and hashed. All previous Milestone 7 reports, generators, manifests and evidence remain tracked and unchanged; generated media under ignored paths remain generated, not relabeled tracked inputs. No applicable AGENTS.md was found. No delegation was used.

Only this report and [verification/task725](../verification/task725/README.md) are added. Final status contains only these untracked deliverables; index/HEAD/branch and all preexisting tracked bytes are unchanged, recorded in [preservation.json](../verification/task725/preservation.json). No reset, clean, stash, stage, commit, push, merge, production DB/backup access, protocol/consensus/genesis/configuration change, WAL activation or Task 7.26/archive work.

Read the seven requested historical reports, source and frozen results. [source_versions.json](../verification/task725/source_versions.json) identifies inspected implementation boundaries. `canonical_v3/media.py` selects valid Zstd versus identity by complete descriptor size, verifies exact accepted originals and stores base64. `block.py` binds complete canonical bytes and signed certificates. `storage.py` uses a WITHOUT ROWID canonical BLOB table plus derived tables and four named secondary indexes. The existing Task 7.21 `DisposableStore` reuses actual inherited insert/get/index operations and the exact schema with DELETE/EXTRA initialization. The legacy initializer/backup verifier would enable WAL, so neither is invoked.

The active backup CLI exports a different v1 JSON application snapshot; it is not falsely reported as accepting this disabled v3 database. This study uses SQLite's actual consistent backup API and full byte-copy recovery at the isolated storage boundary. Active network handling accepts versions 1/2, so v3 transfer is explicitly simulated at the closest existing HTTP services and serialization boundary.

## 2. Workloads, identities and Balanced eligibility

{workloads}

E includes codec framing; R is the entire stored canonical JSON block. Every record's MIME, source/accepted sizes and hashes, E, R, codec, block identity and cap inclusion/exclusion are in [workloads.json](../verification/task725/workloads.json). All 126 constructible primary records reproduce their exact frozen canonical SHA-256, not merely lengths. Balanced reuses 41 of those records; it is not another 41 independent originals. Meme coverage denominators retain all 58 originals. The JPEG 2,242,286-B and PNG 3,594,660-B texture originals exceed the frozen 2-MiB original cap: E/R/identity are unavailable, never fabricated. The separate 7.23 diagnostic is excluded only as originally declared. A separate golden native-transaction control tests transaction-index allocation and is excluded from economics.

All populations are synthetic, equal-record coverage, with no observed production distribution. The historical source has 6,093,917 B versus 6,093,910 accepted B after its preexisting seven-byte text normalization. Later corpora's accepted/source domains match. Exact regenerated manifests, original commitments and frozen R hashes are checked before physical measurement. Frozen corpora and historical benchmarks are unchanged.

Balanced remains provisional/inactive: static images 262,144 B, animated GIF 524,288 B, canonical text 16,384 B, encoded 525,312 B (**513 KiB**), complete R 1,048,576 B. Single-frame GIF uses the static cap; animated WebP conservatively uses static MIME cap. The 41/58 inclusion matches Task 7.23. These are size gates, not proof of admission, demand or an activation decision.

Additional storage cycles reuse exact media/certificates, change only the unsigned header height and resulting block hash, and pass actual format/signature/strict-media checks on insertion. They are independent valid candidates for allocation experiments, not a fabricated selected/finalized chain, production traffic or authenticated ancestry. No BLOB deduplication or physical savings versus an identical JSON representation are assumed.

## 3. Actual SQLite growth, occupancy and marginal behavior

Reference: Windows AMD64, CPython 3.13.5, SQLite **3.49.1**, page size **4,096 B**, journal **DELETE**, synchronous **EXTRA (3)**. Package/compiler/OS details and compile flags are in [environment.json](../verification/task725/environment.json). No dependency was changed.

{sqlitetable}

File length is page_count×page_size in these observations. Live allocated pages equal `(page_count−freelist_count)×page_size`; this is occupancy of allocated B-tree pages, **not** exact useful cell payload or absence of internal slack. Filesystem allocated bytes and sparse/compressed/reparse attributes are separately recorded. No measured file is sparse or compressed; no hardlink/reflink savings are credited. Host/VHD/storage-layer deduplication, thin provisioning and physical-device independence are not observable here.

Samples include empty, 1, 5, one/two/four corpus cycles; Balanced extends to 8/16/32 cycles (1,312 records). [sqlite.json](../verification/task725/sqlite.json) contains every sample, per-interval total and overhead marginal growth, SQLite settings and separate schemas. Fixed initialization is charged **once**, never multiplied per block. Final complete-cycle marginal overhead, net of the actual canonical bytes in that interval, supplies the projection coefficient:

{slopetable}

The range is observed full-cycle interval variation, not a confidence interval or a proven large-N bound. Prefix composition and whole-page allocation create steps; the small append-only sample does not establish multi-year behavior or deeper B-tree/fragmentation costs. Some first-record net-overhead increments are negative because already allocated initial pages gain payload; this is not negative file growth or evidence of compression. Those prefixes are excluded from extrapolation. Initialization dominates tiny samples, while complete-cycle marginal data/page/index growth is much smaller than the old assumed 10% index/page factor. Aged fragmentation remains a separately labeled 15% planning allowance. Header digit growth at millions of blocks and churn/forks require later measurement; none are silently claimed measured.

## 4. Separate index accounting and retrieval observations

{indextable}

Minimal retains the exact same canonical BLOB/primary-key table and immutable triggers. Full-minus-minimal includes context/settings, derived block/transaction tables, secondary indexes and fixed schema: it is an **incremental schema footprint**, not a precise pure-index estimate. The no-secondary database retains all tables, primary/unique/FK/immutability semantics and removes only the four nonunique query indexes in a disposable comparison. Full-minus-no-secondary is actual file allocation difference with equivalent integrity semantics; page packing can make it differ from separately reclaimable index pages.

`dbstat` is unavailable. On a full disposable copy, dropping each secondary index without VACUUM leaves file length/page count fixed and directly measures its increment in freelist pages. This is the **marginal releasable allocation**, including any schema-page release; per-index pages are retained. WITHOUT ROWID primary B-trees combine keys/data and cannot be split precisely without changing layout. No required production index is removed. Primary and derived integrity, immutable update/delete, duplicate identity, BLOB type/size, SQLite integrity and foreign-key checks pass. All media-only populations have zero native transactions; the native control's transaction entries quantify a separate lower-coverage dimension, not a production transaction mix.

{indexgrowthtable}

[index_growth.json](../verification/task725/index_growth.json) retains the equivalent aggregate secondary-file and live-page difference at **every** sample count for every workload, plus the full-minus-minimal schema footprint. Empty index roots are fixed overhead. At 1,312 Balanced blocks the per-index DROP probe releases height 110,592 B, previous-hash 212,992 B, original-hash 221,184 B and empty transaction-ID root 4,096 B, totaling **548,864 B**. The endpoint file difference agrees exactly in this run; no assertion of generic page-packing equality is needed.

The separate 32-record native control has **16.20% gross physical overhead**, versus 0.62–1.97% in the larger media populations. Its smaller records, one transfer per candidate, low sample count and BLOB/page quantization differ from the main corpora: this is **not** a pure 16.20% transaction-index charge. Its transaction-ID index grows to 12,288 B with 32 entries. Zero-transfer media coefficients and $100 results must not be generalized to transaction-heavy traffic; a realistic native-transfer mix remains part of operational economics qualification.

Warm-cache median query/BLOB-fetch timings, five batches, µs (observational, same SQL):

{latencytable}

Full height queries use `block_height_idx`; comparison plans show a table scan without it. PK retrieval includes actual BLOB fetch. These small, warm, sequential local checks exclude crypto/decoder time and do not qualify concurrency, cold-cache IOPS, production latency or a restore SLA.

## 5. Consistent snapshots, full backups and recovery

{backuptable}

Every consistent SQLite online-backup snapshot and every uncompressed full backup is **1.000000×** its source in this run. Four retained backups therefore require exactly four measured backup sizes at the tested population, rather than the old assumed 0.95 factor. Copy sizes are not retention-policy measurements.

Full backup and restore use exclusive streaming writes, fsync each 1-MiB chunk and verify whole-file SHA-256, separate file identities and compression/sparse attributes. Snapshot is a standalone database, not a dependent CoW layer. Copies remain on the same volume and share a device/failure domain; no independent remote archival durability is inferred. Daily snapshot refresh, four monthly uploads and four remotely retained full copies are still modeled operational policies.

The measured restore procedure retains live DB + snapshot + staged full backup + restored DB. Monotone, fsynced file-length observations give the actual copy high water. One new destination is one source-sized increment, but workspace above normal live+snapshot retention is **two source-sized copies** (staged backup plus destination). The revised local forecast funds both. RAM/OS buffers and unobserved underlying storage allocation are outside that file-workspace measurement; no VACUUM/decompression workspace or provider snapshot service is claimed tested.

Every recovered database is reopened by a **fresh Python process** with the explicit trusted fixture context. Actual inherited `get` independently parses/verifies canonical/signature/index bindings and runs the real isolated decoder for every stored record. The decoder output used by that get is observed directly to avoid redundant second decoding. Block set, exact canonical SHA-256, original byte length and original-byte SHA-256 match the independently frozen/reconstructed commitments; SQLite integrity/FKs and derived/orphan counts pass. The parent also retrieves and compares every canonical byte string against its pre-backup original. Initial corpus reconstruction compared actual original bytes directly. No original/media cache is supplied to recovery. Selected/finality counts remain zero: internal identity/reconstruction does not establish canonical finalized membership. Details: [backup_recovery.json](../verification/task725/backup_recovery.json).

After completing all SQLite measurements and the first historical recovery, the development run was interrupted to eliminate a redundant second parent decode. `measure.py --copies-only` continues from the same measured source databases into a new disposable copy directory; the parent comparison now uses read-only SQL, while the fresh child still fully verifies every record. [copy_execution.json](../verification/task725/copy_execution.json) records byte-identical source-file hashes before/after and the bounded continuation. The whole fresh-recovery process bound is 1,200 seconds; per-object decoder limits are unchanged. This is a recorded development interruption, not a hidden failure or timeout.

## 6. Measured transfer: real framing, simulated v3 service

{transfertable}

Counts above cover all unique legal records per workload, not expanded storage cycles. Propagation uses the **actual** `PeerBroadcastService.broadcast_block`: first a separate certificate POST, then a block wrapper containing another certificate plus the complete block (which already contains its certificate). This duplicated evidence and requests' actual JSON spacing/escaping are charged. Optional external originality-evidence transfers are absent/unqualified, not asserted free in a future protocol. The receiver authenticates real fixture HMAC headers, canonicalizes the received map back to exact R, verifies signed canonical identity and reconstructs original media through the disabled service.

The measured sender excess over R is **56.49% Balanced**, **29.35% historical**, **14.25% full legal meme** and **14.46% production-like**, before the model's separate contingency; ACKs are additional. Balanced bounded-history responses add **26.52%** over canonical bytes. Fixed certificate/wrapper charges explain this meaningful workload variance. A large-object corpus ratio cannot substitute for the smaller Balanced mean, and this application excess is not a packet-overhead measurement. All **346** exchanges complete without application failure in the permitted measurement pass. The sideband certificate POST measures framing only; the embedded certificate is cryptographically validated as part of the canonical block. No active v1 certificate admission or v3 network acceptance is claimed.

For each workload, actual `PeerChainSyncService.fetch_blocks` performs single historical, bounded eight-block and fresh bounded-history GETs. Starlette's real JSONResponse serializer emits the source-derived `blocks/certificates/originality_evidence` wrapper. Returned records match exact sent canonical bytes and are independently reconstructed. Fresh history includes all declared records; it excludes genesis/summary/handshake, reviewer/authority/finality proof acquisition and adoption. It is **not a measured fresh production node bootstrap**. The current service fetches whole remaining history; no pagination or archive protocol is implemented.

[transfer.json](../verification/task725/transfer.json) retains each exchange: canonical payload, request/response bodies, application excess, HTTP request/response framing, authentication-header subset and checksums. Auth bytes are already inside HTTP framing and are never double-counted. HTTP stream octets are observed; TCP/IP/link framing, TLS and TCP retransmissions are **unobserved/null**, not invented zeroes. HTTP is unencrypted loopback, sequential, uncompressed, unchunked, no application retries/redirects. One connection per exchange. Ephemeral port digits can change request header lengths by up to two bytes on replay. Application payloads/checksums have no tolerance.

ACKs use the harness's explicitly synthetic `accepted/integration_status` response, serialized by real Starlette; they are not an approved active-v3 response contract. Their octets are measured for that fixture, and their use in a future bill remains part of the simulated-boundary assumption. Request wrappers/history response structure come from the existing services/source, while all claims of active acceptance remain blocked.

The first restricted Windows loopback precheck failed with WinError 10013 before transmitting a payload; the identical permitted local-only test passed. The complete transfer pass runs with local-connection permission. Both development outcomes and any restricted main-run attempt are preserved. No public peer or active HTTP route is contacted/registered. This satisfies the requested **explicit simulated-transfer alternative**, not v3 network activation or production P2P qualification.

## 7. Three-year projection and measured-versus-assumed split

36 months = 1,095 days, normal month lengths with February fixed to 28 days. Rates imply 109,500 / 1,095,000 / 10,950,000 retained complete records. One GiB = 2³⁰ B. Main scenario is equal-admitted Balanced mean R **118,935.536585 B**. All nodes retain full history in these scenarios; distributed allocation receives no savings credit.

{balancedtable}

Full monthly series for all four workloads, three rates and three hosts (36 scenarios) plus 54 Balanced sensitivities are in [projections.json](../verification/task725/projections.json); [month36.csv](../verification/task725/month36.csv) contains all final bills/capacities. Historical full-retention datasets remain available for comparison. Their complete canonical bytes and actual measured coefficients replace guessed physical overhead; historical small/large analytical scenarios are preserved unchanged rather than relabeled measured.

Measured inputs are original/R/E identities, one-time initialization, final complete-cycle marginal overhead and its interval range, snapshot/full-backup ratio, recovery-file coexistence, and actual application/HTTP transfer sizes at the simulated service boundary. Projection is an **extrapolation**, not physical measurement of three years. All prices, weights, retention/upload frequency, 1-GiB nonmedia reserve, 15% aged fragmentation, 20% operational reserve, 1.45× monthly write reserve, fixed 5-GiB headroom, eight outgoing peers, one incoming propagation, 20% traffic contingency, and one bootstrap/restore served per year remain assumptions. The 1.45 factor is retained workspace planning, not WAL use or measurement. The 20% traffic contingency is not a fabricated packet count.

The model charges primary `P=1GiB+init+N*(mean_R+marginal_overhead)+.15*C`; snapshot S=P; recovery W=2P; operational `H=.20P+1.45*monthly*(R+overhead+.15R)+5GiB`; local capacity `P+S+W+H`. Four measured 1× full backups are priced remotely, with four P-sized uploads/month. Propagation uses actual sender/ACK means at eight peers, then 1.20 assumed contingency. Bootstrap uses measured per-record canonical+certificate+array bytes and **one** fixed collection/HTTP charge; small-batch initialization is not multiplied per block. The bootstrap quantity is the server response/egress; its GET request is measured separately and ingress is assumed free. Yearly expected bootstrap and restore service are priced as monthly 1/12 fractions. Backup upload protocol framing remains unmeasured and uncredited. Baseline reserve/fragmentation applied to copied P are conservative model allowances, not newly measured application-state bytes.

Sensitivity cases vary complete-cycle marginal range, remove aged fragmentation, increase traffic contingency, double peers and retain twelve backups. They expose model dependence; their range is not a probability interval or universal workload cap. Four workloads' full-retention comparisons are in the CSV; no actual production weights, long-term fragmentation, cold storage throughput, administrative cost or future proof/journal/archive traffic is asserted measured.

## 8. Updated month-36 hosting economics and $100 target

Historical [Task 7.22 USD inputs](../verification/task722/economic_inputs.json) and [pricing review](../verification/task722/pricing_review.json) are deliberately reused, with no provider recommendation or fabricated current quote: budget $20 compute /160 GiB included /$0.05 extra GiB /$0.006 backup GiB /$0.01 egress GiB; storage-focused $45 /500 /$0.02 /$0.006 /$0.01; cloud $40 /160 /$0.10 /$0.05 /$0.09. Each assumes 4 vCPU/8 GiB but does not qualify them. The budget/cloud/storage labels describe illustrative pools, not purchasable verified regional plans. Disk uses the inherited ceil-to-GiB marginal billing rule; transfer allowances, taxes/currency and tier premiums are not invented.

{costtable}

Δ is a sequential additive attribution: prior Task 7.23 formula → measured SQLite **and two-copy recovery** basis → measured 1× backup ratio → measured simulated transfer basis. R/population, prices and other default assumptions are held fixed in that comparison. These deltas are caused by measured coefficients **inside an assumption-driven extrapolation**, not invoices or three-year observed savings. The storage/recovery term deliberately includes the larger recovery coexistence requirement; the backup term includes retained backup and expected restore-transfer effects. Each line sums to the total delta, with only display rounding. The new full-meme comparator is the prior formula applied to that corpus, explicitly distinguished from an already published bill.

Original representative-corpus economics, preserved and compared transparently:

{historicaltable}

The 7.8 column uses its original 211,172-B context and incomplete local-copy pricing; the 7.22 frozen-v3 column uses 228,925.027778 R and corrected local capacity. Thus the entire difference versus 7.8 is **not** a measured-physical delta: canonical context, snapshot/workspace accounting and historical workload assumptions also changed. Balanced has a different admitted synthetic population; comparing it to 7.8 does not prove compression alone reduced cost. Original 7.8 JSON/monthly CSV and all 7.22/7.23 results remain byte-identical.

All three Balanced hosts are arithmetically below $100 at 100/day; only budget/storage are below at 1,000/day; none are below at 10,000/day. These misses remain explicit under the original acceptance contract. The CSV records every host/rate/workload verdict. No claim that all nodes cost below $100/month. The 100/day local requirement fits both included-capacity assumptions, while 1,000/day and 10,000/day exceed both 160 and 500 GiB and need actual expansion/tier quotes. In particular, the prior Balanced 1,000/day local estimate of 499.585 GiB barely fit the assumed storage-focused pool; the new two-copy recovery reserve moves it above 500 GiB. Historical Task 7.22 noted provider attachment/minimum/capacity and snapshot coverage restrictions; these are not refreshed contractual limits. Multi-TiB local requirements, compute/IOPS, backup/snapshot windows, bootstrap memory/pagination and restore time are unqualified. The blended storage host is unspecified. A low modeled bill cannot establish tier availability or production service capacity.

**Known service-boundary limitation:** even the 100/day three-year Balanced history contains 12.129 GiB of canonical bytes before duplicate certificates or JSON object expansion. The existing whole-history response plus `response.json()` therefore cannot load that projected history as one in-memory response on the assumed 8-GiB hosts. This is an inference from actual source and projected sizes, **not** a measured out-of-memory event. Reviewed bounded paging/streaming or another qualified retrieval procedure is required before production; none is implemented here. Cheap modeled bills do not fund an implicitly free memory/tier upgrade. This remains a production blocker, not a silently waived feasibility claim or a new activation.

## 9. Regression, reproduction and preservation

{testtable}

Final focused suite: **{counts.get('passed',0)} passed, {counts.get('failed',0)} failed, {counts.get('skipped',0)} skipped, {tests['deselected']} deselected, {tests['timeouts']} timeouts**. Initial loopback precheck: one environmental failure, then one permitted pass, separately recorded and not hidden in final-suite totals. No Linux/macOS containment qualification or unsafe WAL tests. Legacy WAL storage/backup and crash suites are deliberately outside collection, not claimed passing or counted as pytest deselections.

Supplementary development runs record **{supplemental['passed']} passes, {supplemental['failed']} initial environmental failure, {supplemental['skipped']} skips, {supplemental['deselected']} deselections and zero timeouts**. The deselections belong to the three-test physical-control precheck. [all_test_attempts.json](../verification/task725/all_test_attempts.json) reconciles these with the final suite; aggregate attempt counts include repeated executions of the same nodes and are not unique test counts. Every initial failure remains recorded after its successful permitted rerun.

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
'''
    (ROOT/'docs/milestone-7-physical-storage-and-network-economics-verification.md').write_text(text,encoding='utf-8')
    print('Report generated from raw measurements')


if __name__=='__main__':
    main()
