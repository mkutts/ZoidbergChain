"""Versioned deterministic pre-vote originality evidence for Milestone 5.3.

Exact SHA-256 matching is the only v1 hard-reject rule.  Image and text
similarity are review signals: they can flag a submission, but can never reject
it automatically.
"""

from __future__ import annotations

import hashlib
import io
import re
import unicodedata
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from PIL import Image, ImageOps
import imagehash
import pytesseract

from content import SUPPORTED_IMAGE_MIME_TYPES, TEXT_MIME_TYPE, load_content_bytes, resolve_local_path
from protocol_v1 import PUBLIC_TESTNET_V1_NETWORK_ID, canonical_hash, canonical_json_text


ORIGINALITY_RULE_VERSION = 1
ORIGINALITY_EVIDENCE_VERSION = 1

PASS = "PASS"
FLAGGED_FOR_REVIEW = "FLAGGED_FOR_REVIEW"
HARD_REJECT = "HARD_REJECT"

CHECK_NOT_APPLICABLE = "NOT_APPLICABLE"
CHECK_UNAVAILABLE = "UNAVAILABLE"
CHECK_FAILED = "FAILED"
CHECK_SUCCESS = "SUCCESS"

EXACT_MINTED_CONTENT_DUPLICATE = "EXACT_MINTED_CONTENT_DUPLICATE"
PERCEPTUAL_SIMILARITY = "PERCEPTUAL_SIMILARITY"
OCR_TEXT_SIMILARITY = "OCR_TEXT_SIMILARITY"
NEAR_DUPLICATE_SIMILARITY = "NEAR_DUPLICATE_SIMILARITY"
FUZZY_CHECK_INCOMPLETE = "FUZZY_CHECK_INCOMPLETE"

_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_HEX_16 = re.compile(r"^[0-9a-f]{16}$")
_TOKEN_RE = re.compile(r"\w+", flags=re.UNICODE)

_ORIGINALITY_RULES: dict[int, dict[str, Any]] = {
    1: {
        "network_id": PUBLIC_TESTNET_V1_NETWORK_ID,
        "policy_kind": "originality",
        "originality_rule_version": 1,
        "evidence_version": 1,
        "accepted_media_types": sorted([*SUPPORTED_IMAGE_MIME_TYPES, TEXT_MIME_TYPE]),
        "exact": {
            "algorithm": "sha256-full-immutable-media-bytes-v1",
            "hard_reject_reason": EXACT_MINTED_CONTENT_DUPLICATE,
            "pending_submission_matches_do_not_reject": True,
        },
        "image_normalization": {
            "decoder": "pillow",
            "frame": "first-frame-only",
            "orientation": "exif-transpose-before-color-conversion",
            "color_mode": "rgb-srgb-values-without-profile-conversion",
            "alpha": "composite-over-opaque-white",
            "perceptual_resize": "imagehash-average-hash-8x8-lanczos",
            "near_duplicate_resize": "imagehash-dhash-9x8-lanczos",
            "decode_failure": CHECK_FAILED,
        },
        "perceptual": {
            "algorithm": "imagehash-average-hash-v1",
            "hash_bits": 64,
            "flag_hamming_distance_lte": 8,
            "hard_reject_enabled": False,
        },
        "near_duplicate": {
            "algorithm": "imagehash-difference-hash-v1",
            "hash_bits": 64,
            "flag_hamming_distance_lte": 10,
            "candidate_index": "deterministic-bk-tree-hamming-v1",
            "hard_reject_enabled": False,
        },
        "ocr": {
            "algorithm": "tesseract-eng-psm11-oem1-v1",
            "preprocess": "exif-rgb-white-alpha-grayscale-autocontrast-threshold-160",
            "tesseract_config": "--psm 11 --oem 1 -l eng",
            "unicode_normalization": "NFKC",
            "case_normalization": "casefold",
            "punctuation": "replace-with-space",
            "whitespace": "unicode-whitespace-collapse",
            "minimum_normalized_characters": 12,
            "minimum_distinct_tokens": 3,
            "similarity": "set-jaccard",
            "flag_numerator": 4,
            "flag_denominator": 5,
            "generic_phrases_ignored": [
                "good morning", "happy birthday", "hello world", "thank you",
            ],
            "hard_reject_enabled": False,
            "runtime_requirement": "Tesseract 5.x with eng traineddata; unavailable/failed checks flag review",
        },
        "failure_policy": {
            "exact_hash": "mandatory",
            "fuzzy_unavailable_or_failed": FLAGGED_FOR_REVIEW,
        },
        "candidate_order": ["distance", "block_height", "block_hash", "content_hash"],
    }
}


