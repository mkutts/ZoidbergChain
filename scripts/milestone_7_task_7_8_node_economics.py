"""Deterministic three-year full-archival-node economics model for Task 7.8.

It models retained canonical media, a conservative SQLite projection, full backups,
and peer transfer.  It deliberately does not touch the chain or production storage.
"""
from __future__ import annotations

import argparse
import csv
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "benchmarks" / "milestone_7_task_7_8_config.json"
DEFAULT_JSON = ROOT / "benchmarks" / "milestone_7_task_7_8_results.json"
DEFAULT_CSV = ROOT / "benchmarks" / "milestone_7_task_7_8_monthly.csv"


def validate_config(cfg: dict[str, Any]) -> None:
    required = {"schema_version", "months", "month_days", "bytes_per_gib", "workloads", "storage", "backups", "network", "compute", "profiles", "sensitivity"}
    missing = required - set(cfg)
    if missing or cfg.get("schema_version") != 1 or cfg.get("months") != 36 or len(cfg.get("month_days", [])) != 12:
        raise ValueError("invalid economics configuration")
    if not cfg["workloads"] or not cfg["backups"] or not cfg["profiles"]:
        raise ValueError("economics configuration has no scenarios")


def gib(value: float, cfg: dict[str, Any]) -> float:
    return value / cfg["bytes_per_gib"]


def month_days(cfg: dict[str, Any], month: int) -> int:
    return cfg["month_days"][(month - 1) % 12]


def capacity_month(rows: list[dict[str, Any]], field: str, threshold_gib: float) -> int | None:
    return next((row["month"] for row in rows if row[field] / 1024 ** 3 >= threshold_gib), None)


def monthly_cost(profile: dict[str, Any], primary_gib: float, backup_gib: float, egress_gib: float) -> dict[str, float]:
    primary = max(0.0, primary_gib - profile["included_primary_gib"]) * profile["primary_gib_month"]
    return {"compute": profile["monthly_compute"], "primary_storage": primary,
            "backup": backup_gib * profile["backup_gib_month"], "egress": egress_gib * profile["egress_gib"],
            "total": profile["monthly_compute"] + primary + backup_gib * profile["backup_gib_month"] + egress_gib * profile["egress_gib"]}


