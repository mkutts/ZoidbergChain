"""Proposed G2 bytes/commitments only; no approved application-policy semantics.

The trust pin is LOCAL caller configuration. Never derive it from a peer/cache.
No complete-valid outcome or implicit Boolean acceptance is available.
"""
from dataclasses import dataclass
from enum import Enum
import hmac

from canonical_v3.primitives import (V3Error, parse as unicode_parse,
    closed, require, uint, h64, pattern, wallet, decimal_units)
from isolated_bft717j.wire import J, parse, sha, descriptor
from isolated_bft717k.manifest import Manifest
from isolated_bft717k.outcomes import AuthorityFailure, Outcome as KOutcome

GENESIS_LIMIT = 1048576  # Proposed TEST-ONLY limit, not the media-block cap.
CAPS = dict(validator_manifest=8192, agreement_descriptor=4096,
    policy_registry=65536, reviewer_bootstrap=8192, native_bootstrap=786432)
POLICIES = dict(encoding=1, history=1, issuance=1, media=2, native=2,
    reputation=3, review=3, reviewer=2, rights=1, technical=1)
PAYLOAD = ('genesis_version index previous_hash application initial_block_version '
    'consensus_message_version validator_manifest validator_set_commitment '
    'agreement_descriptor agreement_profile_digest policy_registry policy_registry_digest '
    'reviewer_bootstrap reviewer_bootstrap_digest native_bootstrap native_bootstrap_digest '
    'history_bootstrap')
INCOMPLETE = ('All ten policy source schemas/approvals remain unfrozen',
    'reviewer cohort/all-unsure/participation/offense authority and complete history',
    'native reward ordering/exhaustion and approved launch allocations',
    'combined block4/application transitions, release authority and activation')
# Explicit forbidden dependency names from L sections 3/5/8. This is only a
# structural diagnostic, NOT a schema or proof of source-policy noncircularity.
DEPENDENT_FIELDS = frozenset(('genesis_hash', 'agreement_profile_digest',
    'application_policy_digest', 'policy_registry_digest', 'initial_state_commitment',
    'reviewer_bootstrap_digest', 'native_bootstrap_digest', 'bootstrap_history_commitment',
    'bootstrap_digest', 'finalized_ref'))


class Outcome(str, Enum):
    INVALID_STRUCTURE = 'INVALID_GENESIS_STRUCTURE_OR_CANONICAL_BYTES'
    INVALID_COMMITMENT = 'INVALID_COMPONENT_COMMITMENT'
    WRONG_AUTHORITY = 'WRONG_PINNED_GENESIS_OR_NETWORK'
    INCOMPLETE_AUTHORITY = 'INCOMPLETE_AUTHORITY'
    INCOMPLETE_POLICY = 'VALID_ENVELOPE_INCOMPLETE_POLICY'
    IO_FAILURE = 'LOCAL_IO_FAILURE'
    RESOURCE_FAILURE = 'LOCAL_VERIFICATION_RESOURCE_FAILURE'


@dataclass(frozen=True)
class TrustedGenesisPin:
    """Independent local TEST pin, not a genesis self-authentication mechanism.

    Uses K's existing test-network namespace so its adapter needs no widening.
    Construct only from independently trusted local configuration/fixture data.
    """
    genesis_hash: str
    network_id: str
    application: str
    protocol_version: int = 2
    authority_profile: str = 'static-genesis-n4-f1-q3-v1'

    def __post_init__(self):
        h64(self.genesis_hash)
        pattern(self.network_id, r'task717[ijk]-test(?:-[a-z0-9-]+)?')
        pattern(self.network_id, r'[a-z0-9][a-z0-9-]{2,63}')
        pattern(self.application, r'[A-Za-z0-9][A-Za-z0-9_.-]{2,63}')
        require(uint(self.protocol_version) == 2 and
            self.authority_profile == 'static-genesis-n4-f1-q3-v1', 'test_pin_profile')


