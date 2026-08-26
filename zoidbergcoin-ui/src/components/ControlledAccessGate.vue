<template>
  <div class="access-shell">
    <PublicDemoBanner />
    <section class="access-card">
      <div class="access-hero-grid">
        <div class="access-intro-panel">
          <p class="eyebrow">ZoidbergChain</p>
          <p v-if="accessLabel" class="access-label">{{ accessLabel }}</p>
          <div class="hero-heading">
            <h1>Join the beta</h1>
            <span class="beta-badge">Controlled Beta</span>
          </div>
          <p class="lead">
            A controlled beta for testing meme originality, voting, and native test ZOID rewards.
          </p>

          <div class="journey-grid access-paths responsive-access-grid">
            <article class="journey-card">
              <p class="section-label">I&apos;m New</p>
              <strong>Request beta access</strong>
            </article>
            <article class="journey-card">
              <p class="section-label">I Have an Invite</p>
              <strong>Enter your invite code</strong>
            </article>
            <article class="journey-card">
              <p class="section-label">I&apos;m Returning</p>
              <strong>Reconnect your approved wallet</strong>
            </article>
            <article v-if="requestsEnabled" class="journey-card">
              <p class="section-label">Request Access</p>
              <strong>Ask for beta access</strong>
            </article>
          </div>

          <div class="entry-switch">
            <button
              type="button"
              class="entry-btn"
              :class="{ active: entryMode === 'new' }"
              @click="setEntryMode('new')"
            >
              I&apos;m New
            </button>
            <button
              type="button"
              class="entry-btn"
              :class="{ active: entryMode === 'returning' }"
              @click="setEntryMode('returning')"
            >
              Returning With My Approved Wallet
            </button>
          </div>

          <p v-if="mobileWalletSupport.helperText" class="status info">{{ mobileWalletSupport.helperText }}</p>
          <p v-if="mobileWalletSupport.noProviderMessage" class="status warning">{{ mobileWalletSupport.noProviderMessage }}</p>

          <div v-if="mobileWalletSupport.shouldShowOpenInMetaMask" class="mobile-open-card">
            <a
              :href="mobileWalletSupport.openInMetaMaskUrl"
              class="secondary-btn meta-mask-link"
              @click="persistGateState"
            >
              Open in MetaMask
            </a>
            <p class="mobile-open-note">
              Open the current page in MetaMask Mobile so wallet connection and signing can continue there.
            </p>
          </div>

          <div class="active-flow-shell">
            <div v-if="entryMode === 'returning'" class="panel-stack">
              <div class="returning-panel">
                <p class="section-label">Returning Approved Wallet</p>
                <h2>{{ returningWalletGuidance.headline }}</h2>
                <p class="wallet-note">{{ returningWalletGuidance.detail }}</p>
                <p v-if="accessActionState.showProviderChooser" class="wallet-note">Choose how to connect your approved wallet.</p>
                <p v-if="shouldShowWalletStatus" class="wallet-line"><strong>Wallet status:</strong> {{ walletStatusText }}</p>
                <p class="wallet-note">{{ walletNextStepText }}</p>

                <p v-if="interruptedWalletMessage" class="status warning">{{ interruptedWalletMessage }}</p>
                <p v-if="returningStatusMessage" class="status" :class="returningStatusClass">{{ returningStatusMessage }}</p>

                <div class="wallet-actions">
                  <button
                    v-if="showMetaMaskButton"
                    type="button"
                    class="primary-btn"
                    @click="connectMetaMaskWallet"
                    :disabled="wallet.state.connectionStatus === 'connecting' && wallet.state.providerId === 'metamask'"
                  >
                    {{ wallet.state.connectionStatus === 'connecting' && wallet.state.providerId === 'metamask' ? 'Connecting...' : 'Continue with MetaMask' }}
                  </button>
                  <button
                    v-if="showEmbeddedWalletConnectButton"
                    type="button"
                    class="secondary-btn"
                    @click="connectEmbeddedWalletFromExistingSession"
                    :disabled="isConnectingEmbeddedWallet"
                  >
                    {{ isConnectingEmbeddedWallet ? 'Connecting...' : 'Continue with Email / Social Wallet' }}
                  </button>
                  <button
                    v-if="showEmbeddedWalletUnavailableButton"
                    type="button"
                    class="ghost-btn"
                    disabled
                  >
                    {{ embeddedWalletDisabledButtonLabel }}
                  </button>
                  <button
                    v-else-if="accessActionState.showVerify"
                    type="button"
                    class="primary-btn"
                    @click="continueReturningFlow"
                    :disabled="wallet.state.connectionStatus === 'verifying'"
                  >
                    {{ wallet.state.connectionStatus === 'verifying' ? 'Verifying...' : returningWalletGuidance.actionLabel }}
                  </button>
                  <button
                    v-else-if="wallet.state.isVerifiedSession && !access.state.me?.access_granted"
                    type="button"
                    class="secondary-btn"
                    @click="refreshReturningAccess"
                  >
                    {{ returningWalletGuidance.actionLabel }}
                  </button>
                  <button
                    v-if="showRetryButton"
                    type="button"
                    class="secondary-btn"
                    @click="retryPendingWalletAction"
                  >
                    Retry Wallet Step
                  </button>
                  <button
                    v-if="shouldShowChangeWalletMethod"
                    type="button"
                    class="ghost-btn"
                    @click="changeWalletMethod"
                  >
                    Change Wallet Method
                  </button>
                  <button
                    type="button"
                    class="ghost-btn"
                    @click="setEntryMode('new')"
                  >
                    I&apos;m New Here
                  </button>
                </div>
                <p v-if="showEmbeddedWalletConnectButton" class="wallet-note provider-helper">
                  {{ embeddedWalletConfiguredHelperText }}
                </p>
                <p
                  v-if="(accessActionState.showProviderChooser || selectedWalletProvider === 'privy_embedded') && embeddedWalletPublicMessage"
                  class="status"
                  :class="embeddedWalletTemporarilyUnavailable ? 'warning' : 'info'"
                >
                  {{ embeddedWalletPublicMessage }}
                </p>
                <details v-if="shouldShowEmbeddedWalletDiagnostics" class="diagnostic-panel">
                  <summary>Email / Social Wallet diagnostics (development only)</summary>
                  <p v-if="embeddedWalletUnavailableMessage" class="wallet-note">{{ embeddedWalletUnavailableMessage }}</p>
                  <p class="wallet-note">Unavailable reason: {{ embeddedWalletDiagnosticReasonLabel }}</p>
                  <ul class="diagnostic-list">
                    <li>providerConfigured: {{ embeddedWalletDiagnostics?.providerConfigured ? 'true' : 'false' }}</li>
                    <li>appIdPresent: {{ embeddedWalletDiagnostics?.appIdPresent ? 'true' : 'false' }}</li>
                    <li>providerName: {{ embeddedWalletDiagnostics?.providerName || '(not set)' }}</li>
                    <li>sdkImportAttempted: {{ embeddedWalletDiagnostics?.sdkImportAttempted ? 'true' : 'false' }}</li>
                    <li>sdkImportSucceeded: {{ embeddedWalletDiagnostics?.sdkImportSucceeded ? 'true' : 'false' }}</li>
                    <li>initAttempted: {{ embeddedWalletDiagnostics?.initAttempted ? 'true' : 'false' }}</li>
                    <li>initSucceeded: {{ embeddedWalletDiagnostics?.initSucceeded ? 'true' : 'false' }}</li>
                    <li>origin: {{ embeddedWalletDiagnostics?.origin || '(not available)' }}</li>
                    <li>isSecureContext: {{ embeddedWalletDiagnostics?.isSecureContext ? 'true' : 'false' }}</li>
                    <li>lastErrorMessage: {{ embeddedWalletDiagnostics?.lastErrorMessage || '(none)' }}</li>
                  </ul>
                </details>
                <div v-if="shouldShowEmbeddedAuthPanel" class="panel-stack embedded-auth-panel">
                  <label class="field">
                    <span>Email</span>
                    <input v-model.trim="embeddedWalletEmail" type="email" placeholder="you@example.com" autocomplete="email" />
                  </label>
                  <div class="wallet-actions">
                    <button
                      type="button"
                      class="secondary-btn"
                      @click="sendEmbeddedWalletCode"
                      :disabled="isSendingEmbeddedWalletCode || !embeddedWalletEmail"
                    >
                      {{ isSendingEmbeddedWalletCode ? 'Sending Code...' : 'Email Me A Code' }}
                    </button>
                    <button
                      v-if="supportsEmbeddedSocialLogin"
                      type="button"
                      class="ghost-btn"
                      @click="startEmbeddedWalletSocialLogin"
                    >
                      Continue with {{ embeddedWalletSocialProviderLabel }}
                    </button>
                  </div>
                  <label class="field">
                    <span>Verification Code</span>
                    <input v-model.trim="embeddedWalletCode" type="text" placeholder="123123" inputmode="numeric" autocomplete="one-time-code" />
                  </label>
                  <button
                    type="button"
                    class="primary-btn"
                    @click="connectEmbeddedWalletWithCode"
                    :disabled="isConnectingEmbeddedWallet || !embeddedWalletEmail || !embeddedWalletCode"
                  >
                    {{ isConnectingEmbeddedWallet ? 'Connecting...' : 'Verify Email And Connect Wallet' }}
                  </button>
                  <p class="wallet-note">{{ embeddedWalletOption?.portability_help_copy || 'Use a wallet you can reconnect with later.' }}</p>
                  <p v-if="embeddedWalletMessage" class="status success">{{ embeddedWalletMessage }}</p>
                  <p v-if="embeddedWalletError" class="status error">{{ embeddedWalletError }}</p>
                </div>
              </div>
            </div>

            <template v-else>
              <div class="mode-switch">
                <button
                  type="button"
                  class="mode-btn"
                  :class="{ active: newUserMode === 'invite' }"
                  @click="setNewUserMode('invite')"
                >
                  I Have an Invite
                </button>
                <button
                  v-if="requestsEnabled"
                  type="button"
                  class="mode-btn"
                  :class="{ active: newUserMode === 'request' }"
                  @click="setNewUserMode('request')"
                >
                  Request Beta Access
                </button>
              </div>

              <div v-if="newUserMode === 'invite'" class="panel-stack flow-panel">
                <label class="field">
                  <span>Invite Code</span>
                  <input v-model.trim="inviteCode" type="text" placeholder="ZC-..." autocomplete="one-time-code" />
                </label>
                <button type="button" class="primary-btn" @click="login" :disabled="access.state.isLoggingIn || !inviteCode">
                  {{ access.state.isLoggingIn ? 'Checking Invite...' : 'Continue With Invite' }}
                </button>
                <p v-if="inviteAcceptedMessage" class="status success">{{ inviteAcceptedMessage }}</p>

                <div class="wallet-box">
                  <p class="section-label">Connect And Verify Your Wallet</p>
                  <h2 v-if="accessActionState.showProviderChooser" class="wallet-box-heading">Choose how to connect your wallet</h2>
                  <p v-if="shouldShowWalletStatus" class="wallet-line"><strong>Wallet status:</strong> {{ walletStatusText }}</p>
                  <p class="wallet-note">{{ walletNextStepText }}</p>
                  <p v-if="accessActionState.showBind" class="status success">Wallet verified. Bind this wallet to your approved beta access.</p>
                  <p v-if="interruptedWalletMessage" class="status warning">{{ interruptedWalletMessage }}</p>
                  <div class="wallet-actions">
                    <button
                      v-if="showMetaMaskButton"
                      type="button"
                      class="secondary-btn"
                      @click="connectMetaMaskWallet"
                      :disabled="wallet.state.connectionStatus === 'connecting' && wallet.state.providerId === 'metamask'"
                    >
                      {{ wallet.state.connectionStatus === 'connecting' && wallet.state.providerId === 'metamask' ? 'Connecting...' : 'Continue with MetaMask' }}
                    </button>
                    <button
                      v-if="showEmbeddedWalletConnectButton"
                      type="button"
                      class="secondary-btn"
                      @click="connectEmbeddedWalletFromExistingSession"
                      :disabled="isConnectingEmbeddedWallet"
                    >
                      {{ isConnectingEmbeddedWallet ? 'Connecting...' : 'Continue with Email / Social Wallet' }}
                    </button>
                    <button
                      v-if="showEmbeddedWalletUnavailableButton"
                      type="button"
                      class="ghost-btn"
                      disabled
                    >
                      {{ embeddedWalletDisabledButtonLabel }}
                    </button>
                    <button
                      v-else-if="accessActionState.showVerify"
                      type="button"
                      class="secondary-btn"
                      @click="verifyWallet"
                      :disabled="wallet.state.connectionStatus === 'verifying'"
                    >
                      {{ wallet.state.connectionStatus === 'verifying' ? 'Verifying...' : 'Verify Wallet' }}
                    </button>
                    <button
                      v-else-if="accessActionState.showBind"
                      type="button"
                      class="primary-btn"
                      @click="bindWallet"
                      :disabled="access.state.isBindingWallet"
                    >
                      {{ access.state.isBindingWallet ? 'Binding Wallet...' : 'Bind Verified Wallet' }}
                    </button>
                    <button
                      v-if="showRetryButton"
                      type="button"
                      class="secondary-btn"
                      @click="retryPendingWalletAction"
                    >
                      Retry Wallet Step
                    </button>
                    <button
                      v-if="shouldShowChangeWalletMethod"
                      type="button"
                      class="ghost-btn"
                      @click="changeWalletMethod"
                    >
                      Change Wallet Method
                    </button>
                  </div>
                  <p v-if="showEmbeddedWalletConnectButton" class="wallet-note provider-helper">
                    {{ embeddedWalletConfiguredHelperText }}
                  </p>
                  <p
                    v-if="(accessActionState.showProviderChooser || selectedWalletProvider === 'privy_embedded') && embeddedWalletPublicMessage"
                    class="status"
                    :class="embeddedWalletTemporarilyUnavailable ? 'warning' : 'info'"
                  >
                    {{ embeddedWalletPublicMessage }}
                  </p>
                  <details v-if="shouldShowEmbeddedWalletDiagnostics" class="diagnostic-panel">
                    <summary>Email / Social Wallet diagnostics (development only)</summary>
                    <p v-if="embeddedWalletUnavailableMessage" class="wallet-note">{{ embeddedWalletUnavailableMessage }}</p>
                    <p class="wallet-note">Unavailable reason: {{ embeddedWalletDiagnosticReasonLabel }}</p>
                    <ul class="diagnostic-list">
                      <li>providerConfigured: {{ embeddedWalletDiagnostics?.providerConfigured ? 'true' : 'false' }}</li>
                      <li>appIdPresent: {{ embeddedWalletDiagnostics?.appIdPresent ? 'true' : 'false' }}</li>
                      <li>providerName: {{ embeddedWalletDiagnostics?.providerName || '(not set)' }}</li>
                      <li>sdkImportAttempted: {{ embeddedWalletDiagnostics?.sdkImportAttempted ? 'true' : 'false' }}</li>
                      <li>sdkImportSucceeded: {{ embeddedWalletDiagnostics?.sdkImportSucceeded ? 'true' : 'false' }}</li>
                      <li>initAttempted: {{ embeddedWalletDiagnostics?.initAttempted ? 'true' : 'false' }}</li>
                      <li>initSucceeded: {{ embeddedWalletDiagnostics?.initSucceeded ? 'true' : 'false' }}</li>
                      <li>origin: {{ embeddedWalletDiagnostics?.origin || '(not available)' }}</li>
                      <li>isSecureContext: {{ embeddedWalletDiagnostics?.isSecureContext ? 'true' : 'false' }}</li>
                      <li>lastErrorMessage: {{ embeddedWalletDiagnostics?.lastErrorMessage || '(none)' }}</li>
                    </ul>
                  </details>
                  <div v-if="shouldShowEmbeddedAuthPanel" class="panel-stack embedded-auth-panel">
                    <label class="field">
                      <span>Email</span>
                      <input v-model.trim="embeddedWalletEmail" type="email" placeholder="you@example.com" autocomplete="email" />
                    </label>
                    <div class="wallet-actions">
                      <button
                        type="button"
                        class="secondary-btn"
                        @click="sendEmbeddedWalletCode"
                        :disabled="isSendingEmbeddedWalletCode || !embeddedWalletEmail"
                      >
                        {{ isSendingEmbeddedWalletCode ? 'Sending Code...' : 'Email Me A Code' }}
                      </button>
                      <button
                        v-if="supportsEmbeddedSocialLogin"
                        type="button"
                        class="ghost-btn"
                        @click="startEmbeddedWalletSocialLogin"
                      >
                        Continue with {{ embeddedWalletSocialProviderLabel }}
                      </button>
                    </div>
                    <label class="field">
                      <span>Verification Code</span>
                      <input v-model.trim="embeddedWalletCode" type="text" placeholder="123123" inputmode="numeric" autocomplete="one-time-code" />
                    </label>
                    <button
                      type="button"
                      class="primary-btn"
                      @click="connectEmbeddedWalletWithCode"
                      :disabled="isConnectingEmbeddedWallet || !embeddedWalletEmail || !embeddedWalletCode"
                    >
                      {{ isConnectingEmbeddedWallet ? 'Connecting...' : 'Verify Email And Connect Wallet' }}
                    </button>
                    <p class="wallet-note">{{ embeddedWalletOption?.portability_help_copy || 'Use a wallet you can reconnect with later.' }}</p>
                    <p v-if="embeddedWalletMessage" class="status success">{{ embeddedWalletMessage }}</p>
                    <p v-if="embeddedWalletError" class="status error">{{ embeddedWalletError }}</p>
                  </div>
                </div>
              </div>

              <form v-else-if="requestsEnabled" class="panel-stack flow-panel request-panel" @submit.prevent="submitRequest">
                <label class="field">
                  <span>Name</span>
                  <input v-model.trim="requestForm.name" type="text" required />
                </label>
                <label class="field">
                  <span>Email</span>
                  <input v-model.trim="requestForm.email" type="email" required />
                </label>
                <label class="field">
                  <span>Organization Or Social Handle (Optional)</span>
                  <input v-model.trim="requestForm.handle" type="text" />
                </label>
                <label class="field">
                  <span>Why Would You Like Access?</span>
                  <textarea v-model.trim="requestForm.reason" rows="3" required />
                </label>
                <label class="field">
                  <span>Anything Else We Should Know? (Optional)</span>
                  <textarea v-model.trim="requestForm.notes" rows="3" />
                </label>
                <button type="submit" class="primary-btn" :disabled="access.state.isSubmittingRequest">
                  {{ access.state.isSubmittingRequest ? 'Sending Request...' : 'Send Access Request' }}
                </button>
              </form>

              <div v-else class="panel-stack flow-panel">
                <p class="status">
                  New requests are paused on this node right now. If you already have approval, use your invite code or return with your approved wallet.
                </p>
              </div>
            </template>
          </div>
        </div>

        <div class="rules-panel main-access-card">
          <div class="card-heading-inline">
            <div>
              <p class="section-label">Wallet Login</p>
              <h2>Choose a wallet method</h2>
            </div>
            <p class="wallet-note card-aside">Want details? Read the Beta Guide.</p>
          </div>
          <div class="journey-grid onboarding-grid compact-options responsive-wallet-grid">
            <article
              v-for="option in onboardingOptions"
              :key="option.id"
              class="journey-card"
            >
              <p class="section-label">{{ option.availability === 'available' ? 'Available Now' : 'Coming Soon' }}</p>
              <strong>{{ option.title }}</strong>
              <p class="wallet-note compact-copy">{{ option.description }}</p>
              <p v-if="option.warning" class="wallet-note">{{ option.warning }}</p>
            </article>
          </div>
          <div class="helper-links-inline">
            <router-link to="/why-zoidbergcoin" class="ghost-btn feedback-shortcut">Beta Guide</router-link>
            <button type="button" class="ghost-btn feedback-shortcut" @click="openFeedbackPanel">Send Feedback</button>
          </div>
          <details class="mini-help top-help">
            <summary>Need help?</summary>
            <p class="wallet-note">Use your invite code, request access, or return with your approved wallet. Want details? Read the Beta Guide.</p>
            <p class="wallet-note">If MetaMask is not detected on mobile, open this page in the MetaMask Mobile browser.</p>
            <p v-if="eligibilityHeadline" class="status compact-help-status" :class="eligibilityTone">{{ eligibilityHeadline }}</p>
            <p v-if="primaryBlockedReason" class="wallet-note">{{ primaryBlockedReason }}</p>
            <p v-if="blockedSummaryCallToAction" class="wallet-note">{{ blockedSummaryCallToAction }}</p>
            <p v-if="activeOverrideMessage" class="status success">{{ activeOverrideMessage }}</p>
            <details v-if="hasEligibilityDetails" class="diagnostic-panel compact-help-panel">
              <summary>Why am I blocked?</summary>
              <div v-if="accessRuleChecks.length" class="eligibility-checklist">
                <div
                  v-for="rule in accessRuleChecks"
                  :key="`${rule.scope}-${rule.rule_id}`"
                  class="eligibility-rule"
                  :class="{ pass: rule.passed, fail: rule.required && !rule.passed }"
                >
                  <strong>{{ rule.label }}</strong>
                  <p class="wallet-note">{{ rule.description }}</p>
                  <p class="wallet-note eligibility-rule-value">
                    Current: {{ rule.current_value ?? 'Not available' }}
                    <span v-if="rule.required_value !== null && rule.required_value !== undefined"> | Needed: {{ rule.required_value }}</span>
                  </p>
                </div>
              </div>
              <p v-for="step in nextSteps" :key="step" class="wallet-note">{{ step }}</p>
              <p class="wallet-note">More details are available in the Beta Guide.</p>
            </details>
            <details v-if="canRequestOverride" class="diagnostic-panel compact-help-panel">
              <summary>Request Beta Help</summary>
              <p class="wallet-note">
                If you believe this wallet should already work, send a quick beta help request so an operator can review it.
              </p>
              <button type="button" class="ghost-btn compact-help-button" @click="showOverrideForm = !showOverrideForm">
                {{ showOverrideForm ? 'Hide Beta Help Form' : 'Open Beta Help Form' }}
              </button>
              <form v-if="showOverrideForm" class="panel-stack compact-help-form" @submit.prevent="submitOverride">
                <label class="field">
                  <span>Requested Scope</span>
                  <select v-model="overrideForm.requested_scope" class="field-select">
                    <option value="access">App Access</option>
                    <option value="review">Review Access</option>
                    <option value="voting">Voting Access</option>
                    <option value="rewards">Rewards Access</option>
                    <option value="all_beta">Full Beta Access</option>
                  </select>
                </label>
                <label class="field">
                  <span>Name (Optional)</span>
                  <input v-model.trim="overrideForm.name" type="text" />
                </label>
                <label class="field">
                  <span>Email (Optional)</span>
                  <input v-model.trim="overrideForm.email" type="email" />
                </label>
                <label class="field">
                  <span>Handle (Optional)</span>
                  <input v-model.trim="overrideForm.handle" type="text" />
                </label>
                <label class="field">
                  <span>Why do you need an override?</span>
                  <textarea v-model.trim="overrideForm.reason" rows="3" required />
                </label>
                <button type="submit" class="primary-btn" :disabled="access.state.isSubmittingOverrideRequest || !overrideForm.reason">
                  {{ access.state.isSubmittingOverrideRequest ? 'Sending Beta Help Request...' : 'Send Beta Help Request' }}
                </button>
              </form>
            </details>
          </details>
        </div>
      </div>

      <FeedbackPanel
        headline="Blocked or stuck? Send feedback."
        intro-copy="If wallet setup, allowlist access, mobile behavior, or beta rules are getting in your way, send a note directly from this screen."
        toggle-label="Open Feedback Form"
        entry-point="access_gate"
        :default-open="false"
        panel-id="feedback-panel"
      />

      <p v-if="access.state.successMessage" class="status success">{{ access.state.successMessage }}</p>
      <p v-if="wallet.state.errorMessage" class="status error">{{ wallet.state.errorMessage }}</p>
      <p v-if="access.state.errorMessage" class="status error">{{ access.state.errorMessage }}</p>

      <div class="disclaimer-row">
        <p class="wallet-note">Test ZOID has no real monetary value.</p>
        <p class="wallet-note">Never share seed phrases or private keys.</p>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue';
