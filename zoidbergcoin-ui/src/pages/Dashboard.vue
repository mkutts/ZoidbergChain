<template>
  <div class="dashboard-page">
    <header class="dashboard-header">
      <div>
        <p class="eyebrow">Task 1 Workflow</p>
        <h1>Dashboard</h1>
        <p class="subtitle">Submit content, review pending memes, and mint approved queue items.</p>
      </div>
      <div class="header-actions">
        <button @click="refreshWorkflow" class="btn secondary" :disabled="isLoading || isQueueLoading">
          {{ isLoading || isQueueLoading ? 'Refreshing...' : 'Refresh Workflow' }}
        </button>
      </div>
    </header>

    <main class="dashboard-shell">
      <section class="card submit-card">
        <div class="card-heading">
          <div>
            <p class="section-label">Create Submission</p>
            <h2>Submit Meme/Content</h2>
          </div>
          <span class="workflow-chip">Creates Pending</span>
        </div>

        <div class="form-stack">
          <div class="field-group">
            <label for="wallet">Submitter Wallet ID</label>
            <input id="wallet" type="text" v-model.trim="wallet" placeholder="Enter your public wallet key" class="input-field">
          </div>

          <div class="field-group">
            <label for="content-text">Content Text</label>
            <textarea id="content-text" v-model.trim="textContent" placeholder="Enter the meme text or caption" class="input-field text-area"></textarea>
          </div>

          <div class="field-group">
            <label for="meme-upload">Meme Image</label>
            <input type="file" id="meme-upload" accept=".jpg,.jpeg,.png,.webp" @change="uploadMeme" class="file-input">
          </div>
        </div>

        <div class="card-actions">
          <button @click="submitMeme" class="btn primary" :disabled="isSubmitting">
            {{ isSubmitting ? 'Submitting...' : 'Submit for Review' }}
          </button>
        </div>

        <div v-if="submitMessage || errorMessage" class="message-stack">
          <p v-if="submitMessage" class="status-message success">{{ submitMessage }}</p>
          <p v-if="errorMessage" class="status-message error">{{ errorMessage }}</p>
        </div>

        <div v-if="lastSubmission" class="submission-result">
          <div class="submission-header">
            <span class="status-pill">{{ formatStatus(lastSubmission.status) }}</span>
            <span>{{ formatDate(lastSubmission.created_at) }}</span>
          </div>
          <p><strong>Submission ID:</strong> {{ lastSubmission.submission_id }}</p>
          <p class="hint">Submitted content is pending community voting and is not minted automatically.</p>
        </div>
      </section>

      <section class="card voting-card">
        <div class="card-heading">
          <div>
            <p class="section-label">Community Review</p>
            <h2>Pending Submissions</h2>
          </div>
          <button @click="fetchSubmissions" class="btn ghost" :disabled="isLoading">
            {{ isLoading ? 'Refreshing...' : 'Refresh' }}
          </button>
        </div>

        <div class="voter-wallet">
          <div class="field-group">
            <label for="voter-wallet">Voter Wallet ID</label>
            <input id="voter-wallet" type="text" v-model.trim="voterWallet" placeholder="Enter voter public wallet key" class="input-field">
          </div>
        </div>

        <div v-if="voteMessage || voteError || evaluateMessage || evaluateError" class="message-grid">
          <p v-if="voteMessage" class="status-message success">{{ voteMessage }}</p>
          <p v-if="voteError" class="status-message error">{{ voteError }}</p>
          <p v-if="evaluateMessage" class="status-message success">{{ evaluateMessage }}</p>
          <p v-if="evaluateError" class="status-message error">{{ evaluateError }}</p>
        </div>

        <div v-if="pendingSubmissions.length === 0" class="empty-state">
          No pending submissions are waiting for votes.
        </div>

        <div v-else class="submission-list">
          <article v-for="submission in pendingSubmissions" :key="submission.submission_id" class="submission-card">
            <div class="submission-header">
              <span class="status-pill pending">{{ formatStatus(submission.status) }}</span>
              <span>{{ formatDate(submission.created_at) }}</span>
            </div>

            <p class="submission-text">{{ submission.text_content }}</p>
            <p class="meta">Submitted by {{ shortenKey(submission.submitter) }}</p>

            <div class="submission-actions">
              <div class="vote-actions">
                <button @click="vote(submission.submission_id, 'original')" class="btn vote">Original</button>
                <button @click="vote(submission.submission_id, 'not_original')" class="btn vote">Not Original</button>
                <button @click="vote(submission.submission_id, 'unsure')" class="btn vote">Unsure</button>
              </div>
              <button @click="evaluateSubmission(submission.submission_id)" class="btn evaluate">
                Evaluate
              </button>
            </div>
          </article>
        </div>
      </section>

      <section class="card queue-card">
        <div class="card-heading">
          <div>
            <p class="section-label">Approved Content</p>
            <h2>Mint Queue</h2>
          </div>
          <button @click="fetchMintQueue" class="btn ghost" :disabled="isQueueLoading">
            {{ isQueueLoading ? 'Refreshing...' : 'Refresh Queue' }}
          </button>
        </div>

        <div v-if="mintMessage || mintError" class="message-stack">
          <p v-if="mintMessage" class="status-message success">{{ mintMessage }}</p>
          <p v-if="mintError" class="status-message error">{{ mintError }}</p>
        </div>

        <div v-if="mintQueue.length === 0" class="empty-state">
          No approved submissions are waiting to mint.
        </div>

        <div v-else class="queue-list">
          <article v-for="submission in mintQueue" :key="submission.submission_id" class="submission-card queue-item">
            <div class="submission-header">
              <span class="status-pill queued">{{ formatStatus(submission.status) }}</span>
              <span>{{ formatDate(submission.created_at) }}</span>
            </div>
            <p class="submission-text">{{ submission.text_content }}</p>
            <p class="meta">Submitted by {{ shortenKey(submission.submitter) }}</p>
            <div class="card-actions">
              <button @click="mintSubmission(submission.submission_id)" class="btn primary">
                Mint Block
              </button>
            </div>
          </article>
        </div>
      </section>
    </main>

    <nav class="navigation-card">
      <router-link to="/blockchain" class="btn secondary">View Blockchain</router-link>
      <button @click="goToHome" class="btn secondary">Home</button>
    </nav>
  </div>
