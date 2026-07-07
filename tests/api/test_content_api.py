from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from blockchain import Blockchain
from peers import PeerStore
from storage import JSONStorageBackend, SQLiteStorageBackend
from submission import MINTED, VOTE_ORIGINAL
from wallet import Wallet


PNG_BYTES = b"\x89PNG\r\n\x1a\npng-test"
JPEG_BYTES = b"\xff\xd8\xff\xdbjpeg-test\xff\xd9"
GIF_BYTES = b"GIF89agif-test"
WEBP_BYTES = b"RIFF\x0c\x00\x00\x00WEBPwebp"
TEXT_BYTES = b"api text content"


def _client(blockchain):
    import api

    api.blockchain = blockchain
    api.peer_store = PeerStore()
    return TestClient(api.app)


def _json_backend(base_dir, name="node"):
    node_dir = base_dir / name
    return JSONStorageBackend(
        blockchain_file=str(node_dir / "blockchain.json"),
        peers_file=str(node_dir / "peers.json"),
    )


def _sqlite_backend(base_dir, name="node"):
    node_dir = base_dir / name
    return SQLiteStorageBackend(sqlite_db_path=str(node_dir / "zoidbergchain.db"))


def _make_blockchain(backend):
    owner = Wallet()
    contributor_one = Wallet()
    contributor_two = Wallet()
    blockchain = Blockchain(
        project_owner_wallet=owner,
        Contributor_one=contributor_one,
        Contributor_two=contributor_two,
        storage_backend=backend,
    )
    return blockchain, owner


def _generate_wallet(client):
    response = client.post("/generate_wallet")
    assert response.status_code == 200
    return response.json()["wallet"]["public_key"]


