"""Offline reproducible evidence; traced Python memory is NOT process RSS."""
import argparse
import hashlib
import json
import platform
import statistics
import subprocess
import time
import tracemalloc
import xml.etree.ElementTree as ET
from pathlib import Path

from isolated_g2717m import TrustedGenesisPin, verify_bytes
from isolated_g2717m.verifier import GENESIS_LIMIT
from protocol_v1_genesis import canonical_public_testnet_v1_genesis_hash
from .fixtures import ROOT, VECTORS, base, encode, digest, wide


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--iterations',type=int,default=7)
    parser.add_argument('--junit',action='append',default=[])
    parser.add_argument('--output',default='verification/g2717m/verification-results.json')
    args = parser.parse_args()
    assert args.iterations > 0
    rows = []
    for name,e in [('published-L-G2',base()),('4096-allocations-128-reviewers-3-max-sources',wide())]:
        raw = encode(e)
        pin = TrustedGenesisPin(digest(e),e['network_id'],e['payload']['application'])
        result = verify_bytes(raw,trusted_pin=pin)
        times = []
        for _ in range(args.iterations):
            start = time.perf_counter_ns()
            result = verify_bytes(raw,trusted_pin=pin)
            times.append((time.perf_counter_ns()-start)/10**6)
        tracemalloc.start()
        result = verify_bytes(raw,trusted_pin=pin)
        _,peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        rows.append(dict(case=name,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),
            median_ms=statistics.median(times),iterations=args.iterations,
            peak_traced_python_bytes=peak,component_sizes=dict(result.component_sizes),
            outcome=result.outcome.value,complete_semantic_genesis_valid=False,
            production_consensus_authorized=False))
    pin = TrustedGenesisPin(VECTORS['objects']['G2']['sha256'],'task717i-test','task717i-test')
    for name,raw in [('exact-1MiB-non-envelope-string',b'"'+b'a'*(GENESIS_LIMIT-2)+b'"'),
            ('1MiB-plus-one',b' '*(GENESIS_LIMIT+1)),
            ('array-count-bomb',b'['+b'0,'*4096+b'0]'),
            ('nesting-bomb',b'['*33+b'0'+b']'*33)]:
        tracemalloc.start(); start = time.perf_counter_ns()
        result = verify_bytes(raw,trusted_pin=pin)
        elapsed = (time.perf_counter_ns()-start)/10**6
        _,peak = tracemalloc.get_traced_memory(); tracemalloc.stop()
        rows.append(dict(case=name,bytes=len(raw),outcome=result.outcome.value,detail=result.detail,
            observed_ms_with_tracing=elapsed,peak_traced_python_bytes=peak))
    oracle = subprocess.run(['node',str(ROOT/'verification/g2717m/oracle.cjs'),
        str(ROOT/'tests/fixtures/g2717m_v1/vectors.json')],capture_output=True,text=True,check=True)
    suites = []
    for filename in args.junit:
        tree = ET.parse(filename)
        suites.append(dict(source=filename,tests=[dict(name=c.get('name'),classname=c.get('classname'),
            status='failed' if c.find('failure') is not None or c.find('error') is not None
            else 'skipped' if c.find('skipped') is not None else 'passed')
            for c in tree.iter('testcase')],summary=[dict(s.attrib) for s in tree.iter('testsuite')]))
    report = dict(task='7.17M',status='TEST_ONLY_VALID_ENVELOPE_INCOMPLETE_POLICY',
        branch=subprocess.check_output(['git','branch','--show-current'],text=True).strip(),
        head=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        python=platform.python_version(),platform=platform.platform(),
        node=subprocess.check_output(['node','--version'],text=True).strip(),
        source_fixture_sha256=hashlib.sha256((ROOT/'tests/fixtures/g2717m_v1/vectors.json').read_bytes()).hexdigest(),
        golden_objects=12,negative_vector_inputs=10,independent_oracle=oracle.stdout.strip(),
        historical_v1_genesis=canonical_public_testnet_v1_genesis_hash(),measurements=rows,
        limitations=['Python traced allocations exclude native crypto/RSS and caller input buffers',
            'No full policy, history replay, production, deployment, or multi-host claim',
            'Exact 1MiB lexical input is structurally invalid; simultaneous component caps are tighter'],
        suites=suites)
    Path(args.output).write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(output=args.output,measurements=rows,
        tests=sum(len(s['tests']) for s in suites)),indent=2))


if __name__ == '__main__':
    main()