@dataclass(frozen=True)
class Result:
    outcome: Outcome
    detail: str
    genesis_hash: str | None = None
    canonical_envelope_verified: bool = False
    component_commitments_verified: bool = False
    pinned_test_identity_matched: bool = False
    incomplete_policies: tuple[str, ...] = ()
    # Immutable evidence only. Adapter rechecks bytes and independent pin.
    manifest_bytes: bytes | None = None
    agreement_bytes: bytes | None = None
    component_sizes: tuple[tuple[str, int], ...] = ()

    @property
    def complete_semantic_genesis_valid(self):
        return False

    @property
    def production_consensus_authorized(self):
        return False

    def __bool__(self):
        raise TypeError('inspect outcome and individual guarantees explicitly')


class _Mismatch(ValueError):
    pass


def envelope(kind, payload, network):
    """Exact L domain envelope; closed purpose registry, no arbitrary dispatch."""
    require(kind in ('genesis', 'reviewer-bootstrap', 'native-bootstrap',
        'history-bootstrap', 'initial-state'), 'purpose')
    version = 2 if kind == 'genesis' else 1
    return dict(domain=f'zoidbergchain/{kind}/v{version}', network_id=network,
        object_type=kind, payload=payload, protocol='zoidbergchain', protocol_version=2)


def _match(declared, actual, label):
    h64(declared)
    if not hmac.compare_digest(declared, actual):
        raise _Mismatch(label)


def _outer_tree(value):
    # Bound every G2-defined container/string before component crypto. The
    # generic maxima cover every closed outer level; source JSON is separate.
    require(value is not None, 'null_outer_field')
    if type(value) is dict:
        require(len(value) <= 17, 'outer_object_count')
        for child in value.values():
            _outer_tree(child)
    elif type(value) is list:
        require(len(value) <= 4096, 'outer_array_count')
        for child in value:
            _outer_tree(child)
    elif type(value) is str:
        require(len(value) <= 16384, 'outer_string_length')


def _prescan(raw):
    """Bound outer token widths/container counts before JSON tree allocation.

    Syntax, duplicate names, Unicode and exact J still belong to the parser.
    No valid G2-defined object has >17 fields, array >4096 entries, or encoded
    string token content >16384 bytes (the longest allowed value is source hex).
    """
    require(type(raw) is bytes and len(raw) <= GENESIS_LIMIT, 'json_size')
    stack = []
    quoted = escaped = False
    start = 0
    for offset, byte in enumerate(raw):
        if quoted:
            require(offset - start <= 16384, 'outer_string_length')
            if escaped:
                escaped = False
            elif byte == 92:
                escaped = True
            elif byte == 34:
                quoted = False
        elif byte == 34:
            quoted, start = True, offset + 1
        elif byte in (91, 123):
            stack.append([byte, 1])
            require(len(stack) <= 32, 'json_depth')
        elif byte == 44 and stack:
            stack[-1][1] += 1
            require(stack[-1][1] <= (4096 if stack[-1][0] == 91 else 17), 'outer_container_count')
        elif byte in (93, 125) and stack:
            stack.pop()


def _source_context(value, network, application):
    if type(value) is dict:
        require(not DEPENDENT_FIELDS.intersection(value), 'forbidden_source_dependency')
        for name, child in value.items():
            if name in ('network_id', 'application'):
                require(child == (network if name == 'network_id' else application),
                    'source_context_binding')
            _source_context(child, network, application)
    elif type(value) is list:
        for child in value:
            _source_context(child, network, application)


