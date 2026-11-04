"""Reproducible bounded searches, adverse schedules and unsafe counterexamples."""
from __future__ import annotations

from collections import deque
from dataclasses import replace
from itertools import combinations
import json
from pathlib import Path

from .model import (A, C, CONTEXT, G, N, Batch, Rejected, State, apply, batch_for,
                    certificate_for, digest, fingerprint, media_candidate, open_event,
                    replay, result, sources, step, tally, validate_media, vote_event)
from .oracle import accepted, counts
from .workload import report as workload_report

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT/'tests/fixtures/review717p_v1/cases.json'


def expect_rejected(call, outcome='INVALID'):
    try:
        call()
    except Rejected as e:
        assert e.outcome == outcome, str(e)
        return dict(outcome=e.outcome, reason=e.reason)
    raise AssertionError('unsafe success')


def initial(count=6, window=3):
    return State(window=window, statuses={f'r{i}': 'established' if i == 0 else 'probationary' for i in range(count)})


def opened(window=3):
    return step(initial(window=window), open_event(window=window))


def passing(window=3):
    s = opened(window)
    s = step(s, *(vote_event(s, f'r{i}', dimension=d) for d in ('originality', 'admissibility') for i in range(5)))
    while s.height < s.sessions['s'].close:
        s = step(s)
    assert s.sessions['s'].closed['outcome'] == 'PASS'
    return s


def search(window=3, max_states=30000):
    base = initial(2, window)
    first = batch_for(base, (open_event(window=window),))
    history = ((first, certificate_for(first)),)
    start = apply(base, *history[0], sources(first))
    alphabet = [vote_event(start, 'r0'), vote_event(start, 'r0', choice='not_original'),
                vote_event(start, 'r0', nonce='variant'),
                vote_event(start, 'r1', choice='unsure'),
                vote_event(start, 'r1', dimension='admissibility'),
                vote_event(start, network='foreign'), vote_event(start, genesis='foreign'),
                vote_event(start, session='foreign'), vote_event(start, dimension='foreign', choice='original'),
                vote_event(start, authenticated=False)]
    queue = deque([(start, history)])
    states = 1
    attempts = transitions = rejects = terminals = checks = 0
    # Full ordered histories remain distinct; no unsound state quotient.
    while queue:
        state, h = queue.popleft()
        inventory = frozenset(x for b, _ in h for x in sources(b))
        # Independent node receives sources in reverse order before replay.
        other = replay(base, h, frozenset(reversed(sorted(inventory))), checkpoint=(state.height, state.tip))
        assert fingerprint(state) == fingerprint(other)
        rows, charges = accepted(base.statuses, [b for b, _ in h], N, G)
        assert state.charges == charges
        for sid, s in state.sessions.items():
            assert s.admitted == rows[sid]
            assert all(s.opened < r['position'][0] < s.close for r in s.admitted)
            assert len({(r['vote']['dimension'], r['vote']['reviewer']) for r in s.admitted}) == len(s.admitted)
            for d in ('originality', 'admissibility'):
                assert tally(s.admitted, d) == counts(rows[sid], d)
            if s.closed:
                assert s.closed == result(s)
        checks += 1
        if state.height == 1+window:
            terminals += 1
            continue
        for event in [None]+alphabet:
            attempts += 1
            b = batch_for(state, () if event is None else (event,))
            c = certificate_for(b)
            try:
                child = apply(state, b, c, sources(b))
            except Rejected as e:
                assert e.outcome == 'INVALID' and event and not event['vote']['authenticated']
                rejects += 1
                continue
            transitions += 1
            states += 1
            assert states <= max_states, 'search truncated: raise configured bound explicitly'
            queue.append((child, h+((b, c),)))
    return dict(window=window, max_height=1+window, reviewers=2, sessions=1,
                nodes_replaying=2, dimensions=2, max_optional_events_batch=1,
                input_alphabet=len(alphabet), empty_tick_option=True, states=states,
                transitions=transitions, attempted_transitions=attempts,
                invalid_transition_rejections=rejects, terminal_states=terminals,
                invariant_checks=checks, state_limit=max_states, truncated=False,
                boundary='configured finite histories through mandatory closing height; no fairness/liveness proof',
                unique_prefix_assumed=True, cryptography_assumed=True)


