"""R717 exact crypto and deliberately incomplete history; no protocol activation."""
from copy import deepcopy
from dataclasses import asdict
import importlib
import json
import subprocess

import pytest

from canonical_v3.primitives import CURVE_ORDER
from isolated_bft717j.wire import J
from verification.review717r import wire as w
from verification.review717s.fixtures import ROOT, load, pins, transcript
from verification.review717s.verify import (Result, record, json_record, verify_user, user_bindings,
    verify_message, verify_pv, verify_proof, verify_checkpoint, verify_clock)
from verification.review717s.history import audit_fixture_history
from verification.review717s.check import check_vectors, verify_row

D = load()
P = pins(D)
ROWS = {r['name']:r for r in D['records']}
H = D['history']


def row(name):
    return deepcopy(ROWS[name]['object'])


def user(obj, expected=None, kind='VOTE'):
    return verify_user(P, kind, w.pack(kind,obj), expected=user_bindings(kind,expected or row('vote-0-0')))


def coordinates(obj):
    return {k:obj[k] for k in ('height','parent','round','step','value','nil')}


def message(obj, **kw):
    return verify_message(P,w.pack('MESSAGE',obj),**(coordinates(row('precommit-3-0'))|kw))


def proof(obj=None, *, batch=None, height=3, round=0, pv=None):
    units=transcript(D)
    raw=w.pack('PROOF',obj) if obj is not None else units[height-1]['proof']
    return verify_proof(P,raw,batch_bytes=batch if batch is not None else units[height-1]['batch'],
                        height=height,parent=w.parse_body(units[height-1]['batch'])[0]['parent'],round=round,pv_bytes=pv)


def audit(units=None, **kwargs):
    args=dict(fixture_eligibility=H['fixture_eligibility'],actual_media_parent=tuple(H['actual_media_parent']))
    args.update(kwargs)
    return audit_fixture_history(P,transcript(D) if units is None else units,
        bytes.fromhex(H['checkpoint_hex']),bytes.fromhex(H['media_hex']),**args)


@pytest.mark.parametrize('name',list(ROWS))
def test_public_preimages_signatures_and_expected_outcomes(name):
    r=ROWS[name]
    if r['expected']=='REJECT':
        with pytest.raises(ValueError): verify_row(D,P,r)
    else:
        result=verify_row(D,P,r)
        if isinstance(result,Result):
            assert not result.complete_finalized_history and not result.agreement_execution_verified


def test_exact_retained_bytes_hashes_and_python_results():
    result=check_vectors()
    assert result['records']==75 and result['rejected']==10 and result['accepted']==65
    assert result['history']['verification']['outcome']=='INCOMPLETE_HISTORY'


@pytest.mark.parametrize('dimension',[0,1])
@pytest.mark.parametrize('choice',[0,1,2])
def test_both_dimensions_all_three_choices(dimension,choice):
    obj=row(f'choice-{dimension}-{choice}')
    result=user(obj,expected=obj)
    assert result.outcome=='VALID_USER_SIGNATURE_ONLY' and result.identity==ROWS['vote-0-0']['wallet']
    assert not result.test_membership_authenticated


@pytest.mark.parametrize('field,value',[
    ('original','de'*32),('creator','de'*20),('media_hash','de'*32),('base_hash','de'*32),
    ('media_height',1),('base_height',2),('deadline',1507),('nonce','de'*16),('choice',1),
    ('dimension',1),('sid','de'*32),('submission','de'*16),('network','foreign-network'),
    ('genesis','de'*32),('instance','de'*32),('validators','de'*32),('policy','de'*32)])
def test_modified_signed_payload_and_all_context_bindings(field,value):
    obj=row('vote-0-0');obj[field]=value
    with pytest.raises(ValueError): user(obj)


@pytest.mark.parametrize('field,value',[('protocol',2),('membership',1),('sequence',1),
    ('choice',3),('dimension',2),('deadline',True),('key','00'*33),('key','02'+'ff'*32),
    ('signature','00'*65),('signature','00'*66)])
