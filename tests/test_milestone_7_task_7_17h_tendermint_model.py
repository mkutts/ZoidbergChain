"""Inactive model verification; does not import the node, codecs or key tools."""
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from verification.tendermint717h.model import (
    Block, Config, CONTEXT, Decision, Message, Model, NIL, Node, Q, World,
    edge_errors, invariant_errors,
)
from verification.tendermint717h.scenarios import (
    Run, digest, jsonable,
)
from verification.tendermint717h.check import explore, suite
from verification.tendermint717h.replay import replay


def enabled(run, prefix):
    return [(a, w) for a, w in run.model.successors(run.w) if a.startswith(prefix)]


@pytest.fixture(scope="module")
def schedules():
    return suite()


def test_all_adversarial_scenarios_and_expected_progress(schedules):
    cases, negatives, *_ = schedules
    assert len(cases) == 18
    assert all(not c["violations"] for c in cases)
    assert all("A:honest_disagreement" in n["violations"] for n in negatives)


def test_hidden_commit_retains_lock_across_nil_and_intact_restart(schedules):
    h = schedules[2]
    assert h.node(1).locked == "X" and h.node(1).lr == 0
    assert h.node(0).decisions[0].value == "X"
    assert h.message("prevote", 1, NIL, 2)
    assert not h.node(2).decisions


def test_different_locks_are_reachable_and_later_justification_switches(schedules):
    run = schedules[3]
    w, _ = run.checkpoints["different_honest_locks"]
    assert [n.locked for n in w.nodes] == ["X", "Y", NIL]
    assert all(n.decisions[0].value == "Y" for n in run.w.nodes)
    assert run.message("prevote", 0, "Y", 2)


def test_byzantine_proposer_equivocation_preserves_honest_slots(schedules):
    run = schedules[4]
    assert len({m.value for m in run.w.sent if m.sender == 3 and m.kind == "proposal" and m.round == 3}) == 2
    assert not invariant_errors(run.model, run.w)


def test_valid_value_learning_after_nil_precommit_is_not_lock(schedules):
    run = schedules[3]
    events = [e for e in run.trace if e["action"] == "L36/polka/2/Y"]
    assert any(e["state"][2]["lock"] == [NIL, -1] and
               e["state"][2]["valid"] == ["Y", 1] for e in events)


def test_actual_valid_round_proof_needed(schedules):
    run = schedules[3]
    w, _ = run.checkpoints["justified_proposal"]
    n = w.nodes[0]
    assert run.model.weight(n, "prevote", 1, "Y") == Q
    assert any(a == "L28/prevote/0/Y" for a, _ in run.model.successors(w))
    n = replace(n, log=frozenset(m for m in n.log if not (m.kind == "prevote" and m.round == 1)))
    assert not any(a.startswith("L28/prevote/0/") for a, _ in run.model.successors(run.model.put(w, n)))


def test_stale_justification_cannot_override_newer_different_lock(schedules):
    # Guard-level unit fixture, explicitly not a reachable-execution seed.
    run = schedules[3]
    w, _ = run.checkpoints["justified_proposal"]
    n = replace(w.nodes[0], locked="X", lr=2)
    after = next(after for a, after in run.model.successors(run.model.put(w, n))
                 if a == "L28/prevote/0/Y")
    assert Message("prevote", 1, 2, 0, NIL) in after.sent


def test_equal_lock_round_is_accepted_by_line_29(schedules):
    run = schedules[3]
    w, _ = run.checkpoints["justified_proposal"]
    # Equality matters: use <= as printed, not the paper's informal > wording.
    n = replace(w.nodes[0], locked="X", lr=1)
    after = next(after for a, after in run.model.successors(run.model.put(w, n))
                 if a == "L28/prevote/0/Y")
    assert Message("prevote", 1, 2, 0, "Y") in after.sent


def test_late_old_round_decision_after_advance(schedules):
    run = schedules[5]
    assert run.node(1).decisions[0].proposal.round == 0
    assert run.trace[-2]["state"][1]["r"] == 1


@pytest.mark.parametrize("field", ["protocol", "canonical", "original", "admission", "transactions", "resources"])
def test_abstract_validity_component_rejected(field):
    b = replace(Block("X"), **{field: False})
    model = Model(Config(blocks=(b,)))
    assert model.validity(model.initial().nodes[0], "X") is False
    assert not model.objective_valid("X", 1, "genesis")


