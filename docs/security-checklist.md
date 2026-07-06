# ZoidbergChain Security Checklist

## Environment settings

- `ENVIRONMENT=development` is for local work only.
- `ENVIRONMENT=testnet` and `ENVIRONMENT=production` must be treated as public-facing modes.
- `PUBLIC_API_MODE=true` should be enabled for any public deployment.
- Never deploy a public server with `ENVIRONMENT=development` or `PUBLIC_API_MODE=false`.

## Private key exposure

- Public API responses must never include `private_key`, `privateKey`, `signing_key`, `seed`, `secret`, or raw key material.
- Private key export is only allowed in development when `ALLOW_DEV_WALLET_PRIVATE_KEY_EXPORT=true`.
- Dev wallet export endpoints must remain blocked in testnet and production.

## Dev endpoints

- `/dev/*` endpoints are development-only.
- `/dev/*` endpoints must be blocked in testnet and production.
- `/dev/*` endpoints must also be blocked when `PUBLIC_API_MODE=true`.
- Dev reset and debug routes must never be exposed on a public node.

## Peer authentication

- Peer receive/register routes require shared-secret auth when `REQUIRE_PEER_AUTH=true`.
- Signed peer messages are required when `ENABLE_SIGNED_PEER_MESSAGES=true`.
- Shared secrets must never be logged or returned in responses.
- Testnet and production must use a non-default `PEER_SHARED_SECRET`.

## Signed peer messages

- Signed peer requests must include the expected headers and body hash.
- Expired timestamps, replayed nonces, and invalid signatures must be rejected.
- Public read endpoints must not require peer auth or signed headers.

## Rate limiting

- Rate limiting is disabled by default in development.
- Rate limiting is enabled in testnet and production.
- Write-heavy endpoints should be tighter than read endpoints.
- Peer sync and peer receive routes should remain usable for normal node operation.

## Logging

- Do not log private keys, secrets, seed phrases, or raw signatures.
- Do not log full request URLs if query strings can contain sensitive values.
- Prefer short public-key or address fragments when a reference is needed in logs.

## Known remaining limitations

- Wallet private keys are still stored server-side for local development workflows.
- Full client-side signing is not implemented yet.
- There is no independent public/private node identity key infrastructure yet.
- Shared-secret peer auth is acceptable for controlled environments, but not ideal for open public networks.
- There is no formal third-party security audit yet.
- Secret management still relies on environment configuration rather than a dedicated production secret manager.

## Before public deployment

- Set `ENVIRONMENT=production`.
- Set `PUBLIC_API_MODE=true`.
- Set `REQUIRE_PEER_AUTH=true`.
- Set `ENABLE_RATE_LIMITING=true`.
- Use a real `PEER_SHARED_SECRET`.
- Confirm `/dev/*` routes are blocked.
- Confirm no public endpoint returns private key material or raw secrets.
- Confirm logs do not include request secrets or private keys.