@pytest.mark.parametrize(
    ("filename", "mime_type", "payload"),
    [
        ("upload.png", "image/png", PNG_BYTES),
        ("upload.jpg", "image/jpeg", JPEG_BYTES),
        ("upload.gif", "image/gif", GIF_BYTES),
        ("upload.webp", "image/webp", WEBP_BYTES),
    ],
)
def test_binary_upload_succeeds_and_returns_safe_metadata(blockchain, wallets, filename, mime_type, payload):
    client = _client(blockchain)

    response = client.post(
        "/content/upload",
        data={"submitted_by": wallets["owner"].public_key, "caption": "uploaded content"},
        files={"file": (filename, payload, mime_type)},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["content_hash"]
    assert body["content_id"]
    assert body["mime_type"] == mime_type
    assert body["storage_status"] == "verified"
    assert body["download_url"] == f"/content/{body['content_hash']}"
    assert "local_path" not in body


def test_text_plain_upload_succeeds(blockchain, wallets):
    client = _client(blockchain)

    response = client.post(
        "/content/upload",
        data={"submitted_by": wallets["owner"].public_key},
        files={"file": ("note.txt", TEXT_BYTES, "text/plain")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["mime_type"] == "text/plain"
    assert body["content_type"] == "text"
    assert body["storage_status"] == "verified"


def test_empty_upload_is_rejected(blockchain, wallets):
    client = _client(blockchain)

    response = client.post(
        "/content/upload",
        data={"submitted_by": wallets["owner"].public_key},
        files={"file": ("empty.png", b"", "image/png")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Uploaded file is empty."


def test_oversized_upload_is_rejected(blockchain, wallets, monkeypatch):
    client = _client(blockchain)
    import content

    monkeypatch.setattr(content.config, "MAX_CONTENT_FILE_SIZE_BYTES", 5)
    response = client.post(
        "/content/upload",
        data={"submitted_by": wallets["owner"].public_key},
        files={"file": ("too-big.png", b"x" * 6, "image/png")},
    )

    assert response.status_code == 400
    assert "exceeds max size" in response.json()["detail"]


def test_file_at_limit_is_accepted(blockchain, wallets, monkeypatch):
    client = _client(blockchain)
    import content

    monkeypatch.setattr(content.config, "MAX_CONTENT_FILE_SIZE_BYTES", len(PNG_BYTES))
    response = client.post(
        "/content/upload",
        data={"submitted_by": wallets["owner"].public_key},
        files={"file": ("limit.png", PNG_BYTES, "image/png")},
    )

    assert response.status_code == 200


def test_text_above_limit_is_rejected(blockchain, wallets, monkeypatch):
    client = _client(blockchain)
    import content

    monkeypatch.setattr(content.config, "MAX_TEXT_CONTENT_BYTES", 4)
    response = client.post(
        "/content/text",
        json={"text_content": "hello", "submitted_by": wallets["owner"].public_key},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Text content exceeds max size of 4 bytes."


def test_text_at_limit_is_accepted(blockchain, wallets, monkeypatch):
    client = _client(blockchain)
    import content

    monkeypatch.setattr(content.config, "MAX_TEXT_CONTENT_BYTES", 5)
    response = client.post(
        "/content/text",
        json={"text_content": "hello", "submitted_by": wallets["owner"].public_key},
    )

    assert response.status_code == 200


def test_caption_above_limit_is_rejected(blockchain, wallets, monkeypatch):
    client = _client(blockchain)
    import content

    monkeypatch.setattr(content.config, "MAX_CAPTION_LENGTH", 5)
    response = client.post(
        "/content/upload",
        data={"submitted_by": wallets["owner"].public_key, "caption": "toolong"},
        files={"file": ("caption.png", PNG_BYTES, "image/png")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Caption exceeds max length of 5 characters."


def test_declared_detected_mime_mismatch_is_rejected_in_strict_mode(blockchain, wallets):
    client = _client(blockchain)

    response = client.post(
        "/content/upload",
        data={"submitted_by": wallets["owner"].public_key},
        files={"file": ("wrong.jpg", PNG_BYTES, "image/jpeg")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Declared mime_type 'image/jpeg' does not match detected mime_type 'image/png'."


def test_filename_extension_alone_does_not_determine_mime(blockchain, wallets):
    client = _client(blockchain)

    response = client.post(
        "/content/upload",
        data={"submitted_by": wallets["owner"].public_key},
        files={"file": ("looks-like.jpg", PNG_BYTES, "image/png")},
    )

    assert response.status_code == 200
    assert response.json()["mime_type"] == "image/png"


def test_unsupported_upload_mime_type_is_rejected(blockchain, wallets):
    client = _client(blockchain)

    response = client.post(
        "/content/upload",
        data={"submitted_by": wallets["owner"].public_key},
        files={"file": ("bad.pdf", b"%PDF-1.7", "application/pdf")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Unsupported mime_type for uploaded content."


def test_path_traversal_filename_is_ignored(blockchain, wallets):
    client = _client(blockchain)

    response = client.post(
        "/content/upload",
        data={"submitted_by": wallets["owner"].public_key},
        files={"file": ("..\\..\\evil.png", PNG_BYTES, "image/png")},
    )

    assert response.status_code == 200
    body = response.json()
    content_object = blockchain.get_content_object_by_hash(body["content_hash"])
    assert content_object is not None
    assert content_object.file_name.endswith(".png")
    assert "evil" not in content_object.file_name


def test_overlong_filename_is_safely_truncated_in_metadata(blockchain, wallets, monkeypatch):
    client = _client(blockchain)
    import content

    monkeypatch.setattr(content.config, "MAX_FILENAME_LENGTH", 12)
    response = client.post(
        "/content/upload",
        data={"submitted_by": wallets["owner"].public_key},
        files={"file": ("verylongfilename!!.png", PNG_BYTES, "image/png")},
    )

    assert response.status_code == 200
    content_object = blockchain.get_content_object_by_hash(response.json()["content_hash"])
    assert len(content_object.metadata["original_filename"]) <= 12


def test_upload_hash_is_computed_from_bytes(blockchain, wallets):
    client = _client(blockchain)
    import api

    response = client.post(
        "/content/upload",
        data={"submitted_by": wallets["owner"].public_key},
        files={"file": ("hash.png", PNG_BYTES, "image/png")},
    )

    assert response.status_code == 200
    assert response.json()["content_hash"] == api.compute_content_hash_bytes(PNG_BYTES)


def test_duplicate_upload_is_idempotent(blockchain, wallets):
    client = _client(blockchain)

    first = client.post(
        "/content/upload",
        data={"submitted_by": wallets["owner"].public_key},
        files={"file": ("dup.png", PNG_BYTES, "image/png")},
    )
    second = client.post(
        "/content/upload",
        data={"submitted_by": wallets["owner"].public_key},
        files={"file": ("dup-again.png", PNG_BYTES, "image/png")},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["content_hash"] == second.json()["content_hash"]
    assert first.json()["content_id"] == second.json()["content_id"]


def test_metadata_endpoint_returns_safe_fields(blockchain, wallets):
    client = _client(blockchain)
    upload = client.post(
        "/content/upload",
        data={"submitted_by": wallets["owner"].public_key, "caption": "safe metadata"},
        files={"file": ("meta.png", PNG_BYTES, "image/png")},
    )

    response = client.get(f"/content/{upload.json()['content_hash']}/metadata")

    assert response.status_code == 200
    content = response.json()["content"]
    assert content["content_hash"] == upload.json()["content_hash"]
    assert content["hash_scheme"] == "sha256_bytes"
    assert content["verified_at"] is not None
    assert content["verification_error"] is None
    assert content["network_name"]
    assert "local_path" not in content
    assert "private_key" not in content


def test_text_metadata_endpoint_works(blockchain, wallets):
    client = _client(blockchain)
    upload = client.post(
        "/content/text",
        json={
            "text_content": "metadata text",
            "submitted_by": wallets["owner"].public_key,
            "caption": "text caption",
        },
    )

    response = client.get(f"/content/{upload.json()['content_hash']}/metadata")

    assert response.status_code == 200
    assert response.json()["content"]["mime_type"] == "text/plain"
    assert response.json()["content"]["content_type"] == "text"
    assert response.json()["content"]["hash_scheme"] == "sha256_text"


def test_text_hash_is_canonical_across_line_endings(blockchain, wallets):
    client = _client(blockchain)

    first = client.post(
        "/content/text",
        json={"text_content": "line one\r\nline two", "submitted_by": wallets["owner"].public_key},
    )
    second = client.post(
        "/content/text",
        json={"text_content": "line one\nline two", "submitted_by": wallets["owner"].public_key},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["content_hash"] == second.json()["content_hash"]


def test_existing_verified_content_downloads_successfully(blockchain, wallets):
    client = _client(blockchain)
    upload = client.post(
        "/content/upload",
        data={"submitted_by": wallets["owner"].public_key},
        files={"file": ("download.png", PNG_BYTES, "image/png")},
    )

    response = client.get(f"/content/{upload.json()['content_hash']}")

    assert response.status_code == 200
    assert response.content == PNG_BYTES
    assert response.headers["content-type"].startswith("image/png")


def test_text_content_downloads_successfully(blockchain, wallets):
    client = _client(blockchain)
    upload = client.post(
        "/content/text",
        json={"text_content": "download me", "submitted_by": wallets["owner"].public_key},
    )

    response = client.get(f"/content/{upload.json()['content_hash']}")

    assert response.status_code == 200
    assert response.text == "download me"
    assert response.headers["content-type"].startswith("text/plain")


def test_missing_content_download_returns_404(blockchain):
    client = _client(blockchain)

    response = client.get("/content/" + ("a" * 64))

    assert response.status_code == 404


def test_missing_local_file_download_fails_safely(blockchain, wallets):
    client = _client(blockchain)
    upload = client.post(
        "/content/upload",
        data={"submitted_by": wallets["owner"].public_key},
        files={"file": ("missing.png", PNG_BYTES, "image/png")},
    )
    content_object = blockchain.get_content_object_by_hash(upload.json()["content_hash"])
    file_path = Path(blockchain.storage.data_dir) / Path(content_object.local_path)
    file_path.unlink()

    response = client.get(f"/content/{upload.json()['content_hash']}")

    assert response.status_code == 404
    assert "Content file not found" in response.json()["detail"]


def test_corrupt_local_file_download_fails_safely(blockchain, wallets):
    client = _client(blockchain)
    upload = client.post(
        "/content/upload",
        data={"submitted_by": wallets["owner"].public_key},
        files={"file": ("corrupt.png", PNG_BYTES, "image/png")},
    )
    content_object = blockchain.get_content_object_by_hash(upload.json()["content_hash"])
    file_path = Path(blockchain.storage.data_dir) / Path(content_object.local_path)
    file_path.write_bytes(b"corrupted")

    response = client.get(f"/content/{upload.json()['content_hash']}")

    assert response.status_code == 409
    assert response.json()["detail"] == "Content file failed integrity verification."


def test_malformed_content_hash_is_rejected(blockchain):
    client = _client(blockchain)

    response = client.get("/content/not-a-hash")

    assert response.status_code == 422


def test_uploaded_content_can_be_referenced_by_submission_and_minted(blockchain, submission_image):
    client = _client(blockchain)
    submitter = _generate_wallet(client)
    voters = [_generate_wallet(client) for _ in range(5)]

    with open(submission_image, "rb") as image_file:
        upload = client.post(
            "/content/upload",
            data={"submitted_by": submitter, "caption": "upload-first"},
            files={"file": ("upload-first.jpg", image_file.read(), "image/jpeg")},
        )

    assert upload.status_code == 200
    submission_response = client.post(
        "/submit_content",
        data={
            "submitter": submitter,
            "text_content": "upload-first submission",
            "content_hash": upload.json()["content_hash"],
            "content_id": upload.json()["content_id"],
        },
    )
    assert submission_response.status_code == 200
    submission = submission_response.json()["submission"]

    for voter in voters:
        vote_response = client.post(
            f"/submissions/{submission['submission_id']}/vote",
            data={"voter": voter, "vote_type": VOTE_ORIGINAL},
        )
        assert vote_response.status_code == 200

    evaluate = client.post(
        f"/submissions/{submission['submission_id']}/evaluate",
        data={"automated_originality_passed": "true"},
    )
    assert evaluate.status_code == 200
    mint = client.post(f"/mint-queue/{submission['submission_id']}/mint")
    assert mint.status_code == 200
    assert mint.json()["submission"]["status"] == MINTED


@pytest.mark.parametrize("backend_factory", [_json_backend, _sqlite_backend])
def test_uploaded_content_metadata_persists_across_backends(backend_factory, isolated_data_dir):
    backend = backend_factory(isolated_data_dir, "persisted-content")
    blockchain, owner = _make_blockchain(backend)
    client = _client(blockchain)

    response = client.post(
        "/content/upload",
        data={"submitted_by": owner.public_key},
        files={"file": ("persisted.png", PNG_BYTES, "image/png")},
    )

    assert response.status_code == 200
    content_hash = response.json()["content_hash"]
    reloaded = Blockchain(storage_backend=backend)
    content_object = reloaded.get_content_object_by_hash(content_hash)
    assert content_object is not None
    assert content_object.storage_status == "verified"
    assert content_object.local_path is not None
