"""Task 7.17C historical diagnostics, including the pre-7.17E defects.

These passing assertions reproduce audit findings; they are not desired future
consensus requirements. Task 7.17E preserves their assertions using the exact
pre-repair facade method snapshot and explicitly bypasses its new storage guard.
Current durability assertions live in the separate Task 7.17E suite. The service
and cryptographic diagnostics still exercise the unchanged agreement semantics.
Structural tests assume authenticated votes by replacing
only signature recovery. They generate no keys/signatures, do not validate full
media chains, and use synthetic chain targets. One separate test verifies the
unchanged published v2 proof with real recovery. No production module is edited.
"""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
from types import SimpleNamespace
from threading import Barrier

import pytest

from blockchain import Blockchain
from canonical_v3 import finality
from canonical_v3.primitives import Context, V3Error
from protocol_v1 import PUBLIC_TESTNET_V1_NETWORK_ID as NETWORK
from protocol_v1_finality import build_protocol_v1_finality_attestation
from services import FinalityAttestationError, FinalityService
from services.canonical_reorg_service import CanonicalReorgService
from services.peer_chain_sync_service import PeerChainSyncService
from storage import create_storage_backend
from finality_717c_baseline import HistoricalFinalityBlockchain


FIXTURES = Path(__file__).parent / 'fixtures' / 'milestone_7_v3_v1'
# Public identities only. No key material or real new signatures are used.
VALIDATORS = tuple('0x' + digit * 40 for digit in '1234')


@pytest.fixture(autouse=True)
def historical_storage_boundary(monkeypatch):
    """Reproduce the explicitly version-pinned OLD document-write contract."""
    monkeypatch.setattr('storage._preserve_finality', lambda durable, replacement, **kwargs: replacement)


@pytest.fixture
def authenticated_votes(monkeypatch):
    """Assume authentic signatures; preserve all production message checks."""
    monkeypatch.setattr('services.finality_service.recover_signed_wallet_address',
                        lambda message, signature: json.loads(message)['payload']['validator_address'])

    def vote(validator, target='a' * 64, height=0):
        return build_protocol_v1_finality_attestation(
            validator_address=validator, block_height=height, block_hash=target,
            network_id=NETWORK, signature='diagnostic-crypto-boundary-stub')
    return vote


def collect(votes, validators, target='a' * 64, height=0):
    service = FinalityService()
    retained, proofs = [], []
    result = None
    for vote in votes:
        result = service.process_attestation(
            vote, validator_set=validators, expected_network_id=NETWORK,
            canonical_block={'index': height, 'hash': target},
            existing_attestations=retained, finalized_blocks=proofs)
        if result['status'] != 'duplicate':
            retained.append(result['attestation'])
        if result['finalization'] is not None:
            proofs.append(result['finalization'])
    return result, retained, proofs


def facade(validators, storage=None, targets=('a' * 64,)):
    """Use real finality facade/save methods, stub unrelated chain/media work."""
    node = HistoricalFinalityBlockchain.__new__(HistoricalFinalityBlockchain)
    node.validator_set = validators
    node.finality_attestations, node.finalized_blocks = [], []
    node._finality_service = FinalityService()
    node.chain = [SimpleNamespace(index=h, hash=target,
                  to_dict=lambda h=h, target=target: {'index': h, 'hash': target})
                  for h, target in enumerate(targets)]
    node.is_chain_valid = lambda chain: True
    node.calculate_hash_from_dict = lambda block: block['hash']
    node.protocol_v1_network_id = lambda: NETWORK
    node._report_reviewer_index = {}
    node._set_report_reviewer_index = lambda *args, **kwargs: None
    node.reconcile_canonical_reviewer_states = lambda: None
    node._serialize_blockchain_state = lambda: deepcopy(dict(
        chain=node.chain_to_dicts(node.chain), submissions=[], mint_queue=[],
        finality_attestations=node.finality_attestations,
        finalized_blocks=node.finalized_blocks))
    if storage is None:
        node.save_blockchain = lambda: None
    else:
        node.storage = storage
    return node


def test_conflicting_quorums_with_one_equivocator_in_three(authenticated_votes):
    vote = authenticated_votes
    validators = VALIDATORS[:3]
    first, _, _ = collect([vote(v) for v in validators[:2]], validators)
    second, _, _ = collect([vote(v, 'b' * 64) for v in validators[1:]], validators, 'b' * 64)
    for result in (first, second):
        FinalityService().validate_finalization_evidence(result['finalization'], expected_network_id=NETWORK)
    assert first['finalization']['block_hash'] != second['finalization']['block_hash']
    # Only the shared signer double-voted; local observations never see the pair.
    assert first['required_quorum'] == second['required_quorum'] == 2


