import pytest

from blockchain import Blockchain
from storage import create_storage_backend
from submission import APPROVED, MINTED, PENDING, QUEUED, Submission


def _certify_submission(blockchain, submission):
    for vote_index in range(5):
        blockchain.cast_submission_vote(
            submission_id=submission.submission_id,
            voter=f"mint-voter-{submission.submission_id}-{vote_index}",
            vote_type="original",
            created_at=1_000_000 + vote_index,
        )
    submission.transition_to(APPROVED)
    blockchain.create_originality_certificate(submission.submission_id, approved_at=1_000_100)


def _new_ordering_node(tmp_path, name, wallets):
    node_dir = tmp_path / name
    node_dir.mkdir()
    storage = create_storage_backend(
        blockchain_file=str(node_dir / "blockchain.json"),
        peers_file=str(node_dir / "peers.json"),
        sqlite_db_path=str(node_dir / "zoidbergchain.db"),
    )
    return Blockchain(
        project_owner_wallet=wallets["owner"],
        Contributor_one=wallets["contributor_one"],
        Contributor_two=wallets["contributor_two"],
        storage_backend=storage,
    )


def _add_ready_submissions_in_order(node, submission_image, wallets, indexes):
    for index in indexes:
        submission = node.submit_content(
            image_path=str(submission_image),
            text_content=f"Independent node ordering content {index}",
            submitter=wallets["owner"].public_key,
        )
        submission.submission_id = f"ordering-node-submission-{index}"
        _certify_submission(node, submission)
        node.add_to_mint_queue(submission.submission_id)


@pytest.fixture
def approved_submissions(blockchain, submission_image, wallets):
    submissions = []
    for index in range(3):
        submission = blockchain.submit_content(
            image_path=str(submission_image),
            text_content=f"Mint queue content {index}",
            submitter=wallets["owner"].public_key,
        )
        _certify_submission(blockchain, submission)
        submissions.append(submission)
    return submissions


def test_mint_queue_insertion(blockchain, approved_submissions):
    submission = approved_submissions[0]

    queued_submission = blockchain.add_to_mint_queue(submission.submission_id)

    assert queued_submission.status == QUEUED
    assert blockchain.mint_queue == [submission.submission_id]


def test_mint_queue_ordering(blockchain, approved_submissions):
    observed_orders = []
    insertion_orders = [
        approved_submissions,
        list(reversed(approved_submissions)),
        [approved_submissions[1], approved_submissions[2], approved_submissions[0]],
    ]

    for insertion_order in insertion_orders:
        blockchain.mint_queue = []
        for submission in approved_submissions:
            submission.status = APPROVED
        for submission in insertion_order:
            blockchain.add_to_mint_queue(submission.submission_id)
        observed_orders.append([
            submission["submission_id"]
            for submission in blockchain.get_mint_queue(mintable_only=True)
        ])

    assert len({tuple(order) for order in observed_orders}) == 1
    assert set(observed_orders[0]) == {submission.submission_id for submission in approved_submissions}


def test_mint_queue_uses_vote_hash_after_content_hash_tie(
    blockchain, submission_image, wallets
):
    submissions = []
    for submission_id in ("tie-break-a", "tie-break-b"):
        submission = blockchain.submit_content(
            image_path=str(submission_image),
            text_content="Identical canonical content for the ordering tie.",
            submitter=wallets["owner"].public_key,
        )
        submission.submission_id = submission_id
        _certify_submission(blockchain, submission)
        blockchain.add_to_mint_queue(submission_id)
        submissions.append(submission)

    certificates = [
        blockchain.get_originality_certificate_for_submission(submission.submission_id)
        for submission in submissions
    ]
    assert len({certificate.content_hash for certificate in certificates}) == 1
    assert len({certificate.vote_hash for certificate in certificates}) == 2

    expected = [
        certificate.submission_id
        for certificate in sorted(certificates, key=lambda certificate: certificate.vote_hash)
    ]
    assert [record["submission_id"] for record in blockchain.get_mint_queue(mintable_only=True)] == expected


def test_mint_selection_is_stable_without_state_changes(
    blockchain, approved_submissions, wallets, monkeypatch
):
    for submission in reversed(approved_submissions):
        blockchain.add_to_mint_queue(submission.submission_id)

    expected_order = [
        record["submission_id"] for record in blockchain.get_mint_queue(mintable_only=True)
    ]
    selected = []
    monkeypatch.setattr(
        blockchain,
        "_mint_submission_record",
        lambda submission, certificate, **kwargs: selected.append(submission.submission_id) or True,
    )

    assert blockchain.mint_next_queued_submission(miner=wallets["contributor_one"].public_key) is True
    assert blockchain.mint_next_queued_submission(miner=wallets["contributor_one"].public_key) is True
    assert selected == [expected_order[0], expected_order[0]]


def test_independent_nodes_derive_the_same_mint_order_from_different_insertions(
    isolated_data_dir, submission_image, wallets
):
    node_a = _new_ordering_node(isolated_data_dir, "node-a", wallets)
    node_b = _new_ordering_node(isolated_data_dir, "node-b", wallets)
    _add_ready_submissions_in_order(node_a, submission_image, wallets, [0, 1, 2, 3, 4])
    _add_ready_submissions_in_order(node_b, submission_image, wallets, [4, 2, 0, 3, 1])

    node_a_order = [record["submission_id"] for record in node_a.get_mint_queue(mintable_only=True)]
    node_b_order = [record["submission_id"] for record in node_b.get_mint_queue(mintable_only=True)]

    assert node_a_order == node_b_order
    assert len(node_a_order) == 5


