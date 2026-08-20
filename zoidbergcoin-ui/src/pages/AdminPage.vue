<template>
  <div class="admin-shell" :class="{ 'stacked-admin-shell': usesMobileCards }">
    <div class="admin-backdrop"></div>
    <main class="admin-content">
      <header class="hero-card">
        <div>
          <p class="eyebrow">Controlled Testnet Admin</p>
          <h1>Operator Access Dashboard</h1>
          <p class="subtitle">
            Review access requests, issue one-time invites, and manage controlled-testnet accounts.
          </p>
        </div>
        <router-link to="/" class="ghost-link">Return to public site</router-link>
      </header>

      <section class="warning-card">
        <p v-for="line in safetyLines" :key="line">{{ line }}</p>
      </section>

      <section v-if="!dashboardVisible" class="panel login-panel">
        <div class="panel-heading">
          <div>
            <p class="section-label">Admin Login</p>
            <h2>Sign in to manage access</h2>
          </div>
        </div>

        <p v-if="sessionState?.admin_ui_enabled === false" class="status-message error">
          Admin UI is disabled on this node.
        </p>
        <p
          v-else-if="sessionState && sessionState.admin_auth_configured === false && sessionState.admin_auth_enabled !== false"
          class="status-message error"
        >
          Admin auth is enabled but not configured on this node yet.
        </p>

        <form class="form-stack" @submit.prevent="handleLogin">
          <div class="field-group">
            <label for="admin-password">Admin password or bootstrap token</label>
            <input
              id="admin-password"
              v-model="loginPassword"
              type="password"
              autocomplete="current-password"
              class="input-field"
              placeholder="Enter the server-side admin credential"
            >
          </div>
          <button class="primary-button" :disabled="admin.state.isLoggingIn || !loginPassword.trim()">
            {{ admin.state.isLoggingIn ? 'Signing in...' : 'Sign In' }}
          </button>
        </form>
      </section>

      <template v-else>
        <section class="panel session-panel">
          <div class="panel-heading">
            <div>
              <p class="section-label">Session</p>
              <h2>Authenticated operator session</h2>
            </div>
            <div class="inline-actions">
              <button class="secondary-button" :disabled="isRefreshing" @click="refreshDashboard">
                {{ isRefreshing ? 'Refreshing...' : 'Refresh' }}
              </button>
              <button class="ghost-button" :disabled="admin.state.isSubmitting" @click="handleLogout">
                Log Out
              </button>
            </div>
          </div>
          <div class="metric-row">
            <div>
              <span>Authenticated</span>
              <strong>{{ sessionState?.authenticated ? 'Yes' : 'No' }}</strong>
            </div>
            <div>
              <span>Expires</span>
              <strong>{{ formatDate(sessionState?.expires_at) }}</strong>
            </div>
            <div>
              <span>Session backend</span>
              <strong>{{ sessionState?.session_backend || 'unknown' }}</strong>
            </div>
          </div>
        </section>

        <section v-if="admin.state.lastInviteCode" class="panel invite-result-panel">
          <div class="panel-heading">
            <div>
              <p class="section-label">One-Time Invite</p>
              <h2>Copy this invite before leaving</h2>
            </div>
            <button class="secondary-button" @click="copyInviteCode">Copy Code</button>
          </div>
          <p class="invite-code">{{ admin.state.lastInviteCode }}</p>
          <p class="muted-copy">{{ admin.state.inviteWarning }}</p>
        </section>

        <section class="dashboard-grid">
          <section class="panel">
            <div class="panel-heading">
              <div>
                <p class="section-label">Pending Requests</p>
                <h2>Review incoming access requests</h2>
              </div>
            </div>

            <div v-if="pendingRequests.length === 0" class="empty-state">
              No pending access requests right now.
            </div>

            <div v-for="request in pendingRequests" :key="request.request_id" class="request-card">
              <div class="card-topline">
                <strong>{{ request.name }}</strong>
                <span>{{ request.status }}</span>
              </div>
              <p>{{ request.email }}</p>
              <p v-if="request.handle" class="muted-copy">{{ request.handle }}</p>
              <p class="request-reason">{{ request.reason }}</p>
              <p v-if="request.notes" class="muted-copy">{{ request.notes }}</p>
              <p class="meta-row">Requested {{ formatDate(request.created_at) }}</p>

              <button class="ghost-button small-button" @click="selectRequest(request)">
                {{ selectedRequest?.request_id === request.request_id ? 'Selected' : 'Review Request' }}
              </button>
            </div>
          </section>

          <section class="panel">
            <div class="panel-heading">
              <div>
                <p class="section-label">Request Detail</p>
                <h2>Approve or reject access</h2>
              </div>
            </div>

            <div v-if="!selectedRequest" class="empty-state">
              Select a pending request to review it.
            </div>

            <template v-else>
              <div class="detail-block">
                <p class="detail-line">
                  <strong>Request ID:</strong>
                  <span class="detail-value">{{ selectedRequest.request_id }}</span>
                  <button class="ghost-button small-button" type="button" @click="copyText(selectedRequest.request_id)">Copy</button>
                </p>
                <p><strong>Name:</strong> {{ selectedRequest.name }}</p>
                <p><strong>Email:</strong> {{ selectedRequest.email }}</p>
                <p><strong>Handle:</strong> {{ selectedRequest.handle || 'None' }}</p>
                <p><strong>Reason:</strong> {{ selectedRequest.reason }}</p>
                <p><strong>Notes:</strong> {{ selectedRequest.notes || 'None' }}</p>
              </div>

              <div class="form-stack">
                <div class="field-group">
                  <label for="reviewed-by">Reviewed by</label>
                  <input id="reviewed-by" v-model="reviewedBy" class="input-field" type="text">
                </div>
                <div class="field-group">
                  <label for="request-max-wallets">Max wallets</label>
                  <input id="request-max-wallets" v-model.number="requestMaxWallets" class="input-field" type="number" min="1" max="50">
                </div>
                <div class="field-group">
                  <label for="request-notes">Operator notes</label>
                  <textarea id="request-notes" v-model="requestNotes" class="input-field text-area" placeholder="Add approval or rejection notes"></textarea>
                </div>
              </div>

              <div class="inline-actions">
                <button class="primary-button" :disabled="admin.state.isSubmitting" @click="approveSelectedRequest">
                  Approve Request
                </button>
                <button class="danger-button" :disabled="admin.state.isSubmitting" @click="rejectSelectedRequest">
                  Reject Request
                </button>
              </div>
            </template>
          </section>

          <section class="panel">
            <div class="panel-heading">
              <div>
                <p class="section-label">Direct Invite</p>
                <h2>Create an approved account directly</h2>
              </div>
            </div>

            <div class="form-stack">
              <div class="field-group">
                <label for="invite-name">Name</label>
                <input id="invite-name" v-model="inviteForm.name" class="input-field" type="text">
              </div>
              <div class="field-group">
                <label for="invite-email">Email</label>
                <input id="invite-email" v-model="inviteForm.email" class="input-field" type="email">
              </div>
              <div class="field-group">
                <label for="invite-handle">Handle</label>
                <input id="invite-handle" v-model="inviteForm.handle" class="input-field" type="text">
              </div>
              <div class="field-group">
                <label for="invite-notes">Notes</label>
                <textarea id="invite-notes" v-model="inviteForm.notes" class="input-field text-area"></textarea>
              </div>
              <div class="field-group">
                <label for="invite-max-wallets">Max wallets</label>
                <input id="invite-max-wallets" v-model.number="inviteForm.max_wallets" class="input-field" type="number" min="1" max="50">
              </div>
            </div>

            <button class="primary-button" :disabled="admin.state.isSubmitting" @click="createDirectInvite">
              Create Direct Invite
            </button>
          </section>

          <section class="panel accounts-panel">
            <div class="panel-heading">
              <div>
                <p class="section-label">Approved Accounts</p>
                <h2>Monitor access and bound wallets</h2>
              </div>
            </div>

            <div v-if="admin.state.accounts.length === 0" class="empty-state">
              No approved access accounts yet.
            </div>

            <div v-for="account in admin.state.accounts" :key="account.access_account_id" class="account-card">
              <div class="card-topline">
                <strong>{{ account.name }}</strong>
                <span>{{ account.status }}</span>
              </div>
              <p>{{ account.email }}</p>
              <p class="meta-row">
                {{ account.wallet_count }} / {{ account.max_wallets }} wallets bound
              </p>
              <p class="meta-row">
                Invite redeemed: {{ account.invite_redeemed ? 'Yes' : 'No' }}
              </p>
              <p class="meta-row">
                Last login: {{ formatDate(account.last_login_at) }}
              </p>
              <div class="wallet-pill-row">
                <div v-for="walletRow in walletRows(account.bound_wallets)" :key="walletRow.walletAddress" class="wallet-row">
                  <span class="wallet-pill" :title="walletRow.walletAddress">{{ walletRow.shortLabel }}</span>
                  <button class="ghost-button small-button" type="button" @click="copyText(walletRow.walletAddress)">Copy</button>
                </div>
                <span v-if="account.bound_wallets.length === 0" class="muted-copy">No bound wallets</span>
              </div>
              <div class="inline-actions wrap-actions">
                <button class="ghost-button small-button" @click="openAccount(account.access_account_id)">Details</button>
                <button class="secondary-button small-button" :disabled="admin.state.isSubmitting" @click="changeAccountStatus(account.access_account_id, 'suspend')">Suspend</button>
                <button class="secondary-button small-button" :disabled="admin.state.isSubmitting" @click="changeAccountStatus(account.access_account_id, 'reactivate')">Reactivate</button>
                <button class="danger-button small-button" :disabled="admin.state.isSubmitting" @click="changeAccountStatus(account.access_account_id, 'revoke')">Revoke</button>
              </div>
            </div>
          </section>

          <section class="panel">
            <div class="panel-heading">
              <div>
                <p class="section-label">Bound Wallet Detail</p>
                <h2>Review and revoke bindings</h2>
              </div>
            </div>

            <div v-if="!admin.state.selectedAccount" class="empty-state">
              Choose an account to inspect wallet bindings.
            </div>

            <template v-else>
              <div class="detail-block">
                <p><strong>Access account:</strong> {{ admin.state.selectedAccount.access_account.name }}</p>
                <p><strong>Status:</strong> {{ admin.state.selectedAccount.access_account.status }}</p>
                <p><strong>Approved:</strong> {{ formatDate(admin.state.selectedAccount.access_account.approved_at) }}</p>
              </div>

              <div v-if="admin.state.selectedAccount.wallet_bindings.length === 0" class="empty-state">
                No wallet bindings found for this account.
              </div>

              <div v-for="binding in admin.state.selectedAccount.wallet_bindings" :key="binding.wallet_address" class="binding-card">
                <p class="detail-line">
                  <strong>{{ binding.wallet_address }}</strong>
                  <button class="ghost-button small-button" type="button" @click="copyText(binding.wallet_address)">Copy</button>
                </p>
                <p class="meta-row">Status: {{ binding.status }}</p>
                <p class="meta-row">Bound: {{ formatDate(binding.bound_at) }}</p>
                <button class="danger-button small-button" :disabled="admin.state.isSubmitting" @click="revokeWallet(binding.wallet_address)">
                  Revoke Wallet Binding
                </button>
              </div>
            </template>
          </section>
        </section>
      </template>

      <p v-if="admin.state.successMessage" class="status-message success">{{ admin.state.successMessage }}</p>
      <p v-if="copyFeedback" class="status-message success">{{ copyFeedback }}</p>
      <p v-if="admin.state.errorMessage" class="status-message error">{{ admin.state.errorMessage }}</p>
    </main>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue';