def test_correct_parent_height_and_unknown_data_are_distinct():
    m = Model()
    assert not m.objective_valid("X", 2, "genesis")
    assert not m.objective_valid("X", 1, "other-finalized-parent")
    assert m.validity(m.initial().nodes[0], "not-delivered") is None
    m = Model(Config(decoder_unavailable=frozenset({0})))
    assert m.objective_valid("X", 1, "genesis")
    assert m.validity(m.initial().nodes[0], "X") is None


@pytest.mark.parametrize("mutation", [
    {"sender": 4}, {"authentic": False}, {"context": ("wrong-net", *CONTEXT[1:])},
    {"context": (CONTEXT[0], "wrong-genesis", *CONTEXT[2:])},
    {"context": (*CONTEXT[:2], "wrong-membership", *CONTEXT[3:])},
    {"context": (*CONTEXT[:3], "wrong-policy", *CONTEXT[4:])},
    {"context": (*CONTEXT[:4], 1, 1)}, {"context": (*CONTEXT[:5], 2)},
    {"parent": "conflicting-finalized-parent"},
])
def test_wrong_context_unauthorized_or_forged_message_cannot_count(mutation):
    m = Model()
    w = m.initial()
    v = replace(Message("precommit", 1, 0, 3, "X"), **mutation)
    assert m.deliver(w, 0, v) == w
    assert m.weight(w.nodes[0], "precommit", 0, "X") == 0


def test_duplicate_and_equivocated_byzantine_messages_count_one_identity():
    m = Model()
    w = m.initial()
    for v in (NIL, "X", "Y", "X", NIL):
        w = m.deliver(w, 0, Message("prevote", 1, 0, 3, v))
    assert m.weight(w.nodes[0], "prevote", 0) == 1
    assert m.weight(w.nodes[0], "prevote", 0, "X") == 1
    assert m.deliver(w, 0, Message("prevote", 1, 0, 3, "X")) == w
    assert not any(a.startswith("L34/arm/0") for a, _ in m.successors(w))


def test_one_byzantine_cannot_force_round_catchup_by_multiple_phases():
    r = Run()
    r.start()
    for kind in ("prevote", "precommit"):
        m = r.send_bad(kind, r=5)
        r.deliver(0, m)
    assert not enabled(r, "L55/catchup/0/")


def test_quorum_of_nil_precommits_does_not_decide():
    r = Run()
    r.start()
    n = r.node(0)
    # Guard fixture: authenticated votes, no Byzantine power inflation.
    n = replace(n, log=n.log | frozenset(Message("precommit", 1, 0, i) for i in (0, 1, 3)))
    assert not any(a.startswith("L49/decide/0") for a, _ in r.model.successors(r.model.put(r.w, n)))


@pytest.mark.parametrize("availability", ["unknown_proposal", "incomplete_data", "decoder_unavailable"])
def test_qc_alone_cannot_decide_contents(availability):
    r = Run(Config(decoder_unavailable=frozenset({0}) if availability == "decoder_unavailable" else frozenset()))
    r.start()
    n = r.node(0)
    p = Message("proposal", 1, 0, 0, "X")
    votes = frozenset(Message("precommit", 1, 0, i, "X") for i in (0, 1, 3))
    n = replace(n, log=votes | ({p} if availability != "unknown_proposal" else set()),
                data=frozenset() if availability == "incomplete_data" else n.data)
    assert not any(a.startswith("L49/decide/0") for a, _ in r.model.successors(r.model.put(r.w, n)))


def test_stale_timers_do_not_sign_or_advance(schedules):
    r = schedules[2]
    n = r.node(1)
    assert any(h == 1 and round == 1 for h, round, _ in n.timers)
    assert n.round == 2
    assert not any(a.startswith("L61/timeout/1") for a, _ in r.model.successors(r.w))


def test_once_guards_and_timer_arming(schedules):
    w, _ = schedules[2].checkpoints["two_honest_X_locks"]
    model = schedules[2].model
    assert not any(a.startswith("L36/polka/0/") for a, _ in model.successors(w))
    # Armed PC wait requires quorum; a plain timer request is never enabled.
    m = Model()
    w = m.initial()
    assert not any("/timeout/" in a for a, _ in m.successors(w))


