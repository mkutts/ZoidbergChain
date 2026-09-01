# Protocol v1 UI/Backend Audit

Date: 2026-08-29

## Audit summary

- Critical: 0
- High: 6
- Medium: 6
- Low: 3
- Runtime behavior changed during UI-1: No

## 1. Frontend architecture

- Frontend root: `zoidbergcoin-ui/`
- Framework: Vue 3 (`vue@^3.5.13`)
- Build tool: Vite 6 with `@vitejs/plugin-vue`
- Routing: Vue Router 4, with `/dashboard`, `/submit`, `/vote`, `/rewards`, `/activity`, `/help`, `/feedback`, `/why-zoidbergcoin`, and `/admin`
- State management: singleton reactive services and component-local state; no Pinia/Vuex store
- API client layer: `src/config/api.js` with `apiClient`, `publicApiClient`, and `adminApiClient`
- Wallet integration: `src/services/wallet.js` for MetaMask connection, verification challenge flow, and Bearer auth propagation
- Native transfer signing: `src/services/nativeTransfer.js`
- Access gating: `src/services/access.js` plus `src/components/ControlledAccessGate.vue`
- Major user-facing pages/components:
  - `src/pages/HomePage.vue`
  - `src/pages/Dashboard.vue`
  - `src/pages/Blockchain.vue`
  - `src/components/WalletPanel.vue`
  - `src/pages/AdminPage.vue`
- Generated/static artifacts committed separately:
  - `zoidbergcoin-ui/dist/`
  - `zoidbergcoin-ui/zoidbergchain-dist.zip`
  - `static/index.html`

Observations:

- The Vue source is the authoritative frontend.
- The backend root route still serves `static/index.html`, not the Vue app.
- `zoidbergcoin-ui/dist/` appears to be a current Vue build.
- `zoidbergcoin-ui/zoidbergchain-dist.zip` appears unrelated to the current Vue app and should not be treated as trustworthy deployment output.

## 2. Backend API surface used by UI

