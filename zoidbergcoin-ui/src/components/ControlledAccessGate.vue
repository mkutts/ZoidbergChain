<template>
  <div class="access-shell">
    <PublicDemoBanner />
    <section class="access-card">
      <p class="eyebrow">Controlled Testnet Access</p>
      <p v-if="accessLabel" class="access-label">{{ accessLabel }}</p>
      <h1>ZoidbergChain is currently a controlled testnet.</h1>
      <p class="lead">
        Access is invite-only while we test voting, rewards, and network safety. Test ZOID has no real monetary value, and this does not represent mainnet.
      </p>

      <div class="rules-panel">
        <p class="section-label">Allowlist / Beta Eligibility Rules</p>
        <p class="wallet-note">
          ZoidbergChain is in a controlled beta. App access, submissions, voting, and rewards can require admin approval, an allowlist entry, a verified wallet, and good standing while we limit spam during testing.
        </p>
        <ul class="rules-list">
          <li>The beta is controlled and invite-only.</li>
          <li>Submissions currently require controlled beta access plus a verified wallet.</li>
          <li>Voting and rewards can still have separate review eligibility rules.</li>
          <li>Admins can grant temporary overrides for early testers.</li>
          <li>Test ZOID is only for testing and has no real monetary value.</li>
        </ul>
      </div>

      <div class="entry-switch">
        <button
          type="button"
          class="entry-btn"
          :class="{ active: entryMode === 'new' }"
          @click="setEntryMode('new')"
        >
          New User
        </button>
        <button
          type="button"
          class="entry-btn"
          :class="{ active: entryMode === 'returning' }"
          @click="setEntryMode('returning')"
        >
          Returning Approved User
        </button>
      </div>

      <p v-if="mobileWalletSupport.helperText" class="status info">{{ mobileWalletSupport.helperText }}</p>
      <p v-if="mobileWalletSupport.noProviderMessage" class="status warning">{{ mobileWalletSupport.noProviderMessage }}</p>

      <div v-if="mobileWalletSupport.shouldShowOpenInMetaMask" class="mobile-open-card">
        <a
          :href="mobileWalletSupport.openInMetaMaskUrl"
          class="secondary-btn meta-mask-link"
          @click="persistGateState"
        >
          Open in MetaMask
        </a>
        <p class="mobile-open-note">
          Open the current page in MetaMask Mobile so wallet connection and signing can continue there.
        </p>
      </div>

      <div v-if="entryMode === 'returning'" class="panel-stack">
        <div class="returning-panel">
          <p class="section-label">Returning Approved Wallet</p>
          <h2>{{ returningWalletGuidance.headline }}</h2>
          <p class="wallet-note">{{ returningWalletGuidance.detail }}</p>
          <p class="wallet-line"><strong>Wallet status:</strong> {{ walletStatusText }}</p>
          <p class="wallet-note">{{ walletNextStepText }}</p>

          <p v-if="interruptedWalletMessage" class="status warning">{{ interruptedWalletMessage }}</p>
          <p v-if="returningStatusMessage" class="status" :class="returningStatusClass">{{ returningStatusMessage }}</p>

          <div class="wallet-actions">
            <button
              v-if="accessActionState.showConnect"
              type="button"
              class="primary-btn"
              @click="continueReturningFlow"
              :disabled="wallet.state.connectionStatus === 'connecting'"
            >
              {{ wallet.state.connectionStatus === 'connecting' ? 'Connecting...' : returningWalletGuidance.actionLabel }}
            </button>
            <button
              v-else-if="accessActionState.showVerify"
              type="button"
              class="primary-btn"
              @click="continueReturningFlow"
              :disabled="wallet.state.connectionStatus === 'verifying'"
            >
              {{ wallet.state.connectionStatus === 'verifying' ? 'Verifying...' : returningWalletGuidance.actionLabel }}
            </button>
            <button
              v-else-if="wallet.state.isVerifiedSession && !access.state.me?.access_granted"
              type="button"
              class="secondary-btn"
              @click="refreshReturningAccess"
            >
              {{ returningWalletGuidance.actionLabel }}
            </button>
            <button
              v-if="showRetryButton"
              type="button"
              class="secondary-btn"
              @click="retryPendingWalletAction"
            >
              Retry Wallet Step
            </button>
            <button
              type="button"
              class="ghost-btn"
              @click="setEntryMode('new')"
            >
              I Need a New Invite
            </button>
          </div>
        </div>
      </div>

      <template v-else>
        <div class="mode-switch">
          <button
            type="button"
            class="mode-btn"
            :class="{ active: newUserMode === 'invite' }"
            @click="setNewUserMode('invite')"
          >
            Enter Invite Code
          </button>
          <button
            v-if="requestsEnabled"
            type="button"
            class="mode-btn"
            :class="{ active: newUserMode === 'request' }"
            @click="setNewUserMode('request')"
          >
            Request Access
          </button>
        </div>

        <div v-if="newUserMode === 'invite'" class="panel-stack">
          <label class="field">
            <span>Invite / Access Code</span>
            <input v-model.trim="inviteCode" type="text" placeholder="ZC-..." autocomplete="one-time-code" />
          </label>
          <button type="button" class="primary-btn" @click="login" :disabled="access.state.isLoggingIn || !inviteCode">
            {{ access.state.isLoggingIn ? 'Checking Invite...' : 'Use Invite Code' }}
          </button>
          <p v-if="inviteAcceptedMessage" class="status success">{{ inviteAcceptedMessage }}</p>

          <div class="wallet-box">
            <p class="section-label">Wallet Bind</p>
            <p class="wallet-line"><strong>Wallet status:</strong> {{ walletStatusText }}</p>
            <p class="wallet-note">{{ walletNextStepText }}</p>
            <p v-if="interruptedWalletMessage" class="status warning">{{ interruptedWalletMessage }}</p>
            <div class="wallet-actions">
              <button
                v-if="accessActionState.showConnect"
                type="button"
                class="secondary-btn"
                @click="connectWallet"
                :disabled="wallet.state.connectionStatus === 'connecting'"
              >
                {{ wallet.state.connectionStatus === 'connecting' ? 'Connecting...' : 'Connect MetaMask' }}
              </button>
              <button
                v-else-if="accessActionState.showVerify"
                type="button"
                class="secondary-btn"
                @click="verifyWallet"
                :disabled="wallet.state.connectionStatus === 'verifying'"
              >
                {{ wallet.state.connectionStatus === 'verifying' ? 'Verifying...' : 'Verify Wallet' }}
              </button>
              <button
                v-else-if="accessActionState.showBind"
                type="button"
                class="primary-btn"
                @click="bindWallet"
                :disabled="access.state.isBindingWallet"
              >
                {{ access.state.isBindingWallet ? 'Binding Wallet...' : 'Bind Verified Wallet' }}
              </button>
              <button
                v-if="showRetryButton"
                type="button"
                class="secondary-btn"
                @click="retryPendingWalletAction"
              >
                Retry Wallet Step
              </button>
            </div>
          </div>
        </div>

        <form v-else-if="requestsEnabled" class="panel-stack" @submit.prevent="submitRequest">
          <label class="field">
            <span>Name</span>
            <input v-model.trim="requestForm.name" type="text" required />
          </label>
          <label class="field">
            <span>Email</span>
            <input v-model.trim="requestForm.email" type="email" required />
          </label>
          <label class="field">
            <span>Organization / Social Handle (Optional)</span>
            <input v-model.trim="requestForm.handle" type="text" />
          </label>
          <label class="field">
            <span>Reason For Access</span>
            <textarea v-model.trim="requestForm.reason" rows="3" required />
          </label>
          <label class="field">
            <span>Notes (Optional)</span>
            <textarea v-model.trim="requestForm.notes" rows="3" />
          </label>
          <button type="submit" class="primary-btn" :disabled="access.state.isSubmittingRequest">
            {{ access.state.isSubmittingRequest ? 'Submitting Request...' : 'Submit Access Request' }}
          </button>
        </form>

        <div v-else class="panel-stack">
          <p class="status">
            New access requests are currently disabled on this node. Use an approved invite code from the operator to enter the controlled testnet.
          </p>
        </div>
      </template>

      <section v-if="shouldShowEligibilityStatus" class="rules-panel">
        <p class="section-label">Why Am I Blocked?</p>
        <p v-if="eligibilityHeadline" class="status" :class="eligibilityTone">{{ eligibilityHeadline }}</p>
        <p v-if="primaryBlockedReason" class="wallet-note">{{ primaryBlockedReason }}</p>
        <div v-if="accessRuleChecks.length" class="eligibility-checklist">
          <div
            v-for="rule in accessRuleChecks"
            :key="`${rule.scope}-${rule.rule_id}`"
            class="eligibility-rule"
            :class="{ pass: rule.passed, fail: rule.required && !rule.passed }"
          >
            <strong>{{ rule.label }}</strong>
            <p class="wallet-note">{{ rule.description }}</p>
            <p class="wallet-note eligibility-rule-value">
              Current: {{ rule.current_value ?? 'Not available' }}
              <span v-if="rule.required_value !== null && rule.required_value !== undefined"> | Needed: {{ rule.required_value }}</span>
            </p>
          </div>
        </div>
        <p v-for="step in nextSteps" :key="step" class="wallet-note">{{ step }}</p>
        <p v-if="activeOverrideMessage" class="status success">{{ activeOverrideMessage }}</p>
      </section>

      <section v-if="canRequestOverride" class="rules-panel">
        <div class="card-heading-inline">
          <div>
            <p class="section-label">Request an Override</p>
            <p class="wallet-note">
              If you were invited or approved but still cannot access something, send a focused override request for this controlled beta.
            </p>
          </div>
          <button type="button" class="ghost-btn" @click="showOverrideForm = !showOverrideForm">
            {{ showOverrideForm ? 'Hide Override Form' : 'Request an Override' }}
          </button>
        </div>

        <form v-if="showOverrideForm" class="panel-stack" @submit.prevent="submitOverride">
          <label class="field">
            <span>Requested Scope</span>
            <select v-model="overrideForm.requested_scope" class="field-select">
              <option value="access">Access Allowlist</option>
              <option value="review">Review Eligibility Allowlist</option>
              <option value="voting">Voting Override</option>
              <option value="rewards">Rewards Override</option>
              <option value="all_beta">All Beta Permissions</option>
            </select>
          </label>
          <label class="field">
            <span>Name (Optional)</span>
            <input v-model.trim="overrideForm.name" type="text" />
          </label>
          <label class="field">
            <span>Email (Optional)</span>
            <input v-model.trim="overrideForm.email" type="email" />
          </label>
          <label class="field">
            <span>Handle (Optional)</span>
            <input v-model.trim="overrideForm.handle" type="text" />
          </label>
          <label class="field">
            <span>Why do you need an override?</span>
            <textarea v-model.trim="overrideForm.reason" rows="3" required />
          </label>
          <button type="submit" class="primary-btn" :disabled="access.state.isSubmittingOverrideRequest || !overrideForm.reason">
            {{ access.state.isSubmittingOverrideRequest ? 'Submitting Override Request...' : 'Submit Override Request' }}
          </button>
        </form>
      </section>

      <p v-if="access.state.successMessage" class="status success">{{ access.state.successMessage }}</p>
      <p v-if="wallet.state.errorMessage" class="status error">{{ wallet.state.errorMessage }}</p>
      <p v-if="access.state.errorMessage" class="status error">{{ access.state.errorMessage }}</p>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue';
