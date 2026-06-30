from wallet import Wallet


def test_add_wallet_stores_new_wallet(blockchain):
    wallet = Wallet()

    result = blockchain.add_wallet(wallet)

    assert result is True
    assert blockchain.wallets[wallet.public_key] is wallet


def test_add_wallet_rejects_duplicate_public_key_without_overwriting(blockchain):
    wallet = Wallet()
    duplicate_wallet = Wallet()
    duplicate_wallet.public_key = wallet.public_key

    assert blockchain.add_wallet(wallet) is True
    assert blockchain.add_wallet(duplicate_wallet) is False
    assert blockchain.wallets[wallet.public_key] is wallet
