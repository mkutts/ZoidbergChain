import asyncio
import hashlib
import io
import json
import zlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

import media_technical_validation as technical
from media_admission_policy import (
    REASON_DECLARED_MIME_MISMATCH,
    REASON_DISALLOWED_ARCHIVE,
    REASON_EXCEEDS_ACCEPTED_MEDIA_BYTE_LIMIT,
    REASON_EXCEEDS_DIMENSION_LIMIT,
    REASON_EXCEEDS_FRAME_LIMIT,
    REASON_EXCEEDS_PIXEL_LIMIT,
    REASON_EXCEEDS_TEXT_BYTE_LIMIT,
    REASON_EXECUTABLE_OR_SCRIPT,
    REASON_MALFORMED_MEDIA,
    REASON_RESOURCE_LIMIT_TERMINATED,
    REASON_UNSUPPORTED_METADATA,
    REASON_UNSUPPORTED_MEDIA_TYPE,
)
from media_technical_validation import (
    TechnicalMediaValidationError,
    sanitize_display_filename,
    validate_media_bytes,
    validate_technical_evidence,
)
from peers import PeerStore
from blockchain import Blockchain


def _image_bytes(format_name, size=(3, 2), *, frames=1):
    buffer = io.BytesIO()
    if frames == 1:
        Image.new("RGB", size, "red").save(buffer, format=format_name)
    else:
        images = [Image.new("P", size, number % 2) for number in range(frames)]
        images[0].save(
            buffer,
            format=format_name,
            save_all=True,
            append_images=images[1:],
            duration=10,
            loop=0,
            optimize=False,
        )
    return buffer.getvalue()


def _client(blockchain):
    import api
    api.limiter.reset()
    api.blockchain = blockchain
    api.peer_store = PeerStore(storage_backend=blockchain.storage)
    return TestClient(api.app)


def _reasons(payload, **kwargs):
    with pytest.raises(TechnicalMediaValidationError) as exc_info:
        validate_media_bytes(payload, **kwargs)
    return exc_info.value.result["reason_codes"]


@pytest.mark.parametrize(
    ("format_name", "mime_type", "media_type"),
    [("JPEG", "image/jpeg", "jpeg"), ("PNG", "image/png", "png"),
     ("GIF", "image/gif", "gif"), ("WEBP", "image/webp", "webp")],
)
def test_m6_ac03_all_supported_images_require_complete_decode(format_name, mime_type, media_type):
    payload = _image_bytes(format_name)
    validated = validate_media_bytes(payload, declared_mime_type=mime_type)
    assert validated.raw_media_bytes == payload
    assert validated.result["detected_media_type"] == media_type
    assert validated.result["raw_media_sha256"] == hashlib.sha256(payload).hexdigest()
    assert validated.result["width_pixels"] == 3
    assert validated.result["height_pixels"] == 2
    assert validated.result["frame_count"] == 1


@pytest.mark.parametrize(
    "payload",
    [
        _image_bytes("JPEG")[:-2],
        _image_bytes("PNG")[:-8],
        b"GIF89a" + b"\x00" * 20,
        b"RIFF\x0c\x00\x00\x00WEBPbad!",
        b"\xff\xfeinvalid utf8",
    ],
)
def test_m6_ac03_corrupt_or_invalid_encoding_rejected(payload):
    reasons = _reasons(payload)
    assert set(reasons) & {REASON_MALFORMED_MEDIA, REASON_UNSUPPORTED_MEDIA_TYPE}


@pytest.mark.parametrize(
    ("payload", "declared", "expected"),
    [
        (b"MZ" + b"\x00" * 30, "image/jpeg", REASON_EXECUTABLE_OR_SCRIPT),
        (b"#!/bin/sh\necho unsafe", "image/png", REASON_EXECUTABLE_OR_SCRIPT),
        (b"PK\x03\x04" + b"\x00" * 30, "image/png", REASON_DISALLOWED_ARCHIVE),
        (b"%PDF-1.7\nplain-looking bytes", None, REASON_UNSUPPORTED_MEDIA_TYPE),
        (b"\x00\x01\x02\x03", "text/plain", REASON_UNSUPPORTED_MEDIA_TYPE),
        (b"<script>alert(1)</script>", "image/png", REASON_EXECUTABLE_OR_SCRIPT),
    ],
)
def test_m6_ac03_type_confusion_and_dangerous_prefixes_rejected(payload, declared, expected):
    assert expected in _reasons(payload, declared_mime_type=declared, original_filename="renamed.jpg")