import PublicDemoBanner from './PublicDemoBanner.vue';
import { useWallet } from '../services/wallet';
import { useAccess } from '../services/access';
import {
  getAccessGateWalletStatusText,
  getControlledAccessActionState,
  getControlledAccessNextStepText,
} from '../utils/controlledAccessUi.js';
import {
  getEligibilityRuleChecks,
  getFailedRequiredRuleChecks,
} from '../utils/eligibilityChecklist.js';
import {
  buildReturningWalletGuidance,
  describeWalletSupport,
} from '../utils/mobileWallet.js';

const emit = defineEmits(['unlocked']);

const ACCESS_GATE_STATE_KEY = 'zoidberg:access-gate-state';
const wallet = useWallet();
const access = useAccess();
const entryMode = ref('new');
const newUserMode = ref('invite');
const inviteCode = ref('');
const interruptedWalletMessage = ref('');
const pendingWalletAction = ref('');
const requestForm = ref({
  name: '',
  email: '',
  handle: '',
  reason: '',
  notes: '',
});
const overrideForm = ref({
  requested_scope: 'access',
  name: '',
  email: '',
  handle: '',
  reason: '',
});
const showOverrideForm = ref(false);
const mobileWalletSupport = ref({
  isMobileDevice: false,
  hasInjectedProvider: false,
  isMetaMaskMobileBrowser: false,
  helperText: '',
  noProviderMessage: '',
  openInMetaMaskUrl: '',
  shouldShowOpenInMetaMask: false,
});

