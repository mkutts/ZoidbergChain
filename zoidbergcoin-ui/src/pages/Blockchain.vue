<template>
  <div class="blockchain-page">
    <PublicDemoBanner v-if="showPublicDemoBanner" />
    <header class="explorer-header">
      <div>
        <p class="eyebrow">Blockchain Explorer</p>
        <h1>Protocol v1 Explorer</h1>
        <p class="subtitle">Inspect Public Testnet v1 blocks, genesis identity, and validator-quorum finality.</p>
      </div>
      <div class="header-actions">
        <button @click="refreshExplorer" class="btn secondary" :disabled="isLoading">
          {{ isLoading ? 'Refreshing...' : 'Refresh' }}
        </button>
        <button @click="goToDashboard" class="btn ghost">Dashboard</button>
      </div>
    </header>

    <main class="explorer-shell">
      <section class="section-panel">
        <div class="card-heading">
          <div>
            <p class="section-label">Chain Summary</p>
            <h2>Current Network Identity</h2>
          </div>
          <span class="workflow-chip">{{ protocolIdentity.protocolLabel }}</span>
        </div>

        <p v-if="summaryError" class="status-message error">{{ summaryError }}</p>

        <div v-if="chainSummary" class="metric-grid">
          <div class="metric-card">
            <span>Chain Height</span>
            <strong>{{ chainSummary.chain_height }}</strong>
          </div>
          <div class="metric-card">
            <span>Cumulative Originality Score</span>
            <strong>{{ formatScore(chainSummary.cumulative_originality_score) }}</strong>
          </div>
          <div class="metric-card">
            <span>Latest Block</span>
            <strong>{{ shortenHash(chainSummary.latest_block_hash) }}</strong>
          </div>
          <div class="metric-card">
            <span>Public Network</span>
            <strong>{{ protocolIdentity.displayName }}</strong>
          </div>
          <div class="metric-card">
            <span>Node</span>
            <strong>{{ shortenKey(chainSummary.node_id) }}</strong>
          </div>
        </div>

        <div v-if="chainSummary" class="detail-grid protocol-identity-grid">
          <div>
            <span>Network ID</span>
            <strong>{{ protocolIdentity.networkId || 'Unknown' }}</strong>
          </div>
          <div>
            <span>Protocol</span>
            <strong>{{ protocolIdentity.protocolLabel }}</strong>
          </div>
          <div>
            <span>Runtime Alias</span>
            <strong>{{ protocolIdentity.networkAlias || 'Unknown' }}</strong>
          </div>
          <div>
            <span>Canonical Genesis Hash</span>
            <strong>{{ protocolIdentity.genesisHash || 'Unknown' }}</strong>
          </div>
        </div>
        <p v-if="chainSummary" class="hint">
          Runtime alias {{ chainSummary.network_name || 'Unknown' }} is a display label. Protocol v1 identity is anchored by the network ID and genesis hash.
        </p>

        <div v-else-if="!summaryError" class="empty-state">
          Loading chain summary...
        </div>
      </section>

      <section class="section-panel">
        <div class="card-heading">
          <div>
            <p class="section-label">Recent Blocks</p>
            <h2>Explorer</h2>
          </div>
          <span class="workflow-chip">{{ chain.length }} blocks</span>
        </div>

        <p v-if="errorMessage" class="status-message error">{{ errorMessage }}</p>

        <div v-if="chain.length === 0 && !errorMessage" class="empty-state">
          Loading blockchain data...
        </div>

        <div v-else class="blocks">
          <article v-for="block in chain" :key="block.hash || block.index" class="block-card">
            <div class="block-heading">
              <div>
                <p class="section-label">Block #{{ block.index }}</p>
                <h3>{{ blockDisplay(block).title }}</h3>
              </div>
              <span class="status-pill" :class="blockDisplay(block).statusTone">
                {{ blockDisplay(block).statusLabel }}
              </span>
            </div>

            <p class="hint">{{ blockDisplay(block).detail }}</p>

            <div v-if="hasContentPreview(block)" class="content-preview">
              <img v-if="isImageContent(block) && block.download_url" :src="contentUrl(block.download_url)" alt="Block content preview" class="content-image">
              <pre v-else-if="isTextContent(block)">{{ previewText(block) }}</pre>
            </div>

            <div class="detail-grid">
              <div>
                <span>Block Hash</span>
                <strong>{{ shortenHash(block.hash) }}</strong>
              </div>
              <div>
                <span>Previous Hash</span>
                <strong>{{ shortenHash(block.previous_hash) }}</strong>
              </div>
              <div>
                <span>Block Version</span>
                <strong>{{ block.block_version ?? 'Missing' }}</strong>
              </div>
              <div>
                <span>Protocol</span>
                <strong>{{ block.protocol_version ? `Protocol v${block.protocol_version}` : 'Missing' }}</strong>
              </div>
              <div>
                <span>Network ID</span>
                <strong>{{ block.network_id || protocolIdentity.networkId || 'Missing' }}</strong>
              </div>
              <div>
                <span>Canonical State</span>
                <strong>{{ blockDisplay(block).statusLabel }}</strong>
              </div>
              <div>
                <span>Confirmations</span>
                <strong>{{ block.confirmations ?? 0 }}</strong>
              </div>
              <div>
                <span>Native Transfer Count</span>
                <strong>{{ block.transaction_count ?? 0 }}</strong>
              </div>
              <div v-if="blockDisplay(block).isGenesis">
                <span>Canonical Genesis Hash</span>
                <strong>{{ block.canonical_genesis_hash || protocolIdentity.genesisHash || 'Missing' }}</strong>
              </div>
              <div v-if="!blockDisplay(block).isGenesis">
                <span>Submission ID</span>
                <strong>{{ shortenHash(block.submission_id) }}</strong>
              </div>
              <div v-if="!blockDisplay(block).isGenesis">
                <span>Certificate ID</span>
                <strong>{{ shortenHash(block.certificate_id) }}</strong>
              </div>
              <div v-if="!blockDisplay(block).isGenesis">
                <span>Content Hash</span>
                <strong>{{ shortenHash(block.content_hash) }}</strong>
              </div>
              <div v-if="!blockDisplay(block).isGenesis">
                <span>Content ID</span>
                <strong>{{ shortenHash(block.content_id) }}</strong>
              </div>
              <div v-if="!blockDisplay(block).isGenesis">
                <span>Content Type</span>
                <strong>{{ block.content_type || 'Missing' }}</strong>
              </div>
              <div v-if="!blockDisplay(block).isGenesis">
                <span>MIME Type</span>
                <strong>{{ block.mime_type || 'Missing' }}</strong>
              </div>
              <div v-if="!blockDisplay(block).isGenesis">
                <span>Originality Score</span>
                <strong>{{ formatScore(block.originality_score) }}</strong>
              </div>
              <div v-if="!blockDisplay(block).isGenesis">
                <span>Creator Account</span>
                <strong>{{ shortenKey(block.creator_wallet) }}</strong>
              </div>
              <div v-if="!blockDisplay(block).isGenesis">
                <span>Reward Type</span>
                <strong>{{ block.reward_type || 'Missing' }}</strong>
              </div>
              <div v-if="!blockDisplay(block).isGenesis">
                <span>Native Reward Recipient</span>
                <strong>{{ shortenKey(block.reward_recipient) }}</strong>
              </div>
              <div v-if="!blockDisplay(block).isGenesis">
                <span>Native ZOID Reward Amount</span>
                <strong>{{ block.reward_amount ?? 'Missing' }}</strong>
              </div>
              <div v-if="!blockDisplay(block).isGenesis">
                <span>Approval</span>
                <strong>{{ formatPercent(block.approval_percentage) }}</strong>
              </div>
              <div v-if="Array.isArray(block.voter_rewards) && block.voter_rewards.length">
                <span>Voter Reward Settlements</span>
                <strong>{{ block.voter_rewards.length }}</strong>
              </div>
            </div>

            <div class="content-state-line">
              <span class="status-pill" :class="blockContentAvailability(block).chipTone">{{ blockContentAvailability(block).chipLabel }}</span>
              <a v-if="block.download_url" :href="contentUrl(block.download_url)" target="_blank" rel="noreferrer" class="meta-link">
                View Content
              </a>
            </div>
            <p class="hint">{{ blockContentAvailability(block).detail }}</p>

            <div v-if="(block.transaction_count ?? 0) > 0" class="native-transfer-panel">
              <div class="history-header">
                <span class="native-transfer-label">Native ZOID transfers included</span>
                <span class="status-pill ready">{{ block.transaction_count }} settled</span>
              </div>
              <div class="detail-grid">
                <div>
                  <span>Transaction IDs</span>
                  <strong>{{ joinTransactionIds(block.transaction_ids) }}</strong>
                </div>
              </div>
              <ul class="native-transfer-list">
                <li v-for="transaction in block.native_transactions || []" :key="transaction.tx_id" class="native-transfer-item">
                  <div class="history-title-row">
                    <strong>{{ shortenHash(transaction.tx_id) }}</strong>
                    <span>{{ transaction.status_detail || 'Settled on ZoidbergChain' }}</span>
                  </div>
                  <div class="detail-grid">
                    <div>
                      <span>From</span>
                      <strong>{{ shortenKey(transaction.from_address) }}</strong>
                    </div>
                    <div>
                      <span>To</span>
                      <strong>{{ shortenKey(transaction.to_address) }}</strong>
                    </div>
                    <div>
                      <span>Amount</span>
                      <strong>{{ transaction.amount }} ZOID</strong>
                    </div>
                    <div>
                      <span>Fee</span>
                      <strong>{{ transaction.fee ?? '0' }} ZOID</strong>
                    </div>
                    <div>
                      <span>Nonce</span>
                      <strong>{{ transaction.nonce ?? 'Missing' }}</strong>
                    </div>
                    <div>
                      <span>Protocol</span>
                      <strong>{{ transaction.protocol_version ? `Tx v${transaction.transaction_version ?? '?'} / Protocol v${transaction.protocol_version}` : 'Missing' }}</strong>
                    </div>
                  </div>
                </li>
              </ul>
            </div>
          </article>
        </div>
      </section>
    </main>
  </div>
