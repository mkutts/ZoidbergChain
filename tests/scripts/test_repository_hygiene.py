from scripts.check_repository_hygiene import classify_path, find_prohibited_paths


def test_classifies_prohibited_runtime_and_generated_paths():
    failures = dict(
        find_prohibited_paths(
            [
                ".env",
                "blockchain.json",
                "content/ab/cd/upload.jpg",
                "venv/Lib/site-packages/package.py",
                "pre-genesis-meme-v1-backup/zoidbergchain.sqlite3",
                "rollback-prep-working-tree.patch",
            ]
        )
    )

    assert failures[".env"] == "local environment file"
    assert failures["blockchain.json"] == "mutable blockchain state"
    assert failures["content/ab/cd/upload.jpg"] == "runtime content cache"
    assert failures["venv/Lib/site-packages/package.py"] == "Python virtual environment"
    assert failures["pre-genesis-meme-v1-backup/zoidbergchain.sqlite3"] == "pre-genesis runtime backup"
    assert failures["rollback-prep-working-tree.patch"] == "local patch artifact"


def test_allows_protocol_fixtures_examples_and_static_assets():
    allowed_paths = [
        ".env.example",
        "deploy/examples/zoidbergchain.server.env.example",
        "zoidbergcoin-ui/.env.production.example",
        "protocol_v1.py",
        "protocol_v1_genesis.py",
        "public_testnet_v1_genesis_meme_base64.txt",
        "tests/fixtures/protocol_v1_golden_vectors.json",
        "static/ZoidbergCoin_WhitePaper.pdf",
    ]

    assert find_prohibited_paths(allowed_paths) == []
    assert classify_path("tests/fixtures/protocol_v1_golden_vectors.json") is None
