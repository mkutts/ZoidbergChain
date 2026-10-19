import json

from scripts import milestone_7_task_7_7_block_composition as composition


def test_component_accounting_reconciles_every_constructed_block():
    config = json.loads(composition.CONFIG_PATH.read_text(encoding="utf-8"))
    rows = composition.build_rows(config)

    assert len(rows) == 5 * len(json.loads((composition.PROJECT_ROOT / config["corpus_manifest"]).read_text(encoding="utf-8"))["samples"])
    for row in rows:
        components = {key: row[key] for key in (
            "serialized_media_representation_bytes", "certificate_bytes",
            "transaction_record_bytes", "header_bytes",
            "remaining_structural_metadata_bytes", "envelope_bytes", "delimiter_bytes",
        )}
        assert sum(components.values()) == row["complete_serialized_block_bytes"]
        assert row["nonmedia_metadata_bytes"] == (
            row["complete_serialized_block_bytes"] - row["serialized_media_representation_bytes"]
        )
        assert row["signature_bytes_subset"] <= row["certificate_bytes"] + row["transaction_record_bytes"]


def test_projected_adaptive_mode_never_exceeds_its_identity_projection():
    config = json.loads(composition.CONFIG_PATH.read_text(encoding="utf-8"))
    rows = composition.build_rows(config)
    identity = {row["sample_id"]: row for row in rows if row["representation"] == "projected_v3" and row["encoding"] == "identity"}
    adaptive = [row for row in rows if row["representation"] == "projected_v3" and row["encoding"] == "adaptive"]

    assert {row["selected_codec"] for row in adaptive} == {"identity", "zstd"}
    assert all(row["complete_serialized_block_bytes"] <= identity[row["sample_id"]]["complete_serialized_block_bytes"] for row in adaptive)
