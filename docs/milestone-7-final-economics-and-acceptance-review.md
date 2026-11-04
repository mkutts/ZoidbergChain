# Milestone 7 Task 7.22 — Final three-year economics and original-scope acceptance review

Date: **2026-10-28, America/New_York**. **Original Milestone 7 acceptance: INCOMPLETE. Production/network activation readiness: BLOCKED.** Task 7.22 is a completed acceptance audit, ready for review and an owner-performed commit; the milestone is not accepted. No exception has been approved for a failed mandatory target.

## 1. Preflight, authority and preservation

Branch: `Compression-State-Bloat-and-Node-Economics`. HEAD: `43f299c9a130135fe8823ec1eedadec8313bf765`. Task 7.21 is separately committed at that HEAD. Initial index/worktree were clean including untracked files; all requested Task 7.18–7.21 reports/evidence were tracked. No applicable repository/ancestor AGENTS.md was found and no delegation was used. [preflight.json](../verification/task722/preflight.json) records every preexisting tracked-file SHA-256 and environment.

Read the four final scope reports, historical codec/composition/SQLite/economics reports, and their actual scripts, configs, row ledgers, canonical producer/decoder, disabled bridge/recovery and focused tests. This report uses the original owner contract, not later journal design work. Only this document and `verification/task722/` are added. Production source, test assertions, frozen formats/fixtures, approved parameters and historical reports/results are unchanged. No stage, commit, reset, clean, stash, push, merge, migration, reset, live API/validator operation, deployment or WAL activation was performed. [preservation.json](../verification/task722/preservation.json) verifies unchanged preexisting files, branch, HEAD and index.

## 2. What changed since the Task 7.18 audit

Task 7.19 repaired source-identity reproduction wrappers while preserving immutable bytes and obsolete historical admission observations. Task 7.20 added 34 separately versioned synthetic production-like objects, substantive prose/JSON/source examples, seven-codec trials, 78 complete signed ledgers and two justified historical-test repairs. It measured, rather than fixed, the <15% metadata miss. Task 7.21 connected real upload/admission/construction and canonical retrieval interfaces in an explicitly disabled bridge, including DELETE/EXTRA persistence and fresh-process recovery. This audit closes the previously omitted snapshot/headroom/recovery capacity charges, preserves historical projections, and identifies the natural raw-payload expansion counterexample below. None of these steps activated compressed media or supplied independent security/Linux qualification.

## 3. Original, encoded, serialized and physical bytes

| Population | Original M B | Encoded E B | Base64 B B | Media member B | Complete R B |
| --- | --- | --- | --- | --- | --- |
| Historical 36 accepted originals | 6,093,910 | 5,285,229 | 7,047,024 | 7,055,315 | 8,241,301 |
| Task 7.20 new 34 originals | 11,521,163 | 11,002,892 | 14,670,572 | 14,678,466 | 15,798,621 |

The new totals reproduce exactly: **11,521,163 original − 518,271 codec saving = 11,002,892 encoded; +3,667,680 base64 expansion +7,894 descriptor/member framing = 14,678,466 serialized media bytes**. Other header/certificate/transaction/envelope bytes add 1,120,155, giving **15,798,621 complete canonical bytes**. `B=4*ceil(E/3)`; codec-frame bytes, checksum and content-size framing are already inside E and are not counted twice. The canonical descriptor includes the eight required fields; the media-member total also includes its JSON key.

The historical source corpus remains **6,093,917 B**, while its accepted canonical-text domain totals **6,093,910 B** after the existing seven-byte normalization. The new source/accepted domains match. Sensitivity records reuse four originals; they are not extra unique objects or part of the new 34-object totals. Across 70 unique accepted originals: M=17,615,073; E=16,288,121; base64=21,717,596; media members=21,733,781 B. Primary complete R=24,039,922 B. [compression_reconciliation.json](../verification/task722/compression_reconciliation.json) independently reconciles the exact integer partitions from tracked per-field ledgers.

Original M is a recoverable logical domain, not a second required physical media copy. R is the canonical data actually stored in a BLOB; it retains base64. Physical DB/index/page allocation, free pages, recovery copies, snapshots and backups are distinct additional domains. Raw codec savings prove neither R≤M nor physical disk savings.

### No-expansion interpretation and concrete counterexamples

The implemented normal selector tests `len(J(zstd_descriptor)) < len(J(identity_descriptor))`, then strictly reconstructs its selection; INVALID compressed profiles fall back to verified identity and local decoder failure does not become fallback success. The baseline is the **same original, identity representation, and otherwise identical frozen record context**. Since all other fields and the 64-character record hash have constant lengths under that replacement, descriptor delta equals media-member and complete-R delta. This is a valid canonical-storage interpretation of B in the disabled implementation; owner acceptance of its application scope remains open.

| Layer / comparison | Outcome | Evidence / limit |
| --- | --- | --- |
| Raw E≤M | FAIL as universal producer guarantee | 104→105 natural default Zstd output; selector does not test raw length. All primary corpus selections happen to satisfy E≤M. |
| E plus descriptor non-payload bytes (hypothetical binary ledger) | Measured PASS versus identity | Counterexample 327→324 B; not the actual frozen stored format or an independently implemented selection test. |
| Complete canonical descriptor / media member versus identity | PASS, isolated implementation | All 78 primary/sensitivity rows; comparison includes base64, keys, algorithm label and size fields. |
| Complete fixed-context canonical R versus identity | PASS, isolated implementation | All 78 rows; counterexample 33,330→33,326 B. |
| Serialized media or R versus raw original M | FAIL as universal savings claim | New media total 14,678,466 > 11,521,163 M; mandatory evidence and base64 make tiny originals expand. |
| Physical DB/index/pages versus identity | NOT VERIFIED as a monotonic guarantee | SQLite allocation and indexes are not selection inputs; pages/row layout and write history can dominate. |
| Validator refuses externally larger valid encodings | Not required by B; no such consensus rule | Tracked valid alternate 249→261 descriptor, 33,215→33,227 R; producer retains identity. |

