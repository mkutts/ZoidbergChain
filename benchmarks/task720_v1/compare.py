"""Compare an independent replay; size/hash evidence is exact, timing is not."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent


def normalized(name, value):
    value=deepcopy(value)
    if name=='codecs.json':
        for row in value['rows']:
            for key in ('encode_ns','decode_ns','encode_ns_median','decode_ns_median'):
                del row[key]
        for categories in value['aggregates'].values():
            for summary in categories.values():
                for key in ('encode_ns_median','decode_ns_median'):
                    del summary['distributions'][key]
    if name=='records.json':
        for row in value['rows']+value['sensitivity_rows']:
            row.pop('worker_metrics')
            for trial in row.get('strict_source_roundtrips',[]):
                trial.pop('worker_metrics')
    return value


def main():
    replay=Path(sys.argv[1]).resolve()
    results={}
    for name in ('manifest.json','codecs.json','records.json','metrics.json','historical_audit.json','admission.json'):
        reference=(HERE/name).read_bytes(); fresh=(replay/name).read_bytes()
        results[name]=dict(exact_nontiming=normalized(name,json.loads(reference))==normalized(name,json.loads(fresh)),
            reference_sha256=hashlib.sha256(reference).hexdigest(),replay_sha256=hashlib.sha256(fresh).hexdigest())
    (replay/'comparison.json').write_text(json.dumps(results,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    print(json.dumps(results,indent=2))
    assert all(r['exact_nontiming'] for r in results.values())


if __name__=='__main__':
    main()
