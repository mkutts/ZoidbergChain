import json

import pytest

from scripts import milestone_7_task_7_8_node_economics as economics


@pytest.fixture
def cfg():
    return json.loads(economics.DEFAULT_CONFIG.read_text(encoding="utf-8"))


def test_block_arithmetic_and_monthly_accumulation(cfg):
    result = economics.simulate(cfg, 100, "small_media", "budget_vps")
    assert result["rows"][0]["new_blocks"] == 3100
    assert result["rows"][1]["new_blocks"] == 2800
    assert result["three_year"]["blocks"] == 100 * 365 * 3
    assert result["rows"][-1]["cumulative_canonical_bytes"] == result["three_year"]["canonical_bytes"]


def test_storage_backup_network_and_costs_are_accounted(cfg):
    result = economics.simulate(cfg, 1000, "representative_corpus", "mainstream_cloud")
    row = result["month_36"]
    assert row["primary_physical_bytes"] > row["cumulative_canonical_bytes"]
    assert row["backup_retained_bytes"] > row["primary_physical_bytes"]
    assert row["temporary_headroom_bytes"] > row["primary_physical_bytes"] * .2
    assert row["outgoing_bytes"] > row["incoming_bytes"]
    assert row["monthly_cost"]["total"] == sum(row["monthly_cost"].values()) - row["monthly_cost"]["total"]
    assert result["three_year"]["cumulative_cost"] >= sum(r["monthly_cost"]["total"] for r in result["rows"])


def test_threshold_status_sensitivity_and_reproducibility(cfg):
    first = economics.simulate(cfg, 10000, "large_media", "mainstream_cloud")
    second = economics.simulate(cfg, 10000, "large_media", "mainstream_cloud")
    assert first == second
    assert first["acceptance"] == "FAIL"
    assert first["capacity_months"]["1000_gib_primary"] is not None
    smaller = economics.simulate(cfg, 1000, "representative_corpus", "budget_vps", encoded_factor=.75)
    larger = economics.simulate(cfg, 1000, "representative_corpus", "budget_vps", encoded_factor=1.25)
    assert larger["month_36"]["primary_physical_bytes"] > smaller["month_36"]["primary_physical_bytes"]
    assert economics.max_block_bytes_at_budget(cfg, 1000, "budget_vps") > economics.max_block_bytes_at_budget(cfg, 10000, "budget_vps")


@pytest.mark.parametrize("rate,workload,profile", [(0, "small_media", "budget_vps"), (100, "bad", "budget_vps"), (100, "small_media", "bad")])
def test_invalid_selectors_rejected(cfg, rate, workload, profile):
    with pytest.raises(ValueError):
        economics.simulate(cfg, rate, workload, profile)


def test_malformed_config_rejected(cfg):
    cfg.pop("network")
    with pytest.raises(ValueError):
        economics.validate_config(cfg)
