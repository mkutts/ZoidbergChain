<template>
  <div class="access-shell">
    <PublicDemoBanner />
    <section class="access-card">
      <p class="eyebrow">Controlled Testnet Access</p>
      <p v-if="accessLabel" class="access-label">{{ accessLabel }}</p>
      <h1>Join the ZoidbergChain beta</h1>
      <p class="lead">
        ZoidbergChain is in controlled beta while we test submissions, originality voting, rewards, and wallet safety. Test ZOID has no real monetary value, and this is not mainnet.
      </p>
      <div class="top-feedback-cta">
        <button type="button" class="ghost-btn feedback-shortcut" @click="openFeedbackPanel">Send Feedback</button>
        <router-link to="/why-zoidbergcoin" class="ghost-btn feedback-shortcut">Beta Guide</router-link>
        <p class="wallet-note">Open the Beta Guide for setup help, or send feedback directly from this screen if something is broken or confusing.</p>
      </div>

      <div class="journey-grid">
        <article class="journey-card">
          <p class="section-label">I&apos;m New</p>
          <strong>Request beta access.</strong>
          <p class="wallet-note">Tell us why you want in, wait for approval, then use your invite once.</p>
        </article>
        <article class="journey-card">
          <p class="section-label">I Have an Invite</p>
          <strong>Use the code, then bind your wallet.</strong>
          <p class="wallet-note">Invite codes are one-time. After that, your approved wallet becomes your normal return path.</p>
        </article>
        <article class="journey-card">
          <p class="section-label">I&apos;m Returning</p>
          <strong>Connect your approved wallet.</strong>
          <p class="wallet-note">Reconnect the same wallet and sign a quick verification message to continue.</p>
        </article>
      </div>

      <div class="rules-panel">
        <p class="section-label">How Beta Access Works</p>
        <p class="wallet-note">
          Some actions need approval while the beta is small. Your invite, verified wallet, and account standing decide what you can do next.
        </p>
        <ul class="rules-list">
          <li>New testers can request access or use an invite code from the team.</li>
          <li>Approved testers receive a one-time invite code before binding their wallet.</li>
          <li>Returning testers usually only need their approved wallet and a fresh verification signature.</li>
          <li>Submitting content requires beta access plus a verified wallet.</li>
          <li>Voting and rewards can still have separate approval rules while we reduce spam.</li>
          <li>Test ZOID stays testnet-only and has no real monetary value.</li>
          <li>On mobile, use the MetaMask Mobile browser if your wallet is not detected.</li>
          <li>Never enter a seed phrase or private key anywhere in this app.</li>
        </ul>
      </div>

      <div class="rules-panel">
        <p class="section-label">Login Options</p>
        <div class="journey-grid onboarding-grid">
          <article
            v-for="option in onboardingOptions"
            :key="option.id"
            class="journey-card"
          >
            <p class="section-label">{{ option.availability === 'available' ? 'Available Now' : 'Coming Soon' }}</p>
            <strong>{{ option.title }}</strong>
            <p class="wallet-note">{{ option.description }}</p>
            <p v-if="option.warning" class="wallet-note">{{ option.warning }}</p>
          </article>
        </div>
      </div>

      <div class="entry-switch">
        <button
          type="button"
          class="entry-btn"
          :class="{ active: entryMode === 'new' }"
          @click="setEntryMode('new')"
        >
          I&apos;m New
        </button>
        <button
          type="button"
          class="entry-btn"
          :class="{ active: entryMode === 'returning' }"
          @click="setEntryMode('returning')"
        >
          Returning With My Approved Wallet
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
              I&apos;m New Here
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
            I Have an Invite
          </button>
          <button
            v-if="requestsEnabled"
            type="button"
            class="mode-btn"
            :class="{ active: newUserMode === 'request' }"
            @click="setNewUserMode('request')"
          >
            Request Beta Access
          </button>
        </div>

        <div v-if="newUserMode === 'invite'" class="panel-stack">
          <label class="field">
            <span>Invite Code</span>
            <input v-model.trim="inviteCode" type="text" placeholder="ZC-..." autocomplete="one-time-code" />
          </label>
          <button type="button" class="primary-btn" @click="login" :disabled="access.state.isLoggingIn || !inviteCode">
            {{ access.state.isLoggingIn ? 'Checking Invite...' : 'Continue With Invite' }}
          </button>
          <p v-if="inviteAcceptedMessage" class="status success">{{ inviteAcceptedMessage }}</p>

          <div class="wallet-box">
            <p class="section-label">Connect And Verify Your Wallet</p>
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
                {{ wallet.state.connectionStatus === 'connecting' ? 'Connecting...' : `Continue with ${wallet.state.providerLabel || 'MetaMask'}` }}
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
            <span>Organization Or Social Handle (Optional)</span>
            <input v-model.trim="requestForm.handle" type="text" />
          </label>
          <label class="field">
            <span>Why Would You Like Access?</span>
            <textarea v-model.trim="requestForm.reason" rows="3" required />
          </label>
          <label class="field">
            <span>Anything Else We Should Know? (Optional)</span>
            <textarea v-model.trim="requestForm.notes" rows="3" />
          </label>
          <button type="submit" class="primary-btn" :disabled="access.state.isSubmittingRequest">
            {{ access.state.isSubmittingRequest ? 'Sending Request...' : 'Send Access Request' }}
          </button>
        </form>

        <div v-else class="panel-stack">
          <p class="status">
            New requests are paused on this node right now. If you already have approval, use your invite code or return with your approved wallet.
          </p>
        </div>
      </template>

      <section v-if="shouldShowEligibilityStatus" class="rules-panel">
        <p class="section-label">What Is Blocking Me?</p>
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
            <p class="section-label">Still Blocked?</p>
            <p class="wallet-note">
              If you believe this wallet should already work, send a quick beta help request so an operator can review it.
            </p>
          </div>
          <button type="button" class="ghost-btn" @click="showOverrideForm = !showOverrideForm">
            {{ showOverrideForm ? 'Hide Beta Help Form' : 'Request Beta Help' }}
          </button>
        </div>

        <form v-if="showOverrideForm" class="panel-stack" @submit.prevent="submitOverride">
          <label class="field">
              <span>Requested Scope</span>
              <select v-model="overrideForm.requested_scope" class="field-select">
              <option value="access">App Access</option>
              <option value="review">Review Access</option>
              <option value="voting">Voting Access</option>
              <option value="rewards">Rewards Access</option>
              <option value="all_beta">Full Beta Access</option>
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
            {{ access.state.isSubmittingOverrideRequest ? 'Sending Beta Help Request...' : 'Send Beta Help Request' }}
          </button>
        </form>
      </section>

      <FeedbackPanel
        headline="Blocked or stuck? Send feedback."
        intro-copy="If wallet setup, allowlist access, mobile behavior, or beta rules are getting in your way, send a note directly from this screen."
        toggle-label="Open Feedback Form"
        entry-point="access_gate"
        :default-open="false"
        panel-id="feedback-panel"
      />

      <p v-if="access.state.successMessage" class="status success">{{ access.state.successMessage }}</p>
      <p v-if="wallet.state.errorMessage" class="status error">{{ wallet.state.errorMessage }}</p>
      <p v-if="access.state.errorMessage" class="status error">{{ access.state.errorMessage }}</p>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue';
