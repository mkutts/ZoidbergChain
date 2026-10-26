"""Deterministic schedules, all positive steps use the executable relation.

No seeded synthetic honest locks or fabricated honest votes. Checkpoints for
bounded exploration are prefixes of these replayable executions.
"""
from dataclasses import replace
import hashlib
import json

from .model import (Block, Config, CONTEXT, Message, Model, NIL, World,
                    edge_errors, invariant_errors)


def jsonable(value):
    if hasattr(value, "__dataclass_fields__"):
        return {k: jsonable(v) for k, v in value.__dict__.items()}
    if isinstance(value, (set, frozenset)):
        return sorted((jsonable(v) for v in value), key=lambda x: json.dumps(x, sort_keys=True))
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    return value


def digest(w):
    return hashlib.sha256(json.dumps(jsonable(w), sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def snapshot(w):
    return [dict(id=n.identity, h=n.height, r=n.round, phase=n.phase,
                 lock=[n.locked, n.lr], valid=[n.valid, n.vr],
                 decisions=[d.value for d in n.decisions]) for n in w.nodes]


class Run:
    def __init__(self, config=Config()):
        self.model = Model(config)
        self.w = self.model.initial()
        self.trace = []
        self.violations = set()
        self.states = {self.w}
        self.checkpoints = {}

    def record(self, action, after, *, invalid_recovery=False):
        errors = invariant_errors(self.model, after) + edge_errors(self.w, after, action)
        self.violations.update(errors)
        self.trace.append(dict(action=action, digest=digest(after), state=snapshot(after),
                               violations=errors, outside_reference=invalid_recovery))
        self.w = after
        self.states.add(after)

    def step(self, prefix, *, contains=None):
        for action, after in self.model.successors(self.w):
            if action.startswith(prefix) and (contains is None or contains in action):
                self.record(action, after)
                return
        raise AssertionError(f"disabled action {prefix!r} {contains!r}; {snapshot(self.w)}")

    def node(self, i):
        return next(n for n in self.w.nodes if n.identity == i)

    def message(self, kind, i, value=NIL, r=None, h=1):
        return next(m for m in sorted(self.w.sent) if m.kind == kind and m.sender == i
                    and m.value == value and m.height == h and (r is None or m.round == r))

    def send_bad(self, kind, value=NIL, r=0, vr=-1, h=1, parent="genesis"):
        i = next(iter(self.model.c.byzantine))
        m = Message(kind, h, r, i, value, vr, parent)
        assert m in set(self.model.byzantine_messages(self.w))
        if m not in self.w.sent:
            self.record("byzantine/" + m.label(), World(self.w.nodes, self.w.sent | {m}))
        return m

    def deliver(self, i, m):
        assert m in self.w.sent
        after = self.model.deliver(self.w, i, m)
        self.record(f"deliver/{i}/{m.label()}", after)

    def start(self, values=None):
        for n in self.w.nodes:
            if n.identity not in self.model.c.offline:
                value = (values or {}).get(n.identity)
                self.step(f"L10/start/{n.identity}/" + (value or ""))

    def mark(self, name):
        self.checkpoints[name] = (self.w, list(self.trace))

    def settle(self, *, recipients=None, excluded_kinds=(), max_steps=1000):
        """Controlled synchronous segment: drain rules/messages before any timer.

        Preference is one selected schedule, NOT a fairness or liveness proof.
        It models gossip by delivering every released message, including Byzantine
        messages received elsewhere, to all connected honest recipients.
        """
        for _ in range(max_steps):
            choices = self.model.successors(self.w, adversary=False)
            chosen = None
            for action, after in choices:
                if "/timeout/" in action:
                    continue
                if action.startswith("deliver/"):
                    bits = action.split("/")
                    if recipients is not None and int(bits[1]) not in recipients:
                        continue
                    if bits[2].split(":")[0] in excluded_kinds:
                        continue
                chosen = (action, after)
                break
            if chosen is None:
                return
            self.record(*chosen)
        raise AssertionError("controlled schedule did not quiesce within bound")

    def result(self, name, expected="safe"):
        return dict(name=name, expected=expected, config=jsonable(self.model.c),
                    unique_states=len(self.states), transitions=len(self.trace),
                    violations=sorted(self.violations), final=snapshot(self.w),
                    final_digest=digest(self.w), trace=list(self.trace))


def hidden_commit(config=Config(max_height=1, max_round=2), *, unsafe_restart=False):
    """A decides X, B's X lock is hidden from C; B/C/D later try Y at round 2."""
    run = Run(config)
    run.start({0: "X"})
    p = run.message("proposal", 0, "X", 0)
    run.deliver(1, p)
    for i in (0, 1):
        run.step(f"L22/prevote/{i}/X")
    bad = run.send_bad("prevote", "X")
    for i in (0, 1):
        for j in (0, 1):
            run.deliver(i, run.message("prevote", j, "X", 0))
        run.deliver(i, bad)
        run.step(f"L36/polka/{i}/X")
    run.mark("two_honest_X_locks")
    badpc = run.send_bad("precommit", "X")
    for j in (0, 1):
        run.deliver(0, run.message("precommit", j, "X", 0))
    run.deliver(0, badpc)
    run.step("L49/decide/0/X")
    run.mark("hidden_X_decision")
    # B,C catch up to r1 using two honest-independent identities, C's timeout nil
    # plus D's r1 vote; B doesn't send a second round-0 vote.
    run.step("L57/timeout/2")
    # Advance C through r0 with B's PC(X) and D PC(nil), enough wildcard weight.
    badnil = run.send_bad("precommit")
    run.deliver(2, run.message("precommit", 1, "X", 0))
    run.deliver(2, badnil)
    # C needs its own PC(nil); get q PV(any), then expire its armed PV timer.
    for j in (0, 1):
        run.deliver(2, run.message("prevote", j, "X", 0))
    run.step("L34/arm/2")
    run.step("L61/timeout/2")
    run.step("L47/arm/2")
    run.step("L65/timeout/2/1")
    badr1 = run.send_bad("prevote", r=1)
    # C times out in r1, furnishing f+1 senders for B's catchup.
    run.step("L57/timeout/2")
    run.deliver(1, run.message("prevote", 2, NIL, 1))
    run.deliver(1, badr1)
    run.step("L55/catchup/1/1")
    # B honestly re-proposes X with vr0. C receives no proposal. B still votes X.
    run.step("L28/prevote/1/X")
    for i in (1, 2):
        run.deliver(i, run.message("prevote", 1, "X", 1))
        run.deliver(i, run.message("prevote", 2, NIL, 1))
        run.deliver(i, badr1)
        run.step(f"L34/arm/{i}")
        run.step(f"L61/timeout/{i}")
    pc = run.send_bad("precommit", r=1)
    for i in (1, 2):
        for j in (1, 2):
            run.deliver(i, run.message("precommit", j, NIL, 1))
        run.deliver(i, pc)
        run.step(f"L47/arm/{i}")
    run.mark("nil_did_not_unlock")
    if unsafe_restart:
        # Deliberate fault injection, NOT an enabled rule of the correct model.
        n = run.node(1)
        run.record("FAULT/lost_signer_lock_and_valid/1", run.model.put(run.w,
                   replace(n, locked=NIL, lr=-1, valid=NIL, vr=-1)), invalid_recovery=True)
    else:
        # Identity on immutable safety state abstracts a restart with exact replay.
        run.record("restart/intact/1", run.w)
    run.step("L65/timeout/1/2")
    # Select C's fresh getValue Y (start has two possible outputs).
    choices = [(a, w) for a, w in run.model.successors(run.w)
               if a.startswith("L65/timeout/2/2") and
               any(m.kind == "proposal" and m.sender == 2 and m.round == 2 and m.value == "Y"
                   for m in w.sent - run.w.sent)]
    assert choices
    run.record(*choices[0])
    run.deliver(1, run.message("proposal", 2, "Y", 2))
    run.step("L22/prevote/1/Y")
    run.step("L22/prevote/2/Y")
    pv = run.send_bad("prevote", "Y", r=2)
    for i in (1, 2):
        for j in (1, 2):
            val = "Y" if config.broken_locking or unsafe_restart or j == 2 else NIL
            run.deliver(i, run.message("prevote", j, val, 2))
        run.deliver(i, pv)
    run.mark("attempt_conflicting_Y")
    if config.broken_locking or unsafe_restart:
        for i in (1, 2):
            run.step(f"L36/polka/{i}/Y")
        pc = run.send_bad("precommit", "Y", r=2)
        for j in (1, 2):
            run.deliver(2, run.message("precommit", j, "Y", 2))
        run.deliver(2, pc)
        run.step("L49/decide/2/Y")
        assert "A:honest_disagreement" in run.violations
    else:
        assert run.node(1).locked == "X" and not run.node(2).decisions
        assert not run.violations
    return run


def different_locks():
    """One X lock, then a Y polka without its holder, then justified switch."""
    r = Run(Config(max_height=1))
    r.start({0: "X"})
    for i in (1, 2):
        r.deliver(i, r.message("proposal", 0, "X", 0))
    for i in (0, 1, 2):
        r.step(f"L22/prevote/{i}/X")
    for j in (1, 2):
        r.deliver(0, r.message("prevote", j, "X", 0))
    r.step("L36/polka/0/X")
    # B,C see wildcard PV, but no full proposal+polka rule is selected before timeout.
    for i in (1, 2):
        for j in (0, 1, 2):
            r.deliver(i, r.message("prevote", j, "X", 0))
        r.step(f"L34/arm/{i}")
        r.step(f"L61/timeout/{i}")
    pc = r.send_bad("precommit")
    for i in (0, 1, 2):
        for j in (1, 2):
            r.deliver(i, r.message("precommit", j, NIL, 0))
        r.deliver(i, pc)
        r.step(f"L47/arm/{i}")
    # B proposes fresh Y; A will nil, but B/C/D form Y PV without A.
    for i in (0, 1, 2):
        choices = [(a, w) for a, w in r.model.successors(r.w)
                   if a.startswith(f"L65/timeout/{i}/1") and (i != 1 or
                       any(m.kind == "proposal" and m.value == "Y" and m.round == 1
                           for m in w.sent - r.w.sent))]
        r.record(*choices[0])
    p = r.message("proposal", 1, "Y", 1)
    for i in (0, 2):
        r.deliver(i, p)
    for i in (0, 1, 2):
        r.step(f"L22/prevote/{i}/Y")
    badpv = r.send_bad("prevote", "Y", r=1)
    for i in (1, 2):
        for j in (1, 2):
            r.deliver(i, r.message("prevote", j, "Y", 1))
        r.deliver(i, badpv)
    r.step("L36/polka/1/Y")
    r.mark("different_honest_locks")
    assert r.node(0).locked == "X" and r.node(1).locked == "Y"
    # C precommits nil before learning Y validValue late in precommit.
    r.step("L34/arm/2")
    r.step("L61/timeout/2")
    r.step("L36/polka/2/Y")
    assert r.node(2).locked == NIL and r.node(2).valid == "Y"
    pc = r.send_bad("precommit", r=1)
    for i in (0, 1, 2):
        r.deliver(i, r.message("precommit", 1, "Y", 1))
        r.deliver(i, r.message("precommit", 2, NIL, 1))
        r.deliver(i, pc)
        r.step(f"L47/arm/{i}")
    for i in (0, 1, 2):
        r.step(f"L65/timeout/{i}/2")
    p = r.message("proposal", 2, "Y", 2)
    r.deliver(0, p)
    # Claim alone cannot enable L28. Actual old-round prevotes are necessary.
    assert not any(a.startswith("L28/prevote/0") for a, _ in r.model.successors(r.w))
    for j in (1, 2):
        r.deliver(0, r.message("prevote", j, "Y", 1))
    r.deliver(0, badpv)
    r.mark("justified_proposal")
    r.step("L28/prevote/0/Y")
    assert r.node(0).locked == "X"  # A prevote alone does not replace the lock.
    r.settle()
    assert all(n.decisions and n.decisions[0].value == "Y" for n in r.w.nodes)
    assert not r.violations
    return r


def reach_byzantine_round_three(config=Config(max_height=1, max_round=4)):
    """Reach Byzantine proposer r3 by withholding all earlier proposal deliveries."""
    r = Run(config)
    r.start({0: "X"})
    for round in range(3):
        for i in (0, 1, 2):
            # Proposer has its own value, others see no proposal.
            if i == r.model.proposer(1, round):
                r.step(f"L22/prevote/{i}/")
            else:
                r.step(f"L57/timeout/{i}")
        for i in (0, 1, 2):
            for j in (0, 1, 2):
                m = next(m for m in r.w.sent if m.kind == "prevote" and m.sender == j
                         and m.height == 1 and m.round == round)
                r.deliver(i, m)
            r.step(f"L34/arm/{i}")
            r.step(f"L61/timeout/{i}")
        for i in (0, 1, 2):
            for j in (0, 1, 2):
                r.deliver(i, r.message("precommit", j, NIL, round))
            r.step(f"L47/arm/{i}")
            r.step(f"L65/timeout/{i}/{round+1}")
    r.mark("byzantine_proposer_round3")
    return r


def round_three_equivocation():
    r = reach_byzantine_round_three()
    px = r.send_bad("proposal", "X", r=3)
    py = r.send_bad("proposal", "Y", r=3)
    r.deliver(0, px)
    r.deliver(1, py)
    r.deliver(2, px)
    r.step("L22/prevote/0/X")
    r.step("L22/prevote/1/Y")
    r.step("L22/prevote/2/X")
    pvx = r.send_bad("prevote", "X", r=3)
    r.send_bad("prevote", "Y", r=3)
    r.send_bad("precommit", "Y", r=3)
    r.mark("equivocating_proposer_split")
    r.deliver(0, pvx)
    r.deliver(0, r.message("prevote", 2, "X", 3))
    r.step("L36/polka/0/X")
    r.settle()
    assert not r.violations
    return r


def invalid_byzantine_proposal():
    r = reach_byzantine_round_three(Config(blocks=(Block("X"), Block("Y"),
                                            Block("BAD", canonical=False)), max_height=1, max_round=4))
    proposal = r.send_bad("proposal", "BAD", r=3)
    for i in (0, 1, 2):
        r.deliver(i, proposal)
        r.step(f"L22/prevote/{i}/BAD")
        assert r.message("prevote", i, NIL, 3)
    r.settle()
    assert not any(n.decisions for n in r.w.nodes)
    assert not r.violations
    return r


def unavailable_proposal_qc():
    r = Run(Config(max_height=1, missing=frozenset({(2, "X")})))
    r.start({0: "X"})
    r.deliver(1, r.message("proposal", 0, "X", 0))
    for i in (0, 1):
        r.step(f"L22/prevote/{i}/X")
    pv = r.send_bad("prevote", "X")
    for i in (0, 1):
        for j in (0, 1):
            r.deliver(i, r.message("prevote", j, "X", 0))
        r.deliver(i, pv)
        r.step(f"L36/polka/{i}/X")
    pc = r.send_bad("precommit", "X")
    for j in (0, 1):
        r.deliver(2, r.message("precommit", j, "X", 0))
    r.deliver(2, pc)
    assert not any(a.startswith("L49/decide/2") for a, _ in r.model.successors(r.w))
    r.mark("qc_without_proposal")
    r.deliver(2, r.message("proposal", 0, "X", 0))
    assert not any(a.startswith("L49/decide/2") for a, _ in r.model.successors(r.w))
    r.mark("qc_without_data")
    r.step("fetch/2/X")
    r.step("L49/decide/2/X")
    assert not r.violations
    return r


def controlled(config, *, rounds=3):
    r = Run(config)
    r.start()
    r.settle()
    for _ in range(rounds):
        # Before GST/as failures require, allow one timer then drain gossip.
        choice = next(((a, w) for a, w in r.model.successors(r.w, adversary=False)
                       if "/timeout/" in a), None)
        if choice is None:
            break
        r.record(*choice)
        r.settle()
    assert not r.violations
    return r