[producer_counterexample.json](../verification/task722/producer_counterexample.json) retains the exact printable 104-byte input and hashes. The **unmodified native default encoder and normal producer** select E=105 with VALID exact reconstruction. Base64 stays 140 B; codec label `zstd` is four bytes shorter than `identity`, so the descriptor shrinks **363→359 B** and R shrinks **33,330→33,326 B**. No monkeypatch or protocol change forces this result. If B instead means raw encoded bytes, that interpretation remains a measured acceptance gap; it cannot silently inherit the canonical comparison PASS. Physical-allocation savings are never asserted.

## 4. Metadata: exact population, ledger and FAIL

For each complete primary record, N=R−B where B is base64 payload content characters only, and metadata%=100N/R. Descriptor fields/quotes/framing and all security/transaction/header evidence are included. The stricter 100(R−E)/R also counts base64 expansion; it cannot improve the verdict. Each per-field JSON byte ledger and independent additive component partition sum to R exactly. Every baseline has fourteen votes, creator attestation/reward and an empty native array; eight separately labeled ten-vote/long-metadata cases never enter the primary percentiles. There is no invented producer-block signature.

| Population | n | p50 % | p95 % | Worst % | Equal-record mean % | Canonical-byte share % |
| --- | --- | --- | --- | --- | --- | --- |
| Historical frozen v3 | 36 | 85.97237 | 99.60381 | 99.85557 | 70.81241 | 14.49136 |
| New frozen v3 | 34 | 54.70902 | 99.80752 | 99.81935 | 53.05444 | 7.14017 |

Percentiles are equal-record **nearest rank**, sorted index `ceil(n*p/100)−1`: new p50 is rank 17 and p95 rank 33; historical p50 rank 18 and p95 rank 35. **Criterion C: FAIL.** Only 12/34 new records are below 15%; a 7.14017% byte-weighted share does not replace p50/p95/worst or the 53.05444% equal-record mean. No tiny valid media is excluded. Historical projected 7.7 uses a different definition, `(R−complete media member)/R`, and a generated projection rather than frozen R; its reproduced v3-adaptive p50/p95/worst are 72.84841/97.57337/98.11770% (exact raw values in metadata_reconciliation.json). It is not substituted for frozen-v3 evidence.

### Required evidence, base64 and theoretical optimization

New nonmedia N totals **1,128,049 B**, including **1,073,154 B certificate members** (1,072,338 certificate-value bytes plus 816 key bytes), 7,894 media framing bytes and 47,001 other canonical bytes. The complete certificate is 95.134% of N; signature tokens are only a subset. Mandatory technical evidence, signed creator rights/attestation, fourteen signed reviewer messages/votes, bindings/digests/tallies and required repeated fields are all charged. These exact fields/bytes are unavoidable **under the frozen format**, not an assertion that every JSON byte is information-theoretically incompressible. Cryptographic validation confirms their presence.

Base64 adds **3,667,680 B**, separately from N. Together all non-E bytes are **4,795,729 B**, or **30.35536%** of R. Binary serializing payloads could theoretically avoid approximately one quarter of base64 character bytes, but changing the frozen canonical representation needs explicit consensus-format approval. Shorter field names, packed integers/keys or compression of redundant evidence could preserve semantic signed evidence only with a separately specified representation and cryptographic review; removing signatures/votes, trusting a future journal or omitting required bindings is not credited. Local physical layout, derived-index tuning and backup policies can change disk/cost without changing R, and therefore cannot make this canonical metadata percentage pass.

With fixed N, N/R<0.15 iff **B>(17/3)N**; approximately **E>(17/4)N** and **M>(17/4)N/q** for encoded/original ratio q. N≈33,178 B requires B≈188,008 B or E≈141,006 B. At q=.125 that implies original M≈1.13 MB, above the 256 KiB text cap. Tiny originals with mandatory per-record certificate/hash evidence are technically incompatible with <15% in this measured format, including identity. Larger original size is insufficient when compression makes E small: good media compression can increase metadata share while reducing total R. Padding, deleting evidence or excluding small media would not resolve the original criterion. A changed criterion requires **explicit owner acceptance**; none is assumed.

### Historical 36: metadata by MIME and original size band

| Grouping | Value | n | p50 % | p95 % | Worst % |
| --- | --- | --- | --- | --- | --- |
| MIME | image/gif | 6 | 80.04682 | 97.43808 | 97.43808 |
| MIME | image/jpeg | 7 | 53.96554 | 95.12433 | 95.12433 |
| MIME | image/png | 7 | 92.95925 | 99.24580 | 99.24580 |
| MIME | image/webp | 7 | 70.67434 | 98.50303 | 98.50303 |
| MIME | text/plain | 9 | 98.98592 | 99.85557 | 99.85557 |
| Size | 1-16KiB | 15 | 92.62693 | 98.98592 | 98.98592 |
| Size | 1-2MiB | 2 | 1.38423 | 1.59983 | 1.59983 |
| Size | 16-256KiB | 7 | 43.92469 | 72.59794 | 72.59794 |
| Size | 256KiB-1MiB | 3 | 3.82755 | 12.56158 | 12.56158 |
| Size | <1KiB | 9 | 99.04495 | 99.85557 | 99.85557 |

### New 34: metadata by MIME and original size band

| Grouping | Value | n | p50 % | p95 % | Worst % |
| --- | --- | --- | --- | --- | --- |
| MIME | image/gif | 6 | 9.26784 | 99.81935 | 99.81935 |
| MIME | image/jpeg | 5 | 8.75968 | 98.15275 | 98.15275 |
| MIME | image/png | 5 | 8.69408 | 99.72327 | 99.72327 |
| MIME | image/webp | 6 | 13.69351 | 99.73530 | 99.73530 |
| MIME | text/plain | 12 | 84.76823 | 99.80752 | 99.80752 |
| Size | 1-16KiB | 7 | 78.51529 | 98.34064 | 98.34064 |
| Size | 1-2MiB | 4 | 1.17323 | 1.17630 | 1.17630 |
| Size | 16-256KiB | 12 | 33.59717 | 84.76823 | 84.76823 |
| Size | 256KiB-1MiB | 4 | 6.09847 | 43.83898 | 43.83898 |
| Size | <1KiB | 7 | 99.72327 | 99.81935 | 99.81935 |