</template>

<script>
import { apiClient, buildApiUrl, getApiErrorMessage } from '../config/api';
import PublicDemoBanner from '../components/PublicDemoBanner.vue';
import { isPublicDemoMode } from '../utils/runtimeConfig';
import {
  buildBlockContentAvailability,
  buildBlockDisplay,
  buildProtocolNetworkIdentity,
  hasRenderableProtocolPreview,
  isProtocolImageContent,
  isProtocolTextContent,
  resolveProtocolTextPreview,
} from '../utils/protocolV1Ui.js';

export default {
  components: {
    PublicDemoBanner,
  },
  data() {
    return {
      chain: [],
      chainSummary: null,
      errorMessage: '',
      summaryError: '',
      isLoading: false,
      showPublicDemoBanner: isPublicDemoMode(),
    };
  },
  computed: {
    protocolIdentity() {
      return buildProtocolNetworkIdentity(this.chainSummary || {});
    },
  },
  async created() {
    await this.refreshExplorer();
  },
  methods: {
    contentUrl(path) {
      return buildApiUrl(path);
    },
    async refreshExplorer() {
      this.isLoading = true;
      try {
        await Promise.all([this.fetchChainSummary(), this.fetchChain()]);
      } finally {
        this.isLoading = false;
      }
    },
    async fetchChainSummary() {
      this.summaryError = '';
      try {
        const response = await apiClient.get('/chain/summary');
        this.chainSummary = response.data;
      } catch (error) {
        console.error('Error fetching chain summary:', error);
        this.summaryError = getApiErrorMessage(error, 'Failed to load chain summary.');
      }
    },
    async fetchChain() {
      this.errorMessage = '';
      try {
        const response = await apiClient.get('/chain');
        this.chain = [...(response.data.chain || [])].reverse();
      } catch (error) {
        console.error('Error fetching blockchain data:', error);
        this.errorMessage = getApiErrorMessage(error, 'Failed to load blockchain data.');
      }
    },
    formatPercent(value) {
      if (value === null || value === undefined || value === '') {
        return 'Missing';
      }
      return `${Math.round(Number(value) * 1000) / 10}%`;
    },
    formatScore(value) {
      if (value === null || value === undefined || value === '') {
        return '0';
      }
      return Number(value).toLocaleString(undefined, {
        minimumFractionDigits: 0,
        maximumFractionDigits: 8,
      });
    },
    shortenHash(hash) {
      if (!hash) {
        return 'Missing';
      }
      if (String(hash).length <= 18) {
        return hash;
      }
      return `${String(hash).slice(0, 10)}...${String(hash).slice(-8)}`;
    },
    shortenKey(key) {
      if (!key || String(key).length <= 18) {
        return key || 'Unknown';
      }
      return `${String(key).slice(0, 10)}...${String(key).slice(-8)}`;
    },
    joinTransactionIds(transactionIds) {
      if (!Array.isArray(transactionIds) || transactionIds.length === 0) {
        return 'None';
      }
      return transactionIds.map((txId) => this.shortenHash(txId)).join(', ');
    },
    hasContentPreview(record) {
      return hasRenderableProtocolPreview(record);
    },
    isImageContent(record) {
      return isProtocolImageContent(record);
    },
    isTextContent(record) {
      return isProtocolTextContent(record);
    },
    previewText(record) {
      return resolveProtocolTextPreview(record);
    },
    blockDisplay(block) {
      return buildBlockDisplay(block);
    },
    blockContentAvailability(block) {
      return buildBlockContentAvailability(block);
    },
    goToDashboard() {
      this.$router.push('/dashboard');
    },
  },
};
</script>

