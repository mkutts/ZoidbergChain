<template>
  <div class="blockchain-page">
    <header class="explorer-header">
      <div>
        <p class="eyebrow">Blockchain Explorer</p>
        <h1>Certified Meme Blocks</h1>
        <p class="subtitle">Inspect the chain powered by community-approved originality certificates.</p>
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
            <h2>Current Consensus</h2>
          </div>
          <span class="workflow-chip">Cumulative Originality Score</span>
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
            <span>Network</span>
            <strong>{{ chainSummary.network_name || 'Unknown' }}</strong>
          </div>
          <div class="metric-card">
            <span>Node</span>
            <strong>{{ shortenKey(chainSummary.node_id) }}</strong>
          </div>
        </div>

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
                <h3>{{ block.index === 0 ? 'Genesis Block' : 'Meme Block' }}</h3>
              </div>
              <span :class="block.certificate_id ? 'status-pill ready' : 'status-pill'">
                {{ block.certificate_id ? 'Certified' : 'No Certificate Required' }}
              </span>
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
                <span>Mined By</span>
                <strong>{{ shortenKey(block.miner) }}</strong>
              </div>
              <div v-if="block.certificate_id">
                <span>Submission ID</span>
                <strong>{{ shortenHash(block.submission_id) }}</strong>
              </div>
              <div v-if="block.certificate_id">
                <span>Certificate ID</span>
                <strong>{{ shortenHash(block.certificate_id) }}</strong>
              </div>
              <div v-if="block.certificate_id">
                <span>Content Hash</span>
                <strong>{{ shortenHash(block.content_hash) }}</strong>
              </div>
              <div v-if="block.certificate_id">
                <span>Originality Score</span>
                <strong>{{ formatScore(block.originality_score) }}</strong>
              </div>
              <div v-if="block.certificate_id">
                <span>Creator Wallet</span>
                <strong>{{ shortenKey(block.creator_wallet) }}</strong>
              </div>
              <div v-if="block.certificate_id">
                <span>Approval</span>
                <strong>{{ formatPercent(block.approval_percentage) }}</strong>
              </div>
            </div>

            <div v-if="block.meme && block.meme.encoded_image" class="meme-container">
              <img :src="'data:image/png;base64,' + block.meme.encoded_image" alt="Meme submitted for this block" class="meme-image" />
            </div>
          </article>
        </div>
      </section>
    </main>
  </div>
</template>

<script>
import { apiClient, getApiErrorMessage } from '../config/api';

export default {
  data() {
    return {
      chain: [],
      chainSummary: null,
      errorMessage: '',
      summaryError: '',
      isLoading: false,
    };
  },
  async created() {
    await this.refreshExplorer();
  },
  methods: {
    async refreshExplorer() {
      this.isLoading = true;
      await Promise.all([this.fetchChainSummary(), this.fetchChain()]);
      this.isLoading = false;
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

.blocks {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.block-card {
  padding: 18px;
  text-align: left;
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

.meme-container {
  margin-top: 16px;
  text-align: center;
}

.meme-image {
  max-width: 100%;
  max-height: 360px;
  border-radius: 8px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  object-fit: contain;
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
  .header-actions {
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
}
</style>
