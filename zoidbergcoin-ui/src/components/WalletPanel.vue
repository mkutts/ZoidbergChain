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
        <p class="wallet-meta">Signature verification coming next. This browser connection is not a verified ZoidbergChain session yet.</p>
        <p v-if="wallet.state.chainId" class="wallet-meta">Chain ID: {{ wallet.state.chainId }}</p>
        <div class="wallet-actions">
          <button type="button" class="wallet-btn secondary" @click="copyAddress">
            {{ copyButtonLabel }}
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
    </div>
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue';
import { useWallet } from '../services/wallet';

const wallet = useWallet();
const copyButtonLabel = ref('Copy Full Address');

const shortenedAddress = computed(() => wallet.shortenAddress(wallet.state.walletAddress));

const statusText = computed(() => {
  if (wallet.state.isConnected) {
    return 'Connected';
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
  if (wallet.state.isConnected) {
    return 'connected';
  }
  if (!wallet.state.isMetaMaskAvailable) {
    return 'warning';
  }
  return 'idle';
});

async function connect() {
  await wallet.connectWallet();
}

function disconnect() {
  wallet.disconnectWallet();
  copyButtonLabel.value = 'Copy Full Address';
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

onMounted(async () => {
  await wallet.detectMetaMask();
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