| Method | Route | Public/Admin/Peer | Request model | Response model | UI caller(s) |
| --- | --- | --- | --- | --- | --- |
| POST | `/auth/wallet/challenge` | Public | `WalletChallengeRequest` | wallet login challenge with `message`, `issued_at`, `expires_at` | `src/services/wallet.js` |
| POST | `/auth/wallet/verify` | Public | `WalletVerifyRequest` | verified wallet session payload | `src/services/wallet.js` |
| GET | `/auth/wallet/session` | Public | Bearer auth | current wallet session payload | `src/services/wallet.js` |
| POST | `/auth/wallet/logout` | Public | Bearer auth | logout result | `src/services/wallet.js` |
| POST | `/auth/wallet/submission-challenge` | Public | `WalletSubmissionChallengeRequest` | signed-submission challenge | `src/pages/Dashboard.vue` |
| POST | `/submit_content` | Public | multipart signed submission form | serialized submission plus broadcast result | `src/pages/Dashboard.vue` |
| POST | `/content/upload` | Public | multipart upload | public content metadata with `download_url` | `src/pages/Dashboard.vue` |
| POST | `/content/text` | Public | `TextContentUpload` | public content metadata with `download_url` | `src/pages/Dashboard.vue` |
| POST | `/content/{content_hash}/sync` | Dev/ops | path param | sync result plus content metadata | `src/pages/Dashboard.vue` |
| GET | `/content/{content_hash}/metadata` | Public | path param | safe content metadata | `src/pages/Dashboard.vue` |
| GET | `/chain/summary` | Public | none | chain summary including `protocol_version`, `network_id`, `genesis_hash`, `canonical_genesis_hash`, `cumulative_originality_score` | `src/pages/Dashboard.vue`, `src/pages/Blockchain.vue` |
| GET | `/chain` | Public | none | full serialized selected chain | `src/pages/Dashboard.vue`, `src/pages/Blockchain.vue` |
| GET | `/submissions` | Public | optional `status` | serialized submissions list | `src/pages/Dashboard.vue` |
| GET | `/submissions/{submission_id}/certificate` | Public | path param | serialized originality certificate | `src/pages/Dashboard.vue` |
| GET | `/submissions/{submission_id}/votes` | Public | path param | vote summary for submission | `src/pages/Dashboard.vue` |
| POST | `/auth/wallet/vote-challenge` | Public | `WalletVoteChallengeRequest` | Protocol v1 vote challenge | `src/pages/Dashboard.vue` |
| POST | `/submissions/{submission_id}/vote` | Public | multipart signed vote form | recorded vote plus broadcast result | `src/pages/Dashboard.vue` |
| GET | `/mint-queue` | Public | query flags | mint queue entries | `src/pages/Dashboard.vue` |
| POST | `/submissions/{submission_id}/evaluate` | Dev/admin | multipart | evaluation result, submission, certificate, voter reward summary | `src/pages/Dashboard.vue` |
| POST | `/mint/{submission_id}` | Dev/admin | optional form `miner` | minted block result | `src/pages/Dashboard.vue` |
| POST | `/submissions/{submission_id}/block-minting` | Dev/admin | `MintBlockRequest` | updated submission | `src/pages/Dashboard.vue` |
| POST | `/submissions/{submission_id}/unblock-minting` | Dev/admin | path param | updated submission | `src/pages/Dashboard.vue` |
| POST | `/auth/wallet/transfer-challenge` | Public | `WalletTransferChallengeRequest` | Protocol v1 transfer challenge with preview | `src/services/nativeTransfer.js` |
| POST | `/transfers/submit` | Public | `WalletTransferSubmitRequest` | serialized transfer/native transaction record | `src/services/nativeTransfer.js` |
| GET | `/accounts/{wallet_address}` | Public | path param | native account summary | `src/components/WalletPanel.vue` |
| GET | `/accounts/{wallet_address}/rewards` | Public | path param | reward history | `src/components/WalletPanel.vue` |
| GET | `/accounts/{wallet_address}/transactions` | Public | path param | canonical native transaction history | `src/components/WalletPanel.vue` |
| GET | `/accounts/{wallet_address}/nonce` | Public | path param | nonce state | `src/components/WalletPanel.vue` |
| GET | `/mempool` | Dev/ops | none | local mempool transaction list | `src/components/WalletPanel.vue` |
| POST | `/transactions/{tx_id}/admit` | Dev/ops | path param | mempool admission result | `src/components/WalletPanel.vue` |
| POST | `/feedback` | Public | feedback payload | feedback record plus message | `src/services/feedback.js` |
| GET | `/access/status` | Public | none | public access config | `src/services/access.js` |
| GET | `/access/me` | Public | Bearer and optional `X-ZOID-Access-Session` | access/account/wallet binding snapshot | `src/services/access.js` |
| GET | `/eligibility/status` | Public | Bearer and optional `X-ZOID-Access-Session` | access and review eligibility snapshot | `src/services/access.js` |
| POST | `/access/request` | Public | `AccessRequestCreate` | access request result | `src/services/access.js` |
| POST | `/access/login` | Public | `AccessLoginRequest` | invite login result with `access_session_token` | `src/services/access.js` |
| POST | `/access/bind-wallet` | Public | no body; auth headers only | wallet binding result | `src/services/access.js` |
| POST | `/eligibility/override-requests` | Public | override request payload | override request result | `src/services/access.js` |
| GET | `/admin/session` | Admin | cookie-auth | admin session state | `src/services/admin.js` |
| POST | `/admin/login` | Admin | `AdminLoginRequest` | admin session start | `src/services/admin.js` |
| POST | `/admin/logout` | Admin | cookie-auth | admin session end | `src/services/admin.js` |
| GET | `/admin/access/requests` | Admin | query `status` | access request list | `src/services/admin.js` |
| POST | `/admin/access/requests/{request_id}/approve` | Admin | approval payload | invite/access response | `src/services/admin.js` |
| POST | `/admin/access/requests/{request_id}/reject` | Admin | rejection payload | request result | `src/services/admin.js` |
| POST | `/admin/access/invites` | Admin | invite payload | invite result | `src/services/admin.js` |
| GET | `/admin/access/accounts` | Admin | query `status` | access account list | `src/services/admin.js` |
| GET | `/admin/access/accounts/{access_account_id}` | Admin | path param | access account detail | `src/services/admin.js` |
| POST | `/admin/access/accounts/{access_account_id}/{action}` | Admin | action path | access account status result | `src/services/admin.js`, `src/pages/AdminPage.vue` |
| POST | `/admin/access/wallet-bindings/{wallet_address}/revoke` | Admin | path param | wallet binding revoke result | `src/services/admin.js` |
| GET | `/admin/allowlist` | Admin | query params | allowlist list | `src/services/admin.js` |
| POST | `/admin/allowlist` | Admin | create payload | allowlist result | `src/services/admin.js` |
| PATCH | `/admin/allowlist/{allowlist_entry_id}` | Admin | patch payload | allowlist update result | `src/services/admin.js` |
| POST | `/admin/allowlist/{allowlist_entry_id}/revoke` | Admin | revoke payload | allowlist revoke result | `src/services/admin.js` |
| POST | `/admin/allowlist/{allowlist_entry_id}/reactivate` | Admin | reactivate payload | allowlist reactivate result | `src/services/admin.js` |
| GET | `/admin/override-requests` | Admin | query `status` | override request list | `src/services/admin.js` |
| POST | `/admin/override-requests/{override_request_id}/approve` | Admin | approval payload | override approval result | `src/services/admin.js` |
| POST | `/admin/override-requests/{override_request_id}/reject` | Admin | rejection payload | override rejection result | `src/services/admin.js` |
| GET | `/admin/feedback` | Admin | filter query | feedback list plus summary | `src/services/admin.js` |
| GET | `/admin/feedback/{feedback_id}` | Admin | path param | feedback detail | `src/services/admin.js` |
| PATCH | `/admin/feedback/{feedback_id}` | Admin | update payload | feedback update result | `src/services/admin.js` |
| POST | `/admin/feedback/{feedback_id}/status` | Admin | status payload | feedback status result | `src/services/admin.js` |
| POST | `/admin/feedback/{feedback_id}/note` | Admin | note payload | feedback note result | `src/services/admin.js` |
| GET | `/admin/ops/status` | Admin | none | operator health/status snapshot | `src/services/admin.js` |
| GET | `/admin/audit-log` | Admin | query `limit` | admin audit log list | `src/services/admin.js` |
| POST | `/generate_wallet` | Dev/ops | none | development-only wallet result | `src/pages/HomePage.vue` |

## 3. Frontend API calls

