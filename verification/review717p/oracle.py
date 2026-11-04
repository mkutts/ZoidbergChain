"""Independent acceptance/accounting oracle for OPEN/VOTE/tick search alphabet.

Does not import model tally/admit/apply. Trusted journal/certification is outside
this oracle. Broader penalties/media scenarios use explicit expected assertions.
"""
from fractions import Fraction


def counts(rows, dimension):
    chosen = [r for r in rows if r['vote']['dimension'] == dimension]
    positive = 'original' if dimension == 'originality' else 'admissible'
    negative = 'not_original' if dimension == 'originality' else 'not_admissible'
    p = len([r for r in chosen if r['vote']['choice'] == positive])
    n = len([r for r in chosen if r['vote']['choice'] == negative])
    u = len(chosen)-p-n
    e = len([r for r in chosen if r['status'] == 'established'])
    q = len(chosen) >= 5 and e >= 1
    verdict = 'UNDECIDED'
    if q and p+n:
        verdict = 'PASS' if Fraction(p, p+n) >= Fraction(7, 10) else 'FAIL'
    return dict(positive=p, negative=n, unsure=u, established=e, total=len(chosen),
                decisive=p+n, quorum=q, outcome=verdict)


def accepted(initial_statuses, batches, network, genesis):
    sessions, charges = {}, {}
    for b in batches:
        for i, event in enumerate(b.events):
            if event['kind'] == 'OPEN':
                sessions[event['sid']] = dict(open=b.height, close=b.height+event['window'],
                    submission=event['submission'], original=event['original'], creator=event['creator'],
                    journal=(b.height-1, b.parent), rows=[], slots=set())
            elif event['kind'] == 'VOTE':
                v = event['vote']
                s = sessions.get(v['session'])
                if not s or not v['authenticated'] or (v['network'], v['genesis']) != (network, genesis):
                    continue
                if not s['open'] < b.height < s['close']:
                    continue
                if (v['submission'], v['original'], v['creator'], v['base_media'], v['base_journal'],
                    v['close_height']) != (s['submission'], s['original'], s['creator'], (0, genesis),
                                          s['journal'], s['close']):
                    continue
                d, w, c = v['dimension'], v['reviewer'], v['choice']
                choices = {'originality': {'original', 'not_original', 'unsure'},
                           'admissibility': {'admissible', 'not_admissible', 'unsure'}}
                if d not in choices or c not in choices[d] or (d, w) in s['slots']:
                    continue
                status = initial_statuses.get(w)
                if status not in {'probationary', 'established'} or w == s['creator']:
                    continue
                key = w, s['submission']
                cap = 25 if status == 'established' else 5
                if key not in charges and sum(a == w for a, _ in charges) >= cap:
                    continue
                charges[key] = 0
                s['slots'].add((d, w))
                s['rows'].append(dict(vote=v, status=status, position=(b.height, i)))
    return {sid: s['rows'] for sid, s in sessions.items()}, charges
