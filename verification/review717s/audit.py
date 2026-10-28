"""Constrained S delivery audit. Read-only Git, no staging or protocol actions."""
import ast
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

from .fixtures import ROOT, load

HEAD='afdffe52a32f955d35a5daa7872ee4cbc1748bf0'
BRANCH='Compression-State-Bloat-and-Node-Economics'
R='docs/milestone-7-review-journal-wire-and-closure-contract.md'
REPORT='docs/milestone-7-review-journal-cryptographic-verification.md'
SUITES=[('temp/task717s-focused-final.xml',154),('temp/task717s-regression.xml',753)]


def git(*args):
    return subprocess.check_output(['git',*args],cwd=ROOT,text=True).strip()


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def main():
    assert git('rev-parse','HEAD')==HEAD
    assert git('branch','--show-current')==BRANCH
    assert not git('diff','--cached','--name-only')
    assert git('diff','--name-only').splitlines()==[R]
    before=subprocess.check_output(['git','show','HEAD:'+R],cwd=ROOT).decode('utf-8').replace('\r\n','\n')
    now=(ROOT/R).read_text(encoding='utf-8')
    start=now.index('**Task 7.17S follow-up')
    end=now.index('\nR717 is ',start)
    assert now[:start]+now[end+1:]==before
    names=('__init__.py','verify.py','history.py','fixtures.py','check.py','generate.py',
           'oracle.cjs','measure.py','audit.py','resource-results.json','vector-results.json','validation.json')
    allowed={R,REPORT,'tests/test_milestone_7_task_7_17s_crypto.py','tests/fixtures/review717s_v1/vectors.json'}
    allowed.update('verification/review717s/'+name for name in names)
    output=ROOT/'verification/review717s/validation.json'
    if not output.exists(): output.write_text('{}\n',encoding='utf-8')
    actual=set(git('ls-files','--others','--exclude-standard').splitlines())|{R}
    assert actual==allowed,(actual-allowed,allowed-actual)
    paths=[ROOT/p for p in sorted(allowed)]
    for path in paths:
        raw=path.read_bytes()
        assert raw.endswith(b'\n') and not raw.startswith(b'\xef\xbb\xbf'),path
        raw.decode('utf-8')
        assert all(line==line.rstrip(b' \t') for line in raw.splitlines()),path
        if path.suffix=='.py': ast.parse(raw,filename=str(path))
    for doc in (REPORT,R):
        content=(ROOT/doc).read_text(encoding='utf-8')
        assert content.count('```')%2==0
        for target in re.findall(r'\]\(([^)]+)\)',content):
            if '://' not in target: assert ((ROOT/doc).parent/target.split('#')[0]).exists(),target
    results=[]
    all_cases=[]
    for name,expected in SUITES:
        source=ROOT/name
        doc=ET.parse(source).getroot()
        counts,modules=Counter(),Counter()
        inventory=[]
        for case in doc.iter('testcase'):
            outcome=next((x for x in ('failure','error','skipped') if case.find(x) is not None),'passed')
            counts[outcome]+=1
            modules[case.attrib['classname']]+=1
            inventory.append(case.attrib['classname']+'::'+case.attrib['name'])
        assert counts['passed']==len(inventory)==expected and len(counts)==1
        results.append(dict(junit=name,sha256=digest(source),total=expected,outcomes=dict(counts),
            modules=dict(modules),case_inventory=inventory,
            inventory_sha256=sha256('\n'.join(inventory).encode()).hexdigest(),
            elapsed_seconds=sum(float(s.get('time','0')) for s in doc.iter('testsuite'))))
        all_cases+=inventory
    # Each requested negative family has actual final focused test evidence.
    controls=[
        ('modified signed payload','test_modified_signed_payload'),
        ('modified choice','test_modified_signed_payload_and_all_context_bindings[choice'),
        ('wrong review dimension','test_modified_signed_payload_and_all_context_bindings[dimension'),
        ('wrong session','test_modified_signed_payload_and_all_context_bindings[sid'),
        ('wrong submission','test_modified_signed_payload_and_all_context_bindings[submission'),
        ('wrong network','test_validator_context_phase_and_value_reject[network'),
        ('wrong G2 genesis','test_validator_context_phase_and_value_reject[genesis'),
        ('wrong journal instance','test_validator_context_phase_and_value_reject[instance'),
        ('wrong signature purpose','test_unauthorized_identity_and_wrong_signature_purpose'),
        ('wrong validator epoch','test_validator_context_phase_and_value_reject[membership'),
        ('wrong validator-set commitment','test_validator_context_phase_and_value_reject[validators'),
        ('duplicate signer inflation','test_quorum_negative_controls[duplicate]'),
        ('mixed rounds','test_quorum_negative_controls[mixed]'),
        ('missing proposal bytes','test_missing_batch_and_truncated_proof'),
        ('missing journal evidence','test_missing_journal_evidence'),
        ('replaced CLOSE page','test_fully_signed_quorum_over_false_close'),
        ('wrong media parent','test_missing_journal_evidence_and_wrong_media_parent'),
        ('cross media/journal replay','test_unauthorized_identity_and_wrong_signature_purpose'),
        ('unknown fields','test_unknown_duplicate_and_noncanonical_json'),
        ('duplicate JSON keys or malformed canonical bytes','test_unknown_duplicate_and_noncanonical_json'),
        ('signed nonfinalized vote excluded','test_correctly_signed_nonfinalized_vote_never_enters_tally')]
    negative=[]
    for control,pattern in controls:
        matches=[c for c in results[0]['case_inventory'] if pattern in c]
        assert matches,(control,pattern)
        negative.append(dict(control=control,passed=True,cases=matches))
    oracle_files=list((ROOT/'temp/task717s-focused-final').rglob('independent-oracle.json'))
    assert len(oracle_files)==1
    oracle=json.loads(oracle_files[0].read_text(encoding='utf-8'))
    assert oracle['records']==75 and oracle['signed_false_close_detected']
    vectors=load()
    assert len(vectors['public_identities'])==12
    def no_secrets(value):
        if isinstance(value,dict):
            assert not {'private_key','secret_key','scalar','seed','mnemonic'} & value.keys()
            for v in value.values(): no_secrets(v)
        elif isinstance(value,list):
            for v in value:no_secrets(v)
    no_secrets(vectors)
    preserved=git('ls-files','isolated_bft717j','isolated_bft717k','isolated_g2717m',
        'verification/review717r','verification/review717q','verification/review717p',
        'tests/fixtures/bft717j','tests/fixtures/g2717m_v1','tests/fixtures/review717r_v1',
        'tests/fixtures/protocol_v1_golden_vectors.json').splitlines()
    assert not git('diff','HEAD','--',*preserved)
    resources=json.loads((ROOT/'verification/review717s/resource-results.json').read_text(encoding='utf-8'))
    vector_results=json.loads((ROOT/'verification/review717s/vector-results.json').read_text(encoding='utf-8'))
    assert vector_results['history']['fixture_fold']==vectors['history']['media']['fold']
    assert resources['sizes']['transcript_batches']==[len(bytes.fromhex(u['batch_hex'])) for u in vectors['history']['units']]
    result=dict(task='7.17S',classification='ISOLATED TEST ONLY; no production approval',
        branch=BRANCH,initial_head=HEAD,final_head=HEAD,
        initial_git_status='clean index and full worktree including untracked files',
        final_git_status=git('status','--porcelain=v1','--untracked-files=all').splitlines(),
        index_unchanged=True,commit_push_merge_performed=False,
        python=sys.version.split()[0],node=subprocess.check_output(['node','--version'],text=True).strip(),
        commands=dict(
            vectors=r'.\.venv\Scripts\python.exe -B -m verification.review717s.check',
            focused=r'.\.venv\Scripts\python.exe -B -m pytest tests/test_milestone_7_task_7_17s_crypto.py -q --tb=short --basetemp=temp/task717s-focused-final --junitxml=temp/task717s-focused-final.xml',
            regressions=r'.\.venv\Scripts\python.exe -B -m pytest tests/test_milestone_7_task_7_17r_wire_closure.py tests/test_milestone_7_task_7_17q_capacity_clock.py tests/test_milestone_7_task_7_17p_review_journal.py tests/test_milestone_7_task_7_17j_durable_signer.py tests/test_milestone_7_task_7_17k_validator_authority.py tests/test_milestone_7_task_7_17m_g2_genesis.py tests/test_protocol_v1_golden_vectors.py tests/test_milestone_7_task_7_10c_v3.py -q --tb=short --basetemp=temp/task717s-regression --junitxml=temp/task717s-regression.xml',
            regression_environment='TEMP and TMP point to workspace temp/task717s-runtime',
            measurements=r'.\.venv\Scripts\python.exe -B -m verification.review717s.measure',
            javascript='node verification/review717s/oracle.cjs (also invoked by final focused test)',
            audit=r'.\.venv\Scripts\python.exe -B -m verification.review717s.audit'),
        suites=results,total_passed=sum(r['total'] for r in results),failed=0,errors=0,skipped=0,timed_out=0,
        earlier_runs=[dict(junit='temp/task717s-focused.xml',passed=153,failed=0,
            status='superseded before adding signed false-CLOSE test; excluded from final total')],
        negative_controls=negative,independent_oracle=oracle,
        vector_outcomes=dict(records=vector_results['records'],accepted=vector_results['accepted'],rejected=vector_results['rejected']),
        history=vector_results['history'],
        guarantees=dict(A_signatures_and_bytes='VERIFIED_FOR_LISTED_CASES',
            B_membership='INDEPENDENT_LOCAL_TEST_PINS_ONLY',C_quorum_structure='VERIFIED_FOR_LISTED_CASES',
            D_complete_finalized_history=False,E_agreement_execution=False,physical_time_trusted=False),
        readiness=dict(isolated_crypto_package='READY_FOR_REVIEW_AND_OWNER_COMMIT',
            production_journal='BLOCKED',task717='BLOCKED',activation=False,next_task_started=False),
        exclusions=['whole repository suite','general R application engine','production policy validation',
            'trustworthy physical deadlines','independent BFT engine/refinement','multi-host network/custody campaign',
            'launch keys/genesis','production activation/deployment'],
        checks=['branch/HEAD preserved','empty index','only R notice tracked diff','closed allowed additions',
            'R historical report body preserved','historical fixtures and code unchanged','UTF-8/newlines/whitespace',
            'Python syntax','Markdown local links','final JUnit inventory','public fixture contains no private-key fields',
            'negative-family coverage','independent JS crypto','resource/vector identity consistency','git diff --check'],
        artifacts={p.relative_to(ROOT).as_posix():digest(p) for p in paths if p!=output},
        preserved_artifacts={p:digest(ROOT/p) for p in preserved})
    assert result['total_passed']==907
    subprocess.check_call(['git','diff','--check'],cwd=ROOT)
    output.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    print(json.dumps(dict(passed=result['total_passed'],negative_families=len(negative),
        oracle=oracle,files=len(allowed),scope='PASS'),indent=2))


if __name__=='__main__': main()
