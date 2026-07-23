<template>
  <div class="dashboard-page">
    <header class="dashboard-header">
      <div>
        <p class="eyebrow">Originality Consensus</p>
        <h1>ZoidbergCoin Dashboard</h1>
        <p class="subtitle">Community-approved original memes power every certified block.</p>
      </div>
      <div class="header-actions">
        <button @click="refreshWorkflow" class="btn secondary" :disabled="isRefreshing">
          {{ isRefreshing ? 'Refreshing...' : 'Refresh' }}
        </button>
        <router-link to="/blockchain" class="btn ghost">Explorer</router-link>
      </div>
    </header>

    <WalletPanel />

    <main class="dashboard-shell">
      <section class="section-panel summary-panel">
        <div class="card-heading">
          <div>
            <p class="section-label">Chain Summary</p>
            <h2>Current Consensus</h2>
          </div>
          <span class="workflow-chip">Meme Originality</span>
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

      <section class="section-panel content-panel">
        <div class="card-heading">
          <div>
            <p class="section-label">Content Upload</p>
            <h2>Upload First, Then Submit</h2>
          </div>
          <span class="workflow-chip">Content Object</span>
        </div>

        <p class="section-note">
          Upload an image or text payload first, then reuse the returned `content_id` and `content_hash` in the submission flow.
        </p>

        <div class="form-stack">
          <div class="field-group">
            <label for="content-upload-file">Content File</label>
            <input
              id="content-upload-file"
              type="file"
              accept=".jpg,.jpeg,.png,.webp,.gif,.txt"
              @change="onContentUploadFileChange"
              class="file-input"
            >
          </div>

          <div class="field-group">
            <label for="content-upload-text">Text Payload</label>
            <textarea
              id="content-upload-text"
              v-model.trim="contentUploadText"
              placeholder="Optional text payload for /content/text"
              class="input-field text-area"
            ></textarea>
          </div>

          <div class="field-group">
            <label for="content-caption">Caption</label>
            <input
              id="content-caption"
              type="text"
              v-model.trim="contentCaption"
              placeholder="Optional caption or alt text"
              class="input-field"
            >
          </div>
        </div>

        <div class="card-actions">
          <button @click="uploadContent" class="btn primary" :disabled="isContentUploading">
            {{ isContentUploading ? 'Uploading...' : 'Upload Content' }}
          </button>
          <button v-if="uploadedContent" @click="useUploadedContentForSubmission" class="btn secondary">
            Use for Submission
          </button>
          <button v-if="uploadedContent" @click="clearUploadedContent" class="btn ghost">
            Clear
          </button>
        </div>

        <div v-if="contentUploadMessage || contentUploadError" class="message-stack">
          <p v-if="contentUploadMessage" class="status-message success">{{ contentUploadMessage }}</p>
          <p v-if="contentUploadError" class="status-message error">{{ contentUploadError }}</p>
        </div>

        <div v-if="uploadedContent" class="content-preview-card">
          <p v-if="uploadedContentPreviewError" class="status-message error">{{ uploadedContentPreviewError }}</p>
          <div class="submission-header">
            <span class="status-pill" :class="contentStatusClass(uploadedContent)">{{ contentStatusLabel(uploadedContent) }}</span>
            <span>{{ formatDate(uploadedContent.created_at) }}</span>
          </div>
          <div v-if="isImageContent(uploadedContent) && uploadedContent.download_url" class="content-preview">
            <img :src="contentUrl(uploadedContent.download_url)" alt="Uploaded meme preview" class="content-image">
          </div>
          <div v-else-if="isTextContent(uploadedContent)" class="content-text-preview">
            <pre>{{ uploadedContent.text_content || contentUploadText || 'Text preview unavailable.' }}</pre>
          </div>
          <div class="detail-grid">
            <div>
              <span>Content ID</span>
              <strong>{{ shortenHash(uploadedContent.content_id) }}</strong>
            </div>
            <div>
              <span>Content Hash</span>
              <strong>{{ shortenHash(uploadedContent.content_hash) }}</strong>
            </div>
            <div>
              <span>Content Type</span>
              <strong>{{ uploadedContent.content_type || 'Missing' }}</strong>
            </div>
            <div>
              <span>MIME Type</span>
              <strong>{{ uploadedContent.mime_type || 'Missing' }}</strong>
            </div>
            <div>
              <span>Storage Status</span>
              <strong>{{ formatContentStatus(uploadedContent.storage_status) }}</strong>
            </div>
            <div>
              <span>Caption</span>
              <strong>{{ uploadedContent.caption || 'None' }}</strong>
            </div>
          </div>
          <p v-if="uploadedContent.download_url" class="content-link-row">
            <a :href="contentUrl(uploadedContent.download_url)" target="_blank" rel="noreferrer">View or download content</a>
          </p>
        </div>
      </section>

      <section class="section-panel submit-panel">
        <div class="card-heading">
          <div>
            <p class="section-label">Create Submission</p>
            <h2>Submit Meme/Content</h2>
          </div>
          <span class="workflow-chip">Creates Pending</span>
        </div>

        <div class="form-stack">
          <div class="field-group">
            <label>Creator Account</label>
            <div class="derived-wallet-panel">
              <strong v-if="submissionWalletAddress">{{ submissionWalletAddress }}</strong>
              <strong v-else>Connect and verify MetaMask to derive the creator account.</strong>
              <span class="meta">New submissions derive the creator account from the verified MetaMask signer.</span>
            </div>
          </div>

          <div class="field-group">
            <label for="content-text">Content Text</label>
            <textarea id="content-text" v-model.trim="textContent" placeholder="Enter the meme text or caption" class="input-field text-area"></textarea>
          </div>

          <div class="field-group">
            <label for="meme-upload">Meme Image</label>
            <input type="file" id="meme-upload" accept=".jpg,.jpeg,.png,.webp" @change="uploadMeme" class="file-input">
          </div>

          <div class="field-group">
            <label for="submission-content-hash">Content Hash</label>
            <input id="submission-content-hash" type="text" v-model.trim="submissionContentHash" placeholder="Optional content_hash from upload" class="input-field">
          </div>

          <div class="field-group">
            <label for="submission-content-id">Content ID</label>
            <input id="submission-content-id" type="text" v-model.trim="submissionContentId" placeholder="Optional content_id from upload" class="input-field">
          </div>
        </div>

        <div class="card-actions">
          <button @click="submitMeme" class="btn primary" :disabled="isSubmitting || !canSubmitSignedContent">
            {{ submitButtonLabel }}
          </button>
        </div>

        <p class="hint wallet-flow-hint">
          {{ submissionIdentityHint }}
        </p>

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
          <div class="detail-grid">
            <div>
              <span>Content ID</span>
              <strong>{{ shortenHash(lastSubmission.content_id) }}</strong>
            </div>
            <div>
              <span>Content Hash</span>
              <strong>{{ shortenHash(lastSubmission.content_hash) }}</strong>
            </div>
            <div>
              <span>Content Type</span>
              <strong>{{ lastSubmission.content_type || 'Missing' }}</strong>
            </div>
            <div>
              <span>Storage Status</span>
              <strong>{{ formatContentStatus(lastSubmission.storage_status) }}</strong>
            </div>
          </div>
          <div v-if="hasContentPreview(lastSubmission)" class="content-preview">
            <img v-if="isImageContent(lastSubmission) && lastSubmission.download_url" :src="contentUrl(lastSubmission.download_url)" alt="Submitted content preview" class="content-image">
            <pre v-else-if="isTextContent(lastSubmission)">{{ lastSubmission.text_content }}</pre>
          </div>
          <p v-if="lastSubmission.download_url" class="content-link-row">
            <a :href="contentUrl(lastSubmission.download_url)" target="_blank" rel="noreferrer">Download submitted content</a>
          </p>
          <p class="hint">Submitted content enters community voting before it can be certified.</p>
        </div>
      </section>

      <section class="section-panel voting-panel">
        <div class="card-heading">
          <div>
            <p class="section-label">Pending Community Vote</p>
            <h2>Review Submissions</h2>
          </div>
          <button @click="fetchSubmissions" class="btn ghost" :disabled="isLoading">
            {{ isLoading ? 'Refreshing...' : 'Refresh' }}
          </button>
        </div>

        <div class="voter-wallet">
          <div class="field-group">
            <label>Voter Account</label>
            <div class="derived-wallet-panel">
              <strong v-if="voteWalletAddress">{{ voteWalletAddress }}</strong>
              <strong v-else>Connect and verify MetaMask to derive the voter account.</strong>
              <span class="meta">New votes derive the voter account from the verified MetaMask signer.</span>
            </div>
          </div>
        </div>

        <p class="hint wallet-flow-hint">
          {{ votingIdentityHint }}
        </p>

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

            <div v-if="hasContentPreview(submission)" class="content-preview">
            <img v-if="isImageContent(submission) && submission.download_url" :src="contentUrl(submission.download_url)" alt="Submission content preview" class="content-image">
              <pre v-else-if="isTextContent(submission)">{{ submission.text_content }}</pre>
            </div>

            <p class="submission-text">{{ submission.text_content }}</p>
            <p class="meta">Submitted by {{ shortenKey(submission.submitter) }}</p>
            <div class="content-state-line">
              <span class="status-pill" :class="contentStatusClass(submission)">{{ contentStatusLabel(submission) }}</span>
              <span class="meta-chip">ID {{ shortenHash(submission.content_id) }}</span>
              <span class="meta-chip">Hash {{ shortenHash(submission.content_hash) }}</span>
              <span class="meta-chip">{{ submission.mime_type || submission.content_type || 'No MIME data' }}</span>
              <button
                v-if="submission.content_hash && needsContentSync(submission)"
                @click="syncContent(submission.content_hash)"
                class="btn ghost sync-btn"
                :disabled="syncingContentHash === submission.content_hash"
              >
                {{ syncingContentHash === submission.content_hash ? 'Syncing...' : 'Sync Content' }}
              </button>
              <a v-else-if="submission.download_url" :href="contentUrl(submission.download_url)" target="_blank" rel="noreferrer" class="meta-link">
                View Content
              </a>
            </div>

            <div class="submission-actions">
              <p v-if="currentWalletVoteForSubmission(submission)" class="meta">
                Your vote: {{ formatStatus(currentWalletVoteForSubmission(submission).vote_type) }}
              </p>
              <div class="vote-actions">
                <button @click="vote(submission.submission_id, 'original')" class="btn vote" :disabled="voteDisabled(submission)">
                  Original
                </button>
                <button @click="vote(submission.submission_id, 'not_original')" class="btn vote" :disabled="voteDisabled(submission)">
                  Not Original
                </button>
                <button @click="vote(submission.submission_id, 'unsure')" class="btn vote" :disabled="voteDisabled(submission)">
                  Unsure
                </button>
              </div>
              <button @click="evaluateSubmission(submission.submission_id)" class="btn evaluate">
                Evaluate
              </button>
            </div>
          </article>
        </div>
      </section>

      <section class="section-panel approved-panel">
        <div class="card-heading">
          <div>
            <p class="section-label">Approved / Certificate Ready</p>
            <h2>Originality Certificates</h2>
          </div>
          <span class="workflow-chip">Vote Snapshot</span>
        </div>

        <p v-if="certificateError" class="status-message error">{{ certificateError }}</p>

        <div v-if="approvedCertificateSubmissions.length === 0" class="empty-state">
          No certified approved submissions are ready yet.
        </div>

        <div v-else class="submission-list">
          <article v-for="submission in approvedCertificateSubmissions" :key="submission.submission_id" class="submission-card">
            <div class="submission-header">
              <span class="status-pill ready">{{ formatStatus(submission.status) }}</span>
              <span>{{ formatDate(submission.created_at) }}</span>
            </div>

            <div v-if="hasContentPreview(submission)" class="content-preview">
            <img v-if="isImageContent(submission) && submission.download_url" :src="contentUrl(submission.download_url)" alt="Certificate content preview" class="content-image">
              <pre v-else-if="isTextContent(submission)">{{ submission.text_content }}</pre>
            </div>

            <p class="submission-text">{{ submission.text_content }}</p>
            <div class="detail-grid">
              <div>
                <span>Certificate Status</span>
                <strong class="text-success">exists</strong>
              </div>
              <div>
                <span>Certificate ID</span>
                <strong>{{ shortenHash(getCertificate(submission)?.certificate_id) || 'Missing' }}</strong>
              </div>
              <div>
                <span>Content ID</span>
                <strong>{{ shortenHash(submission.content_id || getCertificate(submission)?.content_id) }}</strong>
              </div>
              <div>
                <span>Approval</span>
                <strong>{{ formatPercent(getCertificate(submission)?.approval_percentage) }}</strong>
              </div>
              <div>
                <span>Decisive Votes</span>
                <strong>{{ getCertificate(submission)?.decisive_vote_total ?? 'Missing' }}</strong>
              </div>
              <div>
                <span>Vote Hash</span>
                <strong>{{ shortenHash(getCertificate(submission)?.vote_hash) || 'Missing' }}</strong>
              </div>
              <div>
                <span>Originality Score</span>
                <strong>{{ formatScore(getCertificate(submission)?.originality_score) }}</strong>
              </div>
              <div>
                <span>Content Type</span>
                <strong>{{ submission.content_type || 'Missing' }}</strong>
              </div>
              <div>
                <span>MIME Type</span>
                <strong>{{ submission.mime_type || 'Missing' }}</strong>
              </div>
              <div>
                <span>Storage Status</span>
                <strong>{{ formatContentStatus(submission.storage_status) }}</strong>
              </div>
            </div>
            <div class="content-state-line">
              <span class="status-pill" :class="contentStatusClass(submission)">{{ contentStatusLabel(submission) }}</span>
              <a v-if="submission.download_url" :href="contentUrl(submission.download_url)" target="_blank" rel="noreferrer" class="meta-link">
                View Content
              </a>
            </div>
          </article>
        </div>
      </section>

      <section v-if="approvedMissingCertificateSubmissions.length > 0" class="section-panel missing-panel">
        <div class="card-heading">
          <div>
            <p class="section-label">Approved / Certificate Missing</p>
            <h2>Needs Certificate Repair</h2>
          </div>
          <span class="workflow-chip warning-chip">Not Mintable</span>
        </div>

        <div class="submission-list">
          <article v-for="submission in approvedMissingCertificateSubmissions" :key="submission.submission_id" class="submission-card">
            <div class="submission-header">
              <span class="status-pill pending">{{ formatStatus(submission.status) }}</span>
              <span>{{ formatDate(submission.created_at) }}</span>
            </div>
            <div v-if="hasContentPreview(submission)" class="content-preview">
            <img v-if="isImageContent(submission) && submission.download_url" :src="contentUrl(submission.download_url)" alt="Missing certificate submission preview" class="content-image">
              <pre v-else-if="isTextContent(submission)">{{ submission.text_content }}</pre>
            </div>
            <p class="submission-text">{{ submission.text_content }}</p>
            <p class="queue-warning">Originality certificate is missing. This submission is not certificate-ready and cannot be minted.</p>

            <div class="detail-grid">
              <div>
                <span>Submission ID</span>
                <strong>{{ shortenHash(submission.submission_id) }}</strong>
              </div>
              <div>
                <span>Content Hash</span>
                <strong>{{ shortenHash(submission.content_hash) }}</strong>
              </div>
              <div>
                <span>Content ID</span>
                <strong>{{ shortenHash(submission.content_id) }}</strong>
              </div>
              <div>
                <span>Creator Account</span>
                <strong>{{ shortenKey(submission.submitter) }}</strong>
              </div>
              <div>
                <span>Certificate Status</span>
                <strong class="text-warning">missing</strong>
              </div>
              <div>
                <span>Storage Status</span>
                <strong>{{ formatContentStatus(submission.storage_status) }}</strong>
              </div>
            </div>
            <div class="content-state-line">
              <span class="status-pill" :class="contentStatusClass(submission)">{{ contentStatusLabel(submission) }}</span>
              <button
                v-if="submission.content_hash && needsContentSync(submission)"
                @click="syncContent(submission.content_hash)"
                class="btn ghost sync-btn"
                :disabled="syncingContentHash === submission.content_hash"
              >
                {{ syncingContentHash === submission.content_hash ? 'Syncing...' : 'Sync Content' }}
              </button>
            </div>
          </article>
        </div>
      </section>

      <section class="section-panel queue-panel">
        <div class="card-heading">
          <div>
            <p class="section-label">Mint Queue</p>
            <h2>Certified Queue</h2>
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
          No certified submissions are waiting to mint.
        </div>

        <div v-else class="queue-list">
          <article v-for="(submission, index) in mintQueue" :key="submission.submission_id" class="submission-card queue-item">
            <div class="submission-header">
              <span class="status-pill" :class="submission.mintable ? 'ready' : 'warning-chip'">
                {{ submission.mintable ? 'Mintable' : 'Blocked' }}
              </span>
              <span>{{ formatDate(submission.created_at) }}</span>
            </div>
            <div v-if="hasContentPreview(submission)" class="content-preview">
              <img v-if="isImageContent(submission) && submission.download_url" :src="contentUrl(submission.download_url)" alt="Mint queue content preview" class="content-image">
              <pre v-else-if="isTextContent(submission)">{{ submission.text_content }}</pre>
            </div>
            <p class="submission-text">{{ submission.text_content }}</p>

            <div class="detail-grid">
              <div>
                <span>Submission ID</span>
                <strong>{{ shortenHash(submission.submission_id) }}</strong>
              </div>
              <div>
                <span>Certificate ID</span>
                <strong>{{ shortenHash(getCertificate(submission)?.certificate_id) || 'Missing' }}</strong>
              </div>
              <div>
                <span>Content Hash</span>
                <strong>{{ shortenHash(getCertificate(submission)?.content_hash || submission.content_hash) }}</strong>
              </div>
              <div>
                <span>Content ID</span>
                <strong>{{ shortenHash(getCertificate(submission)?.content_id || submission.content_id) }}</strong>
              </div>
              <div>
                <span>Content Type</span>
                <strong>{{ formatContentField(submission.content_type, submission.content_metadata_missing) }}</strong>
              </div>
              <div>
                <span>MIME Type</span>
                <strong>{{ formatContentField(submission.mime_type, submission.content_metadata_missing) }}</strong>
              </div>
              <div>
                <span>Originality Score</span>
                <strong>{{ formatScore(getCertificate(submission)?.originality_score) }}</strong>
              </div>
              <div>
                <span>Creator Account</span>
                <strong>{{ shortenKey(getCertificate(submission)?.creator_wallet || submission.submitter) }}</strong>
              </div>
              <div>
                <span>Storage Status</span>
                <strong>{{ formatContentField(formatContentStatus(submission.storage_status), submission.content_metadata_missing) }}</strong>
              </div>
              <div>
                <span>Certificate Status</span>
                <strong>{{ formatCertificateStatus(submission.certificate_status) }}</strong>
              </div>
            </div>
            <div class="content-state-line">
              <span class="status-pill" :class="contentStatusClass(submission)">{{ contentStatusLabel(submission) }}</span>
              <span class="meta-chip">Content ID {{ shortenHash(submission.content_id) }}</span>
              <span class="meta-chip">Hash {{ shortenHash(submission.content_hash) }}</span>
              <a v-if="submission.download_url" :href="contentUrl(submission.download_url)" target="_blank" rel="noreferrer" class="meta-link">
                View Content
              </a>
              <button
                v-if="submission.content_hash && needsContentSync(submission)"
                @click="syncContent(submission.content_hash)"
                class="btn ghost sync-btn"
                :disabled="syncingContentHash === submission.content_hash"
              >
                {{ syncingContentHash === submission.content_hash ? 'Syncing...' : 'Sync Content' }}
              </button>
            </div>

            <p v-if="submission.mint_block_reason" class="queue-warning">
              {{ formatMintReason(submission.mint_block_reason) }}
            </p>

            <div class="card-actions">
              <button
                v-if="showMintQueueTools && submission.submission_id && !submission.mint_blocked"
                @click="blockMinting(submission)"
                class="btn ghost"
              >
                Quarantine
              </button>
              <button
                v-if="showMintQueueTools && submission.mint_blocked"
                @click="unblockMinting(submission)"
                class="btn ghost"
              >
                Unblock
              </button>
              <button
                @click="mintSubmission(submission.submission_id)"
                class="btn primary"
                :disabled="!submission.mintable || mintingSubmissionId === submission.submission_id"
              >
                {{ mintingSubmissionId === submission.submission_id ? 'Minting...' : 'Mint Block' }}
              </button>
            </div>
          </article>
        </div>
      </section>

      <section class="section-panel blocks-panel">
        <div class="card-heading">
          <div>
            <p class="section-label">Recent Blocks</p>
            <h2>Certified Meme Blocks</h2>
          </div>
          <button @click="fetchRecentBlocks" class="btn ghost" :disabled="isBlocksLoading">
            {{ isBlocksLoading ? 'Refreshing...' : 'Refresh Blocks' }}
          </button>
        </div>

        <p v-if="blocksError" class="status-message error">{{ blocksError }}</p>

        <div v-if="recentBlocks.length === 0" class="empty-state">
          No blocks loaded yet.
        </div>

        <div v-else class="block-list">
          <article v-for="block in recentBlocks" :key="block.hash || block.index" class="block-card">
            <div class="block-heading">
              <h3>Block #{{ block.index }}</h3>
              <span :class="block.certificate_id ? 'status-pill ready' : 'status-pill'">
                {{ block.certificate_id ? 'Certified Meme' : 'Genesis / Legacy' }}
              </span>
            </div>

            <div v-if="hasContentPreview(block)" class="content-preview">
              <img v-if="isImageContent(block) && block.download_url" :src="contentUrl(block.download_url)" alt="Block content preview" class="content-image">
              <pre v-else-if="isTextContent(block)">{{ block.meme && block.meme.text ? block.meme.text : 'Text preview unavailable.' }}</pre>
              <img v-else-if="block.meme && block.meme.encoded_image" :src="'data:image/png;base64,' + block.meme.encoded_image" alt="Block meme preview" class="content-image">
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
                <span>Content ID</span>
                <strong>{{ shortenHash(block.content_id) }}</strong>
              </div>
              <div v-if="block.certificate_id">
                <span>Content Type</span>
                <strong>{{ block.content_type || 'Missing' }}</strong>
              </div>
              <div v-if="block.certificate_id">
                <span>MIME Type</span>
                <strong>{{ block.mime_type || 'Missing' }}</strong>
              </div>
              <div v-if="block.certificate_id">
                <span>Originality Score</span>
                <strong>{{ formatScore(block.originality_score) }}</strong>
              </div>
              <div v-if="block.certificate_id">
                <span>Creator Account</span>
                <strong>{{ shortenKey(block.creator_wallet) }}</strong>
              </div>
              <div v-if="block.certificate_id">
                <span>Reward Type</span>
                <strong>{{ block.reward_type || 'Missing' }}</strong>
              </div>
              <div v-if="block.certificate_id">
                <span>Native Reward Recipient</span>
                <strong>{{ shortenKey(block.reward_recipient) }}</strong>
              </div>
              <div v-if="block.certificate_id">
                <span>Native ZOID Reward Amount</span>
                <strong>{{ block.reward_amount ?? 'Missing' }}</strong>
              </div>
              <div v-if="block.certificate_id">
                <span>Approval</span>
                <strong>{{ formatPercent(block.approval_percentage) }}</strong>
              </div>
              <div v-if="block.certificate_id">
                <span>Storage Status</span>
                <strong>{{ formatContentStatus(block.storage_status) }}</strong>
              </div>
            </div>

            <div class="content-state-line">
              <span v-if="block.storage_status" class="status-pill" :class="contentStatusClass(block)">{{ contentStatusLabel(block) }}</span>
              <a v-if="block.download_url" :href="contentUrl(block.download_url)" target="_blank" rel="noreferrer" class="meta-link">
                View Content
              </a>
            </div>

            <div v-if="!hasContentPreview(block) && block.meme && block.meme.encoded_image" class="meme-container">
              <img :src="'data:image/png;base64,' + block.meme.encoded_image" alt="Meme submitted for this block" class="meme-image" />
            </div>
          </article>
        </div>
      </section>
    </main>

    <nav class="navigation-card">
      <router-link to="/blockchain" class="btn secondary">View Blockchain Explorer</router-link>
      <button @click="goToHome" class="btn secondary">Home</button>
    </nav>
  </div>
