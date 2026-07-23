<template>
  <section class="wallet-panel">
    <div class="wallet-copy">
      <p class="wallet-label">Native Account</p>
      <h2>MetaMask-backed ZoidbergChain wallet</h2>
      <p class="wallet-note">
        MetaMask provides the signing key for your native ZoidbergChain account. Native ZOID lives on ZoidbergChain and does not appear in normal MetaMask yet.
      </p>
    </div>

    <div class="wallet-card" :class="{ connected: wallet.state.isConnected }">
      <p class="wallet-status">
        <span class="status-badge" :class="statusClass">{{ statusText }}</span>
      </p>

      <template v-if="wallet.state.isConnected">
        <p class="address-short">{{ shortenedAddress }}</p>
        <p class="address-full">{{ wallet.state.normalizedWalletAddress }}</p>
        <p v-if="wallet.state.isVerifiedSession" class="wallet-meta">Verified MetaMask-backed ZoidbergChain wallet. This session is the active native account identity for signed submissions, votes, rewards, and future transfer intents.</p>
        <p v-else-if="wallet.state.connectionStatus === 'expired'" class="wallet-meta">This wallet was connected before, but the verified session expired or changed. Verify again to restore the active native ZoidbergChain account identity.</p>
        <p v-else class="wallet-meta">Connected only at the browser level. Verify this wallet before using it as a native ZoidbergChain account identity.</p>
        <p v-if="wallet.state.chainId" class="wallet-meta">Chain ID: {{ wallet.state.chainId }}</p>
        <p v-if="wallet.state.sessionExpiresAt && wallet.state.isVerifiedSession" class="wallet-meta">
          Session expires at: {{ sessionExpiryLabel }}
        </p>

        <div v-if="wallet.state.isVerifiedSession" class="native-balance-card">
          <span class="native-balance-label">Native ZOID balance on ZoidbergChain</span>
          <strong class="native-balance-value">{{ nativeBalanceLabel }}</strong>
          <div v-if="balanceSummaryRows.length" class="wallet-summary-list">
            <div v-for="row in balanceSummaryRows" :key="row.label" class="wallet-summary-row">
              <span>{{ row.label }}</span>
              <strong>{{ row.value }}</strong>
            </div>
          </div>
          <p class="wallet-meta">Native ZOID does not appear in normal MetaMask yet.</p>
          <p class="wallet-meta">{{ balanceNote }}</p>
        </div>

        <div v-if="wallet.state.isVerifiedSession" class="reward-card">
          <div class="history-header">
            <span class="native-balance-label">Native ZoidbergChain account activity</span>
            <button
              type="button"
              class="wallet-btn secondary compact"
              @click="refreshAccountData"
              :disabled="isBalanceLoading || isRewardHistoryLoading || isTransferHistoryLoading"
            >
              {{ isBalanceLoading || isRewardHistoryLoading || isTransferHistoryLoading ? 'Refreshing Account...' : 'Refresh Account Data' }}
            </button>
          </div>
          <div v-if="accountSummaryRows.length" class="wallet-summary-list">
            <div v-for="row in accountSummaryRows" :key="row.label" class="wallet-summary-row">
              <span>{{ row.label }}</span>
              <strong>{{ row.value }}</strong>
            </div>
          </div>
          <p class="wallet-meta">
            Native accounts do not need to be pre-registered in the old dev wallet list. Your verified 0x address becomes a ZoidbergChain account when it submits, votes, receives rewards, or holds balance.
          </p>
        </div>

        <div v-if="wallet.state.isVerifiedSession" class="reward-card">
          <div class="history-header">
            <span class="native-balance-label">Native ZOID reward history</span>
            <button
              type="button"
              class="wallet-btn secondary compact"
              @click="refreshRewardHistory"
              :disabled="isRewardHistoryLoading"
            >
              {{ isRewardHistoryLoading ? 'Refreshing Rewards...' : 'Refresh Rewards' }}
            </button>
          </div>
          <p v-if="rewardError" class="wallet-error">{{ rewardError }}</p>
          <p v-else-if="!rewardHistory.length" class="wallet-meta">No native ZOID rewards yet.</p>
          <ul v-else class="history-list">
            <li v-for="reward in rewardHistory" :key="reward.block_hash || reward.submission_id || reward.minted_at" class="history-card">
              <div class="history-title-row">
                <strong>{{ reward.reward_amount }} {{ nativeBalanceSymbol }}</strong>
                <span>{{ formatDateTime(reward.minted_at) || 'Unknown time' }}</span>
              </div>
              <div class="history-grid">
                <div v-for="item in rewardSummary(reward)" :key="`${reward.block_hash || reward.submission_id}-${item.label}`">
                  <span>{{ item.label }}</span>
                  <strong>{{ formatHistoryValue(item.value) }}</strong>
                </div>
              </div>
            </li>
          </ul>
        </div>

        <div class="transfer-card">
          <span class="native-balance-label">Native ZOID Transfer Preview</span>
          <template v-if="wallet.state.isVerifiedSession">
            <p class="wallet-meta">{{ transferWarning }}</p>
            <label class="transfer-field">
              <span>From Native Account</span>
              <input :value="wallet.state.verifiedWalletAddress" type="text" readonly />
            </label>
            <label class="transfer-field">
              <span>To Native Account</span>
              <input v-model="transferForm.toAddress" type="text" placeholder="0x..." />
            </label>
            <label class="transfer-field">
              <span>Amount</span>
              <input v-model="transferForm.amount" type="text" inputmode="decimal" placeholder="10" />
            </label>
            <label class="transfer-field">
              <span>Memo (Optional)</span>
              <textarea v-model="transferForm.memo" rows="2" placeholder="Optional note" />
            </label>
            <div class="wallet-actions">
              <button
                type="button"
                class="wallet-btn primary"
                @click="submitTransferIntent"
                :disabled="isTransferSubmitting"
              >
                {{ isTransferSubmitting ? 'Signing Transfer Intent...' : 'Sign Native Transfer Intent' }}
              </button>
              <button
                type="button"
                class="wallet-btn secondary"
                @click="refreshTransferHistory"
                :disabled="isTransferHistoryLoading"
              >
                {{ isTransferHistoryLoading ? 'Refreshing Transfers...' : 'Refresh Transfer History' }}
              </button>
            </div>
            <p v-if="transferSuccessMessage" class="wallet-meta transfer-success">{{ transferSuccessMessage }}</p>
            <p v-if="transferError" class="wallet-error">{{ transferError }}</p>
            <div class="transfer-history">
              <p class="wallet-meta transfer-history-title">Signed Transfer Intent History</p>
              <p v-if="!transferHistory.length" class="wallet-meta">No signed transfer intents yet.</p>
              <template v-else>
                <p class="wallet-meta">Pending transaction processing. These records are not settled yet.</p>
                <ul class="history-list">
                  <li v-for="transfer in transferHistory" :key="transfer.transfer_id" class="history-card">
                    <div class="history-title-row">
                      <strong>{{ transferStatusLabel(transfer.status) }}</strong>
                      <span>{{ transferDirection(transfer) }}</span>
                    </div>
                    <div class="history-grid">
                      <div>
                        <span>Transfer ID</span>
                        <strong>{{ shortenTransferId(transfer.transfer_id) }}</strong>
                      </div>
                      <div>
                        <span>Status</span>
                        <strong>{{ transfer.status }}</strong>
                      </div>
                      <div>
                        <span>From Native Account</span>
                        <strong>{{ wallet.shortenAddress(transfer.from_address) }}</strong>
                      </div>
                      <div>
                        <span>To Native Account</span>
                        <strong>{{ wallet.shortenAddress(transfer.to_address) }}</strong>
                      </div>
                      <div>
                        <span>Amount</span>
                        <strong>{{ transfer.amount }} {{ nativeBalanceSymbol }}</strong>
                      </div>
                      <div>
                        <span>Fee</span>
                        <strong>{{ transfer.fee }} {{ nativeBalanceSymbol }}</strong>
                      </div>
                      <div>
                        <span>Signed At</span>
                        <strong>{{ formatDateTime(transferTimestamp(transfer)) || 'Unknown time' }}</strong>
                      </div>
                      <div>
                        <span>Settlement</span>
                        <strong>Not settled yet</strong>
                      </div>
                    </div>
                    <p v-if="transfer.memo" class="wallet-meta history-note">Memo: {{ transfer.memo }}</p>
                    <p class="wallet-meta history-note">Pending transaction processing. This signed transfer intent has not moved balances yet.</p>
                  </li>
                </ul>
              </template>
            </div>
          </template>
          <template v-else-if="wallet.state.isConnected">
            <p class="wallet-meta">Verify wallet before signing a transfer.</p>
          </template>
          <template v-else>
            <p class="wallet-meta">Connect MetaMask to prepare a native ZOID transfer.</p>
          </template>
        </div>

        <div class="wallet-actions">
          <button
            v-if="!wallet.state.isVerifiedSession"
            type="button"
            class="wallet-btn primary"
            @click="verify"
            :disabled="wallet.state.connectionStatus === 'verifying'"
          >
            {{ wallet.state.connectionStatus === 'verifying' ? 'Verifying...' : 'Verify Wallet' }}
          </button>
          <button type="button" class="wallet-btn secondary" @click="copyAddress">
            {{ copyButtonLabel }}
          </button>
          <button
            v-if="wallet.state.isVerifiedSession"
            type="button"
            class="wallet-btn secondary"
            @click="refreshAccountSummary"
            :disabled="isBalanceLoading"
          >
            {{ isBalanceLoading ? 'Refreshing Balance...' : 'Refresh Balance' }}
          </button>
          <button type="button" class="wallet-btn ghost" @click="disconnect">
            Disconnect
          </button>
        </div>
      </template>

      <template v-else>
        <p class="wallet-meta">
          MetaMask is used to sign ZoidbergChain actions. Native ZOID balances live in the ZoidbergChain app, not in the old development-only server wallet list.
        </p>
        <p v-if="wallet.state.lastConnectedAddress" class="wallet-meta">
          Last connected address: {{ wallet.shortenAddress(wallet.state.lastConnectedAddress) }}
        </p>
        <p v-if="!wallet.state.isMetaMaskAvailable" class="wallet-warning">
          MetaMask was not detected in this browser. Install it to connect a wallet here.
        </p>
        <div class="wallet-actions">
          <button
            type="button"
            class="wallet-btn primary"
            @click="connect"
            :disabled="wallet.state.connectionStatus === 'connecting' || !wallet.state.isMetaMaskAvailable"
          >
            {{ wallet.state.connectionStatus === 'connecting' ? 'Connecting...' : 'Connect MetaMask' }}
          </button>
        </div>
      </template>

      <p v-if="wallet.state.errorMessage" class="wallet-error">{{ wallet.state.errorMessage }}</p>
      <p v-if="balanceError" class="wallet-error">{{ balanceError }}</p>
    </div>
  </section>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { useWallet } from '../services/wallet';
