"""Isolated application/feasibility checks. No sockets, keys or live state."""
from dataclasses import replace
import json
from pathlib import Path

import pytest

from verification.review717p import check
from verification.review717p.model import (
    G, Rejected, State, apply, batch_for, certificate_for, checkpoint_guard,
    digest, fingerprint, media_candidate, open_event, replay, sources, step,
    tally, validate_media, vote_event,
)
from verification.review717p.workload import calculate, report

ROOT = Path(__file__).resolve().parents[1]
RETAINED = json.loads((ROOT/'verification/review717p/results.json').read_text())


@pytest.mark.parametrize('window', [3, 4])
def test_bounded_exhaustive_search_reproduces(window):
    assert check.search(window) == RETAINED['searches'][window-3]


def test_adversarial_delivery_exploration_reproduces():
    assert check.delivery_search() == RETAINED['delivery_search']


def test_selected_adverse_schedules_reproduce():
    assert check.scenarios() == RETAINED['scenarios']


@pytest.mark.parametrize('case', RETAINED['fixtures'], ids=lambda c: c['name'])
def test_independently_authored_tally_fixtures(case):
    result = next(r for r in check.fixture_results() if r['name'] == case['name'])
    assert result == case


@pytest.mark.parametrize('name', [r['name'] for r in RETAINED['negative_controls']])
def test_unsafe_variant_has_counterexample(name):
    actual = next(r for r in check.negative_controls() if r['name'] == name)
    assert actual['detected'] and actual['expected'] != actual['weakened']
    assert actual == next(r for r in RETAINED['negative_controls'] if r['name'] == name)


@pytest.mark.parametrize('mutation', [
    {'context': ('foreign',)}, {'authenticated': False}, {'signers': (0, 1)},
    {'signers': (0, 0, 1)}, {'signers': (0, 1, 9)}, {'round': -1}, {'round': True},
    {'value': 'foreign'}, {'parent': 'foreign'}, {'height': 99},
    {'signers': (0, True, 2)},
])
def test_checkpoint_cannot_substitute_authority(mutation):
    s = check.opened()
    b = batch_for(s)
    with pytest.raises(Rejected, match='INVALID'):
        apply(s, b, replace(certificate_for(b), **mutation), sources(b))


@pytest.mark.parametrize('changes,reason', [
    ({'network': 'foreign'}, 'WRONG_CONTEXT'), ({'genesis': 'foreign'}, 'WRONG_CONTEXT'),
    ({'session': 'foreign'}, 'WRONG_SESSION'), ({'submission': 'foreign'}, 'WRONG_BINDING'),
    ({'original': 'foreign'}, 'WRONG_BINDING'), ({'creator': 'foreign'}, 'WRONG_BINDING'),
    ({'base_media': (5, 'foreign')}, 'WRONG_BINDING'),
    ({'base_journal': (5, 'foreign')}, 'WRONG_BINDING'), ({'close_height': 99}, 'WRONG_BINDING'),
    ({'dimension': 'wrong'}, 'WRONG_DIMENSION_OR_CHOICE'),
    ({'choice': 'admissible'}, 'WRONG_DIMENSION_OR_CHOICE'),
])
def test_signed_contexts_do_not_count(changes, reason):
    s = check.opened()
    event = vote_event(s)
    event['vote'].update(changes)
    s = step(s, event)
    assert s.observations[-1][-1] == reason and not s.charges
    assert not s.sessions['s'].admitted


def test_unauthenticated_vote_invalidates_batch_without_mutation():
    s = check.opened()
    before = fingerprint(s)
    with pytest.raises(Rejected, match='unauthenticated vote'):
        step(s, vote_event(s, authenticated=False))
    assert fingerprint(s) == before


def test_window_is_fixed_by_policy_not_proposer():
    with pytest.raises(Rejected, match='fixed policy window'):
        step(check.initial(), open_event(window=4))


