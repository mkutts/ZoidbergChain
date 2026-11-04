"""Executable transition relation for arXiv:1807.04938v3, Algorithm 1.

Pure standard library. Symbolic authentication, unit voting power, collision-free
value IDs, and atomic upon rules are assumptions, not implemented cryptography.
Line numbers below refer to the algorithm's printed numbers, not PDF text lines.
"""
from dataclasses import dataclass, replace
from typing import Iterator

N, F, Q = 4, 1, 3
NIL = ""
CONTEXT = ("model-network", "model-genesis", "static-0123", "algorithm1-v3", 0, 1)


@dataclass(frozen=True, order=True)
class Block:
    id: str
    height: int = 1
    parent: str = "genesis"
    protocol: bool = True
    canonical: bool = True
    original: bool = True
    admission: bool = True
    transactions: bool = True
    resources: bool = True


@dataclass(frozen=True, order=True)
class Message:
    kind: str
    height: int
    round: int
    sender: int
    value: str = NIL
    vr: int = -1
    parent: str = "genesis"
    context: tuple = CONTEXT
    authentic: bool = True

    def label(self):
        return f"{self.kind}:{self.height}:{self.round}:{self.sender}:{self.value or 'nil'}:{self.vr}"


@dataclass(frozen=True)
class Decision:
    height: int
    value: str
    parent: str
    proposal: Message
    votes: frozenset[Message]


@dataclass(frozen=True)
class Node:
    identity: int
    height: int = 1  # Project's genesis anchor offset; paper starts its instance at 0.
    round: int = 0
    phase: str = "propose"
    started: bool = False
    locked: str = NIL
    lr: int = -1
    valid: str = NIL
    vr: int = -1
    log: frozenset[Message] = frozenset()
    timers: frozenset[tuple] = frozenset()
    once: frozenset[tuple] = frozenset()
    data: frozenset[str] = frozenset()
    decisions: tuple[Decision, ...] = ()

    @property
    def parent(self):
        return self.decisions[-1].value if self.decisions else "genesis"


@dataclass(frozen=True)
class World:
    nodes: tuple[Node, ...]
    sent: frozenset[Message] = frozenset()


@dataclass(frozen=True)
class Config:
    blocks: tuple[Block, ...] = (Block("X"), Block("Y"))
    byzantine: frozenset[int] = frozenset({3})
    offline: frozenset[int] = frozenset()
    max_height: int = 2
    max_round: int = 5  # Inclusive; enabled rounds beyond this are search cutoffs.
    missing: frozenset[tuple[int, str]] = frozenset()
    retrievable: frozenset[str] = frozenset({"X", "Y", "XX", "YY"})
    decoder_unavailable: frozenset[int] = frozenset()
    broken_locking: bool = False  # Negative control ONLY.

    def __post_init__(self):
        if not self.byzantine <= frozenset(range(N)) or len(self.byzantine) > F:
            raise ValueError("primary model permits at most one Byzantine identity")
        if len({b.id for b in self.blocks}) != len(self.blocks):
            raise ValueError("value IDs must be injective")


