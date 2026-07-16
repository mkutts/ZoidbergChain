<template>
  <section class="wallet-panel">
    <div class="wallet-copy">
      <p class="wallet-label">Wallet Connection</p>
      <h2>MetaMask For ZoidbergChain Signing</h2>
      <p class="wallet-note">
        MetaMask provides the signing key. ZOID is native to ZoidbergChain and will not appear in normal MetaMask yet.
      </p>
    </div>

    <div class="wallet-card" :class="{ connected: wallet.state.isConnected }">
      <p class="wallet-status">
        <span class="status-badge" :class="statusClass">{{ statusText }}</span>
      </p>

      <template v-if="wallet.state.isConnected">
        <p class="address-short">{{ shortenedAddress }}</p>
        <p class="address-full">{{ wallet.state.normalizedWalletAddress }}</p>
        <p v-if="wallet.state.isVerifiedSession" class="wallet-meta">Verified ZoidbergChain wallet. This session is the active identity for app actions that require verified wallet ownership.</p>
        <p v-else-if="wallet.state.connectionStatus === 'expired'" class="wallet-meta">This wallet was connected before, but the verified session expired or changed. Verify again to restore wallet identity.</p>
        <p v-else class="wallet-meta">Connected only at the browser level. Verify this wallet to use it as your ZoidbergChain identity.</p>
        <p v-if="wallet.state.chainId" class="wallet-meta">Chain ID: {{ wallet.state.chainId }}</p>
        <p v-if="wallet.state.sessionExpiresAt && wallet.state.isVerifiedSession" class="wallet-meta">
          Session expires at: {{ sessionExpiryLabel }}
        </p>
        <div v-if="wallet.state.isVerifiedSession" class="native-balance-card">
          <span class="native-balance-label">Native ZOID balance on ZoidbergChain</span>
          <strong class="native-balance-value">{{ nativeBalanceLabel }}</strong>
          <p class="wallet-meta">This balance is tracked by ZoidbergChain and does not appear in normal MetaMask.</p>
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
            @click="refreshNativeBalance"
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
          MetaMask is used to sign ZoidbergChain actions. Native ZOID balances live in the ZoidbergChain app.
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

const wallet = useWallet();
const copyButtonLabel = ref('Copy Full Address');
const nativeBalance = ref(null);
const nativeBalanceSymbol = ref('ZOID');
const isBalanceLoading = ref(false);
const balanceError = ref('');

const shortenedAddress = computed(() => wallet.shortenAddress(wallet.state.walletAddress));
const nativeBalanceLabel = computed(() => {
  if (nativeBalance.value === null || nativeBalance.value === undefined || nativeBalance.value === '') {
    return '--';
  }
  return `${nativeBalance.value} ${nativeBalanceSymbol.value}`;
});
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
    await refreshNativeBalance();
  }
}

function disconnect() {
  wallet.disconnectWallet();
  copyButtonLabel.value = 'Copy Full Address';
  nativeBalance.value = null;
  balanceError.value = '';
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

async function refreshNativeBalance() {
  if (!wallet.state.isVerifiedSession || !wallet.state.verifiedWalletAddress) {
    nativeBalance.value = null;
    balanceError.value = '';
    return;
  }

  isBalanceLoading.value = true;
  balanceError.value = '';
  try {
    const response = await apiClient.get(`/wallets/${wallet.state.verifiedWalletAddress}/balance`);
    nativeBalance.value = response.data.native_balance;
    nativeBalanceSymbol.value = response.data.symbol || 'ZOID';
  } catch (error) {
    nativeBalance.value = null;
    balanceError.value = getApiErrorMessage(error, 'Failed to load native ZOID balance.');
  } finally {
    isBalanceLoading.value = false;
  }
}

function handleBalanceRefreshEvent() {
  refreshNativeBalance();
}

watch(
  () => [wallet.state.isVerifiedSession, wallet.state.verifiedWalletAddress],
  async ([isVerified, verifiedWalletAddress]) => {
    if (!isVerified || !verifiedWalletAddress) {
      nativeBalance.value = null;
      balanceError.value = '';
      return;
    }
    await refreshNativeBalance();
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

@media (max-width: 900px) {
  .wallet-panel {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
