"""Bounded BFS plus deterministic adversarial schedules; NOT a formal checker.

Run from repository root: python -B -m verification.tendermint717h.check
All output is ordinary JSON; no databases, keys, network, codecs or node imports.
"""
import argparse
from collections import deque
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import platform
import time

from .model import Block, Config, Model, edge_errors, invariant_errors
from .scenarios import (Run, controlled, different_locks, digest, hidden_commit,
                        invalid_byzantine_proposal, jsonable,
                        round_three_equivocation, snapshot, unavailable_proposal_qc)


def explore(model, initial, *, depth, state_limit):
    """Every enabled transition/order up to depth, unless explicit cap stops BFS.

    No symmetry/partial-order reduction or automatic execution of enabled upon
    rules. Duplicate network deliveries and intact restart are exact stutters and
    are quotiented out. Timers are explicit armed events, not an elapsed clock.
    """
    begun = time.perf_counter()
    queue = deque([(initial, 0)])
    seen = {initial}
    paths = {initial: []}
    transitions = 0
    expanded = 0
    boundary = 0
    deepest = 0
    reached_cap = False
    counterexample = None
    violations = invariant_errors(model, initial)
    if violations:
        counterexample = dict(violations=violations, actions=[], state=snapshot(initial))
    while queue and counterexample is None and not reached_cap:
        w, level = queue.popleft()
        deepest = max(deepest, level)
        if level == depth:
            boundary += 1
            continue
        expanded += 1
        for action, after in model.successors(w):
            transitions += 1
            errors = invariant_errors(model, after) + edge_errors(w, after, action)
            if errors:
                counterexample = dict(violations=sorted(set(errors)),
                                      actions=paths[w]+[action], state=snapshot(after))
                break
            if after not in seen:
                if len(seen) >= state_limit:
                    reached_cap = True
                    break
                seen.add(after)
                paths[after] = paths[w]+[action]
                queue.append((after, level+1))
    return dict(method="deterministic BFS of executable transition system",
                depth_bound=depth, state_limit=state_limit,
                states=len(seen), transitions=transitions, expanded_states=expanded,
                depth_boundary_states=boundary, frontier_unexpanded=len(queue),
                deepest_dequeued=deepest, state_cap_reached=reached_cap,
                exhausted_configured_depth=not reached_cap and counterexample is None,
                result="COUNTEREXAMPLE" if counterexample else "BOUNDED_PASS",
                counterexample=counterexample,
                runtime_seconds=round(time.perf_counter()-begun, 6))


