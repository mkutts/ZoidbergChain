import hashlib
import json
import os
import sqlite3
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytesseract
from PIL import Image, ImageEnhance, ImageOps

from blockchain import Blockchain
from originality import (
    CHECK_FAILED,
    CHECK_SUCCESS,
    CHECK_UNAVAILABLE,
    EXACT_MINTED_CONTENT_DUPLICATE,
    FLAGGED_FOR_REVIEW,
    HARD_REJECT,
    ORIGINALITY_RULE_VERSION,
    PASS,
    DeterministicHammingIndex,
    OriginalityPipeline,
    canonical_minted_media_features,
    normalize_ocr_text,
    originality_evidence_digest,
    originality_rule,
    originality_rule_canonical_text,
    originality_rule_digest,
    validate_originality_evidence,
)
from services.canonical_reorg_service import CanonicalReorgService
from storage import SQLiteStorageBackend
from submission import HARD_REJECTED, PENDING, VOTE_ORIGINAL
from wallet import Wallet
from scripts.task_5_3_adversarial_corpus import build_report
from test_support import fund_native_wallet_with_block


RULE_V1_DIGEST = "0be4f10129899a7da07da1fa5d07297b945d71065fc8474bcedb74a55dd497a5"


def _png_bytes(image):
    from io import BytesIO

    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _block(payload, *, height=1, block_hash="a" * 64, mime_type="image/png"):
    return {
        "index": height,
        "hash": block_hash,
        "submission_id": f"minted-{height}",
        "certificate_id": f"certificate-{height}",
        "mime_type": mime_type,
        "media_bytes": payload,
    }


def _evaluate(tmp_path, candidate, prior, *, candidate_ocr="", prior_ocr="", mime_type="image/png"):
    candidate_path = tmp_path / "candidate.png"
    candidate_path.write_bytes(candidate)
    calls = iter([prior_ocr, candidate_ocr])
    pipeline = OriginalityPipeline(ocr=lambda _image: next(calls))
    chain = [_block(prior)]
    submission = SimpleNamespace(
        submission_id="candidate", content_hash=hashlib.sha256(candidate).hexdigest(),
        image_path=str(candidate_path), text_content="",
    )
    content = SimpleNamespace(mime_type=mime_type, local_path=str(candidate_path), text_content="")
    return pipeline.evaluate(submission, content, chain, data_dir=str(tmp_path))


def _sqlite_chain(tmp_path, name="node"):
    backend = SQLiteStorageBackend(sqlite_db_path=str(tmp_path / name / "chain.db"))
    return Blockchain(Wallet(), Wallet(), Wallet(), storage_backend=backend)


def _mint_image(chain, image_path):
    submission = chain.submit_content(
        image_path=str(image_path), text_content="minted source artwork", submitter="0x" + "1" * 40
    )
    for index in range(5):
        chain.cast_submission_vote(
            submission.submission_id, f"voter-{index}", VOTE_ORIGINAL, created_at=1_000 + index
        )
    chain.evaluate_submission(submission.submission_id, automated_originality_passed=True, now=2_000)
    chain.add_to_mint_queue(submission.submission_id)
    assert chain.mint_next_queued_submission(miner="0x" + "2" * 40, validate_meme=False)
    chain.save_blockchain()
    return submission, chain.get_latest_block()


def test_originality_rule_v1_has_golden_canonical_digest_and_unknown_versions_fail(monkeypatch):
    assert json.loads(originality_rule_canonical_text()) == originality_rule()
    assert originality_rule_digest() == RULE_V1_DIGEST
    monkeypatch.setenv("ORIGINALITY_FLAG_THRESHOLD", "0")
    assert originality_rule_digest() == RULE_V1_DIGEST
    with pytest.raises(ValueError, match="Unsupported originality rule"):
        originality_rule(999)


def test_exact_minted_bytes_hard_reject_with_prior_block_reference(tmp_path):
    image = _png_bytes(Image.new("RGB", (64, 64), "navy"))
    evidence = _evaluate(tmp_path, image, image)
    assert evidence["final_prevote_decision"] == HARD_REJECT
    assert evidence["reason_codes"] == [EXACT_MINTED_CONTENT_DUPLICATE]
    assert evidence["exact_candidate_matches"][0]["block_hash"] == "a" * 64