import PublicDemoBanner from './PublicDemoBanner.vue';
import FeedbackPanel from './FeedbackPanel.vue';
import { useWallet } from '../services/wallet';
import { useAccess } from '../services/access';
import {
  getAccessGateWalletStatusText,
  getControlledAccessActionState,
  getControlledAccessNextStepText,
} from '../utils/controlledAccessUi.js';
import {
  getEligibilityRuleChecks,
  getFailedRequiredRuleChecks,
} from '../utils/eligibilityChecklist.js';
import {
  buildReturningWalletGuidance,
  describeWalletSupport,
} from '../utils/mobileWallet.js';
import { EMBEDDED_WALLET_CONFIG } from '../utils/embeddedWalletConfig.js';
import { getWalletOnboardingOptions } from '../utils/walletOnboarding.js';
import { requestFeedbackPanelOpen } from '../utils/feedbackPanel.js';
import { showDevelopmentTools } from '../utils/runtimeConfig.js';

const emit = defineEmits(['unlocked']);

const ACCESS_GATE_STATE_KEY = 'zoidberg:access-gate-state';
const developmentToolsEnabled = showDevelopmentTools();
const wallet = useWallet();
const access = useAccess();
const entryMode = ref('new');
const newUserMode = ref('invite');
const inviteCode = ref('');
const selectedWalletProvider = ref('');
const interruptedWalletMessage = ref('');
const pendingWalletAction = ref('');
const showEmbeddedWalletForm = ref(false);
const embeddedWalletEmail = ref('');
const embeddedWalletCode = ref('');
const embeddedWalletMessage = ref('');
const embeddedWalletError = ref('');
const isSendingEmbeddedWalletCode = ref(false);
const isConnectingEmbeddedWallet = ref(false);
const requestForm = ref({
  name: '',
  email: '',
  handle: '',
  reason: '',
  notes: '',
});
const overrideForm = ref({
  requested_scope: 'access',
  name: '',
  email: '',
  handle: '',
  reason: '',
});
const showOverrideForm = ref(false);
const onboardingOptions = getWalletOnboardingOptions();
const mobileWalletSupport = ref({
  primaryWalletProviderLabel: 'MetaMask',
  isMobileDevice: false,
  hasInjectedProvider: false,
  isMetaMaskMobileBrowser: false,
  helperText: '',
  noProviderMessage: '',
  openInMetaMaskUrl: '',
  shouldShowOpenInMetaMask: false,
});