def test_unsupported_versions_epoch_and_malformed_fields(field,value):
    obj=row('vote-0-0');obj[field]=value
    with pytest.raises(ValueError): user(obj)


def test_tamper_signature_high_s_bad_v_and_zero_scalars():
    obj=row('vote-0-0');raw=bytearray.fromhex(obj['signature']);raw[0]^=1
    with pytest.raises(ValueError): user(dict(obj,signature=raw.hex()))
    raw=bytes.fromhex(obj['signature'])
    high=(raw[:32]+(CURVE_ORDER-int.from_bytes(raw[32:64])).to_bytes(32,'big')+
          bytes([55-raw[64]]))
    with pytest.raises(ValueError,match='low_s'): user(dict(obj,signature=high.hex()))
    for bad in (raw[:64]+b'\x00',bytes(32)+raw[32:],raw[:32]+bytes(32)+raw[64:]):
        with pytest.raises(ValueError): user(dict(obj,signature=bad.hex()))


def test_creator_full_key_and_wallet_bound():
    op=row('open')
    assert user(op,expected=op,kind='OPEN').identity==op['creator']
    op['creator']='aa'*20
    with pytest.raises(ValueError): user(op,expected=op,kind='OPEN')


def test_unknown_duplicate_and_noncanonical_json_display_fields():
    obj=row('vote-0-0')
    good=J(obj)
    assert json_record('VOTE',good)==w.pack('VOTE',obj)
    for raw in (good[:-1]+b',"choice":0}',good+b'\n',b'\xef\xbb\xbf'+good,
                good.replace(b'"choice":0',b'"choice":0.0'),good.replace(b'"choice":0',b'"choice":true'),
                J(dict(obj,unknown=0)),good.replace(b'"choice":0',b'"choice":-0'),
                good.replace(b'"choice":0',b'"choice":1e0')):
        with pytest.raises(ValueError): json_record('VOTE',raw)
    nested=w.unpack('PROOF',transcript(D)[2]['proof']);nested['proposal']['unknown']=0
    with pytest.raises(ValueError): json_record('PROOF',J(nested))


@pytest.mark.parametrize('offset,value',[(64,1),(97,1),(98,2),(170,1)])
def test_noncanonical_binary_network_version_epoch(offset,value):
    raw=bytearray.fromhex(ROWS['vote-0-0']['hex']);raw[offset]=value
    with pytest.raises(ValueError): verify_user(P,'VOTE',bytes(raw),expected=user_bindings('VOTE',row('vote-0-0')))


@pytest.mark.parametrize('field,value',[
    ('network','foreign-network'),('genesis','ab'*32),('instance','ab'*32),('validators','ab'*32),
    ('membership',1),('protocol',2),('height',4),('round',1),('step',1),('value','ab'*32),('parent','ab'*32)])
def test_validator_context_phase_and_value_reject(field,value):
    obj=row('precommit-3-0');obj[field]=value
    with pytest.raises(ValueError): message(obj)


def test_unauthorized_identity_and_wrong_signature_purpose():
    for name in ('unauthorized-validator','personal-wrapped-validator','media-domain-validator'):
        with pytest.raises(ValueError): message(row(name))
    # The same bytes cannot be relabeled as a media-chain Signed envelope.
    from isolated_bft717j.wire import signed
    from verification.bft717k.fixtures import context as media_context
    for raw in (bytes.fromhex(ROWS['precommit-3-0']['hex']),
                J(dict(envelope=row('precommit-3-0'),signature='0x'+row('precommit-3-0')['signature'],
                       signature_scheme='personal_sign'))):
        with pytest.raises(ValueError): signed(raw,media_context())
    # Real frozen media signature has valid r/s/v but cannot authenticate journal bytes.
    from verification.bft717k.fixtures import VECTORS
    sig=VECTORS['cases']['precommit']['signed']['signature'][2:]
    with pytest.raises(ValueError): message(dict(row('precommit-3-0'),signature=sig))