def delivery_search():
    """All delivery orders for three gossip votes to two replicas, plus commit.

    The finalized subset may include any proposer-seen messages, or none. Local
    queues and custody receipts never enter tally authority. Other validators'
    full source acquisition at certification is an explicit abstraction.
    """
    base = opened()
    votes = [vote_event(base, 'r0'), vote_event(base, 'r1', choice='not_original'),
             vote_event(base, 'r2', choice='unsure')]
    queue, seen = deque([(0, 0)]), {(0, 0)}
    deliveries = commits = 0
    while queue:
        masks = queue.popleft()
        for node in range(2):
            for bit in range(3):
                if not masks[node] & (1 << bit):
                    child = list(masks)
                    child[node] |= 1 << bit
                    child = tuple(child)
                    deliveries += 1
                    if child not in seen:
                        queue.append(child)
                        seen.add(child)
        available = [i for i in range(3) if masks[0] & (1 << i)]
        for n in range(len(available)+1):
            for subset in combinations(available, n):
                b = batch_for(base, tuple(votes[i] for i in subset))
                c = certificate_for(b)
                left = apply(base, b, c, sources(b))
                right = apply(base, b, c, frozenset(reversed(sorted(sources(b)))))
                assert fingerprint(left) == fingerprint(right)
                assert len(left.sessions['s'].admitted) == len(subset)
                commits += 1
    return dict(gossip_states=len(seen), delivery_transitions=deliveries,
                terminal_finalization_transitions=commits, terminal_worlds=commits,
                total_states=len(seen)+commits, total_transitions=deliveries+commits,
                messages=3, recipients=2, delivery_mask_bits=6, truncated=False,
                permutations_merged_only_at_identical_delivery_masks=True)