| Frontend file/function | Method | Endpoint | Request fields | Expected response fields |
| --- | --- | --- | --- | --- |
| `src/services/wallet.js:createChallenge` | POST | `/auth/wallet/challenge` | `wallet_address` | `message`, `issued_at`, `expires_at` |
| `src/services/wallet.js:verifyChallenge` | POST | `/auth/wallet/verify` | `wallet_address`, `message`, `signature` | `session_token`, `expires_at`, `normalized_wallet_address` |
| `src/services/wallet.js:getSession` | GET | `/auth/wallet/session` | Bearer auth | `valid`, `expires_at`, `normalized_wallet_address` |
| `src/services/wallet.js:logout` | POST | `/auth/wallet/logout` | Bearer auth | `logged_out`, `message` |
| `src/services/access.js:loadPublicStatus` | GET | `/access/status` | none | public access config |
| `src/services/access.js:refreshMe` | GET | `/access/me` | Bearer auth, `X-ZOID-Access-Session` | access/account/wallet binding snapshot |
| `src/services/access.js:refreshEligibility` | GET | `/eligibility/status` | Bearer auth, `X-ZOID-Access-Session` | eligibility snapshot |
| `src/services/access.js:submitAccessRequest` | POST | `/access/request` | `name`, `email`, `handle`, `reason`, `notes` | `message` and request snapshot |
| `src/services/access.js:loginWithCode` | POST | `/access/login` | `access_code` | `access_session_token`, `message` |
| `src/services/access.js:bindWallet` | POST | `/access/bind-wallet` | auth headers only | `message`, access snapshot |
| `src/services/access.js:submitOverrideRequest` | POST | `/eligibility/override-requests` | `requested_scope`, `reason` plus auth headers | `message`, request snapshot |
| `src/services/feedback.js:submitFeedback` | POST | `/feedback` | feedback payload | `message`, `feedback` |
| `src/services/nativeTransfer.js:submitSignedTransferIntent` | POST | `/auth/wallet/transfer-challenge` | `from_address`, `to_address`, `amount`, `fee`, `memo` | `message`, `transaction_version`, `protocol_version`, `network_id`, `nonce` |
| `src/services/nativeTransfer.js:submitSignedTransferIntent` | POST | `/transfers/submit` | `from_address`, `to_address`, `amount`, `fee`, `memo`, `message`, `signature` | transfer/native transaction record, `tx_id`, `nonce`, `status` |
| `src/pages/HomePage.vue:generateWallet` | POST | `/generate_wallet` | none | dev wallet payload |
| `src/pages/Dashboard.vue:uploadSubmissionContent` | POST | `/content/upload` | multipart `file`, `submitted_by`, optional `caption` | content metadata, `download_url`, `storage_status` |
| `src/pages/Dashboard.vue:uploadSubmissionContent` | POST | `/content/text` | `text_content`, `submitted_by`, `caption` | content metadata, `download_url`, `storage_status` |
| `src/pages/Dashboard.vue:syncContent` | POST | `/content/{content_hash}/sync` | path param | sync result, `content` |
| `src/pages/Dashboard.vue:syncContent` | GET | `/content/{content_hash}/metadata` | path param | safe content metadata |
| `src/pages/Dashboard.vue:submitContent` | POST | `/auth/wallet/submission-challenge` | `wallet_address`, `content_hash`, `content_id`, `caption` | `message`, `issued_at`, `expires_at` |
| `src/pages/Dashboard.vue:submitContent` | POST | `/submit_content` | multipart `wallet_address`, `content_hash`, optional `content_id`, `message`, `signature` | `message`, serialized `submission` |
| `src/pages/Dashboard.vue:fetchChainSummary` | GET | `/chain/summary` | none | chain summary |
| `src/pages/Dashboard.vue:fetchSubmissions` | GET | `/submissions` | none | `submissions` |
| `src/pages/Dashboard.vue:fetchMintQueue` | GET | `/mint-queue` | query `include_blocked=true` | `mint_queue` |
| `src/pages/Dashboard.vue:fetchBlocks` | GET | `/chain` | none | `chain` |
| `src/pages/Dashboard.vue:fetchCertificate` | GET | `/submissions/{submission_id}/certificate` | path param | `certificate` |
| `src/pages/Dashboard.vue:fetchVotes` | GET | `/submissions/{submission_id}/votes` | path param | vote summary |
| `src/pages/Dashboard.vue:vote` | POST | `/auth/wallet/vote-challenge` | `wallet_address`, `submission_id`, `vote` | `message`, `vote_version`, `protocol_version`, `network_id`, `issued_at`, `expires_at` |
| `src/pages/Dashboard.vue:vote` | POST | `/submissions/{submission_id}/vote` | multipart `wallet_address`, `vote_type`, `message`, `signature` | `message`, `vote` |
| `src/pages/Dashboard.vue:evaluateSubmission` | POST | `/submissions/{submission_id}/evaluate` | multipart `automated_originality_passed=true` | `submission`, `certificate`, `voter_reward_summary` |
| `src/pages/Dashboard.vue:mintSubmission` | POST | `/mint/{submission_id}` | path param | `block`, `block_hash`, `reward_amount`, `transaction_ids` |
| `src/pages/Dashboard.vue:blockMinting` | POST | `/submissions/{submission_id}/block-minting` | `reason`, `notes` | `submission`, `message` |
| `src/pages/Dashboard.vue:unblockMinting` | POST | `/submissions/{submission_id}/unblock-minting` | path param | `submission`, `message` |
| `src/pages/Blockchain.vue:fetchChainSummary` | GET | `/chain/summary` | none | chain summary |
| `src/pages/Blockchain.vue:fetchChain` | GET | `/chain` | none | `chain` |
| `src/components/WalletPanel.vue:refreshAccountSummary` | GET | `/accounts/{wallet_address}` | path param | account summary |
| `src/components/WalletPanel.vue:refreshRewardHistory` | GET | `/accounts/{wallet_address}/rewards` | path param | `rewards` |
| `src/components/WalletPanel.vue:refreshTransferHistory` | GET | `/accounts/{wallet_address}/transactions` | path param | `transactions` |
| `src/components/WalletPanel.vue:refreshNonceState` | GET | `/accounts/{wallet_address}/nonce` | path param | nonce state |
| `src/components/WalletPanel.vue:refreshMempool` | GET | `/mempool` | none | mempool `transactions` |
| `src/components/WalletPanel.vue:admitTransferToMempool` | POST | `/transactions/{tx_id}/admit` | path param | admission result |
| `src/services/admin.js:loadSession` | GET | `/admin/session` | cookie-auth | admin session |
| `src/services/admin.js:login` | POST | `/admin/login` | `password` | admin session |
| `src/services/admin.js:logout` | POST | `/admin/logout` | none | logout/session state |
| `src/services/admin.js:loadRequests` | GET | `/admin/access/requests` | query `status` | `requests` |
| `src/services/admin.js:approveRequest` | POST | `/admin/access/requests/{request_id}/approve` | `reviewed_by`, `max_wallets`, `notes` | invite/access result |
| `src/services/admin.js:rejectRequest` | POST | `/admin/access/requests/{request_id}/reject` | rejection note payload | request result |
| `src/services/admin.js:createInvite` | POST | `/admin/access/invites` | direct invite payload | invite result |
| `src/services/admin.js:loadAccounts` | GET | `/admin/access/accounts` | query `status` | `accounts` |
| `src/services/admin.js:loadAccountDetail` | GET | `/admin/access/accounts/{access_account_id}` | path param | account detail |
| `src/services/admin.js:updateAccountStatus` | POST | `/admin/access/accounts/{access_account_id}/{action}` | optional notes | account status result |
| `src/services/admin.js:revokeWalletBinding` | POST | `/admin/access/wallet-bindings/{wallet_address}/revoke` | optional reason | wallet binding result |
| `src/services/admin.js:loadAllowlist` | GET | `/admin/allowlist` | scope/subject/status filters | `allowlist_entries` |
| `src/services/admin.js:createAllowlistEntry` | POST | `/admin/allowlist` | allowlist payload | allowlist result |
| `src/services/admin.js:updateAllowlistEntry` | PATCH | `/admin/allowlist/{allowlist_entry_id}` | patch payload | allowlist result |
| `src/services/admin.js:revokeAllowlistEntry` | POST | `/admin/allowlist/{allowlist_entry_id}/revoke` | revoke payload | allowlist result |
| `src/services/admin.js:reactivateAllowlistEntry` | POST | `/admin/allowlist/{allowlist_entry_id}/reactivate` | reactivate payload | allowlist result |
| `src/services/admin.js:loadOverrideRequests` | GET | `/admin/override-requests` | query `status` | `override_requests` |
| `src/services/admin.js:approveOverrideRequest` | POST | `/admin/override-requests/{override_request_id}/approve` | approval payload | override result |
| `src/services/admin.js:rejectOverrideRequest` | POST | `/admin/override-requests/{override_request_id}/reject` | rejection payload | override result |
| `src/services/admin.js:loadFeedback` | GET | `/admin/feedback` | filter query | feedback list plus summary |
| `src/services/admin.js:loadFeedbackDetail` | GET | `/admin/feedback/{feedback_id}` | path param | feedback detail |
| `src/services/admin.js:updateFeedback` | PATCH | `/admin/feedback/{feedback_id}` | feedback patch payload | feedback result |
| `src/services/admin.js:updateFeedbackStatus` | POST | `/admin/feedback/{feedback_id}/status` | status payload | feedback result |
| `src/services/admin.js:addFeedbackNote` | POST | `/admin/feedback/{feedback_id}/note` | note payload | feedback result |
| `src/services/admin.js:loadOpsStatus` | GET | `/admin/ops/status` | none | ops status |
| `src/services/admin.js:loadAuditLog` | GET | `/admin/audit-log` | query `limit` | `audit_log` |