import { useAdmin } from '../services/admin.js';
import {
  adminSafetyLines,
  buildBoundWalletRows,
  shouldShowAdminDashboard,
  shouldUseStackedAdminCards,
} from '../utils/adminUi.js';

const admin = useAdmin();
const safetyLines = adminSafetyLines();
const loginPassword = ref('');
const selectedRequest = ref(null);
const reviewedBy = ref('operator');
const requestNotes = ref('');
const requestMaxWallets = ref(1);
const isRefreshing = ref(false);
const viewportWidth = ref(typeof window === 'undefined' ? 0 : window.innerWidth);
const copyFeedback = ref('');

const inviteForm = reactive({
  name: '',
  email: '',
  handle: '',
  notes: '',
  reviewed_by: 'operator',
  operator_notes: '',
  max_wallets: 1,
});

const sessionState = computed(() => admin.state.session);
const dashboardVisible = computed(() => shouldShowAdminDashboard(admin.state.session));
const pendingRequests = computed(() => admin.state.requests.filter((request) => request.status === 'pending'));
const usesMobileCards = computed(() => shouldUseStackedAdminCards(viewportWidth.value));

function formatDate(value) {
  if (!value) {
    return 'Not available';
  }
  const parsed = Date.parse(value);
  if (Number.isNaN(parsed)) {
    return value;
  }
  return new Date(parsed).toLocaleString();
}

