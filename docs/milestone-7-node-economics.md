# Milestone 7 Task 7.8 — Reproducible Three-Year Full-Node Storage and Economics Simulator

Status: modeling, measurement interpretation, and reporting complete. This task does not change compression, consensus, schema, chain state, decoder behavior, or deployment. Figures are planning estimates, not a production capacity commitment.

## Executive findings

This model is for an independently operated **full archival node**. It retains every accepted canonical media representation and the data needed to validate the chain. It does not substitute a light verifier, remote object store, pruning, or another node for that obligation.

Under the recommended weekly-full-backup policy, the $100/month target is supportable only for some volume/workload/provider combinations. At 1,000 representative-corpus blocks/day, the modeled month-36 cost is $43.18 on the budget VPS assumption, $205.95 on the mainstream-cloud assumption, and $62.67 on the storage-focused assumption. At 10,000 representative blocks/day it fails on all three. Large image-heavy traffic fails at 1,000/day on all three profiles.

These conclusions are driven chiefly by retained backup copies, then primary storage and egress; compute is not the modeled bottleneck at steady state. Security readiness remains separately blocked by the Task 7.5/7.6 decoder-security and isolation sign-offs.

## Scope, sources, and conventions

The simulator uses a 365-day/year convention with normal Gregorian month lengths (31/28/…/31), repeated for 36 months: 1,095 days total. Dollars are USD. One GiB is 1,073,741,824 bytes. Results contain no wall-clock timestamp, so identical inputs produce byte-identical JSON/CSV.

Task 7.7 is the measured source for the representative workload: 36 deterministic, repository-authored image-oriented fixtures, 7,602,184 projected adaptive-v3 canonical bytes total (211,172 bytes/block), 6,093,917 original bytes, 5,285,234 encoded bytes, and 7.19% byte-weighted metadata. It measured 7.62 MB logical projected-v3 JSON, 7.93 MB post-VACUUM SQLite, 10.55 MB after checkpoint, and 10.73 MB transient WAL. It does **not** establish million-block linearity or a future v3 layout.