## 4. Request mismatches

- No breaking request-shape mismatch was found in current wallet auth, vote signing, or native transfer signing.
- `src/pages/Dashboard.vue` signs submissions correctly but omits `text_content` in the final `/submit_content` request even when the content object was created through `/content/text`. This does not break signature verification, but it leaves the serialized submission record without the mirrored text payload that the UI later expects.
- Dev-only operational requests remain embedded in general-purpose views:
  - `/content/{content_hash}/sync`
  - `/submissions/{submission_id}/evaluate`
  - `/mint/{submission_id}`
  - `/submissions/{submission_id}/block-minting`
  - `/submissions/{submission_id}/unblock-minting`
  - `/mempool`
  - `/transactions/{tx_id}/admit`
  - `/generate_wallet`

## 5. Response mismatches

- `src/pages/Dashboard.vue`, `src/pages/Blockchain.vue`, and `src/components/WalletPanel.vue` do not consume important frozen response fields now returned by the backend:
  - `protocol_version`
  - `network_id`
  - `genesis_hash`
  - `canonical_genesis_hash`
  - `protocol_v1_lifecycle`
  - `submission_status`
  - `certificate_status`
  - `mint_status`
  - `block_status`
  - `confirmations`
  - `confirmed`
  - `finalized`
  - `is_genesis`
  - `object_type`
  - `accepted`
  - `canonical`
  - `confirmation_depth`
  - `finality_depth`
  - `finality_model`
  - `finality_scope`
  - `media_embedded`
  - `media_size_bytes`
