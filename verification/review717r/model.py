"""Bounded application experiment, supplied authentication/finality facts ONLY.

Not a BFT engine, crypto verifier, source-policy verifier, signer or database.
State uses a bounded ordered expiry index; no scan over vote history at CLOSE.
"""
from bisect import insort
from copy import deepcopy
from dataclasses import dataclass, field
from fractions import Fraction
from hashlib import sha256
import json

from .wire import CTX, pack, tagged

MAX_LIVE, PAGE, OPEN_LIMIT = 4096, 16, 16
EPSILON, WINDOW, EPOCH_SPAN = 1, 1200, 300
CONTEXT = dict(network='r717-laboratory', genesis='11'*32, protocol=1,
               instance='22'*32, validators='33'*32, membership=0, policy='44'*32)
RESULTS = ('ADMIT', 'DUPLICATE', 'CONFLICT', 'LATE', 'WRONG_SESSION', 'WRONG_BINDING',
           'INELIGIBLE', 'PENALIZED', 'QUOTA_EXHAUSTED', 'STALE_SESSION')


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def tally(counts):
    p, n, u, e = counts
    d, total = p+n, p+n+u
    ratio = Fraction(p, d) if d else None
    outcome = 0 if total < 5 or e < 1 or not d else 1 if 10000*p >= 7000*d else 2
    return dict(positive=p, negative=n, unsure=u, established=e, total=total, decisive=d,
                numerator=ratio.numerator if ratio is not None else 0,
                denominator=ratio.denominator if ratio is not None else 0, outcome=outcome)


@dataclass
class Session:
    sid: str
    submission: str
    original: str
    creator: str
    opened: int
    base_height: int
    base_hash: str
    media_height: int
    media_hash: str
    eligibility: dict
    deadline: int | None = None
    started: int | None = None
    count: int = 0
    fold: str = '00'*32
    counts: list = field(default_factory=lambda: [[0, 0, 0, 0], [0, 0, 0, 0]])
    slots: dict = field(default_factory=dict)
    conflicts: set = field(default_factory=set)
    close: dict | None = None
    close_position: tuple | None = None


@dataclass
class State:
    height: int = 0
    tip: str = '00'*32
    lower: int = 0
    median: int = 0
    epoch: int = 0
    sessions: dict = field(default_factory=dict)
    originals: set = field(default_factory=set)
    submissions: set = field(default_factory=set)
    expiry: list = field(default_factory=list)
    pending: list = field(default_factory=list)
    charges: dict = field(default_factory=dict)
    used: dict = field(default_factory=dict)
    penalties: dict = field(default_factory=dict)
    media: tuple = (0, '11'*32)
    finalized: dict = field(default_factory=dict)


def closed(s, lower):
    return s.deadline is not None and s.deadline <= lower


def close_row(s, freeze_height):
    a, b = [tally(c) for c in s.counts]
    out = 2 if 2 in (a['outcome'], b['outcome']) else 1 if a['outcome'] == b['outcome'] == 1 else 0
    return dict(sid=s.sid, deadline=s.deadline, freeze_height=freeze_height, count=s.count,
                fold=s.fold, originality=a, admissibility=b, outcome=out)


def clock(state, readings, signers, authenticated=True, parent=None, height=None, available=True):
    if (not authenticated or not available or len(readings) != 3 or len(signers) != 3
            or any(type(x) is not int or x < 0 or x > 9007199254740991 for x in readings)
            or any(type(x) is not int for x in signers)
            or len(set(signers)) != 3 or list(signers) != sorted(signers) or not set(signers) <= {0, 1, 2, 3}):
        raise ValueError('clock authority/evidence')
    if parent is not None and parent != state.tip or height is not None and height != state.height+1:
        raise ValueError('clock parent/height')
    m = sorted(readings)[1]
    active = bool(state.expiry or state.pending)
    delta = 5 if active else 300
    if m < state.median + delta or m < EPSILON or m + EPSILON + WINDOW > 9007199254740991:
        raise ValueError('clock cadence/overflow')
    return m, m-EPSILON


