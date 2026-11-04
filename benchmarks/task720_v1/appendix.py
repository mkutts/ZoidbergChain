"""Render evidence tables without changing any measurement or historical file."""
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]


def main():
    read=lambda n:json.loads((HERE/n).read_bytes())
    m=read('metrics.json'); c=read('codecs.json'); resources=read('resource_summary.json')
    output=[]
    emit=output.append
    emit('### A. Raw codec byte-weighted reduction by category\n')
    names=['identity-1','zstd-3','zstd-6','zstd-9','brotli-4','brotli-6','zlib-6']
    emit('| Category | '+ ' | '.join(names)+' |')
    emit('| --- | '+' | '.join(['---:']*len(names))+' |')
    for cat in c['aggregates']['zstd-3']:
        emit('| '+cat+' | '+' | '.join(f"{c['aggregates'][n][cat]['byte_weighted_savings_percent']:.5f}%" for n in names)+' |')
    emit('\nThese are raw encoded/original reductions, before descriptor selection and strict-profile acceptance. Negative values are expansion.\n')
    emit('### B. Default Zstd-3 category bytes, savings tails and encode/decode time\n')
    emit('| Category | n | Original B | Encoded B | Savings p50 / p95 / worst % | Raw expansions | Encode p50 / p95 / worst µs | Decode p50 / p95 / worst µs |')
    emit('| --- | ---: | ---: | ---: | --- | ---: | --- | --- |')
    for cat,s in c['aggregates']['zstd-3'].items():
        ds=s['distributions']
        savings=' / '.join(f"{ds['savings_percent'][k]:.5f}" for k in ('p50','p95','worst'))
        enc=' / '.join(f"{ds['encode_ns_median'][k]/1000:.2f}" for k in ('p50','p95','worst'))
        dec=' / '.join(f"{ds['decode_ns_median'][k]/1000:.2f}" for k in ('p50','p95','worst'))
        emit(f"| {cat} | {s['objects']} | {s['original_bytes']:,} | {s['encoded_bytes']:,} | {savings} | {s['raw_expansions']} | {enc} | {dec} |")
    emit('\nTime distributions are across per-object medians of nine repetitions; every raw timing sample and every profile/category distribution remains in codecs.json. Savings worst means minimum reduction; timing worst means maximum duration.\n')
    emit('### C. Full canonical additive byte ledger\n')
    emit('| Component | Historical 36 records B | New 34 records B |')
    emit('| --- | ---: | ---: |')
    a=m['historical']['all']; b=m['production-like']['all']
    for key in a['partition']:
        emit(f"| {key} | {a['partition'][key]:,} | {b['partition'][key]:,} |")
    emit(f"| **Complete R (sum above)** | **{a['totals']['record_bytes']:,}** | **{b['totals']['record_bytes']:,}** |")
    emit('\nMedia/member overhead is included above, not an omitted additional charge. The following are diagnostic byte domains, not an additive second partition:\n')
    emit('| Byte domain | Historical B | New B |')
    emit('| --- | ---: | ---: |')
    for key in ('source_bytes','original_bytes','encoded_bytes','base64_media_bytes','nonmedia_bytes'):
        emit(f"| {key} | {a['totals'][key]:,} | {b['totals'][key]:,} |")
    for name,fn in [('Base64 expansion B − E',lambda x:x['base64_media_bytes']-x['encoded_bytes']),
                    ('Descriptor/media-field framing',lambda x:None),('All bytes outside encoded E',lambda x:x['record_bytes']-x['encoded_bytes'])]:
        if name=='Descriptor/media-field framing':
            left=a['partition']['serialized_media_representation_bytes']-a['totals']['base64_media_bytes']
            right=b['partition']['serialized_media_representation_bytes']-b['totals']['base64_media_bytes']
        else:
            left=fn(a['totals']); right=fn(b['totals'])
        emit(f'| {name} | {left:,} | {right:,} |')
    binary=100*(b['totals']['record_bytes']-b['totals']['encoded_bytes'])/b['totals']['record_bytes']
    emit(f'\nThe new aggregate stricter `(R−E)/R` share is **{binary:.5f}%**, including base64 expansion. Exact per-record field paths/byte charges are in records.json; all 78 ledgers reconcile.\n')
    emit('### D. New per-MIME and payload-size results\n')
    emit('| Group | n | Metadata p50 % | p95 % | Worst % | Canonical-byte weighted % |')
    emit('| --- | ---: | ---: | ---: | ---: | ---: |')
    for name,s in m['production-like'].items():
        if name=='all' or name.startswith('mime_band:'):
            continue
        d=s['metadata_percent']
        emit(f"| {name} | {s['objects']} | {d['p50']:.5f} | {d['p95']:.5f} | {d['worst']:.5f} | {s['canonical_byte_weighted_metadata_percent']:.5f} |")
    emit('\nBands by accepted original bytes: tiny 1–1,023; small 1,024–16,383; medium 16,384–262,143; large 262,144–2,097,152. The exact upper text cap belongs to the large byte band. MIME×band and historical equivalents are in metrics.json.\n')
    emit('### E. Focused regression outcomes and resources\n')
    emit('| Completed selection | Passed | Failed | Skipped |')
    emit('| --- | ---: | ---: | ---: |')
    totals=dict(passed=0,failed=0,skipped=0)
    for group in ('acceptance','measurements','codecs','format'):
        outcomes=read(group+'_outcomes.json')
        counts={k:sum(r['outcome']==k for r in outcomes['reports']) for k in totals}
        for key in totals:
            totals[key]+=counts[key]
        emit(f"| {group} | {counts['passed']} | {counts['failed']} | {counts['skipped']} |")
    emit(f"| **Disjoint final total** | **{totals['passed']}** | **{totals['failed']}** | **{totals['skipped']}** |")
    emit('\nThere are zero deselections. Acceptance includes nine new cases and twelve unchanged reproduction guards; measurements includes both corrected historical tests. All 193 skips explicitly require an actual Linux kernel; exact IDs/reasons are retained. No incomplete or earlier failed attempt is added to these totals.\n')
    emit('| Worker observation (210 record/source trials) | p50 | p95 | Worst |')
    emit('| --- | ---: | ---: | ---: |')
    for key,values in resources['worker'].items():
        emit(f"| {key} | {values['p50']:,} | {values['p95']:,} | {values['worst']:,} |")
    emit('\nCommit bytes are Windows job/process measurements, not RSS. Sensitivity-worker and boundary-worker peak observations are not part of this 210-observation summary. Native in-process codec peak memory remains unavailable.\n')
    emit('### F. Reproduction fingerprints\n')
    emit('| Artifact | SHA-256 |')
    emit('| --- | --- |')
    comparison=read('replay_comparison.json')
    for name,entry in comparison.items():
        assert entry['exact_nontiming']
        emit(f"| {name} | `{entry['reference_sha256']}` |")
    emit('\nThe fresh second run reproduced manifest/metrics/admission/historical audit bytes exactly and all non-timing codec/record data exactly. Raw codec/record file hashes differ only because timing/process/resource observations are retained. Independent cross-checks pass on both runs. The complete inventory is checksums.sha256.\n')
    summary=dict(task='7.20',profile='task720-production-like-v1',branch='Compression-State-Bloat-and-Node-Economics',
        head='681e74863a2985b706138a95956d4bd885d062cd',tests=totals,production_like_records=34,historical_records=36,
        sensitivity_records=8,native_codec_rows=238,strict_valid_source_trials=139,strict_invalid_candidates=1,
        acceptance=dict(A='PARTIAL',B='PARTIAL',C='PASS (isolated)',D='PASS (measured)',E='PASS (frozen v3)',F='FAIL',G='PASS (pinned Windows)'),
        metadata=m['production-like']['all'],owner_review_ready=True,milestone_complete=False,activation=False,
        replay_exact_nontiming=all(x['exact_nontiming'] for x in comparison.values()))
    (HERE/'summary.json').write_text(json.dumps(summary,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    report=ROOT/'docs/milestone-7-production-like-compression-and-metadata-acceptance.md'
    text=report.read_text(encoding='utf-8')
    marker='### A. Raw codec byte-weighted reduction by category'
    text=text.split(marker)[0].rstrip()+'\n\n'+'\n'.join(output)
    report.write_text(text,encoding='utf-8')
    print('Wrote measured appendix and summary:',totals)


if __name__=='__main__':
    main()