function selectRequest(request) {
  selectedRequest.value = request;
  requestNotes.value = request.operator_notes || '';
  requestMaxWallets.value = 1;
  reviewedBy.value = 'operator';
}

function walletRows(boundWallets) {
  return buildBoundWalletRows(boundWallets);
}

async function refreshDashboard() {
  isRefreshing.value = true;
  try {
    await Promise.all([
      admin.loadRequests('pending'),
      admin.loadAccounts(),
    ]);
    if (admin.state.selectedAccount?.access_account?.access_account_id) {
      await admin.loadAccountDetail(admin.state.selectedAccount.access_account.access_account_id);
    }
  } finally {
    isRefreshing.value = false;
  }
}

async function handleLogin() {
  const result = await admin.login(loginPassword.value);
  if (result?.authenticated) {
    loginPassword.value = '';
    await refreshDashboard();
  }
}

async function handleLogout() {
  await admin.logout();
  selectedRequest.value = null;
}

async function approveSelectedRequest() {
  if (!selectedRequest.value) {
    return;
  }
  const result = await admin.approveRequest(selectedRequest.value.request_id, {
    reviewed_by: reviewedBy.value,
    operator_notes: requestNotes.value,
    max_wallets: Number(requestMaxWallets.value) || 1,
  });
  if (result) {
    selectedRequest.value = null;
    requestNotes.value = '';
    requestMaxWallets.value = 1;
  }
}

