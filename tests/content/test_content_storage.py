from pathlib import Path

import pytest

import storage
from blockchain import Blockchain
from content import (
    HASH_SCHEME_LEGACY,
    HASH_SCHEME_SHA256_BYTES,
    HASH_SCHEME_SHA256_TEXT,
    STORAGE_STATUS_VERIFIED,
    TEXT_MIME_TYPE,
    compute_content_hash_bytes,
    compute_text_content_hash,
    content_file_exists,
    ensure_content_storage_dir,
    load_content_bytes,
    store_content_bytes,
    verify_content_hash_bytes,
    verify_content_hash_text,
    verify_content_object_payload,
    verify_content_file,
)
from storage import JSONStorageBackend, SQLiteStorageBackend
from wallet import Wallet


PNG_BYTES = b"\x89PNG\r\n\x1a\npng-test"
JPEG_BYTES = b"\xff\xd8\xff\xdbjpeg-test\xff\xd9"
GIF_BYTES = b"GIF89agif-test"
WEBP_BYTES = b"RIFF\x0c\x00\x00\x00WEBPwebp"
TEXT_BYTES = b"zoidberg text content"


def _json_backend(base_dir, name="node"):
    node_dir = base_dir / name
    return JSONStorageBackend(
        blockchain_file=str(node_dir / "blockchain.json"),
        peers_file=str(node_dir / "peers.json"),
    )


def _sqlite_backend(base_dir, name="node"):
    node_dir = base_dir / name
    return SQLiteStorageBackend(sqlite_db_path=str(node_dir / "zoidbergchain.db"))


def _wallets():
    return Wallet(), Wallet(), Wallet()


def _blockchain(backend):
    owner, contributor_one, contributor_two = _wallets()
    blockchain = Blockchain(
        project_owner_wallet=owner,
        Contributor_one=contributor_one,
        Contributor_two=contributor_two,
        storage_backend=backend,
    )
    return blockchain, owner


def test_content_storage_directory_is_created_inside_data_dir(isolated_data_dir):
    content_dir = Path(ensure_content_storage_dir(data_dir=str(isolated_data_dir / "node-a")))

    assert content_dir.exists()
    assert content_dir.is_dir()
    assert content_dir == isolated_data_dir / "node-a" / "content"


def test_compute_content_hash_bytes_is_deterministic():
    assert compute_content_hash_bytes(PNG_BYTES) == compute_content_hash_bytes(PNG_BYTES)
    assert compute_content_hash_bytes(PNG_BYTES) != compute_content_hash_bytes(JPEG_BYTES)


def test_store_content_bytes_writes_file_by_content_hash_and_ignores_original_filename(isolated_data_dir):
    content_hash = compute_content_hash_bytes(PNG_BYTES)
    result = store_content_bytes(
        content_hash,
        PNG_BYTES,
        mime_type="image/png",
        original_filename="..\\..\\evil.png",
        data_dir=str(isolated_data_dir),
    )

    stored_path = Path(result["path"])
    assert stored_path.exists()
    assert stored_path.name == f"{content_hash}.png"
    assert ".." not in str(stored_path)
    assert stored_path.parent.parent.parent == isolated_data_dir / "content"
    assert load_content_bytes(content_hash, "image/png", data_dir=str(isolated_data_dir)) == PNG_BYTES


def test_verify_content_file_succeeds_for_matching_hash(isolated_data_dir):
    content_hash = compute_content_hash_bytes(JPEG_BYTES)
    store_content_bytes(content_hash, JPEG_BYTES, mime_type="image/jpeg", data_dir=str(isolated_data_dir))

    verification = verify_content_file(content_hash, "image/jpeg", data_dir=str(isolated_data_dir))

    assert verification["verified"] is True
    assert verification["byte_hash"] == compute_content_hash_bytes(JPEG_BYTES)


