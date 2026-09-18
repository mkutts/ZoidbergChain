"""Small reproducible Task 6.3 media-validation resource-abuse benchmark."""

from __future__ import annotations

import io
import json
import statistics
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PIL import Image

from media_technical_validation import TechnicalMediaValidationError, validate_media_bytes


def _png(size):
    output = io.BytesIO()
    Image.new("1", size, 0).save(output, format="PNG", optimize=True)
    return output.getvalue()


def _measure(label, payload, *, mime_type, attempts=3):
    durations = []
    outcome = None
    reasons = []
    for _ in range(attempts):
        started = time.perf_counter()
        try:
            validate_media_bytes(payload, declared_mime_type=mime_type)
            outcome = "ACCEPT"
        except TechnicalMediaValidationError as exc:
            outcome = "REJECT"
            reasons = exc.result["reason_codes"]
        durations.append(time.perf_counter() - started)
    return {
        "case": label,
        "input_bytes": len(payload),
        "outcome": outcome,
        "reason_codes": reasons,
        "attempts": attempts,
        "median_seconds": round(statistics.median(durations), 6),
        "maximum_seconds": round(max(durations), 6),
    }


def main():
    cases = [
        _measure("near_limit_valid_pixels", _png((4096, 4096)), mime_type="image/png"),
        _measure("oversized_media_early_rejection", b"x" * 262_145, mime_type="text/plain"),
        _measure("dimension_bomb_early_rejection", _png((4097, 4096)), mime_type="image/png"),
        _measure("malformed_container_rejection", b"\x89PNG\r\n\x1a\ntruncated", mime_type="image/png"),
    ]
    print(json.dumps({"benchmark": "milestone_6_task_6_3", "cases": cases}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