</template>

<script>
import { apiClient, getApiErrorMessage } from '../config/api';

export default {
  data() {
    return {
      memeFile: null,
      wallet: '',
      voterWallet: '',
      textContent: '',
      submissions: [],
      mintQueue: [],
      lastSubmission: null,
      submitMessage: '',
      errorMessage: '',
      voteMessage: '',
      voteError: '',
      evaluateMessage: '',
      evaluateError: '',
      mintMessage: '',
      mintError: '',
      isSubmitting: false,
      isLoading: false,
      isQueueLoading: false,
    };
  },
  computed: {
    pendingSubmissions() {
      return this.submissions.filter((submission) => submission.status === 'pending');
    },
  },
  async created() {
    await this.refreshWorkflow();
  },
  methods: {
    uploadMeme(event) {
      this.memeFile = event.target.files[0] || null;
    },
    async refreshWorkflow() {
      await Promise.all([this.fetchSubmissions(), this.fetchMintQueue()]);
    },
    async submitMeme() {
      this.submitMessage = '';
      this.errorMessage = '';
      this.lastSubmission = null;

      if (!this.wallet) {
        this.errorMessage = 'Please enter your submitter wallet ID.';
        return;
      }
      if (!this.textContent) {
        this.errorMessage = 'Please enter the meme text or caption.';
        return;
      }
      if (!this.memeFile) {
        this.errorMessage = 'Please upload a meme image.';
        return;
      }

      const formData = new FormData();
      formData.append('image', this.memeFile);
      formData.append('submitter', this.wallet);
      formData.append('text_content', this.textContent);

      this.isSubmitting = true;
      try {
        const response = await apiClient.post('/submit_content', formData, {
          headers: { 'Content-Type': 'multipart/form-data' },
        });
        this.lastSubmission = response.data.submission;
        this.submitMessage = `${response.data.message || 'Content submitted successfully.'} Status: ${this.formatStatus(this.lastSubmission.status)}.`;
        this.textContent = '';
        this.memeFile = null;
        const fileInput = document.getElementById('meme-upload');
        if (fileInput) {
          fileInput.value = '';
        }
        await this.refreshWorkflow();
      } catch (error) {
        console.error('Error submitting meme:', error);
        this.errorMessage = getApiErrorMessage(error, 'Failed to submit meme.');
      } finally {
        this.isSubmitting = false;
      }
    },
    async fetchSubmissions() {
      this.isLoading = true;
      this.voteError = '';
      try {
        const response = await apiClient.get('/submissions');
        this.submissions = response.data.submissions || [];
      } catch (error) {
        console.error('Error fetching submissions:', error);
        this.voteError = getApiErrorMessage(error, 'Failed to load submissions.');
      } finally {
        this.isLoading = false;
      }
    },
    async fetchMintQueue() {
      this.isQueueLoading = true;
      this.mintError = '';
      try {
        const response = await apiClient.get('/mint-queue');
        this.mintQueue = response.data.mint_queue || [];
      } catch (error) {
        console.error('Error fetching mint queue:', error);
        this.mintError = getApiErrorMessage(error, 'Failed to load mint queue.');
      } finally {
        this.isQueueLoading = false;
      }
    },
    async vote(submissionId, voteType) {
      this.voteMessage = '';
      this.voteError = '';

      if (!this.voterWallet) {
        this.voteError = 'Please enter your voter wallet ID before voting.';
        return;
      }

      const formData = new FormData();
      formData.append('voter', this.voterWallet);
      formData.append('vote_type', voteType);

      try {
        const response = await apiClient.post(`/submissions/${submissionId}/vote`, formData, {
          headers: { 'Content-Type': 'multipart/form-data' },
        });
        this.voteMessage = `${response.data.message || 'Vote recorded successfully.'} Vote: ${this.formatStatus(voteType)}.`;
        await this.fetchSubmissions();
      } catch (error) {
        console.error('Error recording vote:', error);
        this.voteError = getApiErrorMessage(error, 'Failed to record vote.');
      }
    },
    async evaluateSubmission(submissionId) {
      this.evaluateMessage = '';
      this.evaluateError = '';

      try {
        const formData = new FormData();
        formData.append('automated_originality_passed', 'true');
        const response = await apiClient.post(`/submissions/${submissionId}/evaluate`, formData, {
          headers: { 'Content-Type': 'multipart/form-data' },
        });
        this.evaluateMessage = `${response.data.message || 'Submission evaluated successfully.'} Status: ${this.formatStatus(response.data.submission?.status)}.`;
        await this.refreshWorkflow();
      } catch (error) {
        console.error('Error evaluating submission:', error);
        this.evaluateError = getApiErrorMessage(error, 'Failed to evaluate submission.');
      }
    },
    async mintSubmission(submissionId) {
      this.mintMessage = '';
      this.mintError = '';

      try {
        const response = await apiClient.post(`/mint-queue/${submissionId}/mint`);
        this.mintMessage = `${response.data.message || 'Submission minted successfully.'} Status: ${this.formatStatus(response.data.submission?.status)}.`;
        await this.refreshWorkflow();
      } catch (error) {
        console.error('Error minting submission:', error);
        this.mintError = getApiErrorMessage(error, 'Failed to mint submission.');
      }
    },
    formatStatus(status) {
      return (status || '').replace(/_/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());
    },
    formatDate(timestamp) {
      if (!timestamp) {
        return 'Time unavailable';
      }
      return new Date(timestamp * 1000).toLocaleString();
    },
    shortenKey(key) {
      if (!key || key.length <= 18) {
        return key || 'Unknown wallet';
      }
      return `${key.slice(0, 10)}...${key.slice(-8)}`;
    },
    goToHome() {
      this.$router.push('/');
    },
  },
};
</script>