def test_verify_content_file_fails_for_corrupt_content(isolated_data_dir):
    content_hash = compute_content_hash_bytes(GIF_BYTES)
    result = store_content_bytes(content_hash, GIF_BYTES, mime_type="image/gif", data_dir=str(isolated_data_dir))

    Path(result["path"]).write_bytes(b"corrupted")
    verification = verify_content_file(content_hash, "image/gif", data_dir=str(isolated_data_dir))

    assert verification["verified"] is False
    assert verification["error"] == "hash_mismatch"


def test_storing_same_content_twice_is_idempotent(isolated_data_dir):
    content_hash = compute_content_hash_bytes(WEBP_BYTES)
    first = store_content_bytes(content_hash, WEBP_BYTES, mime_type="image/webp", data_dir=str(isolated_data_dir))
    second = store_content_bytes(content_hash, WEBP_BYTES, mime_type="image/webp", data_dir=str(isolated_data_dir))

    assert first["path"] == second["path"]
    assert first["byte_hash"] == second["byte_hash"]


def test_storing_different_bytes_under_same_content_hash_fails(isolated_data_dir):
    content_hash = compute_content_hash_bytes(PNG_BYTES)
    store_content_bytes(content_hash, PNG_BYTES, mime_type="image/png", data_dir=str(isolated_data_dir))

    with pytest.raises(ValueError, match="does not match"):
        store_content_bytes(content_hash, JPEG_BYTES, mime_type="image/jpeg", data_dir=str(isolated_data_dir))


def test_oversized_content_is_rejected(isolated_data_dir):
    with pytest.raises(ValueError, match="exceeds MAX_CONTENT_FILE_SIZE_BYTES"):
        store_content_bytes(
            "f" * 64,
            b"x" * 6,
            mime_type=TEXT_MIME_TYPE,
            data_dir=str(isolated_data_dir),
            max_size_bytes=5,
        )


def test_unsupported_mime_type_is_rejected(isolated_data_dir):
    with pytest.raises(ValueError, match="Unsupported mime_type"):
        store_content_bytes(
            "1" * 64,
            b"not-supported",
            mime_type="application/pdf",
            data_dir=str(isolated_data_dir),
        )


@pytest.mark.parametrize(
    ("mime_type", "payload"),
    [
        ("image/jpeg", JPEG_BYTES),
        ("image/png", PNG_BYTES),
        ("image/gif", GIF_BYTES),
        ("image/webp", WEBP_BYTES),
        (TEXT_MIME_TYPE, TEXT_BYTES),
    ],
)
def test_supported_mime_types_are_accepted(isolated_data_dir, mime_type, payload):
    content_hash = compute_content_hash_bytes(payload)
    result = store_content_bytes(content_hash, payload, mime_type=mime_type, data_dir=str(isolated_data_dir))

    assert result["mime_type"] == mime_type
    assert content_file_exists(content_hash, mime_type, data_dir=str(isolated_data_dir)) is True


@pytest.mark.parametrize("backend_factory", [_json_backend, _sqlite_backend])
def test_submission_content_object_becomes_verified_and_persists(
    backend_factory,
    isolated_data_dir,
    submission_image,
):
    backend = backend_factory(isolated_data_dir, "persisted-node")
    blockchain, owner = _blockchain(backend)

    content_object = blockchain.upload_binary_content(
        file_bytes=submission_image.read_bytes(),
        submitted_by=owner.public_key,
        mime_type="image/jpeg",
        original_filename=submission_image.name,
    )
    submission = blockchain.submit_existing_content(
        content_hash=content_object.content_hash,
        content_id=content_object.content_id,
        text_content="verified content object",
        submitter=owner.public_key,
    )
    blockchain.save_blockchain()

    content_object = blockchain.get_content_object_by_hash(submission.content_hash)
    assert content_object is not None
    assert content_object.storage_status == STORAGE_STATUS_VERIFIED
    assert content_object.hash_scheme == HASH_SCHEME_SHA256_BYTES
    assert content_object.file_size_bytes == Path(submission.image_path).stat().st_size
    assert content_object.local_path is not None
    assert Path(submission.image_path).exists()
    assert str(Path(submission.image_path)).startswith(str(Path(backend.data_dir) / "content"))

    reloaded = Blockchain(storage_backend=backend)
    reloaded_object = reloaded.get_content_object_by_hash(submission.content_hash)
    assert reloaded_object is not None
    assert reloaded_object.storage_status == STORAGE_STATUS_VERIFIED
    assert reloaded_object.file_size_bytes == content_object.file_size_bytes
    assert reloaded.get_submission(submission.submission_id).image_path == submission.image_path


