<template>
  <div class="dashboard-page">
    <PublicDemoBanner v-if="showPublicDemoBanner" />
    <header class="dashboard-header">
      <div>
        <p class="eyebrow">{{ pageEyebrow }}</p>
        <h1>{{ pageTitle }}</h1>
        <p class="subtitle">{{ pageSubtitle }}</p>
      </div>
      <div class="header-actions">
        <button v-if="showRefreshButton" @click="refreshWorkflow" class="btn secondary" :disabled="isRefreshing">
          {{ isRefreshing ? 'Refreshing...' : 'Refresh' }}
        </button>
        <button type="button" class="btn primary feedback-link" @click="openFeedbackPanel">Send Feedback</button>
        <router-link to="/help" class="btn ghost">Help</router-link>
      </div>
    </header>

    <nav class="navigation-card app-nav" aria-label="Beta app navigation">
      <router-link
        v-for="item in navigationItems"
        :key="item.to"
        :to="item.to"
        class="btn ghost nav-link"
        :class="{ active: item.section === appSection }"
      >
        {{ item.label }}
      </router-link>
    </nav>

    <section v-if="isHomePage" class="home-overview">
      <div class="home-grid">
        <article class="section-panel home-card">
          <p class="section-label">Access And Wallet</p>
          <h2>{{ accessSummaryHeadline }}</h2>
          <p class="hint">{{ accessSummaryDetail }}</p>
          <div class="detail-grid compact-detail-grid">
            <div>
              <span>Wallet</span>
              <strong>{{ walletSummaryHeadline }}</strong>
            </div>
            <div>
              <span>App Access</span>
              <strong>{{ accessUnlockLabel }}</strong>
            </div>
          </div>
        </article>

        <article class="section-panel home-card">
          <p class="section-label">What To Do Next</p>
          <h2>{{ nextActionTitle }}</h2>
          <p class="hint">{{ nextActionDetail }}</p>
          <router-link :to="nextActionRoute" class="btn primary">
            {{ nextActionLabel }}
          </router-link>
        </article>
      </div>

      <section class="navigation-card quickstart-card home-action-grid">
        <article v-for="card in homeActionCards" :key="card.to" class="quickstart-item home-action-card">
          <p class="section-label">{{ card.kicker }}</p>
          <strong>{{ card.title }}</strong>
          <p class="hint">{{ card.copy }}</p>
          <router-link :to="card.to" class="btn ghost">Open</router-link>
        </article>
      </section>

      <section class="navigation-card helper-strip">
        <p class="hint">
          Need the walkthrough again? Open the Beta Guide for access, MetaMask, submission, voting, rewards, mobile tips, and safety reminders.
        </p>
      </section>

      <section class="navigation-card helper-strip">
        <p class="hint">
          Controlled beta only. Test ZOID has no real monetary value, balances can reset, and admin tools remain separate at /admin.
        </p>
      </section>
    </section>

    <section v-if="isRewardsPage" class="navigation-card helper-strip rewards-intro-card">
      <p class="hint">
        Rewards, balances, and transfers live here. Test ZOID has no real monetary value, and your verified wallet remains the only way to sign balance-affecting actions in beta.
      </p>
    </section>

    <WalletPanel v-if="isRewardsPage" />

    <main v-if="mainSectionVisible" class="dashboard-shell">
      <section v-if="isActivityPage" class="section-panel summary-panel">
        <div class="card-heading">
          <div>
            <p class="section-label">Beta Overview</p>
            <h2>What Is Happening Right Now</h2>
          </div>
          <span class="workflow-chip">Live Beta Status</span>
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
            <span>Waiting For Votes</span>
            <strong>{{ pendingSubmissions.length }}</strong>
          </div>
          <div class="metric-card">
            <span>Certified Memes</span>
            <strong>{{ approvedCertificateSubmissions.length }}</strong>
          </div>
        </div>

        <div v-else-if="!summaryError" class="empty-state">
          Loading the current beta activity summary...
        </div>
      </section>

      <section v-if="isSubmitPage" class="section-panel content-panel">
        <div class="card-heading">
          <div>
            <p class="section-label">Step 1</p>
            <h2>Prepare Your Content</h2>
          </div>
          <span class="workflow-chip">Upload First</span>
        </div>

        <p class="section-note">
          Upload an image or text post first. The app can carry it into the submission step for you.
        </p>

        <div class="form-stack">
          <div class="field-group">
            <label for="content-upload-file">Image Or File</label>
            <input
              id="content-upload-file"
              type="file"
              accept=".jpg,.jpeg,.png,.webp,.gif,.txt"
              @change="onContentUploadFileChange"
              class="file-input"
            >
          </div>

          <div class="field-group">
            <label for="content-upload-text">Text Version</label>
            <textarea
              id="content-upload-text"
              v-model.trim="contentUploadText"
              placeholder="Optional text-only post"
              class="input-field text-area"
            ></textarea>
          </div>

          <div class="field-group">
            <label for="content-caption">Caption Or Alt Text</label>
            <input
              id="content-caption"
              type="text"
              v-model.trim="contentCaption"
              placeholder="Optional description"
              class="input-field"
            >
          </div>
        </div>

        <div class="card-actions">
          <button @click="uploadContent" class="btn primary" :disabled="isContentUploading">
            {{ isContentUploading ? 'Uploading...' : 'Upload Content' }}
          </button>
          <button v-if="uploadedContent" @click="useUploadedContentForSubmission" class="btn secondary">
            Use In Submission
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
            <a :href="contentUrl(uploadedContent.download_url)" target="_blank" rel="noreferrer">Open uploaded content</a>
          </p>
        </div>
      </section>

      <section v-if="isSubmitPage" class="section-panel submit-panel">
        <div class="card-heading">
          <div>
            <p class="section-label">Step 2</p>
            <h2>Submit Your Meme</h2>
          </div>
          <span class="workflow-chip">Needs Verified Wallet</span>
        </div>

        <div class="form-stack">
          <div class="field-group">
            <label>Submitting Wallet</label>
            <div class="derived-wallet-panel">
              <strong v-if="submissionWalletAddress">{{ submissionWalletAddress }}</strong>
              <strong v-else>Connect and verify MetaMask before you submit.</strong>
              <span class="meta">Your verified wallet is used as your submission identity in the beta.</span>
            </div>
          </div>

          <div class="field-group">
            <label for="content-text">Title Or Caption</label>
            <textarea id="content-text" v-model.trim="textContent" placeholder="Add the meme text or a short caption" class="input-field text-area"></textarea>
          </div>

          <div class="field-group">
            <label for="meme-upload">Optional Image</label>
            <input type="file" id="meme-upload" accept=".jpg,.jpeg,.png,.webp" @change="uploadMeme" class="file-input">
          </div>

          <button type="button" class="btn ghost helper-btn" @click="showSubmissionAdvancedFields = !showSubmissionAdvancedFields">
            {{ showSubmissionAdvancedFields ? 'Hide Advanced Content References' : 'Show Advanced Content References' }}
          </button>

          <div v-if="showSubmissionAdvancedFields || submissionContentHash || submissionContentId" class="field-group">
            <label for="submission-content-hash">Content Hash</label>
            <input id="submission-content-hash" type="text" v-model.trim="submissionContentHash" placeholder="Optional advanced reference from the upload step" class="input-field">
          </div>

          <div v-if="showSubmissionAdvancedFields || submissionContentHash || submissionContentId" class="field-group">
            <label for="submission-content-id">Content ID</label>
            <input id="submission-content-id" type="text" v-model.trim="submissionContentId" placeholder="Optional advanced reference from the upload step" class="input-field">
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

        <div v-if="submissionEligibilityView.headline || submissionEligibilityView.detail || submissionEligibilityView.policyNote" class="review-policy-panel submission-status-panel">
          <p class="section-label">Submission Eligibility</p>
          <p v-if="submissionEligibilityView.headline" class="status-message" :class="submissionEligibilityToneClass">{{ submissionEligibilityView.headline }}</p>
          <p v-if="submissionEligibilityView.detail" class="hint">{{ submissionEligibilityView.detail }}</p>
          <p v-if="submissionEligibilityView.policyNote" class="hint">{{ submissionEligibilityView.policyNote }}</p>
          <div v-if="submissionRuleChecks.length" class="eligibility-checklist">
            <div
              v-for="rule in submissionRuleChecks"
              :key="`${rule.scope}-${rule.rule_id}`"
              class="eligibility-rule"
              :class="{ pass: rule.passed, fail: rule.required && !rule.passed }"
            >
              <strong>{{ rule.label }}</strong>
              <p class="hint">{{ rule.description }}</p>
              <p class="hint eligibility-rule-value">
                Current: {{ rule.current_value ?? 'Not available' }}
                <span v-if="rule.required_value !== null && rule.required_value !== undefined"> | Needed: {{ rule.required_value }}</span>
              </p>
            </div>
          </div>
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
          <p><strong>Tracking ID:</strong> {{ shortenHash(lastSubmission.submission_id) }}</p>
          <div class="detail-grid">
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
            <a :href="contentUrl(lastSubmission.download_url)" target="_blank" rel="noreferrer">Open submitted content</a>
          </p>
          <p class="hint">Your submission is now waiting for community voting before it can become certified.</p>
        </div>
      </section>

      <section v-if="isSubmitPage" class="section-panel recent-submissions-panel">
        <div class="card-heading">
          <div>
            <p class="section-label">Recent Submissions</p>
            <h2>Your Recent Submission Activity</h2>
          </div>
        </div>

        <div v-if="userRecentSubmissions.length === 0" class="empty-state">
          Submit your first meme to start testing originality review.
        </div>

        <div v-else class="submission-list">
          <article v-for="submission in userRecentSubmissions" :key="submission.submission_id" class="submission-card">
            <div class="submission-header">
              <span class="status-pill" :class="submission.status === 'approved' ? 'ready' : submission.status === 'rejected' ? 'pending' : ''">
                {{ formatStatus(submission.status) }}
              </span>
              <span>{{ formatDate(submission.created_at) }}</span>
            </div>
            <div v-if="hasContentPreview(submission)" class="content-preview">
              <img v-if="isImageContent(submission) && submission.download_url" :src="contentUrl(submission.download_url)" alt="Recent submission preview" class="content-image">
              <pre v-else-if="isTextContent(submission)">{{ submission.text_content }}</pre>
            </div>
            <p class="submission-text">{{ submission.text_content || 'Uploaded submission content' }}</p>
            <div class="detail-grid">
              <div>
                <span>Tracking ID</span>
                <strong>{{ shortenHash(submission.submission_id) }}</strong>
              </div>
              <div>
                <span>Storage Status</span>
                <strong>{{ formatContentStatus(submission.storage_status) }}</strong>
              </div>
            </div>
          </article>
        </div>
      </section>

      <section v-if="isVotePage" class="section-panel voting-panel">
        <div class="card-heading">
          <div>
            <p class="section-label">Step 3</p>
            <h2>Vote On Originality</h2>
          </div>
          <button @click="fetchSubmissions" class="btn ghost" :disabled="isLoading">
            {{ isLoading ? 'Refreshing...' : 'Refresh' }}
          </button>
        </div>

        <div class="voter-wallet">
          <div class="field-group">
            <label>Voting Wallet</label>
            <div class="derived-wallet-panel">
              <strong v-if="voteWalletAddress">{{ voteWalletAddress }}</strong>
              <strong v-else>Connect and verify MetaMask before you vote.</strong>
              <span class="meta">Your verified wallet is used as your voting identity in the beta.</span>
            </div>
          </div>
        </div>

        <p class="hint wallet-flow-hint">
          {{ votingIdentityHint }}
        </p>

        <div class="review-policy-panel">
          <p class="section-label">Can You Vote Yet?</p>
          <strong>{{ reviewPolicySummary }}</strong>
          <p class="hint">{{ reviewPolicyWarning }}</p>
          <p v-if="reviewerEligibilityMessage" class="status-message error">{{ reviewerEligibilityMessage }}</p>
          <p v-if="reviewEligibilityBlockedReason" class="status-message error">{{ reviewEligibilityBlockedReason }}</p>
          <p v-if="reviewEligibilityOverrideMessage" class="status-message success">{{ reviewEligibilityOverrideMessage }}</p>
          <div v-if="reviewEligibilityRuleChecks.length" class="eligibility-checklist">
            <div
              v-for="rule in reviewEligibilityRuleChecks"
              :key="`${rule.scope}-${rule.rule_id}`"
              class="eligibility-rule"
              :class="{ pass: rule.passed, fail: rule.required && !rule.passed }"
            >
              <strong>{{ rule.label }}</strong>
              <p class="hint">{{ rule.description }}</p>
              <p class="hint eligibility-rule-value">
                Current: {{ rule.current_value ?? 'Not available' }}
                <span v-if="rule.required_value !== null && rule.required_value !== undefined"> | Needed: {{ rule.required_value }}</span>
              </p>
            </div>
          </div>
          <p v-for="step in reviewEligibilityNextSteps" :key="step" class="hint">{{ step }}</p>
          <div v-if="canRequestReviewOverride" class="card-actions">
            <button @click="showReviewOverrideForm = !showReviewOverrideForm" class="btn ghost">
              {{ showReviewOverrideForm ? 'Hide Override Form' : 'Request an Override' }}
            </button>
          </div>
          <div v-if="showReviewOverrideForm" class="inline-override-panel">
            <label class="field-group">
              <span>Requested Scope</span>
              <select v-model="reviewOverrideScope" class="input-field">
                <option value="review">Review Eligibility Allowlist</option>
                <option value="voting">Voting Override</option>
                <option value="rewards">Rewards Override</option>
                <option value="all_beta">All Beta Permissions</option>
              </select>
            </label>
            <label class="field-group">
              <span>Reason</span>
              <textarea v-model.trim="reviewOverrideReason" class="input-field text-area" rows="3" placeholder="Explain what is blocked and what you need."></textarea>
            </label>
            <button @click="submitReviewOverride" class="btn primary" :disabled="accessService.state.isSubmittingOverrideRequest || !reviewOverrideReason">
              {{ accessService.state.isSubmittingOverrideRequest ? 'Submitting Override...' : 'Submit Override Request' }}
            </button>
          </div>
          <p v-if="reviewPolicyError" class="status-message error">{{ reviewPolicyError }}</p>
        </div>

        <div class="reward-policy-panel">
          <p class="section-label">Voter Rewards</p>
          <strong>Final majority-side voters can receive testnet ZOID.</strong>
          <p v-for="line in voterRewardPolicyLines" :key="line" class="hint">{{ line }}</p>
        </div>

        <div v-if="voteMessage || voteError || evaluateMessage || evaluateError" class="message-grid">
          <p v-if="voteMessage" class="status-message success">{{ voteMessage }}</p>
          <p v-if="voteError" class="status-message error">{{ voteError }}</p>
          <p v-if="evaluateMessage" class="status-message success">{{ evaluateMessage }}</p>
          <p v-if="evaluateError" class="status-message error">{{ evaluateError }}</p>
        </div>

        <div v-if="pendingSubmissions.length === 0" class="empty-state">
          Nothing needs your vote right now. Check back soon or submit something new for the community to review.
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
              <div class="reward-summary-panel">
                <p class="section-label">Voter Reward</p>
                <strong>{{ describeSubmissionReward(submission) }}</strong>
              </div>
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
              <button v-if="showMintQueueTools" @click="evaluateSubmission(submission.submission_id)" class="btn evaluate">
                Evaluate
              </button>
            </div>
          </article>
        </div>
      </section>

      <section v-if="isActivityPage" class="section-panel approved-panel">
        <div class="card-heading">
          <div>
            <p class="section-label">Certified Results</p>
            <h2>Certified Memes</h2>
          </div>
          <span class="workflow-chip">Community Approved</span>
        </div>

        <p v-if="certificateError" class="status-message error">{{ certificateError }}</p>

        <div v-if="approvedCertificateSubmissions.length === 0" class="empty-state">
          No certified memes yet. Once a submission passes voting, it will show up here.
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
            <div class="reward-summary-panel">
              <p class="section-label">Voter Reward</p>
              <strong>{{ describeSubmissionReward(submission) }}</strong>
            </div>
          </article>
        </div>
      </section>

      <section v-if="isActivityPage && rejectedSubmissions.length > 0" class="section-panel resolved-panel">
        <div class="card-heading">
          <div>
            <p class="section-label">Rejected Decisions</p>
            <h2>Not Original Outcomes</h2>
          </div>
          <span class="workflow-chip warning-chip">Finalized</span>
        </div>

        <div class="submission-list">
          <article v-for="submission in rejectedSubmissions" :key="submission.submission_id" class="submission-card">
            <div class="submission-header">
              <span class="status-pill pending">{{ formatStatus(submission.status) }}</span>
              <span>{{ formatDate(submission.created_at) }}</span>
            </div>
            <div v-if="hasContentPreview(submission)" class="content-preview">
              <img v-if="isImageContent(submission) && submission.download_url" :src="contentUrl(submission.download_url)" alt="Rejected submission preview" class="content-image">
              <pre v-else-if="isTextContent(submission)">{{ submission.text_content }}</pre>
            </div>
            <p class="submission-text">{{ submission.text_content }}</p>
            <div class="detail-grid">
              <div>
                <span>Submission ID</span>
                <strong>{{ shortenHash(submission.submission_id) }}</strong>
              </div>
              <div>
                <span>Decision</span>
                <strong>{{ formatStatus(submission.decision_reason || 'rejected') }}</strong>
              </div>
              <div>
                <span>Content Hash</span>
                <strong>{{ shortenHash(submission.content_hash) }}</strong>
              </div>
              <div>
                <span>Creator Account</span>
                <strong>{{ shortenKey(submission.creator_wallet_address || submission.submitter) }}</strong>
              </div>
            </div>
            <div class="reward-summary-panel">
              <p class="section-label">Voter Reward</p>
              <strong>{{ describeSubmissionReward(submission) }}</strong>
            </div>
          </article>
        </div>
      </section>

      <section v-if="isActivityPage && showMintQueueTools && approvedMissingCertificateSubmissions.length > 0" class="section-panel missing-panel">
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

      <section v-if="isActivityPage && showMintQueueTools" class="section-panel queue-panel">
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

            <div class="reward-summary-panel">
              <p class="section-label">Voter Reward</p>
              <strong>{{ describeSubmissionReward(submission) }}</strong>
            </div>

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

      <section v-if="isActivityPage" class="section-panel blocks-panel">
        <div class="card-heading">
          <div>
            <p class="section-label">Recent Activity</p>
            <h2>Certified Meme Blocks</h2>
          </div>
          <button @click="fetchRecentBlocks" class="btn ghost" :disabled="isBlocksLoading">
            {{ isBlocksLoading ? 'Refreshing...' : 'Refresh Blocks' }}
          </button>
        </div>

        <p v-if="blocksError" class="status-message error">{{ blocksError }}</p>

        <div v-if="recentBlocks.length === 0" class="empty-state">
          No certified blocks to show yet. Once submissions clear voting and mint, they will appear here.
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
              <div v-if="Array.isArray(block.voter_rewards) && block.voter_rewards.length">
                <span>Voter Reward Settlements</span>
                <strong>{{ block.voter_rewards.length }}</strong>
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
            <p v-if="Array.isArray(block.voter_rewards) && block.voter_rewards.length" class="hint">
              {{ describeBlockVoterRewards(block) }}
            </p>

            <div v-if="!hasContentPreview(block) && block.meme && block.meme.encoded_image" class="meme-container">
              <img :src="'data:image/png;base64,' + block.meme.encoded_image" alt="Meme submitted for this block" class="meme-image" />
            </div>
          </article>
        </div>
      </section>

      <section v-if="isHelpPage" class="section-panel help-panel">
        <div class="card-heading">
          <div>
            <p class="section-label">Beta Guide</p>
            <h2>Use this guide if you get stuck.</h2>
          </div>
          <router-link to="/why-zoidbergcoin" class="btn ghost">Open Full Guide Page</router-link>
        </div>

        <div class="page-help-grid">
          <article class="quickstart-item">
            <p class="section-label">MetaMask</p>
            <strong>Connect the same approved wallet each time.</strong>
            <p class="hint">Use MetaMask on desktop or the MetaMask Mobile browser on phones before trying to submit, vote, or send test ZOID.</p>
          </article>
          <article class="quickstart-item">
            <p class="section-label">How Beta Works</p>
            <strong>Invites unlock access, wallets prove identity.</strong>
            <p class="hint">Invite codes are one-time, but returning approved wallets can reconnect and sign again without reusing the invite.</p>
          </article>
          <article class="quickstart-item">
            <p class="section-label">Safety</p>
            <strong>Never share secrets in this app.</strong>
            <p class="hint">Do not enter seed phrases, private keys, passwords, or invite codes into feedback or any free-text field.</p>
          </article>
          <article class="quickstart-item">
            <p class="section-label">Feedback</p>
            <strong>Send a note whenever something feels off.</strong>
            <p class="hint">Feedback stays available from Home, this Help page, and the blocked access flow so testers can always report issues.</p>
          </article>
        </div>
      </section>

      <section v-if="isFeedbackPage" class="section-panel feedback-cta-card">
        <div class="card-heading">
          <div>
            <p class="section-label">Feedback</p>
            <h2>Tell us what is broken, confusing, or missing.</h2>
          </div>
        </div>
        <p class="hint">
          Use the feedback form to report bugs, wallet issues, mobile problems, confusing copy, or anything else making the beta harder to use.
        </p>
        <div class="card-actions">
          <button type="button" class="btn primary" @click="openFeedbackPanel">Open Feedback Form</button>
          <router-link to="/help" class="btn ghost">Read Beta Guide</router-link>
          <router-link to="/dashboard" class="btn ghost">Back To Home</router-link>
        </div>
      </section>
    </main>
  </div>
