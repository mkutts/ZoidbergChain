import pytest

from content import (
    CONTENT_TYPE_IMAGE,
    CONTENT_TYPE_MIXED,
    CONTENT_TYPE_TEXT,
    STORAGE_STATUS_LOCAL,
    STORAGE_STATUS_MISSING,
    STORAGE_STATUS_REMOTE,
    STORAGE_STATUS_VERIFIED,
    ContentObject,
    calculate_content_hash,
)


def test_text_content_object_can_be_created():
    content = ContentObject.from_text(
        text_content="A very normal meme caption",
        submitted_by="wallet-a",
        network_name="zoidberg-testnet",
        caption="caption text",
        metadata={"topic": "memes"},
    )

    assert content.content_type == CONTENT_TYPE_TEXT
    assert content.text_content == "A very normal meme caption"
    assert content.caption == "caption text"
    assert content.content_hash
    assert content.content_id
    assert content.to_dict()["metadata"] == {"topic": "memes"}


def test_image_metadata_content_object_can_be_created():
    content = ContentObject.from_image_metadata(
        submitted_by="wallet-b",
        network_name="zoidberg-testnet",
        mime_type="image/jpeg",
        file_name="zoidberg.jpg",
        file_size_bytes=12345,
        caption="image caption",
        metadata={"source": "camera"},
        storage_status=STORAGE_STATUS_LOCAL,
    )

    assert content.content_type == CONTENT_TYPE_IMAGE
    assert content.mime_type == "image/jpeg"
    assert content.file_name == "zoidberg.jpg"
    assert content.file_size_bytes == 12345
    assert content.storage_status == STORAGE_STATUS_LOCAL
    assert content.content_hash


def test_mixed_content_object_supports_text_and_image_metadata():
    content_hash = calculate_content_hash(
        content_type=CONTENT_TYPE_MIXED,
        mime_type="image/png",
        text_content="alt text",
        caption="caption",
        metadata={"alt": True},
    )
    content = ContentObject(
        content_hash=content_hash,
        content_type=CONTENT_TYPE_MIXED,
        mime_type="image/png",
        submitted_by="wallet-c",
        network_name="zoidberg-testnet",
        text_content="alt text",
        caption="caption",
        metadata={"alt": True},
        storage_status=STORAGE_STATUS_REMOTE,
    )

    assert content.content_type == CONTENT_TYPE_MIXED
    assert content.text_content == "alt text"
    assert content.caption == "caption"
    assert content.storage_status == STORAGE_STATUS_REMOTE


def test_content_id_is_deterministic_from_content_hash():
    content_hash = "a" * 64

    first = ContentObject(
        content_hash=content_hash,
        content_type=CONTENT_TYPE_TEXT,
        mime_type="text/plain",
        submitted_by="wallet-a",
        network_name="zoidberg-testnet",
        text_content="hello world",
    )
    second = ContentObject(
        content_hash=content_hash,
        content_type=CONTENT_TYPE_TEXT,
        mime_type="text/plain",
        submitted_by="wallet-b",
        network_name="zoidberg-testnet",
        text_content="hello world",
    )

    assert first.content_id == second.content_id


def test_content_hash_is_required():
    with pytest.raises(ValueError, match="content_hash is required"):
        ContentObject(
            content_hash="",
            content_type=CONTENT_TYPE_TEXT,
            mime_type="text/plain",
            submitted_by="wallet-a",
            network_name="zoidberg-testnet",
            text_content="hello",
        )


@pytest.mark.parametrize(
    ("storage_status", "expected"),
    [
        (STORAGE_STATUS_MISSING, STORAGE_STATUS_MISSING),
        (STORAGE_STATUS_LOCAL, STORAGE_STATUS_LOCAL),
        (STORAGE_STATUS_REMOTE, STORAGE_STATUS_REMOTE),
        (STORAGE_STATUS_VERIFIED, STORAGE_STATUS_VERIFIED),
    ],
)
def test_storage_status_enum_accepts_expected_values(storage_status, expected):
    content = ContentObject(
        content_hash="b" * 64,
        content_type=CONTENT_TYPE_TEXT,
        mime_type="text/plain",
        submitted_by="wallet-a",
        network_name="zoidberg-testnet",
        text_content="hello",
        storage_status=storage_status,
    )

    assert content.storage_status == expected


def test_storage_status_enum_rejects_invalid_values():
    with pytest.raises(ValueError, match="Invalid storage_status"):
        ContentObject(
            content_hash="c" * 64,
            content_type=CONTENT_TYPE_TEXT,
            mime_type="text/plain",
            submitted_by="wallet-a",
            network_name="zoidberg-testnet",
            text_content="hello",
            storage_status="broken",
        )


def test_content_object_round_trips_through_dict():
    original = ContentObject.from_image_metadata(
        submitted_by="wallet-a",
        network_name="zoidberg-testnet",
        mime_type="image/webp",
        file_name="meme.webp",
        file_size_bytes=4242,
        caption="round trip",
        metadata={"variant": 1},
        storage_status=STORAGE_STATUS_VERIFIED,
    )

    restored = ContentObject.from_dict(original.to_dict())

    assert restored.to_dict() == original.to_dict()