function getStorage() {
  if (typeof window === 'undefined') {
    return null;
  }
  try {
    return window.localStorage || null;
  } catch {
    return null;
  }
}

function refreshMobileWalletSupport() {
  mobileWalletSupport.value = describeWalletSupport({
    userAgent: typeof navigator === 'undefined' ? '' : navigator.userAgent,
    ethereum: typeof window === 'undefined' ? null : window.ethereum,
    currentUrl: typeof window === 'undefined' ? '' : window.location.href,
  });
}

function persistGateState() {
  const storage = getStorage();
  if (!storage) {
    return;
  }
  storage.setItem(
    ACCESS_GATE_STATE_KEY,
    JSON.stringify({
      entryMode: entryMode.value,
      newUserMode: newUserMode.value,
      inviteCode: inviteCode.value,
      pendingWalletAction: pendingWalletAction.value,
      interruptedWalletMessage: interruptedWalletMessage.value,
    }),
  );
}

function restoreGateState() {
  const storage = getStorage();
  if (!storage) {
    return;
  }
  const raw = storage.getItem(ACCESS_GATE_STATE_KEY);
  if (!raw) {
    return;
  }
  try {
    const parsed = JSON.parse(raw);
    entryMode.value = parsed.entryMode === 'returning' ? 'returning' : 'new';
    newUserMode.value = parsed.newUserMode === 'request' ? 'request' : 'invite';
    inviteCode.value = String(parsed.inviteCode || '');
    pendingWalletAction.value = String(parsed.pendingWalletAction || '');
    interruptedWalletMessage.value = String(parsed.interruptedWalletMessage || '');
  } catch {
    // Ignore malformed local gate state.
  }
}