def test_mint_removal_and_status_update(blockchain, approved_submissions, wallets, monkeypatch):
    first, second, _ = approved_submissions
    blockchain.add_to_mint_queue(first.submission_id)
    blockchain.add_to_mint_queue(second.submission_id)
    expected_submission_id = blockchain.get_mint_queue(mintable_only=True)[0]["submission_id"]
    monkeypatch.setattr(blockchain, "add_block", lambda **kwargs: True)

    result = blockchain.mint_next_queued_submission(miner=wallets["contributor_one"].public_key)

    assert result is True
    minted = blockchain.get_submission(expected_submission_id)
    remaining = second if expected_submission_id == first.submission_id else first
    assert minted.status == MINTED
    assert blockchain.mint_queue == [remaining.submission_id]
    assert remaining.status == QUEUED


def test_mint_next_skips_blocked_items_and_mints_valid_submission(blockchain, approved_submissions, wallets, monkeypatch):
    first, second, _ = approved_submissions
    blockchain.add_to_mint_queue(first.submission_id)
    blockchain.add_to_mint_queue(second.submission_id)
    blockchain.block_minting_for_submission(first.submission_id, "legacy bad item")
    monkeypatch.setattr(blockchain, "add_block", lambda **kwargs: True)

    result = blockchain.mint_next_queued_submission(miner=wallets["contributor_one"].public_key)

    assert result is True
    assert blockchain.mint_queue == [first.submission_id]
    assert first.status == QUEUED
    assert first.mint_blocked is True
    assert second.status == MINTED


def test_specific_mint_can_target_non_front_submission(blockchain, approved_submissions, wallets, monkeypatch):
    first, second, _ = approved_submissions
    blockchain.add_to_mint_queue(first.submission_id)
    blockchain.add_to_mint_queue(second.submission_id)
    blockchain.block_minting_for_submission(first.submission_id, "legacy bad item")
    monkeypatch.setattr(blockchain, "add_block", lambda **kwargs: True)

    result = blockchain.mint_submission(second.submission_id, miner=wallets["contributor_one"].public_key)

    assert result is True
    assert blockchain.mint_queue == [first.submission_id]
    assert first.status == QUEUED
    assert second.status == MINTED


def test_manual_block_and_unblock_toggle_mintability(blockchain, approved_submissions):
    submission = approved_submissions[0]
    blockchain.add_to_mint_queue(submission.submission_id)

    blockchain.block_minting_for_submission(submission.submission_id, "legacy bad item")
    blocked = blockchain.get_mint_queue()[0]
    assert blocked["mintable"] is False
    assert blocked["mint_block_reason"] == "legacy bad item"
    assert blocked["mint_blocked"] is True

    blockchain.unblock_minting_for_submission(submission.submission_id)
    unblocked = blockchain.get_mint_queue()[0]
    assert unblocked["mintable"] is True
    assert unblocked["mint_block_reason"] is None
    assert unblocked["mint_blocked"] is False


def test_invalid_mint_queue_entries(blockchain, approved_submissions):
    approved, minted, _ = approved_submissions
    minted.transition_to(QUEUED)
    minted.transition_to(MINTED)
    blockchain.add_to_mint_queue(approved.submission_id)
    blockchain.mint_queue.append(minted.submission_id)
    blockchain.mint_queue.append("missing-submission")

    removed = blockchain.remove_invalid_mint_queue_entries()

    assert removed == [minted.submission_id, "missing-submission"]
    assert blockchain.mint_queue == [approved.submission_id]


def test_ordered_ready_set_excludes_uncertified_rejected_invalid_and_minted_entries(
    blockchain, approved_submissions
):
    ready, invalid, minted = approved_submissions
    blockchain.add_to_mint_queue(ready.submission_id)

    invalid_certificate = blockchain.get_originality_certificate_for_submission(invalid.submission_id)
    invalid_certificate.content_hash = "0" * 64
    blockchain.mint_queue.append(invalid.submission_id)
    invalid.status = QUEUED

    minted.transition_to(QUEUED)
    minted.transition_to(MINTED)
    blockchain.mint_queue.append(minted.submission_id)

    uncertified = Submission(
        image_path="",
        text_content="Uncertified queue entry",
        submitter="uncertified-submitter",
    )
    blockchain.submissions.append(uncertified)
    blockchain.mint_queue.append(uncertified.submission_id)

    rejected = Submission(
        image_path="",
        text_content="Rejected queue entry",
        submitter="rejected-submitter",
    )
    rejected.transition_to("rejected")
    blockchain.submissions.append(rejected)
    blockchain.mint_queue.append(rejected.submission_id)

    assert [record["submission_id"] for record in blockchain.get_mint_queue(mintable_only=True)] == [
        ready.submission_id
    ]


def test_legacy_submission_without_content_id_can_still_be_minted(blockchain, submission_image, wallets, monkeypatch):
    submission = Submission.from_dict(
        {
            "submission_id": "legacy-mint-submission",
            "image_path": str(submission_image),
            "text_content": "Legacy mint meme",
            "submitter": wallets["owner"].public_key,
            "status": PENDING,
            "created_at": 1_000_000,
        }
    )
    blockchain.submissions.append(submission)
    _certify_submission(blockchain, submission)
    blockchain.add_to_mint_queue(submission.submission_id)
    monkeypatch.setattr(blockchain, "add_block", lambda **kwargs: True)

    result = blockchain.mint_next_queued_submission(miner=wallets["contributor_one"].public_key)

    assert result is True
    assert submission.content_id is not None
    assert submission.status == MINTED
