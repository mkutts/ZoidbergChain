import json

import zstandard

from scripts import milestone_7_task_7_4_benchmark as benchmark


def test_descriptor_estimate_uses_exact_proposed_media_object_shape():
    sample = {"mime_type": "text/plain", "bytes": b"hello"}
    assert benchmark._descriptor_size(b"hello", sample, "identity") == 227


def test_benchmark_configuration_is_bounded_and_has_identity_fallback():
    config = json.loads(benchmark.CONFIG_PATH.read_text(encoding="utf-8"))
    assert 1 <= config["warmup_iterations"] <= 5
    assert 3 <= config["timed_repetitions"] <= 15
    assert config["candidates"][0]["codec"] == "identity"
    assert {item["codec"] for item in config["candidates"]} >= {"zstd", "brotli", "zlib"}


def test_zstd_benchmark_profile_caps_the_frame_window_at_256_kib():
    config = json.loads(benchmark.CONFIG_PATH.read_text(encoding="utf-8"))
    candidate = next(item for item in config["candidates"] if item["id"] == "zstd-3")
    encode, _, _ = benchmark._operations(candidate)
    assert zstandard.get_frame_parameters(encode(b"x" * 262_144)).window_size <= 262_144