- The frontend primarily consumes old alias/status fields like `network_name` and `status` and therefore still behaves as though the pre-freeze response contract is the important one.

## 6. Wallet/MetaMask mismatches

Matches:

- Wallet login uses backend-issued challenge messages.
- Verification uses MetaMask `personal_sign`.
- The frontend does not locally construct the signed login message.

Mismatches:

- `src/components/WalletPanel.vue` prominently displays the MetaMask `chainId`.
- `src/services/wallet.js` clears the ZoidbergChain verified session whenever MetaMask emits `chainChanged`.
- Together, those choices suggest Ethereum chain selection materially controls ZoidbergChain ledger identity, even though Protocol v1 treats MetaMask as identity/signing infrastructure and binds consensus to `network_id`, not the wallet's EVM chain setting.

## 7. Vote signing mismatches

Matches:

- The UI requests a backend vote challenge first.
- The backend-provided string is signed via `personal_sign`.
- The submitted vote form sends `wallet_address`, `vote_type`, `message`, and `signature`.
- Vote labels in source match the current accepted values: `original`, `not_original`, `unsure`.

Gaps:

- The UI ignores returned Protocol v1 vote metadata such as `vote_version`, `protocol_version`, `network_id`, `nonce`, `issued_at`, and `expires_at`.
- There is no dedicated expired-challenge UX. An expired vote challenge falls through generic error handling.

## 8. Certificate mismatches

- The UI shows certificate ID and originality score, but it does not expose or internally reason about certificate version/network binding.
- Certificate handling still assumes that a submission's coarse status is the primary truth instead of the certificate-backed lifecycle.
- The UI does not distinguish "certificate exists" from "submission is canonical/confirmed/finalized on-chain."

## 9. Submission lifecycle mismatches

- `src/pages/Dashboard.vue` groups and labels submissions almost entirely from persisted `status`.
- `pendingSubmissions()` only checks `status === 'pending'`.
- `approvedSubmissions()` only checks `status in {'approved','queued'}`.
- `rejectedSubmissions()` only checks `status === 'rejected'`, so `hard_rejected` is not surfaced consistently as a terminal rejected state.
- The UI does not display Protocol v1 lifecycle phases such as:
  - voting
  - certified
  - mint-eligible
  - block accepted
  - canonical
  - confirmed
  - finalized
- Mint success copy treats block creation as the important terminal event and does not separate accepted, canonical, confirmed, and finalized chain state.

## 10. Block explorer mismatches

- `src/pages/Blockchain.vue` and the activity explorer inside `src/pages/Dashboard.vue` omit frozen block identity and chain-state fields:
  - `block_version`
  - `network_id`
  - `object_type`
  - `canonical`
  - `confirmations`
  - `confirmed`
  - `finalized`
  - `confirmation_depth`
  - `finality_depth`
  - `canonical_genesis_hash`
- The explorer still labels blocks largely as "Certified" or "No Certificate Required" instead of using the Protocol v1 chain-state terminology now returned by `_serialize_block(...)`.
- Genesis is rendered with the same block card structure as accepted content blocks, which invites incorrect content/media assumptions.

## 11. MODEL A/media mismatches

- Protocol v1 freezes MODEL A: accepted media bytes are part of the block record.
- Current UI still treats `download_url` and auxiliary `storage_status` as the practical source of truth for accepted content.
- Missing or remote auxiliary content causes the UI to suggest syncing content, even for records whose accepted block can already be authoritative on-chain.
- The UI does not use `media_embedded` or `media_size_bytes`.
- The UI has no block detail path for controlled retrieval/rendering of embedded block media if auxiliary storage is absent.
- The fallback to legacy `block.meme.encoded_image` is not a reliable Protocol v1 MODEL A strategy.

## 12. Native transfer mismatches

Matches:

- Amounts remain strings in the transfer service.
- The service rejects scientific notation and more than 6 decimals before signing.
- The backend supplies the canonical transfer message.
- The frontend signs the exact backend string and submits it unchanged.

Gaps:

- The wallet UI does not show `transaction_version`, `protocol_version`, or `network_id` even though the backend returns them.
- The transfer challenge's `issued_at` and `expires_at` are ignored.
- The transfer/history UI does not explain canonicality or reorg-sensitive transition semantics beyond pending/included/settled wording.
- Dev mempool actions remain mixed into the wallet panel source.

## 13. Network/genesis mismatches

- `src/pages/Dashboard.vue`, `src/pages/Blockchain.vue`, and `src/components/WalletPanel.vue` display `network_name` but not the canonical `network_id`.
- The UI does not display `protocol_version`.
- The UI does not display the canonical genesis hash.
- The UI does not distinguish runtime alias (`zoidberg-testnet`) from consensus identity (`zoidberg-public-testnet-v1`).
- Genesis is labeled with generic phrases like `Genesis / Legacy` or `No Certificate Required` instead of being presented as a special Protocol v1 genesis object with its own frozen semantics.

## 14. Confirmation/finality mismatches

- No user-facing view currently shows the backend's confirmation count.
- No view explains the frozen thresholds:
  - confirmed at 2 descendants
  - finalized at 6 descendants