def originality_rule(version: int = ORIGINALITY_RULE_VERSION) -> dict[str, Any]:
    if isinstance(version, bool) or not isinstance(version, int):
        raise ValueError("Originality rule version must be an integer.")
    try:
        return deepcopy(_ORIGINALITY_RULES[version])
    except KeyError as exc:
        raise ValueError(f"Unsupported originality rule version: {version}") from exc


def originality_rule_canonical_text(version: int = ORIGINALITY_RULE_VERSION) -> str:
    return canonical_json_text(originality_rule(version))


def originality_rule_digest(version: int = ORIGINALITY_RULE_VERSION) -> str:
    return canonical_hash(originality_rule(version))


def normalize_ocr_text(value: str) -> str:
    """Canonical NFKC/casefold/punctuation/whitespace normalization."""
    normalized = unicodedata.normalize("NFKC", str(value or "")).casefold()
    normalized = "".join(
        " " if unicodedata.category(character).startswith("P") else character
        for character in normalized
    )
    return " ".join(normalized.split())


def _meaningful_text(normalized: str, rule: dict[str, Any]) -> bool:
    ocr = rule["ocr"]
    tokens = set(_TOKEN_RE.findall(normalized))
    return (
        len(normalized) >= ocr["minimum_normalized_characters"]
        and len(tokens) >= ocr["minimum_distinct_tokens"]
        and normalized not in set(ocr["generic_phrases_ignored"])
    )


def _token_similarity(left: str, right: str) -> tuple[int, int]:
    left_tokens = set(_TOKEN_RE.findall(left))
    right_tokens = set(_TOKEN_RE.findall(right))
    union = left_tokens | right_tokens
    if not union:
        return 0, 1
    return len(left_tokens & right_tokens), len(union)


def _image_from_bytes(payload: bytes) -> Image.Image:
    with Image.open(io.BytesIO(payload)) as source:
        source.seek(0)
        frame = ImageOps.exif_transpose(source.copy())
    if frame.mode in {"RGBA", "LA"} or "transparency" in frame.info:
        rgba = frame.convert("RGBA")
        background = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        frame = Image.alpha_composite(background, rgba).convert("RGB")
    else:
        frame = frame.convert("RGB")
    return frame


def _image_features(payload: bytes, *, ocr: Callable[[Image.Image], str] | None = None) -> dict[str, Any]:
    image = _image_from_bytes(payload)
    perceptual_hash = str(imagehash.average_hash(image, hash_size=8))
    near_hash = str(imagehash.dhash(image, hash_size=8))
    ocr_result: dict[str, Any]
    try:
        extractor = ocr or (
            lambda prepared: pytesseract.image_to_string(
                prepared, config="--psm 11 --oem 1 -l eng"
            )
        )
        prepared = ImageOps.autocontrast(image.convert("L")).point(
            lambda pixel: 255 if pixel >= 160 else 0
        )
        normalized_text = normalize_ocr_text(extractor(prepared))
        ocr_result = {"status": CHECK_SUCCESS, "normalized_text": normalized_text}
    except pytesseract.TesseractNotFoundError:
        ocr_result = {"status": CHECK_UNAVAILABLE, "normalized_text": ""}
    except Exception:
        ocr_result = {"status": CHECK_FAILED, "normalized_text": ""}
    return {
        "perceptual_hash": perceptual_hash,
        "near_duplicate_hash": near_hash,
        "ocr": ocr_result,
    }