def test_explicit_nil_prevote_precommit_and_nil_pv():
    for step in (1,2):
        obj=row(f'nil-step-{step}')
        assert message(obj,step=step,nil=1,value='00'*32).signatures_valid
    obj=row('nil-step-1')
    for change in (dict(value='ab'*32),dict(step=0)):
        with pytest.raises(ValueError): message(dict(obj,**change),**(dict(step=1,nil=1,value='00'*32)|change))
    args=coordinates(row('nil-step-1'));args.pop('step')
    assert verify_pv(P,bytes.fromhex(D['proofs']['nil_pv_hex']),**args).quorum_structure_valid


def test_quorum_structure_and_justified_later_round_not_execution():
    assert proof().outcome=='VALID_QUORUM_STRUCTURE_ONLY'
    rp=w.unpack('PROOF',bytes.fromhex(D['proofs']['round_one_hex']))
    with pytest.raises(ValueError,match='missing_prevote'): proof(rp,round=1)
    result=proof(rp,round=1,pv=bytes.fromhex(D['proofs']['pv_hex']))
    assert result.quorum_structure_valid and not result.agreement_execution_verified
    assert not result.complete_finalized_history and not result.physical_time_trusted


@pytest.mark.parametrize('control',['duplicate','contradictory','mixed','phase','nil','wrong-value','unsorted','missing-proposal'])
def test_quorum_negative_controls(control):
    obj=w.unpack('PROOF',transcript(D)[2]['proof'])
    if control=='duplicate': obj['precommits'][1]=obj['precommits'][0]
    elif control=='contradictory': obj['precommits'][1]=row('contradictory-precommit')
    elif control=='mixed': obj['precommits'][1]=row('round-one-precommit-1')
    elif control=='phase': obj['precommits'][1]=row('prevote-1')
    elif control=='nil': obj['precommits'][0]=row('nil-step-2')
    elif control=='wrong-value': obj['precommits'][0]=row('contradictory-precommit')
    elif control=='unsorted': obj['precommits'].reverse()
    else: del obj['proposal']
    with pytest.raises(ValueError): proof(obj)


def test_missing_batch_and_truncated_proof_never_quorum_success():
    u=transcript(D)[2];header,_=w.parse_body(u['batch'])
    with pytest.raises(ValueError,match='missing_proposal_bytes'):
        verify_proof(P,u['proof'],batch_bytes=None,height=3,parent=header['parent'],round=0)
    for raw in (u['proof'][383:],u['proof'][:-1],u['proof']+b'0'):
        with pytest.raises(ValueError):
            verify_proof(P,raw,batch_bytes=u['batch'],height=3,parent=header['parent'],round=0)


def test_checkpoint_exact_proof_and_batch_commitments():
    cp=deepcopy(H['checkpoint']);u=transcript(D)[3]
    assert verify_checkpoint(P,bytes.fromhex(H['checkpoint_hex']),batch_bytes=u['batch'],
                             proof_bytes=u['proof']).outcome=='VALID_CHECKPOINT_COMMITMENT_ONLY'
    for field in ('batch','proof'):
        with pytest.raises(ValueError): verify_checkpoint(P,w.pack('CHECKPOINT',dict(cp,**{field:'ab'*32})),
                                                          batch_bytes=u['batch'],proof_bytes=u['proof'])


def test_time_signature_context_no_physical_time_authority():
    h,_=w.parse_body(transcript(D)[2]['batch'])
    result=verify_clock(P,h)
    assert result.signatures_valid and not result.physical_time_trusted
    for change in (dict(height=4),dict(parent='ab'*32)):
        with pytest.raises(ValueError): verify_clock(P,dict(h,**change))
    h['clock']['samples'][0]['reading']+=1
    with pytest.raises(ValueError): verify_clock(P,h)


def test_correctly_signed_nonfinalized_vote_never_enters_tally():
    base=audit()
    pending=audit(pending_votes=[bytes.fromhex(H['pending_vote_hex'])])
    assert pending['pending_verified_not_counted']==1
    assert pending['fixture_count']==base['fixture_count']==10
    assert pending['fixture_fold']==base['fixture_fold']
    assert pending['fixture_originality']==base['fixture_originality']
    assert pending['verification'].outcome=='INCOMPLETE_HISTORY'
    assert not any(asdict(pending['verification'])[k] for k in
                   ('complete_finalized_history','agreement_execution_verified','physical_time_trusted'))