import { apiClient, getApiErrorMessage } from '../config/api';
import { createNativeTransferService, TRANSFER_PENDING_WARNING } from '../services/nativeTransfer.js';
import {
  buildNativeBalanceSummary,
  buildRewardSummary,
  describeTransferIntentDirection,
  describeTransferIntentStatus,
  formatTransferIntentTimestamp,
} from '../utils/nativeWalletUi.js';

const wallet = useWallet();
const copyButtonLabel = ref('Copy Full Address');
const accountSummary = ref(null);
const isBalanceLoading = ref(false);
const balanceError = ref('');
const rewardHistory = ref([]);
const rewardError = ref('');
const isRewardHistoryLoading = ref(false);
const isTransferSubmitting = ref(false);
const isTransferHistoryLoading = ref(false);
const transferError = ref('');
const transferSuccessMessage = ref('');
const transferHistory = ref([]);
const transferForm = ref({
  toAddress: '',
  amount: '',
  memo: '',
});
const transferService = createNativeTransferService({
  api: apiClient,
  getApiErrorMessage,
});

const shortenedAddress = computed(() => wallet.shortenAddress(wallet.state.walletAddress));
const transferWarning = computed(() => TRANSFER_PENDING_WARNING);
const nativeBalanceSymbol = computed(() => accountSummary.value?.symbol || 'ZOID');
const balanceSummaryRows = computed(() => buildNativeBalanceSummary({
  native_balance: accountSummary.value?.native_balance,
  pending_outgoing: accountSummary.value?.pending_outgoing,
  pending_incoming: accountSummary.value?.pending_incoming,
  available_balance: accountSummary.value?.available_balance,
  symbol: nativeBalanceSymbol.value,
}));
const accountSummaryRows = computed(() => {
  const summary = accountSummary.value || {};
  return [
    { label: 'Native Account Type', value: summary.account_type === 'metamask_native' ? 'MetaMask-backed ZoidbergChain wallet' : 'Unknown' },
    { label: 'Network', value: summary.network_name || 'Unknown' },
    { label: 'Submissions', value: summary.submission_count ?? 0 },
    { label: 'Votes', value: summary.vote_count ?? 0 },
    { label: 'Rewards', value: summary.reward_count ?? 0 },
    { label: 'Pending Transfer Intents', value: summary.pending_transfer_count ?? 0 },
  ];
});
const nativeBalanceLabel = computed(() => {
  const balance = accountSummary.value?.native_balance;
  if (balance === null || balance === undefined || balance === '') {
    return '--';
  }
  return `${balance} ${nativeBalanceSymbol.value}`;
});
const balanceNote = computed(() => (
  accountSummary.value?.note
  || 'Pending transfer intents do not affect balance until transaction processing is enabled.'
));
const sessionExpiryLabel = computed(() => {
  if (!wallet.state.sessionExpiresAt) {
    return '';
  }
  const parsed = Date.parse(wallet.state.sessionExpiresAt);
  if (Number.isNaN(parsed)) {
    return wallet.state.sessionExpiresAt;
  }
  return new Date(parsed).toLocaleString();
});

