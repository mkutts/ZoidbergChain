"""Compare a fresh run with reference evidence, excluding observational timings.

Same encoder/SQLite environment required. HTTP Host's ephemeral-port digit count
can change actual request headers; application bodies must still match exactly.
"""
import argparse
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent


def read(base,name):
    return json.loads((base/name).read_bytes())


def compare(candidate):
    checks=[]
    assert read(HERE,'workloads.json')==read(candidate,'workloads.json')
    assert read(HERE,'corpus_hashes.json')==read(candidate,'corpus_hashes.json')
    checks.append('Exact source/accepted/encoded/canonical lengths, hashes, membership and exclusions')
    a=read(HERE,'sqlite.json')['populations'];b=read(candidate,'sqlite.json')['populations']
    for name in a:
        for variant in ('full','no_secondary','minimal'):
            assert a[name][variant]['observations']==b[name][variant]['observations'],(name,variant)
            assert a[name][variant]['constraints']==b[name][variant]['constraints']
            assert a[name][variant]['index_entries']==b[name][variant]['index_entries']
        assert a[name]['secondary_pages']==b[name]['secondary_pages']
        assert a[name]['file_differences']==b[name]['file_differences']
    checks.append('Exact SQLite file/page/freelist/allocation, constraints, index entries and index accounting')
    a=read(HERE,'backup_recovery.json')['populations'];b=read(candidate,'backup_recovery.json')['populations']
    for name in a:
        for key in ('source','snapshot','backup','recovery','verification','snapshot_ratio','backup_ratio',
                    'retained_four_backups_bytes','peak_including_live_source_bytes'):
            assert a[name][key]==b[name][key],(name,key)
    checks.append('Exact full-copy snapshot/backup/restore bytes, workspace and fresh-process commitments')
    a=read(HERE,'transfer.json')['exchanges'];b=read(candidate,'transfer.json')['exchanges']
    assert len(a)==len(b)
    keys=('label','method','target','blocks','canonical_payload_bytes','duplicated_certificate_value_bytes',
          'request_body_bytes','response_body_bytes','application_framing_bytes','response_http_framing_bytes',
          'request_body_sha256','response_body_sha256','peer_auth_header_bytes','content_encoding','transfer_encoding')
    header_deltas=[]
    for x,y in zip(a,b,strict=True):
        for key in keys:
            assert x[key]==y[key],(x['label'],key)
        delta=y['request_http_framing_bytes']-x['request_http_framing_bytes']
        assert abs(delta)<=2,delta
        assert y['http_stream_bytes']-x['http_stream_bytes']==delta
        header_deltas.append(delta)
    checks.append('Exact transfer application bodies/checksums and response/auth framing; ephemeral Host port request-header delta <=2 octets explicitly allowed')
    return dict(version=1,status='PASS',checks=checks,request_header_deltas=sorted(set(header_deltas)),
        excluded=['Wall-clock timings, SQL retrieval timings, environment scratch path/ephemeral port; not performance guarantees',
                  'Projected bills may differ by the explicitly allowed request-header port octets; economic arithmetic is tested independently'])


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('candidate',type=Path);args=ap.parse_args()
    print(json.dumps(compare(args.candidate.resolve()),indent=2))