def test_verifier_does_not_enforce_signer_side_non_equivocation(authenticated_votes):
    votes = authenticated_votes
    first, _, _ = collect([votes(v) for v in VALIDATORS[:3]], VALIDATORS)
    second, _, _ = collect([votes(v, 'b' * 64) for v in VALIDATORS[:3]], VALIDATORS, 'b' * 64)
    assert first['finalization'] and second['finalization']


def test_incompatible_cross_height_proofs_need_no_same_height_double_vote(authenticated_votes):
    # Two valid branch targets are assumed, with b@1 -> c@2 on the second
    # branch. The first branch's a@1 QC is withheld from the second receiver.
    first_votes = [authenticated_votes(v, 'a' * 64, 1) for v in VALIDATORS[:2]]
    second_votes = [authenticated_votes(v, 'c' * 64, 2) for v in VALIDATORS[1:3]]
    first, _, _ = collect(first_votes, VALIDATORS[:3], 'a' * 64, 1)
    second, _, _ = collect(second_votes, VALIDATORS[:3], 'c' * 64, 2)
    for result in (first, second):
        FinalityService().validate_finalization_evidence(result['finalization'], expected_network_id=NETWORK)
    second_branch = [{'index': 0, 'hash': '0' * 64},
                     {'index': 1, 'hash': 'b' * 64, 'previous_hash': '0' * 64},
                     {'index': 2, 'hash': 'c' * 64, 'previous_hash': 'b' * 64}]
    assert not Blockchain._candidate_preserves_finality_records(second_branch, [first['finalization']])
    _, equivocators = FinalityService().votes_for_block(first_votes + second_votes,
        validator_set=VALIDATORS[:3], expected_network_id=NETWORK, block_height=1, block_hash='a' * 64)
    assert not equivocators
    assert {v['block_height'] for v in first_votes + second_votes} == {1, 2}


def test_split_first_votes_and_exact_retries_do_not_reach_quorum(authenticated_votes):
    vote = authenticated_votes
    for target, validators in [('a' * 64, VALIDATORS[:2]), ('b' * 64, VALIDATORS[2:])]:
        result, retained, _ = collect([vote(v, target) for v in validators], VALIDATORS, target)
        assert result['vote_count'] == 2 and result['required_quorum'] == 3
        assert result['finalization'] is None
        retry = FinalityService().process_attestation(retained[0], validator_set=VALIDATORS,
            expected_network_id=NETWORK, canonical_block={'index': 0, 'hash': target},
            existing_attestations=retained, finalized_blocks=[])
        assert retry['status'] == 'duplicate' and retry['finalization'] is None


def test_local_equivocation_changes_live_count_but_not_retained_proof(authenticated_votes):
    vote = authenticated_votes
    result, retained, _ = collect([vote(v) for v in VALIDATORS[:2]], VALIDATORS[:3])
    counted, excluded = FinalityService().votes_for_block(retained + [vote(VALIDATORS[0], 'b' * 64)],
        validator_set=VALIDATORS[:3], expected_network_id=NETWORK, block_height=0, block_hash='a' * 64)
    assert len(counted) == 1 and excluded == {VALIDATORS[0]}
    assert FinalityService().validate_finalization_evidence(
        result['finalization'], expected_network_id=NETWORK) == result['finalization']


def test_persisted_v1_proof_trusts_its_own_validator_set(authenticated_votes):
    result, _, _ = collect([authenticated_votes(VALIDATORS[0])], VALIDATORS[:1])
    node = facade(VALIDATORS[1:])
    node.finalized_blocks = [result['finalization']]
    node._validate_persisted_finality_state()
    assert set(node.validator_set).isdisjoint(node.finalized_blocks[0]['validator_set'])


@pytest.mark.parametrize('batch', [False, True])
def test_new_vote_after_quorum_preserves_single_finalized_height(authenticated_votes, batch):
    node = facade(VALIDATORS[:3])
    votes = [authenticated_votes(v) for v in node.validator_set]
    if batch:
        node.submit_validator_finality_attestations(votes)
    else:
        for vote in votes:
            node.submit_validator_finality_attestation(vote)
    assert len(node.finalized_blocks) == 1
    assert len(node.finality_attestations) == 3
    node._validate_persisted_finality_state()


def test_child_finality_does_not_require_parent_proof(authenticated_votes):
    node = facade(VALIDATORS[:3], targets=('a' * 64, 'b' * 64))
    node.submit_validator_finality_attestations([
        authenticated_votes(v, 'b' * 64, 1) for v in node.validator_set[:2]])
    assert [proof['block_height'] for proof in node.finalized_blocks] == [1]


def test_reorganization_removes_detached_attestation_memory(authenticated_votes):
    document = dict(finalized_blocks=[], finality_attestations=[
        authenticated_votes(VALIDATORS[0], 'a' * 64, 1)])
    report = CanonicalReorgService._reconcile_finality(document,
        [{'index': 0, 'hash': 'c' * 64}, {'index': 1, 'hash': 'b' * 64}])
    assert report['removed_noncanonical_attestations'] == 1
    assert document['finality_attestations'] == []