def simulate(cfg: dict[str, Any], blocks_per_day: int, workload_name: str, profile_name: str,
             backup_name: str = "recommended", peer_count: int | None = None,
             encoded_factor: float = 1.0, physical_factor: float = 1.0) -> dict[str, Any]:
    if blocks_per_day <= 0 or workload_name not in cfg["workloads"] or profile_name not in cfg["profiles"] or backup_name not in cfg["backups"]:
        raise ValueError("invalid scenario selector")
    workload, profile, backup = cfg["workloads"][workload_name], cfg["profiles"][profile_name], cfg["backups"][backup_name]
    peers = peer_count if peer_count is not None else cfg["network"]["peer_count"]
    if peers < 0 or encoded_factor <= 0 or physical_factor <= 0:
        raise ValueError("peer count and factors must be positive")
    # Size variation changes the complete block while holding Task 7.7-shaped metadata fixed.
    canonical_per_block = workload["metadata_bytes"] + (workload["canonical_block_bytes"] - workload["metadata_bytes"]) * encoded_factor
    amp = workload["physical_amplification"] * physical_factor
    rows, canonical, cumulative_cost = [], 0.0, 0.0
    for month in range(1, cfg["months"] + 1):
        blocks = blocks_per_day * month_days(cfg, month)
        new_canonical = blocks * canonical_per_block
        canonical += new_canonical
        primary = cfg["storage"]["base_database_bytes"] + canonical * amp
        backup_retained = primary * backup["retained_full_copies"] * backup["compression_ratio"]
        snapshots = primary * backup["snapshot_copies"]
        temporary = primary * cfg["storage"]["temporary_safety_fraction"] + new_canonical * amp * cfg["storage"]["wal_peak_multiplier"] + cfg["storage"]["temporary_fixed_bytes"]
        incoming = new_canonical * cfg["network"]["incoming_multiplier"] * (1 + cfg["network"]["protocol_overhead_fraction"] + cfg["network"]["retransmission_fraction"])
        outgoing = new_canonical * peers * cfg["network"]["outgoing_multiplier"] * (1 + cfg["network"]["protocol_overhead_fraction"] + cfg["network"]["retransmission_fraction"])
        backup_transfer = primary * backup["frequency_per_month"]
        costs = monthly_cost(profile, gib(primary, cfg), gib(backup_retained, cfg), gib(outgoing + backup_transfer, cfg))
        cumulative_cost += costs["total"]
        rows.append({"month": month, "days": month_days(cfg, month), "new_blocks": blocks, "cumulative_blocks": blocks_per_day * sum(month_days(cfg, x) for x in range(1, month + 1)), "new_canonical_bytes": round(new_canonical), "cumulative_canonical_bytes": round(canonical), "primary_physical_bytes": round(primary), "backup_retained_bytes": round(backup_retained), "snapshot_bytes": round(snapshots), "temporary_headroom_bytes": round(temporary), "incoming_bytes": round(incoming), "outgoing_bytes": round(outgoing), "backup_transfer_bytes": round(backup_transfer), "monthly_cost": costs, "cumulative_cost": cumulative_cost})
    m36 = rows[-1]
    compute = cfg["compute"]
    ram = (compute["node_process_gib"] + compute["database_cache_gib"] + compute["os_and_monitoring_gib"] + compute["worker_concurrency"] * compute["decoder_worker_mib"] / 1024) * (1 + compute["safety_fraction"])
    cpu_seconds_day = blocks_per_day * compute["worker_p95_seconds"]
    status = "PASS" if m36["monthly_cost"]["total"] < 100 else "FAIL"
    return {"scenario": {"blocks_per_day": blocks_per_day, "workload": workload_name, "profile": profile_name, "backup_policy": backup_name, "peer_count": peers, "encoded_factor": encoded_factor, "physical_factor": physical_factor}, "rows": rows, "month_36": m36, "three_year": {"blocks": m36["cumulative_blocks"], "canonical_bytes": m36["cumulative_canonical_bytes"], "primary_physical_bytes": m36["primary_physical_bytes"], "backup_retained_bytes": m36["backup_retained_bytes"], "snapshot_bytes": m36["snapshot_bytes"], "initial_sync_bytes": round(m36["cumulative_canonical_bytes"] * cfg["network"]["bootstrap_multiplier"]), "cumulative_outgoing_bytes": sum(r["outgoing_bytes"] for r in rows), "cumulative_cost": cumulative_cost}, "capacity_months": {str(t) + "_gib_primary": capacity_month(rows, "primary_physical_bytes", t) for t in (100, 500, 1000, 10000)}, "compute": {"required_ram_gib": ram, "profile_ram_gib": profile["memory_gib"], "profile_vcpus": profile["vcpus"], "validation_cpu_seconds_per_day": cpu_seconds_day, "single_vcpu_utilization_percent": cpu_seconds_day / 86400 * 100, "feasibility": "PLAUSIBLE WITH BURST LIMITS" if ram <= profile["memory_gib"] and cpu_seconds_day / 86400 < profile["vcpus"] * 0.5 else "UNDETERMINED"}, "acceptance": status}


def max_block_bytes_at_budget(cfg: dict[str, Any], blocks_per_day: int, profile_name: str, budget: float = 100.0) -> int:
    """Binary-search month-36 canonical bytes/block, retaining all mandatory costs."""
    trial = deepcopy(cfg)
    low, high = 0, 100_000_000
    for _ in range(40):
        middle = (low + high) // 2
        trial["workloads"]["budget_probe"] = {"metadata_bytes": 0, "canonical_block_bytes": middle,
            "physical_amplification": 1.25, "label": "probe", "weighting": "derived", "empirical": False,
            "original_bytes": middle, "encoded_bytes": middle, "transfer_multiplier": 1.0}
        cost = simulate(trial, blocks_per_day, "budget_probe", profile_name)["month_36"]["monthly_cost"]["total"]
        if cost <= budget: low = middle
        else: high = middle
    return low