class Model:
    def __init__(self, config=Config()):
        self.c = config
        self.blocks = {b.id: b for b in config.blocks}

    @staticmethod
    def proposer(height, round):
        return (height - 1 + round) % N

    def initial(self):
        return World(tuple(Node(i, data=frozenset(b.id for b in self.c.blocks
                         if (i, b.id) not in self.c.missing))
                           for i in range(N) if i not in self.c.byzantine))

    def authenticated(self, m):
        return (m.authentic and m.sender in range(N) and m.context == CONTEXT
                and m.kind in {"proposal", "prevote", "precommit"}
                and m.height >= 1 and m.round >= 0
                and (m.kind != "proposal" or
                     (m.value != NIL and -1 <= m.vr < m.round and
                      m.sender == self.proposer(m.height, m.round))))

    def objective_valid(self, value, height, parent):
        b = self.blocks.get(value)
        return bool(b and b.height == height and b.parent == parent and
                    b.protocol and b.canonical and b.original and b.admission and
                    b.transactions and b.resources)

    def validity(self, n, value):
        """None means local incomplete/unavailable, distinct from invalid bytes."""
        if value not in n.data or n.identity in self.c.decoder_unavailable:
            return None
        return self.objective_valid(value, n.height, n.parent)

    def relevant(self, n, m):
        return self.authenticated(m) and m.height == n.height and m.parent == n.parent

    def votes(self, n, kind, round, value=None):
        # None = wildcard; NIL = genuine nil. Equivocation never adds sender weight.
        return frozenset(m for m in n.log if self.relevant(n, m) and m.kind == kind
                         and m.round == round and (value is None or m.value == value))

    def weight(self, n, kind, round, value=None):
        return len({m.sender for m in self.votes(n, kind, round, value)})

    def proposals(self, n, round=None):
        return sorted(m for m in n.log if m.kind == "proposal" and self.relevant(n, m)
                      and (round is None or m.round == round))

    @staticmethod
    def put(w, n, sent=()):
        return World(tuple(n if x.identity == n.identity else x for x in w.nodes),
                     w.sent | frozenset(sent))

    def emit(self, n, kind, value=NIL, vr=-1):
        m = Message(kind, n.height, n.round, n.identity, value, vr, n.parent)
        return replace(n, log=n.log | {m}), m

    def start(self, n, round):
        """L11-21. Branch over valid getValue() choices; retain locks/valid state."""
        n = replace(n, round=round, phase="propose", started=True)
        if self.proposer(n.height, round) != n.identity:
            yield replace(n, timers=n.timers | {(n.height, round, "propose")}), ()
            return
        values = [n.valid] if n.valid else [b.id for b in self.c.blocks
                                          if self.validity(n, b.id) is True]
        if not values:
            # Environment lacks getValue's required input; no fabricated block.
            yield n, ()
        for value in values:
            updated, m = self.emit(n, "proposal", value, n.vr)
            yield updated, (m,)

    def local(self, w, n) -> Iterator[tuple[str, World]]:
        if not n.started:
            for updated, messages in self.start(n, 0):
                value = messages[0].value if messages else "none"
                yield f"L10/start/{n.identity}/{value}", self.put(w, updated, messages)
            return
        h, r, i = n.height, n.round, n.identity
        proposals = self.proposals(n, r)
        # L22-33: proof is actual logged prevotes, never a claimed vr alone.
        if n.phase == "propose":
            for p in proposals:
                justified = p.vr >= 0 and self.weight(n, "prevote", p.vr, p.value) >= Q
                if p.vr != -1 and not justified:
                    continue
                valid = self.validity(n, p.value)
                if valid is None:
                    continue
                lock_ok = ((n.lr == -1 or n.locked == p.value) if p.vr == -1
                           else (n.lr <= p.vr or n.locked == p.value))
                value = p.value if valid and (lock_ok or self.c.broken_locking) else NIL
                updated, m = self.emit(n, "prevote", value)
                yield f"L{'22' if p.vr == -1 else '28'}/prevote/{i}/{p.value}", self.put(
                    w, replace(updated, phase="prevote"), (m,))
        # L34-35 and L47-48: once per height/round; distinct sender wildcard tally.
        for kind, phase, line in (("prevote", "prevote", "34"),
                                  ("precommit", None, "47")):
            flag = (h, r, kind)
            if (flag not in n.once and (phase is None or n.phase == phase)
                    and self.weight(n, kind, r) >= Q):
                updated = replace(n, once=n.once | {flag}, timers=n.timers | {flag})
                yield f"L{line}/arm/{i}", self.put(w, updated)
        # L36-43: may learn validValue in precommit, but only lock in prevote.
        flag = (h, r, "polka")
        if n.phase in {"prevote", "precommit"} and flag not in n.once:
            for p in proposals:
                if self.validity(n, p.value) is True and self.weight(n, "prevote", r, p.value) >= Q:
                    updated = replace(n, valid=p.value, vr=r, once=n.once | {flag})
                    messages = ()
                    if n.phase == "prevote":
                        updated = replace(updated, locked=p.value, lr=r, phase="precommit")
                        updated, m = self.emit(updated, "precommit", p.value)
                        messages = (m,)
                    yield f"L36/polka/{i}/{p.value}", self.put(w, updated, messages)
        if n.phase == "prevote" and self.weight(n, "prevote", r, NIL) >= Q:
            updated, m = self.emit(n, "precommit")
            yield f"L44/nil/{i}", self.put(w, replace(updated, phase="precommit"), (m,))
        # L49-54: r need not be current round. Store decision proof before reset.
        for p in self.proposals(n):
            if self.validity(n, p.value) is True and self.weight(n, "precommit", p.round, p.value) >= Q:
                d = Decision(h, p.value, n.parent, p, self.votes(n, "precommit", p.round, p.value))
                updated = replace(n, height=h+1, round=0, phase="propose", started=False,
                                  locked=NIL, lr=-1, valid=NIL, vr=-1, log=frozenset(),
                                  once=frozenset(), decisions=n.decisions + (d,))
                if updated.height <= self.c.max_height:
                    for started, messages in self.start(updated, 0):
                        yield f"L49/decide/{i}/{p.value}", self.put(w, started, messages)
                else:
                    yield f"L49/decide/{i}/{p.value}", self.put(w, updated)
        # L55-56: f+1 distinct senders at the SAME higher round, any message type.
        for future in sorted({m.round for m in n.log if self.relevant(n, m)
                              and r < m.round <= self.c.max_round}):
            if len({m.sender for m in n.log if self.relevant(n, m) and m.round == future}) >= F+1:
                for updated, messages in self.start(n, future):
                    yield f"L55/catchup/{i}/{future}", self.put(w, updated, messages)
        # L57-67: only previously armed, current-context timers can act.
        for th, tr, kind in sorted(n.timers):
            if (th, tr) != (h, r):
                continue  # Expiring a stale timer is a stutter.
            if kind in {"propose", "prevote"} and n.phase == kind:
                phase = "prevote" if kind == "propose" else "precommit"
                updated, m = self.emit(n, phase)
                yield f"L{'57' if kind == 'propose' else '61'}/timeout/{i}", self.put(
                    w, replace(updated, phase=phase), (m,))
            if kind == "precommit" and r < self.c.max_round:
                for updated, messages in self.start(n, r+1):
                    yield f"L65/timeout/{i}/{r+1}", self.put(w, updated, messages)

    def deliver(self, w, identity, m):
        n = next(x for x in w.nodes if x.identity == identity)
        if identity in self.c.offline or not self.relevant(n, m):
            return w  # Authenticated context/parent admission before counting.
        return self.put(w, replace(n, log=n.log | {m}))

    def byzantine_messages(self, w):
        """Finite alphabet, arbitrary equivocation/withholding; no honest forgery."""
        for h in sorted({n.height for n in w.nodes if n.height <= self.c.max_height}):
            for r in range(self.c.max_round+1):
                for parent in sorted({n.parent for n in w.nodes if n.height == h}):
                    values = [NIL] + [b.id for b in self.c.blocks if b.height == h]
                    for i in sorted(self.c.byzantine):
                        for kind in ("prevote", "precommit", "proposal"):
                            if kind == "proposal" and self.proposer(h, r) != i:
                                continue
                            for value in values:
                                if kind == "proposal" and not value:
                                    continue
                                for vr in (range(-1, r) if kind == "proposal" else (-1,)):
                                    yield Message(kind, h, r, i, value, vr, parent)

    def successors(self, w, *, adversary=True):
        for n in w.nodes:
            if n.identity in self.c.offline or n.height > self.c.max_height:
                continue
            yield from self.local(w, n)
            for m in sorted(w.sent):
                if m not in n.log and self.relevant(n, m):
                    yield f"deliver/{n.identity}/{m.label()}", self.deliver(w, n.identity, m)
            for p in self.proposals(n):
                if p.value not in n.data and p.value in self.c.retrievable:
                    yield f"fetch/{n.identity}/{p.value}", self.put(w, replace(n, data=n.data | {p.value}))
        if adversary:
            for m in self.byzantine_messages(w):
                if m not in w.sent:
                    yield f"byzantine/{m.label()}", World(w.nodes, w.sent | {m})


