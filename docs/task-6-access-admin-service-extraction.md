# Task 6 Access/Admin Service Extraction

## Inventory

`Blockchain` delegates the following record transitions while retaining their
public signatures and return values: refresh access state; allowlist lookup,
list, matching, create, update, revoke, and reactivate; override lookup, list,
create, and update-status; access request/account/binding lookup and lists;
request create/approve/reject; invite create/resolve; login tracking; wallet
binding create/count/list/revoke; account status update; audit append/list; and
feedback lookup/list/summary/create/update/note.

The access service reads/mutates only `access_requests`, `access_accounts`,
`wallet_bindings`, `allowlist_entries`, `override_requests`, and `audit_logs`.
The feedback service reads/mutates only `feedback_records`. All are serialized
under identically named sections by `Blockchain._serialize_blockchain_state` and
loaded by the existing storage paths. Helper dependencies are the existing
access-code hash/generation, text/email/handle normalization, UTC timestamps,
and wallet normalization functions. IDs remain `secrets.token_hex(16)` except
feedback-note IDs (`token_hex(12)`); timestamps remain `utc_now_iso()`.

List behavior is unchanged: allowlist/override/feedback/audit lists sort latest
update or timestamp first; access request/account/binding lists preserve stored
order; existing filters retain normalization and inclusive timestamp behavior.
Exceptions remain `ValueError` with the existing messages.

API routes retain the facade calls in `api.py`; `scripts/access_admin.py`,
`access_control.py`, `ops_support.py`, and storage tests also retain their
existing attributes/method calls. Direct collection access is preserved on
`Blockchain` for API serializers, scripts, tests, storage, and access policy.

## Deliberate Boundaries

`access_control.access_decision_for_wallet` remains outside this extraction: it
implements policy/configuration decisions, including development bypass and
feature gates, and calls the compatibility facade. `admin_auth.py` keeps admin
session authentication. Reward-pool calculation adjacent to the extracted
block remains in `Blockchain` because it is consensus/ledger-adjacent.

## Persistence And Security

Services are stateless and receive explicit state views referencing the
facade-owned lists. They do not save storage, avoiding recursive or hidden
persists. Whole-document JSON and SQLite behavior, missing-section defaults,
backup, atomic writes, and corruption handling are unchanged.

No service serializes API responses or sessions. Invite hashes remain stored
but are exposed only through existing safe serializers; services return the
same internal records only to the existing facade/API orchestration. Access
mode, limits, invite hashing, override policy, audit event recording, and
public/admin separation remain unchanged.

## Evidence

`tests/services/test_access_admin_services.py` directly characterizes
normalization, allowlist lifecycle/matching, access approval/rejection/invites,
login and wallet-limit behavior, override transitions, feedback lifecycle, and
audit sorting. Existing API and storage tests remain the compatibility proof.