def test_m6_ac03_declared_mime_mismatch_rejects_but_extension_is_non_authoritative():
    png = _image_bytes("PNG")
    assert REASON_DECLARED_MIME_MISMATCH in _reasons(
        png, declared_mime_type="image/jpeg", original_filename="image.jpg"
    )
    accepted = validate_media_bytes(
        png, declared_mime_type="image/png", original_filename="misleading.jpg"
    )
    assert accepted.result["extension_matches_detected_type"] is False


def test_m6_ac04_dimension_bomb_rejected_before_decoder(monkeypatch):
    payload = _image_bytes("PNG", (4097, 1))
    called = False

    def decoder(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("decoder must not run")

    monkeypatch.setattr(technical, "_run_isolated_decoder", decoder)
    assert REASON_EXCEEDS_DIMENSION_LIMIT in _reasons(payload, declared_mime_type="image/png")
    assert called is False
    assert len(payload) < 262_144


def test_m6_ac04_frame_limit_and_boundary_metadata(monkeypatch):
    gif = _image_bytes("GIF", frames=2)
    monkeypatch.setattr(technical, "_run_isolated_decoder", lambda *a, **k: {
        "width": 4096, "height": 4096, "frame_count": 60,
        "aggregate_decoded_pixels": 16_777_216,
    })
    accepted = validate_media_bytes(gif, declared_mime_type="image/gif")
    assert accepted.result["frame_count"] == 60
    monkeypatch.setattr(technical, "_run_isolated_decoder", lambda *a, **k: {
        "width": 1, "height": 1, "frame_count": 61,
        "aggregate_decoded_pixels": 61,
    })
    assert REASON_EXCEEDS_FRAME_LIMIT in _reasons(gif, declared_mime_type="image/gif")


def test_m6_ac04_aggregate_pixel_limit_rejects_after_bounded_decode(monkeypatch):
    gif = _image_bytes("GIF", frames=2)
    monkeypatch.setattr(technical, "_run_isolated_decoder", lambda *a, **k: {
        "width": 4096, "height": 4096, "frame_count": 2,
        "aggregate_decoded_pixels": 16_777_217,
    })
    assert REASON_EXCEEDS_PIXEL_LIMIT in _reasons(gif, declared_mime_type="image/gif")


def test_m6_ac04_resource_timeout_and_worker_failure_fail_closed(monkeypatch):
    png = _image_bytes("PNG")
    monkeypatch.setattr(technical, "_run_isolated_decoder", lambda *a, **k: (_ for _ in ()).throw(TimeoutError()))
    assert REASON_RESOURCE_LIMIT_TERMINATED in _reasons(png, declared_mime_type="image/png")
    monkeypatch.setattr(technical, "_run_isolated_decoder", lambda *a, **k: (_ for _ in ()).throw(RuntimeError()))
    assert REASON_MALFORMED_MEDIA in _reasons(png, declared_mime_type="image/png")


def test_m6_ac03_plain_text_is_strict_canonical_utf8_and_not_script():
    validated = validate_media_bytes(b"  hello\r\nworld  ", declared_mime_type="text/plain")
    assert validated.raw_media_bytes == b"hello\nworld"
    assert validated.result["raw_media_semantics"] == "policy_canonical_utf8_text"
    assert REASON_UNSUPPORTED_MEDIA_TYPE in _reasons(b"hello\x00world", declared_mime_type="text/plain")


@pytest.mark.parametrize(
    ("unsafe", "fragment"),
    [
        ("../../evil.png", "evil.png"),
        (r"C:\\Windows\\system32\\evil.png", "evil.png"),
        ("bad\x00name.png", "bad_name.png"),
        ("bad\x01name.png", "bad_name.png"),
        ("CON.jpg", "upload_CON.jpg"),
    ],
)
def test_m6_ac03_filename_is_display_only_and_safely_normalized(unsafe, fragment):
    safe = sanitize_display_filename(unsafe)
    assert safe.endswith(fragment)
    assert "/" not in safe and "\\" not in safe and "\x00" not in safe


def test_m6_ac03_overlong_filename_uses_frozen_ascii_bound():
    safe = sanitize_display_filename("x" * 1000 + ".png")
    assert len(safe.encode("ascii")) == 255


def test_m6_ac03_transport_metadata_is_not_protocol_identity():
    png = _image_bytes("PNG")
    upload = validate_media_bytes(
        png, declared_mime_type="image/png", original_filename="local-name.png"
    ).result
    peer = validate_media_bytes(png).result

    assert upload["safe_display_filename"] == "local-name.png"
    assert peer["safe_display_filename"] is None
    assert upload["evidence_digest"] == peer["evidence_digest"]


def test_m6_ac04_actual_media_byte_boundary_via_public_upload(blockchain, wallets):
    client = _client(blockchain)
    exact = b"x" * 262_144
    response = client.post(
        "/content/upload",
        data={"submitted_by": wallets["owner"].public_key},
        files={"file": ("exact.txt", exact, "text/plain")},
    )
    assert response.status_code == 200
    over = client.post(
        "/content/upload",
        data={"submitted_by": wallets["owner"].public_key},
        files={"file": ("over.txt", exact + b"x", "text/plain")},
    )
    assert over.status_code == 413
    assert len(blockchain.content_objects) == 1


def test_m6_ac04_content_length_request_limit_rejects_before_route(blockchain, wallets):
    response = _client(blockchain).post(
        "/content/upload",
        data={"submitted_by": wallets["owner"].public_key},
        files={"file": ("huge.txt", b"x" * 5_308_416, "text/plain")},
    )
    assert response.status_code == 413
    assert len(blockchain.content_objects) == 0


def test_m6_ac04_missing_or_false_content_length_is_still_counted():
    called = False

    async def downstream(scope, receive, send):
        nonlocal called
        called = True
        while (await receive()).get("more_body"):
            pass

    middleware = technical.TechnicalMediaRequestLimitMiddleware(downstream)
    scope = {"type": "http", "path": "/content/text", "headers": [(b"content-type", b"application/json"), (b"content-length", b"1")]}
    messages = iter([
        {"type": "http.request", "body": b"x" * 327_681, "more_body": False},
    ])
    sent = []
    asyncio.run(middleware(scope, lambda: asyncio.sleep(0, result=next(messages)), lambda message: asyncio.sleep(0, result=sent.append(message))))
    assert called is True
    assert sent[0]["status"] == 413


def test_m6_ac01_invalid_media_never_reaches_storage_or_originality(blockchain, wallets, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("expensive or durable work was reached")

    monkeypatch.setattr(blockchain._originality_pipeline, "evaluate", forbidden)
    import services.content_coordination_service as coordination
    monkeypatch.setattr(coordination, "store_content_bytes", forbidden)
    with pytest.raises(TechnicalMediaValidationError):
        blockchain.upload_binary_content(
            file_bytes=b"MZ" + b"\x00" * 20,
            submitted_by=wallets["owner"].public_key,
            mime_type="image/jpeg",
            original_filename="attack.jpg",
        )
    assert blockchain.submissions == []
    assert blockchain.content_objects == []
    assert blockchain.originality_evidence == []
    assert len(blockchain.chain) == 1


def test_m6_ac01_public_invalid_upload_creates_no_review_or_permanent_file(blockchain, wallets):
    content_root = Path(blockchain.storage.data_dir) / "content"
    response = _client(blockchain).post(
        "/content/upload",
        data={"submitted_by": wallets["owner"].public_key},
        files={"file": ("attack.jpg", b"MZ" + b"\x00" * 20, "image/jpeg")},
    )
    assert response.status_code == 400
    assert blockchain.content_objects == []
    assert blockchain.submissions == []
    assert not content_root.exists() or list(content_root.iterdir()) == []


def test_m6_ac04_ocr_default_has_frozen_local_timeout(monkeypatch):
    import originality
    observed = {}

    def fake_ocr(image, **kwargs):
        observed.update(kwargs)
        raise RuntimeError("local timeout")

    monkeypatch.setattr(originality.pytesseract, "image_to_string", fake_ocr)
    features = originality._image_features(_image_bytes("PNG"))
    assert observed["timeout"] == 5
    assert features["ocr"]["status"] == originality.CHECK_FAILED


def test_m6_ac03_evidence_is_durable_and_unknown_versions_fail_safe(blockchain, wallets):
    payload = _image_bytes("PNG")
    content = blockchain.upload_binary_content_operation(
        file_bytes=payload,
        submitted_by=wallets["owner"].public_key,
        mime_type="image/png",
        original_filename="durable.png",
    )
    evidence = content.metadata["technical_validation"]
    assert validate_technical_evidence(evidence, payload)["outcome"] == "ACCEPT"
    persisted = blockchain.storage.get_content_object_by_hash(content.content_hash)
    assert persisted["metadata"]["technical_validation"]["evidence_digest"] == evidence["evidence_digest"]
    invalid = dict(evidence)
    invalid["evidence_version"] = 999
    with pytest.raises(ValueError, match="Unsupported technical validation evidence version"):
        validate_technical_evidence(invalid, payload)


def test_m6_ac03_polyglot_trailing_payload_rejected():
    assert REASON_MALFORMED_MEDIA in _reasons(
        _image_bytes("PNG") + b"PK\x03\x04archive",
        declared_mime_type="image/png",
    )


def test_m6_ac03_unknown_png_metadata_rejected_fail_closed():
    png = _image_bytes("PNG")
    iend_offset = png.rfind(b"\x00\x00\x00\x00IEND")
    chunk_type = b"vpAg"
    chunk_data = b"opaque"
    chunk = (
        len(chunk_data).to_bytes(4, "big")
        + chunk_type
        + chunk_data
        + (zlib.crc32(chunk_type + chunk_data) & 0xFFFFFFFF).to_bytes(4, "big")
    )
    with pytest.raises(TechnicalMediaValidationError) as exc:
        validate_media_bytes(png[:iend_offset] + chunk + png[iend_offset:])

    assert REASON_UNSUPPORTED_METADATA in exc.value.result["reason_codes"]


def test_m6_ac04_environment_cannot_relax_mime_or_size(monkeypatch):
    monkeypatch.setenv("MAX_CONTENT_FILE_SIZE_BYTES", "999999999")
    monkeypatch.setenv("ENABLE_STRICT_MIME_VALIDATION", "false")
    assert REASON_EXCEEDS_TEXT_BYTE_LIMIT in _reasons(
        b"x" * 262_145, declared_mime_type="text/plain"
    )
    assert REASON_DECLARED_MIME_MISMATCH in _reasons(
        _image_bytes("PNG"), declared_mime_type="image/jpeg"
    )


def test_task_6_3a_promotion_reuses_exact_persisted_pass_after_restart(
    blockchain, submission_image, wallets, monkeypatch
):
    import services.content_coordination_service as coordination

    original_validate = coordination.validate_media_bytes
    validation_calls = 0

    def counted_validate(*args, **kwargs):
        nonlocal validation_calls
        validation_calls += 1
        return original_validate(*args, **kwargs)

    monkeypatch.setattr(coordination, "validate_media_bytes", counted_validate)
    submission = blockchain.submit_content(
        image_path=str(submission_image),
        text_content="Persisted validation reuse",
        submitter=wallets["owner"].public_key,
    )
    assert validation_calls == 1
    blockchain.promote_submission_content_for_protocol_v1(submission)
    blockchain.promote_submission_content_for_protocol_v1(submission)
    assert validation_calls == 1

    blockchain.save_blockchain()
    restored = Blockchain(
        project_owner_wallet=wallets["owner"],
        Contributor_one=wallets["contributor_one"],
        Contributor_two=wallets["contributor_two"],
        storage_backend=blockchain.storage,
    )
    restored_submission = restored.get_submission(submission.submission_id)
    restored.promote_submission_content_for_protocol_v1(restored_submission)
    assert validation_calls == 1


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("evidence_version", 999, "evidence version"),
        ("validator_id", "different-validator/1", "validator identity"),
        ("policy_version", 999, "policy version"),
        ("policy_digest", "0" * 64, "policy digest"),
        ("outcome", "REJECT", "not an acceptance"),
        ("evidence_digest", "0" * 64, "evidence digest"),
    ],
)
def test_task_6_3a_persisted_evidence_identity_mismatch_never_reuses(
    field, value, message
):
    payload = b"exact persisted media"
    evidence = validate_media_bytes(payload, declared_mime_type="text/plain").result
    evidence[field] = value
    with pytest.raises(ValueError, match=message):
        validate_technical_evidence(evidence, payload)