def test_byte_different_resize_is_flagged_never_hard_rejected(tmp_path):
    source = Image.new("RGB", (80, 80), "white")
    for x in range(10, 70):
        for y in range(15, 65):
            if (x + y) % 5:
                source.putpixel((x, y), (10, 40, 160))
    original = _png_bytes(source)
    resized = _png_bytes(source.resize((120, 120), Image.Resampling.LANCZOS))
    assert original != resized
    evidence = _evaluate(tmp_path, resized, original)
    assert evidence["final_prevote_decision"] == FLAGGED_FOR_REVIEW
    assert evidence["perceptual_candidate_matches"] or evidence["near_duplicate_candidate_matches"]


def test_ocr_normalization_similarity_and_generic_phrase_behavior(tmp_path):
    left = _png_bytes(Image.new("RGB", (64, 64), "white"))
    right = _png_bytes(Image.new("RGB", (64, 64), "black"))
    evidence = _evaluate(
        tmp_path, right, left,
        candidate_ocr="Ship IT, Dr. Zoidberg!", prior_ocr="ship it dr zoidberg",
    )
    assert normalize_ocr_text("  CAFÉ—Test\nHere! ") == "café test here"
    assert evidence["ocr_candidate_matches"]
    generic = _evaluate(
        tmp_path, right, left, candidate_ocr="Hello world", prior_ocr="hello world"
    )
    assert generic["ocr_candidate_matches"] == []


def test_no_text_and_ocr_unavailable_are_distinct(tmp_path):
    image = _png_bytes(Image.new("RGB", (64, 64), "green"))
    empty = _evaluate(tmp_path, image + b"", _png_bytes(Image.new("RGB", (64, 64), "red")))
    assert empty["ocr_result"]["status"] == CHECK_SUCCESS
    assert empty["ocr_result"]["meaningful_text"] is False

    path = tmp_path / "unavailable.png"
    path.write_bytes(image)
    pipeline = OriginalityPipeline(ocr=lambda _image: (_ for _ in ()).throw(RuntimeError("missing")))
    submission = SimpleNamespace(submission_id="s", content_hash=hashlib.sha256(image).hexdigest(), image_path=str(path), text_content="")
    content = SimpleNamespace(mime_type="image/png", local_path=str(path), text_content="")
    evidence = pipeline.evaluate(submission, content, [_block(_png_bytes(Image.new("RGB", (64, 64), "red")))], data_dir=str(tmp_path))
    assert evidence["ocr_result"]["status"] == CHECK_FAILED
    assert evidence["final_prevote_decision"] == FLAGGED_FOR_REVIEW

    unavailable_pipeline = OriginalityPipeline(
        ocr=lambda _image: (_ for _ in ()).throw(pytesseract.TesseractNotFoundError())
    )
    unavailable = unavailable_pipeline.evaluate(
        submission, content,
        [_block(_png_bytes(Image.new("RGB", (64, 64), "red")))],
        data_dir=str(tmp_path),
    )
    assert unavailable["ocr_result"]["status"] == CHECK_UNAVAILABLE


def test_bad_decode_records_failed_fuzzy_layers(tmp_path):
    payload = b"not-an-image"
    path = tmp_path / "bad.png"
    path.write_bytes(payload)
    pipeline = OriginalityPipeline()
    submission = SimpleNamespace(submission_id="bad", content_hash=hashlib.sha256(payload).hexdigest(), image_path=str(path), text_content="")
    content = SimpleNamespace(mime_type="image/png", local_path=str(path), text_content="")
    evidence = pipeline.evaluate(submission, content, [_block(_png_bytes(Image.new("RGB", (8, 8), "red")))], data_dir=str(tmp_path))
    assert evidence["perceptual_hash_result"]["status"] == CHECK_FAILED
    assert evidence["near_duplicate_result"]["status"] == CHECK_FAILED
    assert evidence["final_prevote_decision"] == FLAGGED_FOR_REVIEW