def _structure(raw):
    _prescan(raw)
    e = parse(raw, GENESIS_LIMIT)  # size/depth pre-scan; duplicate/UTF-8/J checks
    _outer_tree(e)
    closed(e, 'domain network_id object_type payload protocol protocol_version')
    n = e['network_id']
    pattern(n, r'[a-z0-9][a-z0-9-]{2,63}')
    require(uint(e['protocol_version']) == 2 and e['protocol'] == 'zoidbergchain'
        and e['domain'] == 'zoidbergchain/genesis/v2' and e['object_type'] == 'genesis',
        'genesis_envelope_profile')
    p = e['payload']
    closed(p, PAYLOAD)
    for name, expected in dict(genesis_version=2, index=0, initial_block_version=4,
            consensus_message_version=1).items():
        require(uint(p[name]) == expected, 'genesis_' + name)
    require(h64(p['previous_hash']) == '0'*64, 'genesis_parent')
    pattern(p['application'], r'[A-Za-z0-9][A-Za-z0-9_.-]{2,63}')
    components = {name: J(p[name]) for name in CAPS}
    for name, b in components.items():
        require(len(b) <= CAPS[name], name + '_size')
    require(len(raw) - sum(map(len, components.values())) <= 16384, 'residual_size')

    # All cheap schemas/counts/source checks precede key/identity work.
    pr = p['policy_registry']
    closed(pr, 'domain registry_version network_id policies')
    require(uint(pr['registry_version']) == 1 and pr['network_id'] == n and
        pr['domain'] == 'zoidbergchain/application-policy-registry/v1', 'registry_profile')
    entries = pr['policies']
    require(type(entries) is list and len(entries) == 10, 'policy_count')
    sources = {}
    for entry, (kind, version) in zip(entries, POLICIES.items()):
        closed(entry, 'policy_kind policy_version canonical_bytes')
        require(entry['policy_kind'] == kind and uint(entry['policy_version']) == version,
            'policy_order_or_version')
        encoded = entry['canonical_bytes']
        require(type(encoded) is str and 0 < len(encoded) <= 16384 and len(encoded) % 2 == 0,
            'policy_hex_length')
        pattern(encoded, r'[0-9a-f]+')
        source = bytes.fromhex(encoded)
        obj = unicode_parse(source, limit=8192)
        require(type(obj) is dict, 'policy_source_object')
        _source_context(obj, n, p['application'])
        sources[kind] = sha(source)

    b = p['reviewer_bootstrap']
    closed(b, 'bootstrap_version network_id reviewer_policy_digest reputation_rule_digest reviewers')
    require(uint(b['bootstrap_version']) == 1 and b['network_id'] == n, 'reviewer_profile')
    reviewers = b['reviewers']
    require(type(reviewers) is list and len(reviewers) <= 128, 'reviewer_count')
    for reviewer in reviewers:
        wallet(reviewer)
    require(reviewers == sorted(set(reviewers)), 'reviewer_order_or_duplicate')

    nb = p['native_bootstrap']
    closed(nb, 'native_state_version network_id total_supply initial_reward_pool allocations')
    require(uint(nb['native_state_version']) == 1 and nb['network_id'] == n, 'native_profile')
    total = decimal_units(nb['total_supply'], maximum=10**15)
    pool = decimal_units(nb['initial_reward_pool'], maximum=10**15)
    allocations = nb['allocations']
    require(type(allocations) is list and len(allocations) <= 4096, 'allocation_count')
    previous = ''
    for account in allocations:
        closed(account, 'wallet_address balance next_nonce')
        w = wallet(account['wallet_address'])
        require(w > previous, 'allocation_order_or_duplicate')
        previous = w
        require(type(account['next_nonce']) is str and account['next_nonce'] == '1', 'initial_nonce')
        pool += decimal_units(account['balance'], positive=True, maximum=10**15)
    require(pool == total, 'supply_conservation')

    h = p['history_bootstrap']
    closed(h, 'history_version bootstrap_events bootstrap_history_commitment initial_state initial_state_commitment')
    require(uint(h['history_version']) == 1 and type(h['bootstrap_events']) is list and
        h['bootstrap_events'] == [], 'clean_history')
    s = h['initial_state']
    closed(s, 'state_version policy_registry_digest reviewer_bootstrap_digest native_bootstrap_digest bootstrap_history_commitment')
    require(uint(s['state_version']) == 1, 'state_version')
    d = p['agreement_descriptor']
    require(type(d) is dict and 'application_policy_digest' in d, 'agreement_schema')
    require(components['agreement_descriptor'] == J(descriptor(d['application_policy_digest'])),
        'agreement_profile')
    require(type(p['validator_manifest']) is dict and p['validator_manifest'].get('network_id') == n,
        'manifest_network')
    m = Manifest(components['validator_manifest'])  # unchanged K key/ID/N4/f1/q3/epoch0 checks
    return e, components, sources, m


