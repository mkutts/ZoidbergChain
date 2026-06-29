import shutil
import sys
import uuid
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def isolated_data_dir(monkeypatch):
    """Run file-backed blockchain code away from production data files."""
    assert Path.cwd() == PROJECT_ROOT
    test_data_dir = PROJECT_ROOT / "temp" / "test-data" / uuid.uuid4().hex
    test_data_dir.mkdir(parents=True, exist_ok=False)
    shutil.copy(PROJECT_ROOT / "zoidberg.jpg", test_data_dir / "zoidberg.jpg")
    monkeypatch.chdir(test_data_dir)
    return test_data_dir


@pytest.fixture
def wallets():
    from wallet import Wallet

    return {
        "owner": Wallet(),
        "contributor_one": Wallet(),
        "contributor_two": Wallet(),
        "recipient": Wallet(),
    }


@pytest.fixture
def blockchain(isolated_data_dir, wallets):
    from blockchain import Blockchain

    return Blockchain(
        project_owner_wallet=wallets["owner"],
        Contributor_one=wallets["contributor_one"],
        Contributor_two=wallets["contributor_two"],
    )


@pytest.fixture
def transaction(wallets):
    from transaction import Transaction

    return Transaction(
        sender=wallets["owner"].public_key,
        recipient=wallets["recipient"].public_key,
        amount=1,
        tip=0.1,
    )


@pytest.fixture
def submission_image(isolated_data_dir):
    return isolated_data_dir / "zoidberg.jpg"