function openFeedbackPanel() {
  requestFeedbackPanelOpen({
    panelId: 'feedback-panel',
    scrollIntoView: true,
  });
}

function getStorage() {
  if (typeof window === 'undefined') {
    return null;
  }
  try {
    return window.localStorage || null;
  } catch {
    return null;
  }
}

function refreshMobileWalletSupport() {
  mobileWalletSupport.value = describeWalletSupport({
    userAgent: typeof navigator === 'undefined' ? '' : navigator.userAgent,
    ethereum: typeof window === 'undefined' ? null : window.ethereum,
    currentUrl: typeof window === 'undefined' ? '' : window.location.href,
  });
}

function persistGateState() {
  const storage = getStorage();
  if (!storage) {
    return;
  }
  storage.setItem(
    ACCESS_GATE_STATE_KEY,
    JSON.stringify({
      entryMode: entryMode.value,
      newUserMode: newUserMode.value,
      inviteCode: inviteCode.value,
      pendingWalletAction: pendingWalletAction.value,
      interruptedWalletMessage: interruptedWalletMessage.value,
    }),
  );
}

function restoreGateState() {
  const storage = getStorage();
  if (!storage) {
    return;
  }
  const raw = storage.getItem(ACCESS_GATE_STATE_KEY);
  if (!raw) {
    return;
  }
  try {
    const parsed = JSON.parse(raw);
    entryMode.value = parsed.entryMode === 'returning' ? 'returning' : 'new';
    newUserMode.value = parsed.newUserMode === 'request' ? 'request' : 'invite';
    inviteCode.value = String(parsed.inviteCode || '');
    pendingWalletAction.value = String(parsed.pendingWalletAction || '');
    interruptedWalletMessage.value = String(parsed.interruptedWalletMessage || '');
  } catch {
    // Ignore malformed local gate state.
  }
}

