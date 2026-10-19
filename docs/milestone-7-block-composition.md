# Milestone 7 Task 7.7 — Canonical Block-Size Composition and Physical Storage Measurement

Status: measurement and instrumentation complete; no consensus, block-format, database-schema, compression-integration, chain-reset, or deployment change is included. This report is ready for review, subject to the unresolved protocol bounds listed below.

## Scope and boundaries

There are three deliberately separate measurement populations:

| Representation | Status | How measured |
| --- | --- | --- |
| Current v1/v2 canonical blocks | Direct application measurement | `Block.consensus_payload_v1_bytes()` on deterministic, representative generated fixtures. v1 and v2 are current serializer paths. |
| Proposed v3 blocks | Deterministic projection, **not** an existing production block | The closed v3 descriptor and a protocol-v2-style canonical envelope from `milestone-7-compression-protocol.md`; `identity/1`, actual Task 7.4 zstd/1 framing, and adaptive whole-block fallback are compared. |
| SQLite disk use | Direct, isolated current-storage measurement | Temporary databases use the existing `SQLiteStorageBackend`, its unchanged tables and JSON-section persistence. v3 uses that current JSON-section mechanism only as a storage-engine projection; it is not a future v3 schema measurement. |

No finalized production blocks were available as checked-in fixtures. Certificate-bearing rows therefore use a deterministic schema-shaped generated admission bundle with production-shaped 65-byte signatures, ten vote records, and variable native-transaction records. These fixtures exercise the actual v2 serializer but are not issued certificates or finality evidence. The result file calls this out explicitly.

The corpus is `zoidbergchain-media-benchmark-v1` version 1.1.0 (36 deterministic repository-authored accepted media samples), manifest SHA-256 `d872a8669cad218b72e5dbcf1dfbbff4de8718fc48c37f4950bf7dc46bff121f`. It includes small, medium, and large text/image samples, including capacity samples. The latter remain useful for the 2 MiB evaluation but are not claims of current admission acceptance.

## Reproduce

From the repository root, using the pinned project environment:

```powershell
.\.venv\Scripts\python.exe scripts\milestone_7_task_7_7_block_composition.py
.\.venv\Scripts\python.exe -m pytest tests\test_milestone_7_task_7_7_block_composition.py -q --tb=short
```

The runner verifies that the corpus regenerates exactly, writes [raw machine-readable results](../benchmarks/milestone_7_task_7_7_results.json), and creates only temporary, isolated SQLite databases. Configuration is versioned in [the measurement configuration](../tests/fixtures/milestone_7_block_composition_v1_config.json). It records Python, platform, SQLite, and zstandard versions in the result. This run used Python 3.13.5, SQLite 3.49.1, and zstandard 0.25.0.

The stored raw rows contain original and encoded bytes, all additive component bytes, descriptor overhead, metadata percentage, selected adaptive codec, input categories, and per-observation database/WAL sizes. The fixture certificate is purposefully identified as generated provenance instead of being presented as a finalized block.

## Accounting method

For each canonical envelope, the runner partitions every byte exactly once into:

1. the complete serialized media field;
2. the admission certificate field (including its embedded signatures);
3. transaction/native-transaction fields (including their embedded signatures);
4. block header fields;
5. remaining structural fields;
6. outer domain-envelope fields; and
7. braces, commas, and other delimiters.

These seven additive values reconcile exactly to `complete_serialized_block_bytes`. `signature_bytes_subset` is reported only as a diagnostic subset of certificate and transaction bytes; it is not added a second time. Likewise, original media length, stored encoded-payload length, and base64/hex character length are intentionally distinct quantities.

`metadata_percent = (complete serialized bytes - serialized media-field bytes) / complete serialized bytes * 100`.

Thus “metadata” includes headers, certificates, signatures, transactions, structural fields, and JSON delimiters. It does not count the media descriptor twice. “Media descriptor overhead” is a separate non-additive diagnostic: full serialized media field minus the payload-string characters. Current v1/v2 media is the canonical tagged hexadecimal bytes object; v3 media is a descriptor with strict base64 payload.