def _block_value(block: Any, name: str, default=None):
    return block.get(name, default) if isinstance(block, dict) else getattr(block, name, default)


def _block_media_bytes(block: Any) -> bytes | None:
    value = _block_value(block, "media_bytes")
    if value is None:
        return None
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value)
    from protocol_v1 import decode_canonical_bytes
    return decode_canonical_bytes(value)


def canonical_minted_media_features(
    chain: list[Any], *, ocr: Callable[[Image.Image], str] | None = None
) -> list[dict[str, Any]]:
    """Rebuild the deterministic optimization index from canonical blocks."""
    records: list[dict[str, Any]] = []
    for block in chain or []:
        # Genesis carries frozen network artwork but is not an accepted media
        # submission.  The v1 duplicate corpus is certified/minted content.
        if not _block_value(block, "submission_id") or not _block_value(block, "certificate_id"):
            continue
        block_hash = str(_block_value(block, "hash") or "").strip().lower()
        height = _block_value(block, "index")
        media = _block_media_bytes(block)
        if not block_hash or height is None or media is None:
            continue
        content_hash = hashlib.sha256(media).hexdigest()
        mime_type = str(_block_value(block, "mime_type") or "application/octet-stream").lower()
        record = {
            "block_height": int(height),
            "block_hash": block_hash,
            "content_hash": content_hash,
            "mime_type": mime_type,
            "perceptual_hash": None,
            "near_duplicate_hash": None,
            "ocr_status": CHECK_NOT_APPLICABLE,
            "normalized_text": "",
            "normalized_text_hash": None,
        }
        if mime_type in SUPPORTED_IMAGE_MIME_TYPES:
            try:
                features = _image_features(media, ocr=ocr)
            except Exception:
                record["ocr_status"] = CHECK_FAILED
            else:
                record["perceptual_hash"] = features["perceptual_hash"]
                record["near_duplicate_hash"] = features["near_duplicate_hash"]
                record["ocr_status"] = features["ocr"]["status"]
                record["normalized_text"] = features["ocr"]["normalized_text"]
        elif mime_type == TEXT_MIME_TYPE:
            try:
                record["normalized_text"] = normalize_ocr_text(media.decode("utf-8", errors="strict"))
                record["ocr_status"] = CHECK_SUCCESS
            except UnicodeDecodeError:
                record["ocr_status"] = CHECK_FAILED
        if record["normalized_text"]:
            record["normalized_text_hash"] = hashlib.sha256(
                record["normalized_text"].encode("utf-8")
            ).hexdigest()
        records.append(record)
    return sorted(records, key=lambda item: (item["block_height"], item["block_hash"]))


@dataclass
class _BKNode:
    value: str
    records: list[dict[str, Any]]
    children: dict[int, "_BKNode"]


class DeterministicHammingIndex:
    """A rebuildable exact BK-tree over fixed-width hexadecimal hashes."""

    def __init__(self, records: list[dict[str, Any]], field: str):
        self.root: _BKNode | None = None
        self.field = field
        ordered = sorted(
            (record for record in records if _HEX_16.fullmatch(str(record.get(field) or ""))),
            key=lambda item: (item[field], item["block_height"], item["block_hash"]),
        )
        for record in ordered:
            self._insert(record)

    @staticmethod
    def distance(left: str, right: str) -> int:
        return (int(left, 16) ^ int(right, 16)).bit_count()

    def _insert(self, record: dict[str, Any]) -> None:
        value = record[self.field]
        if self.root is None:
            self.root = _BKNode(value, [record], {})
            return
        node = self.root
        while True:
            distance = self.distance(value, node.value)
            if distance == 0:
                node.records.append(record)
                return
            child = node.children.get(distance)
            if child is None:
                node.children[distance] = _BKNode(value, [record], {})
                return
            node = child

    def query(self, value: str, maximum_distance: int) -> list[tuple[int, dict[str, Any]]]:
        if self.root is None:
            return []
        matches: list[tuple[int, dict[str, Any]]] = []
        pending = [self.root]
        while pending:
            node = pending.pop()
            distance = self.distance(value, node.value)
            if distance <= maximum_distance:
                matches.extend((distance, record) for record in node.records)
            low, high = distance - maximum_distance, distance + maximum_distance
            pending.extend(node.children[key] for key in sorted(node.children, reverse=True) if low <= key <= high)
        return sorted(matches, key=lambda item: (item[0], item[1]["block_height"], item[1]["block_hash"], item[1]["content_hash"]))


