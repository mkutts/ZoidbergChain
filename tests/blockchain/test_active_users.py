from block import Block
from config import ACTIVE_USER_LOOKBACK_DAYS
from transaction import Transaction


SECONDS_PER_DAY = 24 * 60 * 60


def test_active_users_zero_users(blockchain):
    assert blockchain.get_active_users(now=1_000_000) == 0


def test_active_users_count_submissions(blockchain, submission_image, wallets):
    now = 1_000_000
    blockchain.submit_content(
        image_path=str(submission_image),
        text_content="Active submission",
        submitter=wallets["owner"].public_key,
    ).created_at = now

    assert blockchain.get_active_users(now=now) == 1


def test_active_users_count_votes(blockchain, wallets):
    now = 1_000_000
    blockchain.record_vote(voter=wallets["owner"].public_key, submission_id="submission", created_at=now)

    assert blockchain.get_active_users(now=now) == 1


def test_active_users_count_transactions(blockchain, wallets):
    now = 1_000_000
    blockchain.pending_transactions.append(
        Transaction(
            sender=wallets["owner"].public_key,
            recipient=wallets["recipient"].public_key,
            amount=1,
            created_at=now,
        )
    )

    assert blockchain.get_active_users(now=now) == 1


def test_active_users_count_tips(blockchain, wallets):
    now = 1_000_000
    blockchain.pending_transactions.append(
        Transaction(
            sender=wallets["owner"].public_key,
            recipient=wallets["recipient"].public_key,
            amount=1,
            tip=0.25,
            created_at=now,
        )
    )

    assert blockchain.get_active_users(now=now) == 1


def test_active_users_ignore_duplicate_wallets(blockchain, submission_image, wallets):
    now = 1_000_000
    wallet = wallets["owner"].public_key

    blockchain.submit_content(
        image_path=str(submission_image),
        text_content="Duplicate wallet activity",
        submitter=wallet,
    ).created_at = now
    blockchain.record_vote(voter=wallet, submission_id="submission", created_at=now)
    blockchain.pending_transactions.append(
        Transaction(
            sender=wallet,
            recipient=wallets["recipient"].public_key,
            amount=1,
            tip=0.25,
            created_at=now,
        )
    )

    assert blockchain.get_active_users(now=now) == 1


def test_active_users_ignore_inactive_wallets(blockchain, submission_image, wallets):
    now = 1_000_000
    old_timestamp = now - ((ACTIVE_USER_LOOKBACK_DAYS + 1) * SECONDS_PER_DAY)

    blockchain.submit_content(
        image_path=str(submission_image),
        text_content="Inactive submission",
        submitter=wallets["owner"].public_key,
    ).created_at = old_timestamp
    blockchain.record_vote(voter=wallets["contributor_one"].public_key, created_at=old_timestamp)
    blockchain.pending_transactions.append(
        Transaction(
            sender=wallets["contributor_two"].public_key,
            recipient=wallets["recipient"].public_key,
            amount=1,
            tip=0.25,
            created_at=old_timestamp,
        )
    )

    assert blockchain.get_active_users(now=now) == 0


def test_active_users_count_transactions_in_blocks(blockchain, wallets):
    now = 1_000_000
    transaction = Transaction(
        sender=wallets["owner"].public_key,
        recipient=wallets["recipient"].public_key,
        amount=1,
        created_at=now,
    )
    blockchain.chain.append(
        Block(
            index=1,
            previous_hash=blockchain.get_latest_block().hash,
            timestamp=now,
            transactions=[transaction],
            miner=wallets["contributor_one"].public_key,
        )
    )

    assert blockchain.get_active_users(now=now) == 1
