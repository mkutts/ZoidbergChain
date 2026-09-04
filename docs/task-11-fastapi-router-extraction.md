# Task 11: FastAPI Router And Thin-Adapter Extraction

Date: 2026-09-03

## Scope And Compatibility

This change is a behavior-preserving Milestone 2 refactor. It does not alter
protocol v1, genesis, consensus, finality, storage, signing, peer messages,
content rules, nonce/replay policy, rewards, or any public HTTP contract.

`api.py` remains the supported `uvicorn api:app` entry point. It aliases the
assembled runtime module so existing callers and tests that replace
`api.blockchain`, session managers, peer stores, configuration values, or peer
authentication helpers still replace the values read by handlers.

The frozen contract remains 129 application routes plus FastAPI's four built-in
documentation routes. The existing `tests/fixtures/api_route_contract.json` was
accurate and was not changed.

## Route Ownership

| Router | Routes | Owned responsibilities |
|---|---:|---|
| `api_routers.public_chain` | 5 | Public chain download, summary, block listing, block media, legacy sync read |
| `api_routers.access` | 16 | Feedback, access requests/sessions/binding, eligibility, wallet authentication challenges and sessions, review policy |
| `api_routers.admin` | 29 | Admin session, access lifecycle, allowlist, overrides, feedback administration, audit and privileged ops |
| `api_routers.content` | 20 | Content upload/read, submissions, originality votes and certificates, evaluation, voter views, mint queue and mint blocking |
| `api_routers.native` | 23 | Native transfer submission/read, account and wallet ledger views, mempool, nonce, transaction admission and reward-pool views |
| `api_routers.peer` | 20 | Peer registration/receipt/read, authenticated peer chain/content endpoints, broadcasts, chain sync and content sync |
| `api_routers.operations` | 16 | Static information pages, health/status, development reset/debug/wallet tools, legacy direct block operation and repair tools |

The peer router owns 20 routes by responsibility; 12 of those are classified as
authenticated peer routes by the frozen contract, while its public broadcast and
synchronization initiators retain their existing public/access behavior. The
operations router similarly keeps all nine routes classified as development-only
separate from its seven public status/static routes. Admin lifecycle routes are
not mixed into either public router.

## Router And Service Boundary

Task 11A corrected the public-chain (5), access (16), and admin (29) domains.
Task 11B gives the content (20) and native (23) modules concrete FastAPI
endpoint definitions. Task 11C completes the peer (20) and operations (16)
modules, so all seven routers now retain their original
signatures, dependencies, request parsing, status/error mapping, and response
serialization, while their mutations call named `Blockchain` facade operations.
The facades coordinate persistence and delegate content/submission/originality
to Task 7, native ledger/mempool/rewards to Task 8, and the applicable minting
transition through the established Task 9 facade.

`api_runtime.py` now retains only application construction, schemas,
dependencies, middleware, CORS, rate limits, lifespan behavior, compatibility
globals, serializers, and narrow support helpers. It defines no endpoint
handlers and performs no endpoint-owned persistence or state transitions.

`Blockchain` remains the authoritative state owner and whole-document
persistence facade. Access/admin/feedback, content/submission/originality/mint
queue, native ledger/mempool/reward, consensus/finality, and peer networking
decisions remain in the services extracted by Tasks 6-10. Existing save timing
and facade calls were deliberately retained because changing them would alter
transactional behavior and is outside Task 11.

The resulting dependency direction is:

`api -> api_runtime + api_routers -> Blockchain/peer_sync -> services`

Services import neither the application runtime nor router modules. Router
modules do not call persistence, consensus, signing, or state-transition APIs.

## Preserved Details

- All 129 application paths, methods, names, order, prefixes, and slash behavior.
- Request parameters and aliases, Pydantic models, dependencies, declared status
  codes, response behavior, and error details.
- Public, admin, peer, access-controlled, and development authorization rules.
- CORS, middleware, exception handlers, rate limits, lifespan, and OpenAPI.
- `api:app`, direct `api_runtime` import, and `importlib.reload(api)` behavior.
- Test monkeypatch seams for chain state, peer stores, authentication managers,
  configuration switches, time, hashing, and signing helpers.
- Model A immutable media, native ZOID settlement, peer payload verification,
  and every Task 6-10 service boundary.

`api.py` is reduced from 6,913 lines to 45 lines. After Task 11C,
`api_runtime.py` is 2,900 physical lines. The seven explicit routers contain
all 129 application routes: 36 final peer/operations routes joined the 93
already extracted by Tasks 11A and 11B.