def build_results(cfg: dict[str, Any]) -> dict[str, Any]:
    scenarios = [simulate(cfg, rate, workload, profile) for rate in (100, 1000, 10000) for workload in cfg["workloads"] for profile in cfg["profiles"]]
    sensitivities = [simulate(cfg, 1000, "representative_corpus", "budget_vps", backup, peers, encoded, amp) for backup in cfg["sensitivity"]["backup_policies"] for peers in cfg["sensitivity"]["peer_counts"] for encoded in cfg["sensitivity"]["encoded_size_factors"] for amp in cfg["sensitivity"]["physical_amplification_factors"]]
    limits = {str(rate): {profile: max_block_bytes_at_budget(cfg, rate, profile) for profile in cfg["profiles"]} for rate in (100, 1000, 10000)}
    return {"schema_version": 1, "deterministic": True, "configuration": {"months": cfg["months"], "calendar": cfg["model"]}, "scenarios": scenarios, "sensitivity_representative_1000_budget": sensitivities, "max_canonical_block_bytes_at_100_month36": limits}


def write_outputs(result: dict[str, Any], json_path: Path, csv_path: Path) -> None:
    json_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    fields = ["blocks_per_day", "workload", "profile", "month", "new_blocks", "cumulative_blocks", "cumulative_canonical_bytes", "primary_physical_bytes", "backup_retained_bytes", "temporary_headroom_bytes", "outgoing_bytes", "monthly_cost_usd"]
    with csv_path.open("w", newline="", encoding="utf-8") as out:
        writer = csv.DictWriter(out, fieldnames=fields); writer.writeheader()
        for item in result["scenarios"]:
            for row in item["rows"]:
                writer.writerow({"blocks_per_day": item["scenario"]["blocks_per_day"], "workload": item["scenario"]["workload"], "profile": item["scenario"]["profile"], "month": row["month"], "new_blocks": row["new_blocks"], "cumulative_blocks": row["cumulative_blocks"], "cumulative_canonical_bytes": row["cumulative_canonical_bytes"], "primary_physical_bytes": row["primary_physical_bytes"], "backup_retained_bytes": row["backup_retained_bytes"], "temporary_headroom_bytes": row["temporary_headroom_bytes"], "outgoing_bytes": row["outgoing_bytes"], "monthly_cost_usd": f'{row["monthly_cost"]["total"]:.6f}'})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG); parser.add_argument("--output", type=Path, default=DEFAULT_JSON); parser.add_argument("--csv", type=Path, default=DEFAULT_CSV); parser.add_argument("--blocks-per-day", type=int); parser.add_argument("--workload"); parser.add_argument("--profile"); parser.add_argument("--backup-policy", default="recommended"); parser.add_argument("--peer-count", type=int); parser.add_argument("--encoded-factor", type=float, default=1.0); parser.add_argument("--physical-factor", type=float, default=1.0)
    args = parser.parse_args(); cfg = json.loads(args.config.read_text(encoding="utf-8")); validate_config(cfg)
    if args.blocks_per_day is not None:
        if not args.workload or not args.profile: parser.error("--workload and --profile are required with --blocks-per-day")
        result = {"schema_version": 1, "deterministic": True, "scenarios": [simulate(cfg, args.blocks_per_day, args.workload, args.profile, args.backup_policy, args.peer_count, args.encoded_factor, args.physical_factor)]}
    else: result = build_results(cfg)
    write_outputs(result, args.output, args.csv); print(f"wrote {args.output} and {args.csv}")


if __name__ == "__main__": main()