def test_task_6_3a_stale_evidence_never_authorizes_different_bytes():
    payload = b"exact persisted media"
    evidence = validate_media_bytes(payload, declared_mime_type="text/plain").result
    with pytest.raises(ValueError, match="does not bind"):
        validate_technical_evidence(evidence, payload + b"!")


def test_task_6_3a_failed_or_incomplete_evidence_is_never_reused():
    with pytest.raises(TechnicalMediaValidationError):
        validate_media_bytes(b"MZ rejected executable", declared_mime_type="text/plain")
    accepted = validate_media_bytes(b"retry with valid text", declared_mime_type="text/plain")
    incomplete = dict(accepted.result)
    incomplete.pop("evidence_digest")
    with pytest.raises(ValueError, match="evidence digest"):
        validate_technical_evidence(incomplete, accepted.raw_media_bytes)


def test_task_6_3a_concurrent_promotion_reuses_only_persisted_exact_evidence(
    blockchain, submission_image, wallets, monkeypatch
):
    submission = blockchain.submit_content(
        image_path=str(submission_image),
        text_content="Concurrent persisted validation reuse",
        submitter=wallets["owner"].public_key,
    )
    import services.content_coordination_service as coordination
    monkeypatch.setattr(
        coordination,
        "validate_media_bytes",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("durable PASS evidence should be reused")
        ),
    )
    with ThreadPoolExecutor(max_workers=8) as executor:
        promoted = list(
            executor.map(
                blockchain.promote_submission_content_for_protocol_v1,
                [submission] * 16,
            )
        )
    assert {item.content_hash for item in promoted} == {submission.content_hash}