</template>

<script>
import { apiClient, buildApiUrl, getApiErrorMessage, publicApiClient } from '../config/api';
import PublicDemoBanner from '../components/PublicDemoBanner.vue';
import WalletPanel from '../components/WalletPanel.vue';
import { useWallet } from '../services/wallet';
import { useAccess } from '../services/access';
import {
  buildReviewerEligibilityMessage,
  buildReviewPolicySummary,
  buildReviewPolicyWarning,
  normalizeReviewPolicyResponse,
} from '../utils/reviewPolicy';
import {
  buildVoterRewardRulesCopy,
  describeBlockVoterRewardSettlements,
  describeSubmissionVoterReward,
} from '../utils/voterRewards';
import { isPublicDemoMode, showDevelopmentTools } from '../utils/runtimeConfig';
import { buildSubmissionEligibilityView } from '../utils/submissionEligibility.js';
import { getEligibilityRuleChecks } from '../utils/eligibilityChecklist.js';
import { requestFeedbackPanelOpen } from '../utils/feedbackPanel.js';

export default {
  components: {
    PublicDemoBanner,
    WalletPanel,
  },
  data() {
    const walletManager = useWallet();
    const accessService = useAccess();
    return {
      walletManager,
      accessService,
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
      reviewPolicy: null,
      reviewPolicyError: '',
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
      showReviewOverrideForm: false,
      showSubmissionAdvancedFields: false,
      reviewOverrideScope: 'review',
      reviewOverrideReason: '',
      showMintQueueTools: showDevelopmentTools(),
      showPublicDemoBanner: isPublicDemoMode(),
    };
  },
  computed: {
    appSection() {
      return this.$route.meta?.appSection || 'home';
    },
    isHomePage() {
      return this.appSection === 'home';
    },
    isSubmitPage() {
      return this.appSection === 'submit';
    },
    isVotePage() {
      return this.appSection === 'vote';
    },
    isRewardsPage() {
      return this.appSection === 'rewards';
    },
    isActivityPage() {
      return this.appSection === 'activity';
    },
    isHelpPage() {
      return this.appSection === 'help';
    },
    isFeedbackPage() {
      return this.appSection === 'feedback';
    },
    mainSectionVisible() {
      return !this.isHomePage && !this.isRewardsPage;
    },
    pageEyebrow() {
      const labels = {
        home: 'Controlled Beta Home',
        submit: 'Submit',
        vote: 'Vote',
        rewards: 'Rewards And Wallet',
        activity: 'Activity And Explorer',
        help: 'Help And Beta Guide',
        feedback: 'Feedback',
      };
      return labels[this.appSection] || 'Controlled Beta Dashboard';
    },
    pageTitle() {
      const labels = {
        home: 'What should you do next?',
        submit: 'Prepare and submit a meme',
        vote: 'Review originality and cast votes',
        rewards: 'Track rewards, wallet state, and test ZOID',
        activity: 'Follow recent submissions and chain activity',
        help: 'Use this guide if you get stuck',
        feedback: 'Send beta feedback without leaving the app',
      };
      return labels[this.appSection] || 'Create, vote, and track test ZOID';
    },
    pageSubtitle() {
      const labels = {
        home: 'Home keeps the beta simple: check your status, see the next recommended action, and jump into the right tool.',
        submit: 'Upload content, check submission eligibility, and send new memes into originality review.',
        vote: 'Review the current queue, confirm voting eligibility, and help decide what becomes certified.',
        rewards: 'See your balance, reward history, transfer tools, and wallet verification details in one place.',
        activity: 'Keep the more technical submission, certificate, and recent block details off the main dashboard but easy to reach.',
        help: 'Find setup reminders, MetaMask guidance, beta rules, feedback entry points, and safety warnings.',
        feedback: 'Feedback stays easy to find before and after login so beta testers can report issues quickly.',
      };
      return labels[this.appSection] || 'This is the main beta workspace for submitting content, voting on originality, and following your rewards.';
    },
    showRefreshButton() {
      return !this.isHelpPage && !this.isFeedbackPage;
    },
    navigationItems() {
      return [
        { label: 'Home', to: '/dashboard', section: 'home' },
        { label: 'Submit', to: '/submit', section: 'submit' },
        { label: 'Vote', to: '/vote', section: 'vote' },
        { label: 'Rewards', to: '/rewards', section: 'rewards' },
        { label: 'Activity', to: '/activity', section: 'activity' },
        { label: 'Help', to: '/help', section: 'help' },
        { label: 'Feedback', to: '/feedback', section: 'feedback' },
      ];
    },
    accessSummaryHeadline() {
      if (this.accessService.isAppUnlocked()) {
        return 'Your approved beta session is active.';
      }
      if (this.accessService.state.me?.wallet_session_authenticated) {
        return 'Wallet verified, but approval is still limited.';
      }
      return 'Reconnect your approved wallet to keep testing.';
    },
    accessSummaryDetail() {
      return this.accessService.state.eligibility?.blocked_reasons?.[0]?.message
        || 'Admin tools remain separate. Use these pages only for normal tester actions such as submit, vote, rewards, activity, help, and feedback.';
    },
    walletSummaryHeadline() {
      if (this.walletManager.state.isVerifiedSession) {
        return this.walletManager.shortenAddress(this.walletManager.state.verifiedWalletAddress);
      }
      if (this.walletManager.state.isConnected) {
        return 'Connected but not verified';
      }
      return 'Not connected';
    },
    accessUnlockLabel() {
      return this.accessService.isAppUnlocked() ? 'Unlocked' : 'Needs approval';
    },
    nextActionTitle() {
      if (!this.walletManager.state.isConnected || !this.walletManager.state.isVerifiedSession) {
        return 'Reconnect and verify your wallet';
      }
      if (this.submissionEligibility?.can_submit === false) {
        return 'Check what is blocking submissions';
      }
      if (this.pendingSubmissions.length > 0) {
        return 'Review the current vote queue';
      }
      return 'Submit your next meme';
    },
    nextActionDetail() {
      if (!this.walletManager.state.isConnected || !this.walletManager.state.isVerifiedSession) {
        return 'Most beta actions still require the same approved wallet you used before. Verify it again before testing submit, vote, or rewards.';
      }
      if (this.submissionEligibility?.can_submit === false) {
        return this.submissionEligibilityView.detail || 'Submission eligibility is currently blocked. Open Submit to see the rule checks and next steps.';
      }
      if (this.pendingSubmissions.length > 0) {
        return 'There are submissions waiting for originality review right now. Voting helps decide what becomes certified.';
      }
      return 'Nothing is waiting on you yet, so the easiest next step is to submit content and start a fresh review.';
    },
    nextActionRoute() {
      if (!this.walletManager.state.isConnected || !this.walletManager.state.isVerifiedSession) {
        return '/rewards';
      }
      if (this.submissionEligibility?.can_submit === false) {
        return '/submit';
      }
      if (this.pendingSubmissions.length > 0) {
        return '/vote';
      }
      return '/submit';
    },
    nextActionLabel() {
      if (!this.walletManager.state.isConnected || !this.walletManager.state.isVerifiedSession) {
        return 'Open Rewards And Wallet';
      }
      if (this.submissionEligibility?.can_submit === false) {
        return 'Open Submit';
      }
      if (this.pendingSubmissions.length > 0) {
        return 'Open Vote';
      }
      return 'Open Submit';
    },
    homeActionCards() {
      return [
        {
          kicker: 'Main Action',
          title: 'Submit a meme',
          copy: 'Upload content, check submission eligibility, and send a new meme into originality review.',
          to: '/submit',
        },
        {
          kicker: 'Main Action',
          title: 'Vote on originality',
          copy: this.pendingSubmissions.length > 0
            ? `${this.pendingSubmissions.length} submission${this.pendingSubmissions.length === 1 ? '' : 's'} waiting for review right now.`
            : 'Nothing to vote on right now. Check back after someone submits content.',
          to: '/vote',
        },
        {
          kicker: 'Wallet',
          title: 'View rewards',
          copy: 'Check your test ZOID balance, reward history, wallet verification state, and transfer tools.',
          to: '/rewards',
        },
        {
          kicker: 'Support',
          title: 'Read beta guide',
          copy: 'Open setup help, MetaMask instructions, safety reminders, and feedback guidance.',
          to: '/help',
        },
      ];
    },
    pendingSubmissions() {
      return this.submissions.filter((submission) => submission.status === 'pending');
    },
    approvedCertificateSubmissions() {
      return this.approvedSubmissions.filter((submission) => this.getCertificate(submission));
    },
    rejectedSubmissions() {
      return this.submissions.filter((submission) => submission.status === 'rejected');
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
      if (!this.hasVerifiedWalletIdentity) {
        return false;
      }
      if (this.submissionEligibility && this.submissionEligibility.can_submit === false) {
        return false;
      }
      return true;
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
      if (this.submissionEligibility && this.submissionEligibility.can_submit === false) {
        return 'Submission Blocked';
      }
      return this.uploadedContent ? 'Sign And Submit' : 'Sign And Submit';
    },
    submissionIdentityHint() {
      if (this.hasVerifiedWalletIdentity) {
        return 'Your verified wallet will sign this submission before it enters community voting.';
      }
      if (!this.walletManager.state.isConnected) {
        return 'Connect MetaMask first so the app knows which wallet should own this submission.';
      }
      return 'Verify your wallet before submitting. Every new submission needs a fresh wallet signature.';
    },
    votingIdentityHint() {
      if (this.hasVerifiedWalletIdentity) {
        return 'Your verified wallet signs each originality vote before it is recorded.';
      }
      if (!this.walletManager.state.isConnected) {
        return 'Connect MetaMask first so you can review and vote with your wallet.';
      }
      return 'Verify your wallet before voting. Each vote needs a fresh wallet signature.';
    },
    submissionEligibility() {
      return this.accessService.state.eligibility?.submission || null;
    },
    submissionEligibilityView() {
      return buildSubmissionEligibilityView(this.accessService.state.eligibility);
    },
    submissionEligibilityToneClass() {
      return this.submissionEligibilityView.tone === 'error' ? 'error' : 'success';
    },
    submissionRuleChecks() {
      return getEligibilityRuleChecks(this.accessService.state.eligibility, ['submission']);
    },
    reviewPolicySummary() {
      return this.reviewPolicy ? buildReviewPolicySummary(this.reviewPolicy) : 'Loading reviewer policy...';
    },
    reviewPolicyWarning() {
      return buildReviewPolicyWarning(this.reviewPolicy);
    },
    reviewerEligibilityMessage() {
      return buildReviewerEligibilityMessage(this.reviewPolicy);
    },
    reviewEligibilityBlockedReason() {
      return this.accessService.state.eligibility?.blocked_reasons?.find((item) => ['review', 'voting', 'rewards'].includes(item.scope))?.message || '';
    },
    reviewEligibilityRuleChecks() {
      return getEligibilityRuleChecks(this.accessService.state.eligibility, ['voting', 'rewards']);
    },
    reviewEligibilityNextSteps() {
      return Array.isArray(this.accessService.state.eligibility?.possible_next_steps)
        ? this.accessService.state.eligibility.possible_next_steps
        : [];
    },
    reviewEligibilityOverrideMessage() {
      const overrides = this.accessService.state.eligibility?.allowlist_overrides_applied || [];
      const reviewOverride = overrides.find((item) => ['review', 'voting', 'rewards'].includes(item.scope));
      if (!reviewOverride) {
        return '';
      }
      return `An admin override is active for ${String(reviewOverride.allowlist_scope || reviewOverride.scope || 'this wallet').replace(/_/g, ' ')}.`;
    },
    canRequestReviewOverride() {
      return Boolean(this.voteWalletAddress && (this.reviewPolicy?.eligibility?.eligible === false || this.reviewEligibilityBlockedReason));
    },
    voterRewardPolicyLines() {
      return buildVoterRewardRulesCopy();
    },
    userRecentSubmissions() {
      const walletAddress = String(this.submissionWalletAddress || '').toLowerCase();
      if (!walletAddress) {
        return [];
      }
      return this.submissions
        .filter((submission) => String(submission.submitter || submission.creator_wallet_address || '').toLowerCase() === walletAddress)
        .slice()
        .sort((left, right) => (right.created_at || 0) - (left.created_at || 0))
        .slice(0, 5);
    },
  },
  async created() {
    await this.walletManager.detectMetaMask();
    await this.refreshWorkflow();
  },
  watch: {
    voteWalletAddress() {
      this.fetchReviewPolicy();
    },
    hasVerifiedWalletIdentity() {
      this.fetchReviewPolicy();
    },
  },
  methods: {
    openFeedbackPanel() {
      requestFeedbackPanelOpen({ panelId: 'feedback-panel' });
    },
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
          this.fetchReviewPolicy(),
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
      if (this.submissionEligibility && this.submissionEligibility.can_submit === false) {
        this.errorMessage = this.submissionEligibility.message || 'Submission is currently blocked.';
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
    async fetchReviewPolicy() {
      this.reviewPolicyError = '';
      try {
        await this.accessService.refreshEligibility(this.walletManager.getAuthorizationHeader());
        const client = this.hasVerifiedWalletIdentity ? apiClient : publicApiClient;
        const params = this.voteWalletAddress ? { wallet_address: this.voteWalletAddress } : {};
        const response = await client.get('/review/policy', { params });
        this.reviewPolicy = normalizeReviewPolicyResponse(response.data);
      } catch (error) {
        console.error('Error fetching review policy:', error);
        this.reviewPolicy = null;
        this.reviewPolicyError = getApiErrorMessage(error, 'Failed to load reviewer policy.');
      }
    },
    async submitReviewOverride() {
      const result = await this.accessService.submitOverrideRequest(
        {
          requested_scope: this.reviewOverrideScope,
          reason: this.reviewOverrideReason,
          wallet_address: this.voteWalletAddress || null,
          access_account_id: this.accessService.state.me?.access_account_id || this.accessService.state.me?.access_account?.access_account_id || null,
          current_page: '/dashboard/review',
          detected_blocked_reason: this.accessService.state.eligibility?.blocked_reasons?.find((item) => ['review', 'voting', 'rewards'].includes(item.scope))?.reason || null,
        },
        this.walletManager.getAuthorizationHeader(),
      );
      if (result) {
        this.reviewOverrideReason = '';
        this.reviewOverrideScope = 'review';
        this.showReviewOverrideForm = false;
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
      if (this.reviewPolicy?.eligibility?.eligible === false) {
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
    describeSubmissionReward(submission) {
      return describeSubmissionVoterReward(submission?.voter_reward_summary);
    },
    describeBlockVoterRewards(block) {
      return describeBlockVoterRewardSettlements(block);
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
      if (this.reviewPolicy?.eligibility?.eligible === false) {
        this.voteError = this.reviewerEligibilityMessage || 'This wallet is not currently eligible to review.';
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
        await this.fetchReviewPolicy();
      } catch (error) {
        console.error('Error recording vote:', error);
        this.voteError = getApiErrorMessage(error, 'Failed to record vote.');
        await this.fetchReviewPolicy();
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
  grid-template-columns: minmax(0, 1fr);
  gap: 22px;
  align-items: start;
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
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.quickstart-card {
  align-items: stretch;
  justify-content: stretch;
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.quickstart-item {
  padding: 16px;
  border-radius: 10px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: rgba(8, 8, 8, 0.58);
  display: grid;
  gap: 8px;
  text-align: left;
}

.quickstart-item strong {
  color: #f4f4f4;
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

.review-policy-panel,
.reward-policy-panel,
.reward-summary-panel {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 16px;
  border-radius: 8px;
}

.review-policy-panel,
.reward-policy-panel {
  margin-bottom: 18px;
}

.review-policy-panel {
  border: 1px solid rgba(255, 184, 77, 0.35);
  background: rgba(255, 184, 77, 0.08);
}

.eligibility-checklist {
  display: grid;
  gap: 10px;
}

.eligibility-rule {
  padding: 12px;
  border-radius: 10px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.04);
}

.eligibility-rule.pass {
  border-color: rgba(141, 245, 166, 0.24);
}

.eligibility-rule.fail {
  border-color: rgba(255, 71, 71, 0.3);
}

.eligibility-rule-value {
  overflow-wrap: anywhere;
  word-break: break-word;
}

.inline-override-panel {
  display: grid;
  gap: 12px;
}

.reward-policy-panel,
.reward-summary-panel {
  border: 1px solid rgba(141, 245, 166, 0.25);
  background: rgba(141, 245, 166, 0.06);
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

.helper-strip {
  justify-content: flex-start;
}

.app-nav {
  flex-wrap: wrap;
  justify-content: flex-start;
}

.nav-link.active {
  background: linear-gradient(135deg, #ff4747 0%, #d71919 100%);
  border-color: transparent;
  box-shadow: 0 6px 16px rgba(255, 0, 0, 0.28);
}

.home-overview,
.rewards-intro-card {
  width: min(1220px, 100%);
  margin: 22px auto 0;
}

.home-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 22px;
}

.home-card {
  display: grid;
  gap: 16px;
}

.compact-detail-grid {
  margin-top: 0;
}

.home-action-grid {
  margin-top: 22px;
}

.home-action-card {
  gap: 12px;
}

.page-help-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.feedback-cta-card {
  width: 100%;
}

@media (max-width: 1060px) {
  .dashboard-header {
    align-items: flex-start;
    flex-direction: column;
  }

  .metric-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .home-grid,
  .quickstart-card {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .page-help-grid {
    grid-template-columns: minmax(0, 1fr);
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

  .home-grid,
  .quickstart-card {
    grid-template-columns: minmax(0, 1fr);
  }

  .btn,
  .header-actions {
    width: 100%;
  }

  .file-input,
  .input-field {
    font-size: 16px;
  }

  .vote-actions,
  .card-actions,
  .submission-actions {
    display: grid;
    grid-template-columns: minmax(0, 1fr);
  }

  .workflow-chip,
  .status-pill,
  .meta-chip {
    white-space: normal;
  }

  .content-image {
    max-height: 260px;
  }
}
</style>