def test_missing_journal_evidence_and_wrong_media_parent():
    with pytest.raises(ValueError,match='INCOMPLETE_HISTORY'): audit(transcript(D)[:3])
    units=transcript(D);units[1]['batch']=None
    with pytest.raises(ValueError,match='INCOMPLETE_HISTORY'): audit(units)
    with pytest.raises(ValueError,match='media_reference'): audit(actual_media_parent=(1,'ab'*32))


def test_replaced_close_page_and_admission_bytes_break_authenticated_commitment():
    for height,kind in ((4,'CLOSE'),(3,'ADMISSION')):
        units=transcript(D);h,events=w.parse_body(units[height-1]['batch'])
        obj=next(o for k,o in events if k==kind)
        if kind=='CLOSE': obj['count']-=1
        else: obj['vote']['choice']=1
        units[height-1]['batch']=w.body(h,events)
        with pytest.raises(ValueError): audit(units)


def test_fully_signed_quorum_over_false_close_still_fails_replay():
    bad=D['negative_close']['unit']
    units=transcript(D)
    units[-1]=dict(batch=bytes.fromhex(bad['batch_hex']),proof=bytes.fromhex(bad['proof_hex']))
    h,_=w.parse_body(units[-1]['batch'])
    assert verify_proof(P,units[-1]['proof'],batch_bytes=units[-1]['batch'],height=4,
        parent=h['parent'],round=0).quorum_structure_valid
    with pytest.raises(ValueError,match='replaced_close_page_or_tally'): audit(units)


@pytest.mark.parametrize('kind',['OPEN','VOTE','MESSAGE','TIME_SAMPLE','PV','PROOF'])
def test_oversized_signed_records_refuse_before_crypto(kind,monkeypatch):
    import verification.review717s.verify as v
    def forbidden(*args): raise AssertionError('crypto must not run')
    monkeypatch.setattr(v,'recover',forbidden)
    with pytest.raises(ValueError,match='record_size'): record(kind,b'x'*(w.CAP+1))
    with pytest.raises(ValueError): json_record(kind,b' '*(8192+1))


def test_frozen_resource_limits_and_mixed_batch_work():
    assert w.CAP==262144
    from verification.review717s.verify import MAX_MEDIA
    assert MAX_MEDIA==3145728
    _,events=w.parse_body(transcript(D)[2]['batch'])
    assert len(events)==15 and w.preflight_work(events)['vote_checks']==10
    a=next(obj for k,obj in events if k=='ADMISSION')
    with pytest.raises(ValueError,match='work budget'): w.preflight_work([('ADMISSION',a)]*97)


def test_generator_cannot_be_imported_as_signer_and_no_active_imports():
    with pytest.raises(ImportError,match='cannot be imported'): importlib.import_module('verification.review717s.generate')
    paths=subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard','*.py'],cwd=ROOT,text=True).splitlines()
    excluded=('tests/','verification/','.venv/','temp/')
    for path in paths:
        if not path.startswith(excluded): assert 'review717s' not in (ROOT/path).read_text(encoding='utf-8')
    protected=['isolated_bft717j','isolated_bft717k','isolated_g2717m','canonical_v3','services',
               'verification/review717r','tests/fixtures/review717r_v1','tests/fixtures/bft717j']
    assert subprocess.check_output(['git','diff','HEAD','--',*protected],cwd=ROOT,text=True)==''


def test_independent_javascript_bytes_hashes_and_crypto(tmp_path):
    result=json.loads(subprocess.check_output(['node','verification/review717s/oracle.cjs'],cwd=ROOT,text=True,timeout=120))
    assert result['records']==75 and result['accepted']==65 and result['rejected']==10
    assert result['independent_encoder'] and result['full_key_recovery_and_ecdsa'] and result['fixture_fold']
    assert result['signed_false_close_detected']
    assert result['history_outcome']=='INCOMPLETE_HISTORY' and not result['agreement_execution']
    (tmp_path/'independent-oracle.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n',encoding='utf-8')