</template>

<script>
import { apiClient, buildApiUrl, getApiErrorMessage, publicApiClient } from '../config/api';
import WalletPanel from '../components/WalletPanel.vue';
import { useWallet } from '../services/wallet';

export default {
  components: {
    WalletPanel,
  },
  data() {
    const walletManager = useWallet();
    return {
      walletManager,
      memeFile: null,
      textContent: '',
      contentUploadFile: null,
      contentUploadText: '',
      contentCaption: '',
      uploadedContent: null,
      uploadedContentPreviewError: '',
      contentUploadMessage: '',
      contentUploadError: '',
      isContentUploading: false,
      syncingContentHash: '',
      submissionContentHash: '',
      submissionContentId: '',
      submissions: [],
      mintQueue: [],
      recentBlocks: [],
      chainSummary: null,
      certificatesBySubmission: {},
      votesBySubmission: {},
      lastSubmission: null,
      submitMessage: '',
      errorMessage: '',
      voteMessage: '',
      voteError: '',
      evaluateMessage: '',
      evaluateError: '',
      mintMessage: '',
      mintError: '',
      summaryError: '',
      certificateError: '',
      blocksError: '',
      isSubmitting: false,
      isLoading: false,
      isQueueLoading: false,
      isBlocksLoading: false,
      isSummaryLoading: false,
      isRefreshing: false,
      mintingSubmissionId: '',
      showMintQueueTools: import.meta.env.DEV,
    };
  },
  computed: {
    pendingSubmissions() {
      return this.submissions.filter((submission) => submission.status === 'pending');
    },
    approvedCertificateSubmissions() {
      return this.approvedSubmissions.filter((submission) => this.getCertificate(submission));
    },
    approvedMissingCertificateSubmissions() {
      return this.approvedSubmissions.filter(
        (submission) => this.certificateLookupComplete(submission) && !this.getCertificate(submission),
      );
    },
    approvedSubmissions() {
      return this.submissions.filter((submission) => ['approved', 'queued'].includes(submission.status));
    },
    identityWalletAddress() {
      return this.walletManager.state.verifiedWalletAddress || this.walletManager.state.normalizedWalletAddress;
    },
    submissionWalletAddress() {
      return this.walletManager.state.verifiedWalletAddress || '';
    },
    voteWalletAddress() {
      return this.walletManager.state.verifiedWalletAddress || '';
    },
    hasVerifiedWalletIdentity() {
      return this.walletManager.state.isVerifiedSession;
    },
    identityWalletLabel() {
      return this.hasVerifiedWalletIdentity
        ? 'Verified wallet identity'
        : 'Connected MetaMask address';
    },
    shortenIdentityWallet() {
      return this.walletManager.shortenAddress(this.identityWalletAddress);
    },
    canSubmitSignedContent() {
      return this.hasVerifiedWalletIdentity;
    },
    submitButtonLabel() {
      if (this.isSubmitting) {
        return 'Submitting...';
      }
      if (!this.walletManager.state.isConnected) {
        return 'Connect MetaMask To Submit';
      }
      if (!this.hasVerifiedWalletIdentity) {
        return 'Verify Wallet Before Submitting';
      }
      return this.uploadedContent ? 'Sign And Submit Content' : 'Upload Then Sign Submission';
    },
    submissionIdentityHint() {
      if (this.hasVerifiedWalletIdentity) {
        return 'This verified wallet session is now the app identity for submissions. Task 7.4 requires a direct MetaMask signature for each new submission.';
      }
      if (!this.walletManager.state.isConnected) {
        return 'Connect MetaMask to submit new content from a native ZoidbergChain 0x wallet identity.';
      }
      return 'Verify wallet before submitting. New normal submissions now require a verified session plus a direct MetaMask signature.';
    },
    votingIdentityHint() {
      if (this.hasVerifiedWalletIdentity) {
        return 'This verified wallet session is now the app identity for votes. Task 7.5 requires a direct MetaMask signature for each originality vote.';
      }
      if (!this.walletManager.state.isConnected) {
        return 'Connect MetaMask to cast originality votes from a native ZoidbergChain 0x wallet identity.';
      }
      return 'Verify wallet before voting. New normal votes now require a verified session plus a direct MetaMask signature.';
    },
  },
  async created() {
    await this.walletManager.detectMetaMask();
    await this.refreshWorkflow();
  },
  methods: {
    async blockMinting(submission) {
      if (!submission?.submission_id) {
        return;
      }
      try {
        const response = await apiClient.post(`/submissions/${submission.submission_id}/block-minting`, {
          reason: submission.mint_block_reason || 'legacy bad queue item',
          notes: 'Quarantined from the mint queue UI.',
        });
        this.mintMessage = response.data.message || 'Submission minting blocked successfully.';
        await this.fetchMintQueue();
      } catch (error) {
        console.error('Error blocking minting:', error);
        this.mintError = getApiErrorMessage(error, 'Failed to quarantine submission.');
      }
    },
    async unblockMinting(submission) {
      if (!submission?.submission_id) {
        return;
      }
      try {
        const response = await apiClient.post(`/submissions/${submission.submission_id}/unblock-minting`);
        this.mintMessage = response.data.message || 'Submission minting unblocked successfully.';
        await this.fetchMintQueue();
      } catch (error) {
        console.error('Error unblocking minting:', error);
        this.mintError = getApiErrorMessage(error, 'Failed to unblock submission.');
      }
    },
    uploadMeme(event) {
      this.memeFile = event.target.files[0] || null;
    },
    contentUrl(path) {
      return buildApiUrl(path);
    },
    resetUploadedPreviewState(content) {
      this.uploadedContentPreviewError = '';
      if (!content?.download_url) {
        return;
      }
      if (!this.hasContentPreview(content)) {
        this.uploadedContentPreviewError = 'Preview is unavailable for this content.';
      }
    },
    onContentUploadFileChange(event) {
      this.contentUploadFile = event.target.files[0] || null;
    },
    async refreshWorkflow() {
      this.isRefreshing = true;
      try {
        await Promise.all([
          this.fetchChainSummary(),
          this.fetchSubmissions(false),
          this.fetchMintQueue(false),
          this.fetchRecentBlocks(),
        ]);
        await this.loadVisibleCertificates(true);
      } finally {
        this.isRefreshing = false;
      }
    },
    async submitMeme() {
      this.submitMessage = '';
      this.errorMessage = '';
      this.lastSubmission = null;

      if (!this.walletManager.state.isConnected) {
        this.errorMessage = 'Connect MetaMask to submit content.';
        return;
      }

      if (!this.hasVerifiedWalletIdentity || !this.submissionWalletAddress) {
        this.errorMessage = 'Verify wallet before submitting.';
        return;
      }

      this.isSubmitting = true;
      try {
        let preparedContent = this.uploadedContent;
        if (!preparedContent && (this.memeFile || this.textContent)) {
          preparedContent = await this.uploadSubmissionContent();
          this.uploadedContent = preparedContent;
          this.submissionContentHash = preparedContent.content_hash || '';
          this.submissionContentId = preparedContent.content_id || '';
          this.resetUploadedPreviewState(preparedContent);
        }

        const finalContentHash = this.submissionContentHash || preparedContent?.content_hash || '';
        const finalContentId = this.submissionContentId || preparedContent?.content_id || '';

        if (!finalContentHash && !finalContentId) {
          this.errorMessage = 'Please upload content or enter text before submitting.';
          return;
        }

        const challengeResponse = await apiClient.post('/auth/wallet/submission-challenge', {
          wallet_address: this.submissionWalletAddress,
          content_hash: finalContentHash,
          content_id: finalContentId || null,
          caption: this.textContent || preparedContent?.caption || this.contentCaption || null,
        });

        if (typeof window === 'undefined' || !window.ethereum?.request) {
          this.errorMessage = 'MetaMask is unavailable for signing right now.';
          return;
        }

        let signature;
        try {
          signature = await window.ethereum.request({
            method: 'personal_sign',
            params: [challengeResponse.data.message, this.walletManager.state.walletAddress],
          });
        } catch (error) {
          if (error?.code === 4001) {
            this.errorMessage = 'Signature request was rejected in MetaMask.';
            return;
          }
          throw error;
        }

        const formData = new FormData();
        formData.append('wallet_address', this.submissionWalletAddress);
        formData.append('content_hash', finalContentHash);
        if (finalContentId) {
          formData.append('content_id', finalContentId);
        }
        formData.append('message', challengeResponse.data.message);
        formData.append('signature', signature);

        const response = await apiClient.post('/submit_content', formData, {
          headers: { 'Content-Type': 'multipart/form-data' },
        });

        this.lastSubmission = response.data.submission;
        this.submitMessage = `${response.data.message || 'Content submitted successfully.'} Status: ${this.formatStatus(this.lastSubmission.status)}.`;
        this.textContent = '';
        this.memeFile = null;
        this.submissionContentHash = '';
        this.submissionContentId = '';
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
    async uploadContent() {
      this.contentUploadMessage = '';
      this.contentUploadError = '';

      if (!this.walletManager.state.isConnected) {
        this.contentUploadError = 'Connect MetaMask before uploading content.';
        return;
      }

      if (!this.hasVerifiedWalletIdentity || !this.submissionWalletAddress) {
        this.contentUploadError = 'Verify wallet before uploading content.';
        return;
      }

      this.isContentUploading = true;
      try {
        const response = await this.uploadSubmissionContent({
          file: this.contentUploadFile,
          text: this.contentUploadText,
          caption: this.contentCaption,
        });

      this.uploadedContent = response;
      this.submissionContentHash = response.content_hash || '';
      this.submissionContentId = response.content_id || '';
      this.resetUploadedPreviewState(this.uploadedContent);
      this.contentUploadMessage = `Content uploaded successfully. Storage status: ${this.formatContentStatus(response.storage_status)}.`;
      } catch (error) {
        console.error('Error uploading content:', error);
        this.contentUploadError = getApiErrorMessage(error, 'Failed to upload content.');
      } finally {
        this.isContentUploading = false;
      }
    },
    useUploadedContentForSubmission() {
      if (!this.uploadedContent) {
        return;
      }
      this.submissionContentHash = this.uploadedContent.content_hash || '';
      this.submissionContentId = this.uploadedContent.content_id || '';
      this.memeFile = null;
      const fileInput = document.getElementById('meme-upload');
      if (fileInput) {
        fileInput.value = '';
      }
      if (!this.textContent && this.uploadedContent.caption) {
        this.textContent = this.uploadedContent.caption;
      }
      this.submitMessage = 'Uploaded content is ready to submit.';
    },
    clearUploadedContent() {
      this.uploadedContent = null;
      this.contentUploadMessage = '';
      this.contentUploadError = '';
      this.submissionContentHash = '';
      this.submissionContentId = '';
      this.contentUploadFile = null;
      this.contentUploadText = '';
      this.contentCaption = '';
      this.uploadedContentPreviewError = '';
      const fileInput = document.getElementById('content-upload-file');
      if (fileInput) {
        fileInput.value = '';
      }
    },
    async uploadSubmissionContent(options = {}) {
      const file = options.file ?? this.memeFile;
      const text = options.text ?? this.textContent;
      const caption = options.caption ?? this.textContent ?? this.contentCaption;

      if (!this.submissionWalletAddress) {
        throw new Error('Verify wallet before uploading content.');
      }

      if (file) {
        const formData = new FormData();
        formData.append('file', file);
        formData.append('submitted_by', this.submissionWalletAddress);
        if (caption) {
          formData.append('caption', caption);
        }
        const response = await apiClient.post('/content/upload', formData, {
          headers: { 'Content-Type': 'multipart/form-data' },
        });
        return response.data;
      }

      if (text) {
        const response = await apiClient.post('/content/text', {
          text_content: text,
          submitted_by: this.submissionWalletAddress,
          caption: caption || null,
        });
        return response.data;
      }

      throw new Error('Choose a file or enter text before uploading content.');
    },
    async syncContent(contentHash) {
      if (!contentHash) {
        return;
      }

      this.syncingContentHash = contentHash;
      this.contentUploadError = '';
      try {
        await apiClient.post(`/content/${contentHash}/sync`);
        const response = await apiClient.get(`/content/${contentHash}/metadata`);
        const content = response.data.content || null;
        if (content) {
          this.uploadedContent = this.uploadedContent?.content_hash === contentHash ? content : this.uploadedContent;
          this.resetUploadedPreviewState(content);
        }
        this.contentUploadMessage = 'Content synced successfully.';
        await this.refreshWorkflow();
      } catch (error) {
        console.error('Error syncing content:', error);
        this.contentUploadError = getApiErrorMessage(error, 'Failed to sync content.');
      } finally {
        this.syncingContentHash = '';
      }
    },
    async fetchChainSummary() {
      this.isSummaryLoading = true;
      this.summaryError = '';
      try {
        const response = await apiClient.get('/chain/summary');
        this.chainSummary = response.data;
      } catch (error) {
        console.error('Error fetching chain summary:', error);
        this.summaryError = getApiErrorMessage(error, 'Failed to load chain summary.');
      } finally {
        this.isSummaryLoading = false;
      }
    },
    async fetchSubmissions(loadCertificates = true) {
      this.isLoading = true;
      this.voteError = '';
      try {
        const response = await apiClient.get('/submissions');
        this.submissions = response.data.submissions || [];
        await this.loadVisibleVotes();
        if (loadCertificates) {
          await this.loadVisibleCertificates(true);
        }
      } catch (error) {
        console.error('Error fetching submissions:', error);
        this.voteError = getApiErrorMessage(error, 'Failed to load submissions.');
      } finally {
        this.isLoading = false;
      }
    },
    async fetchMintQueue(loadCertificates = true) {
      this.isQueueLoading = true;
      this.mintError = '';
      try {
        const response = await apiClient.get('/mint-queue', {
          params: { include_blocked: true },
        });
        this.mintQueue = response.data.mint_queue || [];
        if (loadCertificates) {
          await this.loadVisibleCertificates(true);
        }
      } catch (error) {
        console.error('Error fetching mint queue:', error);
        this.mintError = getApiErrorMessage(error, 'Failed to load mint queue.');
      } finally {
        this.isQueueLoading = false;
      }
    },
    async fetchRecentBlocks() {
      this.isBlocksLoading = true;
      this.blocksError = '';
      try {
        const response = await apiClient.get('/chain');
        this.recentBlocks = [...(response.data.chain || [])].reverse().slice(0, 6);
      } catch (error) {
        console.error('Error fetching recent blocks:', error);
        this.blocksError = getApiErrorMessage(error, 'Failed to load recent blocks.');
      } finally {
        this.isBlocksLoading = false;
      }
    },
    async fetchCertificateForSubmission(submissionId) {
      try {
        const response = await apiClient.get(`/submissions/${submissionId}/certificate`);
        return response.data.certificate || null;
      } catch (error) {
        if (error?.response?.status === 404) {
          return null;
        }
        this.certificateError = getApiErrorMessage(error, 'Failed to load originality certificate.');
        return null;
      }
    },
    async fetchVotesForSubmission(submissionId) {
      try {
        const response = await apiClient.get(`/submissions/${submissionId}/votes`);
        return response.data?.votes || [];
      } catch (error) {
        if (error?.response?.status === 404) {
          return [];
        }
        throw error;
      }
    },
    async loadVisibleVotes() {
      const pendingIds = this.pendingSubmissions.map((submission) => submission.submission_id);
      const nextVotesBySubmission = {};

      await Promise.all(pendingIds.map(async (submissionId) => {
        nextVotesBySubmission[submissionId] = await this.fetchVotesForSubmission(submissionId);
      }));

      this.votesBySubmission = nextVotesBySubmission;
    },
    async loadVisibleCertificates(force = false) {
      this.certificateError = '';
      const ids = new Set();

      this.approvedSubmissions.forEach((submission) => ids.add(submission.submission_id));
      this.mintQueue.forEach((submission) => ids.add(submission.submission_id));

      await Promise.all([...ids].map(async (submissionId) => {
        if (!force && Object.prototype.hasOwnProperty.call(this.certificatesBySubmission, submissionId)) {
          return;
        }
        const certificate = await this.fetchCertificateForSubmission(submissionId);
        this.certificatesBySubmission = {
          ...this.certificatesBySubmission,
          [submissionId]: certificate,
        };
      }));
    },
    getCertificate(submission) {
      if (!submission?.submission_id) {
        return null;
      }
      return this.certificatesBySubmission[submission.submission_id] || null;
    },
    currentWalletVoteForSubmission(submission) {
      if (!submission?.submission_id || !this.voteWalletAddress) {
        return null;
      }
      const votes = this.votesBySubmission[submission.submission_id] || [];
      return votes.find((vote) => vote.voter === this.voteWalletAddress) || null;
    },
    voteDisabled(submission) {
      if (!this.walletManager.state.isConnected || !this.hasVerifiedWalletIdentity || !this.voteWalletAddress) {
        return true;
      }
      if (submission?.submitter === this.voteWalletAddress) {
        return true;
      }
      return Boolean(this.currentWalletVoteForSubmission(submission));
    },
    certificateLookupComplete(submission) {
      return Boolean(
        submission?.submission_id
        && Object.prototype.hasOwnProperty.call(this.certificatesBySubmission, submission.submission_id),
      );
    },
    hasContentPreview(record) {
      return Boolean(record?.download_url || this.isTextContent(record) || this.isImageContent(record));
    },
    isImageContent(record) {
      const value = String(record?.mime_type || record?.content_type || '').toLowerCase();
      return value.startsWith('image/');
    },
    isTextContent(record) {
      const mimeType = String(record?.mime_type || '').toLowerCase();
      const contentType = String(record?.content_type || '').toLowerCase();
      return mimeType === 'text/plain' || contentType === 'text' || contentType === 'mixed';
    },
    needsContentSync(record) {
      const status = String(record?.storage_status || '').toLowerCase();
      return Boolean(record?.content_hash) && ['remote', 'missing', 'local'].includes(status) && !record?.download_url;
    },
    contentStatusLabel(record) {
      if (record?.content_metadata_missing) {
        return 'Content Metadata Missing';
      }
      const status = String(record?.storage_status || '').toLowerCase();
      if (!status) {
        return 'Content Unknown';
      }
      if (status === 'verified') {
        return 'Verified Locally';
      }
      if (status === 'local') {
        return 'Not Verified Locally';
      }
      if (status === 'remote') {
        return 'Remote Content';
      }
      if (status === 'missing') {
        return 'Missing Content';
      }
      return this.formatContentStatus(status);
    },
    contentStatusClass(record) {
      if (record?.content_metadata_missing) {
        return 'warning-chip';
      }
      const status = String(record?.storage_status || '').toLowerCase();
      if (status === 'verified') {
        return 'ready';
      }
      if (status === 'local') {
        return 'pending';
      }
      if (status === 'remote' || status === 'missing') {
        return 'warning-chip';
      }
      return '';
    },
    formatContentField(value, metadataMissing = false) {
      if (metadataMissing) {
        return 'Content metadata missing';
      }
      if (value === null || value === undefined || value === '') {
        return 'Missing';
      }
      return value;
    },
    formatCertificateStatus(status) {
      if (!status) {
        return 'Certificate missing';
      }
      return String(status).replace(/_/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());
    },
    formatMintReason(reason) {
      const normalized = String(reason || '').toLowerCase();
      const labels = {
        submission_not_found: 'Submission not found.',
        submission_not_approved: 'Submission is not approved for minting.',
        certificate_missing: 'Certificate missing.',
        certificate_content_hash_mismatch: 'Certificate content hash mismatch.',
        content_metadata_missing: 'Content metadata missing.',
        content_payload_missing: 'Cannot mint: content payload is not verified on this node. Upload or sync the content first.',
        content_not_verified: 'Cannot mint: content payload is not verified on this node. Upload or sync the content first.',
        content_hash_mismatch: 'Content hash mismatch.',
        no_text_content_extracted: 'Cannot mint: no text content could be extracted from the image. Add text before submission or quarantine this item.',
        already_minted: 'Submission has already been minted.',
        mint_blocked_manually: 'Minting is manually blocked.',
        legacy_unverifiable_content: 'Legacy content cannot be verified locally.',
        unknown_error: 'Minting is blocked for an unknown reason.',
      };
      return labels[normalized] || String(reason || 'Minting is blocked.');
    },
    formatContentStatus(status) {
      if (!status) {
        return 'Missing';
      }
      return String(status).replace(/_/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());
    },
    mintDisabledReason(submission, index) {
      if (!submission) {
        return 'Cannot mint: queue item is missing.';
      }
      if (!submission.mintable) {
        return this.formatMintReason(submission.mint_block_reason || 'unknown_error');
      }
      return '';
    },
    async vote(submissionId, voteType) {
      this.voteMessage = '';
      this.voteError = '';

      if (!this.walletManager.state.isConnected) {
        this.voteError = 'Connect MetaMask to vote.';
        return;
      }
      if (!this.hasVerifiedWalletIdentity || !this.voteWalletAddress) {
        this.voteError = 'Verify wallet before voting.';
        return;
      }

      const submission = this.submissions.find((item) => item.submission_id === submissionId);
      if (!submission) {
        this.voteError = 'Submission not found for voting.';
        return;
      }
      if (submission.submitter === this.voteWalletAddress) {
        this.voteError = 'Submission creator cannot vote on their own submission.';
        return;
      }
      if (this.currentWalletVoteForSubmission(submission)) {
        this.voteError = 'This wallet has already voted on that submission.';
        return;
      }

      try {
        const challengeResponse = await apiClient.post('/auth/wallet/vote-challenge', {
          wallet_address: this.voteWalletAddress,
          submission_id: submissionId,
          vote: voteType,
        });

        if (typeof window === 'undefined' || !window.ethereum?.request) {
          this.voteError = 'MetaMask is unavailable for signing right now.';
          return;
        }

        let signature;
        try {
          signature = await window.ethereum.request({
            method: 'personal_sign',
            params: [challengeResponse.data.message, this.walletManager.state.walletAddress],
          });
        } catch (error) {
          if (error?.code === 4001) {
            this.voteError = 'Signature request was rejected in MetaMask.';
            return;
          }
          throw error;
        }

        const formData = new FormData();
        formData.append('wallet_address', this.voteWalletAddress);
        formData.append('vote_type', voteType);
        formData.append('message', challengeResponse.data.message);
        formData.append('signature', signature);

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
        if (response.data.certificate) {
          this.certificatesBySubmission = {
            ...this.certificatesBySubmission,
            [submissionId]: response.data.certificate,
          };
        }
        const status = response.data.submission?.status;
        const certificateId = response.data.certificate?.certificate_id;
        this.evaluateMessage = `${response.data.message || 'Submission evaluated successfully.'} Status: ${this.formatStatus(status)}${certificateId ? `, certificate ${this.shortenHash(certificateId)}.` : '.'}`;
        await this.refreshWorkflow();
      } catch (error) {
        console.error('Error evaluating submission:', error);
        this.evaluateError = getApiErrorMessage(error, 'Failed to evaluate submission.');
      }
    },
    async mintSubmission(submissionId) {
      this.mintMessage = '';
      this.mintError = '';

      const submission = this.mintQueue.find((item) => item.submission_id === submissionId);
      if (!submission?.mintable) {
        this.mintError = this.formatMintReason(submission?.mint_block_reason || 'unknown_error');
        return;
      }

      this.mintingSubmissionId = submissionId;
      try {
        const response = await apiClient.post(`/mint/${submissionId}`);
        const certificateId = response.data.block?.certificate_id;
        const rewardRecipient = response.data.reward_recipient || response.data.block?.reward_recipient;
        const rewardAmount = response.data.reward_amount ?? response.data.block?.reward_amount;
        this.mintMessage = `${response.data.message || 'Submission minted successfully.'} Block #${response.data.block?.index ?? 'created'}${certificateId ? ` with certificate ${this.shortenHash(certificateId)}` : ''}${rewardRecipient ? `, reward recipient ${this.shortenKey(rewardRecipient)}` : ''}${rewardAmount !== null && rewardAmount !== undefined ? `, reward ${rewardAmount} ZOID.` : '.'}`;
        if (typeof window !== 'undefined') {
          window.dispatchEvent(new Event('zoidberg-wallet-balance-refresh'));
        }
        await this.refreshWorkflow();
      } catch (error) {
        console.error('Error minting submission:', error);
        this.mintError = getApiErrorMessage(error, 'Failed to mint submission.');
      } finally {
        this.mintingSubmissionId = '';
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
        return '';
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
  background: linear-gradient(150deg, #090909 0%, #181818 48%, #080808 100%);
  color: #fff;
  font-family: Arial, sans-serif;
}

.dashboard-header,
.dashboard-shell,
.navigation-card {
  width: min(1220px, 100%);
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
  font-size: 1.08rem;
}

.subtitle {
  margin-bottom: 0;
  color: #c6c6c6;
  font-size: 1.05rem;
}

.section-note {
  margin-bottom: 18px;
  color: #b6bbc4;
  font-size: 0.94rem;
  line-height: 1.5;
}

.dashboard-shell {
  display: grid;
  grid-template-columns: minmax(320px, 0.9fr) minmax(420px, 1.1fr);
  grid-template-areas:
    "summary summary"
    "content content"
    "submit voting"
    "approved voting"
    "missing voting"
    "queue blocks";
  gap: 22px;
  align-items: start;
}

.summary-panel {
  grid-area: summary;
}

.content-panel {
  grid-area: content;
}

.submit-panel {
  grid-area: submit;
}

.voting-panel {
  grid-area: voting;
}

.approved-panel {
  grid-area: approved;
}

.missing-panel {
  grid-area: missing;
}

.queue-panel {
  grid-area: queue;
}

.blocks-panel {
  grid-area: blocks;
}

.section-panel,
.navigation-card {
  background: rgba(28, 28, 28, 0.94);
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 8px;
  box-shadow: 0 12px 28px rgba(0, 0, 0, 0.35);
}

.section-panel {
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

.warning-chip {
  background: rgba(255, 201, 71, 0.14);
  color: #ffd884;
}

.status-pill.queued,
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
.content-preview-card,
.submission-result,
.submission-card,
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

.form-stack,
.message-stack,
.submission-list,
.queue-list,
.block-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.field-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.derived-wallet-panel {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-height: 46px;
  padding: 12px;
  border: 1px solid rgba(255, 71, 71, 0.4);
  border-radius: 8px;
  background: rgba(0, 0, 0, 0.22);
  color: #fff;
  overflow-wrap: anywhere;
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

.success,
.text-success {
  color: #8df5a6;
}

.success {
  background: rgba(141, 245, 166, 0.12);
}

.error {
  background: rgba(255, 140, 140, 0.12);
  color: #ff8c8c;
}

.text-warning,
.queue-warning {
  color: #ffd884;
}

.submission-result {
  margin-top: 18px;
  padding: 14px;
}

.submission-card,
.block-card {
  padding: 16px;
}

.content-preview-card {
  margin-top: 18px;
  padding: 16px;
}

.empty-state {
  padding: 18px;
  color: #bbb;
}

.submission-header,
.block-heading {
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

.content-preview pre,
.content-text-preview pre {
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

.meta-chip {
  padding: 5px 8px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.08);
  color: #d9dde3;
  font-size: 0.8rem;
}

.meta-link {
  color: #8eb9ff;
  font-size: 0.88rem;
  font-weight: 700;
}

.sync-btn {
  min-height: 34px;
  padding-block: 7px;
}

.hint,
.meta,
.queue-warning {
  margin-bottom: 0;
  font-size: 0.9rem;
  line-height: 1.4;
}

.hint,
.meta {
  color: #b8b8b8;
}

.queue-warning {
  margin-top: 12px;
}

.wallet-helper-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.helper-btn {
  min-height: 34px;
  padding: 7px 12px;
}

.wallet-flow-hint {
  margin-top: 14px;
}

.detail-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin-top: 14px;
}

.navigation-card {
  display: flex;
  justify-content: center;
  gap: 12px;
  margin-top: 22px;
  padding: 16px;
}

@media (max-width: 1060px) {
  .dashboard-header {
    align-items: flex-start;
    flex-direction: column;
  }

  .dashboard-shell {
    grid-template-columns: minmax(0, 1fr);
    grid-template-areas:
      "summary"
      "content"
      "submit"
      "voting"
      "approved"
      "missing"
      "queue"
      "blocks";
  }

  .metric-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 620px) {
  .dashboard-page {
    padding: 28px 14px 40px;
  }

  h1 {
    font-size: 2.3rem;
  }

  .section-panel,
  .navigation-card {
    padding: 16px;
  }

  .card-heading,
  .submission-header,
  .block-heading,
  .submission-actions,
  .navigation-card {
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