function setPendingWalletAction(action, message) {
  pendingWalletAction.value = action;
  interruptedWalletMessage.value = message;
  persistGateState();
}

function clearPendingWalletAction() {
  pendingWalletAction.value = '';
  interruptedWalletMessage.value = '';
  persistGateState();
}

function resetEmbeddedWalletMessages() {
  embeddedWalletMessage.value = '';
  embeddedWalletError.value = '';
}

function clearWalletMethodUi() {
  selectedWalletProvider.value = '';
  showEmbeddedWalletForm.value = false;
  embeddedWalletEmail.value = '';
  embeddedWalletCode.value = '';
  resetEmbeddedWalletMessages();
}

function selectWalletProvider(providerId, options = {}) {
  const preserveAuthInputs = options.preserveAuthInputs === true;
  selectedWalletProvider.value = providerId;
  if (!preserveAuthInputs || providerId !== 'privy_embedded') {
    showEmbeddedWalletForm.value = false;
  }
  if (!preserveAuthInputs) {
    embeddedWalletEmail.value = '';
    embeddedWalletCode.value = '';
  }
  resetEmbeddedWalletMessages();
}

async function changeWalletMethod() {
  clearPendingWalletAction();
  clearWalletMethodUi();
  if (wallet.state.isConnected || wallet.state.isVerifiedSession) {
    await wallet.disconnectWallet();
  }
}