def test_candidate_order_and_digest_are_deterministic(tmp_path):
    image = _png_bytes(Image.new("RGB", (64, 64), "purple"))
    path = tmp_path / "candidate.png"
    path.write_bytes(image)
    chain = [
        _block(image, height=2, block_hash="b" * 64),
        _block(image, height=1, block_hash="a" * 64),
    ]
    pipeline = OriginalityPipeline(ocr=lambda _: "")
    submission = SimpleNamespace(submission_id="s", content_hash=hashlib.sha256(image).hexdigest(), image_path=str(path), text_content="")
    content = SimpleNamespace(mime_type="image/png", local_path=str(path), text_content="")
    evidence = pipeline.evaluate(submission, content, chain, data_dir=str(tmp_path))
    assert [item["block_height"] for item in evidence["exact_candidate_matches"]] == [1, 2]
    assert originality_evidence_digest(evidence) == evidence["canonical_evidence_digest"]
    with_timestamp = {**evidence, "observed_at": "2099-01-01T00:00:00Z"}
    assert originality_evidence_digest(with_timestamp) == evidence["canonical_evidence_digest"]
    changed = deepcopy(evidence)
    changed["reason_codes"] = ["CHANGED"]
    assert originality_evidence_digest(changed) != evidence["canonical_evidence_digest"]
    with pytest.raises(ValueError, match="digest"):
        validate_originality_evidence(changed)


def test_independent_nodes_produce_identical_evidence(tmp_path):
    prior = _png_bytes(Image.new("RGB", (48, 48), "white"))
    candidate = _png_bytes(Image.new("RGB", (48, 48), "navy"))
    path = tmp_path / "same.png"
    path.write_bytes(candidate)
    chain = [_block(prior)]
    submission = SimpleNamespace(
        submission_id="shared-submission", content_hash=hashlib.sha256(candidate).hexdigest(),
        image_path=str(path), text_content="",
    )
    content = SimpleNamespace(mime_type="image/png", local_path=str(path), text_content="")
    first = OriginalityPipeline(ocr=lambda _: "").evaluate(submission, content, chain, data_dir=str(tmp_path))
    second = OriginalityPipeline(ocr=lambda _: "").evaluate(submission, content, deepcopy(chain), data_dir=str(tmp_path))
    assert first == second
    assert first["canonical_evidence_digest"] == second["canonical_evidence_digest"]


def test_bk_tree_results_do_not_depend_on_input_order():
    records = [
        {"perceptual_hash": value, "block_height": index, "block_hash": f"{index:064x}", "content_hash": f"{index + 10:064x}"}
        for index, value in enumerate(["0000000000000000", "0000000000000001", "ffffffffffffffff"])
    ]
    forward = DeterministicHammingIndex(records, "perceptual_hash").query("0000000000000000", 1)
    reverse = DeterministicHammingIndex(list(reversed(records)), "perceptual_hash").query("0000000000000000", 1)
    assert forward == reverse


def test_sqlite_exact_duplicate_is_rejected_before_vote_and_survives_restart(tmp_path, submission_image):
    chain = _sqlite_chain(tmp_path)
    _source, minted_block = _mint_image(chain, submission_image)
    duplicate = chain.submit_content_operation(
        image_path=str(submission_image), text_content="new caption cannot change bytes", submitter="other"
    )
    evidence = chain.get_originality_evidence(duplicate.submission_id)
    assert duplicate.status == HARD_REJECTED
    assert evidence["final_prevote_decision"] == HARD_REJECT
    assert evidence["exact_candidate_matches"][0]["block_hash"] == minted_block.hash
    with pytest.raises(ValueError, match="cannot receive votes"):
        chain.cast_submission_vote(duplicate.submission_id, "reviewer", VOTE_ORIGINAL)

    reloaded = Blockchain(storage_backend=chain.storage)
    restored = reloaded.get_submission(duplicate.submission_id)
    assert restored.status == HARD_REJECTED
    assert reloaded.get_originality_evidence(duplicate.submission_id) == evidence
    history = chain.storage.list_originality_evidence_history(duplicate.submission_id)
    assert history[-1]["is_current"] is True