async function rejectSelectedRequest() {
  if (!selectedRequest.value) {
    return;
  }
  const result = await admin.rejectRequest(selectedRequest.value.request_id, {
    reviewed_by: reviewedBy.value,
    operator_notes: requestNotes.value,
  });
  if (result) {
    selectedRequest.value = null;
    requestNotes.value = '';
  }
}

async function createDirectInvite() {
  const result = await admin.createInvite({
    ...inviteForm,
    max_wallets: Number(inviteForm.max_wallets) || 1,
  });
  if (result) {
    inviteForm.name = '';
    inviteForm.email = '';
    inviteForm.handle = '';
    inviteForm.notes = '';
    inviteForm.operator_notes = '';
    inviteForm.max_wallets = 1;
  }
}

async function openAccount(accessAccountId) {
  await admin.loadAccountDetail(accessAccountId);
}

async function changeAccountStatus(accessAccountId, action) {
  await admin.updateAccountStatus(accessAccountId, action);
}

async function revokeWallet(walletAddress) {
  await admin.revokeWalletBinding(walletAddress);
}

async function copyInviteCode() {
  if (!admin.state.lastInviteCode || typeof navigator === 'undefined' || !navigator.clipboard) {
    return;
  }
  await navigator.clipboard.writeText(admin.state.lastInviteCode);
  copyFeedback.value = 'Invite code copied.';
}

async function copyText(value) {
  if (!value || typeof navigator === 'undefined' || !navigator.clipboard) {
    return;
  }
  await navigator.clipboard.writeText(String(value));
  copyFeedback.value = 'Copied to clipboard.';
}

function handleResize() {
  viewportWidth.value = typeof window === 'undefined' ? 0 : window.innerWidth;
}

onMounted(async () => {
  if (typeof window !== 'undefined') {
    window.addEventListener('resize', handleResize);
  }
  const session = await admin.loadSession();
  if (session?.authenticated) {
    await refreshDashboard();
  }
});

onBeforeUnmount(() => {
  if (typeof window !== 'undefined') {
    window.removeEventListener('resize', handleResize);
  }
});
</script>

<style scoped>
.admin-shell {
  min-height: 100vh;
  position: relative;
  overflow: hidden;
  background:
    radial-gradient(circle at top left, rgba(255, 153, 102, 0.18), transparent 28%),
    radial-gradient(circle at bottom right, rgba(255, 209, 102, 0.14), transparent 32%),
    linear-gradient(180deg, #090d15 0%, #05070d 100%);
  color: #f7f0de;
  padding: 32px 16px 56px;
}

.admin-backdrop {
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(rgba(255, 205, 115, 0.05) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 205, 115, 0.05) 1px, transparent 1px);
  background-size: 24px 24px;
  mask-image: linear-gradient(180deg, rgba(0, 0, 0, 0.8), transparent 92%);
}