const statusText = computed(() => {
  if (wallet.state.isVerifiedSession) {
    return 'Verified ZoidbergChain Wallet';
  }
  if (wallet.state.connectionStatus === 'expired') {
    return 'Verification Required Again';
  }
  if (wallet.state.connectionStatus === 'verifying') {
    return 'Verification In Progress';
  }
  if (wallet.state.isConnected) {
    return 'Connected - Verification Required';
  }
  if (!wallet.state.isMetaMaskAvailable) {
    return 'MetaMask Unavailable';
  }
  if (wallet.state.connectionStatus === 'connecting') {
    return 'Connecting';
  }
  return 'Disconnected';
});

const statusClass = computed(() => {
  if (wallet.state.isVerifiedSession) {
    return 'connected';
  }
  if (wallet.state.connectionStatus === 'expired' || wallet.state.connectionStatus === 'verifying') {
    return 'warning';
  }
  if (!wallet.state.isMetaMaskAvailable) {
    return 'warning';
  }
  return 'idle';
});

async function connect() {
  await wallet.connectWallet();
}

async function verify() {
  const verification = await wallet.verifyWallet();
  if (verification) {
    await refreshAccountData();
  }
}

function disconnect() {
  wallet.disconnectWallet();
  copyButtonLabel.value = 'Copy Full Address';
  accountSummary.value = null;
  rewardHistory.value = [];
  rewardError.value = '';
  balanceError.value = '';
  transferHistory.value = [];
  transferError.value = '';
  transferSuccessMessage.value = '';
}