def invariant_errors(model, w):
    """Independent history/proof checks. Returns named violations, not assert-only."""
    errors = set()
    by_height = {}
    slots = {}
    for m in w.sent:
        if m.sender in model.c.byzantine:
            continue
        slot = (m.sender, m.height, m.round, m.kind)
        slots.setdefault(slot, set()).add(m)
        signer = next(n for n in w.nodes if n.identity == m.sender)
        prior = next((d for d in signer.decisions if d.height == m.height-1), None)
        if (m.height == 1 and m.parent != "genesis") or (m.height > 1 and
                (prior is None or prior.value != m.parent)):
            errors.add("D:signature_without_finalized_parent")
    if any(len(messages) > 1 for messages in slots.values()):
        errors.add("C:honest_conflicting_slot")
    for n in w.nodes:
        parent = "genesis"
        for expected, d in enumerate(n.decisions, 1):
            by_height.setdefault(d.height, set()).add(d.value)
            if not model.objective_valid(d.value, d.height, d.parent):
                errors.add("B:invalid_decision")
            if d.height != expected or d.parent != parent:
                errors.add("D:finalized_ancestry")
            parent = d.value
            p = d.proposal
            if (not model.authenticated(p) or p.kind != "proposal" or
                    (p.height, p.value, p.parent) != (d.height, d.value, d.parent)):
                errors.add("F:missing_proposal")
            if any(not model.authenticated(v) or v.kind != "precommit" or
                   (v.height, v.round, v.value, v.parent) !=
                   (d.height, p.round, d.value, d.parent) for v in d.votes):
                errors.add("E:unauthorized_certificate")
            if len({v.sender for v in d.votes}) < Q:
                errors.add("H:inflated_quorum")
            if d.value not in n.data:
                errors.add("F:unavailable_decision")
        if n.valid:
            if model.weight(n, "prevote", n.vr, n.valid) < Q or not any(
                    p.round == n.vr and p.value == n.valid for p in model.proposals(n)):
                errors.add("valid_value_without_evidence")
    if any(len(values) > 1 for values in by_height.values()):
        errors.add("A:honest_disagreement")
    return sorted(errors)


def edge_errors(before, after, action):
    """G plus the atomic lock-before-release obligation at the transition boundary."""
    errors = set()
    for old, new in zip(before.nodes, after.nodes):
        if old.height != new.height:
            continue
        if (old.locked, old.lr) != (new.locked, new.lr) and not action.startswith("L36/polka/"):
            errors.add("G:unsupported_lock_change")
        for m in after.sent - before.sent:
            if m.sender == new.identity and m.kind == "precommit" and m.value:
                if (new.locked, new.lr) != (m.value, m.round):
                    errors.add("lock_not_atomic_with_precommit")
    return sorted(errors)