function setPendingWalletAction(action, message) {
  pendingWalletAction.value = action;
  interruptedWalletMessage.value = message;
  persistGateState();
}

function clearPendingWalletAction() {
  pendingWalletAction.value = '';
  interruptedWalletMessage.value = '';
  persistGateState();
}

function setEntryMode(mode) {
  entryMode.value = mode === 'returning' ? 'returning' : 'new';
}

function setNewUserMode(mode) {
  newUserMode.value = mode === 'request' ? 'request' : 'invite';
}

const accessMode = computed(() => (entryMode.value === 'returning' ? 'returning' : 'login'));

const accessActionState = computed(() => getControlledAccessActionState({
  mode: accessMode.value,
  walletState: wallet.state,
  accessState: access.state,
}));

const walletStatusText = computed(() => getAccessGateWalletStatusText(wallet.state));

const walletNextStepText = computed(() => getControlledAccessNextStepText({
  mode: accessMode.value,
  walletState: wallet.state,
  accessState: access.state,
}));

const returningWalletGuidance = computed(() => buildReturningWalletGuidance({
  accessGranted: Boolean(access.state.me?.access_granted),
  walletBound: Boolean(access.state.me?.wallet_bound || access.state.me?.wallet_binding?.wallet_address),
  isVerifiedSession: wallet.state.isVerifiedSession,
  isConnected: wallet.state.isConnected,
}));

const walletAccountStatus = computed(
  () => String(access.state.me?.access_account?.status || '').trim().toLowerCase(),
);

const walletBindingStatus = computed(
  () => String(access.state.me?.wallet_binding?.status || '').trim().toLowerCase(),
);

const accessLabel = computed(
  () => access.state.publicStatus?.access_public_label || '',
);

const requestsEnabled = computed(
  () => access.state.publicStatus?.access_requests_enabled !== false,
);

const inviteAuthenticated = computed(
  () => accessActionState.value.inviteAuthenticated,
);