<style scoped>
.blockchain-page {
  min-height: 100vh;
  padding: 40px 24px 56px;
  background: linear-gradient(150deg, #090909 0%, #181818 48%, #080808 100%);
  color: #fff;
  font-family: Arial, sans-serif;
}

.explorer-header,
.explorer-shell {
  width: min(1100px, 100%);
  margin: 0 auto;
}

.explorer-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 24px;
  margin-bottom: 28px;
}

.explorer-shell {
  display: grid;
  gap: 22px;
}

.eyebrow,
.section-label {
  margin: 0 0 8px;
  color: #ffb0b0;
  font-size: 0.78rem;
  font-weight: 700;
  letter-spacing: 0;
  text-transform: uppercase;
}

h1,
h2,
h3,
p {
  margin-top: 0;
}

h1 {
  margin-bottom: 8px;
  font-size: 3rem;
  line-height: 1;
  text-shadow: 3px 3px 6px rgba(255, 0, 0, 0.42);
}

h2 {
  margin-bottom: 0;
  font-size: 1.35rem;
  line-height: 1.2;
}

h3 {
  margin-bottom: 0;
  font-size: 1.18rem;
}

.subtitle {
  margin-bottom: 0;
  color: #c6c6c6;
  font-size: 1.05rem;
}

.hint {
  color: #b9c1cc;
  line-height: 1.5;
}