Provider inputs are versioned in the configuration and were retrieved on 2026-10-18. The budget VPS assumption is informed by [Hetzner's price-adjustment table](https://docs.hetzner.com/general/infrastructure-and-availability/price-adjustment/); the mainstream profile is informed by [Amazon Lightsail pricing](https://aws.amazon.com/lightsail/pricing/); object-backup economics are informed by [Backblaze B2 pricing](https://www.backblaze.com/cloud-storage). Currency normalization, bundle selection, storage, and egress values are explicitly **illustrative assumptions**, not quotes; obtain region-specific quotes before purchase. Simulation has no network dependency.

## Workloads

| Workload | Mix / provenance | Original → encoded | Canonical block | Metadata | Physical DB amplification |
| --- | --- | ---: | ---: | ---: | ---: |
| SMALL-MEDIA | Assumed 70% compact raster/text, 30% small JPEG/WebP | 16,384 → 15,319 B | 26,500 B | 11,181 B | 1.25× |
| REPRESENTATIVE CORPUS | Equal-weight Task 7.7 fixtures; empirical sample, **not** forecast mix | 169,275 → 146,812 B | 211,172 B | 15,190 B | 1.25× |
| LARGE-MEDIA | Assumed 80% 1.2–2 MiB images / 20% 512 KiB; image-heavy, little further compression | 1,572,864 → 1,541,407 B | 2,070,000 B | 14,800 B | 1.30× |

Adaptive compression is represented in encoded sizes. No synthetic distribution is silently substituted for a real traffic forecast: only the middle row has a measured corpus basis, and its equal sample weighting is called out.

## Storage, backups, networking, and compute method

`canonical = blocks × canonical_bytes_per_block`. Primary physical data is `1 GiB base + canonical × physical amplification`. The 1.25× representative amplification is conservative against the observed 1.04× VACUUM ratio and reflects uncertainty in future indexes/JSON/base64/duplicate representations. Temporary capacity is `20% primary + 1.45× monthly writes + 5 GiB`; quarterly VACUUM additionally needs a second primary-sized working copy. The 1.45× WAL factor is a cautious interpretation of Task 7.7's checkpoint/WAL observations, not a claim of linear WAL behavior.

The output distinguishes retained primary data, retained backup data, snapshot bytes, and temporary headroom. It models daily checkpointing; WAL is temporary, while checkpoint and VACUUM are maintenance operations. Exact table/index attribution was unavailable in Task 7.7 (`dbstat` absent); a future BLOB-row v3 layout is not observed.

| Policy | Full backups / month; retention | Compression | Local snapshots | Limitation |
| --- | --- | ---: | ---: | --- |
| Minimal | 1; 2 full copies | 0.95× | 1 | RPO up to a month |
| Recommended | 4; 4 full copies | 0.95× | 1 | Weekly RPO; primary assessment default |
| Conservative | 4; 12 full copies | 0.98× | 2 | Higher retention cost |

All are SQLite-consistent **full** backups. Incremental support was not evidenced, so no incremental savings are assumed. Backup transfer is separate from retained bytes; restore needs retained backup plus a new primary copy and cannot repair a corrupted accepted canonical record.

Incoming propagation is canonical bytes × 1.15; outbound is canonical bytes × peer count (default 8) × 1.20. Both receive another 20% for protocol messages and retransmissions. Initial sync is one-time cumulative canonical data × 1.20. These are configurable estimates, not network measurements.

The small Ubuntu-server deployment class is 4 vCPU/8 GiB. The model reserves 1 GiB node process, 1 GiB database cache, 1 GiB OS/monitoring, two 128 MiB decoder workers, and 25% safety margin: 4.06 GiB. It uses a provisional 0.45-second Task 7.6C/7.6D adversarial p95 worker time per block; at 10,000/day this is 4,500 CPU seconds/day (5.21% of one vCPU). Thus steady-state compute is *plausible with burst limits*, but not throughput-validated: startup, storage contention, complete validation, peer ingress bursts, and end-to-end throughput still need measurement.

## Month-36 results and acceptance

Each cell is `month-36 cost / PASS|FAIL`; costs include compute, primary storage, recommended retained full backups, and egress. All values below are illustrative-model results.

| Blocks/day + workload | Budget VPS | Mainstream cloud | Storage-focused |
| --- | ---: | ---: | ---: |
| 100 SMALL | $20.28 PASS | $42.49 PASS | $45.28 PASS |
| 100 REPRESENTATIVE | $21.82 PASS | $55.99 PASS | $46.82 PASS |
| 100 LARGE | $43.76 PASS | $209.22 FAIL | $62.99 PASS |
| 1,000 SMALL | $22.27 PASS | $59.92 PASS | $47.27 PASS |
| 1,000 REPRESENTATIVE | $43.18 PASS | $205.95 FAIL | $62.67 PASS |
| 1,000 LARGE | $328.55 FAIL | $1,870.39 FAIL | $269.19 FAIL |
| 10,000 SMALL | $51.10 PASS | $252.16 FAIL | $67.16 PASS |
| 10,000 REPRESENTATIVE | $322.78 FAIL | $1,837.60 FAIL | $265.00 FAIL |
| 10,000 LARGE | $3,176.50 FAIL | $18,482.07 FAIL | $2,376.19 FAIL |

No scenario is marked PASS when backups or egress are excluded. This is an affordability result only, not a production-security approval.

Representative examples (recommended policy, month 36):

| Volume | Canonical / primary / retained backup after 3 years | Month-36 outbound | One-time initial sync | Month-36 cost (budget / mainstream / storage) | 3-year cumulative cost (same order) |
| ---: | ---: | ---: | ---: | ---: |
| 100/day | 21.54 / 27.92 / 106.09 GiB | 7.02 GiB | 25.85 GiB | $21.82 / $55.99 / $46.82 | $755.97 / $1,755.64 / $1,655.97 |
| 1,000/day | 215.35 / 270.19 / 1,026.73 GiB | 70.23 GiB | 258.45 GiB | $43.18 / $205.95 / $62.67 | $1,102.64 / $4,504.76 / $1,959.38 |
| 10,000/day | 2,153.53 / 2,692.91 / 10,233.06 GiB | 702.35 GiB | 2,584.24 GiB | $322.78 / $1,837.60 / $265.00 | $6,298.56 / $35,454.53 / $5,657.54 |

For comparison, LARGE at 10,000/day reaches 21,109.82 GiB canonical, 27,443.77 GiB primary, 104,286.33 GiB retained backup, 6,884.69 GiB month-36 outbound, and $3,176.50 / $18,482.07 / $2,376.19 per month.

## Sensitivity and thresholds

The machine-readable sensitivity grid varies representative 1,000/day traffic across encoded sizes 0.75×/1×/1.25×, DB amplification 1×/1.25×/1.5×, 4/8/16 peers, and all three backup policies. Storage/backup amplification and encoded size dominate retained costs; peer count and egress pricing dominate traffic-sensitive providers. Conservative retention is materially more expensive because it holds twelve complete copies; it is not confused with temporary backup work space.

For the representative 1,000/day budget-VPS baseline, 100 GiB primary is crossed in month 14; 500 GiB is not crossed in 36 months. The simulator emits crossings for 100, 500, 1,000, and 10,000 GiB for every scenario.

Maximum supportable average canonical block bytes at exactly $100/month (recommended policy; all mandatory modeled costs) are:

| Rate | Budget VPS | Mainstream cloud | Storage-focused |
| ---: | ---: | ---: | ---: |
| 100/day | 5,973,946 B | 813,219 B | 5,962,541 B |
| 1,000/day | 597,394 B | 81,321 B | 596,254 B |
| 10,000/day | 59,739 B | 8,132 B | 59,625 B |

Storage-focused hosting materially improves affordability for medium and high retained-byte loads, but does not change the large-media-at-1,000/day or representative-at-10,000/day conclusion. It also does not eliminate archival responsibility, backup transfer, or security work.

## Reproduce

```powershell
.\.venv\Scripts\python.exe scripts\milestone_7_task_7_8_node_economics.py
.\.venv\Scripts\python.exe -m pytest tests\test_milestone_7_task_7_8_node_economics.py -q --tb=short
```

The versioned input is [the configuration](../benchmarks/milestone_7_task_7_8_config.json). Outputs are [JSON](../benchmarks/milestone_7_task_7_8_results.json) and [monthly CSV](../benchmarks/milestone_7_task_7_8_monthly.csv). A one-scenario override is supported, for example:

```powershell
.\.venv\Scripts\python.exe scripts\milestone_7_task_7_8_node_economics.py --blocks-per-day 1000 --workload representative_corpus --profile budget_vps --peer-count 16 --encoded-factor 1.25 --physical-factor 1.5
```

The test suite covers block arithmetic, monthly accumulation, physical storage, full-backup calculations, network traffic, cost aggregation, $100 threshold behavior, sensitivity, malformed selectors, and deterministic repeatability.

## Remaining limitations and recommendations

Missing measurements: finalized chain-record distributions, real accepted upload MIME/size mix, future-v3 schema/index growth at scale, filesystem/snapshot behavior, actual peer retransmission/egress, end-to-end decoding/validation under bursts, and regional provider quotes. The provisional worker timings are not a capacity certification.

Before treating the target as release-ready, collect production-shaped observations, measure a bounded future storage layout at scale, define an evidence-backed backup/restore procedure, and run peer-sync plus burst-validation benchmarks. Potential future optimization work includes a non-duplicative canonical BLOB-row layout, measured incremental/logical backup support, bounded evidence representation, and lower-overhead transport—none is implemented or proposed as a consensus change here.

Task 7.8 is ready for review and commit as a modeling/reporting deliverable, subject to those explicit measurement and security limitations.