def test_data_dir_isolation_keeps_node_a_and_node_b_content_files_separate(
    isolated_data_dir,
    submission_image,
):
    backend_a = _json_backend(isolated_data_dir, "node-a")
    backend_b = _sqlite_backend(isolated_data_dir, "node-b")
    blockchain_a, owner_a = _blockchain(backend_a)
    blockchain_b, owner_b = _blockchain(backend_b)

    submission_a = blockchain_a.submit_content(
        image_path=str(submission_image),
        text_content="node a content",
        submitter=owner_a.public_key,
    )
    submission_b = blockchain_b.submit_content(
        image_path=str(submission_image),
        text_content="node b content",
        submitter=owner_b.public_key,
    )

    path_a = Path(submission_a.image_path)
    path_b = Path(submission_b.image_path)
    assert path_a.exists()
    assert path_b.exists()
    assert path_a != path_b
    assert str(path_a).startswith(str(isolated_data_dir / "node-a" / "content"))
    assert str(path_b).startswith(str(isolated_data_dir / "node-b" / "content"))


def test_verify_content_hash_helpers_cover_binary_and_text():
    assert verify_content_hash_bytes(compute_content_hash_bytes(PNG_BYTES), PNG_BYTES)["verified"] is True
    assert verify_content_hash_bytes(compute_content_hash_bytes(PNG_BYTES), JPEG_BYTES)["error"] == "hash_mismatch"
    assert verify_content_hash_text(compute_text_content_hash("hello\r\nworld"), "hello\nworld")["verified"] is True
    assert verify_content_hash_text(compute_text_content_hash("hello world"), "different")["error"] == "hash_mismatch"


def test_legacy_submission_content_object_stays_local_and_unverifiable(isolated_data_dir, submission_image):
    backend = _json_backend(isolated_data_dir, "legacy-node")
    blockchain, owner = _blockchain(backend)

    submission = blockchain.submit_content(
        image_path=str(submission_image),
        text_content="legacy content object",
        submitter=owner.public_key,
    )

    content_object = blockchain.get_content_object_by_hash(submission.content_hash)
    verification = verify_content_object_payload(content_object, data_dir=backend.data_dir)
    assert content_object.storage_status == "local"
    assert content_object.hash_scheme == HASH_SCHEME_LEGACY
    assert verification["verified"] is False
    assert verification["error"] == "legacy_unverifiable"


def test_integrity_check_reports_corrupt_verified_content(isolated_data_dir):
    backend = _json_backend(isolated_data_dir, "integrity-corrupt")
    blockchain, owner = _blockchain(backend)
    content_object = blockchain.upload_binary_content(
        file_bytes=PNG_BYTES,
        submitted_by=owner.public_key,
        mime_type="image/png",
        original_filename="integrity.png",
    )
    blockchain.save_blockchain()

    file_path = Path(backend.data_dir) / Path(content_object.local_path)
    file_path.write_bytes(b"corrupt")
    report = storage.check_storage_integrity(backend)

    assert report["healthy"] is False
    assert any("hash_mismatch" in detail for detail in report["details"])


def test_integrity_check_warns_for_legacy_unverifiable_content(isolated_data_dir, submission_image):
    backend = _json_backend(isolated_data_dir, "integrity-legacy")
    blockchain, owner = _blockchain(backend)
    blockchain.submit_content(
        image_path=str(submission_image),
        text_content="legacy integrity",
        submitter=owner.public_key,
    )
    blockchain.save_blockchain()

    report = storage.check_storage_integrity(backend)

    assert report["healthy"] is True
    assert any("legacy/unverifiable" in detail for detail in report["details"])