<style scoped>
.dashboard-page {
  min-height: 100vh;
  padding: 40px 24px 56px;
  background:
    radial-gradient(circle at top, rgba(255, 71, 71, 0.12), transparent 34rem),
    radial-gradient(circle, #1a1a1a 0%, #000 100%);
  color: #fff;
  font-family: Arial, sans-serif;
}

.dashboard-header,
.dashboard-shell,
.navigation-card {
  width: min(1180px, 100%);
  margin: 0 auto;
}

.dashboard-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 24px;
  margin-bottom: 28px;
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
p {
  margin-top: 0;
}

h1 {
  margin-bottom: 8px;
  font-size: 3rem;
  line-height: 1;
  text-shadow: 3px 3px 6px rgba(255, 0, 0, 0.5);
}

h2 {
  margin-bottom: 0;
  font-size: 1.35rem;
  line-height: 1.2;
}

.subtitle {
  margin-bottom: 0;
  color: #c6c6c6;
  font-size: 1.05rem;
}

.dashboard-shell {
  display: grid;
  grid-template-columns: minmax(320px, 430px) minmax(420px, 1fr);
  grid-template-areas:
    "submit voting"
    "queue voting";
  gap: 22px;
  align-items: start;
}

.submit-card {
  grid-area: submit;
}

.voting-card {
  grid-area: voting;
}

.queue-card {
  grid-area: queue;
}

.card,
.navigation-card {
  background: rgba(28, 28, 28, 0.94);
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 8px;
  box-shadow: 0 12px 28px rgba(0, 0, 0, 0.35);
}

.card {
  padding: 22px;
}

.card-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 20px;
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

.status-pill.pending {
  background: rgba(255, 201, 71, 0.14);
  color: #ffd884;
}

.status-pill.queued {
  background: rgba(141, 245, 166, 0.14);
  color: #8df5a6;
}

.form-stack,
.message-stack,
.submission-list,
.queue-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.field-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.field-group label {
  color: #e4e4e4;
  font-size: 0.93rem;
  font-weight: 700;
}

.input-field,
.file-input {
  width: 100%;
  min-height: 46px;
  padding: 12px;
  border: 1px solid rgba(255, 71, 71, 0.78);
  border-radius: 8px;
  background: #181818;
  color: #fff;
  font-size: 0.98rem;
}

.input-field:focus,
.file-input:focus {
  outline: 2px solid rgba(255, 71, 71, 0.35);
  outline-offset: 2px;
}

.text-area {
  min-height: 118px;
  resize: vertical;
}

.voter-wallet {
  margin-bottom: 18px;
  padding: 16px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 8px;
  background: rgba(0, 0, 0, 0.22);
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

.primary {
  background: linear-gradient(135deg, #ff4747 0%, #d71919 100%);
  box-shadow: 0 6px 16px rgba(255, 0, 0, 0.28);
}

.secondary {
  background: linear-gradient(135deg, #4a90e2 0%, #2455a5 100%);
  box-shadow: 0 6px 16px rgba(74, 144, 226, 0.24);
}

.ghost,
.vote,
.evaluate {
  background: #2b2b2b;
  border-color: rgba(255, 255, 255, 0.16);
  box-shadow: none;
}

.evaluate {
  border-color: rgba(255, 71, 71, 0.45);
  color: #ffb0b0;
}

.card-actions,
.header-actions,
.submission-actions,
.vote-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.card-actions {
  margin-top: 18px;
}

.submission-actions {
  justify-content: space-between;
  margin-top: 16px;
}

.vote-actions {
  gap: 8px;
}

.message-grid {
  display: grid;
  gap: 10px;
  margin-bottom: 18px;
}

.status-message {
  margin: 0;
  padding: 11px 12px;
  border-radius: 8px;
  line-height: 1.4;
}

.success {
  background: rgba(141, 245, 166, 0.12);
  color: #8df5a6;
}

.error {
  background: rgba(255, 140, 140, 0.12);
  color: #ff8c8c;
}

.submission-result,
.submission-card,
.empty-state {
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 8px;
  background: rgba(8, 8, 8, 0.58);
}

.submission-result {
  margin-top: 18px;
  padding: 14px;
}

.submission-card {
  padding: 16px;
}

.empty-state {
  padding: 18px;
  color: #bbb;
}

.submission-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
  color: #bbb;
  font-size: 0.88rem;
}

.submission-text {
  margin-bottom: 10px;
  color: #f3f3f3;
  font-size: 1rem;
  line-height: 1.5;
  word-break: break-word;
}

.hint,
.meta {
  margin-bottom: 0;
  color: #b8b8b8;
  font-size: 0.9rem;
  line-height: 1.4;
}

.navigation-card {
  display: flex;
  justify-content: center;
  gap: 12px;
  margin-top: 22px;
  padding: 16px;
}

@media (max-width: 980px) {
  .dashboard-header {
    align-items: flex-start;
    flex-direction: column;
  }

  .dashboard-shell {
    grid-template-columns: minmax(0, 1fr);
    grid-template-areas:
      "submit"
      "voting"
      "queue";
  }
}

@media (max-width: 620px) {
  .dashboard-page {
    padding: 28px 14px 40px;
  }

  h1 {
    font-size: 2.3rem;
  }

  .card,
  .navigation-card {
    padding: 16px;
  }

  .card-heading,
  .submission-header,
  .submission-actions,
  .navigation-card {
    align-items: stretch;
    flex-direction: column;
  }

  .btn,
  .header-actions {
    width: 100%;
  }
}
</style>