const inviteAcceptedMessage = computed(() => {
  if (!inviteAuthenticated.value || access.state.me?.wallet_bound) {
    return '';
  }
  return 'Invite accepted. Connect and verify your MetaMask wallet to bind this access account.';
});

const returningStatusMessage = computed(() => {
  if (!wallet.state.isVerifiedSession) {
    return '';
  }
  if (walletBindingStatus.value === 'revoked') {
    return 'This wallet binding was revoked. Request access or enter a fresh invite code from the operator.';
  }
  if (walletAccountStatus.value === 'suspended') {
    return 'This approved wallet belongs to a suspended access account. Contact the operator for reactivation.';
  }
  if (walletAccountStatus.value === 'revoked') {
    return 'This approved wallet belongs to a revoked access account. Contact the operator before trying again.';
  }
  if (access.state.me?.access_granted) {
    return 'Approved wallet verified. Unlocking the controlled testnet now.';
  }
  if (access.state.me?.wallet_session_authenticated) {
    return 'This wallet is not approved. Request access or enter an invite code.';
  }
  return '';
});

const returningStatusClass = computed(() => {
  if (access.state.me?.access_granted) {
    return 'success';
  }
  return 'error';
});

const showRetryButton = computed(
  () => Boolean(pendingWalletAction.value) && !access.state.me?.access_granted,
);
const shouldShowEligibilityStatus = computed(
  () => Boolean(access.state.eligibility || access.state.me?.blocked_reason || access.state.me?.allowlist_override_applied),
);
const accessRuleChecks = computed(
  () => getEligibilityRuleChecks(access.state.eligibility, ['access']),
);
const failedAccessRuleChecks = computed(
  () => getFailedRequiredRuleChecks(access.state.eligibility, ['access']),
);
const primaryBlockedReason = computed(
  () => access.state.eligibility?.blocked_reasons?.find((item) => item.scope === 'access')?.message
    || failedAccessRuleChecks.value[0]?.description
    || '',
);
const nextSteps = computed(
  () => Array.isArray(access.state.eligibility?.possible_next_steps) ? access.state.eligibility.possible_next_steps : [],
);
const activeOverrideMessage = computed(() => {
  const accessOverride = (access.state.eligibility?.allowlist_overrides_applied || []).find((item) => item.scope === 'access');
  if (!accessOverride) {
    return '';
  }
  return `An admin override is active for ${String(accessOverride.allowlist_scope || accessOverride.scope || 'this account').replace(/_/g, ' ')}.`;
});
const eligibilityHeadline = computed(() => {
  if (access.state.me?.access_granted) {
    return 'You are approved for app access.';
  }
  if (activeOverrideMessage.value) {
    return 'An admin override is active for this session.';
  }
  if (walletAccountStatus.value === 'suspended') {
    return 'You are blocked because this account is suspended.';
  }
  if (walletBindingStatus.value === 'revoked') {
    return 'You are blocked because this wallet binding was revoked.';
  }
  if (wallet.state.isVerifiedSession) {
    return 'Your wallet is connected but not approved yet.';
  }
  return 'Approval or an override may still be required.';
});
const eligibilityTone = computed(() => (access.state.me?.access_granted || activeOverrideMessage.value ? 'success' : 'warning'));
const canRequestOverride = computed(
  () => !access.state.me?.access_granted && Boolean(requestsEnabled.value || wallet.state.isVerifiedSession || inviteAuthenticated.value),
);

async function refreshAccessAndUnlock() {
  await access.refreshMe(wallet.getAuthorizationHeader());
  await access.refreshEligibility(wallet.getAuthorizationHeader());
  if (access.isAppUnlocked()) {
    clearPendingWalletAction();
    emit('unlocked');
  }
}

async function connectWallet() {
  refreshMobileWalletSupport();
  await wallet.detectMetaMask();
  refreshMobileWalletSupport();
  const result = await wallet.connectWallet();
  refreshMobileWalletSupport();
  if (result && wallet.state.isVerifiedSession) {
    await refreshAccessAndUnlock();
  }
}

async function verifyWallet() {
  setPendingWalletAction(
    'verify_wallet',
    'Wallet verification was interrupted. Reconnect the same approved wallet and try the signature again.',
  );
  const result = await wallet.verifyWallet();
  if (result && wallet.state.isVerifiedSession) {
    await refreshAccessAndUnlock();
  }
}

