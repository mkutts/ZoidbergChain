# Task 7.22 final original-scope audit evidence

Read [the final report](../../docs/milestone-7-final-economics-and-acceptance-review.md).
Original milestone **INCOMPLETE**; production activation **BLOCKED**.

From the repository root, use the existing pinned Windows environment:

```powershell
.\.venv\Scripts\python.exe -B verification/task722/run.py replay
.\.venv\Scripts\python.exe -B verification/task722/run.py tests
.\.venv\Scripts\python.exe -B verification/task722/reconcile.py
.\.venv\Scripts\python.exe -B verification/task722/economics.py
.\.venv\Scripts\python.exe -B verification/task722/report.py
.\.venv\Scripts\python.exe -B verification/task722/crosscheck.py
```

No install, network request, WAL initializer or production database is needed.
The existing strict Windows workers and Pillow/native encoders are required.
Reference versions are in `preflight.json`. Every subprocess has a 600-second
bound. Replay inputs must match frozen manifests exactly; only timings and
worker process/resource observations are excluded from exact result comparisons.
The runner stores full transient outputs under unique ignored `temp/task722-*`
paths; only 30-line log tails, argv/exit/elapsed records, compact comparisons and
the fresh 128-record recovery evidence are retained here. Original raw codec,
record, physical SQLite and economic evidence remains tracked at its old paths.

`reconcile.py` independently checks old per-field integer ledgers/percentiles,
reproduces the natural 104-to-105-byte raw expansion, and compares tracked/fresh
bridge claims with frozen original hashes, sizes and codec choices.
`economics.py` produces fully capacity-priced **illustrative** scenarios from
exact measured means; `crosscheck.py` independently recomputes their bills with
Decimal arithmetic without importing that simulator. Its tolerances concern
floating-point expectations, not corpus hashes or integer serialization bytes.

`economic_inputs.json`, `cost_formulas.json` and `pricing_review.json` state all
units, day counts, source classes, dates, unspecified regions, formula and tier
limitations. `economic_scenarios.json` retains 27 base cases (nine each on the
original historical projection, frozen-v3 historical corpus, and new corpus);
`sensitivity_scenarios.json` has 171 one-axis and 27 best/reference/stress cases.
`historical_economics.json` preserves all 27 historical uncorrected scenarios;
it must not be cited as fully loaded. The $100 test is month-36 **monthly** cost.

`acceptance_matrix.json` separates original requirements, readiness and minimum
remaining acceptance work. It grants no owner exception or activation approval.
Per-group outcome files retain every pytest ID, skip and deselection;
`test_summary.json` reports disjoint totals and exact excluded IDs/reasons.

`preflight.json` captures the genuinely clean starting state and hashes every
preexisting tracked file. `preservation.json` checks those hashes, HEAD/branch and
the unchanged index after writes; expected new audit files remain untracked.
`checksums.sha256` covers the report and this evidence bundle except itself;
rerun the final crosscheck after intentional changes to these new deliverables.
No staging or commit is performed. Initial runner-error evidence is retained
separately and earns no complete-replay credit. No other task is begun.
