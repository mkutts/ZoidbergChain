"""Build only the Task 7.23 recommendation from new measured evidence."""
from collections import Counter
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
REPORT=ROOT/'docs/milestone-7-meme-first-launch-sizing-recommendation.md'


def read(n): return json.loads((HERE/n).read_bytes())
def table(headers, rows):
    return '\n'.join(['| '+' | '.join(headers)+' |','| '+' | '.join('---' for _ in headers)+' |']+
                     ['| '+' | '.join(str(v) for v in row)+' |' for row in rows])
def f(v,d=2): return f'{v:,.{d}f}'
def kib(v): return f(v/1024,0)+' KiB'


def main():
    c=read('candidates.json');rec=read('records.json');code=read('codecs.json');econ=read('economics.json')
    base=read('baseline.json');before=read('preflight.json');primary=rec['rows'];valid=[r for r in primary if r['record_bytes'] is not None]
    samples=read('manifest.json')['samples'];ps=c['profiles'];s=c['primary'];G=2**30
    source_table=table(['Source / boundary','Inspected value','Scope'],[
        ['canonical_v3/primitives.py MAX_RECORD',f(base['inactive_v3']['complete'],0)+' B','Inactive frozen v3'],
        ['canonical_v3/media.py MAX_IMAGE / MAX_ENCODED','2,097,152 / 2,097,152 B','Inactive frozen v3'],
        ['canonical_v3/media.py MAX_TEXT','262,144 B','Inactive frozen v3; canonical accepted text'],
        ['media_admission_policy.py accepted_image_bytes','262,144 B','Active admission'],
        ['media_admission_policy.py accepted_plain_text_bytes_after_canonicalization','262,144 B','Active admission; submission text has a separate UI bound'],
        ['media_admission_policy.py canonical_serialized_non_genesis_block_bytes','524,288 B','Active admission/legacy block policy'],
        ['canonical_v3/block.py check_budgets','196,608 B certificate + 98,304 B native array + 32,768 B rest','Disjoint component ceilings, plus payload base64'],
        ['codec_prototype/strict_decoder.py','2 MiB output; 256 KiB window; 64 blocks; 1 MiB native arena','Codec checks/guard, not full MIME safety']])
    corpus_table=table(['Dataset MIME','Primary n','Original min / p50 / max B','Coverage'],[
        [mime,len(group),f(min(r['original_bytes'] for r in group),0)+' / '+f(sorted(r['original_bytes'] for r in group)[(len(group)-1)//2],0)+' / '+f(max(r['original_bytes'] for r in group),0),
         'Two sizes × four semantic types + five byte boundaries'+('; two RGBA stickers' if mime=='image/png' else '') if mime in ('image/jpeg','image/png','image/webp') else 'Two sizes × two two-frame styles + five boundaries' if mime=='image/gif' else 'Seven quip lengths, 8–262,144 B']
        for mime in sorted({r['mime'] for r in primary})
        for group in [[r for r in primary if r['mime']==mime]]])
    codec_table=[]
    for p in code['profiles']:
        rr=[r for r in code['rows'] if r['candidate']==p['id'] and r['id']!='text-expansion-control']
        orig=sum(r['original_bytes'] for r in rr);enc=sum(r['encoded_bytes'] for r in rr)
        vr=[r for r in rr if r['complete_record_bytes'] is not None]
        codec_table.append([p['id'],f(orig,0),f(enc,0),f(100*(1-enc/orig),3)+'%',sum(r['raw_expansion'] for r in rr),
            f(sum(r['complete_record_bytes'] for r in vr),0)+(' hypothetical' if p['codec']=='brotli' else ' legal-size contexts'),
            f(sum(sorted(r['encode_cpu_ns'])[2] for r in rr)/1e6),f(sum(sorted(r['decode_cpu_ns'])[2] for r in rr)/1e6)])
    codec_table=table(['Native profile','Primary M B','E B','Raw saving','Grow n','56-context complete R B','Sum median encode CPU ms','Sum median decode CPU ms'],codec_table)
    adaptive_table=table(['MIME / valid n','Original M B','Selected E B','Complete R B','Same-context identity R B','Net canonical saving','Zstd / identity'],[
        [mime+' / '+str(len(group)),f(sum(r['original_bytes'] for r in group),0),f(sum(r['encoded_bytes'] for r in group),0),
         f(sum(r['record_bytes'] for r in group),0),f(sum(r['identity_record_bytes'] for r in group),0),
         f(100*(1-sum(r['record_bytes'] for r in group)/sum(r['identity_record_bytes'] for r in group)),3)+'%',
         str(sum(r['codec']=='zstd' for r in group))+' / '+str(sum(r['codec']=='identity' for r in group))]
        for mime in sorted({r['mime'] for r in valid}) for group in [[r for r in valid if r['mime']==mime]]])
    common_table=table(['Common original image/GIF cap','Admitted / 58','Percent','M p50 / p95 / p99 / max B','R p50 / p95 / p99 / max B','E ceiling / block cap'],[
        [kib(p['static_cap']),p['admitted'],f(p['admitted_percent'])+'%',
         ' / '.join(f(p['statistics']['original_bytes'][k],0) for k in ('p50','p95','p99','worst')),
         ' / '.join(f(p['statistics']['record_bytes'][k],0) for k in ('p50','p95','p99','worst')),
         kib(p['encoded_cap'])+' / '+kib(p['proposed_block_cap'])] for p in c['common_ceiling']])
    exclusion_table=table(['Original image/GIF ceiling','Excluded JPEG','PNG','WebP','GIF','Text'],[
        [kib(p['static_cap']),*[p['excluded_by_mime'].get(m,0) for m in ('image/jpeg','image/png','image/webp','image/gif','text/plain')]] for p in c['common_ceiling']])
    metadata_table=table(['Population','p50 %','p95 %','Worst %','Below 15%','Original target verdict'],[
        [name,f(stats['metadata_percent']['p50'],5),f(stats['metadata_percent']['p95'],5),f(stats['metadata_percent']['worst'],5),str(stats['below15'])+'/'+str(stats['valid_record_n']),'FAIL']
        for name,stats in [('All 56 format-valid primary records',s)]+[(p['name'],p['statistics']) for p in ps]])
    invalid_trials=[dict(id=r['id'],candidate=r['candidate'],stage=r.get('strict_stage'),code=r.get('strict_code')) for r in code['rows'] if r.get('strict_status')=='INVALID']
    profile_table=table(['PROPOSED UNAPPROVED profile','Static','Animated GIF','Text','Encoded','Complete block','Equal admitted mean R','Coverage'],[
        [p['name'],kib(p['static_cap']),kib(p['gif_cap']),kib(p['text_cap']),kib(p['encoded_cap']),kib(p['proposed_block_cap']),f(p['statistics']['record_bytes']['mean'],0)+' B',f(p['admitted_percent'])+'% ('+str(p['admitted'])+'/58)'] for p in ps])
    bound_table=table(['PROPOSED profile','Base64 maximum B','Full reserved evidence / tx / rest B','Analytic complete bound B','Rounded cap B','Rounding surplus B'],[
        [p['name'],f(p['base64_bound'],0),'196,608 / 98,304 / 32,768',f(p['safe_complete_bound'],0),f(p['proposed_block_cap'],0),f(p['rounding_headroom'],0)] for p in ps])
    storage_rows=[];reserve_rows=[];bandwidth_rows=[];cost_rows=[]
    for p in ps:
        for rate in (100,1000,10000):
            group=[v for v in econ['scenarios'] if v['workload']==p['name'] and v['blocks_per_day']==rate]
            m=group[0]['month36']
            storage_rows.append([p['name'],rate,*[f(m[k]/G) for k in ('serialized_media_bytes','other_canonical_bytes','canonical_bytes','index_and_page_overhead_bytes','fragmentation_bytes','primary_database_bytes')]])
            reserve_rows.append([p['name'],rate,*[f(m[k]/G) for k in ('operational_headroom_bytes','snapshot_bytes','backup_retained_bytes','recovery_workspace_bytes','local_capacity_bytes')]])
            bandwidth_rows.append([p['name'],rate,*[f(m[k]/G) for k in ('bootstrap_once_bytes','peer_incoming_bytes','peer_outgoing_bytes','backup_upload_bytes','charged_egress_bytes')]])
            cost_rows.append([p['name'],rate,*[f(next(g for g in group if g['profile']==host)['month36']['cost_usd']['total']) for host in ('budget_vps','storage_focused','mainstream_cloud')],
                ' / '.join(f(next(g for g in group if g['profile']==host)['three_year_cumulative_usd']) for host in ('budget_vps','storage_focused','mainstream_cloud'))])
    storage_table=table(['Profile','Blocks/day','Canonical media GiB','Other canonical GiB','Total C GiB','Index/page allowance GiB','Fragmentation GiB','Primary P GiB'],storage_rows)
    reserve_table=table(['Profile','Blocks/day','Operational H GiB','Snapshot S GiB','Remote backups K GiB','Recovery W GiB','Total local L GiB'],reserve_rows)
    bandwidth_table=table(['Profile','Blocks/day','Fresh sync once GiB','Month-36 peer ingress GiB','Peer egress GiB','Backup upload GiB','All charged egress GiB'],bandwidth_rows)
    cost_table=table(['Profile','Blocks/day','Budget VPS $/mo','Storage-focused $/mo','Mainstream cloud $/mo','3-year total USD budget / storage / cloud'],cost_rows)
    sens_rows=[]
    for p in ps:
        for label in ('small','largest_quartile'):
            group=[v for v in econ['sensitivities'] if v['workload']==p['name']+'_'+label and v['blocks_per_day']==1000]
            w=next(w for w in econ['workloads'] if w['name']==p['name']+'_'+label)
            sens_rows.append([p['name'],label,f(w['canonical_bytes'],0),*[f(next(g for g in group if g['profile']==host)['month36']['cost_usd']['total']) for host in ('budget_vps','storage_focused','mainstream_cloud')]])
    sensitivity_table=table(['Profile','Accepted workload sensitivity','Mean R B','Budget $/mo at 1000/day','Storage $/mo','Cloud $/mo'],sens_rows)
    worst_table=table(['Profile','100/day canonical GiB','1000/day canonical GiB','10000/day canonical GiB'],[
        [p['name'],*[f(econ['worst_case_canonical_bytes_3yr'][p['name']][str(rate)]/G) for rate in (100,1000,10000)]] for p in ps])
    rr=rec['diagnostic_controls'][0]
    test=read('test_results.json') if (HERE/'test_results.json').exists() else {'status':'PENDING'}
    replay=read('replay_comparison.json') if (HERE/'replay_comparison.json').exists() else {'status':'PENDING'}
    text=f'''# Milestone 7 Task 7.23 — Meme-first launch sizing recommendation

Date: **2026-10-29, America/New_York**. This is a benchmark and protocol-policy study only. **Every proposed value is PROPOSED, UNAPPROVED and INACTIVE. Original Milestone 7 remains INCOMPLETE; launch/network readiness remains BLOCKED.** MODEL A remains mandatory: recover the complete accepted original byte-for-byte using canonical on-chain data and the historical normative decoder.

## 1. Recommendation and authority

**Prefer profile B, balanced meme-first**, ranked B first, A second, C third for the initial experiment. B retains the current active 256 KiB static-image allowance and explores 512 KiB GIFs with 16 KiB text. Its full experimental block allowance is 1 MiB after reserving existing signed evidence and transactions. This is an evidence-informed starting hypothesis, not a measured optimum or production admission forecast. The synthetic corpus cannot establish actual user demand.

{profile_table}

All profile values, including expected sizes and costs, are **PROPOSED / UNAPPROVED scenario results**. A/B/C are names, not an activation sequence. The static benchmark rows cover JPEG, PNG and WebP; all GIF samples are animated. Under the proposed product profile, a single-frame GIF would use the static ceiling, but that subtype is not separately measured here and receives no extra coverage claim. The GIF column covers GIF animation. Animated WebP uses the static ceiling conservatively; any deployment must classify frame structure from the fully validated container and specify these rules in its separately approved policy. No video/audio or unknown MIME is admitted.

Branch `{before['branch']}`; initial HEAD `{before['head']}`. Task 7.22 was separately committed with title `{before['task722_commit']}`. Before writes the worktree/index were clean including untracked files. No ancestor/repository AGENTS.md was found. No delegation was used. [preflight.json](../benchmarks/task723_v1/preflight.json) records the initial state and all {len(before['tracked_sha256'])} preexisting tracked-file hashes. Only this report and `benchmarks/task723_v1/` are added. No stage, commit, push, reset, deployment, schema/fixture/genesis/reviewer/consensus/codec mutation or activation is performed.

## 2. Source-derived baseline and previous work

Read Tasks [7.18](milestone-7-original-scope-completion-audit.md), [7.19](milestone-7-reproducibility-and-regression-triage.md), [7.20](milestone-7-production-like-compression-and-metadata-acceptance.md), [7.21](milestone-7-disabled-compression-integration.md) and [7.22](milestone-7-final-economics-and-acceptance-review.md), their measurement/ledger/economics tools, frozen canonical producer/parser/evidence budgets and isolated strict decoder. Task 7.20 established synthetic general-media results and the metadata miss; 7.21 demonstrated a disabled application/recovery bridge; 7.22 corrected full capacity pricing and retained acceptance gaps. This study changes neither their data nor their verdicts.

{source_table}

The requested 3 MiB complete / 2 MiB encoded / 2 MiB image / 256 KiB text baseline is verified for **inactive v3**. It is not the current active image/block policy. The legacy active path still uses versions 1/2. [baseline.json](../benchmarks/task723_v1/baseline.json) snapshots the complete current policy, including MIME allowlist, dimensions, frames and local resource limits. All five supported MIMEs are exercised. Larger format-capacity records are not accepted-current submissions. Per-object active technical admission outcomes/reasons are retained in records.json, independently of every proposed size-only gate.

## 3. Corpus coverage, rights and representativeness

Version **1.0.0**, fixed seed 7232026. **58 equally counted primary originals**, plus one predeclared historical raw-expansion diagnostic outside the primary coverage/metadata/economic population. All new raster/text artifacts are self-created and dedicated to CC0-1.0; no downloads, private submissions, production traffic or assumed traffic weights. Original quips, procedural cartoon shapes and the installed Pillow default font provide captions. Existing fixture keys/signature context retain repository terms; their use is public test context only.

{corpus_table}

The fixed semantic factorial has caption, screenshot, two-panel image macro and high-detail noise at 320×240 and 1280×960 for each static MIME. There are two transparent RGBA PNG stickers; animated GIFs cover flat and high-entropy frames at two dimensions plus five near-ceiling files. A small animated WebP checks relevant supported-MIME behavior. Text lengths are 8, 64, 512, 4,096, 16,384, 65,536 and 262,144 bytes; their repeated quips are a compressible text-meme control, not representative long prose. JPEG/WebP/PNG/GIF containers are already compressed before outer codec trials. Texture is synthetic high entropy, not photography.

The five boundary targets per static MIME and GIF are 128/256/512/1024/2048 KiB. Bisection varies dimensions based **only on original container size**, requiring 90–100% of target. No outer compression, runtime, adaptive outcome or desired acceptance fraction influences membership. Random seeds, native settings, dimensions/frame counts, aggregate pixels, MIME, original lengths/hashes, provenance and construction are in [manifest.json](../benchmarks/task723_v1/manifest.json); [corpus.py](../benchmarks/task723_v1/corpus.py) regenerates all bytes. Encoder/library drift must fail manifest comparison.

Two fixed-dimension texture files exceed 2 MiB: JPEG **2,242,286 B**, PNG **3,594,660 B**. They remain in all 58-object admission denominators and native codec trials. The unchanged frozen producer rejects them; complete-record size, metadata and verification timing are explicitly unavailable. No valid mandatory-evidence record is fabricated. Thus complete-record statistics use **56 legal-size primary records**, clearly separated from 58-original size coverage. These exclusions cannot silently improve a codec or metadata claim. The small expansion diagnostic is excluded by design, not for its poor compression result.

This stratified stress/feature corpus deliberately overrepresents size boundaries and high entropy. Counts are coverage statistics, not acceptance probabilities for future users. There is no real photograph, popular-template sample, mobile upload distribution, or production mix. A consented/provenance-cleared pilot remains needed before claiming representative launch demand; this study does not close Task 7.22 R2 by relabeling synthetic data.

## 4. Lossless codec and complete-record measurements

Seven native configurations: identity; Zstd levels 1/3/9 with existing 256 KiB window, checksum, content size, single-thread/no dictionary framing; Brotli levels 1/5/9, generic mode and 256 KiB window. Production experimental selection remains **unchanged Zstd level 3 versus identity**. Alternate levels are benchmark encoder configurations, not new canonical codec versions. Brotli is comparison-only and is rejected by the frozen codec-ID allowlist. No third-party submission is executed.

Five measured repetitions after one warmup; wall time and process CPU measured separately. CPU measurements amortize approximately 20 ms of work per batch (up to 200,000 iterations) to reduce Windows coarse-tick quantization, including Python loop/call overhead; per-row batch counts and observations are retained. Table CPU sums are sums of per-object amortized medians, excluding fixture construction/signing. They are local Windows observations, not admission timeouts, cross-platform qualifications or throughput promises. The 413 trials include the diagnostic; the following 406-trial table excludes it and includes both above-ceiling texture originals. The complete column covers only the 56 legal-size contexts, and Brotli remains a hypothetical byte-length substitution; one actual serialized Zstd-3 context is rejected as detailed below.

{codec_table}

Every native trial compares exact original bytes and SHA-256. [codecs.json](../benchmarks/task723_v1/codecs.json) retains encoded hashes, raw sizes, descriptor/media-member sizes, complete-record sizes/statuses, timings and memory. For every legal identity/Zstd trial with E≤2 MiB, enrich.py constructs the actual complete frozen record, parses its signatures and records the strict isolated reconstruction outcome. Over-encoded and over-original trials are explicitly nonconstructible. Native roundtrip success does not establish frozen-profile acceptance: **{len(invalid_trials)} alternate Zstd trial(s) were strict INVALID**, recorded as `{json.dumps(invalid_trials)}`. These complete sizes are actual serialized records but rejected encodings, not accepted canonical-storage results. All actual selected producer records remain strictly VALID. Brotli can have a smaller hypothetical R but cannot be treated as valid v3 or credited as activated storage savings.

Selected adaptive records in [records.json](../benchmarks/task723_v1/records.json) use the actual unmodified producer, fourteen cryptographically signed votes, creator attestation, all required technical evidence, rewards and empty native transfers. Public fixture context is not authority to create chain history. Full JSON field ledgers and disjoint media/certificate/transaction/header/envelope/wrapper partitions each sum to the exact complete record. Identity replacements use the same evidence and context. Canonical-only reconstruction reads embedded payloads, without external media/cache. Text is already canonical, so source and accepted hashes/lengths coincide.

Actual adaptive results below cover **only the 56 legal-size primary objects**, with **31 Zstd / 25 identity** selections. The near-2-MiB GIF's default Zstd stream exceeds the frozen 64-block limit; the existing producer's INVALID-to-identity fallback preserves strict validity and exact originals without changing its behavior. Its rejected compressed size earns no adaptive storage credit. PNG/JPEG/WebP gains are workload-specific and small in aggregate; no large outer-compression promise is made for already-compressed images.

{adaptive_table}

M = original bytes; E = encoded bytes including codec frame; B = 4·ceil(E/3) base64 content; D = full canonical descriptor; media member = D+8 for `"media":`; R = complete canonical record including envelope/hash wrapper. E is not the stored canonical BLOB size. Metadata N=R−B includes descriptor fields, quotes, every signed evidence item, certificate, header, transactions and framing. Base64 expansion B−E is separately charged. Signature subsets are not added again.

The diagnostic reproduces the natural **{rr['original_bytes']}→{rr['encoded_bytes']} raw expansion** while D shrinks {rr['identity_descriptor_bytes']}→{rr['descriptor_bytes']} B and complete R shrinks {rr['identity_record_bytes']}→{rr['record_bytes']} B. Base64 length is unchanged and `zstd` is four label bytes shorter than `identity`. Actual adaptive selection optimizes complete serialized descriptor/R versus identity, not E≤M. All selected legal-size records satisfy R≤same-context identity R; physical SQLite allocation monotonicity is not proved.

Memory: native trials record separate untimed **Python traced allocation peaks only**, excluding native arenas/RSS. They are not codec-specific native total-memory peaks. Strict selected/alternate decoder requests record Windows Job peak commit and process resource counters; those include worker/interpreter/IPC overhead. Primary maximum selected-worker job commit is **{f(s['worker_peak_commit_bytes']/1048576)} MiB**. Complete parse/crypto/recovery wall time p50/p95/worst is **{f(s['verification_wall_ns']['p50']/1e6)} / {f(s['verification_wall_ns']['p95']/1e6)} / {f(s['verification_wall_ns']['worst']/1e6)} ms**, including process startup and existing verification helpers, not CPU-only decode. No unsupported native peak-memory claim is made.

## 5. Candidate ceilings, exclusions and security headroom

Common-ceiling comparison leaves text at its existing experimental 256 KiB and applies each image ceiling equally to GIF/static images. Admission here is a proposed original-size predicate only; current technical rejection reasons and all other admission checks still apply.

{common_table}

{exclusion_table}

Exact excluded IDs, original bytes, MIME and reasons-by-size are in candidates.json. That file also contains the complete **100-case separate-cap grid**: five static ceilings × five GIF ceilings × four text ceilings (8/16/64/256 KiB). Each case retains admission fraction, excluded MIME/size detail, M/R p50/p95/p99/worst, certificate/metadata distributions, selected-worker peaks/timing and encoded/complete safety budgets. Text/GIF differentiation is explored rather than assumed: a common 256 KiB image cap is a viable feature tradeoff; B's larger GIF allowance offers two-frame detail at increased worst-case storage. Corpus counts do not establish its real demand benefit.

The proposed encoded ceiling is min(2 MiB, max(original caps)+1 KiB). Identity always fits. The extra 1 KiB conservatively covers label/base64-rounding selection effects such as 104→105, and an explicit independent encoded gate still applies to received alternate representations. For the unchanged selector, if E>M, stored-size digit width cannot decrease; the four-byte codec-label saving cannot pay for an extra four-byte base64 group under strict shrink. Therefore selected raw expansion is at most two bytes; 1 KiB is a deliberately rounded reservation rather than a measured expansion requirement. This is not a general promise that any compressor's output fits: an oversized compressed encoding must be rejected or a future approved producer must retain identity. Existing codec behavior is untouched. Payload/dimension/frame/decoded-pixel restrictions remain independent.

For a v3 record satisfying the **unchanged existing component-budget checks**, the conservative complete bound is:

`R ≤ 4·ceil(encoded_cap/3) + 196,608 certificate + 98,304 native array + 32,768 rest`.

The complete cap rounds this sum up to 64 KiB. The three additive budgets are disjoint as implemented by check_budgets; rest already includes all remaining descriptor/envelope/caption/hash/framing bytes. No external proof or journal is presumed to fit for free. This is an analytic sufficient serialization bound, not a claim that every simultaneously maximal field combination is constructible or that a smaller empirical maximum is safe.

{bound_table}

No profile lowers certificate, transaction or rest budgets. Compared with measured ~{f(s['certificate_bytes']['p50'],0)} B p50 certificates and ~{f(s['metadata_bytes']['p50'],0)} B p50 total metadata, the full 192 KiB certificate reservation accommodates variable signed evidence; full 96 KiB native budget preserves transaction room, plus 32 KiB rest and rounding surplus. Sensitivity records use ten votes and independently long nonces/captions plus ten signed transfers; all are parsed/reconstructed and retained separately. They do not replace the primary fourteen-vote distribution. A proposed cap below valid mandatory evidence would be rejected by this framework.

These bounds establish byte capacity **conditional on frozen v3 and its retained gates**, not security certification. Keep codec checks: single complete frame, content-size/hash checks, no dictionary/skippable/concatenated/trailing data, bounded input/output/window/block count/work/native arena, deterministic sequence verification. Existing default worker guards are 128 MiB, 5 CPU seconds, 10 wall seconds and 5 startup seconds, with global concurrency two. Operational failure stays indeterminate/fail closed and must never become valid data or deterministic consensus-invalid solely because of a local timeout.

Keep active image defenses: ≤4096×4096, ≤60 frames, ≤16,777,216 aggregate decoded pixels, every frame validated; active technical worker 256 MiB/2 seconds. A smaller compressed/original cap does not bound decoded image pixels, image-parser bugs, signature work or pathological sequence complexity. Existing certificate size/vote/transfer/type/crypto checks remain necessary. Cold Linux/cross-platform qualification, malformed-case testing and independent security review remain required before any activation; this local study does not certify them.

## 6. Original metadata acceptance target

Use the original denominator **100·(R−B)/R**, equal-record nearest-rank p50/p95/worst. No padding, evidence removal or byte weighting is substituted.

{metadata_table}

Primary metadata bytes p50/p95/worst are **{f(s['metadata_bytes']['p50'],0)} / {f(s['metadata_bytes']['p95'],0)} / {f(s['metadata_bytes']['worst'],0)} B**; certificate value bytes are **{f(s['certificate_bytes']['p50'],0)} / {f(s['certificate_bytes']['p95'],0)} / {f(s['certificate_bytes']['worst'],0)} B**. Both above-ceiling controls have no valid R and no reported metadata ratio. Every tiny valid primary object remains included. All three requested primary statistics exceed the original **below-15%** target: **FAIL**, not PASS. Profile-specific misses are also shown directly.

For fixed N, N/R<0.15 requires B>(17/3)N, approximately E>(17/4)N. At N≈33 KiB, E must exceed roughly 140 KiB; tiny valid media cannot satisfy that threshold with mandatory evidence, and strong compression can increase metadata percentage while reducing actual R. The stricter (R−E)/R measure cannot improve the verdict. Smaller meme caps may worsen the target by admitting predominantly small records. The owner must separately accept a revised criterion/exception or authorize an evidence-preserving format redesign; this study supplies no waiver.

## 7. Three-year economics and month-36 hosting

All numbers below are **PROPOSED / UNAPPROVED analytical scenarios**, not quoted offers or production forecasts. Use Task 7.22's exact unchanged simulator/accounting assumptions and historical illustrative prices. Each profile's average is the equal-record mean of its admitted legal-size samples; its admission percentage is over all 58 originals. These means show corpus truncation effects, not changes expected in a real launch mix. No second mandatory raw-original disk copy is charged because MODEL A reconstruction is from canonical R.

36 months = 1,095 days; 109,500 / 1,095,000 / 10,950,000 accepted blocks. Month 36 has 31 days; GiB=2^30 B. C = blocks·mean R. P = 1 GiB + C + .10C index/page allowance + .15C fragmentation. These are analytical allowances, not newly measured physical indexes. H = .20P + 1.45·monthly_R·1.25 + 5 GiB. S=P (daily refresh, one retained full local snapshot); W=P (additional recovery workspace); K=4·.95P remote retained backups, four full uploads/month. L=P+H+S+W; all L is priced, including snapshots/headroom/workspace. No deduplication credit, WAL initialization or production DB access.

{storage_table}

{reserve_table}

Network: peer ingress=1.38·monthly_R; peer egress=11.52·monthly_R for eight peers; backup upload=4P/month; one fresh bootstrap=1.2C. Expected bootstrap serving and backup restore are each one event/year, charged as monthly fractions. These are workload assumptions, not measured network bytes. Fresh-node verification must still reconstruct/check every historical record; sync bytes alone do not quantify bootstrap CPU or elapsed recovery time.

{bandwidth_table}

Inherited profiles, USD/month: budget compute $20, included 160 GiB, extra disk $.05/GiB-month, backup $.006/GiB-month, egress $.01/GiB; storage-focused $45/500 GiB/$.02/$.006/$.01; mainstream cloud $40/160 GiB/$.10/$.05/$.09. Charge ceil(max(0,L/GiB−included)) extra disk, K·backup rate and all expected peer/backup/bootstrap/restore egress. Ingress assumed free. All are illustrative storage pools with 4 vCPU/8 GiB RAM reference assumptions, no tier/volume/IOPS feasibility or CPU sufficiency promise. Taxes, labor, redundancy replicas, region/currency effects and negotiated discounts are outside these prices.

{cost_table}

All profiles must disclose misses of the $100/month target at each traffic rate; the table makes no universal affordability claim. Three-year totals sum all 36 monthly bills, not 36×month-36. [economics.json](../benchmarks/task723_v1/economics.json) retains all monthly partitions and totals for 36 main cases (three profiles plus a common-average control × three rates × three hosts), plus 54 average-size sensitivity cases. This is model output based on measured logical R, not a new physical DB or hosting benchmark.

Price review **2026-10-29**: checked official [Hetzner Cloud](https://www.hetzner.com/cloud/), [AWS Lightsail pricing](https://aws.amazon.com/lightsail/pricing/) and [Backblaze B2 pricing](https://www.backblaze.com/cloud-storage/pricing). Hetzner's fetched page did not expose a complete priced regional bundle; B2 advertises a starting $6.95/TB-month, distinct from the inherited $.006/GiB-month backup assumption and not a host price. AWS lists region/bundle/storage/transfer-dependent rates. No complete same-region host+disk+backup+egress quote was established. Historical assumptions remain fixed for comparability; the review does **not** verify those rates as current purchasable offers. Obtain regional capacity/transfer/IOPS quotes before purchase or treating $100 as guaranteed.

### Worst-case ceiling versus expected average

At the cap every day, retained canonical bytes alone could reach:

{worst_table}

These are ceiling envelopes, excluding extra physical/backup capacity. Lowering the cap reduces maximum permitted growth. It reduces expected disk/cost **only if accepted mean R actually falls**. Retrying/resizing images can shift the mix differently; rejected uploads do not count as accepted blocks. The common `fixed_small_average_all_caps` workload fits A/B/C unchanged and has exactly the same costs under each cap. This control is saved once and applies identically to every profile, avoiding invented savings from the cap itself.

Holding each profile's limits fixed, admitted subsets show the impact of changing the average (illustrative selection sensitivities at 1,000/day):

{sensitivity_table}

These small and largest-quartile subsets are labelled alternatives, not reweighting of the primary corpus. Repeated quips may compress strongly while mandatory evidence still dominates. Worst-case original size, average accepted original size and average R must be monitored independently.

**Future review journal is separate, unapproved and unpriced here.** Do not interpret its exclusion as zero cost or declare combined-node affordability. It needs independently approved event rates, canonical evidence sizes, retention, authority/closure/finality proofs, replicas/indexes, bandwidth, backup and recovery accounting. External finality proofs are likewise outside measured R unless later explicitly embedded and charged; they cannot silently consume reserved headroom.

## 8. Launch profile tradeoffs and ranked preference

**Rank 1: B balanced (preferred, PROPOSED/UNAPPROVED).** Static 256 KiB preserves today's image allowance, while a separate 512 KiB GIF hypothesis offers more frame detail. Text 16 KiB supports compact memes but rejects the long text controls. Mean admitted R is {f(ps[1]['statistics']['record_bytes']['mean'],0)} B; size-only corpus coverage is {f(ps[1]['admitted_percent'])}%. Month-36 costs are in the profile/rate table above for all three hosts. Its 1 MiB complete cap safely retains full existing v3 component reservations. Users may need local resizes before submission; any resaved upload becomes a distinct original with its own hash, never a node-side lossy replacement.

**Rank 2: A lean (PROPOSED/UNAPPROVED).** Static 128 KiB, GIF 256 KiB, text 8 KiB; {f(ps[0]['admitted_percent'])}% coverage, {f(ps[0]['statistics']['record_bytes']['mean'],0)} B measured admitted mean R, 704 KiB complete cap. Lowest ceiling and simplest compact workload, at the cost of more screenshot/detail/GIF rejection and more client preparation. Signed evidence still dominates tiny memes; strict safety review remains necessary. Its lower byte allowance does not certify lower CPU or give a production cost guarantee.

**Rank 3: C flexible (PROPOSED/UNAPPROVED).** Static 512 KiB, GIF 1 MiB, text 64 KiB; {f(ps[2]['admitted_percent'])}% coverage, {f(ps[2]['statistics']['record_bytes']['mean'],0)} B measured admitted mean R, 1,728 KiB complete cap. More headroom for detailed screenshots and animation, with larger worst-case disk/sync exposure and greater operational provisioning. It still excludes near-2-MiB objects and both above-ceiling controls. High compression is not assumed for already-compressed images.

All three profiles keep MODEL A, every signed mandatory evidence field and independent pixel/frame/codec resource defenses. Distinct GIF/text caps are a product tradeoff to validate with actual accepted-workload data, not a demonstrated necessity. No MIME/policy/consensus activation occurs here.

## 9. Future community codec framework — PROPOSED, INACTIVE

This framework evaluates **lossless byte compression**, not visual similarity or lossy re-encoding. No submission is approved, rewarded, distributed or executed in this task. No uploaded-code execution or dynamic plugin mechanism is implemented.

1. **Normative deterministic decoding.** Publish a complete bitstream specification, canonical identifier and immutable version, supported inputs/dictionary rules, exact consumed-length behavior and deterministic reject reasons. Reject trailing/concatenated/ambiguous streams. Decoding must produce identical complete accepted original bytes and exact SHA-256 on every supported implementation/platform. Encoder determinism is desirable for benchmark reproducibility; consensus decoding cannot depend on unspecified native behavior.
2. **MODEL A closure.** All per-object side information/dictionaries must be canonical on-chain bytes or permanently specified normative historical decoder material. No URL, uploader service, private model, cache or mutable external dictionary may be required for fresh reconstruction. Include dictionary/setup bytes in net canonical accounting, including first-use and realistic amortization, not just ideal reuse.
3. **Canonical versions.** Never reinterpret existing identity/1 or zstd/1. Propose a new named/versioned codec through a separately reviewed protocol amendment and frozen test vectors. Unknown IDs remain fail closed. Preserve every existing historical decoder permanently, with maintained safe implementations; activating a new codec never makes old history undecodable.
4. **Deterministic complexity bounds plus local guards.** Specify independent encoded/output/window/block/depth/work bounds and finite memory arenas, zero unbounded allocation before size validation, bounded expansion, streaming output limits and checksums/hash verification. Test forged sizes, extreme ratios, tiny-run floods, overlapping copies, malformed tables, integer overflow, truncation, adversarial dictionaries, CPU stalls and mixed-frame bypasses. Separate consensus-validity predicates from local CPU/wall/memory failures; resource exhaustion must not manufacture validity.
5. **Cross-platform reproducibility.** Freeze a multi-architecture corpus/vector manifest, exact byte/hash outcomes on Windows/Linux and supported CPU architectures, reference and independent implementations, compiler/native-library versions and reproducible decoder builds. Test fresh-node historical replay, recovery and peer synchronization. Performance must fit an explicitly chosen minimum full-node class, including concurrency and certificate verification, not just a developer workstation.
6. **Public and withheld evaluation.** Publish independently governed semantic/entropy/size/MIME corpora plus invalid/adversarial suites and selection/weight rules before scoring. Keep an independently administered sealed holdout with commitments, controlled release and periodic refresh. Fix repeated-tuning access, benchmark leakage, duplicates and contamination; do not let submitters choose the scoring files or weights. Report all failures and per-stratum tails as well as aggregates.
7. **Net canonical benefit gate.** Measure M/E/B/D/R and physical storage separately against the same original, certificate and transaction context, identity and incumbent adaptive selector. Charge full headers, framing, dictionaries, codec/version/setup material and recovery dependencies. Require an owner-approved material improvement threshold and non-regression/security limits before eligibility; no threshold is enacted here. Better raw ratios on text alone or cherry-picked files do not justify a reward or a smaller block cap.
8. **Reward anti-gaming.** Predeclare eligible implementations, attribution/IP/license terms, fixed evaluation budget, independent judges, holdout access and appeal rules. Deduplicate equivalent submissions, prevent self-selected/duplicated traffic, Sybil votes, hard-coded benchmark lookup, hidden dictionaries, payload-specific bypasses and hardware-specific tricks. Audit exact-output failures and total verification costs. Reserve any proposed reward until independent review and approved release criteria are met; funding, recipients and payments require separate explicit authorization. No reward is promised by this study.
9. **Independent security and supply-chain review.** Review parser/decoder arithmetic, memory safety, complexity proofs, build/dependency provenance, licensing, fuzz/differential results and isolation. A native library speedup or public leaderboard win is insufficient. Resolve critical findings before proposing distribution; choose a reviewed implementation, never an arbitrary uploaded binary.
10. **Versioned approval/activation.** Owner-approved protocol specification, independent review, frozen conformance suite, supported decoder availability, staged testnet rehearsal, validator adoption/quorum policy and explicit activation height/version are prerequisites. Define failure/rollback handling without invalidating finalized history, historical reconstruction and support commitments. Codec adoption and cap reductions are separate approval items; neither happens automatically.

## 10. Cap reduction decision policy — independent of codec activation

A new codec alone does not shrink consensus worst-case requirements. High-entropy and already-compressed files may still need identity; mandatory certificates and transactions do not disappear; a stronger encoder may increase decoder work or require unavailable implementations. The existing selector's representation savings are not a universal compression ratio or physical-storage proof.

For any proposed lower cap, require an owner-reviewed record of: actual accepted original/encoded/complete distributions by MIME/dimensions/animation and workload period; tail and worst-case encoded bounds including identity and canonical framing; mandatory evidence/transaction bounds; independent CPU/memory/decoded-pixel/work verification; supported deterministic decoders on all validator platforms; permanent historical compatibility and fresh-node replay; demonstrated sync/recovery/storage capacity; and explicit validator adoption with versioned governance. Publish both fraction affected and user migration/resize costs. Size gates must not retroactively invalidate historical blocks. Keep old historical bounds under their original versions and define the new height/version rules explicitly.

Approve codec activation, original/encoded admission ceilings and complete-block cap reductions as **independent owner decisions**, each with a concrete specification and evidence. Remeasure full bounds when adding certificate fields, changing transaction counts or embedding finality/journal evidence. Never assume a higher mean compression ratio makes a cap lower than a valid mandatory-evidence record viable.

## 11. Reproduction, tests and commit readiness

Use the pinned existing Windows environment. No install/network/production DB is required. [README.md](../benchmarks/task723_v1/README.md) gives exact commands. run.py constructs originals, benchmarks native codecs and selected complete records; enrich.py constructs alternate legal identity/Zstd complete records; crosscheck.py independently checks identities/ledgers/percentiles/security budgets and Decimal economic bills without importing the simulator; test_study.py checks analytical boundary cases and retained failures. replay.py runs a fresh full measurement and compares every deterministic field/encoded/record hash, excluding only clocks/resource observations. finalize.py checks preservation and writes checksums. Tracemalloc/native peak limitations remain explicit.

Focused test execution status: **{test.get('status','PENDING')}**, counts `{json.dumps(test.get('counts',{}))}`. Exact commands, exit codes, counts and one excluded live-API initialization test ID/reason are in test_results.json and tests.txt. The initial default-temp/API attempt was stopped after fixture errors and live-API initialization stalled; it earns no complete-run credit. The final runner confines temporary data to the workspace and excludes that out-of-scope API test. Independent arithmetic is **PASS** in crosscheck.json (108 candidates, 1,350 Decimal monthly checks); full fresh reproduction is **{replay.get('status','PENDING')}** in replay_comparison.json, covering seven deterministic evidence files. Platform-specific strict-worker evidence is Windows only, not a substitute for Linux qualification. [preservation.json](../benchmarks/task723_v1/preservation.json) verifies unchanged HEAD/branch/index and zero changed preexisting tracked hashes. checksums.sha256 covers this report and all package files except itself. Development failure/repair is disclosed separately, not credited as a successful replay.

**Task 7.23 is complete as an isolated sizing/policy study, ready for owner review and an owner-performed commit; no staging, commit or push is performed.** Proposed protocol values remain unapproved. These artifacts do not authorize a network transition or close Milestone 7.

## 12. Remaining original Milestone 7 acceptance issues

Retain Task 7.22 R1–R5: (R1) mandatory metadata target remains FAIL and needs explicit owner resolution or evidence-preserving redesign; (R2) representative real-media/independent-text/code evidence is still missing, and this synthetic meme coverage does not substitute for actual traffic; (R3) original scope's acceptance of disabled versus active integration requires an explicit owner decision, with any active transition separately authorized; (R4) separate physical indexes/snapshots/backup/recovery and real transfer measurements remain incomplete despite full analytical pricing; (R5) resolve the no-expansion denominator explicitly—canonical descriptor/R versus identity passes in isolation, E≤M fails the retained counterexample, and R≤raw M is impossible for tiny valid records.

Network readiness separately still needs reviewed version activation, authority/history/finality completion as applicable, independent codec/native security and cross-platform resource qualification, decoder distribution and validator adoption, approved content/reviewer policy, capacity-qualified hosting and reconstruction/recovery drills. Future journal costs are not closed here. **Do not mark Milestone 7 complete or infer launch readiness from this study.**
'''
    REPORT.write_text(text,encoding='utf-8')
    print(REPORT)


if __name__=='__main__': main()
