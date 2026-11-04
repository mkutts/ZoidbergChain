"""Independent deterministic replay of exported action traces.

python -B -m verification.tendermint717h.replay path/to/trace.json
Negative controls require --allow-negative-controls and remain outside the
reference model. Recomputes transitions, digests and invariant reports.
"""
import argparse
from dataclasses import replace
import json
from pathlib import Path

from .model import Block, Config, NIL
from .scenarios import Run, digest


def decode_config(value):
    value = dict(value)
    value["blocks"] = tuple(Block(**b) for b in value["blocks"])
    for field in ("byzantine", "offline", "retrievable", "decoder_unavailable"):
        value[field] = frozenset(value[field])
    value["missing"] = frozenset(tuple(pair) for pair in value["missing"])
    return Config(**value)


def replay(document, *, allow_negative=False):
    config = decode_config(document["config"])
    if config.broken_locking and not allow_negative:
        raise ValueError("negative control requires explicit opt-in")
    run = Run(config)
    for index, event in enumerate(document["trace"]):
        action = event["action"]
        chosen = None
        for name, after in run.model.successors(run.w):
            if name == action and digest(after) == event["digest"]:
                chosen = after
                break
        if chosen is None and action.startswith("deliver/"):
            # Already-delivered duplicates are exact stutters, omitted by BFS.
            _, target, label = action.split("/", 2)
            m = next((m for m in run.w.sent if m.label() == label), None)
            if m is not None:
                chosen = run.model.deliver(run.w, int(target), m)
        if chosen is None and action == "restart/intact/1":
            chosen = run.w
        if action == "FAULT/lost_signer_lock_and_valid/1":
            if not allow_negative or not event["outside_reference"]:
                raise ValueError("lost safety state is not an honest reference transition")
            chosen = run.model.put(run.w, replace(run.node(1), locked=NIL, lr=-1, valid=NIL, vr=-1))
        if chosen is None or digest(chosen) != event["digest"]:
            raise ValueError(f"trace diverges at event {index}: {action}")
        run.record(action, chosen, invalid_recovery=event["outside_reference"])
        if run.trace[-1]["violations"] != event["violations"]:
            raise ValueError(f"invariant report differs at event {index}")
    if "final_digest" in document and digest(run.w) != document["final_digest"]:
        raise ValueError("final digest mismatch")
    return run


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("trace", type=Path)
    p.add_argument("--allow-negative-controls", action="store_true")
    args = p.parse_args()
    r = replay(json.loads(args.trace.read_text(encoding="utf-8")), allow_negative=args.allow_negative_controls)
    print(json.dumps(dict(replayed_transitions=len(r.trace), violations=sorted(r.violations), digest=digest(r.w))))


if __name__ == "__main__":
    main()
