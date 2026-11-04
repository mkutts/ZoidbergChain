# Task 7.21 verification artifacts

See [the integration report](../../docs/milestone-7-disabled-compression-integration.md).
This directory is never imported by active code and exposes no public route.
All DBs are disposable; no canonical DB binary or new signing keys are retained.

- `bridge.py`: explicit exact-byte construction, independent provisional validation,
  safe DELETE/EXTRA initialization and original-media retrieval.
- `exercise.py`, `recover.py`: 70 format + 58 real-admission records; 128
  fresh-process recoveries, no recompression or cache dependence.
- `test_bridge.py`, `crash.py`: hostile inputs, actual upload-service boundary,
  actual process exits, canonical-only repair and attempted accidental activation.
- `reconcile.py`: frozen 78-record byte/evidence ledger, comparable 70-unique-object
  accounting; no changes to Task 7.20.
- `run.py`: bounded corpus/test runner (`tests --group NAME` supports focused replay).
- `finalize.py`: cross-check identities/choices against Task 7.20, disjoint test
  totals, readiness gates, preservation inventory and checksums.
- `summary.json`, `end_to_end.json`, `reconciliation.json`: machine-readable results.
- `*_outcomes.json`, `*_tests.txt`, `tests_execution.json`: exact final tests/skips.
  The `active` files and `initial_tests_execution.json` retain the preliminary
  75-pass selection that inadvertently configured WAL on an empty test DB solely
  to verify backend refusal. Final `active_safe` excludes it; see
  `initial_attempts.json`. Earlier overlapping passes are not added to final totals.
- `prerequisites.json`, `preservation.json`, `checksums.sha256`: tracked source
  preservation and new evidence inventory.

Run from the repository root with `.venv/Scripts/python.exe -B`:

```powershell
.\.venv\Scripts\python.exe -B verification/task721/run.py corpus
.\.venv\Scripts\python.exe -B verification/task721/run.py tests
.\.venv\Scripts\python.exe -B verification/task721/finalize.py
```

The initial corpus exercise was launched directly (its native workers and
fresh-process child were bounded); `run.py corpus` additionally bounds the
overall parent at 900 seconds for replay. Decoders retain their unchanged
individual resource limits. New results are local Windows evidence; Linux
containment, native security audit and activation authority remain unestablished.