async function bindWallet() {
  setPendingWalletAction(
    'bind_wallet',
    'Wallet binding was interrupted. Return to this page, verify the same wallet again if needed, then retry binding.',
  );
  const result = await access.bindWallet(wallet.getAuthorizationHeader());
  if (result) {
    await refreshAccessAndUnlock();
  }
}

async function login() {
  const result = await access.loginWithCode(inviteCode.value);
  if (result) {
    inviteCode.value = '';
    persistGateState();
    if (wallet.state.isVerifiedSession) {
      await refreshAccessAndUnlock();
    }
  }
}

async function continueReturningFlow() {
  if (!wallet.state.isConnected) {
    await connectWallet();
    return;
  }
  if (!wallet.state.isVerifiedSession) {
    await verifyWallet();
    return;
  }
  await refreshAccessAndUnlock();
}

async function refreshReturningAccess() {
  await refreshAccessAndUnlock();
}

async function retryPendingWalletAction() {
  if (pendingWalletAction.value === 'bind_wallet') {
    await bindWallet();
    return;
  }
  if (!wallet.state.isConnected) {
    await connectWallet();
    return;
  }
  await verifyWallet();
}

async function submitRequest() {
  const result = await access.submitAccessRequest({ ...requestForm.value });
  if (result) {
    requestForm.value = {
      name: '',
      email: '',
      handle: '',
      reason: '',
      notes: '',
    };
  }
}

async function submitOverride() {
  const result = await access.submitOverrideRequest(
    {
      ...overrideForm.value,
      wallet_address: wallet.state.verifiedWalletAddress || null,
      access_account_id: access.state.me?.access_account_id || access.state.me?.access_account?.access_account_id || null,
      current_page: '/access',
      detected_blocked_reason: access.state.eligibility?.blocked_reasons?.[0]?.reason || access.state.me?.blocked_reason || null,
    },
    wallet.getAuthorizationHeader(),
  );
  if (result) {
    overrideForm.value = {
      requested_scope: 'access',
      name: '',
      email: '',
      handle: '',
      reason: '',
    };
    showOverrideForm.value = false;
  }
}

watch([entryMode, newUserMode, inviteCode, pendingWalletAction, interruptedWalletMessage], () => {
  persistGateState();
});

watch(
  () => access.state.me?.access_granted,
  (accessGranted) => {
    if (accessGranted) {
      clearPendingWalletAction();
    }
  },
);

onMounted(() => {
  restoreGateState();
  refreshMobileWalletSupport();
});
</script>

<style scoped>
.access-shell {
  min-height: 100vh;
  padding: 32px 16px 48px;
  background:
    radial-gradient(circle at top, rgba(216, 93, 45, 0.18), transparent 42%),
    linear-gradient(180deg, #0f1724 0%, #05070d 100%);
}

.access-card {
  width: min(760px, 100%);
  margin: 0 auto;
  padding: 28px;
  border-radius: 24px;
  border: 1px solid rgba(255, 205, 115, 0.22);
  background: rgba(8, 12, 20, 0.92);
  color: #f7f0de;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.35);
}

.eyebrow,
.section-label {
  margin: 0 0 10px;
  color: #ffcd73;
  font-size: 0.82rem;
  letter-spacing: 0.18em;
  text-transform: uppercase;
}

.access-label {
  margin: 0 0 10px;
  color: #9fd3ff;
  font-size: 0.95rem;
}

h1,
h2 {
  margin: 0 0 12px;
  line-height: 1.1;
}

h1 {
  font-size: 2rem;
}

h2 {
  font-size: 1.35rem;
}

.lead,
.wallet-note,
.mobile-open-note {
  color: #dfd7c6;
  line-height: 1.6;
}

.lead {
  margin: 0 0 22px;
}

.eligibility-checklist {
  display: grid;
  gap: 12px;
  margin: 14px 0;
}

.eligibility-rule {
  padding: 12px;
  border-radius: 14px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.03);
}

.eligibility-rule.pass {
  border-color: rgba(114, 224, 153, 0.3);
}