def scenarios():
    out = []
    def record(name, outcome, **details):
        out.append(dict(name=name, outcome=outcome, **details))

    s = opened(256)
    s = step(s, vote_event(s, choice='not_original'))
    for _ in range(254):
        s = step(s)
    assert s.height == 256 and s.sessions['s'].closed is None
    s = step(s, vote_event(s, 'r1'))
    assert s.height == 257 and len(s.sessions['s'].admitted) == 1
    assert s.observations[-1][-1] == 'LATE'
    record('W256_boundary_and_negative_preserved', 'PASS', open_height=1, last_vote_height=256,
           close_height=257, interior_heights=255, boundary_vote='LATE')

    s = opened()
    s = step(s, vote_event(s, 'r0'))
    s = step(s, vote_event(s, 'r0', nonce='same-choice'), vote_event(s, 'r0', choice='not_original'))
    assert [r[-1] for r in s.observations] == ['ADMIT', 'DUPLICATE', 'CONFLICT']
    assert len(s.charges) == 1 and len(s.sessions['s'].conflicts) == 1
    record('duplicate_and_equivocation_first_finalized_choice', 'PASS')

    s = opened()
    b = batch_for(s, (vote_event(s),))
    record('crash_before_evidence_persistence', 'INCOMPLETE_HISTORY', safe=
           expect_rejected(lambda: apply(s, b, certificate_for(b), frozenset()), 'INCOMPLETE_HISTORY'))
    after = apply(s, b, certificate_for(b), sources(b))
    assert fingerprint(after) == fingerprint(apply(s, b, certificate_for(b), sources(b)))
    record('intact_restart_full_durable_evidence', 'PASS', boundary='in-memory crash abstraction; no physical durability claim')

    history = []
    state = initial()
    for events in [(open_event(),), (), (), ()]:
        b = batch_for(state, events)
        c = certificate_for(b)
        history.append((b, c))
        state = apply(state, b, c, sources(b))
    ev = frozenset(x for b, _ in history for x in sources(b))
    record('recovering_node_missing_segment', 'INCOMPLETE_HISTORY', safe=expect_rejected(
        lambda: replay(initial(), history[:1]+history[2:], ev), 'INCOMPLETE_HISTORY'))
    for i, (b, _) in enumerate(history):
        for source in sources(b):
            expect_rejected(lambda: replay(initial(), history, ev-{source}), 'INCOMPLETE_HISTORY')
    record('delete_each_OPEN_CLOSE_source', 'INCOMPLETE_HISTORY')

    s = opened()
    candidates = (vote_event(s),)
    b = batch_for(s, candidates)
    bad = replace(certificate_for(b), context=(N, G, C, A, 'media', 0))
    record('wrong_stream_checkpoint', 'INVALID', safe=expect_rejected(lambda: apply(s, b, bad, sources(b))))
    record('journal_checkpoint_ahead_of_replay', 'INCOMPLETE_HISTORY', safe=expect_rejected(
        lambda: replay(initial(), [], frozenset(), checkpoint=(4, 'claimed-tip')), 'INCOMPLETE_HISTORY'))

    s = opened()
    candidate = media_candidate(s)
    record('media_while_session_open', 'INVALID', safe=expect_rejected(lambda: validate_media(s, candidate, local_media=s.media)))
    s = passing()
    mx, my = media_candidate(s), media_candidate(s, name='media-y')
    assert validate_media(s, mx, local_media=s.media) == 'PASS'
    assert validate_media(s, my, local_media=s.media) == 'PASS'
    # Competing candidates are both provisionally valid; media BFT must choose
    # one. Its unique finalized choice is assumed, never simulated by q votes.
    after = step(s, dict(kind='ANCHOR', media=mx))
    record('two_media_candidates_same_review', 'PASS', first='candidate-valid', second='candidate-valid',
           finalized_choice='trusted media BFT abstraction', later=expect_rejected(
               lambda: validate_media(after, my, local_media=after.media)))
    record('checkpoint_ahead_of_local_media', 'INCOMPLETE_HISTORY', safe=expect_rejected(
        lambda: validate_media(after, my, local_media=(0, G)), 'INCOMPLETE_HISTORY'))
    record('duplicate_media_anchor', 'INVALID', safe=expect_rejected(lambda: step(after, dict(kind='ANCHOR', media=mx))))
    record('competing_original_sessions', 'INVALID', safe=expect_rejected(
        lambda: step(opened(), open_event('t', original='original-s'))))

    s = step(initial(), *(open_event(f's{i}', window=3) for i in range(16)))
    s = step(s)
    s = step(s)
    b = batch_for(s)
    assert len(b.events) == 16 and [e['result']['session'] for e in b.events] == sorted(s.sessions)
    s = apply(s, b, certificate_for(b), sources(b))
    assert all(x.closed['outcome'] == 'UNDECIDED' for x in s.sessions.values())
    record('sixteen_simultaneous_zero_vote_closes', 'PASS', closes=16)
    record('seventeenth_open', 'INVALID', safe=expect_rejected(
        lambda: step(initial(), *(open_event(f's{i}') for i in range(17)))))

    s = step(initial(), open_event('s'), open_event('t'))
    s.charges.update({('r1', f'old{i}'): 0 for i in range(4)})  # explicit prehistory fixture
    s = step(s, vote_event(s, 'r1'), vote_event(s, 'r1', sid='t'),
             vote_event(s, 'r1', dimension='admissibility'))
    assert [x[-1] for x in s.observations] == ['ADMIT', 'QUOTA_EXHAUSTED', 'ADMIT']
    assert len(s.charges) == 5
    record('simultaneous_last_quota_and_paired_dimension', 'PASS', final_used=5)

    for status, cap in [('probationary', 5), ('established', 25)]:
        s = initial(window=40)
        s.statuses['r0'] = status
        # Sixteen OPENs/batch; long window keeps all sessions contemporaneous.
        for start in range(0, cap+1, 16):
            s = step(s, *(open_event(f'x{i}', window=40) for i in range(start, min(start+16, cap+1))))
        for i in range(cap+1):
            s = step(s, vote_event(s, 'r0', sid=f'x{i}', choice='unsure'))
        assert len(s.charges) == cap and s.observations[-1][-1] == 'QUOTA_EXHAUSTED'
        for _ in range(100):
            s = step(s)
        assert s.media == (0, G) and len(s.charges) == cap
        record('idle_media_exhaustion_'+status, 'LACK_OF_PROGRESS', cap=cap, journal_height=s.height,
               closed_reviews_keep_charges=True)

    s = opened()
    s = step(s, dict(kind='STATUS', reviewer='r1', status='established', authenticated_history=True),
             vote_event(s, 'r1'))
    assert s.sessions['s'].admitted[0]['status'] == 'probationary'
    s = step(s, dict(kind='PENALTY', reviewer='r0', end_epoch=3, authenticated_proof=True), vote_event(s))
    assert s.observations[-1][-1] == 'PENALIZED'
    record('snapshot_promotion_and_live_prospective_penalty', 'PASS')

    s = passing()
    earlier = s.sessions['s'].closed
    s = step(s, dict(kind='PENALTY', reviewer='r0', end_epoch=3, authenticated_proof=True))
    assert s.sessions['s'].closed == earlier
    record('post_close_penalty_no_rewrite', 'PASS')

    # Explicit abstract BFT scheduling facts. Threshold availability necessary,
    # not sufficient to decide: no new consensus is implemented here.
    for online, outcome in [((0, 1), 'LACK_OF_PROGRESS'), ((0, 1, 2), 'CONDITIONAL_PROGRESS')]:
        assert (len(online) >= 3) == (outcome == 'CONDITIONAL_PROGRESS')
        record('partition_'+str(len(online)), outcome, online=list(online),
               assumptions='eventual synchrony, complete inputs, fair proposer service, reviewed BFT engine')
    s = opened()
    # Faulty proposer serves no negative; next proposer includes it at h3.
    s = step(s)
    s = step(s, vote_event(s, choice='not_original'))
    s = step(s)
    assert s.sessions['s'].closed['dimensions']['originality']['negative'] == 1
    record('rotation_recovers_censored_negative_before_K', 'PASS', proposer_rounds=[0, 1],
           semantics='chosen schedule, not bounded inclusion guarantee')
    s = opened()
    for _ in range(3):
        s = step(s)
    s = step(s, vote_event(s, choice='not_original'))
    assert not s.sessions['s'].admitted and s.observations[-1][-1] == 'LATE'
    record('receipt_and_permanent_censorship_past_K', 'CENSORSHIP', receipt='custody only', admitted=0)
    return out