async function copyAddress() {
  if (!wallet.state.normalizedWalletAddress || typeof navigator === 'undefined' || !navigator.clipboard) {
    copyButtonLabel.value = 'Copy Unavailable';
    return;
  }
  await navigator.clipboard.writeText(wallet.state.normalizedWalletAddress);
  copyButtonLabel.value = 'Copied';
  window.setTimeout(() => {
    copyButtonLabel.value = 'Copy Full Address';
  }, 1200);
}

async function refreshAccountSummary() {
  if (!wallet.state.isVerifiedSession || !wallet.state.verifiedWalletAddress) {
    accountSummary.value = null;
    balanceError.value = '';
    return;
  }

  isBalanceLoading.value = true;
  balanceError.value = '';
  try {
    const response = await apiClient.get(`/accounts/${wallet.state.verifiedWalletAddress}`);
    accountSummary.value = response.data || null;
  } catch (error) {
    accountSummary.value = null;
    balanceError.value = getApiErrorMessage(error, 'Failed to load native ZOID balance.');
  } finally {
    isBalanceLoading.value = false;
  }
}

async function refreshRewardHistory() {
  if (!wallet.state.isVerifiedSession || !wallet.state.verifiedWalletAddress) {
    rewardHistory.value = [];
    rewardError.value = '';
    return;
  }

  isRewardHistoryLoading.value = true;
  rewardError.value = '';
  try {
    const response = await apiClient.get(`/accounts/${wallet.state.verifiedWalletAddress}/rewards`);
    rewardHistory.value = Array.isArray(response.data.rewards) ? response.data.rewards : [];
  } catch (error) {
    rewardHistory.value = [];
    rewardError.value = getApiErrorMessage(error, 'Failed to load native ZOID reward history.');
  } finally {
    isRewardHistoryLoading.value = false;
  }
}

async function refreshTransferHistory() {
  if (!wallet.state.isVerifiedSession || !wallet.state.verifiedWalletAddress) {
    transferHistory.value = [];
    transferError.value = '';
    return;
  }

  isTransferHistoryLoading.value = true;
  transferError.value = '';
  try {
    const response = await apiClient.get(`/accounts/${wallet.state.verifiedWalletAddress}/transfers`);
    transferHistory.value = Array.isArray(response.data.transfers) ? response.data.transfers : [];
  } catch (error) {
    transferHistory.value = [];
    transferError.value = getApiErrorMessage(error, 'Failed to load transfer intent history.');
  } finally {
    isTransferHistoryLoading.value = false;
  }
}