def test_two_consecutive_heights_use_decided_parent_and_reset_lock(schedules):
    case = next(c for c in schedules[0] if c["name"] == "consecutive_heights_finalized_parents")
    assert all(len(n["decisions"]) == 2 and n["lock"] == [NIL, -1] for n in case["final"])
    for event in case["trace"]:
        assert not event["violations"]


def test_fault_budget_and_collision_free_identifier_assumptions():
    with pytest.raises(ValueError):
        Config(byzantine=frozenset({2, 3}))
    with pytest.raises(ValueError):
        Config(blocks=(Block("X"), Block("X", parent="other")))


def test_checker_detects_mutated_proofs_and_decisions(schedules):
    run = schedules[2]
    w = run.w
    n = run.node(0)
    d = n.decisions[0]
    bad_votes = frozenset(replace(v, sender=4) for v in d.votes)
    bad_d = replace(d, value="unknown", parent="other", votes=bad_votes)
    errors = invariant_errors(run.model, run.model.put(w, replace(n, decisions=(bad_d,))))
    assert {"B:invalid_decision", "D:finalized_ancestry", "E:unauthorized_certificate",
            "H:inflated_quorum", "F:unavailable_decision", "F:missing_proposal"} <= set(errors)


def test_checker_detects_honest_double_vote_and_unlock(schedules):
    run = schedules[2]
    w = run.w
    m = run.message("prevote", 1, "X", 0)
    forged = World(w.nodes, w.sent | {replace(m, value="Y")})
    assert "C:honest_conflicting_slot" in invariant_errors(run.model, forged)
    n = replace(run.node(1), locked=NIL, lr=-1)
    assert "G:unsupported_lock_change" in edge_errors(w, run.model.put(w, n), "nil-timeout")


def test_bfs_counts_deterministically_and_exposes_cutoffs():
    m = Model(Config(max_height=1, max_round=0))
    a = explore(m, m.initial(), depth=2, state_limit=10000)
    b = explore(m, m.initial(), depth=2, state_limit=10000)
    assert {k: v for k, v in a.items() if k != "runtime_seconds"} == {
        k: v for k, v in b.items() if k != "runtime_seconds"}
    assert a["exhausted_configured_depth"] and a["depth_boundary_states"] > 0
    capped = explore(m, m.initial(), depth=3, state_limit=2)
    assert capped["state_cap_reached"] and not capped["exhausted_configured_depth"]
    assert capped["states"] == 2


def test_bfs_detects_invalid_initial_state(schedules):
    run = schedules[2]
    n = replace(run.node(1), locked=NIL, lr=-1)
    d = replace(run.node(0).decisions[0], value="invalid")
    w = run.model.put(run.w, replace(n, decisions=(d,)))
    result = explore(run.model, w, depth=1, state_limit=20)
    assert result["result"] == "COUNTEREXAMPLE"


def test_negative_controls_are_not_correct_reference_executions(schedules):
    negative = schedules[1][1]
    with pytest.raises(ValueError):
        replay(negative)
    r = replay(negative, allow_negative=True)
    assert "A:honest_disagreement" in r.violations
    assert any(e["outside_reference"] for e in r.trace)


def test_all_schedules_replay_and_tamper_is_detected(schedules):
    for case in schedules[0] + schedules[1]:
        r = replay(case, allow_negative=case["expected"] == "counterexample_required")
        assert r.result(case["name"])["final_digest"] == case["final_digest"]
    case = json.loads(json.dumps(schedules[0][0]))
    case["trace"][0]["digest"] = "0" * 64
    with pytest.raises(ValueError, match="diverges"):
        replay(case)


def test_retained_results_match_sources_and_all_trace_prefixes_replay():
    root = Path(__file__).resolve().parents[1] / "verification" / "tendermint717h"
    summary = json.loads((root / "results" / "summary.json").read_text(encoding="utf-8"))
    for name, expected in summary["source_sha256"].items():
        assert hashlib.sha256((root / name).read_bytes()).hexdigest() == expected
    for path in sorted((root / "results").glob("trace-*.json")):
        case = json.loads(path.read_text(encoding="utf-8"))
        replay(case, allow_negative=case["expected"] == "counterexample_required")
    for search in summary["searches"]:
        seed = json.loads((root / "results" / f"seed-{search['name']}.json").read_text(encoding="utf-8"))
        run = replay(seed)
        assert digest(run.w) == search["seed_digest"]
        assert jsonable(run.w) == seed["state"]