def custody():
    # Validator 3 is Byzantine. Correct attestations mean all complete source
    # bytes validated and durably persisted BEFORE signing, including parents.
    cases = []
    for signers in combinations(range(4), 3):
        honest = set(signers)-{3}
        assert len(honest) >= 2
        for count in range(len(honest)+1):
            for failed in combinations(sorted(honest), count):
                surviving = honest-set(failed)
                cases.append(dict(signers=list(signers), honest_at_certification=len(honest),
                    permanent_losses=list(failed), honest_sources_remaining=len(surviving),
                    recovering_node='AVAILABLE_IF_REACHABLE' if surviving else 'INCOMPLETE_HISTORY'))
    failures = [
        dict(name='sign_before_complete_store', honest_durable=0, outcome='UNSUPPORTED_CUSTODY_CLAIM'),
        dict(name='honest_crash_intact_disk', honest_durable=2, online=0, outcome='TEMPORARY_UNAVAILABILITY'),
        dict(name='restart_correct_disk', honest_durable=2, online=2, outcome='RECOVERABLE'),
        dict(name='permanent_disk_loss_both', honest_durable=0, outcome='INCOMPLETE_HISTORY'),
        dict(name='corrupt_archive_hash_mismatch', outcome='INVALID_SOURCE_BYTES'),
        dict(name='selective_withholding', outcome='INCOMPLETE_HISTORY_UNTIL_OTHER_SOURCE'),
        dict(name='pruning_without_handoff', outcome='INCOMPLETE_HISTORY'),
        dict(name='retirement_without_handoff', outcome='INCOMPLETE_HISTORY'),
        dict(name='new_node_only_has_root', outcome='INCOMPLETE_HISTORY'),
        dict(name='independent_archive_loss_after_validator_loss', outcome='INCOMPLETE_HISTORY')]
    return dict(quorum_subsets=4, failure_subsets=len(cases), cases=cases, failure_scenarios=failures,
                limitation='set-theoretic custody model; no disk fault injection or permanent online guarantee')