- The UI therefore cannot distinguish:
  - accepted but unconfirmed
  - confirmed but not finalized
  - finalized
- Existing copy uses "settled", "minted", or generic success language without mapping those states onto the new operational finality model.

## 15. Legacy-route exposure

- No frontend source usage of `/add_block` was found. This is good.
- No frontend source usage of the legacy `/wallets/{wallet_address}/...` read routes was found. This is good.
- The frontend still contains dev/ops exposure to non-canonical routes and workflows inside shared user-facing pages when `showDevelopmentTools()` is true:
  - `/generate_wallet`
  - `/content/{content_hash}/sync`
  - `/submissions/{submission_id}/evaluate`
  - `/mint/{submission_id}`
  - `/submissions/{submission_id}/block-minting`
  - `/submissions/{submission_id}/unblock-minting`
  - `/mempool`
  - `/transactions/{tx_id}/admit`

## 16. Admin/public separation

- `src/pages/AdminPage.vue` is cleanly routed under `/admin` and uses `adminApiClient` with cookie-auth. This part matches the backend separation well.
- The larger mismatch is structural: operational actions still live in the general Dashboard and WalletPanel source and are hidden by environment flags rather than by an explicitly separate operator surface.
- Backend route protection prevents these calls from becoming silent security regressions, but the UI source is still carrying public and operator responsibilities together.

## 17. Error-handling gaps

- `src/config/api.js:getApiErrorMessage` extracts generic `detail`, `error`, `message`, `status`, `reason`, and `recommended_action` text well.
- Transfer UX adds targeted mapping in `src/utils/nativeWalletUi.js:humanizeNativeTransferError`.
- Vote and submission flows do not have equivalent explicit handling for Protocol v1-specific cases such as:
  - expired challenge
  - wrong network
  - unsupported version
  - wrong signer
  - reused nonce/challenge
  - already certified or already minted
  - genesis mismatch/reset required
- The result is technically serviceable errors, but not protocol-aware remediation guidance.

## 18. Stale frontend models

| File | Current fields/assumptions | Required fields | Remove/de-emphasize | Add/use |
| --- | --- | --- | --- | --- |
| `src/pages/Dashboard.vue` | `status`, `certificate_id`, `mintable`, `mint_block_reason`, `storage_status` | lifecycle and chain-state fields from `_serialize_submission` and `_serialize_block` | status-only grouping | `protocol_v1_lifecycle`, `submission_status`, `certificate_status`, `mint_status`, `block_status`, `confirmations`, `confirmed`, `finalized`, `canonical` |
| `src/pages/Blockchain.vue` | `network_name`, certificate presence, `download_url`, legacy `meme.encoded_image` fallback | canonical block/genesis identity | alias-only network display, certificate-only block labels | `block_version`, `network_id`, `object_type`, `is_genesis`, `canonical_genesis_hash`, `media_embedded`, `media_size_bytes`, finality fields |
| `src/components/WalletPanel.vue` | `network_name`, `final_balance`, simple transfer `status` strings | Protocol v1 account/transaction identity and settlement context | prominent MetaMask `chainId` display | `network_id`, `protocol_version`, transaction version, better finality/canonical wording |
| `src/utils/nativeWalletUi.js` | status string mapping only | richer settlement/finality mapping | implicit finality from `settled` alone | canonical/finality-aware status labels when backend adds more fields |
| `src/services/wallet.js` | wallet session tied to MetaMask chain change behavior | ZoidbergChain session semantics separated from EVM network display | hard session invalidation on any `chainChanged` | softer UX that explains MetaMask network is not the chain identity |
| `src/services/nativeTransfer.test.js` | tests still assert alias field `network: 'zoidberg-testnet'` | Protocol v1 network binding expectations | alias-only expectations | `network_id`, `protocol_version`, `transaction_version` assertions |

## 19. Terminology/copy issues

- Replace alias-only "Network" labels with language that can show both:
  - display name: `Public Testnet v1`
  - canonical id: `zoidberg-public-testnet-v1`
- Replace generic block labels like `Certified Meme` and `No Certificate Required` with lifecycle-aware phrasing.
- Avoid making `Chain ID` a prominent wallet concept unless explicitly labeled as MetaMask/EVM wallet state.
- Clarify that accepted media is part of the immutable block record and auxiliary download availability is a convenience layer.
- Keep the existing good copy that already says native ZOID is not an ERC-20 and does not live on Ethereum.

Recommended wording replacements:

- `Network` -> `Network (Public Testnet v1)`
- `Chain ID` -> `MetaMask wallet network` or remove from the main wallet card
- `Certified Meme` -> `Accepted Protocol v1 block`
- `No Certificate Required` on genesis -> `Protocol v1 genesis object`
- `Genesis / Legacy` -> `Genesis`

## 20. Generated build artifact status

- `zoidbergcoin-ui/dist/` is present and a safe audit build reproduced matching asset names and sizes without touching the committed `dist/`.
- `static/index.html` is stale and still served by `GET /` in `api.py`.
- `zoidbergcoin-ui/zoidbergchain-dist.zip` appears stale or unrelated. Its entry names do not match the current Vue app and instead resemble another product bundle.
- Deployment/runbook docs still describe a manual `dist/` publish step, which means drift between source and deployable artifacts remains possible if UI-2 changes are not followed by a rebuild/publish step.

## 21. Existing frontend test coverage

- Existing frontend command coverage:
  - `npm test`
  - `npm run build`
