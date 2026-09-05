"""Milestone 3.7: concurrent certified minting, recovery, and convergence."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from multiprocessing import get_context
from threading import Barrier, Thread
from time import perf_counter

import pytest
from eth_account import Account
from eth_account.messages import encode_defunct

from blockchain import Blockchain
from services import LifecycleTimingRecorder
from peer_sync import sync_chain_from_peers
from peers import PeerStore
from protocol_v1_finality import (
    build_protocol_v1_finality_attestation,
    build_protocol_v1_finality_attestation_message,
)
from protocol_v1 import PROTOCOL_VERSION, PUBLIC_TESTNET_V1_NETWORK_ID
from storage import create_storage_backend


WORKLOAD_SIZE = 100
APPROVAL_WORKER_COUNT = WORKLOAD_SIZE
COMMIT_WORKER_COUNT = 4
FINALITY_BATCH_SIZE = 8
FINALITY_WORKER_COUNT = 4


class InjectedCommitFailure(RuntimeError):
    pass


def _backend(tmp_path, name, backend_name="sqlite"):
    node_dir = tmp_path / name
    node_dir.mkdir()
    return create_storage_backend(
        backend_name,
        blockchain_file=str(node_dir / "blockchain.json"),
        peers_file=str(node_dir / "peers.json"),
        sqlite_db_path=str(node_dir / "zoidbergchain.db"),
    )


def _node(wallets, backend, lifecycle_timing=None):
    return Blockchain(
        project_owner_wallet=wallets["owner"],
        Contributor_one=wallets["contributor_one"],
        Contributor_two=wallets["contributor_two"],
        storage_backend=backend,
        lifecycle_timing=lifecycle_timing,
    )


def _ready_submissions_concurrently(node, wallets, workload_size=WORKLOAD_SIZE):
    """Create the 100 candidates, then certify and queue them behind a gate."""
    submissions = []
    for index in range(workload_size):
        submission = node.submit_content(
            image_path="",
            text_content=f"Task 3.7 concurrent certified text payload {index:03d}",
            submitter=wallets["owner"].public_key,
        )
        submissions.append(submission)

    # Media is a prerequisite, not the concurrent state under test.  Promote
    # it once before the gate so 100 certification workers do not race to
    # atomically replace the same content-cache file on Windows.
    for submission in submissions:
        node.promote_submission_content_for_protocol_v1(submission)

    for submission in submissions:
        # Vote creation is deliberately part of the real workflow.  Reuse the
        # same independent validator identities across submissions; one
        # identity may vote once per submission while the dynamic threshold
        # remains stable for the batch.
        for vote_index in range(5):
            node.cast_submission_vote(
                submission.submission_id,
                voter=f"task-3-7-voter-{vote_index}",
                vote_type="original",
                created_at=3_700_000 + vote_index,
            )

    approval_workers = min(APPROVAL_WORKER_COUNT, workload_size)
    gate = Barrier(approval_workers)

    def certify(submission):
        gate.wait()
        result = node.evaluate_submission(
            submission.submission_id,
            automated_originality_passed=True,
            now=3_700_100,
        )
        return submission.submission_id, result

    # The setup phase uses the same evaluation/certificate/queue methods as a
    # node, but defers their ordinary whole-document checkpoints until all
    # workers have crossed the readiness gate.  Certified preparation remains
    # concurrent; a single checkpoint keeps fixture construction from testing
    # the unrelated legacy save path rather than Task 3.7's atomic commit path.
    save_blockchain = node.save_blockchain
    node.save_blockchain = lambda: None
    started = perf_counter()
    try:
        with ThreadPoolExecutor(max_workers=approval_workers) as executor:
            futures = [executor.submit(certify, submission) for submission in submissions]
            certified = [future.result() for future in as_completed(futures)]
    finally:
        node.save_blockchain = save_blockchain
    assert all(result["status"] == "approved" for _, result in certified)
    # Queue admission uses its normal durable implementation after the
    # simultaneous approval/certificate phase has completed.
    for submission_id, _ in certified:
        node.add_to_mint_queue(submission_id)
    node.save_blockchain()
    return submissions, [submission_id for submission_id, _ in certified], perf_counter() - started


def _commit_all_concurrently(wallets, backend, lifecycle_timing=None, on_committed=None):
    """Workers repeatedly prepare the current canonical queue head and CAS it."""
    nodes = [_node(wallets, backend, lifecycle_timing) for _ in range(COMMIT_WORKER_COUNT)]
    gate = Barrier(COMMIT_WORKER_COUNT)

    def worker(node):
        gate.wait()
        outcomes = []
        while True:
            outcome = node.commit_next_certified_submission_with_retry(
                miner=wallets["contributor_one"].public_key,
                # Originality was already certified concurrently above; the
                # commit still validates its certificate and canonical media.
                validate_meme=False,
            )
            if not outcome["committed"]:
                return outcomes
            outcomes.append(outcome)
            if on_committed is not None:
                on_committed(outcome)

    started = perf_counter()
    with ThreadPoolExecutor(max_workers=COMMIT_WORKER_COUNT) as executor:
        results = [future.result() for future in as_completed([executor.submit(worker, node) for node in nodes])]
    return [item for worker_results in results for item in worker_results], perf_counter() - started


def _start_prompt_finality_coordinator(wallets, backend, lifecycle_timing, tmp_path):
    """Finalize each accepted submission on a validator replica without delaying commits.

    The queue receives an accepted submission immediately from the committing
    worker.  Independent validator replicas own disjoint deterministic shards
    of the received blocks, which models safe distributed validator work while
    canonical commit workers continue independently against the primary store.
    """
    validators = [Account.create() for _ in range(3)]
    validator_set = tuple(sorted(account.address.lower() for account in validators))
    validator_backends = []
    submitted = []
    for index in range(FINALITY_WORKER_COUNT):
        validator_backend = _backend(tmp_path, f"task-3-8-finality-validator-{index}")
        validator_backends.append(validator_backend)
    process_context = get_context("spawn")
    submitted = [process_context.Queue() for _ in range(FINALITY_WORKER_COUNT)]
    completed = process_context.Queue()
    backend_paths = (backend.blockchain_file, backend.peers_file, backend.sqlite_db_path)
    workers = [
        process_context.Process(
            target=_prompt_finality_process,
            args=(
                wallets,
                backend_paths,
                (validator_backend.blockchain_file, validator_backend.peers_file, validator_backend.sqlite_db_path),
                [account.key.hex() for account in validators],
                submitted[index],
                completed,
            ),
            name=f"task-3-8-finality-{index}",
        )
        for index, validator_backend in enumerate(validator_backends)
    ]
    for worker in workers:
        worker.start()
    errors = []
    completed_count = 0

    def record_finality():
        nonlocal completed_count
        while completed_count < FINALITY_WORKER_COUNT:
            event = completed.get()
            if event[0] == "finalized":
                _, submission_id, height, block_hash = event
                lifecycle_timing.mark(submission_id, "finalized", block_height=height, block_hash=block_hash)
            elif event[0] == "error":
                errors.append(event[1])
            elif event[0] == "done":
                completed_count += 1

    listener = Thread(target=record_finality, name="task-3-8-finality-results", daemon=True)
    listener.start()

    def accepted(outcome):
        submission_id = outcome["submission_id"]
        submitted[sum(str(submission_id).encode("utf-8")) % FINALITY_WORKER_COUNT].put(submission_id)

    def finish():
        for queue in submitted:
            queue.put(None)
        for worker in workers:
            worker.join()
            if worker.exitcode:
                errors.append(f"finality worker exited with code {worker.exitcode}")
        listener.join()
        if errors:
            raise AssertionError(errors[0])
        return validator_backends, validators, validator_set

    return accepted, finish


def _finality_attestation(account, block):
    message = build_protocol_v1_finality_attestation_message(
        validator_address=account.address,
        block_height=block.index,
        block_hash=block.hash,
        network_id=PUBLIC_TESTNET_V1_NETWORK_ID,
    )
    signature = Account.sign_message(encode_defunct(text=message), account.key).signature.hex()
    return build_protocol_v1_finality_attestation(
        validator_address=account.address,
        block_height=block.index,
        block_hash=block.hash,
        network_id=PUBLIC_TESTNET_V1_NETWORK_ID,
        signature=signature,
    )


def _prompt_finality_process(wallets, primary_paths, validator_paths, validator_keys, submitted, completed):
    """Own one validator replica in a separate process for the lifecycle run."""
    try:
        primary = create_storage_backend(
            "sqlite",
            blockchain_file=primary_paths[0],
            peers_file=primary_paths[1],
            sqlite_db_path=primary_paths[2],
        )
        validator_backend = create_storage_backend(
            "sqlite",
            blockchain_file=validator_paths[0],
            peers_file=validator_paths[1],
            sqlite_db_path=validator_paths[2],
        )
        validator = _node(wallets, validator_backend)
        accounts = [Account.from_key(key) for key in validator_keys]
        validator.validator_set = tuple(sorted(account.address.lower() for account in accounts))

        def finalize_batch(submission_ids):
            canonical_state = primary.load_blockchain_state()
            attestations = list(validator.finality_attestations)
            finalized_blocks = list(validator.finalized_blocks)
            validator._restore_blockchain_state_document(canonical_state)
            validator.finality_attestations = attestations
            validator.finalized_blocks = finalized_blocks
            blocks = []
            for submission_id in submission_ids:
                block = validator.get_protocol_v1_block_for_submission(submission_id)
                if block is None:
                    raise AssertionError(f"accepted submission was not found on the canonical chain: {submission_id}")
                blocks.append(block)
            validator.submit_validator_finality_attestations(
                [
                    _finality_attestation(account, block)
                    for block in blocks
                    for account in accounts[:2]
                ]
            )
            for block in blocks:
                completed.put(("finalized", block.submission_id, block.index, block.hash))

        pending = []
        while True:
            submission_id = submitted.get()
            if submission_id is None:
                if pending:
                    finalize_batch(pending)
                break
            pending.append(submission_id)
            if len(pending) >= FINALITY_BATCH_SIZE:
                finalize_batch(pending)
                pending = []
    except Exception as exc:
        completed.put(("error", repr(exc)))
    finally:
        completed.put(("done",))


def _sync_peer(monkeypatch, source, target, peer_file):
    def fake_get(url, params=None, timeout=None):
        if url.endswith("/chain/summary"):
            latest = source.get_latest_block()
            return _Response({
                "network_name": "zoidberg-testnet",
                "network_id": PUBLIC_TESTNET_V1_NETWORK_ID,
                "protocol_version": PROTOCOL_VERSION,
                "node_id": "task-3-7-source",
                "chain_height": latest.index,
                "latest_block_hash": latest.hash,
                "genesis_hash": source.chain[0].hash,
            })
        if url.endswith("/chain/blocks"):
            from_height = params["from_height"]
            blocks = [block for block in source.chain if block.index >= from_height]
            certificate_ids = {block.certificate_id for block in blocks if block.certificate_id}
            return _Response({
                "blocks": [block.to_dict() for block in blocks],
                "certificates": [
                    certificate.to_dict() for certificate in source.originality_certificates
                    if certificate.certificate_id in certificate_ids
                ],
            })
        raise AssertionError(f"unexpected peer request: {url}")

    monkeypatch.setattr("peer_sync.requests.get", fake_get)
    peers = PeerStore(file_path=str(peer_file))
    peers.register_peer(node_id="task-3-7-source", url="http://task-3-7-source.test:8000", network_name="zoidberg-testnet")
    return sync_chain_from_peers(target, peers, network_name="zoidberg-testnet")


class _Response:
    def __init__(self, payload):
        self._payload = payload
        self.status_code = 200
        self.text = str(payload)

    def json(self):
        return self._payload


def _assert_canonical_workload(document, expected_order):
    blocks = document["chain"][1:]
    workload_size = len(expected_order)
    assert len(blocks) == workload_size
    assert [block["index"] for block in blocks] == list(range(1, workload_size + 1))
    assert len({block["index"] for block in blocks}) == workload_size
    assert all(block["previous_hash"] == document["chain"][index]["hash"] for index, block in enumerate(blocks))
    assert [block["submission_id"] for block in blocks] == expected_order
    assert len({block["submission_id"] for block in blocks}) == workload_size
    assert len({block["certificate_id"] for block in blocks}) == workload_size
    creator_rewards = [
        (block["submission_id"], block["reward_recipient"], block["reward_amount"])
        for block in blocks
    ]
    assert len(creator_rewards) == len(set(creator_rewards)) == workload_size
    voter_rewards = [reward["reward_id"] for block in blocks for reward in block.get("voter_rewards", [])]
    assert len(voter_rewards) == len(set(voter_rewards))
    native_transactions = [tx for block in blocks for tx in block.get("native_transactions", [])]
    assert len({tx["tx_id"] for tx in native_transactions}) == len(native_transactions)
    assert len({(tx["from_address"], str(tx["nonce"])) for tx in native_transactions}) == len(native_transactions)


def test_100_concurrent_certified_approvals_are_linear_recoverable_and_finalized(
    isolated_data_dir, wallets, monkeypatch, record_property
):
    """The Task 3.7 SQLite benchmark; assertions are deliberately non-optional."""
    workload_started = perf_counter()
    lifecycle_timing = LifecycleTimingRecorder()
    backend = _backend(isolated_data_dir, "task-3-7-sqlite")
    coordinator = _node(wallets, backend, lifecycle_timing)
    submissions, certified, approval_duration = _ready_submissions_concurrently(coordinator, wallets)
    assert len(certified) == WORKLOAD_SIZE
    coordinator._restore_blockchain_state_document(backend.load_blockchain_state())
    expected_order = [entry["submission_id"] for entry in coordinator.get_mint_queue(mintable_only=True)]
    assert len(expected_order) == WORKLOAD_SIZE
    on_committed, finish_finality = _start_prompt_finality_coordinator(
        wallets,
        backend,
        lifecycle_timing,
        isolated_data_dir,
    )

    # A pre-commit failure leaves the complete durable document unchanged and
    # the selected submission eligible for the concurrent retry phase.
    before_precommit_failure = deepcopy(backend.load_blockchain_state())
    coordinator._atomic_commit_fault_injector = lambda stage: (_ for _ in ()).throw(InjectedCommitFailure(stage)) if stage == "before_transaction_commit" else None
    with pytest.raises(InjectedCommitFailure, match="before_transaction_commit"):
        coordinator.commit_next_certified_submission_with_retry(miner=wallets["contributor_one"].public_key, validate_meme=False)
    del coordinator._atomic_commit_fault_injector
    assert backend.load_blockchain_state() == before_precommit_failure

    # The commit succeeds but the caller loses its result.  Task 3.4 replay
    # resolves the same logical request without another transition.
    coordinator._atomic_commit_fault_injector = lambda stage: (_ for _ in ()).throw(ConnectionError("lost commit result")) if stage == "after_durable_commit_before_response" else None
    with pytest.raises(ConnectionError, match="lost commit result"):
        coordinator.commit_next_certified_submission_with_retry(miner=wallets["contributor_one"].public_key, validate_meme=False)
    del coordinator._atomic_commit_fault_injector
    after_lost_response = deepcopy(backend.load_blockchain_state())
    assert coordinator.commit_certified_submission(
        expected_order[0],
        miner=wallets["contributor_one"].public_key,
        validate_meme=False,
    ) is True
    assert backend.load_blockchain_state() == after_lost_response
    on_committed({"submission_id": expected_order[0]})

    finality_started = perf_counter()
    outcomes, commit_duration = _commit_all_concurrently(
        wallets,
        backend,
        lifecycle_timing,
        on_committed=on_committed,
    )
    validator_backends, validators, validator_set = finish_finality()
    finality_duration = perf_counter() - finality_started
    document = backend.load_blockchain_state()
    _assert_canonical_workload(document, expected_order)

    # Replaying representative committed requests is a no-op, even after the
    # high-contention workload and its uncertain outcome.
    replay_node = _node(wallets, backend)
    before_replays = deepcopy(backend.load_blockchain_state())
    for submission_id in expected_order[::25]:
        assert replay_node.commit_certified_submission(
            submission_id,
            miner=wallets["contributor_one"].public_key,
            validate_meme=False,
        ) is True
    assert backend.load_blockchain_state() == before_replays
    assert after_lost_response["chain"][1]["submission_id"] == expected_order[0]

    final_block_hash = document["chain"][-1]["hash"]
    source_backend = validator_backends[
        sum(str(expected_order[-1]).encode("utf-8")) % FINALITY_WORKER_COUNT
    ]
    source = _node(wallets, source_backend, lifecycle_timing)
    source.validator_set = validator_set
    assert source.get_finality_evidence(final_block_hash) is not None
    # Synchronize the promptly-finalizing validator chain to an independent
    # node and prove finality convergence without delaying lifecycle marks.
    peer_backend = _backend(isolated_data_dir, "task-3-7-peer")
    peer = _node(wallets, peer_backend)
    sync_result = _sync_peer(monkeypatch, source, peer, isolated_data_dir / "task-3-7-peers.json")
    if sync_result["synced"] < 1:
        raise AssertionError(repr(sync_result))
    assert [block.hash for block in peer.chain] == [block.hash for block in source.chain]

    peer.validator_set = validator_set
    final_block = source.get_latest_block()
    for attestation in reversed([_finality_attestation(account, final_block) for account in validators[:2]]):
        peer.submit_validator_finality_attestation(attestation)
    assert source.get_finalized_head() == peer.get_finalized_head() == {"block_height": 100, "block_hash": final_block.hash}
    assert source.get_finality_evidence(final_block.hash) == peer.get_finality_evidence(final_block.hash)

    # Benchmark-level measurements are left on the test item for a concise
    # failure report/CI hook without adding Task 3.8 production telemetry.
    total_stale = sum(item["stale_head_retries"] for item in outcomes)
    total_busy = sum(item["sqlite_busy_retries"] for item in outcomes)
    max_retries = max(item["retries"] for item in outcomes)
    total_duration = perf_counter() - workload_started
    assert approval_duration >= 0 and commit_duration > 0 and finality_duration >= 0
    assert total_stale >= 0 and total_busy >= 0 and max_retries >= 0
    record_property("approval_worker_count", APPROVAL_WORKER_COUNT)
    record_property("commit_worker_count", COMMIT_WORKER_COUNT)
    record_property("total_workload_duration_seconds", f"{total_duration:.6f}")
    record_property("commit_duration_seconds", f"{commit_duration:.6f}")
    record_property("blocks_per_second", f"{WORKLOAD_SIZE / commit_duration:.6f}")
    record_property("stale_head_retries", total_stale)
    record_property("sqlite_busy_retries", total_busy)
    record_property("maximum_submission_retries", max_retries)
    record_property("finality_duration_seconds", f"{finality_duration:.6f}")
    record_property("finalized_height", final_block.index)
    record_property("finalized_hash", final_block.hash)
    records = lifecycle_timing.completed_records()
    assert len(records) == WORKLOAD_SIZE
    def duration(records, start, end):
        return sorted((record["stages"][end] - record["stages"][start]) / 1_000_000_000 for record in records)
    def percentile(values, fraction):
        return values[max(0, math.ceil(fraction * len(values)) - 1)]
    import math
    for name, start, end in (
        ("vote_to_certificate", "vote_passed", "certificate_created"),
        ("certificate_to_ready", "certificate_created", "ready_for_mint"),
        ("ready_to_proposal", "ready_for_mint", "proposal_prepared"),
        ("proposal_to_accepted", "proposal_prepared", "accepted"),
        ("certificate_to_accepted", "certificate_created", "accepted"),
        ("accepted_to_finalized", "accepted", "finalized"),
        ("vote_to_finalized", "vote_passed", "finalized"),
    ):
        values = duration(records, start, end)
        for label, value in (("count", len(values)), ("min", values[0]), ("p50", percentile(values, .50)), ("p95", percentile(values, .95)), ("p99", percentile(values, .99)), ("max", values[-1])):
            record_property(f"lifecycle_{name}_{label}", value if label == "count" else f"{value:.9f}")


def test_json_backend_concurrent_retry_preserves_linear_order_and_replay(isolated_data_dir, wallets):
    """Exercise the same concurrent coordinator on JSON without benchmarking it."""
    backend = _backend(isolated_data_dir, "task-3-7-json", backend_name="json")
    coordinator = _node(wallets, backend)
    _, certified, _ = _ready_submissions_concurrently(coordinator, wallets, workload_size=8)
    assert len(certified) == 8
    coordinator._restore_blockchain_state_document(backend.load_blockchain_state())
    expected_order = [entry["submission_id"] for entry in coordinator.get_mint_queue(mintable_only=True)]

    before_failure = deepcopy(backend.load_blockchain_state())
    coordinator._atomic_commit_fault_injector = lambda stage: (_ for _ in ()).throw(InjectedCommitFailure(stage)) if stage == "before_transaction_commit" else None
    with pytest.raises(InjectedCommitFailure):
        coordinator.commit_next_certified_submission_with_retry(miner=wallets["contributor_one"].public_key, validate_meme=False)
    del coordinator._atomic_commit_fault_injector
    assert backend.load_blockchain_state() == before_failure

    _commit_all_concurrently(wallets, backend)
    _assert_canonical_workload(backend.load_blockchain_state(), expected_order)
    before_replay = deepcopy(backend.load_blockchain_state())
    assert coordinator.commit_certified_submission(
        expected_order[0], miner=wallets["contributor_one"].public_key, validate_meme=False
    ) is True
    assert backend.load_blockchain_state() == before_replay