.section-panel {
  padding: 22px;
  background: rgba(28, 28, 28, 0.94);
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 8px;
  box-shadow: 0 12px 28px rgba(0, 0, 0, 0.35);
}

.card-heading,
.block-heading,
.header-actions {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.card-heading {
  margin-bottom: 20px;
}

.header-actions {
  align-items: center;
  flex-wrap: wrap;
}

.workflow-chip,
.status-pill {
  display: inline-flex;
  align-items: center;
  min-height: 28px;
  padding: 5px 10px;
  border-radius: 999px;
  background: rgba(255, 71, 71, 0.12);
  color: #ffb0b0;
  font-size: 0.82rem;
  font-weight: 700;
  white-space: nowrap;
}

.status-pill.ready {
  background: rgba(141, 245, 166, 0.14);
  color: #8df5a6;
}

.status-pill.pending {
  background: rgba(255, 201, 71, 0.14);
  color: #ffd884;
}

.warning-chip {
  background: rgba(255, 201, 71, 0.14);
  color: #ffd884;
}

.metric-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 12px;
}

.metric-card,
.block-card,
.empty-state {
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 8px;
  background: rgba(8, 8, 8, 0.58);
}

.metric-card {
  min-height: 92px;
  padding: 14px;
}

.metric-card span,
.detail-grid span {
  display: block;
  margin-bottom: 6px;
  color: #aeb4bd;
  font-size: 0.78rem;
  font-weight: 700;
  text-transform: uppercase;
}