@pytest.mark.parametrize('which', ['OPEN', 'VOTE', 'CLOSE'])
def test_source_loss_recovery_is_incomplete(which):
    base, s, h = check.initial(), check.initial(), []
    for events in [(open_event(),), 'vote', (), ()]:
        events = (vote_event(s),) if events == 'vote' else events
        b = batch_for(s, events)
        c = certificate_for(b)
        h.append((b, c))
        s = apply(s, b, c, sources(b))
    inventory = frozenset(x for b, _ in h for x in sources(b))
    missing = next(digest(e) for b, _ in h for e in b.events if e['kind'] == which)
    with pytest.raises(Rejected, match='INCOMPLETE_HISTORY'):
        replay(base, h, inventory-{missing})
    assert fingerprint(replay(base, h, inventory)) == fingerprint(s)


def test_corrupt_vote_bytes_fail_old_certificate():
    s = check.opened()
    e = vote_event(s)
    b = batch_for(s, (e,))
    cert = certificate_for(b)
    e['vote']['choice'] = 'not_original'
    with pytest.raises(Rejected, match='proof binding'):
        apply(s, b, cert, sources(b))


def test_finalized_sources_do_not_alias_mutable_experiment_inputs():
    s = check.opened()
    event = vote_event(s, choice='not_original')
    s = step(s, event)
    event['vote']['choice'] = 'original'
    assert s.sessions['s'].admitted[0]['vote']['choice'] == 'not_original'
    s = step(s)
    b = batch_for(s)
    after = apply(s, b, certificate_for(b), sources(b))
    b.events[0]['result']['count'] = 0
    assert after.sessions['s'].closed['count'] == 1


@pytest.mark.parametrize('variant', ['omit', 'reorder', 'alter', 'extra', 'early'])
def test_close_is_mandatory_exact_and_first(variant):
    s = check.opened()
    if variant != 'early':
        s = step(step(s))
    b = batch_for(s, (vote_event(s),))
    events = list(b.events)
    if variant == 'omit':
        events = events[1:]
    elif variant == 'reorder':
        events.reverse()
    elif variant == 'alter':
        events[0]['result']['count'] = 99
    elif variant == 'extra':
        events += events[:1]
    else:
        events.insert(0, dict(kind='CLOSE', result=dict(session='s')))
    b = replace(b, events=tuple(events))
    with pytest.raises(Rejected, match='INVALID'):
        apply(s, b, certificate_for(b), sources(b))


@pytest.mark.parametrize('changes', [
    {'context': ('foreign',)}, {'authenticated': False}, {'available': False},
    {'parent': 'foreign'}, {'original': 'foreign'}, {'close_source': (0, 'forged', 0)},
    {'result': {'outcome': 'PASS'}}, {'other_media_checks': False},
])
def test_media_cross_reference_requires_full_compatible_finality(changes):
    s = check.passing()
    m = {**media_candidate(s), **changes}
    with pytest.raises(Rejected):
        validate_media(s, m, local_media=s.media)


def test_five_media_anchors_reset_epoch_and_do_not_erase_charges():
    s = check.initial()
    for i in range(6):
        sid = f's{i}'
        s = step(s, open_event(sid))
        s = step(s, *(vote_event(s, f'r{j}', sid=sid, dimension=d)
                      for d in ('originality', 'admissibility') for j in range(5)))
        while s.height < s.sessions[sid].close:
            s = step(s)
        assert s.sessions[sid].closed['outcome'] == 'PASS'
        s = step(s, dict(kind='ANCHOR', media=media_candidate(s, sid, f'm{i}')))
    assert s.media[0] == 6
    assert s.charges[('r1', 'submission-s0')] == 0
    assert s.charges[('r1', 'submission-s5')] == 1
    assert len(s.charges) == 30


def test_quota_failure_close_has_no_refund():
    s = check.opened()
    s = step(s, *(vote_event(s, f'r{i}', choice='not_original') for i in range(5)))
    s = step(step(s))
    assert s.sessions['s'].closed['outcome'] == 'FAIL'
    assert len(s.charges) == 5


