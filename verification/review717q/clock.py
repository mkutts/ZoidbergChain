"""Symbolic agreed clock/epoch experiment, not a time oracle or consensus.

Inputs assert q3 authenticated distinct epoch0 signers in one exact context.
The experiment cannot establish real clock error, inclusion fairness or BFT.
"""
from copy import deepcopy
from dataclasses import dataclass, field
from hashlib import sha256

CONTEXT = ('test-N', 'test-G', 'review-journal', 'clock-policy-Q')


def state_token(state):
    # Diagnostic binding only, not a production canonical state commitment.
    return sha256(repr(state).encode('utf-8')).hexdigest()


@dataclass
class ClockState:
    lower: int = 0
    epoch: int = 0
    sessions: dict = field(default_factory=dict)
    charges: dict = field(default_factory=dict)
    penalties: dict = field(default_factory=dict)


def clock_step(state, *, readings, signers=(0, 1, 2), context=CONTEXT,
               epsilon=1, epoch_span=100, opens=(), starts=(), votes=(), due=None,
               available=True, authenticated=True, parent=None):
    """Integer test units; every time proof binds the prior state externally.

    opens=(sid,...); starts=(sid, window); votes=(sid,wallet,submission,status). One charge
    across retries/dimensions. Late votes have no charge. No reward transition.
    """
    if not available:
        raise ValueError('INCOMPLETE_EVIDENCE')
    if parent is not None and parent != state_token(state):
        raise ValueError('clock parent/checkpoint')
    if (not authenticated or context != CONTEXT or len(signers) != 3
            or not all(type(s) is int for s in signers)
            or len(set(signers)) != 3 or not set(signers) <= set(range(4))):
        raise ValueError('clock authority')
    if len(readings) != 3 or any(type(t) is not int or t < 0 for t in readings):
        raise ValueError('clock readings')
    median = sorted(readings)[1]
    lower, upper = median-epsilon, median+epsilon
    if lower < state.lower:
        raise ValueError('clock rollback')
    out = deepcopy(state)
    expected = sorted(sid for sid, s in state.sessions.items()
                      if not s['closed'] and s['deadline'] is not None and lower >= s['deadline'])
    if due is not None and list(due) != expected:
        raise ValueError('mandatory close prefix')
    for sid in expected:
        out.sessions[sid]['closed'] = True
    out.lower, out.epoch = lower, max(state.epoch, lower//epoch_span)
    for sid in opens:
        if sid in out.sessions:
            raise ValueError('OPEN')
        out.sessions[sid] = dict(deadline=None, closed=False, votes=[])
    for sid, window in starts:
        if sid not in state.sessions or state.sessions[sid]['deadline'] is not None or type(window) is not int or window <= 0:
            raise ValueError('START')
        # Samples for START must follow its already-finalized OPEN, never itself.
        out.sessions[sid]['deadline'] = upper+window
    observations = []
    for sid, wallet, submission, status in votes:
        if status not in ('probationary', 'established'):
            raise ValueError('unsupported eligibility fact')
        s = out.sessions[sid]
        key = (wallet, submission)
        if s['deadline'] is None:
            observations.append('NOT_STARTED')
        elif s['closed']:
            observations.append('LATE')
        elif out.penalties.get(wallet, -1) > out.epoch:
            observations.append('PENALIZED')
        elif key not in out.charges and sum(w == wallet and e == out.epoch for (w, _), e in out.charges.items()) >= (5 if status == 'probationary' else 25):
            observations.append('QUOTA_EXHAUSTED')
        elif (wallet, submission) in s['votes']:
            observations.append('DUPLICATE')
        else:
            out.charges.setdefault(key, out.epoch)
            s['votes'].append((wallet, submission))
            observations.append('ADMIT')
    return out, observations