.metric-card strong,
.detail-grid strong {
  display: block;
  color: #f4f4f4;
  font-size: 1rem;
  line-height: 1.35;
  overflow-wrap: anywhere;
}

.protocol-identity-grid {
  margin-top: 16px;
}

.blocks {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.block-card {
  padding: 18px;
  text-align: left;
}

.content-preview {
  margin-bottom: 14px;
}

.content-image {
  display: block;
  width: 100%;
  max-height: 360px;
  object-fit: contain;
  border-radius: 8px;
  background: #111;
  border: 1px solid rgba(255, 255, 255, 0.12);
}

.content-preview pre {
  margin: 0;
  padding: 14px;
  border-radius: 8px;
  background: rgba(0, 0, 0, 0.32);
  color: #f1f1f1;
  white-space: pre-wrap;
  word-break: break-word;
}

.content-state-line {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-top: 12px;
}

.meta-link {
  color: #8eb9ff;
  font-size: 0.88rem;
  font-weight: 700;
}

.native-transfer-panel {
  margin-top: 16px;
  padding: 14px;
  border: 1px solid rgba(141, 245, 166, 0.16);
  border-radius: 8px;
  background: rgba(141, 245, 166, 0.06);
}

.native-transfer-label {
  display: block;
  margin-bottom: 6px;
  color: #b8b8b8;
  font-size: 0.82rem;
  font-weight: 700;
  text-transform: uppercase;
}

.native-transfer-list {
  display: grid;
  gap: 12px;
  margin: 12px 0 0;
  padding: 0;
  list-style: none;
}

.native-transfer-item {
  padding: 12px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 8px;
  background: rgba(19, 19, 19, 0.55);
}

.history-header,
.history-title-row {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
}

.block-heading {
  align-items: center;
  margin-bottom: 14px;
}

.detail-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.empty-state {
  padding: 18px;
  color: #bbb;
}

.status-message {
  margin: 0 0 16px;
  padding: 11px 12px;
  border-radius: 8px;
  line-height: 1.4;
}

.error {
  background: rgba(255, 140, 140, 0.12);
  color: #ff8c8c;
}

.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 42px;
  width: auto;
  padding: 10px 16px;
  border: 1px solid transparent;
  border-radius: 8px;
  color: #fff;
  cursor: pointer;
  font-size: 0.94rem;
  font-weight: 700;
  text-align: center;
  text-decoration: none;
  transition: 0.18s ease-in-out;
}

.btn:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

.btn:hover:not(:disabled) {
  transform: translateY(-1px);
}

.secondary {
  background: linear-gradient(135deg, #4a90e2 0%, #2455a5 100%);
  box-shadow: 0 6px 16px rgba(74, 144, 226, 0.24);
}

.ghost {
  background: #2b2b2b;
  border-color: rgba(255, 255, 255, 0.16);
  box-shadow: none;
}

@media (max-width: 920px) {
  .explorer-header {
    align-items: flex-start;
    flex-direction: column;
  }

  .metric-grid,
  .detail-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 620px) {
  .blockchain-page {
    padding: 28px 14px 40px;
  }

  h1 {
    font-size: 2.3rem;
  }

  .section-panel {
    padding: 16px;
  }

  .card-heading,
  .block-heading,
  .header-actions,
  .history-header,
  .history-title-row {
    align-items: stretch;
    flex-direction: column;
  }

  .metric-grid,
  .detail-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .btn,
  .header-actions {
    width: 100%;
  }

  .workflow-chip,
  .status-pill {
    white-space: normal;
  }

  .content-image {
    max-height: 260px;
  }
}
</style>