@pytest.mark.parametrize('backend', ['json', 'sqlite'])
def test_stale_whole_document_save_erases_durable_finality(authenticated_votes, tmp_path, backend):
    storage = create_storage_backend(backend, blockchain_file=str(tmp_path / 'chain.json'),
        peers_file=str(tmp_path / 'peers.json'), sqlite_db_path=str(tmp_path / 'chain.db'))
    current, stale = facade(VALIDATORS[:3], storage), facade(VALIDATORS[:3], storage)
    current.submit_validator_finality_attestations([
        authenticated_votes(v) for v in current.validator_set[:2]])
    assert len(storage.load_blockchain_document()['finalized_blocks']) == 1
    stale.save_blockchain()
    durable = storage.load_blockchain_document()
    assert durable['finalized_blocks'] == [] and durable['finality_attestations'] == []


def test_failed_save_leaves_in_memory_finality_and_duplicate_retry_does_not_save(authenticated_votes):
    node = facade(VALIDATORS[:1])
    calls = []
    def fail():
        calls.append('attempt')
        raise OSError('diagnostic precommit failure')
    node.save_blockchain = fail
    vote = authenticated_votes(VALIDATORS[0])
    with pytest.raises(OSError, match='precommit'):
        node.submit_validator_finality_attestation(vote)
    assert len(node.finalized_blocks) == 1
    result = node.submit_validator_finality_attestation(vote)
    assert result['status'] == 'duplicate' and result['finalization']
    assert calls == ['attempt']


def test_concurrent_attestation_calls_can_lose_a_quorum_vote(authenticated_votes, tmp_path):
    storage = create_storage_backend('json', blockchain_file=str(tmp_path / 'chain.json'),
        peers_file=str(tmp_path / 'peers.json'), sqlite_db_path=str(tmp_path / 'unused.db'))
    node = facade(VALIDATORS[:3], storage)
    process = node._finality_service.process_attestation
    barrier = Barrier(2)
    def interleave(*args, **kwargs):
        # Both facade invocations have copied the same empty retained state.
        barrier.wait(timeout=10)
        return process(*args, **kwargs)
    node._finality_service.process_attestation = interleave
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(node.submit_validator_finality_attestation,
                                   [authenticated_votes(v) for v in VALIDATORS[:2]]))
    assert all(result['vote_count'] == 1 for result in results)
    assert len(node.finality_attestations) == 1 and node.finalized_blocks == []
    durable = storage.load_blockchain_document()
    assert len(durable['finality_attestations']) == 1 and durable['finalized_blocks'] == []


def test_peer_block_fetch_does_not_transfer_finality_even_if_peer_supplies_it():
    response = SimpleNamespace(status_code=200, json=lambda: dict(
        blocks=[{'index': 0}], certificates=[], originality_evidence=[],
        finalized_blocks=[{'diagnostic': 'supplied-but-unconsumed'}]))
    service = PeerChainSyncService(SimpleNamespace(get=lambda *args, **kwargs: response),
                                   lambda *args, **kwargs: {}, None)
    fetched = service.fetch_blocks({'url': 'http://diagnostic.invalid'}, 0,
        origin_node_id='diagnostic', network_name='zoidberg-testnet', timeout_seconds=1)
    assert set(fetched) == {'blocks', 'certificates', 'originality_evidence'}


def test_existing_v2_signature_proof_depends_on_external_equivocator_context():
    proof = json.loads((FIXTURES / 'finality-proof.json').read_bytes())
    context = Context(**json.loads((FIXTURES / 'manifest.json').read_bytes())['context'])
    kwargs = dict(trusted_validators=tuple(proof['validator_set']),
                  block_height=proof['block_height'], block_hash=proof['block_hash'])
    finality.validate_proof(proof, context, equivocators=frozenset(), **kwargs)
    with pytest.raises(V3Error, match='finality_membership'):
        finality.validate_proof(proof, context, equivocators=frozenset(proof['validator_set']), **kwargs)


def test_existing_v2_proof_rejects_invalid_signature_and_wrong_trusted_set():
    proof = json.loads((FIXTURES / 'finality-proof.json').read_bytes())
    context = Context(**json.loads((FIXTURES / 'manifest.json').read_bytes())['context'])
    kwargs = dict(trusted_validators=tuple(proof['validator_set']), equivocators=frozenset(),
                  block_height=proof['block_height'], block_hash=proof['block_hash'])
    wrong_signature = deepcopy(proof)
    wrong_signature['attestations'][0]['signature'] = '0x00'
    with pytest.raises(V3Error):
        finality.validate_proof(wrong_signature, context, **kwargs)
    with pytest.raises(V3Error):
        finality.validate_proof(proof, context, **dict(kwargs, trusted_validators=VALIDATORS[:1]))