.admin-content {
  position: relative;
  width: min(1240px, 100%);
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.hero-card,
.warning-card,
.panel {
  border: 1px solid rgba(255, 205, 115, 0.18);
  border-radius: 24px;
  background: rgba(8, 12, 20, 0.9);
  box-shadow: 0 18px 40px rgba(0, 0, 0, 0.26);
}

.hero-card {
  padding: 28px;
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
}

.eyebrow,
.section-label {
  text-transform: uppercase;
  letter-spacing: 0.18em;
  color: #ffcd73;
  font-size: 0.8rem;
}

.hero-card h1,
.panel h2 {
  margin: 10px 0 8px;
  font-size: clamp(1.8rem, 3vw, 3rem);
  line-height: 1.05;
}

.subtitle,
.muted-copy,
.meta-row,
.request-reason {
  color: #d8d1c0;
  line-height: 1.5;
}

.ghost-link {
  color: #ffcd73;
  text-decoration: none;
  font-weight: 600;
}

.warning-card {
  padding: 18px 24px;
  display: grid;
  gap: 8px;
}

.panel {
  padding: 24px;
}

.panel-heading {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
  margin-bottom: 18px;
}

.dashboard-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 20px;
}

.accounts-panel {
  grid-column: span 2;
}

.form-stack,
.detail-block,
.request-card,
.account-card,
.binding-card {
  display: grid;
  gap: 14px;
}

.field-group {
  display: grid;
  gap: 8px;
}

.field-group label {
  font-weight: 600;
  color: #f7f0de;
}

.input-field {
  width: 100%;
  border-radius: 14px;
  border: 1px solid rgba(255, 205, 115, 0.18);
  background: rgba(255, 255, 255, 0.04);
  color: #f7f0de;
  padding: 12px 14px;
  font: inherit;
}

.text-area {
  min-height: 110px;
  resize: vertical;
}

.primary-button,
.secondary-button,
.ghost-button,
.danger-button {
  border: none;
  border-radius: 14px;
  padding: 12px 16px;
  font: inherit;
  font-weight: 700;
  cursor: pointer;
}

.primary-button {
  background: linear-gradient(135deg, #ffcd73 0%, #ff9a62 100%);
  color: #1a1210;
}

.secondary-button {
  background: rgba(255, 255, 255, 0.08);
  color: #f7f0de;
}

.ghost-button {
  background: transparent;
  color: #ffcd73;
  border: 1px solid rgba(255, 205, 115, 0.26);
}

.danger-button {
  background: linear-gradient(135deg, #ff7d7d 0%, #ff5252 100%);
  color: #220c0c;
}

.inline-actions {
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
}

.wrap-actions {
  flex-wrap: wrap;
}

.small-button {
  padding: 10px 12px;
  font-size: 0.92rem;
}

.metric-row,
.wallet-pill-row {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.wallet-row {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.metric-row > div {
  min-width: 180px;
  display: grid;
  gap: 6px;
}

.metric-row span,
.account-card span {
  color: #a79f90;
}

.card-topline {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  align-items: center;
}

.request-card,
.account-card,
.binding-card {
  padding: 16px;
  border-radius: 18px;
  border: 1px solid rgba(255, 205, 115, 0.12);
  background: rgba(255, 255, 255, 0.03);
}

.invite-code {
  font-size: 1.5rem;
  letter-spacing: 0.08em;
  color: #ffcd73;
  word-break: break-all;
}

.wallet-pill {
  display: inline-flex;
  padding: 8px 10px;
  border-radius: 999px;
  background: rgba(255, 205, 115, 0.12);
  color: #ffdfb1;
  font-size: 0.88rem;
  overflow-wrap: anywhere;
}

.detail-line {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.detail-value {
  overflow-wrap: anywhere;
}

.empty-state {
  color: #b9b3a6;
  line-height: 1.5;
}

.status-message {
  line-height: 1.5;
}

.success {
  color: #8df5a6;
}

.error {
  color: #ff9b9b;
}

@media (max-width: 900px) {
  .hero-card,
  .panel-heading {
    flex-direction: column;
  }

  .dashboard-grid {
    grid-template-columns: 1fr;
  }

  .accounts-panel {
    grid-column: span 1;
  }
}

@media (max-width: 620px) {
  .admin-shell {
    padding: 22px 12px 40px;
  }

  .hero-card,
  .warning-card,
  .panel {
    border-radius: 18px;
  }

  .hero-card,
  .panel,
  .warning-card {
    padding: 16px;
  }

  .primary-button,
  .secondary-button,
  .ghost-button,
  .danger-button {
    width: 100%;
  }

  .inline-actions,
  .metric-row,
  .wallet-pill-row,
  .detail-line {
    display: grid;
    grid-template-columns: minmax(0, 1fr);
  }

  .wallet-row {
    display: grid;
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