def test_flagged_and_pass_submissions_can_vote(tmp_path):
    chain = _sqlite_chain(tmp_path)
    clean = chain.upload_text_content(text_content="entirely fresh deterministic prose", submitted_by="creator")
    passed = chain.submit_content_operation(content_hash=clean.content_hash, content_id=clean.content_id, text_content=clean.text_content, submitter="creator")
    assert chain.get_originality_evidence(passed.submission_id)["final_prevote_decision"] == PASS
    chain.cast_submission_vote(passed.submission_id, "reviewer-a", VOTE_ORIGINAL)

    remote = chain.register_remote_content_reference(
        content_hash="f" * 64, submitted_by="creator", mime_type="image/png",
        content_type="image", storage_status="remote",
    )
    flagged = chain.submit_content_operation(content_hash=remote.content_hash, content_id=remote.content_id, submitter="creator")
    evidence = chain.get_originality_evidence(flagged.submission_id)
    assert evidence["final_prevote_decision"] == FLAGGED_FOR_REVIEW
    assert evidence["perceptual_hash_result"]["status"] == CHECK_UNAVAILABLE
    chain.cast_submission_vote(flagged.submission_id, "reviewer-b", VOTE_ORIGINAL)


def test_later_chain_growth_does_not_retroactively_change_evidence(tmp_path):
    chain = _sqlite_chain(tmp_path)
    content = chain.upload_text_content(
        text_content="stable historical originality reference", submitted_by="creator"
    )
    submission = chain.submit_content_operation(
        content_hash=content.content_hash, content_id=content.content_id,
        text_content=content.text_content, submitter="creator",
    )
    before = deepcopy(chain.get_originality_evidence(submission.submission_id))
    fund_native_wallet_with_block(chain, "0x" + "3" * 40, persist=True)
    after = chain.ensure_current_originality_evidence(submission.submission_id)
    assert after == before


def test_corrupt_sqlite_index_digest_is_detected_and_rebuilt(tmp_path):
    chain = _sqlite_chain(tmp_path)
    assert chain._minted_originality_index() == []
    with sqlite3.connect(chain.storage.sqlite_db_path) as connection:
        connection.execute("UPDATE originality_index_metadata SET index_digest = 'corrupt'")
    assert chain.storage.load_minted_media_originality_index(
        rule_version=ORIGINALITY_RULE_VERSION,
        head_height=chain.chain[-1].index,
        head_hash=chain.chain[-1].hash,
    ) is None
    chain._originality_index_cache_head = None
    chain._originality_index_cache_records = None
    assert chain._minted_originality_index() == []
    with sqlite3.connect(chain.storage.sqlite_db_path) as connection:
        assert connection.execute("SELECT index_digest FROM originality_index_metadata").fetchone()[0] != "corrupt"


def test_sqlite_migration_is_idempotent_and_preserves_task_52_tables(tmp_path):
    path = tmp_path / "migration.db"
    first = SQLiteStorageBackend(sqlite_db_path=str(path))
    first.initialize_reviewer_state("0x" + "1" * 40)
    SQLiteStorageBackend(sqlite_db_path=str(path))
    with sqlite3.connect(path) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"reviewer_states", "durable_vote_records", "originality_evidence_records", "originality_evidence_matches", "minted_media_originality_index"} <= tables
        assert connection.execute("SELECT COUNT(*) FROM reviewer_states").fetchone()[0] == 1


def test_stale_fork_evidence_is_removed_for_recomputation():
    document = {
        "originality_evidence": [{
            "submission_id": "stale",
            "originality_reference_height": 1,
            "originality_reference_block_hash": "a" * 64,
        }]
    }
    winning = [{"index": 0, "hash": "0" * 64}, {"index": 1, "hash": "b" * 64}]
    invalidated = CanonicalReorgService._invalidate_stale_originality_evidence(document, winning)
    assert invalidated == ["stale"]
    assert document["originality_evidence"] == []


def test_index_rebuild_is_deterministic_and_excludes_genesis_artwork():
    image = _png_bytes(Image.new("RGB", (16, 16), "orange"))
    genesis = {"index": 0, "hash": "0" * 64, "mime_type": "image/png", "media_bytes": image}
    minted = _block(image)
    first = canonical_minted_media_features([genesis, minted], ocr=lambda _: "")
    second = canonical_minted_media_features([genesis, minted], ocr=lambda _: "")
    assert first == second
    assert len(first) == 1


def test_focused_adversarial_corpus_observations_are_reproducible():
    report = build_report()
    assert report["exact_hard_reject"] == {
        "true_positives": 3, "true_negatives": 15,
        "false_positives": 0, "false_negatives": 0,
    }
    assert report["fuzzy_review_flag"] == {
        "true_positives": 8, "true_negatives": 4,
        "false_positives": 2, "false_negatives": 1,
    }