function toggleEmbeddedWalletForm() {
  showEmbeddedWalletForm.value = !showEmbeddedWalletForm.value;
  if (showEmbeddedWalletForm.value) {
    resetEmbeddedWalletMessages();
  }
}

function setEntryMode(mode) {
  entryMode.value = mode === 'returning' ? 'returning' : 'new';
  clearWalletMethodUi();
}

function setNewUserMode(mode) {
  newUserMode.value = mode === 'request' ? 'request' : 'invite';
  clearWalletMethodUi();
}

const accessMode = computed(() => (entryMode.value === 'returning' ? 'returning' : 'login'));

const accessActionState = computed(() => getControlledAccessActionState({
  mode: accessMode.value,
  walletState: wallet.state,
  accessState: access.state,
  selectedProviderId: selectedWalletProvider.value,
}));

const walletStatusText = computed(() => getAccessGateWalletStatusText(wallet.state));

const walletNextStepText = computed(() => getControlledAccessNextStepText({
  mode: accessMode.value,
  walletState: wallet.state,
  accessState: access.state,
  selectedProviderId: selectedWalletProvider.value,
}));

const shouldShowWalletStatus = computed(
  () => !accessActionState.value.showProviderChooser && (wallet.state.isConnected || wallet.state.isVerifiedSession),
);

const showMetaMaskButton = computed(
  () => accessActionState.value.showProviderChooser
    || (accessActionState.value.showConnect && selectedWalletProvider.value === 'metamask'),
);

const showEmbeddedWalletConnectButton = computed(
  () => embeddedWalletAvailable.value
    && (
      accessActionState.value.showProviderChooser
      || (
        accessActionState.value.showConnect
        && selectedWalletProvider.value === 'privy_embedded'
        && !showEmbeddedWalletForm.value
      )
    ),
);

const showEmbeddedWalletUnavailableButton = computed(
  () => accessActionState.value.showProviderChooser && !embeddedWalletAvailable.value,
);

const shouldShowChangeWalletMethod = computed(
  () => !accessActionState.value.showProviderChooser
    && !access.state.me?.access_granted
    && (
      Boolean(selectedWalletProvider.value)
      || wallet.state.isConnected
      || wallet.state.isVerifiedSession
      || showEmbeddedWalletForm.value
    ),
);

const returningWalletGuidance = computed(() => buildReturningWalletGuidance({
  accessGranted: Boolean(access.state.me?.access_granted),
  walletBound: Boolean(access.state.me?.wallet_bound || access.state.me?.wallet_binding?.wallet_address),
  isVerifiedSession: wallet.state.isVerifiedSession,
  isConnected: wallet.state.isConnected,
}));

const walletAccountStatus = computed(
  () => String(access.state.me?.access_account?.status || '').trim().toLowerCase(),
);

const walletBindingStatus = computed(
  () => String(access.state.me?.wallet_binding?.status || '').trim().toLowerCase(),
);

const accessLabel = computed(
  () => access.state.publicStatus?.access_public_label || '',
);

const embeddedWalletOption = computed(
  () => wallet.state.availableWalletProviders.find((item) => item.provider_id === 'privy_embedded') || null,
);

const embeddedWalletAvailability = computed(
  () => embeddedWalletOption.value?.availability || 'coming_soon',
);

const embeddedWalletAvailable = computed(
  () => embeddedWalletAvailability.value === 'available',
);

const embeddedWalletTemporarilyUnavailable = computed(
  () => embeddedWalletAvailability.value === 'error',
);

const embeddedWalletUnavailableMessage = computed(
  () => embeddedWalletOption.value?.availability_message || '',
);

const embeddedWalletPublicMessage = computed(() => {
  if (embeddedWalletAvailable.value) {
    return '';
  }
  if (embeddedWalletTemporarilyUnavailable.value) {
    return 'Email / Social Wallet is temporarily unavailable. Continue with MetaMask for now.';
  }
  return 'Email / Social Wallet is coming soon.';
});

const embeddedWalletDiagnostics = computed(
  () => embeddedWalletOption.value?.diagnostics || null,
);

const embeddedWalletDiagnosticReasonLabel = computed(() => {
  switch (embeddedWalletDiagnostics.value?.unavailableReason) {
    case 'provider_disabled':
      return 'Provider disabled';
    case 'missing_app_id':
      return 'Missing public Privy app id';
    case 'low_level_sdk_interop_issue':
      return 'Low-level SDK interop issue';
    case 'sdk_import_failed':
      return 'SDK import failed';
    case 'origin_not_allowed':
      return 'Origin not allowed';
    case 'unsupported_browser':
      return 'Unsupported browser environment';
    case 'sdk_init_failed':
      return 'SDK initialization failed';
    case 'react_sdk_required':
      return 'Supported React SDK path not implemented yet';
    default:
      return 'Unknown';
  }
});

const shouldShowEmbeddedWalletDiagnostics = computed(
  () => developmentToolsEnabled
    && embeddedWalletAvailability.value !== 'available'
    && Boolean(embeddedWalletDiagnostics.value),
);

const embeddedWalletDisabledButtonLabel = computed(() => {
  if (embeddedWalletTemporarilyUnavailable.value) {
    return 'Email / Social Wallet Temporarily Unavailable';
  }
  return 'Email / Social Wallet Coming Soon';
});

const embeddedWalletConfiguredHelperText = computed(
  () => 'Use this if you are new to wallets. This creates or connects a portable beta wallet.',
);

const supportsEmbeddedSocialLogin = computed(
  () => EMBEDDED_WALLET_CONFIG.supportsSocialLogin,
);

const embeddedWalletSocialProviderLabel = computed(() => {
  const provider = String(EMBEDDED_WALLET_CONFIG.socialProvider || '').trim().toLowerCase();
  if (!provider) {
    return 'Google';
  }
  return provider.charAt(0).toUpperCase() + provider.slice(1);
});

const requestsEnabled = computed(
  () => access.state.publicStatus?.access_requests_enabled !== false,
);

const inviteAuthenticated = computed(
  () => accessActionState.value.inviteAuthenticated,
);

const inviteAcceptedMessage = computed(() => {
  if (!inviteAuthenticated.value || access.state.me?.wallet_bound) {
    return '';
  }
  return 'Invite accepted. Choose how to connect your wallet, verify it, and bind it once to finish setup.';
});

const returningStatusMessage = computed(() => {
  if (!wallet.state.isVerifiedSession) {
    return '';
  }
  if (walletBindingStatus.value === 'revoked') {
    return 'This wallet binding was revoked. Request access or enter a fresh invite code from the operator.';
  }
  if (walletAccountStatus.value === 'suspended') {
    return 'This approved wallet belongs to a suspended access account. Contact the operator for reactivation.';
  }
  if (walletAccountStatus.value === 'revoked') {
    return 'This approved wallet belongs to a revoked access account. Contact the operator before trying again.';
  }
  if (access.state.me?.access_granted) {
    return 'Approved wallet verified. Unlocking the controlled testnet now.';
  }
  if (access.state.me?.wallet_session_authenticated) {
    return 'This wallet is not approved. Request access or enter an invite code.';
  }
  return '';
});