def page(state, lower):
    return [sid for deadline, sid in state.expiry[:PAGE] if deadline <= lower]


def freeze_height(state, deadline, boundaries):
    # Historical reference oracle used by the laboratory. An implementation
    # stores monotone time intervals and searches at most 53 UInt bits.
    return next(h for h, lower in boundaries if lower >= deadline)


def step(state, *, readings, opens=(), votes=(), supplied_page=None, signers=(0, 1, 2),
         authenticated=True, available=True, parent=None, height=None, boundaries=(),
         context=None, proof_value=None, finalized=True):
    if context is not None and context != CONTEXT or not finalized:
        raise ValueError('journal authority')
    m, lower = clock(state, readings, signers, authenticated, parent, height, available)
    h = state.height + 1
    expected = page(state, lower)
    if supplied_page is not None and supplied_page != expected:
        raise ValueError('mandatory close page')
    if len(opens) > OPEN_LIMIT or len(votes) > 96:
        raise ValueError('work limit')
    out = deepcopy(state)
    boundaries = tuple(boundaries) + ((h, lower),)
    closes = []
    for close_index, sid in enumerate(expected):
        s = out.sessions[sid]
        row = close_row(s, freeze_height(state, s.deadline, boundaries))
        s.close = row
        s.close_position = (h, close_index)
        closes.append(row)
        out.expiry.remove((s.deadline, sid))
    # START is mandatory for the exact prior-height pending OPEN list.
    for sid in out.pending:
        s = out.sessions[sid]
        s.deadline, s.started = m + EPSILON + WINDOW, h
        insort(out.expiry, (s.deadline, sid))
    out.pending = []
    out.median, out.lower, out.epoch = m, lower, lower // EPOCH_SPAN
    observations = []
    for index, vote in enumerate(votes):
        observations.append(admit(out, vote, h, index))
    # Model OPENs are explicit trusted source/eligibility facts, NOT wire objects.
    if len(out.expiry) + len(opens) > MAX_LIVE:
        raise ValueError('live session cap')
    for o in opens:
        if o['sid'] in out.sessions or not o.get('sources_valid', False):
            raise ValueError('OPEN source/identity')
        if o['original'] in out.originals:
            raise ValueError('UNSUPPORTED_RETRY_OR_ORIGINAL_LOCK')
        if o['submission'] in out.submissions:
            raise ValueError('submission identity lock')
        s = Session(o['sid'], o['submission'], o['original'], o['creator'], h,
                    state.height, state.tip, *state.media, deepcopy(o['eligibility']))
        s.fold = tagged('empty-votes', bytes.fromhex(s.sid))
        out.sessions[s.sid] = s
        out.originals.add(s.original)
        out.submissions.add(s.submission)
        out.pending.append(s.sid)
    value = digest(dict(parent=state.tip, height=h, median=m, closes=closes,
                        observations=observations, opens=list(opens), votes=list(votes)))
    if proof_value is not None and proof_value != value:
        raise ValueError('conflicting journal proof')
    out.height, out.tip = h, value
    out.finalized[h] = value
    return out, dict(closes=closes, observations=observations, boundary=(h, lower))


