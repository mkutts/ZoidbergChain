"""Reproducible focused corpus report for Milestone 5 Task 5.3."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

from PIL import Image, ImageDraw, ImageEnhance, ImageOps, PngImagePlugin

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from originality import FLAGGED_FOR_REVIEW, HARD_REJECT, OriginalityPipeline


def _bytes(image, format="PNG", **options):
    output = BytesIO()
    image.save(output, format=format, **options)
    return output.getvalue()


def _base_image():
    image = Image.new("RGB", (256, 192), "white")
    draw = ImageDraw.Draw(image)
    for y in range(image.height):
        draw.line((0, y, image.width, y), fill=(y, 80 + y // 3, 220 - y // 2))
    draw.ellipse((35, 25, 150, 140), fill=(230, 45, 70), outline="black", width=5)
    draw.rectangle((145, 55, 235, 155), fill=(25, 80, 170), outline="white", width=4)
    draw.text((25, 160), "ZOIDBERG ORIGINAL", fill="black")
    return image


def _metadata_variant(image):
    info = PngImagePlugin.PngInfo()
    info.add_text("Comment", "metadata-only byte change")
    return _bytes(image, pnginfo=info)


def _jpeg_recompression(image):
    first = _bytes(image, format="JPEG", quality=92)
    with Image.open(BytesIO(first)) as decoded:
        return first, _bytes(decoded.convert("RGB"), format="JPEG", quality=70)


def _case(name, prior, candidate, *, expected_duplicate, prior_text="", candidate_text="", mime="image/png"):
    with tempfile.TemporaryDirectory(prefix="zoidberg-task-5-3-") as directory:
        path = Path(directory) / ("candidate.jpg" if mime == "image/jpeg" else "candidate.png")
        path.write_bytes(candidate)
        calls = iter([prior_text, candidate_text])
        pipeline = OriginalityPipeline(ocr=lambda _image: next(calls))
        block = {
            "index": 1,
            "hash": "a" * 64,
            "submission_id": "minted-source",
            "certificate_id": "certificate-source",
            "mime_type": mime,
            "media_bytes": prior,
        }
        submission = SimpleNamespace(
            submission_id=name,
            content_hash=hashlib.sha256(candidate).hexdigest(),
            image_path=str(path),
            text_content="",
        )
        content = SimpleNamespace(mime_type=mime, local_path=str(path), text_content="")
        evidence = pipeline.evaluate(submission, content, [block], data_dir=directory)
    decision = evidence["final_prevote_decision"]
    fuzzy_flag = decision == FLAGGED_FOR_REVIEW
    return {
        "name": name,
        "expected_duplicate_or_review_worthy": expected_duplicate,
        "decision": decision,
        "reason_codes": evidence["reason_codes"],
        "perceptual_distances": [item["distance"] for item in evidence["perceptual_candidate_matches"]],
        "near_duplicate_distances": [item["distance"] for item in evidence["near_duplicate_candidate_matches"]],
        "ocr_match_count": len(evidence["ocr_candidate_matches"]),
        "fuzzy_true_positive": expected_duplicate and fuzzy_flag,
        "fuzzy_true_negative": not expected_duplicate and not fuzzy_flag,
        "fuzzy_false_positive": not expected_duplicate and fuzzy_flag,
        "fuzzy_false_negative": expected_duplicate and not fuzzy_flag,
    }


def build_report():
    base = _base_image()
    base_png = _bytes(base)
    jpeg_prior, jpeg_recompressed = _jpeg_recompression(base)
    crop = ImageOps.fit(base.crop((8, 6, 248, 186)), base.size, method=Image.Resampling.LANCZOS)
    border = ImageOps.expand(base, border=12, fill="black").resize(base.size, Image.Resampling.LANCZOS)
    unrelated = Image.new("RGB", base.size, "gold")
    ImageDraw.Draw(unrelated).polygon([(0, 0), (255, 80), (90, 191)], fill="purple")

    cases = [
        _case("jpeg_recompression", jpeg_prior, jpeg_recompressed, expected_duplicate=True, mime="image/jpeg"),
        _case("resize", base_png, _bytes(base.resize((384, 288), Image.Resampling.LANCZOS)), expected_duplicate=True),
        _case("small_crop", base_png, _bytes(crop), expected_duplicate=True),
        _case("border_addition", base_png, _bytes(border), expected_duplicate=True),
        _case("brightness_adjustment", base_png, _bytes(ImageEnhance.Brightness(base).enhance(0.82)), expected_duplicate=True),
        _case("color_adjustment", base_png, _bytes(ImageEnhance.Color(base).enhance(0.55)), expected_duplicate=True),
        _case("metadata_only_change", base_png, _metadata_variant(base), expected_duplicate=True),
        _case("same_text_visual_change", base_png, _bytes(unrelated), expected_duplicate=True, prior_text="zoidberg ships this original meme", candidate_text="Zoidberg ships this original meme!"),
        _case("ocr_preserving_edit", base_png, _bytes(ImageEnhance.Contrast(base).enhance(1.2)), expected_duplicate=True, prior_text="deliver the same preserved caption", candidate_text="deliver the same preserved caption"),
        _case("generic_phrase_unrelated", base_png, _bytes(unrelated), expected_duplicate=False, prior_text="hello world", candidate_text="HELLO, WORLD!"),
        _case("changed_meme_text_same_template", base_png, _bytes(base.transpose(Image.Transpose.FLIP_LEFT_RIGHT)), expected_duplicate=False, prior_text="one meaning entirely", candidate_text="materially different meme meaning"),
        _case("same_template_materially_different_text", base_png, _bytes(ImageEnhance.Brightness(base).enhance(0.95)), expected_duplicate=False, prior_text="buy high sell low", candidate_text="community science changes everything"),
        _case("same_generic_phrase_unrelated_imagery", base_png, _bytes(unrelated), expected_duplicate=False, prior_text="good morning", candidate_text="good morning"),
        _case("visually_similar_meaningfully_altered", base_png, _bytes(ImageOps.posterize(base, 2)), expected_duplicate=False, prior_text="original source statement", candidate_text="new derivative statement"),
        _case("no_text_image", base_png, _bytes(unrelated), expected_duplicate=False),
    ]
    exact_cases = [
        _case("exact_same_bytes", base_png, base_png, expected_duplicate=True),
        _case("same_bytes_metadata_unchanged", jpeg_prior, jpeg_prior, expected_duplicate=True, mime="image/jpeg"),
        _case("canonical_minted_duplicate", base_png, base_png, expected_duplicate=True),
    ]
    exact = {
        "true_positives": sum(item["decision"] == HARD_REJECT for item in exact_cases),
        "true_negatives": sum(item["decision"] != HARD_REJECT for item in cases),
        "false_positives": sum(item["decision"] == HARD_REJECT for item in cases),
        "false_negatives": sum(item["decision"] != HARD_REJECT for item in exact_cases),
    }
    fuzzy = {
        "true_positives": sum(item["fuzzy_true_positive"] for item in cases),
        "true_negatives": sum(item["fuzzy_true_negative"] for item in cases),
        "false_positives": sum(item["fuzzy_false_positive"] for item in cases),
        "false_negatives": sum(item["fuzzy_false_negative"] for item in cases),
    }
    return {
        "scope": "focused deterministic Task 5.3 corpus; not proof of global originality",
        "exact_hard_reject": exact,
        "exact_cases": exact_cases,
        "fuzzy_review_flag": fuzzy,
        "cases": cases,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--compact", action="store_true")
    args = parser.parse_args()
    print(json.dumps(build_report(), indent=None if args.compact else 2, sort_keys=True))


if __name__ == "__main__":
    main()
