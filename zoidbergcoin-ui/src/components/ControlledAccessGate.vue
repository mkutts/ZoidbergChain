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

      <div class="mode-switch">
        <button type="button" class="mode-btn" :class="{ active: mode === 'returning' }" @click="mode = 'returning'">Returning Approved User</button>
        <button type="button" class="mode-btn" :class="{ active: mode === 'login' }" @click="mode = 'login'">Enter Invite Code / Login</button>
        <button
          v-if="requestsEnabled"
          type="button"
          class="mode-btn"
          :class="{ active: mode === 'request' }"
          @click="mode = 'request'"
        >
          Request Access
        </button>
      </div>

      <div v-if="mode === 'returning'" class="panel-stack">
        <p class="status returning-copy">
          Returning user? Connect your approved wallet and sign the verification challenge. You should not need to reuse a redeemed invite code.
        </p>

        <div class="wallet-box">
          <p class="wallet-line"><strong>Wallet status:</strong> {{ walletStatusText }}</p>
          <p class="wallet-note">{{ walletNextStepText }}</p>
          <div class="wallet-actions">
            <button
              v-if="actionState.showConnect"
              type="button"
              class="secondary-btn"
              @click="connectWallet"
              :disabled="wallet.state.connectionStatus === 'connecting'"
            >
              {{ wallet.state.connectionStatus === 'connecting' ? 'Connecting...' : 'Connect Approved Wallet' }}
            </button>
            <button
              v-else-if="actionState.showVerify"
              type="button"
              class="secondary-btn"
              @click="verifyWallet"
              :disabled="wallet.state.connectionStatus === 'verifying'"
            >
              {{ wallet.state.connectionStatus === 'verifying' ? 'Verifying...' : 'Verify Connected Wallet' }}
            </button>
          </div>
        </div>
      </div>

      <div v-else-if="mode === 'login'" class="panel-stack">
        <label class="field">
          <span>Invite / Access Code</span>
          <input v-model.trim="inviteCode" type="text" placeholder="ZC-..." />
        </label>
        <button type="button" class="primary-btn" @click="login" :disabled="access.state.isLoggingIn || !inviteCode">
          {{ access.state.isLoggingIn ? 'Checking Invite...' : 'Use Invite Code' }}
        </button>
        <p v-if="inviteAcceptedMessage" class="status success">{{ inviteAcceptedMessage }}</p>

        <div class="wallet-box">
          <p class="wallet-line"><strong>Wallet status:</strong> {{ walletStatusText }}</p>
          <p class="wallet-note">{{ walletNextStepText }}</p>
          <div class="wallet-actions">
            <button
              v-if="actionState.showConnect"
              type="button"
              class="secondary-btn"
              @click="connectWallet"
              :disabled="wallet.state.connectionStatus === 'connecting'"
            >
              {{ wallet.state.connectionStatus === 'connecting' ? 'Connecting...' : 'Connect MetaMask' }}
            </button>
            <button
              v-else-if="actionState.showVerify"
              type="button"
              class="secondary-btn"
              @click="verifyWallet"
              :disabled="wallet.state.connectionStatus === 'verifying'"
            >
              {{ wallet.state.connectionStatus === 'verifying' ? 'Verifying...' : 'Verify Wallet' }}
            </button>
            <button
              v-else-if="actionState.showBind"
              type="button"
              class="primary-btn"
              @click="bindWallet"
              :disabled="access.state.isBindingWallet"
            >
              {{ access.state.isBindingWallet ? 'Binding Wallet...' : 'Bind Verified Wallet' }}
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

      <p v-if="access.state.successMessage" class="status success">{{ access.state.successMessage }}</p>
      <p v-if="wallet.state.errorMessage" class="status error">{{ wallet.state.errorMessage }}</p>
      <p v-if="access.state.errorMessage" class="status error">{{ access.state.errorMessage }}</p>
    </section>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue';