async function submitTransferIntent() {
  if (!wallet.state.isVerifiedSession || !wallet.state.verifiedWalletAddress) {
    transferError.value = 'Verify wallet before signing a transfer.';
    return;
  }

  isTransferSubmitting.value = true;
  transferError.value = '';
  transferSuccessMessage.value = '';
  try {
    const result = await transferService.submitSignedTransferIntent({
      fromAddress: wallet.state.verifiedWalletAddress,
      walletAddressForSigning: wallet.state.walletAddress,
      toAddress: transferForm.value.toAddress,
      amount: transferForm.value.amount,
      memo: transferForm.value.memo,
    });
    transferSuccessMessage.value = `Signed transfer intent submitted. Transfer ${result.transfer_id} is pending transaction processing and is not settled yet.`;
    transferForm.value.toAddress = '';
    transferForm.value.amount = '';
    transferForm.value.memo = '';
    await refreshTransferHistory();
    await refreshAccountSummary();
  } catch (error) {
    transferError.value = error?.message || 'Native transfer intent submission failed.';
  } finally {
    isTransferSubmitting.value = false;
  }
}

async function refreshAccountData() {
  await Promise.all([
    refreshAccountSummary(),
    refreshRewardHistory(),
    refreshTransferHistory(),
  ]);
}

function rewardSummary(reward) {
  return buildRewardSummary(reward);
}

function transferDirection(transfer) {
  return describeTransferIntentDirection(transfer, wallet.state.verifiedWalletAddress);
}

function transferStatusLabel(status) {
  return describeTransferIntentStatus(status);
}

function transferTimestamp(transfer) {
  return formatTransferIntentTimestamp(transfer);
}

function shortenTransferId(value) {
  if (!value) {
    return 'Missing';
  }
  return value.length > 18 ? `${value.slice(0, 10)}...${value.slice(-8)}` : value;
}

function formatHistoryValue(value) {
  if (value === null || value === undefined || value === '') {
    return 'Missing';
  }
  const stringValue = String(value);
  return stringValue.length > 24 ? `${stringValue.slice(0, 12)}...${stringValue.slice(-10)}` : stringValue;
}

function formatDateTime(value) {
  if (!value) {
    return '';
  }
  const parsed = Date.parse(value);
  if (Number.isNaN(parsed)) {
    return String(value);
  }
  return new Date(parsed).toLocaleString();
}

function handleBalanceRefreshEvent() {
  refreshAccountSummary();
}

watch(
  () => [wallet.state.isVerifiedSession, wallet.state.verifiedWalletAddress],
  async ([isVerified, verifiedWalletAddress]) => {
    if (!isVerified || !verifiedWalletAddress) {
      accountSummary.value = null;
      balanceError.value = '';
      rewardHistory.value = [];
      rewardError.value = '';
      transferHistory.value = [];
      transferError.value = '';
      transferSuccessMessage.value = '';
      return;
    }
    await refreshAccountData();
  },
  { immediate: true },
);

onMounted(async () => {
  await wallet.detectMetaMask();
  if (typeof window !== 'undefined') {
    window.addEventListener('zoidberg-wallet-balance-refresh', handleBalanceRefreshEvent);
  }
});

onBeforeUnmount(() => {
  if (typeof window !== 'undefined') {
    window.removeEventListener('zoidberg-wallet-balance-refresh', handleBalanceRefreshEvent);
  }
});
</script>

<style scoped>
.wallet-panel {
  display: grid;
  grid-template-columns: minmax(280px, 1.1fr) minmax(300px, 0.9fr);
  gap: 18px;
  margin: 0 auto 24px;
  width: min(1220px, 100%);
}

.wallet-copy,
.wallet-card {
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 8px;
  background: rgba(28, 28, 28, 0.94);
  box-shadow: 0 12px 28px rgba(0, 0, 0, 0.3);
}

.wallet-copy {
  padding: 22px;
}

.wallet-card {
  padding: 20px;
}

.wallet-card.connected {
  border-color: rgba(141, 245, 166, 0.35);
}

.wallet-label {
  margin: 0 0 8px;
  color: #ffb0b0;
  font-size: 0.78rem;
  font-weight: 700;
  text-transform: uppercase;
}

