"""Build and verify the deterministic Milestone 7.3 media corpus.

This utility deliberately produces media inputs only.  It performs no
compression, timing, or codec comparison.  Generated sample bytes live in an
operator-selected directory; the checked-in manifest is the reproducibility
contract, not a binary fixture collection.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import itertools
import json
import math
import random
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PIL import Image, __version__ as PILLOW_VERSION, features

from media_technical_validation import TechnicalMediaValidationError, validate_media_bytes


CORPUS_VERSION = "1.1.0"
MANIFEST_PATH = PROJECT_ROOT / "tests" / "fixtures" / "milestone_7_corpus_v1_manifest.json"
PROVISIONAL_MEDIA_LIMIT = 262_144
PROVISIONAL_BLOCK_LIMIT = 524_288


def _gradient(size: tuple[int, int], seed: int) -> Image.Image:
    width, height = size
    image = Image.new("RGB", size)
    pixels = image.load()
    for y in range(height):
        for x in range(width):
            wave = (x * 17 + y * 11 + seed * 29) % 256
            pixels[x, y] = ((x * 255 // max(1, width - 1) + seed) % 256,
                            (y * 255 // max(1, height - 1) + seed * 3) % 256,
                            wave)
    return image


def _noise(size: tuple[int, int], seed: int) -> Image.Image:
    generator = random.Random(seed)
    return Image.frombytes("RGB", size, generator.randbytes(size[0] * size[1] * 3))


def _poster(size: tuple[int, int], seed: int, *, illustrated: bool = False) -> Image.Image:
    image = Image.new("RGB", size, (246, 239, 214))
    pixels = image.load()
    width, height = size
    # Deterministic raster "caption" bands avoid a system-font dependency.
    for row in range(7):
        y0 = 22 + row * max(22, height // 15)
        for column in range(18):
            if (column * 7 + row * 11 + seed) % 5:
                x0 = 20 + column * max(12, width // 25)
                for y in range(y0, min(y0 + 12, height)):
                    for x in range(x0, min(x0 + max(7, width // 38), width)):
                        pixels[x, y] = (32, 38, 46)
    center_x, center_y = width // 2, height * 3 // 4
    radius = min(width, height) // 7
    for y in range(max(0, center_y - radius), min(height, center_y + radius)):
        for x in range(max(0, center_x - radius), min(width, center_x + radius)):
            dx, dy = x - center_x, y - center_y
            if dx * dx + dy * dy <= radius * radius:
                pixels[x, y] = (34 + (seed % 60), 142, 184 if illustrated else 90)
    return image


def _flat(size: tuple[int, int], seed: int) -> Image.Image:
    image = Image.new("RGB", size, (30 + seed % 100, 90, 160))
    pixels = image.load()
    for y in range(size[1] // 3, size[1] * 2 // 3):
        for x in range(size[0] // 3, size[0] * 2 // 3):
            pixels[x, y] = (241, 204, 74)
    return image


def _image_bytes(kind: str, size: tuple[int, int], seed: int, *, animated: bool = False) -> Image.Image:
    if kind == "noise":
        return _noise(size, seed)
    if kind == "poster":
        return _poster(size, seed)
    if kind == "illustration":
        return _poster(size, seed, illustrated=True)
    if kind == "flat":
        return _flat(size, seed)
    return _gradient(size, seed)


def _encode_image(image: Image.Image, mime_type: str, *, animated: bool = False) -> bytes:
    result = io.BytesIO()
    if mime_type == "image/jpeg":
        image.save(result, format="JPEG", quality=91, optimize=False, progressive=False, subsampling=0)
    elif mime_type == "image/png":
        image.save(result, format="PNG", compress_level=6, optimize=False)
    elif mime_type == "image/webp":
        image.save(result, format="WEBP", lossless=False, quality=88, method=4)
    elif mime_type == "image/gif":
        if animated:
            alternate = image.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
            image.convert("P", palette=Image.Palette.ADAPTIVE).save(
                result, format="GIF", save_all=True,
                append_images=[alternate.convert("P", palette=Image.Palette.ADAPTIVE)],
                duration=[90, 110], loop=0, optimize=False,
            )
        else:
            image.convert("P", palette=Image.Palette.ADAPTIVE).save(result, format="GIF", optimize=False)
    else:
        raise ValueError(f"Unsupported corpus MIME: {mime_type}")
    return result.getvalue()


def _text_samples() -> list[dict[str, Any]]:
    release_notes = """ZoidbergChain node release note