Percentiles are equal-block, nearest-rank values: the sorted value at `ceil(n × p / 100)`. The aggregate percentage is byte-weighted: total nonmedia bytes divided by total complete bytes. Each per-representation population has 36 rows, so p99 is descriptive rather than a robust tail estimate; no small blocks were discarded.

## Complete canonical-block results

All values below are bytes except percentages. `v3 adaptive` chooses zstd only when the **complete constructed block**, including descriptor/base64 change, is smaller; 26/36 corpus records select zstd and 10 retain identity.

| Representation | p50 | p95 | p99 | Worst | Metadata p50 | p95 | p99 | Worst | Byte-weighted metadata |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Current v1 identity | 12,218 | 3,062,921 | 3,547,781 | 3,547,781 | 15.13% | 84.07% | 91.79% | 91.79% | 0.64% |
| Current v2 identity | 25,403 | 3,076,190 | 3,561,029 | 3,561,029 | 57.74% | 98.12% | 99.10% | 99.10% | 4.36% |
| Projected v3 identity | 21,890 | 2,055,683 | 2,379,140 | 2,379,140 | 66.28% | 97.43% | 98.12% | 98.12% | 6.30% |
| Projected v3 zstd candidate | 20,799 | 2,055,747 | 2,379,208 | 2,379,208 | 72.81% | 97.57% | 98.01% | 98.01% | 7.19% |
| Projected v3 adaptive | 20,787 | 2,055,683 | 2,379,140 | 2,379,140 | 72.85% | 97.57% | 98.12% | 98.12% | 7.19% |

The <15% target is not met for small-media workloads or typical per-block v2/v3 samples. It is met byte-weighted for large media (v3 adaptive 1.36%; current v2 0.83%) because fixed evidence amortizes over media bytes. It is not met for the equal-weight representative-image v3 adaptive group: p50 64.39%, p95 95.59%, worst 96.94%, byte-weighted 36.39%. Current v1 representative images have p50 12.14% but p95 62.01%; v1 avoids the complete v2 admission certificate and is not a safe substitute for current admission semantics.

This is an honest failure of a universal <15% per-block target, not a reason to remove required evidence. The dominant contributor for small blocks is the certificate (476,357 bytes across 36 v2/v3 fixtures), followed by transaction/native records and headers. A future target needs an explicit workload definition or a minimum-media-size qualification.

### Aggregate component accounting

| Component total across 36 rows | Current v2 identity | Projected v3 adaptive |
| --- | ---: | ---: |
| Serialized media representation | 12,190,030 | 7,055,323 |
| Media descriptor overhead (diagnostic subset of media field) | 2,196 | 8,291 |
| Certificate (includes signatures) | 476,357 | 476,357 |
| Transaction records (includes signatures) | 34,522 | 34,594 |
| Header | 7,551 | 7,695 |
| Remaining structural metadata | 31,186 | 22,311 |
| Envelope + delimiters | 5,904 | 5,904 |
| Complete serialized blocks | 12,745,550 | 7,602,184 |

The current representation also has a physical compatibility duplicate: `Block.to_dict()` persists `meme.encoded_image` as base64 while the canonical v1/v2 commitment persists `media_bytes` as hex. Native transaction records appear in both the chain record and normalized SQLite storage. These are separate physical copies and are not added into the canonical-block table above.

## Compression contribution

The Task 7.4 baseline remains the source for codec behavior; this task uses its `zstd/1` profile (level 3, 256 KiB window, checksum/content size, no dictionary, one thread) only for a storage projection. The adaptive 36-row corpus changes payload bytes from 6,093,917 original to 5,285,234 encoded, a 13.27% payload reduction. It changes complete projected v3 block bytes from 8,680,536 identity to 7,602,184 adaptive, a 12.42% reduction (1,078,352 bytes).

This is not an assertion about real-world meme upload rates: the corpus is repository-authored synthetic media and current v3 does not exist in production. It does show why whole-block fallback is required: v3 zstd candidates are not always smaller after base64 and descriptor effects, and 10 records retained identity.

## SQLite physical storage results