def _match_record(record: dict[str, Any], **metric: Any) -> dict[str, Any]:
    return {
        "block_height": record["block_height"],
        "block_hash": record["block_hash"],
        "content_hash": record["content_hash"],
        **metric,
    }


def originality_evidence_payload(evidence: dict[str, Any]) -> dict[str, Any]:
    return {
        key: deepcopy(value)
        for key, value in evidence.items()
        if key not in {"canonical_evidence_digest", "observed_at"}
    }


def originality_evidence_digest(evidence: dict[str, Any]) -> str:
    return canonical_hash(originality_evidence_payload(evidence))


def validate_originality_evidence(evidence: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(evidence, dict):
        raise ValueError("Originality evidence must be an object.")
    originality_rule(evidence.get("originality_rule_version"))
    if evidence.get("evidence_version") != ORIGINALITY_EVIDENCE_VERSION:
        raise ValueError("Unsupported originality evidence version.")
    if evidence.get("final_prevote_decision") not in {PASS, FLAGGED_FOR_REVIEW, HARD_REJECT}:
        raise ValueError("Invalid final pre-vote originality decision.")
    for field in ("content_hash", "originality_reference_block_hash"):
        if not _HEX_64.fullmatch(str(evidence.get(field) or "")):
            raise ValueError(f"{field} must be a lowercase SHA-256 hash.")
    expected = originality_evidence_digest(evidence)
    if evidence.get("canonical_evidence_digest") != expected:
        raise ValueError("Originality evidence digest does not match its canonical payload.")
    return deepcopy(evidence)


class OriginalityPipeline:
    def __init__(self, *, ocr: Callable[[Image.Image], str] | None = None):
        self.ocr = ocr
        self._cached_head: tuple[int, str] | None = None
        self._cached_index: list[dict[str, Any]] = []
        self._query_head: tuple[int, str] | None = None
        self._exact_index: dict[str, list[dict[str, Any]]] = {}
        self._perceptual_index: DeterministicHammingIndex | None = None
        self._near_index: DeterministicHammingIndex | None = None

    def index_for_chain(self, chain: list[Any]) -> list[dict[str, Any]]:
        head = (-1, "") if not chain else (
            int(_block_value(chain[-1], "index")), str(_block_value(chain[-1], "hash")).lower()
        )
        if head != self._cached_head:
            self._cached_index = canonical_minted_media_features(chain, ocr=self.ocr)
            self._cached_head = head
        return deepcopy(self._cached_index)

    def _query_indexes(self, records, reference):
        head = (int(_block_value(reference, "index")), str(_block_value(reference, "hash")).lower())
        if head != self._query_head:
            exact: dict[str, list[dict[str, Any]]] = {}
            for record in records:
                exact.setdefault(record["content_hash"], []).append(record)
            self._exact_index = exact
            self._perceptual_index = DeterministicHammingIndex(records, "perceptual_hash")
            self._near_index = DeterministicHammingIndex(records, "near_duplicate_hash")
            self._query_head = head
        return self._exact_index, self._perceptual_index, self._near_index

    @staticmethod
    def _submission_media(content_object: Any, submission: Any, data_dir: str) -> tuple[bytes | None, str]:
        mime_type = str(getattr(content_object, "mime_type", None) or "application/octet-stream").lower()
        path = resolve_local_path(
            getattr(content_object, "local_path", None) or getattr(submission, "image_path", None),
            data_dir=data_dir,
        )
        if path and Path(path).is_file():
            return Path(path).read_bytes(), mime_type
        text = str(getattr(content_object, "text_content", None) or getattr(submission, "text_content", ""))
        if mime_type == TEXT_MIME_TYPE and text:
            return text.encode("utf-8"), mime_type
        return None, mime_type

    def evaluate(
        self, submission: Any, content_object: Any, chain: list[Any], *, data_dir: str,
        minted_index: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        if not chain:
            raise ValueError("Originality evaluation requires a canonical reference block.")
        rule = originality_rule()
        reference = chain[-1]
        media, mime_type = self._submission_media(content_object, submission, data_dir)
        declared_hash = str(getattr(submission, "content_hash", "") or "").strip().lower()
        content_hash = hashlib.sha256(media).hexdigest() if media is not None else declared_hash
        if not _HEX_64.fullmatch(content_hash):
            raise ValueError("Exact originality checking requires canonical media bytes or a SHA-256 content hash.")

        index = deepcopy(minted_index) if minted_index is not None else self.index_for_chain(chain)
        exact_index, perceptual_index, near_index = self._query_indexes(index, reference)
        exact_matches = [
            _match_record(record) for record in exact_index.get(content_hash, [])
        ]
        exact_matches.sort(key=lambda item: (item["block_height"], item["block_hash"], item["content_hash"]))
        exact_result = {
            "status": CHECK_SUCCESS,
            "algorithm": rule["exact"]["algorithm"],
            "duplicate": bool(exact_matches),
            "candidate_count": len(exact_matches),
        }

        perceptual_result = {
            "status": CHECK_NOT_APPLICABLE,
            "algorithm": rule["perceptual"]["algorithm"],
            "hash": None,
            "flag_hamming_distance_lte": rule["perceptual"]["flag_hamming_distance_lte"],
        }
        near_result = {
            "status": CHECK_NOT_APPLICABLE,
            "algorithm": rule["near_duplicate"]["algorithm"],
            "hash": None,
            "flag_hamming_distance_lte": rule["near_duplicate"]["flag_hamming_distance_lte"],
            "candidate_index": rule["near_duplicate"]["candidate_index"],
        }
        ocr_result = {
            "status": CHECK_NOT_APPLICABLE,
            "algorithm": rule["ocr"]["algorithm"],
            "normalized_text_hash": None,
            "meaningful_text": False,
        }
        perceptual_matches: list[dict[str, Any]] = []
        near_matches: list[dict[str, Any]] = []
        ocr_matches: list[dict[str, Any]] = []

        normalized_text = ""
        if mime_type in SUPPORTED_IMAGE_MIME_TYPES:
            if media is None:
                perceptual_result["status"] = CHECK_UNAVAILABLE
                near_result["status"] = CHECK_UNAVAILABLE
                ocr_result["status"] = CHECK_UNAVAILABLE
            else:
                try:
                    features = _image_features(media, ocr=self.ocr)
                except Exception:
                    perceptual_result["status"] = CHECK_FAILED
                    near_result["status"] = CHECK_FAILED
                    ocr_result["status"] = CHECK_FAILED
                else:
                    perceptual_result.update(status=CHECK_SUCCESS, hash=features["perceptual_hash"])
                    near_result.update(status=CHECK_SUCCESS, hash=features["near_duplicate_hash"])
                    ocr_result["status"] = features["ocr"]["status"]
                    normalized_text = features["ocr"]["normalized_text"]
        elif mime_type == TEXT_MIME_TYPE:
            try:
                normalized_text = normalize_ocr_text((media or b"").decode("utf-8", errors="strict"))
                ocr_result["status"] = CHECK_SUCCESS
            except UnicodeDecodeError:
                ocr_result["status"] = CHECK_FAILED
        else:
            unavailable = CHECK_UNAVAILABLE if media is None else CHECK_FAILED
            perceptual_result["status"] = unavailable
            near_result["status"] = unavailable
            ocr_result["status"] = unavailable

        if perceptual_result["status"] == CHECK_SUCCESS:
            perceptual_matches = [
                _match_record(record, distance=distance)
                for distance, record in perceptual_index.query(
                    perceptual_result["hash"], rule["perceptual"]["flag_hamming_distance_lte"]
                )
            ]
        if near_result["status"] == CHECK_SUCCESS:
            near_matches = [
                _match_record(record, distance=distance)
                for distance, record in near_index.query(
                    near_result["hash"], rule["near_duplicate"]["flag_hamming_distance_lte"]
                )
            ]

        meaningful = _meaningful_text(normalized_text, rule)
        ocr_result["meaningful_text"] = meaningful
        if normalized_text:
            ocr_result["normalized_text_hash"] = hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()
        if ocr_result["status"] == CHECK_SUCCESS and meaningful:
            numerator_required = rule["ocr"]["flag_numerator"]
            denominator_required = rule["ocr"]["flag_denominator"]
            for record in index:
                candidate_text = record.get("normalized_text") or ""
                if not _meaningful_text(candidate_text, rule):
                    continue
                numerator, denominator = _token_similarity(normalized_text, candidate_text)
                if numerator * denominator_required >= numerator_required * denominator:
                    ocr_matches.append(_match_record(
                        record,
                        similarity_numerator=numerator,
                        similarity_denominator=denominator,
                        normalized_text_hash=record.get("normalized_text_hash"),
                    ))
            ocr_matches.sort(key=lambda item: (
                -(item["similarity_numerator"] * 1_000_000 // item["similarity_denominator"]),
                item["block_height"], item["block_hash"], item["content_hash"],
            ))

        reason_codes: list[str] = []
        if exact_matches:
            decision = HARD_REJECT
            reason_codes.append(EXACT_MINTED_CONTENT_DUPLICATE)
        else:
            if perceptual_matches:
                reason_codes.append(PERCEPTUAL_SIMILARITY)
            if ocr_matches:
                reason_codes.append(OCR_TEXT_SIMILARITY)
            if near_matches:
                reason_codes.append(NEAR_DUPLICATE_SIMILARITY)
            fuzzy_statuses = {perceptual_result["status"], ocr_result["status"], near_result["status"]}
            if fuzzy_statuses & {CHECK_UNAVAILABLE, CHECK_FAILED}:
                reason_codes.append(FUZZY_CHECK_INCOMPLETE)
            decision = FLAGGED_FOR_REVIEW if reason_codes else PASS

        evidence = {
            "evidence_version": ORIGINALITY_EVIDENCE_VERSION,
            "originality_rule_version": ORIGINALITY_RULE_VERSION,
            "originality_rule_digest": originality_rule_digest(),
            "submission_id": str(submission.submission_id),
            "content_hash": content_hash,
            "originality_reference_height": int(_block_value(reference, "index")),
            "originality_reference_block_hash": str(_block_value(reference, "hash")).lower(),
            "exact_hash_result": exact_result,
            "exact_candidate_matches": exact_matches,
            "perceptual_hash_result": perceptual_result,
            "perceptual_candidate_matches": perceptual_matches,
            "ocr_result": ocr_result,
            "ocr_candidate_matches": ocr_matches,
            "near_duplicate_result": near_result,
            "near_duplicate_candidate_matches": near_matches,
            "reason_codes": sorted(reason_codes),
            "final_prevote_decision": decision,
        }
        evidence["canonical_evidence_digest"] = originality_evidence_digest(evidence)
        return validate_originality_evidence(evidence)
