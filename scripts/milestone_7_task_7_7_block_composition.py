"""Measure existing block composition and deterministic v3 projections for Task 7.7.

This is intentionally measurement-only.  It uses the current Block serializer for
v1/v2 and a local, spec-shaped serializer for unimplemented v3 records; it never
changes consensus, storage schema, or chain state.
"""
from __future__ import annotations

import argparse
import base64
import gc
import hashlib
import json
import os
import platform
import sqlite3
import sys
import tempfile
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import zstandard

from block import ADMISSION_BLOCK_VERSION, Block, PROTOCOL_V1_BLOCK_VERSION
from protocol_v1 import (
    OBJECT_TYPE_BLOCK,
    PUBLIC_TESTNET_V1_NETWORK_ID,
    build_domain_envelope,
    canonical_json_bytes,
)
from storage import SQLiteStorageBackend
from transaction import Transaction
from scripts import milestone_7_task_7_3_corpus as corpus

CONFIG_PATH = PROJECT_ROOT / "tests" / "fixtures" / "milestone_7_block_composition_v1_config.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "benchmarks" / "milestone_7_task_7_7_results.json"


def _nearest_rank(values: list[int | float], percentile: int) -> int | float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[(len(ordered) * percentile + 99) // 100 - 1]


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _quoted_string_bytes(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def _signature_string_bytes(value: Any) -> int:
    if isinstance(value, dict):
        return sum(
            _signature_string_bytes(item)
            for key, item in value.items()
            if key in {"signature", "vote_signature"}
            or isinstance(item, (dict, list))
        )
    if isinstance(value, list):
        return sum(_signature_string_bytes(item) for item in value)
    return _quoted_string_bytes(value) - 2 if isinstance(value, str) else 0


def _fragment_bytes(mapping: dict[str, Any]) -> int:
    if not mapping:
        return 0
    # The already-canonical v1 envelope has a bytes-tag object that would be
    # rejected when parsed back into an ordinary dict by protocol_v1's reserved
    # bytes-object guard.  JSON rendering is otherwise the exact same compact,
    # sorted UTF-8 representation for these parsed scalar/object values.
    return len(json.dumps(mapping, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")) - 2


def component_accounting(envelope_bytes: bytes, media_key: str) -> dict[str, int | float]:
    """Partition one canonical envelope without double-counting nested fields."""
    envelope = json.loads(envelope_bytes)
    payload = envelope["payload"]
    media = {media_key: payload[media_key]}
    certificate = ({"admission_certificate": payload["admission_certificate"]}
                   if "admission_certificate" in payload else {})
    transactions = {
        key: payload[key]
        for key in ("transactions", "native_transactions", "transactions_hash")
        if key in payload
    }
    header_keys = {"block_version", "index", "previous_hash", "timestamp", "minted_at", "miner"}
    header = {key: value for key, value in payload.items() if key in header_keys}
    assigned = set(media) | set(certificate) | set(transactions) | set(header)
    remaining = {key: value for key, value in payload.items() if key not in assigned}
    envelope_fields = {key: value for key, value in envelope.items() if key != "payload"}
    parts = {
        "serialized_media_representation_bytes": _fragment_bytes(media),
        "certificate_bytes": _fragment_bytes(certificate),
        "transaction_record_bytes": _fragment_bytes(transactions),
        "header_bytes": _fragment_bytes(header),
        "remaining_structural_metadata_bytes": _fragment_bytes(remaining),
        "envelope_bytes": _fragment_bytes(envelope_fields),
    }
    parts["delimiter_bytes"] = len(envelope_bytes) - sum(parts.values())
    if parts["delimiter_bytes"] < 0 or sum(parts.values()) != len(envelope_bytes):
        raise AssertionError("component accounting did not reconcile")
    parts["complete_serialized_block_bytes"] = len(envelope_bytes)
    parts["nonmedia_metadata_bytes"] = len(envelope_bytes) - parts["serialized_media_representation_bytes"]
    parts["nonmedia_metadata_percent"] = (
        parts["nonmedia_metadata_bytes"] / len(envelope_bytes) * 100 if envelope_bytes else 0.0
    )
    parts["signature_bytes_subset"] = _signature_string_bytes(certificate) + _signature_string_bytes(transactions)
    return parts


def _certificate(sample_id: str, content_hash: str, index: int) -> dict[str, Any]:
    """A deterministic, schema-shaped admission bundle for size measurement.

    Signatures and IDs have production-shaped lengths, but this is deliberately
    not an issued or finalized certificate.  It lets the current v2 serializer
    measure the certificate-bearing shape without claiming live finality data.
    """
    signature = "0x" + ("ab" * 65)
    wallet = "0x" + ("12" * 20)
    votes = []
    for ordinal in range(10):
        votes.append({
            "voter": "0x" + f"{ordinal + 1:040x}", "voter_wallet_address": "0x" + f"{ordinal + 1:040x}",
            "submission_id": f"composition-{sample_id}-{index}", "content_hash": content_hash,
            "vote_type": "original" if ordinal % 2 == 0 else "admissible",
            "dimension": "originality" if ordinal % 2 == 0 else "admissibility",
            "vote_version": 2, "protocol_version": 1, "network_id": PUBLIC_TESTNET_V1_NETWORK_ID,
            "signature_scheme": "personal_sign", "vote_signature": signature,
            "vote_message": f"zoidbergchain/vote/v1/{sample_id}/{ordinal}",
            "vote_nonce": f"composition-vote-{index}-{ordinal}",
            "signed_message_hash": _sha(f"vote:{sample_id}:{index}:{ordinal}"),
            "vote_identity": _sha(f"identity:{sample_id}:{index}:{ordinal}"),
            "vote_issued_at": "2026-10-18T00:00:00Z", "vote_expires_at": "2026-10-18T01:00:00Z",
            "reviewer_policy_version": 1, "reputation_rule_version": 1,
            "reviewer_status": "PROBATIONARY_REVIEWER", "reviewer_eligible": True,
            "reviewer_status_effective_height": 0,
            "reviewer_status_reference_block_hash": "0" * 64,
        })
    certificate = {
        "certificate_version": 1, "network_id": PUBLIC_TESTNET_V1_NETWORK_ID,
        "submission_id": f"composition-{sample_id}-{index}", "content_hash": content_hash,
        "creator_wallet": wallet, "policy_id": "media-admission-v1", "policy_version": 1,
        "policy_digest": _sha("policy"), "technical_evidence_version": 1,
        "technical_evidence": {"evidence_digest": _sha(f"evidence:{sample_id}"), "mime_type": "text/plain", "byte_length": 0},
        "attestation_version": 1,
        "attestation": {"signer_wallet": wallet, "signature": signature, "nonce": f"attestation-{index}"},
        "review_policy_version": 1, "review_policy_digest": _sha("review-policy"), "votes": votes,
        "originality": {"vote_set_digest": _sha(f"originality:{sample_id}"), "outcome": "original"},
        "admissibility": {"vote_set_digest": _sha(f"admissibility:{sample_id}"), "outcome": "admissible"},
    }
    certificate["certificate_digest"] = _sha(canonical_json_bytes(certificate).decode("utf-8"))
    return certificate


def _native_transactions(sample_id: str, variant: int) -> list[dict[str, Any]]:
    records = []
    sender_seed = _sha(f"sender:{sample_id}")[:40]
    for ordinal in range(variant):
        records.append({
            "tx_id": _sha(f"native:{sample_id}:{ordinal}"), "transaction_type": "native_transfer",
            "network": "zoidberg-testnet", "from_address": "0x" + sender_seed,
            "to_address": "0x" + f"{ordinal + 19:040x}", "amount": "1.5", "fee": "0.01",
            "nonce": ordinal + 1, "memo": f"composition transfer {sample_id}",
            "timestamp": "2026-10-18T00:00:00Z", "signature": "0x" + ("cd" * 65),
            "signature_scheme": "personal_sign", "signed_message": f"native transfer {sample_id} {ordinal}",
            "signed_message_hash": _sha(f"native-message:{sample_id}:{ordinal}"),
        })
    return records


def _current_block(sample: dict[str, Any], index: int, version: int) -> Block:
    raw = sample["bytes"]
    content_hash = hashlib.sha256(raw).hexdigest()
    certificate = _certificate(sample["id"], content_hash, index) if version == ADMISSION_BLOCK_VERSION else None
    native = _native_transactions(sample["id"], index % 3)
    transaction = Transaction("REWARD_POOL", "0x" + ("34" * 20), 5, tip=0, payload_size_kb=0)
    return Block(
        index=index + 1, previous_hash=_sha(f"previous:{index}"), timestamp=1724760000 + index,
        transactions=[transaction], miner="0x" + ("56" * 20),
        meme={"encoded_image": base64.b64encode(raw).decode("ascii"), "text": f"Caption for {sample['id']}"},
        block_version=version, network_id=PUBLIC_TESTNET_V1_NETWORK_ID, media_hash=content_hash,
        media_bytes=raw, submission_id=f"composition-{sample['id']}-{index}",
        certificate_id=certificate["certificate_digest"] if certificate else _sha(f"certificate:{sample['id']}"),
        content_hash=content_hash, content_id=content_hash[:32], content_type="text" if sample["mime_type"] == "text/plain" else "image",
        mime_type=sample["mime_type"], creator_wallet="0x" + ("34" * 20), vote_hash=_sha(f"vote:{sample['id']}"),
        approval_percentage="0.8", decisive_vote_total=5, minimum_votes_required=5, approved_at=0,
        originality_score="0.9", reward_type="meme_mining_reward", reward_recipient="0x" + ("34" * 20),
        reward_amount="5", reward_source="reward_pool", minted_at=1724760000 + index,
        voter_rewards=[], native_transactions=native,
        transactions_hash=_sha(canonical_json_bytes(native).decode("utf-8")), admission_certificate=certificate,
    )


def _v3_envelope(sample: dict[str, Any], index: int, payload: bytes, codec_id: str, certificate: dict[str, Any], native: list[dict[str, Any]]) -> bytes:
    original = sample["bytes"]
    content_hash = hashlib.sha256(original).hexdigest()
    media = {
        "codec_id": codec_id, "codec_version": 1, "encoding_version": 1, "mime_type": sample["mime_type"],
        "original_sha256": content_hash, "original_size": len(original),
        "payload": base64.b64encode(payload).decode("ascii"), "stored_size": len(payload),
    }
    body = {
        "block_version": 3, "index": index + 1, "previous_hash": _sha(f"previous:{index}"),
        "timestamp": str(1724760000 + index), "minted_at": str(1724760000 + index), "transactions": [
            {"sender": "REWARD_POOL", "recipient": "0x" + ("34" * 20), "amount": "5", "tip": 0, "payload_size_kb": 0}
        ], "native_transactions": native,
        "transactions_hash": _sha(canonical_json_bytes(native).decode("utf-8")), "miner": "0x" + ("56" * 20),
        "submission_id": f"composition-{sample['id']}-{index}", "certificate_id": certificate["certificate_digest"],
        "vote_hash": _sha(f"vote:{sample['id']}"), "creator_wallet": "0x" + ("34" * 20),
        "content_type": "text" if sample["mime_type"] == "text/plain" else "image",
        "approval_percentage": "0.8", "originality_score": "0.9", "decisive_vote_total": 5,
        "minimum_votes_required": 5, "approved_at": 0, "reward_type": "meme_mining_reward",
        "reward_source": "reward_pool", "reward_recipient": "0x" + ("34" * 20), "reward_amount": "5",
        "voter_rewards": [], "admission_certificate": certificate, "media": media,
    }
    if sample["mime_type"] != "text/plain":
        body["meme_text"] = f"Caption for {sample['id']}"
    return canonical_json_bytes(build_domain_envelope(
        body, object_type=OBJECT_TYPE_BLOCK, network_id=PUBLIC_TESTNET_V1_NETWORK_ID, protocol_version=2
    ))


def _row(sample: dict[str, Any], representation: str, encoding: str, envelope: bytes, media_key: str, encoded_bytes: int, storage_record: dict[str, Any], *, selected_codec: str | None = None) -> dict[str, Any]:
    components = component_accounting(envelope, media_key)
    media = json.loads(envelope)["payload"][media_key]
    descriptor_overhead = components["serialized_media_representation_bytes"] - (
        len(media["payload"]) if media_key == "media" else len(media["$value"])
    )
    return {
        "sample_id": sample["id"], "mime_type": sample["mime_type"], "category": sample["category"],
        "benchmark_scoring": sample["benchmark_scoring"], "capacity_analysis": sample["capacity_analysis"],
        "representation": representation, "encoding": encoding, "selected_codec": selected_codec or encoding, "measurement_kind": "direct" if representation.startswith("current_") else "deterministic_projection",
        "original_media_bytes": len(sample["bytes"]), "encoded_media_bytes": encoded_bytes,
        "media_descriptor_overhead_bytes": descriptor_overhead, **components,
        "storage_record": storage_record,
    }


def _v3_storage_record(envelope: bytes) -> dict[str, Any]:
    payload = json.loads(envelope)["payload"]
    record = dict(payload)
    record["hash"] = hashlib.sha256(envelope).hexdigest()
    return record


def build_rows(config: dict[str, Any]) -> list[dict[str, Any]]:
    manifest = json.loads((PROJECT_ROOT / config["corpus_manifest"]).read_text(encoding="utf-8"))
    corpus.verify_manifest(manifest)
    samples = {sample["id"]: sample for sample in corpus.build_samples()}
    compressor = zstandard.ZstdCompressor(compression_params=zstandard.ZstdCompressionParameters.from_level(
        config["zstd_level"], window_log=config["zstd_window_log"], write_checksum=1,
        write_content_size=1, write_dict_id=0, threads=0,
    ))
    rows = []
    for index, manifest_sample in enumerate(manifest["samples"]):
        sample = dict(manifest_sample, bytes=samples[manifest_sample["id"]]["bytes"])
        v1 = _current_block(sample, index, PROTOCOL_V1_BLOCK_VERSION)
        v2 = _current_block(sample, index, ADMISSION_BLOCK_VERSION)
        v1_bytes = v1.consensus_payload_v1_bytes()
        v2_bytes = v2.consensus_payload_v1_bytes()
        rows.append(_row(sample, "current_v1", "identity", v1_bytes, "media_bytes", len(sample["bytes"]), v1.to_dict()))
        rows.append(_row(sample, "current_v2", "identity", v2_bytes, "media_bytes", len(sample["bytes"]), v2.to_dict()))
        certificate = v2.admission_certificate
        native = v2.native_transactions
        identity = _v3_envelope(sample, index, sample["bytes"], "identity", certificate, native)
        compressed_payload = compressor.compress(sample["bytes"])
        zstd = _v3_envelope(sample, index, compressed_payload, "zstd", certificate, native)
        chosen = zstd if len(zstd) < len(identity) else identity
        chosen_payload = compressed_payload if chosen is zstd else sample["bytes"]
        chosen_codec = "zstd" if chosen is zstd else "identity"
        rows.append(_row(sample, "projected_v3", "identity", identity, "media", len(sample["bytes"]), _v3_storage_record(identity)))
        rows.append(_row(sample, "projected_v3", "zstd_candidate", zstd, "media", len(compressed_payload), _v3_storage_record(zstd)))
        rows.append(_row(sample, "projected_v3", "adaptive", chosen, "media", len(chosen_payload), _v3_storage_record(chosen), selected_codec=chosen_codec))
    return rows


def _matches_group(row: dict[str, Any], rule: dict[str, Any]) -> bool:
    size = row["original_media_bytes"]
    return (
        ("minimum_original_bytes" not in rule or size >= rule["minimum_original_bytes"])
        and ("maximum_original_bytes" not in rule or size <= rule["maximum_original_bytes"])
        and ("mime_prefix" not in rule or row["mime_type"].startswith(rule["mime_prefix"]))
        and ("benchmark_scoring" not in rule or row["benchmark_scoring"] == rule["benchmark_scoring"])
    )


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    complete = [row["complete_serialized_block_bytes"] for row in rows]
    metadata = [row["nonmedia_metadata_percent"] for row in rows]
    total = sum(complete)
    nonmedia = sum(row["nonmedia_metadata_bytes"] for row in rows)
    return {
        "samples": len(rows), "complete_block_bytes": {"p50": _nearest_rank(complete, 50), "p95": _nearest_rank(complete, 95), "p99": _nearest_rank(complete, 99), "worst": max(complete)},
        "metadata_percent": {"p50": _nearest_rank(metadata, 50), "p95": _nearest_rank(metadata, 95), "p99": _nearest_rank(metadata, 99), "worst": max(metadata), "byte_weighted_aggregate": nonmedia / total * 100 if total else 0},
        "component_totals": {key: sum(row[key] for row in rows) for key in (
            "serialized_media_representation_bytes", "media_descriptor_overhead_bytes", "header_bytes", "certificate_bytes", "transaction_record_bytes", "remaining_structural_metadata_bytes", "envelope_bytes", "delimiter_bytes", "complete_serialized_block_bytes", "nonmedia_metadata_bytes"
        )},
    }


def aggregate(rows: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    identifiers = sorted({(row["representation"], row["encoding"]) for row in rows})
    for representation, encoding in identifiers:
        selected = [row for row in rows if (row["representation"], row["encoding"]) == (representation, encoding)]
        result[f"{representation}:{encoding}"] = {"all": _summary(selected)}
        for name, rule in config["workload_groups"].items():
            group = [row for row in selected if _matches_group(row, rule)]
            if group:
                result[f"{representation}:{encoding}"][name] = _summary(group)
    return result


def _file_size(path: Path) -> int:
    return path.stat().st_size if path.exists() else 0


def _dbstat_sizes(connection: sqlite3.Connection) -> dict[str, int]:
    try:
        rows = connection.execute("SELECT name, SUM(pgsize) FROM dbstat GROUP BY name").fetchall()
    except sqlite3.OperationalError:
        return {"available": False}
    index_bytes = sum(size for name, size in rows if name.startswith("sqlite_autoindex") or name.endswith("_idx"))
    return {"available": True, "index_bytes": index_bytes, "objects": {name: size for name, size in rows}}


def _sqlite_observation(label: str, records: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]:
    counts = sorted({min(len(records), count) for count in config["sqlite"]["observation_block_counts"] if count > 0} | {len(records)})
    # The Python runtime may map the system temp directory into a sandbox that
    # SQLite cannot reopen.  Keep this isolated, ephemeral fixture beneath the
    # repository's writable benchmarks directory instead.
    with tempfile.TemporaryDirectory(prefix=".task-7-7-", dir=PROJECT_ROOT / "benchmarks") as directory:
        database = Path(directory) / "composition.db"
        backend = SQLiteStorageBackend(sqlite_db_path=str(database))
        with sqlite3.connect(database) as connection:
            journal_mode = connection.execute(f"PRAGMA journal_mode={config['sqlite']['journal_mode']}").fetchone()[0]
            actual_page_size = connection.execute("PRAGMA page_size").fetchone()[0]
            if actual_page_size != config["sqlite"]["page_size"]:
                raise ValueError(f"SQLite page size {actual_page_size} differs from configured measurement page size")
            baseline_db = _file_size(database)
            baseline_pages = connection.execute("PRAGMA page_count").fetchone()[0]
            baseline_stat = _dbstat_sizes(connection)
        connection.close()
        observations = []
        for count in counts:
            backend.save_chain(records[:count])
            wal = database.with_name(database.name + "-wal")
            with sqlite3.connect(database) as connection:
                pages = connection.execute("PRAGMA page_count").fetchone()[0]
                logical = connection.execute("SELECT length(json_data) FROM storage_sections WHERE section_name='chain'").fetchone()[0]
                dbstat = _dbstat_sizes(connection)
            connection.close()
            observations.append({"blocks": count, "logical_chain_json_bytes": logical, "database_bytes_before_checkpoint": _file_size(database), "allocated_page_bytes_before_checkpoint": pages * actual_page_size, "wal_bytes_before_checkpoint": _file_size(wal), "dbstat_before_checkpoint": dbstat})
        with sqlite3.connect(database) as connection:
            checkpoint = connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
            pages_after_checkpoint = connection.execute("PRAGMA page_count").fetchone()[0]
            dbstat_after_checkpoint = _dbstat_sizes(connection)
        connection.close()
        database_bytes_after_checkpoint = _file_size(database)
        with sqlite3.connect(database) as connection:
            connection.execute("VACUUM")
            pages_after_vacuum = connection.execute("PRAGMA page_count").fetchone()[0]
            dbstat_after_vacuum = _dbstat_sizes(connection)
        connection.close()
        gc.collect()
        return {"label": label, "storage_kind": "actual_current_sqlite" if label.startswith("current") else "projected_v3_using_current_json_section_storage_only", "journal_mode": journal_mode, "page_size": actual_page_size, "baseline_database_bytes": baseline_db, "baseline_allocated_page_bytes": baseline_pages * actual_page_size, "baseline_dbstat": baseline_stat, "observations": observations, "database_bytes_after_checkpoint": database_bytes_after_checkpoint, "database_bytes_after_vacuum": _file_size(database), "allocated_page_bytes_after_checkpoint": pages_after_checkpoint * actual_page_size, "allocated_page_bytes_after_vacuum": pages_after_vacuum * actual_page_size, "wal_bytes_after_checkpoint": _file_size(database.with_name(database.name + "-wal")), "dbstat_after_checkpoint": dbstat_after_checkpoint, "dbstat_after_vacuum": dbstat_after_vacuum}


def sqlite_measurements(rows: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]:
    wanted = (("current_v2", "identity"), ("projected_v3", "adaptive"))
    results = {}
    for representation, encoding in wanted:
        selected = [row for row in rows if row["representation"] == representation and row["encoding"] == encoding]
        if selected:
            results[f"{representation}:{encoding}"] = _sqlite_observation(
                f"{representation}:{encoding}", [row["storage_record"] for row in selected], config
            )
    return results


def candidate_limits(rows: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]:
    candidates = config["provisional_candidates"]
    adaptive = [row for row in rows if row["representation"] == "projected_v3" and row["encoding"] == "adaptive"]
    maximum = max(row["complete_serialized_block_bytes"] for row in adaptive)
    return {
        "not_a_protocol_change": True,
        "legacy_candidate": {"original_and_encoded_media_cap_bytes": candidates["legacy_media_cap_bytes"], "complete_block_cap_bytes": candidates["legacy_complete_block_cap_bytes"], "projected_adaptive_rows_that_fit": sum(row["original_media_bytes"] <= candidates["legacy_media_cap_bytes"] and row["encoded_media_bytes"] <= candidates["legacy_media_cap_bytes"] and row["complete_serialized_block_bytes"] <= candidates["legacy_complete_block_cap_bytes"] for row in adaptive), "samples": len(adaptive)},
        "evaluated_2mib_candidate": {"original_and_encoded_media_cap_bytes": candidates["evaluated_media_cap_bytes"], "complete_block_cap_bytes": candidates["evaluated_complete_block_cap_bytes"], "observed_max_projected_block_bytes": maximum, "headroom_over_observed_bytes": candidates["evaluated_complete_block_cap_bytes"] - maximum},
        "admission_rule_required": "Admission must calculate the exact future canonical v3 bytes after certificate, reward, native transaction, and finality-required data are fixed, and reject when it exceeds the complete-block cap. Per-media caps alone cannot prove block fit.",
        "unbounded_inputs": "No safe complete-block cap can be finalized until certificate votes/signature sizes, native transaction count/size, captions, and finality attachment placement each have explicit protocol maxima.",
    }


def run(config: dict[str, Any], *, include_sqlite: bool = True) -> dict[str, Any]:
    rows = build_rows(config)
    public_rows = [{key: value for key, value in row.items() if key != "storage_record"} for row in rows]
    manifest_bytes = (PROJECT_ROOT / config["corpus_manifest"]).read_bytes()
    return {
        "measurement_id": config["measurement_id"], "measurement_version": config["measurement_version"],
        "measurement_boundary": {"current_v1_v2": "direct measurement of Block.consensus_payload_v1_bytes using deterministic, schema-shaped generated fixtures; no finalized production blocks were present in this runner.", "projected_v3": "deterministic construction from the proposed v3 schema and protocol-v2-style canonical envelope. It is not accepted by current production code and is not a production block.", "sqlite": "isolated temporary databases using the current SQLiteStorageBackend and unchanged schema; v3 rows exercise only its JSON-section storage behavior, not a future authoritative v3 schema."},
        "environment": {"python": sys.version, "platform": platform.platform(), "zstandard": zstandard.__version__, "sqlite": sqlite3.sqlite_version},
        "corpus": {"id": json.loads(manifest_bytes)["corpus_id"], "version": json.loads(manifest_bytes)["corpus_version"], "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(), "verified_regeneration": True},
        "methodology": {"percentiles": "equal-block nearest-rank percentile: sorted[ceil(n*p/100)-1]. Each representation has 36 rows, so p99 is a descriptive nearest-rank value rather than a robust tail estimate.", "metadata_denominator": "nonmedia_metadata_bytes / complete_serialized_block_bytes; nonmedia means every exact serialized byte outside the one media field, including envelopes, delimiters, certificate, transactions, header, and all structural fields.", "signature_accounting": "signature_bytes_subset is diagnostic only and is contained in certificate_bytes and transaction_record_bytes; it is not added to reconciliation totals."},
        "per_block": public_rows, "aggregates": aggregate(public_rows, config), "candidate_limit_evaluation": candidate_limits(public_rows, config),
        "sqlite": sqlite_measurements(rows, config) if include_sqlite else {"skipped": True},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--skip-sqlite", action="store_true")
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    output = run(config, include_sqlite=not args.skip_sqlite)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {args.output} ({len(output['per_block'])} per-block rows)")


if __name__ == "__main__":
    main()