- Present scripts:
  - no dedicated lint script
  - no dedicated typecheck script
  - no end-to-end/browser automation script
- Current coverage is strongest around:
  - API base URL config
  - runtime config flags
  - access gating
  - admin service/UI helpers
  - wallet session manager
  - native transfer client-side validation
  - user-facing copy assertions
- Coverage is weak for:
  - actual rendered lifecycle/finality states
  - network/genesis display
  - Protocol v1 block explorer fields
  - MODEL A embedded media behavior
  - vote/submission expiry UX

## 22. Recommended Task UI-2 implementation plan

### A. API/client contract

- Update submission, block, and wallet-facing data consumption to use Protocol v1 response fields.
- Files:
  - `zoidbergcoin-ui/src/pages/Dashboard.vue`
  - `zoidbergcoin-ui/src/pages/Blockchain.vue`
  - `zoidbergcoin-ui/src/components/WalletPanel.vue`
  - `zoidbergcoin-ui/src/utils/nativeWalletUi.js`

### B. MetaMask signing flows

- Preserve backend-generated message signing.
- Add explicit expiry/retry UX for wallet-bound submission, vote, and transfer challenges.
- Remove or de-emphasize misleading EVM `chainId` messaging.
- Files:
  - `zoidbergcoin-ui/src/services/wallet.js`
  - `zoidbergcoin-ui/src/pages/Dashboard.vue`
  - `zoidbergcoin-ui/src/components/WalletPanel.vue`
  - `zoidbergcoin-ui/src/services/nativeTransfer.js`

### C. Submission/voting UX

- Rework submission grouping and labels around `protocol_v1_lifecycle`.
- Surface certificate-backed state, vote lock, and rejected `hard_rejected` visibility correctly.
- Pass `text_content` through signed text submissions if the UI expects it later.
- Files:
  - `zoidbergcoin-ui/src/pages/Dashboard.vue`

### D. Native transfers

- Surface `transaction_version`, `protocol_version`, `network_id`, and clearer settlement/finality wording.
- Keep string-only amount handling.
- Improve transfer error mapping and challenge expiry handling.
- Files:
  - `zoidbergcoin-ui/src/components/WalletPanel.vue`
  - `zoidbergcoin-ui/src/services/nativeTransfer.js`
  - `zoidbergcoin-ui/src/utils/nativeWalletUi.js`
  - `zoidbergcoin-ui/src/services/nativeTransfer.test.js`

### E. Explorer/MODEL A

- Use block fields that describe embedded authoritative media.
- Add a detail/download path that can explain auxiliary storage vs embedded chain media without forcing full media bytes into list responses.
- Stop relying on legacy `meme.encoded_image` as the Protocol v1 fallback.
- Files:
  - `zoidbergcoin-ui/src/pages/Dashboard.vue`
  - `zoidbergcoin-ui/src/pages/Blockchain.vue`

### F. Lifecycle/confirmation/finality

- Show accepted/canonical/confirmed/finalized state and the frozen `2/6` depth rules.
- Ensure mint success, block cards, and reward messaging stop implying immediate finality.
- Files:
  - `zoidbergcoin-ui/src/pages/Dashboard.vue`
  - `zoidbergcoin-ui/src/pages/Blockchain.vue`
  - `zoidbergcoin-ui/src/components/WalletPanel.vue`
  - `zoidbergcoin-ui/src/utils/nativeWalletUi.js`

### G. Network/genesis

- Display `Public Testnet v1`, `network_id`, and shortened genesis hash in selected places.
- Render genesis as a special object rather than a normal accepted-media block.
- Files:
  - `zoidbergcoin-ui/src/pages/Dashboard.vue`
  - `zoidbergcoin-ui/src/pages/Blockchain.vue`
  - `zoidbergcoin-ui/src/components/WalletPanel.vue`

### H. Admin/legacy cleanup

- Keep `/admin` as the explicit operator surface.
- Move or isolate dev/ops-only actions from shared public pages.
- Continue avoiding `/add_block` in canonical UI.
- Files:
  - `zoidbergcoin-ui/src/pages/Dashboard.vue`
  - `zoidbergcoin-ui/src/components/WalletPanel.vue`
  - `zoidbergcoin-ui/src/pages/HomePage.vue`
  - `zoidbergcoin-ui/src/utils/runtimeConfig.js`

### I. Build/tests

- Rebuild `zoidbergcoin-ui/dist/` from the updated source.
- Replace or remove the stale `zoidbergchain-dist.zip`.
- Replace `static/index.html` or stop serving it as the primary frontend entrypoint.
- Add frontend tests covering Protocol v1 lifecycle, network/genesis, and MODEL A rendering.
- Files:
  - `zoidbergcoin-ui/dist/`
  - `zoidbergcoin-ui/zoidbergchain-dist.zip`
  - `static/index.html`
  - `zoidbergcoin-ui/src/pages/dashboardNavigation.test.js`
  - new tests for Dashboard, Blockchain, WalletPanel, and Protocol v1 display helpers

## Deliverable 2: mismatch matrix