import PublicDemoBanner from './PublicDemoBanner.vue';
import FeedbackPanel from './FeedbackPanel.vue';
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
import { getWalletOnboardingOptions } from '../utils/walletOnboarding.js';
import { requestFeedbackPanelOpen } from '../utils/feedbackPanel.js';

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
const onboardingOptions = getWalletOnboardingOptions();
const mobileWalletSupport = ref({
  primaryWalletProviderLabel: 'MetaMask',
  isMobileDevice: false,
  hasInjectedProvider: false,
  isMetaMaskMobileBrowser: false,
  helperText: '',
  noProviderMessage: '',
  openInMetaMaskUrl: '',
  shouldShowOpenInMetaMask: false,
});

function openFeedbackPanel() {
  requestFeedbackPanelOpen({
    panelId: 'feedback-panel',
    scrollIntoView: true,
  });
}

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
  return `Invite accepted. Connect ${wallet.state.providerLabel || 'MetaMask'}, verify the wallet, and bind it once to finish setup.`;
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
  return `Admin approval is active for ${String(accessOverride.allowlist_scope || accessOverride.scope || 'this account').replace(/_/g, ' ')}.`;
});
const eligibilityHeadline = computed(() => {
  if (access.state.me?.access_granted) {
    return 'You are approved for the beta app.';
  }
  if (activeOverrideMessage.value) {
    return 'Admin approval is active for this session.';
  }
  if (walletAccountStatus.value === 'suspended') {
    return 'This account is currently suspended.';
  }
  if (walletBindingStatus.value === 'revoked') {
    return 'This wallet connection was revoked.';
  }
  if (wallet.state.isVerifiedSession) {
    return 'Your wallet is verified, but beta approval is still missing.';
  }
  return 'You may still need approval before this wallet can continue.';
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

.top-feedback-cta {
  display: grid;
  gap: 10px;
  margin: 0 0 20px;
  padding: 14px 16px;
  border-radius: 18px;
  border: 1px solid rgba(255, 205, 115, 0.16);
  background: rgba(255, 205, 115, 0.06);
}

.journey-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin: 0 0 20px;
}

.onboarding-grid {
  margin: 12px 0 0;
}

.journey-card {
  padding: 16px;
  border-radius: 18px;
  border: 1px solid rgba(159, 211, 255, 0.16);
  background: rgba(159, 211, 255, 0.06);
  display: grid;
  gap: 8px;
}

.journey-card strong {
  color: #f7f0de;
}

.feedback-shortcut {
  text-decoration: none;
  text-align: center;
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
  .wallet-actions,
  .journey-grid {
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
