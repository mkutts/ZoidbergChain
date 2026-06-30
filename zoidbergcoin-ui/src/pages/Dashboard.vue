<template>
  <div class="dashboard-container">
    <h1>Dashboard</h1>
    <p class="subtitle">Submit content for Task 1 community review</p>

    <div class="content-grid">
      <section class="panel">
        <h2>Submit Meme/Content</h2>

        <label for="wallet" class="label">Submitter Wallet ID</label>
        <input id="wallet" type="text" v-model.trim="wallet" placeholder="Enter your public wallet key" class="input-field">

        <label for="content-text" class="label">Content Text</label>
        <textarea id="content-text" v-model.trim="textContent" placeholder="Enter the meme text or caption" class="input-field text-area"></textarea>

        <label for="meme-upload" class="label">Upload Meme Image</label>
        <input type="file" id="meme-upload" accept=".jpg,.jpeg,.png,.webp" @change="uploadMeme" class="file-input">

        <button @click="submitMeme" class="btn primary" :disabled="isSubmitting">
          {{ isSubmitting ? 'Submitting...' : 'Submit for Review' }}
        </button>

        <p v-if="submitMessage" class="status-message success">{{ submitMessage }}</p>
        <p v-if="errorMessage" class="status-message error">{{ errorMessage }}</p>

        <div v-if="lastSubmission" class="submission-result">
          <p><strong>Submission ID:</strong> {{ lastSubmission.submission_id }}</p>
          <p><strong>Status:</strong> <span class="status-pill">{{ formatStatus(lastSubmission.status) }}</span></p>
          <p class="hint">Submitted content is pending community voting and is not minted automatically.</p>
        </div>

        <router-link to="/blockchain" class="btn secondary">View Blockchain</router-link>
        <button @click="goToHome" class="btn secondary">Home</button>
      </section>

      <section class="panel">
        <div class="section-heading">
          <h2>Community Voting</h2>
          <button @click="fetchSubmissions" class="btn small" :disabled="isLoading">
            {{ isLoading ? 'Refreshing...' : 'Refresh' }}
          </button>
        </div>

        <label for="voter-wallet" class="label">Voter Wallet ID</label>
        <input id="voter-wallet" type="text" v-model.trim="voterWallet" placeholder="Enter voter public wallet key" class="input-field">

        <p v-if="voteMessage" class="status-message success">{{ voteMessage }}</p>
        <p v-if="voteError" class="status-message error">{{ voteError }}</p>

        <div v-if="submissions.length === 0" class="empty-state">
          No submissions found yet.
        </div>

        <article v-for="submission in submissions" :key="submission.submission_id" class="submission-item">
          <div class="submission-header">
            <strong>{{ formatStatus(submission.status) }}</strong>
            <span>{{ formatDate(submission.created_at) }}</span>
          </div>
          <p>{{ submission.text_content }}</p>
          <p class="meta">Submitted by {{ shortenKey(submission.submitter) }}</p>
          <div class="vote-actions" v-if="submission.status === 'pending'">
            <button @click="vote(submission.submission_id, 'original')" class="btn vote">Original</button>
            <button @click="vote(submission.submission_id, 'not_original')" class="btn vote">Not Original</button>
            <button @click="vote(submission.submission_id, 'unsure')" class="btn vote">Unsure</button>
          </div>
        </article>
      </section>
    </div>
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
      lastSubmission: null,
      submitMessage: '',
      errorMessage: '',
      voteMessage: '',
      voteError: '',
      isSubmitting: false,
      isLoading: false,
    };
  },
  async created() {
    await this.fetchSubmissions();
  },
  methods: {
    uploadMeme(event) {
      this.memeFile = event.target.files[0] || null;
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
        this.submitMessage = response.data.message || 'Content submitted successfully.';
        this.textContent = '';
        this.memeFile = null;
        const fileInput = document.getElementById('meme-upload');
        if (fileInput) {
          fileInput.value = '';
        }
        await this.fetchSubmissions();
      } catch (error) {
        console.error('Error submitting meme:', error);
        this.errorMessage = getApiErrorMessage(error, 'Failed to submit meme.');
      } finally {
        this.isSubmitting = false;
      }
    },
    async fetchSubmissions() {
      this.isLoading = true;
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
    async vote(submissionId, voteType) {
      this.voteMessage = '';
      this.voteError = '';

      if (!this.voterWallet) {
        this.voteError = 'Please enter your voter wallet ID.';
        return;
      }

      const formData = new FormData();
      formData.append('voter', this.voterWallet);
      formData.append('vote_type', voteType);

      try {
        const response = await apiClient.post(`/submissions/${submissionId}/vote`, formData, {
          headers: { 'Content-Type': 'multipart/form-data' },
        });
        this.voteMessage = response.data.message || 'Vote recorded successfully.';
        await this.fetchSubmissions();
      } catch (error) {
        console.error('Error recording vote:', error);
        this.voteError = getApiErrorMessage(error, 'Failed to record vote.');
      }
    },
    formatStatus(status) {
      return (status || '').replace(/_/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());
    },
    formatDate(timestamp) {
      if (!timestamp) {
        return '';
      }
      return new Date(timestamp * 1000).toLocaleString();
    },
    shortenKey(key) {
      if (!key || key.length <= 18) {
        return key;
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
.dashboard-container {
  min-height: 100vh;
  padding: 40px 20px;
  text-align: center;
  background: radial-gradient(circle, #1a1a1a 0%, #000000 100%);
  color: #fff;
  font-family: Arial, sans-serif;
}

h1 {
  font-size: 3rem;
  margin-bottom: 10px;
  text-shadow: 3px 3px 6px rgba(255, 0, 0, 0.5);
}

h2 {
  font-size: 1.35rem;
  margin-bottom: 16px;
}

.subtitle {
  font-size: 1.2rem;
  margin-bottom: 24px;
  font-weight: 300;
  color: #bbb;
}

.content-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(300px, 520px));
  justify-content: center;
  gap: 24px;
}

.panel {
  background: rgba(30, 30, 30, 0.92);
  padding: 24px;
  border-radius: 8px;
  box-shadow: 0 4px 10px rgba(255, 0, 0, 0.5);
  display: flex;
  flex-direction: column;
  gap: 14px;
  text-align: left;
}

.section-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.label {
  font-size: 0.95rem;
  color: #ddd;
}

.input-field,
.file-input {
  width: 100%;
  padding: 12px;
  font-size: 1rem;
  border-radius: 8px;
  text-align: left;
  background: #222;
  color: #fff;
  border: 1px solid #ff4747;
}

.text-area {
  min-height: 96px;
  resize: vertical;
}

.file-input {
  cursor: pointer;
}

.btn {
  width: 100%;
  padding: 12px;
  border: none;
  border-radius: 8px;
  font-size: 1rem;
  cursor: pointer;
  transition: 0.2s ease-in-out;
  font-weight: bold;
  text-align: center;
  text-decoration: none;
}

.btn:disabled {
  cursor: not-allowed;
  opacity: 0.65;
}

.primary {
  background: linear-gradient(135deg, #ff4747 0%, #ff1616 100%);
  color: white;
  box-shadow: 0 4px 10px rgba(255, 0, 0, 0.6);
}

.secondary,
.small {
  background: linear-gradient(135deg, #4a90e2 0%, #2455a5 100%);
  color: white;
  box-shadow: 0 4px 10px rgba(74, 144, 226, 0.5);
}

.small {
  width: auto;
  min-width: 110px;
  padding: 9px 12px;
  font-size: 0.9rem;
}

.vote {
  background: #2f2f2f;
  color: white;
  border: 1px solid #666;
  box-shadow: none;
}

.status-message {
  line-height: 1.4;
  text-align: left;
}

.success {
  color: #8df5a6;
}

.error {
  color: #ff8c8c;
}

.submission-result,
.submission-item,
.empty-state {
  background: rgba(12, 12, 12, 0.8);
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 8px;
  padding: 14px;
}

.submission-result p,
.submission-item p {
  margin: 6px 0;
  word-break: break-word;
}

.status-pill {
  color: #8df5a6;
}

.hint,
.meta {
  color: #bbb;
  font-size: 0.92rem;
}

.submission-header,
.vote-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.submission-header {
  color: #ffb0b0;
}

.vote-actions {
  margin-top: 12px;
}

@media (max-width: 900px) {
  .content-grid {
    grid-template-columns: minmax(280px, 520px);
  }

  .submission-header,
  .vote-actions,
  .section-heading {
    align-items: stretch;
    flex-direction: column;
  }

  .small {
    width: 100%;
  }
}
</style>