const returningStatusClass = computed(() => {
  if (access.state.me?.access_granted) {
    return 'success';
  }
  return 'error';
});

const showRetryButton = computed(
  () => Boolean(pendingWalletAction.value) && !access.state.me?.access_granted,
);
const shouldShowEligibilityStatus = computed(
  () => Boolean(access.state.eligibility || access.state.me?.blocked_reason || access.state.me?.allowlist_override_applied),
);
const accessRuleChecks = computed(
  () => getEligibilityRuleChecks(access.state.eligibility, ['access']),
);
const failedAccessRuleChecks = computed(
  () => getFailedRequiredRuleChecks(access.state.eligibility, ['access']),
);
const primaryBlockedReason = computed(
  () => access.state.eligibility?.blocked_reasons?.find((item) => item.scope === 'access')?.message
    || failedAccessRuleChecks.value[0]?.description
    || '',
);
const nextSteps = computed(
  () => Array.isArray(access.state.eligibility?.possible_next_steps) ? access.state.eligibility.possible_next_steps : [],
);
const hasEligibilityDetails = computed(
  () => accessRuleChecks.value.length > 0 || nextSteps.value.length > 0,
);
const activeOverrideMessage = computed(() => {
  const accessOverride = (access.state.eligibility?.allowlist_overrides_applied || []).find((item) => item.scope === 'access');
  if (!accessOverride) {
    return '';
  }
  return `Admin approval is active for ${String(accessOverride.allowlist_scope || accessOverride.scope || 'this account').replace(/_/g, ' ')}.`;
});
const eligibilityHeadline = computed(() => {
  if (access.state.me?.access_granted) {
    return 'You are approved for the beta app.';
  }
  if (activeOverrideMessage.value) {
    return 'Admin approval is active for this session.';
  }
  if (walletAccountStatus.value === 'suspended') {
    return 'This account is currently suspended.';
  }
  if (walletBindingStatus.value === 'revoked') {
    return 'This wallet connection was revoked.';
  }
  if (wallet.state.isVerifiedSession) {
    return 'Your wallet is verified, but beta approval is still missing.';
  }
  return 'You may still need approval before this wallet can continue.';
});
const eligibilityTone = computed(() => (access.state.me?.access_granted || activeOverrideMessage.value ? 'success' : 'warning'));
const blockedSummaryCallToAction = computed(() => {
  if (access.state.me?.access_granted) {
    return '';
  }
  if (wallet.state.isVerifiedSession) {
    return 'Request access or use an invite code. More details are available in the Beta Guide.';
  }
  return 'Request access or use an invite code. More details are available in the Beta Guide.';
});
const canRequestOverride = computed(
  () => !access.state.me?.access_granted && Boolean(requestsEnabled.value || wallet.state.isVerifiedSession || inviteAuthenticated.value),
);

const shouldShowEmbeddedAuthPanel = computed(
  () => selectedWalletProvider.value === 'privy_embedded'
    && showEmbeddedWalletForm.value
    && embeddedWalletAvailable.value,
);

function logAccessFlow(step, payload = {}) {
  if (!developmentToolsEnabled) {
    return;
  }
  console.debug(`[ZoidbergChain][access] ${step}`, payload);
}

async function completeVerifiedWalletLogin(options = {}) {
  const {
    bindIfMissing = false,
    routeOnUnlock = true,
  } = options;

  if (!wallet.state.isVerifiedSession) {
    logAccessFlow('verified-wallet-session-missing', {
      providerId: wallet.state.providerId,
      isConnected: wallet.state.isConnected,
      isVerifiedSession: wallet.state.isVerifiedSession,
    });
    return {
      ok: false,
      shouldUnlock: false,
      reason: 'wallet_not_verified',
    };
  }

  const authHeaders = wallet.getAuthorizationHeader();
  logAccessFlow('verified-wallet-session-start', {
    providerId: wallet.state.providerId,
    walletAddress: wallet.state.normalizedWalletAddress || wallet.state.walletAddress,
    hasWalletSession: Boolean(authHeaders.Authorization),
  });

  const me = await access.refreshMe(authHeaders);
  logAccessFlow('/access/me response', {
    accessGranted: Boolean(access.state.me?.access_granted),
    inviteAuthenticated: Boolean(access.state.me?.invite_authenticated),
    walletBound: Boolean(access.state.me?.wallet_bound || access.state.me?.wallet_binding?.wallet_address),
    me,
  });

  await access.refreshEligibility(authHeaders);
  logAccessFlow('/eligibility/status response', {
    eligibility: access.state.eligibility,
  });

  const accessGranted = Boolean(access.state.me?.access_granted);
  const walletBound = Boolean(access.state.me?.wallet_bound || access.state.me?.wallet_binding?.wallet_address);
  const shouldUnlock = access.isAppUnlocked();
  logAccessFlow('unlock-decision', {
    providerId: wallet.state.providerId,
    accessGranted,
    walletBound,
    shouldUnlock,
    requireAccess: access.requiresAppAccess(),
  });

  if (bindIfMissing && access.state.me && access.state.me.invite_authenticated && !walletBound && !accessGranted) {
    logAccessFlow('bind-wallet-after-verification', {
      providerId: wallet.state.providerId,
      walletAddress: wallet.state.normalizedWalletAddress || wallet.state.walletAddress,
    });
    const bindResult = await access.bindWallet(authHeaders);
    if (bindResult) {
      await access.refreshMe(authHeaders);
      await access.refreshEligibility(authHeaders);
    }
  }

  if (shouldUnlock) {
    clearPendingWalletAction();
    if (routeOnUnlock) {
      emit('unlocked');
    }
  }

  return {
    ok: shouldUnlock,
    shouldUnlock,
    accessGranted,
    walletBound,
    me,
  };
}

async function refreshAccessAndUnlock() {
  return completeVerifiedWalletLogin({
    bindIfMissing: false,
    routeOnUnlock: true,
  });
}

async function connectWallet(providerId = 'metamask', options = {}) {
  refreshMobileWalletSupport();
  await wallet.detectWallets();
  refreshMobileWalletSupport();
  const result = await wallet.connectWallet({
    providerId,
    ...options,
  });
  refreshMobileWalletSupport();
  if (result && wallet.state.isVerifiedSession) {
    await refreshAccessAndUnlock();
  }
  return result;
}

async function connectMetaMaskWallet() {
  selectWalletProvider('metamask');
  if (wallet.state.providerId === 'metamask' && (wallet.state.isConnected || wallet.state.isVerifiedSession)) {
    clearPendingWalletAction();
    return;
  }
  await connectWallet('metamask');
}

async function sendEmbeddedWalletCode() {
  selectWalletProvider('privy_embedded', { preserveAuthInputs: true });
  if (!embeddedWalletEmail.value) {
    embeddedWalletError.value = 'Enter your email address first.';
    return;
  }
  isSendingEmbeddedWalletCode.value = true;
  resetEmbeddedWalletMessages();
  try {
    await wallet.sendEmbeddedWalletEmailCode(embeddedWalletEmail.value);
    embeddedWalletMessage.value = 'Verification code sent. Check your email, then enter the code below to connect your wallet.';
    showEmbeddedWalletForm.value = true;
  } catch (error) {
    embeddedWalletError.value = error?.message || 'Unable to send email code right now.';
  } finally {
    isSendingEmbeddedWalletCode.value = false;
  }
}