Size bands use accepted original bytes, not encoded or record bytes: [0,1024), [1024,16384), [16384,262144), [262144,1048576), [1048576,2097153). Exact-cap 262,144-byte text belongs to the fourth band. These split the original large band for more visibility; no population membership changes. The source metric file also retains MIME×size bands. Both corpora remain synthetic; source-suite examples overlap and image noise/dashboard controls are not photographic or observed traffic samples. Coverage suffices for functional/MIME/size experiments, **not a representative deployment-wide acceptance claim**.

## 5. Three-year storage forecasts and measured SQLite boundary

Three years means **1,095 days**, normal month lengths with February fixed at 28 days, repeated 36 months; month 36 is 31 days. Counts are 109,500 / 1,095,000 / 10,950,000 media blocks. One GiB=2^30 B. No journal block traffic is substituted for these rates. Forecast means can yield fractional expected bytes; displayed GiB are rounded, source integer corpus totals are exact.

| Workload basis (measured except historical config) | n | M B/block | E B/block | Media member B/block | Other canonical B/block | R B/block |
| --- | --- | --- | --- | --- | --- | --- |
| frozen_v3_historical36 | 36 | 169,275.278 | 146,811.917 | 195,980.972 | 32,944.056 | 228,925.028 |
| task720_reference34 | 34 | 338,857.735 | 323,614.471 | 431,719.588 | 32,945.735 | 464,665.324 |
| task720_identity34 | 34 | 338,857.735 | 338,857.735 | 452,046.382 | 32,945.735 | 484,992.118 |
| small_le16KiB | 14 | 3,824.357 | 3,178.429 | 4,468.000 | 32,943.929 | 37,411.929 |
| medium_16_256KiB | 13 | 142,330.769 | 104,581.769 | 139,676.846 | 32,949.923 | 172,626.769 |
| large_gt1MiB | 4 | 2,093,691.500 | 2,093,691.500 | 2,791,829.500 | 32,943.000 | 2,824,772.500 |
| text_only | 12 | 51,604.583 | 11,790.750 | 15,951.417 | 32,960.583 | 48,912.000 |
| images_only | 22 | 495,541.273 | 493,700.136 | 658,502.227 | 32,937.636 | 691,439.864 |
| historical_projection_corrected | 36 | 169,275.000 | 146,812.000 | 195,982.000 | 15,190.000 | 211,172.000 |

Reference 34 MIME counts are 12 text/plain, 5 PNG, 5 JPEG, 6 WebP, 6 GIF; source subcategories are prose/JSON/code/entropy. It selects 17 Zstd/17 identity. Historical 36 MIME counts are 9 text, 7 JPEG, 7 PNG, 7 WebP, 6 GIF; 26 Zstd/10 identity. These are explicitly equal-corpus scenarios, **not a forecast traffic mix**. The identity sensitivity retains identical evidence and uses each measured identity descriptor/R. Near-2-MiB image rows are isolated-v3 format capacity examples and exceed current active image admission limits.

### Frozen-v3 historical 36, updated accounting: month-36 retained storage, GiB

| Blocks/day | Original M | Encoded E | Canonical media | Other canonical | Complete R | Primary DB |
| --- | --- | --- | --- | --- | --- | --- |
| 100 | 17.263 | 14.972 | 19.986 | 3.360 | 23.346 | 30.182 |
| 1000 | 172.627 | 149.719 | 199.861 | 33.596 | 233.457 | 292.822 |
| 10000 | 1,726.266 | 1,497.185 | 1,998.610 | 335.963 | 2,334.573 | 2,919.217 |

| Blocks/day | Index/pages allowance | Fragmentation | Operating reserve H | Snapshot S | Backups K | Recovery W | Total local P+H+S+W |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 100 | 2.335 | 3.502 | 12.234 | 30.182 | 114.692 | 30.182 | 102.781 |
| 1000 | 23.346 | 35.019 | 75.544 | 292.822 | 1,112.722 | 292.822 | 954.009 |
| 10000 | 233.457 | 350.186 | 708.637 | 2,919.217 | 11,093.023 | 2,919.217 | 9,466.287 |

### Task 7.20 reference 34: month-36 retained storage, GiB

| Blocks/day | Original M | Encoded E | Canonical media | Other canonical | Complete R | Primary DB |
| --- | --- | --- | --- | --- | --- | --- |
| 100 | 34.557 | 33.002 | 44.027 | 3.360 | 47.386 | 60.233 |
| 1000 | 345.567 | 330.021 | 440.267 | 33.598 | 473.865 | 593.331 |
| 10000 | 3,455.665 | 3,300.215 | 4,402.669 | 335.980 | 4,738.649 | 5,924.311 |

| Blocks/day | Index/pages allowance | Fragmentation | Operating reserve H | Snapshot S | Backups K | Recovery W | Total local P+H+S+W |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 100 | 4.739 | 7.108 | 19.478 | 60.233 | 228.886 | 60.233 | 200.177 |
| 1000 | 47.386 | 71.080 | 147.982 | 593.331 | 2,254.658 | 593.331 | 1,927.975 |
| 10000 | 473.865 | 710.797 | 1,433.015 | 5,924.311 | 22,512.381 | 5,924.311 | 19,205.948 |

### Original historical Task 7.8 projection — retained unchanged

| Blocks/day | Original GiB | Encoded GiB | Canonical GiB | Primary GiB | Backup GiB | Snapshot GiB | Old temporary GiB | Bootstrap GiB |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 100 | 17.263 | 14.972 | 21.535 | 27.919 | 106.093 | 27.919 | 11.689 | 25.842 |
| 1000 | 172.626 | 149.719 | 215.353 | 270.191 | 1026.726 | 270.191 | 70.089 | 258.423 |
| 10000 | 1726.263 | 1497.186 | 2153.528 | 2692.910 | 10233.059 | 2692.910 | 654.086 | 2584.234 |

Historical assumptions are 211,172 R B/block, 169,275 M and 146,812 E; canonical media including serialization is R−15,190=195,982 B/block. Its 15,190 historical metadata definition is not frozen-v3 N. SMALL assumes 16,384→15,319 encoded and 26,500 R; LARGE assumes 1,572,864→1,541,407 encoded and 2,070,000 R with 1.30× physical amplification. [historical_economics.json](../verification/task722/historical_economics.json) preserves all 27 old scenarios and three-year costs; the exact original full JSON/CSV replay passes. The old small-media metadata allowance is about 11 KiB rather than measured current 33 KiB: it is not credible as a current-format small-media forecast without rebasing.