def test_task_6_3a_tampered_stored_evidence_or_media_fails_promotion(
    blockchain, submission_image, wallets
):
    submission = blockchain.submit_content(
        image_path=str(submission_image),
        text_content="Tamper-resistant validation reuse",
        submitter=wallets["owner"].public_key,
    )
    content = blockchain.get_content_object_by_hash(submission.content_hash)
    evidence = dict(content.metadata["technical_validation"])
    content.metadata["technical_validation"] = {**evidence, "evidence_digest": "0" * 64}
    with pytest.raises(ValueError, match="evidence digest"):
        blockchain.promote_submission_content_for_protocol_v1(submission)

    content.metadata["technical_validation"] = evidence
    stored_path = Path(submission.image_path)
    stored_path.write_bytes(stored_path.read_bytes() + b"!")
    with pytest.raises(ValueError, match="does not bind"):
        blockchain.promote_submission_content_for_protocol_v1(submission)


def test_task_6_3a_chain_prefix_cache_loss_revalidates_and_tampering_fails_closed(
    blockchain
):
    blockchain._validated_chain_prefix_hashes = None
    blockchain._ensure_validated_chain_prefix(blockchain.chain)
    assert blockchain._validated_chain_prefix_hashes == tuple(
        block.hash for block in blockchain.chain
    )

    blockchain.chain[0].miner = "tampered-after-validation"
    with pytest.raises(ValueError, match="Genesis payload|failed validation"):
        blockchain._ensure_validated_chain_prefix(blockchain.chain)
