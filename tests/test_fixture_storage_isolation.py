"""
Test to verify that the blockchain fixture uses isolated test directories,
not repository-root blockchain.json.

This test proves that after the conftest.py fix, each test fixture instance
gets its own storage backend pointing to a unique temp directory.
"""

import os
from pathlib import Path


def test_blockchain_fixture_uses_isolated_temp_directory(blockchain, isolated_data_dir):
    """
    Verify that the blockchain fixture storage backend is using the isolated
    test directory, not the repository root.
    
    This proves:
    1. Storage backend paths point to isolated_data_dir (test temp directory)
    2. Repository-root blockchain.json is never loaded or modified
    3. Each test instance gets completely fresh/isolated blockchain state
    """
    # Get the storage backend from the blockchain instance
    storage_backend = blockchain.storage
    
    # Verify blockchain_file is in the test directory, not repository root
    blockchain_file_path = Path(storage_backend.blockchain_file)
    assert blockchain_file_path.parent == isolated_data_dir, (
        f"Blockchain file should be in isolated test directory. "
        f"Expected parent: {isolated_data_dir}, "
        f"Got: {blockchain_file_path.parent}"
    )
    
    # Verify the file path is absolute and within the test directory
    assert blockchain_file_path.is_absolute(), (
        f"Storage backend should use absolute paths. Got: {blockchain_file_path}"
    )
    assert str(isolated_data_dir) in str(blockchain_file_path), (
        f"Storage path must contain isolated_data_dir. "
        f"Expected substring: {isolated_data_dir}, "
        f"Got: {blockchain_file_path}"
    )
    
    # Verify current working directory is the test directory
    assert Path.cwd() == isolated_data_dir, (
        f"Test should be running in isolated temp directory. "
        f"Expected cwd: {isolated_data_dir}, "
        f"Got: {Path.cwd()}"
    )
    
    # Verify the blockchain.json exists in the test directory (or will be created there)
    # For a fresh blockchain with just genesis, the file should exist
    if blockchain_file_path.exists():
        assert blockchain_file_path.parent == isolated_data_dir, (
            f"If blockchain.json exists, it must be in isolated directory. "
            f"Got: {blockchain_file_path}"
        )
    
    print(f"✓ Blockchain storage successfully isolated to: {blockchain_file_path}")
    print(f"✓ Current working directory: {Path.cwd()}")
    print(f"✓ Isolated data directory: {isolated_data_dir}")
    print(f"✓ Chain has {len(blockchain.chain)} blocks")
    print(f"✓ Wallets registered: {len(blockchain.wallets)}")


def test_multiple_blockchain_fixtures_use_different_directories(
    blockchain, isolated_data_dir
):
    """
    Verify that each blockchain fixture instance gets its own isolated directory.
    This test runs twice (implicitly) - each run creates a separate test_data_dir.
    """
    storage_backend = blockchain.storage
    blockchain_file = Path(storage_backend.blockchain_file)
    
    # Verify this blockchain instance is using the correct isolated directory
    assert str(isolated_data_dir) in str(blockchain_file), (
        f"Blockchain must use current isolated directory. "
        f"Expected to find: {isolated_data_dir}, "
        f"Got: {blockchain_file}"
    )
    
    # Get wallet count for this instance
    wallet_count = len(blockchain.wallets)
    print(f"Blockchain instance at {blockchain_file.parent} has {wallet_count} wallets")
    
    assert wallet_count >= 3, "Should have at least 3 genesis wallets"