import PublicDemoBanner from './PublicDemoBanner.vue';
import { useWallet } from '../services/wallet';
import { useAccess } from '../services/access';
import {
  getAccessGateWalletStatusText,
  getControlledAccessActionState,
  getControlledAccessNextStepText,
} from '../utils/controlledAccessUi.js';

const emit = defineEmits(['unlocked']);

const wallet = useWallet();
const access = useAccess();
const mode = ref('returning');
const inviteCode = ref('');
const requestForm = ref({
  name: '',
  email: '',
  handle: '',
  reason: '',
  notes: '',
});

const accessLabel = computed(
  () => access.state.publicStatus?.access_public_label || '',
);

const requestsEnabled = computed(
  () => access.state.publicStatus?.access_requests_enabled !== false,
);

const inviteAuthenticated = computed(
  () => Boolean(access.state.me?.invite_authenticated || access.state.accessSessionToken),
);

const actionState = computed(() => getControlledAccessActionState({
  mode: mode.value,
  walletState: wallet.state,
  accessState: access.state,
}));

const walletStatusText = computed(
  () => getAccessGateWalletStatusText(wallet.state),
);

const inviteAcceptedMessage = computed(() => {
  if (!inviteAuthenticated.value || access.state.me?.wallet_bound) {
    return '';
  }
  return 'Invite accepted. Connect and verify your MetaMask wallet to bind this access account.';
});

const walletNextStepText = computed(() => getControlledAccessNextStepText({
  mode: mode.value,
  walletState: wallet.state,
  accessState: access.state,
}));

async function connectWallet() {
  await wallet.detectMetaMask();
  await wallet.connectWallet();
}

async function verifyWallet() {
  await wallet.verifyWallet();
  if (wallet.state.isVerifiedSession) {
    await access.refreshMe(wallet.getAuthorizationHeader());
    if (access.isAppUnlocked()) {
      emit('unlocked');
    }
  }
}

async function login() {
  const result = await access.loginWithCode(inviteCode.value);
  if (result && wallet.state.isVerifiedSession) {
    await access.refreshMe(wallet.getAuthorizationHeader());
  }
}

async function bindWallet() {
  const result = await access.bindWallet(wallet.getAuthorizationHeader());
  if (result && access.isAppUnlocked()) {
    emit('unlocked');
  }
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

.eyebrow {
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

h1 {
  margin: 0 0 12px;
  font-size: 2rem;
  line-height: 1.1;
}

.lead {
  margin: 0 0 22px;
  line-height: 1.6;
  color: #dfd7c6;
}

.mode-switch {
  display: flex;
  gap: 12px;
  margin-bottom: 20px;
  flex-wrap: wrap;
}

.mode-btn,
.primary-btn,
.secondary-btn {
  border: none;
  border-radius: 12px;
  padding: 12px 16px;
  font: inherit;
  cursor: pointer;
}

.mode-btn {
  background: rgba(255, 255, 255, 0.07);
  color: #f7f0de;
}

.mode-btn.active {
  background: #ffcd73;
  color: #20150a;
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
  border: 1px solid rgba(255, 205, 115, 0.18);
  border-radius: 12px;
  padding: 12px 14px;
  background: rgba(255, 255, 255, 0.04);
  color: #f7f0de;
}

.primary-btn {
  background: linear-gradient(135deg, #ffcd73 0%, #ff8f5a 100%);
  color: #20150a;
  font-weight: 700;
}

.secondary-btn {
  background: rgba(116, 192, 252, 0.12);
  color: #d8ecff;
  border: 1px solid rgba(116, 192, 252, 0.18);
}

.wallet-box {
  padding: 16px;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.04);
}

.wallet-line,
.wallet-note {
  margin: 0 0 10px;
}

.wallet-actions {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.status {
  margin-top: 16px;
  line-height: 1.5;
}

.status.success {
  color: #9df3b0;
}

.status.error {
  color: #ff9f9f;
}

@media (max-width: 720px) {
  .access-card {
    padding: 22px 18px;
  }

  h1 {
    font-size: 1.6rem;
  }
}
</style>