def negative_controls():
    traces = []
    def add(name, trace, expected, weakened):
        assert expected != weakened, name
        traces.append(dict(name=name, trace=trace, expected=expected, weakened=weakened, detected=True))
    # Concrete modified evaluation rules, not just descriptions of hypothetical bugs.
    s = opened()
    p, n = vote_event(s), vote_event(s, 'r1', choice='not_original')
    queues = [[p], [p, n]]
    add('node_local_cutoff', ['deliver positive to A,B', 'delay negative to A', 'close each local queue'],
        [2, 2], [len(q) for q in queues])
    add('unfinalized_gossip', ['receive unsigned-position vote', 'no finalized VOTE'], 0, len(queues[0]))
    rows = [dict(vote=dict(reviewer=f'r{i}', dimension='originality',
                          choice='original' if i < 5 else 'not_original'), status='established') for i in range(8)]
    add('producer_positive_subset', ['finalize 5 positive and 3 negative', 'producer removes negative sources'],
        tally(rows, 'originality')['outcome'], tally(rows[:5], 'originality')['outcome'])
    add('duplicate_inflation', ['admit r0', 'relay exact vote five times'], 1, len([p]*5))
    b = batch_for(s, (p,))
    safe = expect_rejected(lambda: apply(s, b, certificate_for(b), frozenset()), 'INCOMPLETE_HISTORY')
    add('missing_evidence_accepted', ['verify certificate', 'delete VOTE body', 'unsafe skips inventory check'],
        safe['outcome'], 'PASS')
    add('receipt_is_admission', ['local custody receipt', 'proposer withholds vote', 'CLOSE no VOTEs'], 0, len([p]))
    s = step(step(opened()))
    b = batch_for(s, omit_close=True)
    safe = expect_rejected(lambda: apply(s, b, certificate_for(b), sources(b)))
    # Unsafe variant merely advances a blank batch, so leaves due session open.
    unsafe = replace(s, height=b.height, tip=b.value)
    add('CLOSE_omission', ['OPEN h1 K4', 'ticks h2,h3', 'blank h4'], safe['outcome'],
        'ACCEPTED_OPEN' if unsafe.sessions['s'].closed is None else 'CLOSED')
    good = batch_for(opened())
    foreign = replace(certificate_for(good), context=('foreign', G, C, A, 'review-journal', 0), authenticated=False)
    safe = expect_rejected(lambda: apply(opened(), good, foreign, sources(good)))
    # Weakened adapter substitutes a self-asserted local context/auth bit.
    coerced = replace(foreign, context=CONTEXT, authenticated=True)
    unsafe = apply(opened(), good, coerced, sources(good))
    add('unauthenticated_checkpoint_substitution', ['foreign certificate', 'unsafe overwrites authority flags'],
        safe['outcome'], 'ACCEPTED_H'+str(unsafe.height))
    return traces


def fixture_results():
    fixtures = json.loads(FIXTURES.read_text(encoding='utf-8'))
    outputs = []
    for case in fixtures['tally_cases']:
        p, n, u, e = case['p'], case['n'], case['u'], case['e']
        rows = [dict(vote=dict(reviewer=f'r{i}', dimension='originality', choice=c),
                     status='established' if i < e else 'probationary')
                for i, c in enumerate(['original']*p+['not_original']*n+['unsure']*u)]
        actual = tally(rows, 'originality')
        assert actual == counts(rows, 'originality')
        assert actual['outcome'] == case['expected']
        outputs.append(dict(name=case['name'], actual=actual, expected=case['expected']))
    return outputs


def run():
    return dict(task='7.17P', authority='trusted unique authenticated finalized journal abstraction',
                production_ready=False, searches=[search(3), search(4)],
                delivery_search=delivery_search(), fixtures=fixture_results(),
                scenarios=scenarios(), custody=custody(), negative_controls=negative_controls(),
                workload=workload_report())


def main():
    target = ROOT/'verification/review717p/results.json'
    results = run()
    target.write_text(json.dumps(results, indent=2, sort_keys=True)+'\n', encoding='utf-8')
    traces = ROOT/'verification/review717p/negative-control-traces.json'
    traces.write_text(json.dumps(results['negative_controls'], indent=2, sort_keys=True)+'\n', encoding='utf-8')
    print(json.dumps(dict(searches=results['searches'], delivery=results['delivery_search'],
                         scenarios=len(results['scenarios']), negative_controls=len(results['negative_controls']),
                         output=str(target)), indent=2))


if __name__ == '__main__':
    main()
