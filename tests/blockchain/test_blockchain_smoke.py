from pathlib import Path


def test_blockchain_fixture_creates_genesis_block_in_isolation(blockchain):
    assert len(blockchain.chain) == 1
    assert blockchain.get_latest_block().index == 0
    assert Path("blockchain.json").exists() is False


def test_wallet_fixture_registers_genesis_wallets(blockchain, wallets):
    assert wallets["owner"].public_key in blockchain.wallets
    assert wallets["contributor_one"].public_key in blockchain.wallets
    assert wallets["contributor_two"].public_key in blockchain.wallets


def test_transaction_fixture_has_expected_shape(transaction, wallets):
    assert transaction.sender == wallets["owner"].public_key
    assert transaction.recipient == wallets["recipient"].public_key
    assert transaction.amount == 1
    assert transaction.tip == 0.1


def test_submission_image_fixture_points_to_temp_copy(submission_image):
    assert submission_image.exists()
    assert submission_image.name == "zoidberg.jpg"
