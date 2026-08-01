# Public Demo Deployment Checklist

Use this checklist before exposing the Stage 1 public demo.

- `ENVIRONMENT=testnet` or equivalent production-like demo mode is set.
- `PUBLIC_API_MODE=true` is set.
- `PUBLIC_DEMO_MODE=true` is set.
- dev tools are disabled.
- private key export is disabled.
- reset endpoints are disabled.
- signature bypass is disabled.
- fake/dev voting and multi-account helpers are disabled.
- rate limits are enabled.
- upload limits are enabled.
- strict MIME validation is enabled.
- CORS is restricted to the intended frontend origins.
- HTTPS is configured.
- `VITE_API_BASE_URL` points to the intended public API origin.
- `NODE_DATA_DIR`, `CONTENT_STORAGE_DIR`, and `LOG_DIR` are configured.
- `STORAGE_BACKEND` and `SQLITE_DB_PATH` are configured intentionally if SQLite is used.
- backups for chain state and content storage are configured.
- `GET /health` passes with safe fields only.
- `GET /node-info` and `GET /chain/summary` pass with safe fields only.
- frontend build passes.
- backend tests pass.
- two-node native transfer test passes.
- the public demo disclaimer is visible in the UI.
- the old `/wallets/...` compatibility reads were checked and return safe read-only data.