async function connectEmbeddedWalletWithCode() {
  selectWalletProvider('privy_embedded', { preserveAuthInputs: true });
  if (!embeddedWalletEmail.value || !embeddedWalletCode.value) {
    embeddedWalletError.value = 'Enter both your email address and verification code.';
    return;
  }
  isConnectingEmbeddedWallet.value = true;
  resetEmbeddedWalletMessages();
  try {
    const result = await connectWallet('privy_embedded', {
      authMethod: 'email',
      email: embeddedWalletEmail.value,
      code: embeddedWalletCode.value,
    });
    if (!result) {
      embeddedWalletError.value = 'Email wallet connection did not complete. Try requesting a fresh code.';
      return;
    }
    embeddedWalletMessage.value = 'Embedded wallet connected. Sign the wallet verification message to continue.';
  } catch (error) {
    embeddedWalletError.value = error?.message || 'Unable to connect the embedded wallet right now.';
  } finally {
    isConnectingEmbeddedWallet.value = false;
  }
}

async function connectEmbeddedWalletFromExistingSession() {
  selectWalletProvider('privy_embedded');
  isConnectingEmbeddedWallet.value = true;
  resetEmbeddedWalletMessages();
  try {
    if (wallet.state.providerId === 'privy_embedded' && (wallet.state.isConnected || wallet.state.isVerifiedSession)) {
      clearPendingWalletAction();
      embeddedWalletMessage.value = 'Embedded wallet connected. Sign the wallet verification message to continue.';
      return;
    }
    const result = await connectWallet('privy_embedded', {
      authMethod: 'restore',
    });
    if (!result) {
      embeddedWalletError.value = 'Email / Social Wallet is temporarily unavailable. Continue with MetaMask or try again later.';
      return;
    }
    embeddedWalletMessage.value = 'Embedded wallet connected. Sign the wallet verification message to continue.';
  } catch (error) {
    embeddedWalletError.value = error?.message || 'Unable to reconnect the embedded wallet right now.';
  } finally {
    isConnectingEmbeddedWallet.value = false;
  }
}

async function startEmbeddedWalletSocialLogin() {
  selectWalletProvider('privy_embedded', { preserveAuthInputs: true });
  resetEmbeddedWalletMessages();
  setPendingWalletAction(
    'verify_wallet',
    'Embedded wallet login was interrupted. Return to this page and continue with the same email or social wallet.',
  );
  try {
    await wallet.startEmbeddedWalletOAuthLogin(EMBEDDED_WALLET_CONFIG.socialProvider);
  } catch (error) {
    embeddedWalletError.value = error?.message || 'Unable to start social wallet login right now.';
  }
}

async function verifyWallet() {
  const providerId = selectedWalletProvider.value || wallet.state.providerId || 'metamask';
  setPendingWalletAction(
    'verify_wallet',
    'Wallet verification was interrupted. Reconnect the same approved wallet and try the signature again.',
  );
  const result = await wallet.verifyWallet({ providerId });
  if (result && wallet.state.isVerifiedSession) {
    await completeVerifiedWalletLogin({ bindIfMissing: false });
  }
}

async function bindWallet() {
  setPendingWalletAction(
    'bind_wallet',
    'Wallet binding was interrupted. Return to this page, verify the same wallet again if needed, then retry binding.',
  );
  const authHeaders = wallet.getAuthorizationHeader();
  const result = await access.bindWallet(authHeaders);
  if (result) {
    await completeVerifiedWalletLogin({ bindIfMissing: false });
  }
}

async function login() {
  const result = await access.loginWithCode(inviteCode.value);
  if (result) {
    inviteCode.value = '';
    clearPendingWalletAction();
    clearWalletMethodUi();
    if (wallet.state.isConnected || wallet.state.isVerifiedSession) {
      await wallet.disconnectWallet();
    }
    persistGateState();
  }
}

async function continueReturningFlow() {
  if (!wallet.state.isConnected) {
    await connectWallet();
    return;
  }
  if (!wallet.state.isVerifiedSession) {
    await verifyWallet();
    return;
  }
  await refreshAccessAndUnlock();
}

async function refreshReturningAccess() {
  await refreshAccessAndUnlock();
}

async function retryPendingWalletAction() {
  const action = pendingWalletAction.value;
  clearPendingWalletAction();
  if (action === 'bind_wallet' && accessActionState.value.showBind) {
    await bindWallet();
    return;
  }
  await changeWalletMethod();
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

async function submitOverride() {
  const result = await access.submitOverrideRequest(
    {
      ...overrideForm.value,
      wallet_address: wallet.state.verifiedWalletAddress || null,
      access_account_id: access.state.me?.access_account_id || access.state.me?.access_account?.access_account_id || null,
      current_page: '/access',
      detected_blocked_reason: access.state.eligibility?.blocked_reasons?.[0]?.reason || access.state.me?.blocked_reason || null,
    },
    wallet.getAuthorizationHeader(),
  );
  if (result) {
    overrideForm.value = {
      requested_scope: 'access',
      name: '',
      email: '',
      handle: '',
      reason: '',
    };
    showOverrideForm.value = false;
  }
}

watch([entryMode, newUserMode, inviteCode, pendingWalletAction, interruptedWalletMessage], () => {
  persistGateState();
});

watch(
  () => access.state.me?.access_granted,
  (accessGranted) => {
    if (accessGranted) {
      clearPendingWalletAction();
    }
  },
);

onMounted(() => {
  restoreGateState();
  refreshMobileWalletSupport();
});
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
  width: min(1160px, 100%);
  margin: 0 auto;
  padding: 30px 32px;
  border-radius: 24px;
  border: 1px solid rgba(255, 205, 115, 0.22);
  background: rgba(8, 12, 20, 0.92);
  color: #f7f0de;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.35);
}

.access-hero-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.45fr) minmax(320px, 0.95fr);
  gap: 24px;
  align-items: start;
  margin-bottom: 24px;
}

.access-intro-panel {
  display: grid;
  gap: 0;
  align-content: start;
}

.active-flow-shell {
  display: grid;
  gap: 16px;
  margin-top: 16px;
}

.eyebrow,
.section-label {
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

.hero-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.beta-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 8px 12px;
  border-radius: 999px;
  background: rgba(255, 205, 115, 0.12);
  border: 1px solid rgba(255, 205, 115, 0.22);
  color: #ffcd73;
  font-size: 0.82rem;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

h1,
h2 {
  margin: 0 0 12px;
  line-height: 1.1;
}

h1 {
  font-size: 2rem;
}

h2 {
  font-size: 1.35rem;
}

.lead,
.wallet-note,
.mobile-open-note {
  color: #dfd7c6;
  line-height: 1.6;
}

.lead {
  margin: 0 0 22px;
}

.journey-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin: 0 0 20px;
}

.access-paths {
  margin-bottom: 10px;
}

.responsive-access-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.onboarding-grid {
  margin: 4px 0 0;
}

.compact-options {
  margin-bottom: 0;
}

.responsive-wallet-grid {
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
}