def suite():
    cases = []
    h = hidden_commit()
    locks = different_locks()
    equiv = round_three_equivocation()
    for name, run in (("hidden_commit_nil_rounds_intact_restart", h),
                      ("different_locks_valid_round_late_valid_learning", locks),
                      ("competing_proposals_byzantine_equivocation_reordering", equiv),
                      ("invalid_byzantine_proposal_rejected", invalid_byzantine_proposal()),
                      ("qc_without_proposal_or_data_then_fetch", unavailable_proposal_qc())):
        cases.append(run.result(name))
    chain = (Block("X"), Block("Y"), Block("XX", 2, "X"), Block("YY", 2, "Y"))
    configurations = [
        ("eventually_synchronous_byzantine_withholds", Config(max_height=1), True),
        ("consecutive_heights_finalized_parents", Config(blocks=chain), True),
        ("one_offline", Config(byzantine=frozenset(), offline=frozenset({3}), max_height=1), True),
        ("proposer_crash_then_synchronous", Config(byzantine=frozenset(), offline=frozenset({0}), max_height=1), True),
        ("two_offline_no_quorum", Config(byzantine=frozenset(), offline=frozenset({2, 3}), max_height=1), False),
        ("no_valid_media", Config(blocks=(), max_height=1), False),
        ("invalid_media", Config(blocks=(Block("X", canonical=False),), max_height=1), False),
        ("missing_admission_evidence", Config(max_height=1, missing=frozenset((i, v) for i in range(3) for v in ("X", "Y")), retrievable=frozenset()), False),
        ("incomplete_proposal_data", Config(max_height=1, missing=frozenset({(1, "X"), (2, "X"), (1, "Y"), (2, "Y")}), retrievable=frozenset()), False),
        ("local_decoder_unavailable", Config(max_height=1, decoder_unavailable=frozenset({1})), False),
    ]
    for name, config, progress in configurations:
        run = controlled(config, rounds=16)
        online = [n for n in run.w.nodes if n.identity not in config.offline]
        decided = all(n.decisions for n in online)
        assert decided == progress, (name, snapshot(run.w))
        cases.append(run.result(name, "selected_schedule_progress" if progress else "no_progress_promise"))
    # Partition schedules never deliver across components. Existing sent messages
    # remain available for healing; safety does not require eventual delivery.
    partition = Run(Config(max_height=1))
    partition.start()
    # A,B together, C isolated, D withholding: neither component can reach q.
    partition.settle(recipients={0, 1})
    assert not any(n.decisions for n in partition.w.nodes)
    cases.append(partition.result("permanent_partition_prefix", "no_progress_promise"))
    partition.settle()
    assert all(n.decisions for n in partition.w.nodes)
    cases.append(partition.result("partition_healed_eventual_sync", "selected_schedule_progress"))
    # Old-round precommits may decide after moving on, without current polka.
    late = Run(Config(max_height=1))
    late.start({0: "X"})
    late.settle(excluded_kinds={"precommit"})
    old = sorted(m for m in late.w.sent if m.kind == "precommit" and m.value == "X")
    assert len(old) == 3
    # Deliver PC to B,C only, let B's precommit timer advance it first.
    for i in (1, 2):
        for m in old:
            late.deliver(i, m)
        late.step(f"L47/arm/{i}")
    late.step("L65/timeout/1/1")
    late.mark("old_round_commit_after_advance")
    late.step("L49/decide/1/X")
    assert late.node(1).decisions[0].proposal.round == 0
    cases.append(late.result("delayed_old_round_precommits"))
    negatives = [hidden_commit(Config(max_height=1, max_round=2, broken_locking=True)).result("removed_lock_check", "counterexample_required"),
                 hidden_commit(unsafe_restart=True).result("lost_signer_state", "counterexample_required")]
    return cases, negatives, h, locks, equiv, late


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("verification/tendermint717h/results"))
    parser.add_argument("--depth", type=int, default=4)
    parser.add_argument("--state-limit", type=int, default=50000)
    args = parser.parse_args()
    if args.depth < 1 or args.state_limit < 2:
        parser.error("positive depth and state-limit >=2 required")
    begun = time.perf_counter()
    cases, negatives, h, locks, equiv, late = suite()
    searches = []
    seeds = [("initial", Model(Config(max_height=1, max_round=1)), None, []),
             ("hidden_X_decision", h.model, *h.checkpoints["hidden_X_decision"]),
             ("different_honest_locks", locks.model, *locks.checkpoints["different_honest_locks"]),
             ("justified_proposal", locks.model, *locks.checkpoints["justified_proposal"]),
             ("byzantine_proposer_round3", equiv.model, *equiv.checkpoints["byzantine_proposer_round3"]),
             ("old_round_commit_after_advance", late.model, *late.checkpoints["old_round_commit_after_advance"])]
    for name, model, seed, prefix in seeds:
        # Search-specific bounds; prefix actions and state are unchanged. These
        # restrict the explored universe, never the reference guards within it.
        round_bounds = {"initial": 1, "hidden_X_decision": 2,
                        "different_honest_locks": 3, "justified_proposal": 3,
                        "byzantine_proposer_round3": 4, "old_round_commit_after_advance": 1}
        model = Model(replace(model.c, max_height=1, max_round=round_bounds[name]))
        seed = seed or model.initial()
        result = explore(model, seed, depth=args.depth, state_limit=args.state_limit)
        result.update(name=name, config=jsonable(model.c), seed_digest=digest(seed),
                      reachable_prefix_transitions=len(prefix))
        searches.append(result)
        args.output.mkdir(parents=True, exist_ok=True)
        (args.output / f"seed-{name}.json").write_text(json.dumps(dict(config=jsonable(model.c),
            trace=prefix, state=jsonable(seed)), sort_keys=True, indent=2)+"\n", encoding="utf-8")
        print(f"{name}: {result['result']} states={result['states']} transitions={result['transitions']} cap={result['state_cap_reached']}", flush=True)
    for case in cases + negatives:
        (args.output / f"trace-{case['name']}.json").write_text(json.dumps(case, sort_keys=True, indent=2)+"\n", encoding="utf-8")
    source_hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                     for p in sorted(Path(__file__).parent.glob("*.py"))}
    report = dict(task="7.17H", reference="https://arxiv.org/pdf/1807.04938v3#page=6",
                  method="bounded executable model; not TLC/Apalache or unbounded formal proof",
                  python=platform.python_version(), source_sha256=source_hashes,
                  N=4, f=1, q=3, searches=searches,
                  scenarios=[{k: v for k, v in c.items() if k != "trace"} for c in cases],
                  negative_controls=[{k: v for k, v in c.items() if k != "trace"} for c in negatives],
                  totals=dict(search_states_sum=sum(s["states"] for s in searches),
                              search_transitions=sum(s["transitions"] for s in searches),
                              scenario_transitions=sum(s["transitions"] for s in cases),
                              negative_transitions=sum(s["transitions"] for s in negatives)),
                  runtime_seconds=round(time.perf_counter()-begun, 6),
                  implementation_pass=False, release_pass=False)
    passed = (all(s["result"] == "BOUNDED_PASS" for s in searches) and
              all(not s["violations"] for s in cases) and
              all("A:honest_disagreement" in s["violations"] for s in negatives))
    report["model_level_result"] = "BOUNDED_PASS" if passed else "FAIL"
    (args.output / "summary.json").write_text(json.dumps(report, sort_keys=True, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(dict(result=report["model_level_result"], **report["totals"], runtime_seconds=report["runtime_seconds"])))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