### Direct physical measurement versus analytical scaling

| Historical measured layout / same-record control | Logical bytes | Post-checkpoint DB B | Post-VACUUM DB B | Observed WAL B |
| --- | --- | --- | --- | --- |
| 7.7 current v2 chain JSON | 20,896,854 | 29,659,136 | 21,229,568 | 21,156,232 |
| 7.7 projected v3 chain JSON | 7,621,402 | 10,551,296 | 7,929,856 | 10,728,512 |
| 7.11 frozen R in indexed BLOBs | 8,241,301 | 8,376,320 | 8,372,224 | 9,377,152 |
| 7.11 identical R in minimal JSON section | 8,241,338 | 11,132,928 | 8,261,632 | 11,433,032 |

The 7.11 measured empty schema is 49,152 B, consistent backup 8,376,320 B, logical index value widths 7,200 B. Indexed BLOBs are **110,592 B larger** after VACUUM than the same-R minimal JSON control. The 130,923-B BLOB excess over R combines schema/identifiers/indexes/allocation; it is not pure physical index bytes. dbstat attribution is unavailable. Prior WAL numbers remain historical observations and were **not replayed**. DELETE/EXTRA bridge and atomic restart tests execute now; no WAL initializer or legacy backup verifier is called.

For projections, **P=1 GiB base+C+0.10C index/page allowance+0.15C fragmentation**. The 0.10/0.15 split is an explicitly assumed decomposition of historical 1.25× amplification, not measured index/free-page attribution. **H=.20P+1.45×monthly canonical writes×1.25+5 GiB**, **S=P**, **W=P**, **K=4×.95P**. The 1.45 write reserve is a conservative analytical rollback/maintenance allowance inspired by historical peaks, not newly measured DELETE high-water use or a WAL activation. Recovery workspace is additional to primary and operating reserve, provisioned for the entire month. Full backups are conservatively priced at current P rather than a claim every retained older weekly copy already has that size. No large-scale SQLite linearity, snapshot dedup, incremental backup, alternate-branch distribution or filesystem peak measurement is claimed.

## 6. Complete modeled month-36 cloud-node bills

Every line below uses **historical illustrative USD assumptions dated 2026-10-18**, reviewed against official pages on 2026-10-28. Provider/service class: Hetzner-style budget cloud; AWS Lightsail-style mainstream cloud; an unspecified capacity-focused compute host plus B2-style object backup. **Region unspecified for every profile; none is a provider quotation.** The complete historical bundles and unit-normalized rates could not be substantiated as same-region current purchase quotes, so permitted local assumptions are retained instead of invented quotes.

| Profile | Compute / month | vCPU / GiB RAM | Included local GiB | Extra disk $/GiB-month | Backup $/GiB-month | Egress $/GiB |
| --- | --- | --- | --- | --- | --- | --- |
| budget_vps | $20.00 | 4 / 8 | 160 | 0.05 | 0.006 | 0.01 |
| mainstream_cloud | $40.00 | 4 / 8 | 160 | 0.1 | 0.05 | 0.09 |
| storage_focused | $45.00 | 4 / 8 | 500 | 0.02 | 0.006 | 0.01 |

Local capacity L=P+H+S+W; disk billed=`ceil(max(0,L/GiB−included))` at an **illustrative 1-GiB increment**. Included capacity is allocated to primary first, then snapshots, H and W; the following detailed ledger shows any remaining paid capacity and final rounding separately. Monthly total=compute+disk+retained-backup storage+peer/backup/bootstrap/restore egress. Ingress is assumed uncharged. There is no additional archive/storage-node service in this one-media-node model, so that line is zero by scope, not a claim that future journal archives are free.

### Original historical 7.8 mean, corrected capacity bill: month-36 cost / strictly below $100

| Blocks/day | Budget VPS | Mainstream cloud | Storage-focused |
| --- | --- | --- | --- |
| 100 | $21.87 / PASS* | $56.38 / PASS* | $46.87 / PASS* |
| 1000 | $74.15 / PASS* | $270.89 / MISS | $70.72 / PASS* |
| 10000 | $629.07 / MISS | $2,480.18 / MISS | $390.08 / MISS |

### Frozen historical v3 mean: month-36 cost / strictly below $100

| Blocks/day | Budget VPS | Mainstream cloud | Storage-focused |
| --- | --- | --- | --- |
| 100 | $22.02 / PASS* | $57.71 / PASS* | $47.02 / PASS* |
| 1000 | $79.37 / PASS* | $291.59 / MISS | $73.72 / PASS* |
| 10000 | $680.94 / MISS | $2,686.60 / MISS | $419.93 / MISS |

### Task 7.20 new reference mean: month-36 cost / strictly below $100

| Blocks/day | Budget VPS | Mainstream cloud | Storage-focused |
| --- | --- | --- | --- |
| 100 | $26.08 / PASS* | $79.47 / PASS* | $49.03 / PASS* |
| 1000 | $148.15 / MISS | $565.53 / MISS | $113.31 / MISS |
| 10000 | $1,369.23 / MISS | $5,426.92 / MISS | $816.05 / MISS |

**PASS* is conditional modeled affordability**, not production acceptance, a region/tier quote or universal inexpensive public-network evidence. The reference 34 scenario misses all providers at 1,000/day and 10,000/day. The smaller frozen historical-v3 workload at 1,000/day passes budget/storage assumptions and misses mainstream cloud. Both outcomes are preserved rather than choosing only a favorable case.

### Reference 34: detailed month-36 bills, USD