def _commitments(e, components, sources, manifest):
    p, n = e['payload'], e['network_id']
    for field, name in (('validator_set_commitment', 'validator_manifest'),
            ('agreement_profile_digest', 'agreement_descriptor'),
            ('policy_registry_digest', 'policy_registry')):
        _match(p[field], sha(components[name]), field)
    _match(p['agreement_descriptor']['application_policy_digest'], p['policy_registry_digest'], 'agreement_registry')
    b = p['reviewer_bootstrap']
    _match(b['reviewer_policy_digest'], sources['reviewer'], 'reviewer_source')
    _match(b['reputation_rule_digest'], sources['reputation'], 'reputation_source')
    for kind in ('reviewer', 'native'):
        _match(p[kind+'_bootstrap_digest'], sha(J(envelope(kind+'-bootstrap', p[kind+'_bootstrap'], n))),
            kind+'_bootstrap')
    h = p['history_bootstrap']
    hd = sha(J(envelope('history-bootstrap', dict(history_version=1, bootstrap_events=[]), n)))
    _match(h['bootstrap_history_commitment'], hd, 'history_bootstrap')
    s = h['initial_state']
    for name in ('policy_registry_digest', 'reviewer_bootstrap_digest', 'native_bootstrap_digest'):
        _match(s[name], p[name], 'initial_state_' + name)
    _match(s['bootstrap_history_commitment'], hd, 'initial_state_history')
    _match(h['initial_state_commitment'], sha(J(envelope('initial-state', s, n))), 'initial_state')


def verify_bytes(raw, *, trusted_pin):
    """Verify exact received bytes against an explicit independent test pin.

    Pass None explicitly for an absent pin: it never yields VALID. Unknown source
    semantics always remain incomplete. No cached authority argument exists.
    """
    try:
        if trusted_pin is not None and type(trusted_pin) is not TrustedGenesisPin:
            return Result(Outcome.WRONG_AUTHORITY, 'explicit_local_test_pin_required')
        e, components, sources, manifest = _structure(raw)
        _commitments(e, components, sources, manifest)
        g = sha(raw)  # ENTIRE file, no removed field, normalization, salt or prefix.
        evidence = dict(genesis_hash=g, canonical_envelope_verified=True,
            component_commitments_verified=True, incomplete_policies=INCOMPLETE,
            component_sizes=tuple((name, len(b)) for name, b in components.items()))
        if trusted_pin is None:
            return Result(Outcome.INCOMPLETE_AUTHORITY, 'independent_expected_identity_missing', **evidence)
        p = e['payload']
        if not (hmac.compare_digest(g, trusted_pin.genesis_hash) and
                e['network_id'] == trusted_pin.network_id and p['application'] == trusted_pin.application and
                e['protocol_version'] == trusted_pin.protocol_version and
                p['agreement_descriptor']['authority_profile'] == trusted_pin.authority_profile):
            return Result(Outcome.WRONG_AUTHORITY, 'independent_expected_identity_mismatch', **evidence)
        return Result(Outcome.INCOMPLETE_POLICY, 'test_envelope_only; policy_semantics_unapproved',
            pinned_test_identity_matched=True, manifest_bytes=components['validator_manifest'],
            agreement_bytes=components['agreement_descriptor'], **evidence)
    except _Mismatch as exc:
        return Result(Outcome.INVALID_COMMITMENT, str(exc))
    except AuthorityFailure as exc:
        return Result(Outcome.RESOURCE_FAILURE if exc.outcome == KOutcome.RESOURCE_FAILURE
            else Outcome.INVALID_STRUCTURE, str(exc))
    except V3Error as exc:
        return Result(Outcome.INVALID_STRUCTURE, str(exc))
    except (MemoryError, OSError) as exc:
        return Result(Outcome.RESOURCE_FAILURE, type(exc).__name__)


def verify_file(path, *, trusted_pin):
    """Bound local reads to limit+1. No network download or trust configuration."""
    try:
        with open(path, 'rb') as f:
            raw = f.read(GENESIS_LIMIT + 1)
    except OSError:
        return Result(Outcome.IO_FAILURE, 'genesis_read_failed')
    except MemoryError:
        return Result(Outcome.RESOURCE_FAILURE, 'genesis_read_memory')
    return verify_bytes(raw, trusted_pin=trusted_pin)
