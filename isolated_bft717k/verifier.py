"""Bounded 7.17I message/PV/Q4 crypto core, authorized by local test pins.

This never decides/finalizes a block and never asserts a complete agreement run.
No peer roster, current administrator configuration, SQLite or network access.
"""
from dataclasses import dataclass, replace

from canonical_v3.primitives import closed, h64, require, uint, V3Error
from isolated_bft717j.wire import (COMMON, MAX_ROUND, J, parse, sha, signed,
                                  commitment, slot_key)
from .authority import StaticTestAuthority
from .outcomes import AuthorityFailure, Outcome, Verification

T_FIELDS = ' '.join(k for k in COMMON.split() if k != 'validator_id') + ' block_hash step'


@dataclass
class _Work:
    checks: int = 0
    distinct: int = 0


class _Partial(Exception):
    def __init__(self, outcome, detail):
        self.outcome, self.detail = outcome, detail


def _authenticate(raw, ctx, work):
    work.checks += 1
    return signed(raw, ctx)


def _commitment(t, ctx, kind):
    closed(t, T_FIELDS)
    require(t['step'] == ('prevote' if kind == 'pv' else 'precommit'), 'proof_step')
    require(uint(t['message_version']) == 1 and uint(t['validator_epoch']) == 0, 'version_or_epoch')
    uint(t['block_height'], 1)
    uint(t['round'], 0, MAX_ROUND)
    for field in ('genesis_hash', 'parent_hash', 'agreement_profile_digest', 'validator_set_commitment'):
        h64(t[field])
    require(t['genesis_hash'] == ctx.genesis_hash and t['agreement_profile_digest'] == ctx.A and
            t['validator_set_commitment'] == ctx.C, 'proof_context')
    if t['block_height'] == 1:
        require(t['parent_hash'] == ctx.genesis_hash, 'parent')
    if t['block_hash'] is not None:
        h64(t['block_hash'])
    require(kind == 'pv' or t['block_hash'] is not None, 'nil_commit_proof')


def _certificate(raw, ctx, kind, work):
    require(kind in ('pv', 'q4'), 'proof_kind')
    obj = parse(raw, 12288 if kind == 'pv' else 16384)
    version, count_key, number = ('certificate_version', 'votes', 1) if kind == 'pv' else (
        'proof_version', 'precommits', 4)
    # Missing proposal is diagnosed as incomplete, never accepted as a Q4.
    closed(obj, version + ' commitment ' + count_key,
           optional=('proposal',) if kind == 'q4' else ())
    require(uint(obj[version]) == number, 'proof_version')
    t, votes = obj['commitment'], obj[count_key]
    _commitment(t, ctx, kind)
    require(type(votes) is list and len(votes) <= 4, 'proof_count_bound')
    seen, ids = {}, []
    for v in votes:
        v = _authenticate(J(v), ctx, work)
        e = v['envelope']
        vid = e['payload']['validator_id']
        if vid in seen:
            require(J(e) == seen[vid], 'contradictory_votes_same_identity')
            raise V3Error('duplicate_signer')
        seen[vid] = J(e)
        ids.append(vid)
        work.distinct = len(seen)
        require(commitment(e) == t, 'proof_commitment')
    require(ids == sorted(ids), 'proof_order')
    if kind == 'q4':
        if obj.get('proposal') is None:
            raise _Partial(Outcome.INCOMPLETE_DATA, 'missing_signed_proposal')
        p = _authenticate(J(obj['proposal']), ctx, work)['envelope']
        require(p['payload']['step'] == 'propose', 'proof_proposal')
        pp = {k: v for k, v in commitment(p).items() if k not in ('step', 'valid_round')}
        require(pp == {k: v for k, v in t.items() if k != 'step'}, 'proof_proposal_context')
    if len(votes) < 3:
        # Not a valid canonical PV/Q4 (the grammar requires 3..4). This more
        # specific diagnostic does not turn the undersized wrapper into a QC.
        raise _Partial(Outcome.INSUFFICIENT_QUORUM, 'requires_3_distinct_authorized_signers')
    return obj


def _parent_reference(raw, t, ctx):
    p = parse(raw, 113)
    closed(p, 'block_height block_hash')
    uint(p['block_height'])
    h64(p['block_hash'])
    require(p['block_height'] == t['block_height'] - 1 and p['block_hash'] == t['parent_hash'],
            'parent_reference_mismatch')
    if p['block_height'] == 0:
        require(p['block_hash'] == ctx.genesis_hash, 'genesis_parent')
    # Equality checks a reference only; h>0 needs actual verified B/Q4/prefix.