| Rate | Profile | Compute | Primary | Snapshots | H | W | Disk rounding | Backups | Peer egress | Backup uploads | Bootstrap | Restore | Total |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 100 | budget_vps | 20.00 | 0.00 | 0.00 | 0.00 | 2.01 | 0.04 | 1.37 | 0.15 | 2.41 | 0.05 | 0.05 | 26.08 |
| 100 | mainstream_cloud | 40.00 | 0.00 | 0.00 | 0.00 | 4.02 | 0.08 | 11.44 | 1.39 | 21.68 | 0.43 | 0.43 | 79.47 |
| 100 | storage_focused | 45.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 1.37 | 0.15 | 2.41 | 0.05 | 0.05 | 49.03 |
| 1000 | budget_vps | 20.00 | 21.67 | 29.67 | 7.40 | 29.67 | 0.00 | 13.53 | 1.55 | 23.73 | 0.47 | 0.47 | 148.15 |
| 1000 | mainstream_cloud | 40.00 | 43.33 | 59.33 | 14.80 | 59.33 | 0.00 | 112.73 | 13.91 | 213.60 | 4.26 | 4.23 | 565.53 |
| 1000 | storage_focused | 45.00 | 1.87 | 11.87 | 2.96 | 11.87 | 0.00 | 13.53 | 1.55 | 23.73 | 0.47 | 0.47 | 113.31 |
| 10000 | budget_vps | 20.00 | 288.22 | 296.22 | 71.65 | 296.22 | 0.00 | 135.07 | 15.45 | 236.97 | 4.74 | 4.69 | 1,369.23 |
| 10000 | mainstream_cloud | 40.00 | 576.43 | 592.43 | 143.30 | 592.43 | 0.01 | 1,125.62 | 139.09 | 2,132.75 | 42.65 | 42.21 | 5,426.92 |
| 10000 | storage_focused | 45.00 | 108.49 | 118.49 | 28.66 | 118.49 | 0.00 | 135.07 | 15.45 | 236.97 | 4.74 | 4.69 | 816.05 |

Indexes/metadata are charged inside P, not again as a duplicate fee. Canonical metadata is already inside C. Snapshot/operating/recovery capacity is explicitly charged even when the provider offers no built-in snapshot facility for attached storage. Four full backup uploads per month are charged independently from four retained copies. Expected bootstrap serving and remote backup restore each occur once per year, accrued monthly; neither is silently free. Model means assume a 4-vCPU/8-GiB class with provisional ≈4.06-GiB RAM reserve and existing 0.45-second worker cost; full production validation, burst, sync and restore throughput remain unqualified.

### Three-year cumulative expenditure — distinct from the monthly target

| Workload | Rate | Budget cumulative USD | Cloud cumulative USD | Storage cumulative USD |
| --- | --- | --- | --- | --- |
| frozen_v3_historical36 | 100 | $759.69 | $1,788.49 | $1,659.69 |
| frozen_v3_historical36 | 1000 | $1,723.33 | $5,998.44 | $2,080.27 |
| frozen_v3_historical36 | 10000 | $13,027.80 | $51,434.20 | $8,546.05 |
| task720_reference34 | 100 | $807.11 | $2,144.51 | $1,698.21 |
| task720_reference34 | 1000 | $3,007.90 | $11,179.40 | $2,782.40 |
| task720_reference34 | 10000 | $25,979.87 | $103,456.53 | $16,035.77 |

Each cumulative result sums 36 modeled monthly bills against a growing chain, without discounts/inflation/tax. It is not compared to a $100 cumulative budget. The exact historical representative **unloaded** examples remain $21.82/$55.99/$46.82 at 100/day; $43.18/$205.95/$62.67 at 1,000/day; $322.78/$1,837.60/$265.00 at 10,000/day, in budget/cloud/storage order. They omitted priced snapshot/workspace capacity and expected bootstrap/restore service, so are not fully loaded totals.

### Capacity discontinuities, service limits and price uncertainty