| Severity | Category | Frontend file/function | Backend route/function | Mismatch | User impact | Required fix |
| --- | --- | --- | --- | --- | --- | --- |
| High | STALE LEGACY | `static/index.html`, backend root entry | `GET /` in `api.py:home` | Backend still serves the old splash page instead of the Vue app | Users landing on the local backend root see pre-beta copy and no Protocol v1 workflow | Serve the maintained frontend entrypoint or replace the stale splash page during UI-2 |
| High | STALE LEGACY | `zoidbergcoin-ui/zoidbergchain-dist.zip` | deployment artifact, not live source | Committed zip artifact appears unrelated to the current Vue app | Packaging or manual deployment could publish the wrong UI entirely | Rebuild or remove the zip and treat source plus rebuilt `dist/` as authoritative |
| High | STALE LEGACY | `src/pages/Dashboard.vue` computed submission grouping and mint messaging | `_serialize_submission(...)`, `/submissions`, `/mint-queue`, `/mint/{submission_id}` | Dashboard still models workflow from persisted legacy `status` instead of Protocol v1 lifecycle/finality fields | Users cannot tell certified vs canonical vs confirmed vs finalized state and may treat minting as terminal finality | Rebase Dashboard state and labels on `protocol_v1_lifecycle`, confirmation, and finality fields |
| High | PROTOCOL MISREPRESENTATION | `src/pages/Blockchain.vue`, `src/pages/Dashboard.vue` block explorer cards | `_serialize_block(...)`, `/chain`, `/chain/summary` | Explorer omits block version, network binding, canonical/finality fields, and renders genesis like a normal content block | The chain display still looks like the pre-freeze model and hides the frozen genesis/network contract | Add explicit block/genesis identity and finality rendering |
| High | MISSING FEATURE | `src/pages/Dashboard.vue`, `src/pages/Blockchain.vue` content preview/state logic | `_serialize_block(...)`, MODEL A frozen block format | UI treats auxiliary download/storage state as the practical source of truth and ignores embedded media metadata | Accepted content appears fragile or "missing" even when Protocol v1 blocks are authoritative | Add MODEL A-aware detail behavior using embedded media metadata and clearer storage wording |
| High | PROTOCOL MISREPRESENTATION | `src/pages/Dashboard.vue`, `src/pages/Blockchain.vue`, `src/components/WalletPanel.vue` | `/chain/summary`, `_build_account_summary(...)` | Frontend displays `network_name` only and never surfaces canonical `network_id`, protocol version, or genesis hash | Users see the runtime alias but not the frozen consensus identity | Show a compact Public Testnet v1 identity model in key views |
| Medium | PROTOCOL MISREPRESENTATION | `src/services/wallet.js`, `src/components/WalletPanel.vue` | wallet auth session routes | UI highlights MetaMask `chainId` and invalidates ZoidbergChain verification on any wallet `chainChanged` event | Users can infer that Ethereum network selection determines ZoidbergChain state | De-emphasize `chainId` and explain the distinction between wallet network and ZoidbergChain identity |
| Medium | MISSING FEATURE | `src/pages/Dashboard.vue:vote` | `/auth/wallet/vote-challenge`, `/submissions/{submission_id}/vote` | Vote challenge `issued_at`/`expires_at` are ignored and expired challenges fall back to generic errors | Users may sign stale votes and get opaque failures | Add challenge expiry refresh/retry UX and targeted error copy |
| Medium | BREAKING | `src/pages/Dashboard.vue:submitContent` | `/submit_content` | Signed text submissions omit `text_content` in the final submission request | Text submission previews and later serialized submission text can be blank or inconsistent | Include mirrored text payload when submitting existing text content |
| Medium | MISSING FEATURE | `src/components/WalletPanel.vue`, `src/services/nativeTransfer.js` | `/auth/wallet/transfer-challenge`, `/accounts/{wallet_address}/transactions` | Transfer UI ignores version/network/expiry metadata and only partially explains settlement state | Transfer history works, but users cannot see frozen identity/finality context | Surface transaction identity fields and add expiry-aware transfer UX |
| Medium | STALE LEGACY | `src/pages/Dashboard.vue`, `src/components/WalletPanel.vue`, `src/pages/HomePage.vue` | dev/ops routes listed in sections 4 and 15 | Shared public pages still contain dev/ops actions behind `showDevelopmentTools()` flags | A misbuilt environment could expose operator workflows in the normal tester UI | Move these controls into explicit operator/dev surfaces |
| Medium | MISSING FEATURE | `src/config/api.js`, `src/pages/Dashboard.vue`, `src/services/wallet.js` | multiple Protocol v1 routes | Error handling is generic for vote/submission/network/genesis/finality problems outside transfers | Users get errors, but not helpful protocol-aware next steps | Add targeted UI messaging for expired challenge, wrong network, wrong signer, legacy/reset-required cases |
| Low | COSMETIC | `src/pages/Dashboard.vue`, `src/pages/Blockchain.vue`, `src/components/WalletPanel.vue` | multiple chain and wallet routes | Copy still leans on phrases like `Certified Meme`, `Genesis / Legacy`, and alias-only `Network` | Language understates the frozen Protocol v1 model | Refresh labels to align with Protocol v1 terminology |
| Low | STALE LEGACY | `src/router/index.js`, `src/pages/Blockchain.vue` | `/chain`, `/chain/summary` | Dedicated `Blockchain.vue` explorer remains in source even though `/blockchain` redirects to `/activity` | A second explorer implementation can drift from the real activity explorer | Consolidate or intentionally retire the duplicate explorer in UI-2 |
| Low | STALE LEGACY | `zoidbergcoin-ui/dist/`, deployment docs | manual build/publish path | Deployable artifacts depend on a manual rebuild/publish path and can drift from source | UI-2 fixes could be implemented in source but not actually shipped | Rebuild and publish `dist/` as part of UI-2 completion |