The pending media submission now retains its declared MIME type, immutable byte
hash, technical-evidence digest, creator address, and review queue position.
Operators should preserve the block snapshot with its corresponding admission
certificate and finality evidence.  A peer importing this record must verify
the chain identity before presenting media to a user.
""".encode()
    audit_records = [
        {"height": height, "block_hash": f"{height:064x}", "submission_id": f"sub-{height:04d}",
         "reviewers": 3 + height % 4, "decision": "accepted" if height % 5 else "queued",
         "media_type": ["image/jpeg", "image/png", "image/webp", "text/plain"][height % 4]}
        for height in range(1, 49)
    ]
    peer_snapshot = {
        "network_id": "zoidberg-public-testnet-v1", "snapshot_height": 480,
        "node": {"peer_id": "node-east-03", "software": "0.7.3", "synced": True},
        "recent_admissions": audit_records,
        "retention": {"canonical_media": "embedded", "content_cache": "optional"},
    }
    service_module = b'''from dataclasses import dataclass\n\n\n@dataclass(frozen=True)\nclass AdmissionSummary:\n    submission_id: str\n    media_sha256: str\n    reviewer_count: int\n\n\ndef build_summary(record: dict[str, object]) -> AdmissionSummary:\n    certificate = record["admission_certificate"]\n    return AdmissionSummary(\n        submission_id=str(record["submission_id"]),\n        media_sha256=str(certificate["media_sha256"]),\n        reviewer_count=len(certificate["votes"]),\n    )\n'''
    cli_module = b'''import json\nfrom pathlib import Path\n\n\ndef read_snapshot(path: Path) -> dict[str, object]:\n    payload = json.loads(path.read_text(encoding="utf-8"))\n    if payload.get("network_id") != "zoidberg-public-testnet-v1":\n        raise ValueError("unexpected network")\n    return payload\n\n\ndef print_pending_submissions(snapshot: dict[str, object]) -> None:\n    for submission in snapshot.get("submissions", []):\n        if submission.get("status") == "pending_review":\n            print(f"{submission['submission_id']} {submission['media_sha256']}")\n'''
    return [
        {"id": "text-caption-small", "mime_type": "text/plain", "category": "plain_text", "complexity": "highly_compressible", "seed": None,
         "description": "Short natural-language meme caption.", "bytes": b"All your bytes are belong on-chain.\n"},
        {"id": "text-story-medium", "mime_type": "text/plain", "category": "plain_text", "complexity": "moderately_compressible", "seed": None,
         "description": "Repository-authored node-operation release note.", "bytes": release_notes},
        {"id": "text-audit-log-large", "mime_type": "text/plain", "category": "plain_text", "complexity": "moderately_compressible", "seed": None,
         "description": "Plausible human-readable chain audit log.", "bytes": "\n".join(f"height={item['height']} submission={item['submission_id']} decision={item['decision']} reviewers={item['reviewers']}" for item in audit_records).encode()},
        {"id": "text-json-pretty", "mime_type": "text/plain", "category": "structured_metadata_json", "complexity": "highly_compressible", "seed": None,
         "description": "Pretty-printed metadata represented as accepted plain text.", "bytes": json.dumps({"title": "Deterministic corpus", "tags": ["meme", "image", "storage"], "version": 1}, indent=2, sort_keys=True).encode() + b"\n"},
        {"id": "text-json-minified", "mime_type": "text/plain", "category": "structured_metadata_json", "complexity": "moderately_compressible", "seed": None,
         "description": "Minified blockchain event metadata represented as accepted plain text.", "bytes": json.dumps({"events": audit_records[:16], "kind": "admission_window"}, separators=(",", ":"), sort_keys=True).encode()},
        {"id": "text-json-peer-snapshot-large", "mime_type": "text/plain", "category": "structured_metadata_json", "complexity": "moderately_compressible", "seed": None,
         "description": "Nested peer snapshot and recent admission metadata as accepted plain text.", "bytes": json.dumps(peer_snapshot, indent=2, sort_keys=True).encode() + b"\n"},
        {"id": "text-source-code", "mime_type": "text/plain", "category": "source_code", "complexity": "moderately_compressible", "seed": None,
         "description": "Harmless source-code excerpt represented as accepted plain text.", "bytes": b"def stable_label(index: int) -> str:\n    return f'corpus-{index:03d}'\n\nfor index in range(12):\n    print(stable_label(index))\n"},
        {"id": "text-source-admission-model", "mime_type": "text/plain", "category": "source_code", "complexity": "moderately_compressible", "seed": None,
         "description": "Plausible typed admission-summary source module.", "bytes": service_module},
        {"id": "text-source-snapshot-cli", "mime_type": "text/plain", "category": "source_code", "complexity": "moderately_compressible", "seed": None,
         "description": "Plausible snapshot-inspection command-line source module.", "bytes": cli_module},
    ]


def build_samples() -> list[dict[str, Any]]:
    samples = _text_samples()
    definitions = [
        ("jpeg-flat-small", "image/jpeg", "flat", (320, 180), 101, "simple_image", "highly_compressible", False, True),
        ("jpeg-text-poster", "image/jpeg", "poster", (960, 540), 102, "text_heavy_meme", "moderately_compressible", False, True),
        ("jpeg-photo-like", "image/jpeg", "gradient", (1280, 720), 103, "photographic_like_meme", "moderately_compressible", False, True),
        ("jpeg-noise-capacity", "image/jpeg", "noise", (1024, 768), 104, "high_entropy_image", "difficult_to_compress", False, False),
        ("jpeg-photo-small", "image/jpeg", "gradient", (480, 270), 105, "photographic_like_meme", "moderately_compressible", False, True),
        ("jpeg-mixed-medium", "image/jpeg", "illustration", (800, 600), 106, "mixed_complexity_meme", "moderately_compressible", False, True),
        ("jpeg-text-large", "image/jpeg", "poster", (1200, 675), 107, "text_heavy_meme", "moderately_compressible", False, True),
        ("png-flat-small", "image/png", "flat", (320, 180), 201, "simple_image", "highly_compressible", False, True),
        ("png-illustrated-medium", "image/png", "illustration", (960, 540), 202, "illustrated_meme", "moderately_compressible", False, True),
        ("png-text-poster", "image/png", "poster", (1280, 720), 203, "text_heavy_meme", "moderately_compressible", False, True),
        ("png-noise-capacity", "image/png", "noise", (768, 768), 204, "high_entropy_image", "difficult_to_compress", False, False),
        ("png-photo-small", "image/png", "gradient", (480, 270), 205, "photographic_like_meme", "moderately_compressible", False, True),
        ("png-mixed-medium", "image/png", "illustration", (800, 600), 206, "mixed_complexity_meme", "moderately_compressible", False, True),
        ("png-text-large", "image/png", "poster", (1200, 675), 207, "text_heavy_meme", "moderately_compressible", False, True),
        ("webp-flat-small", "image/webp", "flat", (320, 180), 301, "simple_image", "already_compressed", False, True),
        ("webp-illustrated-medium", "image/webp", "illustration", (960, 540), 302, "illustrated_meme", "already_compressed", False, True),
        ("webp-photo-like", "image/webp", "gradient", (1280, 720), 303, "photographic_like_meme", "already_compressed", False, True),
        ("webp-noise-capacity", "image/webp", "noise", (1024, 768), 304, "high_entropy_image", "difficult_to_compress", False, False),
        ("webp-photo-small", "image/webp", "gradient", (480, 270), 305, "photographic_like_meme", "already_compressed", False, True),
        ("webp-mixed-medium", "image/webp", "illustration", (800, 600), 306, "mixed_complexity_meme", "already_compressed", False, True),
        ("webp-text-large", "image/webp", "poster", (1200, 675), 307, "text_heavy_meme", "already_compressed", False, True),
        ("gif-flat-small", "image/gif", "flat", (320, 180), 401, "simple_image", "already_compressed", False, True),
        ("gif-animated-illustrated", "image/gif", "illustration", (640, 360), 402, "animated_illustrated_meme", "already_compressed", True, True),
        ("gif-noise-capacity", "image/gif", "noise", (768, 768), 403, "high_entropy_image", "difficult_to_compress", False, False),
        ("gif-photo-small", "image/gif", "gradient", (480, 270), 404, "photographic_like_meme", "already_compressed", False, True),
        ("gif-text-medium", "image/gif", "poster", (800, 600), 405, "text_heavy_meme", "already_compressed", False, True),
        ("gif-mixed-large", "image/gif", "illustration", (1200, 675), 406, "mixed_complexity_meme", "already_compressed", False, True),
    ]
    for sample_id, mime_type, kind, dimensions, seed, category, complexity, animated, scoring in definitions:
        payload = _encode_image(_image_bytes(kind, dimensions, seed), mime_type, animated=animated)
        samples.append({"id": sample_id, "mime_type": mime_type, "category": category, "complexity": complexity,
                        "seed": seed, "dimensions": list(dimensions), "description": f"Deterministic {kind} raster sample.",
                        "bytes": payload, "benchmark_scoring": scoring, "capacity_analysis": True, "animated": animated})
    for sample in samples:
        sample.setdefault("benchmark_scoring", True)
        sample.setdefault("capacity_analysis", False)
        sample.setdefault("dimensions", None)
        sample.setdefault("animated", False)
        # Capacity samples remain reproducible corpus members but cannot enter
        # the in-limit reference score until a future limit is explicitly set.
        if len(sample["bytes"]) > PROVISIONAL_MEDIA_LIMIT:
            sample["benchmark_scoring"] = False
            sample["capacity_analysis"] = True
    return samples


def _environment() -> dict[str, str | None]:
    return {"python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}", "pillow": PILLOW_VERSION,
            "jpeg_codec": features.version_codec("jpg"), "webp_codec": features.version_module("webp")}


def _record(sample: dict[str, Any]) -> dict[str, Any]:
    payload = sample["bytes"]
    container_status = "not_applicable"
    if sample["mime_type"].startswith("image/"):
        with Image.open(io.BytesIO(payload)) as decoded:
            decoded.verify()
        container_status = "valid_pillow_decode"
    try:
        validated = validate_media_bytes(payload, declared_mime_type=sample["mime_type"], original_filename=f"{sample['id']}.fixture")
        status, reasons, accepted_length = "accepted", [], len(validated.raw_media_bytes)
    except TechnicalMediaValidationError as exc:
        reasons, accepted_length = exc.result["reason_codes"], None
        status = "rejected_environment_isolation" if container_status == "valid_pillow_decode" and reasons == ["MALFORMED_MEDIA"] else "rejected_policy"
    return {key: sample[key] for key in ("id", "mime_type", "category", "complexity", "seed", "dimensions", "description", "benchmark_scoring", "capacity_analysis", "animated")} | {
        "original_byte_size": len(payload), "sha256": hashlib.sha256(payload).hexdigest(), "generation_method": "repository-authored deterministic Pillow raster or UTF-8 bytes; no network source", "redistribution": "repository-authored deterministic sample", "container_decode_status": container_status, "current_validator_status": status, "current_validator_reason_codes": reasons, "accepted_byte_size": accepted_length,
    }


def make_manifest() -> dict[str, Any]:
    records = [_record(sample) for sample in build_samples()]
    return {"corpus_id": "zoidbergchain-media-benchmark-v1", "corpus_version": CORPUS_VERSION,
            "purpose": "Representative original-media corpus; no compression results are recorded.", "environment": _environment(),
            "provisional_limits": {"original_media_bytes": PROVISIONAL_MEDIA_LIMIT, "encoded_media_bytes": PROVISIONAL_MEDIA_LIMIT, "canonical_block_bytes": PROVISIONAL_BLOCK_LIMIT},
            "samples": records}


def percentile(values: list[int], percent: int) -> int:
    if not values or not 0 < percent <= 100:
        raise ValueError("percentile requires non-empty values and 0 < percent <= 100")
    return sorted(values)[math.ceil(len(values) * percent / 100) - 1]


def image_statistics(manifest: dict[str, Any]) -> dict[str, Any]:
    images = [sample for sample in manifest["samples"] if sample["mime_type"].startswith("image/")]
    sizes = [sample["original_byte_size"] for sample in images]
    by_mime: dict[str, dict[str, int]] = {}
    for mime_type, members in itertools.groupby(sorted(images, key=lambda item: item["mime_type"]), key=lambda item: item["mime_type"]):
        listed = list(members)
        by_mime[mime_type] = {"count": len(listed), "bytes": sum(item["original_byte_size"] for item in listed), "maximum_bytes": max(item["original_byte_size"] for item in listed)}
    return {"image_count": len(images), "p50_bytes": percentile(sizes, 50), "p95_bytes": percentile(sizes, 95), "p99_bytes": percentile(sizes, 99), "maximum_bytes": max(sizes), "by_mime": by_mime,
            "excluded_by_original_media_limit_count": sum(size > PROVISIONAL_MEDIA_LIMIT for size in sizes),
            "excluded_by_encoded_media_limit_count": sum(size > PROVISIONAL_MEDIA_LIMIT for size in sizes),
            "requires_block_overhead_measurement": True}


def write_corpus(destination: Path, manifest: dict[str, Any]) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for sample in build_samples():
        suffix = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif", "text/plain": ".txt"}[sample["mime_type"]]
        (destination / f"{sample['id']}{suffix}").write_bytes(sample["bytes"])
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def verify_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    actual = make_manifest()
    # These three values are historical admission observations, not source
    # identity. Task 7.12 repaired image-worker admission after this manifest
    # was frozen. Preserve every key (including the observation-field schema),
    # sample order, source hash/size and pinned encoder environment exactly.
    # Never emit a new historical manifest just because admission now succeeds.
    observation_fields = {"current_validator_status", "current_validator_reason_codes", "accepted_byte_size"}

    def identity(value: dict[str, Any]) -> dict[str, Any]:
        return value | {"samples": [
            {key: None if key in observation_fields else item for key, item in record.items()}
            for record in value["samples"]
        ]}

    if identity(manifest) != identity(actual):
        raise ValueError("Manifest does not match regenerated deterministic corpus or pinned environment.")
    for record in manifest["samples"]:
        if record["current_validator_status"] == "rejected_policy" and not record["capacity_analysis"]:
            raise ValueError(f"Unexpected rejected non-capacity sample: {record['id']}")
    return image_statistics(manifest)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--emit-manifest", action="store_true", help="write the checked-in manifest after intentional corpus changes")
    parser.add_argument("--output", type=Path, help="write generated sample bytes and a copy of the manifest here")
    parser.add_argument("--verify", action="store_true", help="verify the checked-in manifest against regenerated samples")
    args = parser.parse_args()
    manifest = make_manifest()
    if args.emit_manifest:
        MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    elif MANIFEST_PATH.exists():
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if args.verify:
        statistics = verify_manifest(manifest)
        print(json.dumps({"corpus_id": manifest["corpus_id"], "verified": True,
                          "verification_scope": "source identity, order, schema and pinned encoder environment; historical admission observations are not replayed",
                          "image_statistics": statistics}, indent=2, sort_keys=True))
    if args.output:
        write_corpus(args.output, manifest)


if __name__ == "__main__":
    main()
