"""Offline measurements; run from repo root with -m verification.bft717k.measure.

Only public insecure test scalars, synthetic contexts and disposable files.
Timing/allocations are local observations, not full-node throughput/economics.
"""
import argparse
from dataclasses import asdict
import json
import platform
from pathlib import Path
import shutil
import statistics
import subprocess
import tempfile
from time import perf_counter_ns
import tracemalloc
import xml.etree.ElementTree as ET

from canonical_v3.primitives import MAX_UINT
from isolated_bft717j.wire import J, sha
from isolated_bft717k.authority import save_cache
from isolated_bft717k.outcomes import Outcome
from isolated_bft717k.verifier import verify_quorum, verify_history, compare_quorums
from .fixtures import ROOT, VECTORS, context, authority, certificate, frozen_proof


def observe(a, raw, kind, iterations):
    samples = []
    for _ in range(iterations):
        start = perf_counter_ns()
        result = verify_quorum(a, raw, kind)
        samples.append((perf_counter_ns()-start)/1_000_000)
        assert result.outcome == Outcome.VALID_QUORUM
    tracemalloc.start()
    result = verify_quorum(a, raw, kind)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return dict(bytes=len(raw), digest=sha(raw), verification=asdict(result),
        milliseconds=dict(iterations=iterations, median=round(statistics.median(samples),6),
                          minimum=round(min(samples),6), maximum=round(max(samples),6)),
        peak_python_traced_bytes=peak)


def junit(path):
    tree = ET.parse(path).getroot()
    cases = list(tree.iter('testcase'))
    return dict(path=Path(path).relative_to(ROOT).as_posix(),
        tests=len(cases), failures=len(list(tree.iter('failure'))),
        errors=len(list(tree.iter('error'))), skipped=len(list(tree.iter('skipped'))),
        testcase_seconds=round(sum(float(c.get('time','0')) for c in cases),6),
        by_module={module:sum(c.get('classname') == module for c in cases)
                   for module in sorted({c.get('classname') for c in cases})},
        cases=[dict(name=c.get('name'), module=c.get('classname'),
                    passed=not any(c.find(k) is not None for k in ('failure','error','skipped')))
               for c in cases])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--iterations', type=int, default=15)
    parser.add_argument('--junit', type=Path, action='append', default=[])
    args = parser.parse_args()
    if not 1 <= args.iterations <= 100:
        parser.error('iterations must be 1..100')
    a = authority()
    widths = [('pv',(1,2,3),3583),('pv',(1,2,3,4),4581),
              ('q4',(1,2,3),4632),('q4',(1,2,3,4),5632)]
    maximum = context('task717i-test-'+'a'*50)
    max_authority = authority(maximum)
    observations = {}
    for name in ('pv','q4-x','q4-y','q4-x-four'):
        observations[name] = observe(a,frozen_proof(name),'pv' if name == 'pv' else 'q4',args.iterations)
    for kind,scalars,size in widths:
        raw = J(certificate(maximum,kind,scalars,height=MAX_UINT,round=2147483647,vr=2147483646))
        assert len(raw) == size
        observations[f'max-{kind}-{len(scalars)}'] = observe(max_authority,raw,kind,args.iterations)
    with tempfile.TemporaryDirectory(dir=ROOT/'temp',prefix='task717k-measure-') as folder:
        folder = Path(folder)
        cache = folder/'authority.json'
        save_cache(cache,a)
        cache_bytes = cache.stat().st_size
        shutil.copyfile(ROOT/'verification/bft717j/oracle.cjs',folder/'oracle.cjs')
        shutil.copyfile(ROOT/'tests/fixtures/bft717j/vectors.json',folder/'vectors.json')
        run = subprocess.run(['node',str(folder/'oracle.cjs')],capture_output=True,text=True,timeout=90,check=True)
        oracle = json.loads(run.stdout)
    reports = [junit(p.resolve()) for p in args.junit]
    assert all(r['failures'] == r['errors'] == r['skipped'] == 0 for r in reports)
    files = sorted(list((ROOT/'isolated_bft717k').glob('*.py')) +
                   list((ROOT/'verification/bft717k').glob('*.py')) +
                   [ROOT/'tests/test_milestone_7_task_7_17k_validator_authority.py',
                    ROOT/'tests/test_milestone_7_task_7_17j_durable_signer.py',
                    ROOT/'tests/fixtures/bft717j/vectors.json',ROOT/'isolated_bft717j/wire.py',
                    ROOT/'verification/bft717j/oracle.cjs'])
    output = dict(task='7.17K', scope='isolated local test pins, static N4/f1/q3/epoch0, crypto core only',
        branch=subprocess.run(['git','branch','--show-current'],capture_output=True,text=True,check=True).stdout.strip(),
        head=subprocess.run(['git','rev-parse','HEAD'],capture_output=True,text=True,check=True).stdout.strip(),
        python=platform.python_version(), platform=platform.platform(),
        genesis_authentication=asdict(a.genesis_authentication),
        historical_verification=asdict(verify_history(a,frozen_proof())),
        apparent_conflict=asdict(compare_quorums(a,frozen_proof(),frozen_proof('q4-y'))),
        manifest=dict(bytes=len(a.anchor.manifest_bytes),maximum_bytes=len(maximum.manifest_bytes),
                      commitment=a.context.C,agreement_bytes=len(a.anchor.agreement_bytes)),
        cache=dict(file_bytes=cache_bytes,database_bytes=0,authority='none; disposable cache rechecked against independent pins'),
        observations=observations, independent_frozen_javascript_oracle=oracle,
        regressions=reports,
        source_sha256={p.relative_to(ROOT).as_posix():sha(p.read_bytes()) for p in files},
        limitations=['No G2 identity/serialization/release authentication',
            'No authenticated application block/parent or finalized prefix',
            'No complete agreement execution or safety proof',
            'Timing includes fixture context revalidation/parsing/signature recovery; no network/storage in verifier',
            'Tracemalloc reports Python allocations, not process RSS or all native crypto memory',
            'Signature_checks is entry authentication attempts; valid fixtures perform exactly one recovery per entry',
            'Cache file size excludes filesystem allocation; no authority database exists',
            'Not full-node throughput, multi-host performance or public-testnet economics'])
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(output,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(output=str(args.output),manifest=output['manifest'],cache=output['cache'],
        observations={k:dict(bytes=v['bytes'],checks=v['verification']['signature_checks'],
            median_ms=v['milliseconds']['median'],peak_python_bytes=v['peak_python_traced_bytes'])
            for k,v in observations.items()},
        tests=[{k:v for k,v in r.items() if k != 'cases'} for r in reports]),indent=2))


if __name__ == '__main__':
    main()