def test_delayed_undecided_retry_keeps_lifetime_charge():
    s = check.opened()
    s = step(s, vote_event(s, choice='unsure'))
    while s.height < 6:
        s = step(s)
    retry = open_event('retry', submission='submission-s', original='original-s', attempt=1)
    s = step(s, retry)  # first legal retry height K+W=7
    s = step(s, vote_event(s, sid='retry'))
    assert len(s.charges) == 1 and s.charges[('r0', 'submission-s')] == 0
    while s.height < 13:
        s = step(s)
    with pytest.raises(Rejected, match='retry limit'):
        step(s, open_event('retry2', submission='submission-s', original='original-s', attempt=1))


@pytest.mark.parametrize('kind', ['too_early', 'terminal_negative', 'usable_pass', 'identity_change'])
def test_retry_restrictions(kind):
    s = check.opened()
    if kind == 'terminal_negative':
        s = step(s, *(vote_event(s, f'r{i}', choice='not_original') for i in range(5)))
    elif kind == 'usable_pass':
        s = check.passing()
    while s.height < (4 if kind == 'too_early' else 6):
        s = step(s)
    retry = open_event('retry', submission='submission-s', original='original-s', attempt=1)
    if kind == 'identity_change':
        retry['original'] = 'different-original'
    with pytest.raises(Rejected):
        step(s, retry)


def test_media_anchor_makes_other_session_stale_without_rewrite():
    s = step(check.initial(), open_event('s'), open_event('t'))
    s = step(s, *(vote_event(s, f'r{i}', sid=sid, dimension=d)
                  for sid in ('s', 't') for d in ('originality', 'admissibility') for i in range(5)))
    s = step(step(s))
    m = media_candidate(s)
    s = step(s, dict(kind='ANCHOR', media=m))
    assert s.sessions['t'].closed['outcome'] == 'PASS'
    with pytest.raises(Rejected, match='stale media parent'):
        validate_media(s, media_candidate(s, 't'), local_media=s.media)


@pytest.mark.parametrize('candidate,auth,ancestry,error', [
    ((3, 'old'), True, True, 'INVALID'), ((4, 'fork'), True, True, 'CONFLICTING_FINALITY'),
    ((5, 'new'), False, True, 'INVALID'), ((5, 'new'), True, False, 'INCOMPLETE_HISTORY'),
])
def test_recovery_rollback_and_conflicting_checkpoint(candidate, auth, ancestry, error):
    with pytest.raises(Rejected, match=error):
        checkpoint_guard((4, 'retained'), candidate, authenticated=auth, ancestry_matches=ancestry)


def test_recovery_accepts_only_descendant_for_further_replay():
    assert checkpoint_guard((4, 'retained'), (5, 'new'), authenticated=True, ancestry_matches=True) == 'CONTINUE_REPLAY'


def test_custody_threshold_is_not_permanent_availability():
    actual = check.custody()
    assert actual == RETAINED['custody']
    assert all(c['honest_at_certification'] >= 2 for c in actual['cases'])
    assert any(c['honest_sources_remaining'] == 0 for c in actual['cases'])


def test_sizes_and_workload_arithmetic():
    w = report()
    assert w == RETAINED['workload']
    assert w['measurement']['payload_bytes'] == 1507
    assert w['measurement']['signed_vote_bytes'] == 1701
    assert w['measurement']['payload_sha256'] == '69213dedf3d2aed70609d6ca5ac093bb40a4d475f79662405d174b90e8b87740'
    assert w['binding']['remaining_after_binding_and_native'] == 243028
    a = calculate(votes_per_minute=1000)
    assert a['capacity_votes_minute'] == 288 and not a['stable']
    assert a['clear_backlog_minutes'] is None
    assert a['offered_vote_storage_three_year_bytes'] == 1000*1440*1095*1701
    assert calculate(votes_per_minute=100)['clear_backlog_minutes'] == 36000/188


def test_no_production_module_imports_verification_package():
    # All active tracked Python paths are inspected, not temporary/user files.
    import subprocess
    tracked = subprocess.check_output(['git', 'ls-files', '*.py'], cwd=ROOT, text=True).splitlines()
    for name in tracked:
        if name.startswith(('tests/', 'verification/')):
            continue
        assert 'verification.review717p' not in (ROOT/name).read_text(encoding='utf-8-sig')