.journey-card {
  padding: 16px;
  border-radius: 18px;
  border: 1px solid rgba(159, 211, 255, 0.16);
  background: rgba(159, 211, 255, 0.06);
  display: grid;
  gap: 8px;
}

.journey-card strong {
  color: #f7f0de;
}

.compact-copy {
  min-height: 0;
}

.diagnostic-panel {
  margin-top: 12px;
  padding: 12px 14px;
  border-radius: 14px;
  border: 1px solid rgba(159, 211, 255, 0.2);
  background: rgba(9, 16, 28, 0.72);
}

.diagnostic-panel summary {
  cursor: pointer;
  color: #9fd3ff;
  font-weight: 600;
}

.diagnostic-list {
  margin: 10px 0 0 18px;
  color: #d7deef;
  line-height: 1.5;
}

.feedback-shortcut {
  text-decoration: none;
  text-align: center;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 52px;
}

.main-access-card {
  display: grid;
  gap: 10px;
  align-content: start;
}

.card-aside {
  max-width: 220px;
  text-align: right;
}

.eligibility-checklist {
  display: grid;
  gap: 12px;
  margin: 14px 0;
}

.eligibility-rule {
  padding: 12px;
  border-radius: 14px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.03);
}

.eligibility-rule.pass {
  border-color: rgba(114, 224, 153, 0.3);
}

.eligibility-rule.fail {
  border-color: rgba(255, 145, 117, 0.35);
}

.eligibility-rule-value {
  overflow-wrap: anywhere;
  word-break: break-word;
}

.entry-switch,
.mode-switch,
.wallet-actions {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.entry-switch,
.mode-switch {
  margin-bottom: 18px;
}

.entry-switch {
  justify-content: flex-start;
  margin-top: 10px;
}

.entry-btn,
.mode-btn,
.primary-btn,
.secondary-btn,
.ghost-btn,
.meta-mask-link {
  border: none;
  border-radius: 14px;
  padding: 12px 16px;
  font: inherit;
  cursor: pointer;
  text-decoration: none;
}

.entry-btn,
.mode-btn,
.ghost-btn {
  background: rgba(255, 255, 255, 0.07);
  color: #f7f0de;
}

.entry-btn.active,
.mode-btn.active {
  background: #ffcd73;
  color: #20150a;
}

.primary-btn {
  background: linear-gradient(135deg, #ffcd73 0%, #ff8f5a 100%);
  color: #20150a;
  font-weight: 700;
}

.secondary-btn,
.meta-mask-link {
  background: rgba(116, 192, 252, 0.12);
  color: #d8ecff;
  border: 1px solid rgba(116, 192, 252, 0.18);
}

.ghost-btn {
  border: 1px solid rgba(255, 205, 115, 0.18);
}

.panel-stack {
  display: grid;
  gap: 16px;
}

.flow-panel {
  padding: 20px;
  border-radius: 18px;
  border: 1px solid rgba(255, 205, 115, 0.14);
  background: rgba(255, 255, 255, 0.04);
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
  min-height: 48px;
  border: 1px solid rgba(255, 205, 115, 0.18);
  border-radius: 14px;
  padding: 12px 14px;
  background: rgba(255, 255, 255, 0.04);
  color: #f7f0de;
  font: inherit;
}

.field textarea {
  min-height: 112px;
  resize: vertical;
}

.wallet-box,
.returning-panel,
.mobile-open-card,
.rules-panel {
  padding: 20px;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.04);
}

.returning-panel,
.mobile-open-card,
.rules-panel {
  border: 1px solid rgba(255, 205, 115, 0.14);
}

.rules-list {
  margin: 12px 0 0 18px;
  color: #dfd7c6;
  line-height: 1.6;
}

.card-heading-inline {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}

.helper-links-inline {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  align-items: stretch;
}

.field-select {
  width: 100%;
  min-height: 48px;
  border: 1px solid rgba(255, 205, 115, 0.18);
  border-radius: 14px;
  padding: 12px 14px;
  background: rgba(255, 255, 255, 0.04);
  color: #f7f0de;
  font: inherit;
}

.mobile-open-card {
  display: grid;
  gap: 12px;
  margin-bottom: 18px;
}

.meta-mask-link {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: fit-content;
}

.mini-help {
  flex: 1 1 220px;
  padding: 0;
  border-radius: 14px;
  border: 1px solid rgba(255, 205, 115, 0.18);
  background: rgba(255, 205, 115, 0.05);
  overflow: hidden;
}

.mini-help summary {
  cursor: pointer;
  color: #f7f0de;
  font-weight: 600;
  list-style: none;
  display: flex;
  align-items: center;
  width: 100%;
  min-height: 40px;
  padding: 10px 14px;
}

.mini-help[open] {
  padding-bottom: 14px;
}

.mini-help[open] summary {
  margin-bottom: 10px;
}

.mini-help > :not(summary) {
  padding-inline: 14px;
}

.mini-help summary:focus-visible {
  outline: 2px solid rgba(159, 211, 255, 0.9);
  outline-offset: -2px;
}

.mini-help .wallet-note + .wallet-note {
  margin-top: 8px;
}

.top-help {
  margin-top: 0;
}

.compact-help-status {
  margin-top: 4px;
}

.compact-help-panel {
  margin-top: 10px;
}

.compact-help-button {
  margin-top: 10px;
}

.compact-help-form {
  margin-top: 12px;
}

.disclaimer-row {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin-top: 12px;
  padding-top: 16px;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
}

.wallet-line,
.wallet-note,
.status {
  margin: 0;
}

.status {
  line-height: 1.5;
}

.status + .status {
  margin-top: 12px;
}

.status.success {
  color: #9df3b0;
}

.status.error {
  color: #ff9f9f;
}

.status.warning {
  color: #ffd884;
}

.status.info {
  color: #9fd3ff;
}

@media (max-width: 1024px) {
  .access-card {
    padding: 24px;
  }

  .access-hero-grid {
    grid-template-columns: minmax(0, 1fr);
    gap: 18px;
  }

  .responsive-wallet-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 720px) {
  .access-shell {
    padding: 22px 12px 34px;
  }

  .access-card {
    padding: 20px 16px;
    border-radius: 20px;
  }

  .flow-panel,
  .wallet-box,
  .returning-panel,
  .mobile-open-card,
  .rules-panel {
    padding: 16px;
  }

  .hero-heading {
    align-items: flex-start;
    flex-direction: column;
  }

  h1 {
    font-size: 1.65rem;
  }

  h2 {
    font-size: 1.18rem;
  }

  .entry-switch,
  .mode-switch,
  .wallet-actions,
  .journey-grid,
  .helper-links-inline,
  .disclaimer-row {
    display: grid;
    grid-template-columns: minmax(0, 1fr);
  }

  .responsive-access-grid,
  .responsive-wallet-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .entry-btn,
  .mode-btn,
  .primary-btn,
  .secondary-btn,
  .ghost-btn,
  .meta-mask-link {
    width: 100%;
    text-align: center;
  }

  .meta-mask-link {
    justify-content: center;
  }

  .card-aside {
    max-width: none;
    text-align: left;
  }
}

@media (max-width: 430px) {
  .access-shell {
    padding-inline: 10px;
  }

  .access-card {
    padding: 18px 14px;
  }

  .eyebrow,
  .section-label {
    font-size: 0.76rem;
    letter-spacing: 0.14em;
  }

  .lead,
  .wallet-note,
  .mobile-open-note,
  .status {
    font-size: 0.95rem;
  }
}
</style>