This uses WAL mode, 4,096-byte pages, empty-database baseline 270,336 bytes, and the existing `storage_sections.json_data` chain persistence. It reports retained logical chain JSON, allocated pages, main database size, transient WAL, post-checkpoint size, and post-VACUUM size separately. The SQLite build did not expose the optional `dbstat` virtual table, so table-versus-index page attribution is unavailable; index overhead is included in physical totals but cannot be isolated in this environment.

| 36-block fixture | Logical chain JSON | DB after checkpoint | DB after VACUUM | Checkpoint allocation | VACUUM allocation | WAL before checkpoint | WAL after checkpoint |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Current v2 identity (direct current storage) | 20,896,854 | 29,659,136 | 21,229,568 | 29,659,136 | 21,229,568 | 21,156,232 | 0 |
| Projected v3 adaptive (current JSON-section engine only) | 7,621,402 | 10,551,296 | 7,929,856 | 10,551,296 | 7,929,856 | 10,728,512 | 0 |

The 1-, 5-, 15-, and 36-block raw observations are in the JSON result so page allocation artifacts are visible rather than mistaken for linear overhead. At 36 blocks, v2 JSON is 20.9 MB and transient WAL is 21.2 MB before checkpoint. Compaction reduces retained current-v2 physical DB size by 8.43 MB; it reduces the v3 storage-engine projection by 2.62 MB. WAL is temporary write amplification, not long-term retained state. Rollback-journal mode was not measured; neither are backups, filesystem compression, content-cache files, nor a future BLOB-based v3 schema.

## Candidate size limits and admission fit

These are evaluation findings, **not** production limit changes:

| Candidate | Original-media cap | Encoded-media cap | Complete-block cap | Result |
| --- | ---: | ---: | ---: | --- |
| Current provisional | 256 KiB | 256 KiB | 512 KiB | 31/36 projected-adaptive corpus rows fit all three caps. Capacity samples and certificate-bearing overhead show that a per-media limit alone is insufficient. |
| Evaluated larger option | 2 MiB | 2 MiB | 3 MiB | The largest constructed v3 adaptive fixture is 2,379,140 bytes, leaving 766,588 bytes under a 3 MiB cap. This is evidence for evaluation only, not a safe finalized bound. |

Any activation needs a reserved-overhead budget or, preferably, an exact admission-to-block-fit check after every consensus-relevant certificate, reward, native transaction, caption, and finality-required field is fixed. It must reject a media submission whose eventual constructed canonical block exceeds the block cap. The exact v3 canonical serializer used by production must become the single source of that calculation.

No complete-block limit can be finalized yet because the protocol has no frozen maxima for certificate vote count/signature form, native transaction count/record size, caption size in this measured fixture, or whether/how finality attachments enter retained canonical data. Decoder activation also remains blocked on the outstanding codec security/isolated-decoder review gates; a 2 MiB media cap must additionally freeze decoder output, frame/window, memory, and total-work limits.

## Inputs for the three-year economics simulator

Do not begin that simulator from this task. It will need separately stated low/base/high assumptions for accepted blocks per day by MIME and size bucket, empirical upload mix (not this synthetic corpus), identity/zstd selection frequency, canonical and physical bytes per block from this report, cache/duplicate retention, WAL/checkpoint/backup policy, storage price, replication/backup count, sync bandwidth, CPU/decode cost, and expected growth. Use the raw per-row bytes rather than a single compression percentage; retain separate logical canonical, SQLite-retained, and transient-WAL series to prevent double-counting.

## Remaining gaps and release blockers

- Current results are generated fixtures, not harvested finalized chain blocks; repeat against finalized production-shaped records when safely available.
- The current SQLite layout stores whole-chain JSON. A future BLOB-row v3 layout, exports, snapshots, content cache, journal mode, and backup behavior require their own measurements and must not be inferred from this projection.
- `dbstat` is unavailable in this SQLite build, so exact table/index page split remains a measurement gap.
- V3 schema, its final protocol envelope, exact transaction/certificate adapters, all maxima, and finality placement are not implemented or frozen. The v3 values here remain projections.
- Task 7.5/7.6 decoder-security and isolation review blockers remain release blockers; this task does not alter them.