.eligibility-rule.fail {
  border-color: rgba(255, 145, 117, 0.35);
}

.eligibility-rule-value {
  overflow-wrap: anywhere;
  word-break: break-word;
}

.entry-switch,
.mode-switch,
.wallet-actions {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.entry-switch,
.mode-switch {
  margin-bottom: 18px;
}

.entry-btn,
.mode-btn,
.primary-btn,
.secondary-btn,
.ghost-btn,
.meta-mask-link {
  border: none;
  border-radius: 14px;
  padding: 12px 16px;
  font: inherit;
  cursor: pointer;
  text-decoration: none;
}

.entry-btn,
.mode-btn,
.ghost-btn {
  background: rgba(255, 255, 255, 0.07);
  color: #f7f0de;
}

.entry-btn.active,
.mode-btn.active {
  background: #ffcd73;
  color: #20150a;
}

.primary-btn {
  background: linear-gradient(135deg, #ffcd73 0%, #ff8f5a 100%);
  color: #20150a;
  font-weight: 700;
}

.secondary-btn,
.meta-mask-link {
  background: rgba(116, 192, 252, 0.12);
  color: #d8ecff;
  border: 1px solid rgba(116, 192, 252, 0.18);
}

.ghost-btn {
  border: 1px solid rgba(255, 205, 115, 0.18);
}

.panel-stack {
  display: grid;
  gap: 16px;
}

.field {
  display: grid;
  gap: 8px;
}

.field span {
  font-size: 0.92rem;
  color: #d9cfba;
}

.field input,
.field textarea {
  width: 100%;
  min-height: 48px;
  border: 1px solid rgba(255, 205, 115, 0.18);
  border-radius: 14px;
  padding: 12px 14px;
  background: rgba(255, 255, 255, 0.04);
  color: #f7f0de;
  font: inherit;
}

.field textarea {
  min-height: 112px;
  resize: vertical;
}

.wallet-box,
.returning-panel,
.mobile-open-card,
.rules-panel {
  padding: 16px;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.04);
}

.returning-panel,
.mobile-open-card,
.rules-panel {
  border: 1px solid rgba(255, 205, 115, 0.14);
}

.rules-list {
  margin: 12px 0 0 18px;
  color: #dfd7c6;
  line-height: 1.6;
}

.card-heading-inline {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}

.field-select {
  width: 100%;
  min-height: 48px;
  border: 1px solid rgba(255, 205, 115, 0.18);
  border-radius: 14px;
  padding: 12px 14px;
  background: rgba(255, 255, 255, 0.04);
  color: #f7f0de;
  font: inherit;
}

.mobile-open-card {
  display: grid;
  gap: 12px;
  margin-bottom: 18px;
}

.meta-mask-link {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: fit-content;
}

.wallet-line,
.wallet-note,
.status {
  margin: 0;
}

.status {
  line-height: 1.5;
}

.status + .status {
  margin-top: 12px;
}

.status.success {
  color: #9df3b0;
}

.status.error {
  color: #ff9f9f;
}

.status.warning {
  color: #ffd884;
}

.status.info {
  color: #9fd3ff;
}

@media (max-width: 720px) {
  .access-shell {
    padding: 22px 12px 34px;
  }

  .access-card {
    padding: 20px 16px;
    border-radius: 20px;
  }

  h1 {
    font-size: 1.65rem;
  }

  h2 {
    font-size: 1.18rem;
  }

  .entry-switch,
  .mode-switch,
  .wallet-actions {
    display: grid;
    grid-template-columns: minmax(0, 1fr);
  }

  .entry-btn,
  .mode-btn,
  .primary-btn,
  .secondary-btn,
  .ghost-btn,
  .meta-mask-link {
    width: 100%;
    text-align: center;
  }

  .meta-mask-link {
    justify-content: center;
  }
}

@media (max-width: 430px) {
  .access-shell {
    padding-inline: 10px;
  }

  .access-card {
    padding: 18px 14px;
  }

  .eyebrow,
  .section-label {
    font-size: 0.76rem;
    letter-spacing: 0.14em;
  }

  .lead,
  .wallet-note,
  .mobile-open-note,
  .status {
    font-size: 0.95rem;
  }
}
</style>