The illustrative cost jumps when L exceeds bundled 160 or 500 GiB and at each extra 1-GiB increment; the source scenarios record month-of-crossing for 160/500/1,000/10,000/16,000 GiB. Actual provider minimums, disk attachment limits, topology, bandwidth/IOPS and compute upgrades can cause larger jumps. [Hetzner volume documentation](https://docs.hetzner.com/cloud/volumes/overview/) specifies 10-GB minimum/1-GB increments, up to 16 volumes and 10-TB total; its server snapshots exclude attached volumes. New reference 10,000/day needs ≈19,206 GiB of local capacity, exceeding that volume pool even after the nominal bundle. Its budget-profile arithmetic is **not a feasible single-server quotation**; another storage arrangement would need a separate price.

[Lightsail pricing](https://aws.amazon.com/lightsail/pricing/) lists SSD block storage from 8 GB at $0.10/allocated GB-month, snapshots $0.05/GB-month and regional transfer terms. Those are decimal-GB provider terms, not proof of the entire retained USD/GiB bundle. The local-copy snapshot model deliberately uses block-capacity rates, not an unverified native snapshot discount. [B2 pricing](https://www.backblaze.com/cloud-storage/pricing) currently starts at $6.95/TB-month with transfer terms; it is not a complete compute-host quote or the historical $0.006/GiB assumption. Exact host regions, storage-focused expansion/tier caps, IOPS, taxes, actual transfer allowances and restore-time requirements remain unquoted. [pricing_review.json](../verification/task722/pricing_review.json) records source observations and the inaccessible AWS FAQ attempt.

“Fully loaded” means all specified **modeled media-only capacity/expected-transfer lines** are billed, not a fully quoted operating invoice. Additional operational cost and infeasible tier upgrades are unknown, not invented zero-cost quotations. Therefore the $100 claims remain conditional even for modeled passes.

## 7. Bandwidth, retention and sensitivity

Reference policy: daily refresh/one retained **local full-copy** snapshot; four full consistent backup uploads/month, four retained at assumed .95× P (roughly one-month retention); no incremental/dedup credit. H and a separate P-sized recovery copy remain available concurrently. Backups remain remote additional capacity. A failed/corrupt canonical record cannot be reconstructed from an index or cache.

Ordinary media ingress=monthly R×1.15×1.20, peer outbound=monthly R×8×1.20×1.20. The extra .20 is .10 protocol + .10 retransmission. One full bootstrap=all R×1.20; expected serving is one/year; one remote backup recovery/year transfers .95P at the same illustrative egress rate. Ingress bytes are tracked, with zero ingress price assumed. These are media-chain traffic estimates, not packet captures or complete new BFT/journal traffic.

| Rate | Peer ingress/month GiB | Peer egress/month GiB | Backup upload/month GiB | One bootstrap GiB | Expected bootstrap/month GiB | Expected restore/month GiB | All priced egress/month GiB |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 100 | 1.851 | 15.454 | 240.932 | 56.864 | 4.739 | 4.768 | 265.894 |
| 1000 | 18.513 | 154.545 | 2,373.324 | 568.638 | 47.386 | 46.972 | 2,622.228 |
| 10000 | 185.132 | 1,545.449 | 23,697.243 | 5,686.378 | 473.865 | 469.008 | 26,185.565 |

All three rates/profiles have 19 one-at-a-time sensitivities: measured small/medium/large subsets, text/image MIME mixes, all-identity choices, +64-KiB evidence, illustrative +1,194-B external proof, 2/4/12 backups, weekly/daily snapshot refresh and 1/7 retained copies, bootstrap/restore incidence, 8/16 peers, half-rate capacity versus double-rate SSD storage and higher page/fragmentation overhead. No production distribution is invented. The proof sensitivity is a frozen example size, not a presumed per-block consensus requirement. Snapshot refresh at unchanged full-copy retention has identical modeled capacity cost; increased write/CPU work is not measured, so this is not proof frequency is operationally free.

Best case uses the measured ≤16-KiB subset (mean original 3,824 B), two full backups/one upload per month, one weekly-refreshed local snapshot, no expected bootstrap/restore events and half marginal disk rate. Reference is equal new 34 with default policy. Stress uses four measured >1-MiB identity images (mean original 2,093,692 B), +64-KiB analytical evidence, 12 backups at .98×, seven daily snapshots, 16 peers, monthly bootstrap serving, 1.50× DB allocation and double marginal disk rate. These are conditional scenario bounds, not probability intervals, new valid record fixtures or assertions every stress record can fit frozen component caps.

| Case | Rate | Budget USD/month | Cloud USD/month | Storage USD/month |
| --- | --- | --- | --- | --- |
| best | 100 | $20.14 | $41.18 | $45.14 |
| best | 1000 | $21.24 | $50.28 | $46.17 |
| best | 10000 | $66.32 | $209.31 | $67.01 |
| reference | 100 | $26.08 | $79.47 | $49.03 |
| reference | 1000 | $148.15 | $565.53 | $113.31 |
| reference | 10000 | $1,369.23 | $5,426.92 | $816.05 |
| stress | 100 | $468.81 | $1,300.48 | $243.81 |
| stress | 1000 | $4,638.34 | $12,898.61 | $2,207.02 |
| stress | 10000 | $46,333.27 | $128,879.29 | $21,838.93 |

The default cost geometry remains useful for scenario arithmetic, but its historical small 11-KiB metadata assumption understates frozen evidence; use measured ≈33-KiB overhead instead. Large identity images make canonical bytes ≈4/3 original plus evidence and are not rescued by 60–80% codec assumptions. Mixed traffic costs depend strongly on genuine size/MIME weights, retention and service limits. The 34-object mean more than doubles historical projected bytes/block; strong text savings do not offset a large-image distribution by assumption. Tier feasibility, sync/load/restore throughput and production traffic remain unproven.

## 8. Integration, security and platform status

Tracked 7.21 counts and a fresh unchanged-bridge replay agree: **70 format round trips (43 Zstd/27 identity), 58 current-policy admissible candidates (40/18), 128 persisted and fresh-process recovered records**. Twelve format objects exceed the current image cap and are not falsely counted as active-admission candidates. Exact accepted bytes, SHA-256, MIME, sizes and choices match Task 7.20 frozen rows. Independent received-byte validation/retrieval never recompresses. The actual upload service is exercised; HTTP/validator endpoints are not activated.

| Boundary | Status | Evidence / meaning |
| --- | --- | --- |
| Isolated codec/format validity | PASS | 70 selected format records exact; strict workers and frozen parser. |
| Disabled application interface integration | PASS | 58 admissible constructors, 128 persistent/recovered records, real upload-service/cache-deletion tests. |
| Active production v3 compression | BLOCKED | No production registration/import/version transition; current path supports raw versions 1/2. |
| Approved network protocol version/activation | BLOCKED | Frozen isolated v3 is not an approved network transition. |
| Complete BFT/reviewer-history authority | NOT VERIFIED | Trusted explicit test snapshots do not establish full historical consensus authority. |
| Independent native decoder security review | NOT VERIFIED | Functional adversarial tests and process containment are not independent native review. |
| Linux/platform qualification | NOT VERIFIED | 193 tests skipped on Windows; historical paired evidence is not a fresh platform qualification. |
| Historical WAL measurement replay | NOT VERIFIED | Not run; historical initializer enables WAL; safety gate retained. |
| Review-journal implementation/economics | NOT VERIFIED | Outside original scope and not authorized; combined affordability unproven. |

The bridge returns `integration_status=INCOMPLETE`, `consensus_authorized=False`; selected chain/finality tables remain empty. It uses explicit public fixture certificates and trusted snapshots rather than treating self-declared certificates as historical authority. Active producer/validator/storage/retrieval support raw v1/v2; no approved compressed-media network path is established. Original wording requires storing metadata/applying adaptive compression but does not explicitly mandate a public launch. Accepting the disabled implemented milestone boundary is therefore an **owner interpretation**, not assumed permission to call active acceptance complete. Production remains blocked independently; complete future BFT implementation is not a prerequisite for demonstrating a benchmark or media-only storage simulator.

## 9. Reproduction, independent arithmetic and honest exclusions

Reference Windows 11 build 26200 / AMD64, Python 3.13.5, SQLite 3.49.1, Pillow 12.3.0 (JPEG 8.0/WebP 1.6.0), zstandard 0.25.0/libzstd 1.5.7, Brotli 1.2.0, zlib 1.3.1, cffi 2.0.0, eth-account 0.13.7, cryptography 49.0.0, pytest 8.4.1. No installation/upgrade. Both frozen source manifests regenerate exactly: historical 36 source objects/6,093,917 B and new 34/11,521,163 B. Fresh 7.20 manifest/metrics/admission/historical audit hashes match exactly; all codec/record non-timing data match exactly. Timings and worker resource observations are host observations with no performance pass threshold, not forced-equal bytes.

Historical 252 codec rows have zero non-timing differences; projected composition replays exactly excluding environment and explicitly omitted SQLite; historical economics JSON/CSV are exact. New 238 codec trials, 70 primary and eight sensitivity ledgers reproduce. Independent arithmetic checks all 78 ledgers/base64/nearest-rank values without measurement imports. A separate Decimal checker imports no simulator and recomputes **225 scenarios ×36 monthly bills**, capacity ceilings, cumulative totals, additive partitions and $100 decisions from inputs; tolerances are 1e−7 USD/month, 1e−6 cumulative USD, .1 modeled byte for floating-point forecasts. Exact source/hash/integer ledger comparisons have zero tolerance. [independent_economic_checks.json](../verification/task722/independent_economic_checks.json) records actual maxima.

| Bounded test group | Passed | Failed | Skipped | Deselected |
| --- | --- | --- | --- | --- |
| measurements | 43 | 0 | 0 | 0 |
| bridge | 43 | 0 | 0 | 0 |
| canonical | 324 | 0 | 0 | 0 |
| codecs | 476 | 0 | 193 | 0 |
| atomic | 45 | 0 | 4 | 0 |
| active | 99 | 0 | 0 | 2 |
| Total disjoint final | 1030 | 0 | 197 | 2 |

The 43 measurement cases include both repaired historical tests, the twelve fail-closed wrapper guards and nine acceptance cases; they are not repaired again. Exact IDs/outcomes are in per-group files. **193 Linux-only skips** require an actual Linux kernel. **Four WAL crash skips** retain the SQLite runtime gate before any WAL setup. The atomic refusal-control test passes and does not enable WAL. DELETE/EXTRA crash stages before claims/after claims/after block/after commit and retry execute; 43 bridge and 45 atomic tests pass.

The two active deselections are the known Windows TestClient/socket initialization case `tests/test_milestone_6_task_6_9_media_integrity.py::test_media_api_is_derived_and_returns_exact_binary_bytes` and `tests/test_milestone_7_task_7_17e_finality_durability.py::test_settings_connection_ownership_and_nested_begin`, whose empty-DB control enables WAL. Neither is a pass. Full repository/API/load/Linux/security-review suites and historical WAL storage runners were not run; no new timeout occurred in the final bounded commands. One initial audit-runner attempt stopped after two successful commands because an unused import named a nonexistent script constant; it was removed from this new runner and the full replay reran. [initial_replay_attempt.json](../verification/task722/initial_replay_attempt.json) retains its completed command outcomes; this harness failure earns no acceptance credit. No preexisting source/assertion was changed to make tests pass.

From the repository root with the existing venv:

```powershell
.\.venv\Scripts\python.exe -B verification/task722/run.py replay
.\.venv\Scripts\python.exe -B verification/task722/run.py tests
.\.venv\Scripts\python.exe -B verification/task722/reconcile.py
.\.venv\Scripts\python.exe -B verification/task722/economics.py
.\.venv\Scripts\python.exe -B verification/task722/report.py
.\.venv\Scripts\python.exe -B verification/task722/crosscheck.py
```

Exact argv, temp paths, per-command 600-second bounds, elapsed times/exits and 30-line log tails are in the two execution JSON files. Bulk replays remain ignored scratch data; compact new evidence references original tracked raw rows, preserving them. [checksums.sha256](../verification/task722/checksums.sha256), [source_checksums.json](../verification/task722/source_checksums.json) and the full preflight inventory cover sources, corpus manifests and deliverables. Cross-platform/native encoder portability, independent native security review and million-record physical/index extrapolation remain explicitly unverified.

## 10. Review-journal scope separation

The independent BFT review journal is outside original Milestone 7. Original media-only costs did not include it, failed-review originals, signer/round logs or independent source archives. Existing proposal models show its archive/bandwidth can be substantial; combined media chain plus journal below-$100/month viability is **unproven**. Embedded media certificate evidence remains fully counted here; a future journal is not assumed to remove it. No journal activation, implementation, new consensus work or source-retention policy is authorized or begun. It is not a new prerequisite for original storage-simulator acceptance.

## 11. Strict original acceptance matrix

| Original item | Requirement | Status | Evidence / exact boundary |
| --- | --- | --- | --- |
| MODEL A | Complete originals recoverable from canonical on-chain representation | PASS | bridge_recovery.json: 128 fresh-process exact originals; no cache or recompression; integration_checks.json |
| 1 | Benchmark Zstd, Brotli and suitable lossless alternatives across text/metadata/code/media | PARTIAL | 252 historical + 238 new exact codec trials; replay comparisons PASS. All five supported MIME types; synthetic-only corpus cannot establish real deployment representativeness. |
| 2 | Retain algorithm, original/stored sizes, MIME and original-byte hash | PARTIAL | canonical_v3/media.py eight-field descriptor; 70 format + 58 application records persist/recover. Active application remains v1/v2. |
| 3 | Guarantee byte-exact original reconstruction | PARTIAL | All selected measured records exact SHA-256, strict decoder/bridge tests pass; no active compressed-media path or universal native-security proof. |
| 4 | Three years at 100/1000/10000 blocks/day | PASS | historical_replay_comparison.json: exact 7.8 JSON/CSV; economic_scenarios.json: 27 corrected cases, 1095 days. |
| 5 | Measure primary DB, media, indexes, snapshots/backups and bandwidth | PARTIAL | Historical 7.7/7.11 physical DB/backup measurements preserved; exact media ledger. Separate physical index pages, actual snapshot footprint and production traffic remain unmeasured; forecasts identify analytical allowances. |
| 6 | Apply adaptive compression by MIME/content type | PARTIAL | media.produce MIME allowlist/size caps and descriptor comparison; 43 Zstd/27 identity format cases; bridge not production active. |
| 7 | Realistic expectations for JPEG/WebP/video/already-compressed data | PASS | New raw Zstd-3 image reductions 0.088% JPEG, 0.006% PNG, -0.006% WebP; expansions/fallback retained; unsupported video receives no invented ratio. |
| 8 | Report representative p50/p95/worst metadata overhead | PARTIAL | metadata_reconciliation.json reproduces exact primary percentiles; all MIME/size strata included. Deployment-wide distribution not established. |
| 9 | Account for backup/snapshot/network-transfer costs | PASS | cost_formulas.json and all 27 corrected cases charge backups, snapshots, headroom, recovery, expected bootstrap/restore and peer egress. Prices/tier feasibility remain conditional. |
| A | Roughly 60–80% reduction on realistic compressible content where feasible | PARTIAL | New source suite 65.09446%; code weighted 62.88359%, median 54.79520%; prose/JSON weighted 87.55131/81.35711%. Examples demonstrate feasibility, not a representative deployment-wide claim. |
| B | Normal adaptive producer never selects an increased relevant stored representation | PARTIAL | PASS versus identity for complete descriptor/media member/fixed-context R; all 78 measured rows. Raw E<=M is FAIL: natural 104->105 counterexample. Physical allocation savings not guaranteed; active producer absent. |
| C | Measure metadata and attain below 15% per-record representative target | FAIL | New n=34: p50 54.70902%, p95 99.80752%, worst 99.81935%; 12/34 individually below target. Byte-weighted 7.14017% is not a pass. |
| D | Explicitly support or transparently miss below $100/month at year three | PASS | Reference 34: all profiles pass conditionally at 100/day; all miss at 1000/10000. Frozen historical-v3 corpus at 1000/day passes budget/storage, misses cloud. No quoted universal price claim. |
| E | Every selected compressed media reconstructs exactly with original hash | PARTIAL | 70 format + 58 admissible + 128 fresh recoveries PASS, selected codec/native comparisons exact. Activation/security qualification separate; no vacuous production pass. |
| F | Reproducible corpus, commands, environment, raw data and reports | PASS | 36/34 source identities exact; 252/238 codec results exact except observational timing; 78 canonical ledgers exact; historical economics exact JSON/CSV; focused tests below. Historical WAL replay intentionally unverified. |

Machine-readable [acceptance_matrix.json](../verification/task722/acceptance_matrix.json) separates demonstrated requirements, isolated demonstrations, measured misses, platform/security assumptions, unapproved activation and out-of-scope journal work. PARTIAL does not turn a measured FAIL into a pass. PASS for a bounded model is not production readiness. No additional review-journal/BFT requirement is imposed on a benchmark tool.

## 12. Minimum remaining original acceptance work

These are the remaining acceptance decisions/measurements, **not authorization to begin another task or general blockchain roadmap**. Independent native-decoder security review, actual Linux/platform qualification and approved network activation remain separate production gates; they are not silently added as new benchmark acceptance criteria. If owner interpretation requires active accepted-media use, the applicable decoder safety/authority/version prerequisites must be satisfied before that use.

**R1: C (mandatory FAIL).** Type: owner decision / implementation if redesign selected. Smallest resolution: Explicit owner-approved metadata exception or revised acceptance policy; otherwise separately authorize a format design that preserves all signed evidence and media semantics and remeasure. Current frozen format cannot meet <15% for tiny media. No waiver is granted here. Consensus-format change: No for explicit criterion exception; yes for canonical encoding changes. Can proceed without BFT/journal implementation: **yes**, under a separately authorized scope. Owner waiver/policy: Required if retaining current format and claiming completion despite failed target.

**R2: 1 / 8 / A: representative-content evidence.** Type: measurement. Smallest resolution: One bounded separately versioned provenance-cleared sample of real media, substantive independent code and human/structured text; publish actual population/size/MIME statistics. Keep tiny valid media and existing results. No invented traffic weights. Consensus-format change: No Can proceed without BFT/journal implementation: **yes**, under a separately authorized scope. Owner waiver/policy: Only if owner accepts limited synthetic coverage instead of the required representativeness; not an automatic exception.

**R3: 2 / 3 / 6 / B / E: disabled versus application acceptance.** Type: owner decision / implementation. Smallest resolution: Owner explicitly decides whether the original milestone accepts the demonstrated disabled service boundary. If active accepted-media behavior is required, separately authorize the smallest reviewed versioned application producer/validator/store/retrieval integration; audit cannot activate it. Consensus-format change: Disabled acceptance decision: no. Active support requires an approved version boundary; do not alter frozen v3 merely to force acceptance. Can proceed without BFT/journal implementation: **yes**, under a separately authorized scope. Owner waiver/policy: Explicit scope interpretation required to accept disabled implementation; active network policy approval required before activation.

**R4: 5: physical index/snapshot/backup/network measurement coverage.** Type: measurement / economic accounting. Smallest resolution: Bounded DELETE/EXTRA storage/index allocation and consistent snapshot/backup/recovery measurement on a supported instrumentation build, plus measured media-only transfer workload. Replace analytical splits with evidence where required; retain historical WAL data unchanged. Consensus-format change: No Can proceed without BFT/journal implementation: **yes**, under a separately authorized scope. Owner waiver/policy: Only if owner accepts the clearly disclosed analytical attribution/transfer coverage instead of a strict measurement requirement.

**R5: B only if owner requires raw payload or raw-original storage comparison.** Type: owner decision / implementation. Smallest resolution: Record accounting baseline explicitly. Canonical descriptor/R versus identity already passes in isolation. Raw-payload interpretation fails 104->105; adding E<=M would be a separately authorized local-producer change. A demand for serialized R<=raw M is incompatible with tiny originals and mandatory evidence. Consensus-format change: No for a stronger local producer preference; yes if changing canonical representation/consensus rules. Can proceed without BFT/journal implementation: **yes**, under a separately authorized scope. Owner waiver/policy: Accounting interpretation must be explicit; a measured failing mandatory interpretation needs resolution or explicit exception.

A purchase-ready universal $100 offer is not an unmet criterion D because D expressly permits a transparently reported miss. Capacity-priced scenario accounting is now complete for stated media-only assumptions; actual provider regions/tier quotes and operational measurements remain limitations, not invented guaranteed savings. Historical WAL qualification and full BFT/journal work are not new mandatory closeout tasks.

## 13. Final independent verdicts and review handoff

**VERDICT 1 — ORIGINAL MILESTONE ACCEPTANCE: INCOMPLETE.** Mandatory C is a measured FAIL and no owner-approved exception exists. Representativeness, measurement coverage and disabled-versus-active acceptance interpretation remain partial. COMPLETE WITH DOCUMENTED LIMITATIONS is impermissible while the mandatory target fails without an explicit exception.

**VERDICT 2 — PRODUCTION/NETWORK ACTIVATION READINESS: BLOCKED.** Active compressed-media integration, an approved version transition, complete production authority, independent decoder review and platform qualification are not established. No activation or implementation follows from this audit.

Task 7.22 is **ready for review and owner-performed commit** of this report and `verification/task722/` only. All preexisting tracked bytes and the Git index remain unchanged. Do not formally close Milestone 7, begin Task 7.23/Milestone 8, or call C satisfied on the basis of this completed audit.