def _run(authority, action):
    work = _Work()
    if type(authority) is not StaticTestAuthority:
        return Verification(Outcome.WRONG_CONTEXT, 'explicit_local_test_authority_required')
    try:
        return action(authority.context, work)
    except _Partial as exc:
        return Verification(exc.outcome, exc.detail, fixture_membership_authenticated=True,
            signatures_valid=True, signature_checks=work.checks, distinct_signers=work.distinct)
    except V3Error as exc:
        outcome = Outcome.WRONG_CONTEXT if exc.code in ('context', 'proof_context') else Outcome.INVALID_PROOF
        return Verification(outcome, exc.code, fixture_membership_authenticated=True,
            signature_checks=work.checks, distinct_signers=work.distinct)
    except AuthorityFailure as exc:
        return Verification(exc.outcome, exc.detail, signature_checks=work.checks)
    except (MemoryError, OSError) as exc:
        # Crypto-provider/local resource failures are not objective protocol invalidity.
        return Verification(Outcome.RESOURCE_FAILURE, type(exc).__name__,
                            signature_checks=work.checks)


def verify_message(authority, raw, *, expected_step=None, parent_reference=None):
    def action(ctx, work):
        s = _authenticate(raw, ctx, work)
        t = s['envelope']['payload']
        if expected_step is not None:
            require(expected_step in ('propose', 'prevote', 'precommit') and
                    t['step'] == expected_step, 'unexpected_step')
        if parent_reference is not None:
            _parent_reference(parent_reference, t, ctx)
        return Verification(Outcome.VALID_MESSAGE, 'exact_registered_key_and_preimage; test_pins_only',
            fixture_membership_authenticated=True, signatures_valid=True,
            signature_checks=work.checks, distinct_signers=1)
    return _run(authority, action)


def verify_quorum(authority, raw, kind='q4'):
    def action(ctx, work):
        _certificate(raw, ctx, kind, work)
        return Verification(Outcome.VALID_QUORUM,
            'canonical_' + kind + '_crypto_core; G2/application/ancestry/execution_unverified',
            fixture_membership_authenticated=True, signatures_valid=True, quorum_structure_valid=True,
            signature_checks=work.checks, distinct_signers=work.distinct, proof_id=sha(raw))
    return _run(authority, action)


def verify_history(authority, raw, *, block_bytes=None, parent_reference=None):
    """Diagnose historical prerequisites without inventing combined B/G2 semantics."""
    result = verify_quorum(authority, raw)
    if result.outcome != Outcome.VALID_QUORUM:
        return result
    try:
        t = parse(raw, 16384)['commitment']
        if parent_reference is not None:
            _parent_reference(parent_reference, t, authority.context)
        if block_bytes is not None:
            require(type(block_bytes) is bytes and len(block_bytes) <= 3145728, 'block_size')
    except V3Error as exc:
        return replace(result, outcome=Outcome.INVALID_PROOF, detail=exc.code)
    except (MemoryError, OSError) as exc:
        return replace(result, outcome=Outcome.RESOURCE_FAILURE, detail=type(exc).__name__)
    missing = []
    if block_bytes is None:
        missing.append('missing_canonical_application_block')
    if parent_reference is None:
        missing.append('missing_parent_reference_and_prefix')
    missing.extend(('G2_authentication_unspecified', 'combined_application_hash_and_policy_unfrozen',
                    'full_finalized_ancestry_unverified'))
    return replace(result, outcome=Outcome.INCOMPLETE_DATA, detail='; '.join(missing))


def compare_quorums(authority, first, second):
    """Detect conflicting signature thresholds, NOT conflicting finalized blocks."""
    a = verify_quorum(authority, first)
    if a.outcome != Outcome.VALID_QUORUM:
        return a
    b = verify_quorum(authority, second)
    if b.outcome != Outcome.VALID_QUORUM:
        return replace(b, signature_checks=a.signature_checks + b.signature_checks)
    try:
        x, y = parse(first, 16384)['commitment'], parse(second, 16384)['commitment']
    except (MemoryError, OSError) as exc:
        return Verification(Outcome.RESOURCE_FAILURE, type(exc).__name__,
                            signature_checks=a.signature_checks + b.signature_checks)
    if x['block_height'] != y['block_height']:
        outcome, detail = Outcome.INCOMPLETE_DATA, 'cross_height_ancestry_requires_verified_blocks_and_prefix'
    elif (x['block_hash'], x['parent_hash']) != (y['block_hash'], y['parent_hash']):
        outcome, detail = Outcome.CONFLICT, 'retain_both_test_QCs; block_validity_and_finality_not_established'
    else:
        outcome, detail = Outcome.COMPATIBLE, 'same_target_and_parent; subsets_signatures_rounds_may_differ'
    return replace(a, outcome=outcome, detail=detail, proof_id=None,
                   signature_checks=a.signature_checks + b.signature_checks)


def compare_messages(authority, first, second):
    """Authenticate both before reporting equivocation; never change membership."""
    def action(ctx, work):
        a, b = (_authenticate(raw, ctx, work)['envelope'] for raw in (first, second))
        same_id = a['payload']['validator_id'] == b['payload']['validator_id']
        require(same_id and slot_key(a) == slot_key(b), 'different_identity_or_slot')
        outcome = Outcome.RETRANSMISSION if J(a) == J(b) else Outcome.EQUIVOCATION
        return Verification(outcome, 'same_context_identity_height_round_purpose; static_authority_unchanged',
            fixture_membership_authenticated=True, signatures_valid=True,
            signature_checks=work.checks, distinct_signers=1)
    return _run(authority, action)