.wallet-copy h2,
.wallet-note,
.wallet-meta,
.wallet-status,
.wallet-warning,
.wallet-error,
.address-short,
.address-full {
  margin: 0;
}

.wallet-copy h2 {
  margin-bottom: 8px;
  color: #fff;
  font-size: 1.35rem;
}

.wallet-note,
.wallet-meta {
  color: #b8b8b8;
  line-height: 1.5;
}

.wallet-meta + .wallet-meta,
.wallet-actions,
.wallet-error,
.wallet-warning,
.address-full {
  margin-top: 12px;
}

.wallet-status {
  margin-bottom: 14px;
}

.status-badge {
  display: inline-flex;
  align-items: center;
  min-height: 28px;
  padding: 5px 10px;
  border-radius: 999px;
  font-size: 0.82rem;
  font-weight: 700;
}

.status-badge.connected {
  background: rgba(141, 245, 166, 0.14);
  color: #8df5a6;
}

.status-badge.warning {
  background: rgba(255, 201, 71, 0.14);
  color: #ffd884;
}

.status-badge.idle {
  background: rgba(255, 71, 71, 0.12);
  color: #ffb0b0;
}

.address-short {
  color: #fff;
  font-size: 1.4rem;
  font-weight: 700;
  letter-spacing: 0.02em;
}

.address-full {
  color: #d7dce3;
  font-size: 0.92rem;
  overflow-wrap: anywhere;
}

.wallet-warning {
  color: #ffd884;
}

.wallet-error {
  color: #ff8c8c;
}

.wallet-actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.native-balance-card {
  margin-top: 12px;
  padding: 12px;
  border: 1px solid rgba(141, 245, 166, 0.2);
  border-radius: 8px;
  background: rgba(141, 245, 166, 0.08);
}

.native-balance-label {
  display: block;
  margin-bottom: 6px;
  color: #b8b8b8;
  font-size: 0.82rem;
  font-weight: 700;
  text-transform: uppercase;
}

.native-balance-value {
  display: block;
  color: #8df5a6;
  font-size: 1.35rem;
  line-height: 1.2;
}

.wallet-summary-list,
.history-grid {
  display: grid;
  gap: 10px;
  margin-top: 12px;
}

.wallet-summary-row,
.history-title-row {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: baseline;
}

.wallet-summary-row span,
.history-grid span {
  color: #b8b8b8;
  font-size: 0.82rem;
}

.wallet-summary-row strong,
.history-grid strong {
  color: #fff;
  overflow-wrap: anywhere;
}

.reward-card,
.transfer-card {
  margin-top: 12px;
  padding: 12px;
  border: 1px solid rgba(74, 144, 226, 0.18);
  border-radius: 8px;
  background: rgba(74, 144, 226, 0.08);
}

.transfer-field {
  display: block;
  margin-top: 12px;
}

.transfer-field span {
  display: block;
  margin-bottom: 6px;
  color: #d7dce3;
  font-size: 0.82rem;
  font-weight: 700;
}

.transfer-field input,
.transfer-field textarea {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid rgba(255, 255, 255, 0.14);
  border-radius: 8px;
  background: rgba(19, 19, 19, 0.85);
  color: #fff;
}

.transfer-success {
  color: #8df5a6;
}

.transfer-history {
  margin-top: 12px;
}

.transfer-history-title {
  font-weight: 700;
}

.history-header {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
}

.history-list {
  display: grid;
  gap: 12px;
  margin: 12px 0 0;
  padding: 0;
  list-style: none;
}

.history-card {
  padding: 12px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 8px;
  background: rgba(19, 19, 19, 0.55);
}

.history-note {
  margin-top: 10px;
}

.wallet-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 42px;
  padding: 10px 16px;
  border: 1px solid transparent;
  border-radius: 8px;
  color: #fff;
  cursor: pointer;
  font-size: 0.94rem;
  font-weight: 700;
}

.wallet-btn:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

.wallet-btn.primary {
  background: linear-gradient(135deg, #ff4747 0%, #d71919 100%);
}

.wallet-btn.secondary {
  background: linear-gradient(135deg, #4a90e2 0%, #2455a5 100%);
}

.wallet-btn.ghost {
  background: #2b2b2b;
  border-color: rgba(255, 255, 255, 0.16);
}

.compact {
  min-height: 36px;
  padding: 8px 12px;
}

@media (max-width: 900px) {
  .wallet-panel {
    grid-template-columns: minmax(0, 1fr);
  }

  .wallet-summary-row,
  .history-title-row,
  .history-header {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
