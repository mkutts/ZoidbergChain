"""Pure review application model over a TRUSTED finalized BFT abstraction.

Authentication Boolean facts are supplied by the experiment, never cryptography.
Certificates are assertions of already-decided unique prefixes, not a consensus
algorithm. No signer, wire parser, database, clock, network or production imports.
OPEN source validity, qualification and penalty proofs are explicit oracle facts.
All hashes are model commitments, NOT proposed canonical production schemas.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, field
from hashlib import sha256
import json


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('ascii')


def digest(value):
    return sha256(canonical(value)).hexdigest()


N, G, C, A = 'task717p-symbolic', 'g-model', 'n4-f1-q3-model', 'journal-agreement-model'
CONTEXT = (N, G, C, A, 'review-journal', 0)
DIMENSIONS = ('originality', 'admissibility')
CHOICES = {'originality': ('original', 'not_original', 'unsure'),
           'admissibility': ('admissible', 'not_admissible', 'unsure')}


class Rejected(Exception):
    def __init__(self, outcome, reason):
        self.outcome, self.reason = outcome, reason
        super().__init__(f'{outcome}: {reason}')


def require(condition, reason, outcome='INVALID'):
    if not condition:
        raise Rejected(outcome, reason)


@dataclass(frozen=True)
class Vote:
    session: str
    reviewer: str
    dimension: str = 'originality'
    choice: str = 'original'
    network: str = N
    genesis: str = G
    submission: str = 'submission-s'
    original: str = 'original-s'
    creator: str = 'creator'
    base_media: tuple = (0, G)
    base_journal: tuple = (0, 'unused')
    close_height: int = 4
    nonce: str = '0'
    authenticated: bool = True


@dataclass
class Session:
    sid: str
    submission: str
    original: str
    creator: str
    opened: int
    close: int
    media: tuple
    journal: tuple
    # (reviewer, status) derived from trusted complete history at OPEN.
    eligibility: dict
    admitted: list = field(default_factory=list)
    conflicts: set = field(default_factory=set)
    closed: dict | None = None
    close_source: tuple | None = None
    attempt: int = 0


@dataclass
class State:
    window: int = 3
    height: int = 0
    tip: str = 'J0-model'
    media: tuple = (0, G)
    sessions: dict = field(default_factory=dict)
    charges: dict = field(default_factory=dict)  # (wallet,submission) -> epoch
    penalties: dict = field(default_factory=dict)  # wallet -> exclusive media epoch end
    statuses: dict = field(default_factory=dict)
    observations: list = field(default_factory=list)
    settled: dict = field(default_factory=dict)  # original -> media hash


@dataclass(frozen=True)
class Batch:
    height: int
    parent: str
    events: tuple

    @property
    def value(self):
        return digest(asdict(self))


@dataclass(frozen=True)
class Certificate:
    height: int
    parent: str
    value: str
    round: int = 0
    context: tuple = CONTEXT
    signers: tuple = (0, 1, 2)
    authenticated: bool = True


def tally(rows, dimension):
    require(dimension in DIMENSIONS, 'wrong dimension')
    selected = [r for r in rows if r['vote']['dimension'] == dimension]
    require(len({r['vote']['reviewer'] for r in selected}) == len(selected), 'duplicate tally slot')
    p, n, u = [sum(r['vote']['choice'] == c for r in selected) for c in CHOICES[dimension]]
    e = sum(r['status'] == 'established' for r in selected)
    quorum = len(selected) >= 5 and e >= 1
    outcome = 'UNDECIDED' if not quorum or p+n == 0 else 'PASS' if 10000*p >= 7000*(p+n) else 'FAIL'
    return dict(positive=p, negative=n, unsure=u, established=e, total=len(selected),
                decisive=p+n, quorum=quorum, outcome=outcome)


def result(session):
    dims = {d: tally(session.admitted, d) for d in DIMENSIONS}
    outcomes = [t['outcome'] for t in dims.values()]
    outcome = 'FAIL' if 'FAIL' in outcomes else 'PASS' if outcomes == ['PASS', 'PASS'] else 'UNDECIDED'
    return dict(session=session.sid, open_height=session.opened, close_height=session.close,
                count=len(session.admitted), ordered_commitment=digest(session.admitted),
                dimensions=dims, outcome=outcome)


def due_closes(state, height):
    return tuple(dict(kind='CLOSE', result=result(s)) for _, s in sorted(state.sessions.items())
                 if s.closed is None and s.close == height)


def batch_for(state, events=(), *, omit_close=False):
    h = state.height+1
    closes = () if omit_close else due_closes(state, h)
    return Batch(h, state.tip, closes+tuple(events))


def certificate_for(batch, **kwargs):
    """Trusted experiment supplies prior BFT decision, not a signature service."""
    return Certificate(batch.height, batch.parent, batch.value, **kwargs)


def sources(batch):
    # Each entire event is one content-addressed object in this abstraction.
    return frozenset(digest(e) for e in batch.events)


def admit(state, raw, height, index):
    v = Vote(**raw)
    # Invalid garbage is not a valid journal input. Authenticated contextual
    # rejections may be ordered as observations; neither can count.
    require(v.authenticated, 'unauthenticated vote')
    if (v.network, v.genesis) != (N, G):
        return 'WRONG_CONTEXT'
    s = state.sessions.get(v.session)
    if s is None:
        return 'WRONG_SESSION'
    if (v.submission, v.original, v.creator, v.base_media, v.base_journal, v.close_height) != (
            s.submission, s.original, s.creator, s.media, s.journal, s.close):
        return 'WRONG_BINDING'
    if v.dimension not in DIMENSIONS or v.choice not in CHOICES[v.dimension]:
        return 'WRONG_DIMENSION_OR_CHOICE'
    if s.closed is not None or height >= s.close:
        return 'LATE'
    if height <= s.opened:
        return 'OPEN_HEIGHT'
    prior = next((r for r in s.admitted if (r['vote']['dimension'], r['vote']['reviewer']) ==
                  (v.dimension, v.reviewer)), None)
    if prior:
        if prior['vote']['choice'] == v.choice:
            return 'DUPLICATE'
        s.conflicts.add((v.dimension, v.reviewer))
        return 'CONFLICT'  # first admission immutable; penalty policy abstracted
    status = s.eligibility.get(v.reviewer)
    if status not in ('probationary', 'established') or v.reviewer == s.creator:
        return 'INELIGIBLE'
    if state.media != s.media:
        return 'STALE_SESSION'
    epoch = state.media[0]//5
    if state.penalties.get(v.reviewer, -1) > epoch:
        return 'PENALIZED'
    key = (v.reviewer, s.submission)
    if key not in state.charges:
        used = sum(w == v.reviewer and e == epoch for (w, _), e in state.charges.items())
        if used >= (5 if status == 'probationary' else 25):
            return 'QUOTA_EXHAUSTED'
        state.charges[key] = epoch
    s.admitted.append(dict(vote=raw, status=status, position=(height, index)))
    return 'ADMIT'


def apply(state, batch, cert, available):
    """Validate one complete finalized transition; leave input unchanged on error."""
    require(cert.authenticated and cert.context == CONTEXT, 'untrusted journal authority')
    require(all(type(s) is int for s in cert.signers)
            and len(set(cert.signers)) >= 3 and len(set(cert.signers)) == len(cert.signers)
            and set(cert.signers) <= set(range(4)), 'invalid quorum')
    require(type(cert.round) is int and 0 <= cert.round <= 2147483647, 'round')
    require((cert.height, cert.parent, cert.value) == (batch.height, batch.parent, batch.value), 'proof binding')
    require(batch.height == state.height+1, 'missing journal segment', 'INCOMPLETE_HISTORY')
    require(batch.parent == state.tip, 'incompatible journal parent')
    require(sources(batch) <= available, 'missing source evidence', 'INCOMPLETE_HISTORY')
    expected = due_closes(state, batch.height)
    require(batch.events[:len(expected)] == expected, 'mandatory ordered CLOSE')
    require(sum(e['kind'] == 'CLOSE' for e in batch.events) == len(expected), 'extra CLOSE')
    require(sum(e['kind'] == 'OPEN' for e in batch.events) <= 16, 'OPEN close reservation')
    require(sum(e['kind'] == 'VOTE' for e in batch.events) <= 24, 'VOTE count cap')
    require(sum(e['kind'] == 'ANCHOR' for e in batch.events) <= 1, 'ANCHOR count')
    require(not (any(e['kind'] == 'ANCHOR' for e in batch.events) and
                 any(e['kind'] == 'OPEN' for e in batch.events)), 'OPEN and ANCHOR')
    require(all(e['kind'] != 'ANCHOR' for e in batch.events[len(expected)+1:]), 'ANCHOR order')
    out = deepcopy(state)
    for i, event in enumerate(batch.events):
        # Finalized state owns its sources. Later edits to an experiment's
        # input dictionaries must not rewrite an already admitted vote/CLOSE.
        event = deepcopy(event)
        kind = event['kind']
        if kind == 'CLOSE':
            s = out.sessions[event['result']['session']]
            s.closed, s.close_source = event['result'], (batch.height, batch.value, i)
        elif kind == 'OPEN':
            require(event['authenticated'] and event['sources_valid'], 'unverified OPEN sources')
            sid, sub, original = event['sid'], event['submission'], event['original']
            require(sid not in out.sessions and original not in out.settled, 'duplicate session/original')
            prior = [s for s in out.sessions.values() if s.submission == sub or s.original == original]
            if prior:
                last = max(prior, key=lambda s: s.opened)
                require((sub, original, event['creator']) == (last.submission, last.original, last.creator),
                        'original/submission identity')
                require(last.closed is not None, 'original/submission lock')
                require(last.attempt == 0 and event['attempt'] == 1, 'retry limit')
                require(last.closed['outcome'] != 'FAIL', 'terminal negative')
                require(last.closed['outcome'] != 'PASS' or out.media != last.media, 'outstanding passed admission')
                require(batch.height >= last.close+(last.close-last.opened), 'retry delay')
            else:
                require(event['attempt'] == 0, 'retry without previous session')
            require(type(event['window']) is int and 2 <= event['window'] <= 9007199254740991-batch.height,
                    'window overflow')
            require(event['window'] == state.window, 'fixed policy window')
            out.sessions[sid] = Session(sid, sub, original, event['creator'], batch.height,
                                        batch.height+event['window'], out.media, (state.height, state.tip),
                                        dict(out.statuses), attempt=event['attempt'])
        elif kind == 'VOTE':
            reason = admit(out, event['vote'], batch.height, i)
            out.observations.append((batch.height, i, digest(event), reason))
        elif kind == 'PENALTY':
            require(event['authenticated_proof'], 'unproved penalty')
            out.penalties[event['reviewer']] = max(out.penalties.get(event['reviewer'], -1), event['end_epoch'])
        elif kind == 'STATUS':
            require(event['authenticated_history'], 'unproved status')
            out.statuses[event['reviewer']] = event['status']
        elif kind == 'ANCHOR':
            m = event['media']
            validate_media(out, m, local_media=out.media)
            out.media = (m['height'], m['hash'])
            out.settled[m['original']] = m['hash']
        else:
            raise Rejected('INVALID', 'unknown event')
    out.height, out.tip = batch.height, batch.value
    return out


def open_event(sid='s', window=3, submission=None, original=None, attempt=0):
    return dict(kind='OPEN', sid=sid, submission=submission or 'submission-'+sid,
                original=original or 'original-'+sid, creator='creator', window=window,
                authenticated=True, sources_valid=True, attempt=attempt)


def vote_event(state, reviewer='r0', sid='s', dimension='originality', choice=None, **changes):
    s = state.sessions[sid]
    v = Vote(sid, reviewer, dimension, choice or CHOICES[dimension][0], submission=s.submission,
             original=s.original, creator=s.creator, base_media=s.media, base_journal=s.journal,
             close_height=s.close)
    return dict(kind='VOTE', vote={**asdict(v), **changes})


def step(state, *events):
    b = batch_for(state, events)
    return apply(state, b, certificate_for(b), sources(b))


def media_candidate(state, sid='s', name='media-x'):
    s = state.sessions[sid]
    return dict(context=(N, G, 'media', C), authenticated=True, available=True,
                height=s.media[0]+1, parent=s.media[1], hash=name, original=s.original,
                session=sid, close_source=s.close_source, result=s.closed,
                other_media_checks=True)


def validate_media(state, media, *, local_media):
    require(media['authenticated'] and media['context'] == (N, G, 'media', C), 'media authority')
    require(media['available'], 'missing media evidence', 'INCOMPLETE_HISTORY')
    require(media['other_media_checks'], 'media safety/native/rights checks')
    require(local_media[0] >= state.media[0], 'journal anchor ahead of local media', 'INCOMPLETE_HISTORY')
    require(local_media == state.media, 'unanchored or incompatible media parent')
    s = state.sessions.get(media['session'])
    require(s is not None, 'missing review session', 'INCOMPLETE_HISTORY')
    require(s.closed is not None, 'unfinalized/open review')
    require(media['close_source'] == s.close_source and media['result'] == s.closed, 'substituted review')
    require(s.closed['outcome'] == 'PASS', 'nonpassing review')
    require(s.media == state.media and (media['height']-1, media['parent']) == s.media, 'stale media parent')
    require(media['original'] == s.original and s.original not in state.settled, 'duplicate/conflicting admission')
    return 'PASS'


def replay(initial, history, evidence, *, checkpoint=None):
    out = deepcopy(initial)
    for b, c in history:
        out = apply(out, b, c, evidence)
    if checkpoint is not None:
        require((out.height, out.tip) == checkpoint, 'checkpoint not replayed', 'INCOMPLETE_HISTORY')
    return out


def checkpoint_guard(retained, candidate, *, authenticated, ancestry_matches):
    """Recovery admission guard, not latest-tip discovery or a proof verifier."""
    require(authenticated, 'unauthenticated checkpoint')
    require(candidate[0] >= retained[0], 'checkpoint rollback')
    if candidate[0] == retained[0]:
        require(candidate[1] == retained[1], 'conflicting finalized checkpoint', 'CONFLICTING_FINALITY')
    require(ancestry_matches, 'missing/incompatible checkpoint ancestry', 'INCOMPLETE_HISTORY')
    return 'CONTINUE_REPLAY'


def fingerprint(state):
    # Canonical diagnostic captures sources, statuses, charges, conflicts, and roots.
    return digest(dict(window=state.window, height=state.height, tip=state.tip, media=state.media,
                       sessions={k: {**asdict(s), 'conflicts': sorted(s.conflicts)}
                                 for k, s in sorted(state.sessions.items())},
                       charges=sorted((w, sub, e) for (w, sub), e in state.charges.items()),
                       penalties=state.penalties, statuses=state.statuses,
                       observations=state.observations, settled=state.settled))