def admit(state, v, height, index):
    if not v.get('authenticated', False):
        raise ValueError('INVALID_SIGNATURE')
    if v['context'] != CONTEXT:
        raise ValueError('WRONG_NETWORK')
    s = state.sessions.get(v['sid'])
    if s is None:
        return 'WRONG_SESSION'
    if (v['submission'], v['original'], v['creator'], v['base_height'], v['base_hash'],
        v['media_height'], v['media_hash'], v['deadline']) != (
            s.submission, s.original, s.creator, s.base_height, s.base_hash,
            s.media_height, s.media_hash, s.deadline):
        return 'WRONG_BINDING'
    d, c, w = v['dimension'], v['choice'], v['wallet']
    if type(d) is not int or type(c) is not int or d not in (0, 1) or c not in (0, 1, 2):
        raise ValueError('vote enum')
    if s.started is None or height <= s.started or closed(s, state.lower):
        return 'LATE'
    slot = d, w
    if slot in s.slots:
        if s.slots[slot]['choice'] == c:
            return 'DUPLICATE'
        s.conflicts.add(slot)
        return 'CONFLICT'
    status = s.eligibility.get(w)
    if status not in (1, 2) or w == s.creator:
        return 'INELIGIBLE'
    if state.media != (s.media_height, s.media_hash):
        return 'STALE_SESSION'
    if state.penalties.get(w, 0) > state.epoch:
        return 'PENALIZED'
    key = w, s.submission
    if key not in state.charges:
        used = state.used.get((w, state.epoch), 0)
        if used >= (5 if status == 1 else 25):
            return 'QUOTA_EXHAUSTED'
        state.charges[key] = state.epoch
        state.used[w, state.epoch] = used + 1
    s.slots[slot] = dict(choice=c, height=height, index=index, status=status)
    s.count += 1
    s.counts[d][c] += 1
    s.counts[d][3] += status == 2
    # Compact model commitment; full wire vote fold is specified separately.
    s.fold = tagged('model-fold', bytes.fromhex(s.fold) + bytes.fromhex(digest(v))
                    + height.to_bytes(8, 'big') + index.to_bytes(2, 'big') + bytes([status]))
    return 'ADMIT'


def open_fact(i, eligibility=None):
    return dict(sid=f'{i:064x}', submission=f'{i:032x}', original=f'{i+1:064x}',
                creator='creator', eligibility=eligibility or {'w': 2}, sources_valid=True)


def vote_fact(s, wallet='w', dimension=0, choice=0, **changes):
    v = dict(context=CONTEXT, sid=s.sid, submission=s.submission, original=s.original,
             creator=s.creator, base_height=s.base_height, base_hash=s.base_hash,
             media_height=s.media_height, media_hash=s.media_hash, deadline=s.deadline,
             wallet=wallet, dimension=dimension, choice=choice, authenticated=True)
    v.update(changes)
    return v


def wire_fold(previous, ordinal, height, index, signed_vote, status):
    """Normative fold uses vote/signature bytes, excluding own batch identity."""
    msg = pack('VOTE', signed_vote)
    return tagged('vote-step', bytes.fromhex(previous) + ordinal.to_bytes(8, 'big')
                  + height.to_bytes(8, 'big') + index.to_bytes(2, 'big')
                  + bytes.fromhex(tagged('vote-message', msg[:-65]))
                  + bytes.fromhex(tagged('vote-evidence', msg)) + bytes([status]))


def media_reference(state, sid):
    s = state.sessions[sid]
    if s.close is None or s.close_position is None or s.close['outcome'] != 1:
        raise ValueError('no materialized PASS')
    h, index = s.close_position
    return dict(context=CONTEXT, sid=sid, checkpoint=(h,state.finalized[h]), close_index=index,
                close_id=digest(s.close), submission=s.submission, original=s.original,
                creator=s.creator, media_parent=(s.media_height,s.media_hash),
                count=s.count, fold=s.fold, originality=s.close['originality'],
                admissibility=s.close['admissibility'])


def verify_media_reference(state, candidate, *, actual_media_parent, consumed=frozenset(),
                           evidence_complete=True, genesis_policy_supported=True):
    """Trusted replay experiment, NOT G2/crypto/media canonical validation."""
    if not evidence_complete:
        raise ValueError('INCOMPLETE_EVIDENCE')
    if not genesis_policy_supported:
        raise ValueError('UNSUPPORTED_G2_POLICY')
    sid = candidate.get('sid')
    if sid not in state.sessions or candidate != media_reference(state,sid):
        raise ValueError('review reference mismatch')
    if candidate['media_parent'] != actual_media_parent:
        raise ValueError('stale media parent')
    if candidate['original'] in consumed:
        raise ValueError('duplicate accepted original')
    return 'VALID_REFERENCE_ONLY'
