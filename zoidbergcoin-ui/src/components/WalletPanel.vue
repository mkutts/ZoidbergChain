<template>
  <section class="wallet-panel">
    <div class="wallet-copy">
      <p class="wallet-label">Wallet And Test ZOID</p>
      <h2>Your ZoidbergChain beta wallet</h2>
      <p class="wallet-note">
        Your verified wallet proves who you are and signs actions in the beta. Test ZOID lives inside ZoidbergChain, settles in meme-mined blocks, and does not appear in normal wallet apps yet.
      </p>
      <p class="wallet-note">
        MetaMask remains the only live beta login today. Email / Social Wallet onboarding is planned next through a supported Privy integration path, and every wallet path still has to preserve portable wallet control before any mainnet-value use.
      </p>
      <p v-if="showPublicDemoNotice" class="wallet-demo-note">
        Controlled testnet. Test ZOID has no real monetary value, this network may reset, and it is not mainnet.
      </p>
      <div class="wallet-actions wallet-feedback-actions">
        <button type="button" class="wallet-btn secondary compact feedback-link" @click="openFeedbackPanel">Send Feedback</button>
      </div>
    </div>

    <div class="wallet-card" :class="{ connected: wallet.state.isConnected }">
      <p class="wallet-status">
        <span class="status-badge" :class="statusClass">{{ statusText }}</span>
      </p>

      <template v-if="wallet.state.isConnected">
        <p class="address-short">{{ shortenedAddress }}</p>
        <p class="address-full">{{ wallet.state.normalizedWalletAddress }}</p>
        <p v-if="wallet.state.isVerifiedSession" class="wallet-meta">Wallet verified. You can now use this wallet for submissions, voting, rewards, and test ZOID transfers.</p>
        <p v-else-if="wallet.state.connectionStatus === 'expired'" class="wallet-meta">This wallet was connected before, but verification expired or changed. Verify again to keep using the beta app.</p>
        <p v-else class="wallet-meta">Wallet connected. Verify it to unlock signing and other beta actions.</p>
        <p v-if="wallet.state.chainId" class="wallet-meta">Chain ID: {{ wallet.state.chainId }}</p>
        <p v-if="wallet.state.sessionExpiresAt && wallet.state.isVerifiedSession" class="wallet-meta">
          Verification expires at: {{ sessionExpiryLabel }}
        </p>

        <div v-if="showAccessStatusCard" class="access-card">
          <span class="native-balance-label">Beta Access</span>
          <strong :class="accessStatusClass">{{ accessStatusHeadline }}</strong>
          <p class="wallet-meta">{{ accessStatusDetail }}</p>
          <p v-if="accessAccountLine" class="wallet-meta">{{ accessAccountLine }}</p>
          <p v-if="walletBindingLine" class="wallet-meta">{{ walletBindingLine }}</p>
          <p v-if="eligibilityBlockedReason" class="wallet-meta wallet-warning">{{ eligibilityBlockedReason }}</p>
          <div v-if="accessRuleChecks.length" class="eligibility-checklist">
            <div
              v-for="rule in accessRuleChecks"
              :key="`${rule.scope}-${rule.rule_id}`"
              class="eligibility-rule"
              :class="{ pass: rule.passed, fail: rule.required && !rule.passed }"
            >
              <strong>{{ rule.label }}</strong>
              <p class="wallet-meta">{{ rule.description }}</p>
              <p class="wallet-meta eligibility-rule-value">
                Current: {{ rule.current_value ?? 'Not available' }}
                <span v-if="rule.required_value !== null && rule.required_value !== undefined"> | Needed: {{ rule.required_value }}</span>
              </p>
            </div>
          </div>
          <p v-if="eligibilityOverrideMessage" class="wallet-meta transfer-success">{{ eligibilityOverrideMessage }}</p>
          <p v-for="step in eligibilityNextSteps" :key="step" class="wallet-meta">{{ step }}</p>
          <div v-if="showWalletOverrideTools" class="wallet-actions">
            <button type="button" class="wallet-btn secondary compact" @click="showOverrideForm = !showOverrideForm">
              {{ showOverrideForm ? 'Hide Beta Help Form' : 'Request Beta Help' }}
            </button>
          </div>
          <form v-if="showOverrideForm" class="override-form" @submit.prevent="submitEligibilityOverride">
            <label class="transfer-field">
              <span>Requested Scope</span>
              <select v-model="overrideForm.requested_scope">
                <option value="review">Review Access</option>
                <option value="voting">Voting Access</option>
                <option value="rewards">Rewards Access</option>
                <option value="all_beta">Full Beta Access</option>
              </select>
            </label>
            <label class="transfer-field">
              <span>What Is Blocked?</span>
              <textarea v-model="overrideForm.reason" rows="3" placeholder="Explain what you were trying to do and what should have happened." />
            </label>
            <button type="submit" class="wallet-btn primary compact" :disabled="access.state.isSubmittingOverrideRequest || !overrideForm.reason">
              {{ access.state.isSubmittingOverrideRequest ? 'Sending Beta Help Request...' : 'Send Beta Help Request' }}
            </button>
          </form>
          <p v-if="access.state.errorMessage" class="wallet-error">{{ access.state.errorMessage }}</p>
        </div>

        <div v-if="wallet.state.isVerifiedSession" class="native-balance-card">
          <span class="native-balance-label">Final balance</span>
          <strong class="native-balance-value">{{ nativeBalanceLabel }}</strong>
          <div v-if="balanceSummaryRows.length" class="wallet-summary-list">
            <div v-for="row in balanceSummaryRows" :key="row.label" class="wallet-summary-row">
              <span>{{ row.label }}</span>
              <strong>{{ row.value }}</strong>
            </div>
          </div>
          <p class="wallet-meta">Native ZOID does not appear in normal wallet apps yet.</p>
          <p class="wallet-meta">{{ balanceNote }}</p>
        </div>

        <div v-if="wallet.state.isVerifiedSession" class="reward-card">
          <div class="history-header">
            <span class="native-balance-label">Wallet Activity</span>
            <button
              type="button"
              class="wallet-btn secondary compact"
              @click="refreshAccountData"
              :disabled="isBalanceLoading || isRewardHistoryLoading || isTransferHistoryLoading"
            >
              {{ isBalanceLoading || isRewardHistoryLoading || isTransferHistoryLoading ? 'Refreshing Wallet...' : 'Refresh Wallet Data' }}
            </button>
          </div>
          <div v-if="accountSummaryRows.length" class="wallet-summary-list">
            <div v-for="row in accountSummaryRows" :key="row.label" class="wallet-summary-row">
              <span>{{ row.label }}</span>
              <strong>{{ row.value }}</strong>
            </div>
          </div>
          <p class="wallet-meta">
            Your verified wallet becomes your ZoidbergChain beta identity as soon as it submits, votes, receives rewards, or holds balance.
          </p>
        </div>

        <div v-if="wallet.state.isVerifiedSession" class="reward-card">
          <div class="history-header">
            <span class="native-balance-label">Rewards</span>
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
          <p v-else-if="!rewardHistory.length" class="wallet-meta">No rewards yet. Vote on originality and check back after final decisions settle.</p>
          <template v-else>
            <p class="wallet-meta">Voter rewards are testnet ZOID only and go only to voters on the final majority side.</p>
            <ul class="history-list">
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
          </template>
        </div>

        <div class="transfer-card">
          <span class="native-balance-label">Send Test ZOID</span>
          <template v-if="wallet.state.isVerifiedSession">
            <p class="wallet-meta">{{ transferWarning }}</p>
            <p class="wallet-meta">Pending transfers can affect your available balance before final settlement.</p>
            <p class="wallet-meta">Current next transfer number: <strong>{{ nextTransferNonceLabel }}</strong></p>
            <label class="transfer-field">
              <span>From Wallet</span>
              <input :value="wallet.state.verifiedWalletAddress" type="text" readonly />
            </label>
            <label class="transfer-field">
              <span>To Wallet</span>
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
                {{ isTransferSubmitting ? 'Signing Transfer...' : 'Sign Test ZOID Transfer' }}
              </button>
              <button
                type="button"
                class="wallet-btn secondary"
                @click="refreshTransferHistory"
                :disabled="isTransferHistoryLoading"
              >
                {{ isTransferHistoryLoading ? 'Refreshing Transfers...' : 'Refresh Transfers' }}
              </button>
            </div>
            <p v-if="transferSuccessMessage" class="wallet-meta transfer-success">{{ transferSuccessMessage }}</p>
            <p v-if="transferError" class="wallet-error">{{ transferError }}</p>
            <div class="transfer-history">
              <p class="wallet-meta transfer-history-title">Recent transfers</p>
              <p v-if="!transferHistory.length" class="wallet-meta">No transfers yet. Send a small amount of test ZOID to start your activity history.</p>
              <template v-else>
                <p class="wallet-meta">Pending transfers are not final yet. Settled transfers show the block that confirmed them.</p>
                <ul class="history-list">
                  <li v-for="transfer in transferHistory" :key="transfer.tx_id || transfer.transfer_id" class="history-card">
                    <div class="history-title-row">
                      <strong>{{ transferStatusLabel(transfer.status) }}</strong>
                      <span>{{ transferDirection(transfer) }}</span>
                    </div>
                    <div class="history-grid">
                      <div>
                        <span>Tx ID</span>
                        <strong>{{ shortenTransferId(transfer.tx_id || transfer.transfer_id) }}</strong>
                      </div>
                      <div>
                        <span>Status</span>
                        <strong>{{ transferStatusLabel(transfer.status) }}</strong>
                      </div>
                      <div>
                        <span>From Wallet</span>
                        <strong>{{ wallet.shortenAddress(transfer.from_address) }}</strong>
                      </div>
                      <div>
                        <span>To Wallet</span>
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
                        <span>Nonce</span>
                        <strong>{{ transfer.nonce || transfer.transfer_nonce || 'Missing' }}</strong>
                      </div>
                      <div>
                        <span>Created At</span>
                        <strong>{{ formatDateTime(transfer.created_at || transferTimestamp(transfer)) || 'Unknown time' }}</strong>
                      </div>
                      <div v-if="showDevTransferTools">
                        <span>Admitted At</span>
                        <strong>{{ formatDateTime(transfer.admitted_at) || 'Not admitted' }}</strong>
                      </div>
                      <div>
                        <span>Included Block Height</span>
                        <strong>{{ transfer.included_block_height ?? 'Pending' }}</strong>
                      </div>
                      <div>
                        <span>Included Block Hash</span>
                        <strong>{{ formatHistoryValue(transfer.included_block_hash) }}</strong>
                      </div>
                      <div>
                        <span>Settled At</span>
                        <strong>{{ formatDateTime(transfer.settled_at) || 'Not settled' }}</strong>
                      </div>
                    </div>
                    <p v-if="transfer.memo" class="wallet-meta history-note">Memo: {{ transfer.memo }}</p>
                    <p v-if="transfer.rejection_reason" class="wallet-meta history-note">Rejection reason: {{ transfer.rejection_reason }}</p>
                    <p v-if="transfer.status_detail" class="wallet-meta history-note">{{ transfer.status_detail }}</p>
                    <div v-if="showDevTransferTools && transfer.status === 'signed_pending' && transfer.tx_id" class="wallet-actions">
                      <button
                        type="button"
                        class="wallet-btn secondary"
                        @click="admitTransferToMempool(transfer)"
                        :disabled="isMempoolSubmitting"
                      >
                        {{ isMempoolSubmitting ? 'Admitting...' : 'Admit to Mempool' }}
                      </button>
                    </div>
                    <p v-if="transfer.status === 'signed_pending'" class="wallet-meta history-note">This transfer is signed and pending. It can reduce available balance before the final block settlement appears.</p>
                  </li>
                </ul>
              </template>
            </div>
            <div v-if="showDevTransferTools" class="transfer-history">
              <p class="wallet-meta transfer-history-title">Local pending queue</p>
              <p v-if="!mempoolTransactions.length" class="wallet-meta">No local mempool transactions.</p>
              <template v-else>
                <p class="wallet-meta">The mempool is local to this node. Transactions settle only when included in an accepted meme-mined block.</p>
                <ul class="history-list">
                  <li v-for="transaction in mempoolTransactions" :key="transaction.tx_id" class="history-card">
                    <div class="history-title-row">
                      <strong>{{ transferStatusLabel(transaction.status) }}</strong>
                      <span>{{ transferDirection(transaction) }}</span>
                    </div>
                    <div class="history-grid">
                      <div>
                        <span>Tx ID</span>
                        <strong>{{ shortenTransferId(transaction.tx_id) }}</strong>
                      </div>
                      <div>
                        <span>Status</span>
                        <strong>{{ transferStatusLabel(transaction.status) }}</strong>
                      </div>
                      <div>
                        <span>From Wallet</span>
                        <strong>{{ wallet.shortenAddress(transaction.from_address) }}</strong>
                      </div>
                      <div>
                        <span>To Wallet</span>
                        <strong>{{ wallet.shortenAddress(transaction.to_address) }}</strong>
                      </div>
                      <div>
                        <span>Amount</span>
                        <strong>{{ transaction.amount }} {{ nativeBalanceSymbol }}</strong>
                      </div>
                      <div>
                        <span>Nonce</span>
                        <strong>{{ transaction.nonce || 'Missing' }}</strong>
                      </div>
                      <div>
                        <span>Admitted At</span>
                        <strong>{{ formatDateTime(transaction.admitted_at) || 'Unknown time' }}</strong>
                      </div>
                    </div>
                  </li>
                </ul>
              </template>
            </div>
          </template>
          <template v-else-if="wallet.state.isConnected">
            <p class="wallet-meta">Verify this wallet before sending test ZOID.</p>
          </template>
          <template v-else>
            <p class="wallet-meta">Connect a wallet first, then verify it to send test ZOID.</p>
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
          Your connected wallet provider signs ZoidbergChain actions. Native ZOID balances live in the ZoidbergChain app, not in the old development-only server wallet list.
        </p>
        <p v-if="wallet.state.lastConnectedAddress" class="wallet-meta">
          Last connected address: {{ wallet.shortenAddress(wallet.state.lastConnectedAddress) }}
        </p>
        <p v-if="mobileWalletSupport.helperText" class="wallet-meta wallet-mobile-note">
          {{ mobileWalletSupport.helperText }}
        </p>
        <p v-if="!wallet.state.isWalletProviderAvailable && !wallet.state.availableWalletProviders.find((item) => item.availability === 'available')" class="wallet-warning">
          {{ mobileWalletSupport.noProviderMessage || 'No wallet provider was detected in this browser yet.' }}
        </p>
        <div class="wallet-actions">
          <button
            type="button"
            class="wallet-btn primary"
            @click="connect"
            :disabled="wallet.state.connectionStatus === 'connecting' || !wallet.state.isWalletProviderAvailable"
          >
            {{ wallet.state.connectionStatus === 'connecting' ? 'Connecting...' : `Continue with ${wallet.state.providerLabel || 'Wallet'}` }}
          </button>
          <a
            v-if="mobileWalletSupport.shouldShowOpenInMetaMask && wallet.state.providerId === 'metamask'"
            :href="mobileWalletSupport.openInMetaMaskUrl"
            class="wallet-btn secondary wallet-link-btn"
          >
            Open in MetaMask
          </a>
        </div>
        <div v-if="wallet.state.portabilityHelpCopy" class="access-card">
          <span class="native-balance-label">Wallet Portability</span>
          <p class="wallet-meta">{{ wallet.state.portabilityHelpCopy }}</p>
          <p v-if="wallet.state.portabilityHelpUrl" class="wallet-meta">
            Help: <a :href="wallet.state.portabilityHelpUrl" target="_blank" rel="noreferrer">Export and portability guidance</a>
          </p>
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
import { useAccess } from '../services/access';
import { apiClient, getApiErrorMessage } from '../config/api';
import { createNativeTransferService, TRANSFER_PENDING_WARNING } from '../services/nativeTransfer.js';
import {
  buildNativeBalanceSummary,
  buildRewardSummary,
  describeTransferIntentDirection,
  describeTransferIntentStatus,
  formatTransferIntentTimestamp,
  humanizeNativeTransferError,
} from '../utils/nativeWalletUi.js';
import {
  getEligibilityRuleChecks,
  getFailedRequiredRuleChecks,
} from '../utils/eligibilityChecklist.js';
import { describeWalletSupport } from '../utils/mobileWallet.js';
import { isPublicDemoMode, showDevelopmentTools } from '../utils/runtimeConfig';
import { requestFeedbackPanelOpen } from '../utils/feedbackPanel.js';

const wallet = useWallet();
const access = useAccess();
const showPublicDemoNotice = isPublicDemoMode();
const showDevTransferTools = showDevelopmentTools();
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
const nonceState = ref(null);
const mempoolTransactions = ref([]);
const isMempoolLoading = ref(false);
const isMempoolSubmitting = ref(false);
const transferForm = ref({
  toAddress: '',
  amount: '',
  memo: '',
});
const transferService = createNativeTransferService({
  api: apiClient,
  getApiErrorMessage,
  signMessage: (message, walletAddress) => wallet.requestSignature(message, walletAddress),
});
const mobileWalletSupport = ref({
  isMobileDevice: false,
  hasInjectedProvider: false,
  isMetaMaskMobileBrowser: false,
  helperText: '',
  noProviderMessage: '',
  openInMetaMaskUrl: '',
  shouldShowOpenInMetaMask: false,
});
const showOverrideForm = ref(false);
const overrideForm = ref({
  requested_scope: 'review',
  reason: '',
});

function openFeedbackPanel() {
  requestFeedbackPanelOpen({ panelId: 'feedback-panel' });
}

const shortenedAddress = computed(() => wallet.shortenAddress(wallet.state.walletAddress));
const transferWarning = computed(() => TRANSFER_PENDING_WARNING);
const nativeBalanceSymbol = computed(() => accountSummary.value?.symbol || 'ZOID');
const nextTransferNonceLabel = computed(() => nonceState.value?.next_nonce ?? accountSummary.value?.nonce?.next_nonce ?? '--');
const balanceSummaryRows = computed(() => buildNativeBalanceSummary({
  final_balance: accountSummary.value?.final_balance,
  native_balance: accountSummary.value?.native_balance,
  pending_outgoing: accountSummary.value?.pending_outgoing,
  pending_incoming: accountSummary.value?.pending_incoming,
  available_balance: accountSummary.value?.available_balance,
  symbol: nativeBalanceSymbol.value,
}));
const accountSummaryRows = computed(() => {
  const summary = accountSummary.value || {};
  return [
    { label: 'Native Account Type', value: summary.account_type === 'metamask_native' ? 'MetaMask-backed ZoidbergChain account' : 'Unknown' },
    { label: 'Network', value: summary.network_name || 'Unknown' },
    { label: 'Verified Session', value: wallet.state.isVerifiedSession ? 'Verified' : 'Not verified' },
    { label: 'Submissions', value: summary.submission_count ?? 0 },
    { label: 'Votes', value: summary.vote_count ?? 0 },
    { label: 'Rewards', value: summary.reward_count ?? 0 },
    { label: 'Pending Transactions', value: summary.pending_transaction_count ?? 0 },
    { label: 'Settled Transactions', value: summary.settled_transaction_count ?? 0 },
    { label: 'Next Transfer Nonce', value: nextTransferNonceLabel.value },
  ];
});
const nativeBalanceLabel = computed(() => {
  const balance = accountSummary.value?.final_balance ?? accountSummary.value?.native_balance;
  if (balance === null || balance === undefined || balance === '') {
    return '--';
  }
  return `${balance} ${nativeBalanceSymbol.value}`;
});
const balanceNote = computed(() => (
  accountSummary.value?.note
  || 'Pending outgoing transfers reduce available balance. Final balance changes only when a transfer is settled in a meme-mined block.'
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

const showAccessStatusCard = computed(() => {
  const status = access.state.publicStatus;
  const me = access.state.me;
  return Boolean(
    status?.require_access_for_app
    || status?.require_access_for_submissions
    || status?.require_access_for_votes
    || status?.require_access_for_rewards
    || status?.require_access_for_transfers
    || me?.access_account
    || me?.wallet_binding
  );
});

const accessStatusHeadline = computed(() => {
  if (access.state.me?.access_granted) {
    return 'Beta access is active';
  }
  if (access.state.me?.access_account && !access.state.me?.wallet_binding) {
    return 'Invite accepted. Finish wallet setup to unlock the beta app.';
  }
  if (wallet.state.isVerifiedSession) {
    return 'This verified wallet is not fully approved yet.';
  }
  if (access.requiresAppAccess()) {
    return 'This beta currently requires approval.';
  }
  return 'Open local testing is available on this node.';
});

const accessStatusClass = computed(() => {
  if (access.state.me?.access_granted) {
    return 'access-success';
  }
  if (access.requiresAppAccess() || wallet.state.isVerifiedSession) {
    return 'access-warning';
  }
  return 'access-neutral';
});

const accessStatusDetail = computed(() => {
  const status = access.state.publicStatus || {};
  if (access.state.me?.access_granted) {
    return 'This wallet can use the beta app while access stays active and the verification session remains current. Voting and rewards can still have separate approval rules.';
  }
  if (access.state.me?.access_account && !access.state.me?.wallet_binding) {
    return 'Your invite was accepted, but you still need to bind the first verified wallet to finish setup.';
  }
  if (wallet.state.isVerifiedSession) {
    return 'Some actions can still stay blocked until this wallet is approved and linked to an active beta account.';
  }
  if (status.access_dev_bypass_enabled) {
    return 'This local node is open for development testing right now.';
  }
  return 'This node can require approval before submissions, votes, rewards, or transfers are allowed.';
});

const accessAccountLine = computed(() => {
  const account = access.state.me?.access_account;
  if (!account) {
    return '';
  }
  const status = String(account.status || 'unknown').replace(/_/g, ' ');
  return `Approved account: ${account.email || account.name || account.access_account_id} (${status}).`;
});

const walletBindingLine = computed(() => {
  const binding = access.state.me?.wallet_binding;
  if (!binding?.wallet_address) {
    return '';
  }
  return `Linked wallet: ${wallet.shortenAddress(binding.wallet_address)} (${binding.status || 'unknown'}).`;
});
const accessRuleChecks = computed(
  () => getEligibilityRuleChecks(access.state.eligibility, ['access']),
);
const failedAccessRuleChecks = computed(
  () => getFailedRequiredRuleChecks(access.state.eligibility, ['access']),
);
const eligibilityBlockedReason = computed(
  () => access.state.eligibility?.blocked_reasons?.find((item) => item.scope === 'access')?.message
    || failedAccessRuleChecks.value[0]?.description
    || '',
);
const eligibilityNextSteps = computed(
  () => Array.isArray(access.state.eligibility?.possible_next_steps) ? access.state.eligibility.possible_next_steps : [],
);
const eligibilityOverrideMessage = computed(() => {
  const accessOverride = (access.state.eligibility?.allowlist_overrides_applied || []).find((item) => item.scope === 'access');
  if (!accessOverride) {
    return '';
  }
  return `Admin approval is active for ${String(accessOverride.allowlist_scope || accessOverride.scope || 'this wallet').replace(/_/g, ' ')}.`;
});
const showWalletOverrideTools = computed(
  () => (wallet.state.isVerifiedSession && !access.state.me?.access_granted) || Boolean(eligibilityBlockedReason.value),
);

const statusText = computed(() => {
  if (wallet.state.isVerifiedSession) {
    return 'Wallet Verified';
  }
  if (wallet.state.connectionStatus === 'expired') {
    return 'Verify Again';
  }
  if (wallet.state.connectionStatus === 'verifying') {
    return 'Verifying Wallet';
  }
  if (wallet.state.isConnected) {
    return 'Wallet Connected';
  }
  if (!wallet.state.isWalletProviderAvailable) {
    return 'Wallet Provider Unavailable';
  }
  if (wallet.state.connectionStatus === 'connecting') {
    return 'Connecting Wallet';
  }
  return 'Wallet Not Connected';
});

const statusClass = computed(() => {
  if (wallet.state.isVerifiedSession) {
    return 'connected';
  }
  if (wallet.state.connectionStatus === 'expired' || wallet.state.connectionStatus === 'verifying') {
    return 'warning';
  }
  if (!wallet.state.isWalletProviderAvailable) {
    return 'warning';
  }
  return 'idle';
});

function refreshMobileWalletSupport() {
  mobileWalletSupport.value = describeWalletSupport({
    userAgent: typeof navigator === 'undefined' ? '' : navigator.userAgent,
    ethereum: typeof window === 'undefined' ? null : window.ethereum,
    currentUrl: typeof window === 'undefined' ? '' : window.location.href,
  });
}

async function connect() {
  refreshMobileWalletSupport();
  await wallet.connectWallet();
  refreshMobileWalletSupport();
}

async function verify() {
  const verification = await wallet.verifyWallet();
  if (verification) {
    await Promise.all([
      refreshAccountData(),
      refreshAccessStatus(),
    ]);
  }
}

async function disconnect() {
  await wallet.disconnectWallet();
  copyButtonLabel.value = 'Copy Full Address';
  accountSummary.value = null;
  rewardHistory.value = [];
  rewardError.value = '';
  balanceError.value = '';
  transferHistory.value = [];
  mempoolTransactions.value = [];
  transferError.value = '';
  transferSuccessMessage.value = '';
  nonceState.value = null;
  await refreshAccessStatus();
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
    balanceError.value = getApiErrorMessage(error, 'Failed to load native ZOID account summary.');
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
    const response = await apiClient.get(`/accounts/${wallet.state.verifiedWalletAddress}/transactions`);
    transferHistory.value = Array.isArray(response.data.transactions) ? response.data.transactions : [];
  } catch (error) {
    transferHistory.value = [];
    transferError.value = getApiErrorMessage(error, 'Failed to load native ZOID transaction history.');
  } finally {
    isTransferHistoryLoading.value = false;
  }
}

async function refreshNonceState() {
  if (!wallet.state.isVerifiedSession || !wallet.state.verifiedWalletAddress) {
    nonceState.value = null;
    return;
  }

  try {
    const response = await apiClient.get(`/accounts/${wallet.state.verifiedWalletAddress}/nonce`);
    nonceState.value = response.data || null;
  } catch (error) {
    nonceState.value = null;
  }
}

async function refreshMempool() {
  if (!wallet.state.isVerifiedSession) {
    mempoolTransactions.value = [];
    return;
  }

  isMempoolLoading.value = true;
  try {
    const response = await apiClient.get('/mempool');
    mempoolTransactions.value = Array.isArray(response.data.transactions) ? response.data.transactions : [];
  } catch (_error) {
    mempoolTransactions.value = [];
  } finally {
    isMempoolLoading.value = false;
  }
}

async function admitTransferToMempool(transfer) {
  if (!transfer?.tx_id) {
    return;
  }

  isMempoolSubmitting.value = true;
  transferError.value = '';
  transferSuccessMessage.value = '';
  try {
    await apiClient.post(`/transactions/${transfer.tx_id}/admit`);
    transferSuccessMessage.value = 'Transaction admitted to local mempool. Not settled yet.';
    await refreshAccountData();
  } catch (error) {
    transferError.value = humanizeNativeTransferError(
      getApiErrorMessage(error, 'Failed to admit transaction to local mempool.'),
    );
  } finally {
    isMempoolSubmitting.value = false;
  }
}

async function submitTransferIntent() {
  if (!wallet.state.isVerifiedSession || !wallet.state.verifiedWalletAddress) {
    transferError.value = 'Verify wallet before signing a transfer.';
    return;
  }
  if (!wallet.state.supportsNativeTransferSigning) {
    transferError.value = `${wallet.state.providerLabel || 'This wallet provider'} cannot sign native test ZOID transfers yet.`;
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
      availableBalance: accountSummary.value?.available_balance ?? null,
    });
    if (result.duplicate) {
      transferSuccessMessage.value = `Signed native ZOID transfer already recorded at nonce ${result.nonce || result.transfer_nonce}. Not settled yet.`;
    } else {
      transferSuccessMessage.value = `Signed native ZOID transfer recorded. Tx ${result.tx_id} uses nonce ${result.nonce || result.transfer_nonce}. Not settled yet.`;
    }
    transferForm.value.toAddress = '';
    transferForm.value.amount = '';
    transferForm.value.memo = '';
    await refreshAccountData();
  } catch (error) {
    const message = error?.message || 'Native transfer submission failed.';
    transferError.value = humanizeNativeTransferError(message);
  } finally {
    isTransferSubmitting.value = false;
  }
}

async function refreshAccountData() {
  await Promise.all([
    refreshAccountSummary(),
    refreshRewardHistory(),
    refreshTransferHistory(),
    refreshNonceState(),
    refreshMempool(),
  ]);
}

async function refreshAccessStatus() {
  await Promise.all([
    access.refreshMe(wallet.getAuthorizationHeader()),
    access.refreshEligibility(wallet.getAuthorizationHeader()),
  ]);
}

async function submitEligibilityOverride() {
  const result = await access.submitOverrideRequest(
    {
      requested_scope: overrideForm.value.requested_scope,
      reason: overrideForm.value.reason,
      wallet_address: wallet.state.verifiedWalletAddress || null,
      access_account_id: access.state.me?.access_account_id || access.state.me?.access_account?.access_account_id || null,
      current_page: '/wallet',
      detected_blocked_reason: access.state.eligibility?.blocked_reasons?.[0]?.reason || access.state.me?.blocked_reason || null,
    },
    wallet.getAuthorizationHeader(),
  );
  if (result) {
    overrideForm.value = {
      requested_scope: 'review',
      reason: '',
    };
    showOverrideForm.value = false;
  }
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
  refreshAccountData();
}

watch(
  () => [wallet.state.isVerifiedSession, wallet.state.verifiedWalletAddress],
  async ([isVerified, verifiedWalletAddress]) => {
    await refreshAccessStatus();
    if (!isVerified || !verifiedWalletAddress) {
      accountSummary.value = null;
      balanceError.value = '';
      rewardHistory.value = [];
      rewardError.value = '';
      transferHistory.value = [];
      mempoolTransactions.value = [];
      transferError.value = '';
      transferSuccessMessage.value = '';
      nonceState.value = null;
      return;
    }
    await refreshAccountData();
  },
  { immediate: true },
);

onMounted(async () => {
  refreshMobileWalletSupport();
  await wallet.detectMetaMask();
  refreshMobileWalletSupport();
  await refreshAccessStatus();
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

.wallet-mobile-note {
  color: #9fd3ff;
}

.wallet-demo-note {
  color: #ffd58a;
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

.wallet-feedback-actions {
  margin-top: 16px;
}

.eligibility-checklist {
  display: grid;
  gap: 10px;
  margin-top: 12px;
}

.eligibility-rule {
  padding: 10px;
  border-radius: 10px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.03);
}

.eligibility-rule.pass {
  border-color: rgba(141, 245, 166, 0.24);
}

.eligibility-rule.fail {
  border-color: rgba(255, 140, 140, 0.28);
}

.eligibility-rule-value {
  overflow-wrap: anywhere;
  word-break: break-word;
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
  text-decoration: none;
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

.access-card {
  margin-top: 12px;
  padding: 12px;
  border: 1px solid rgba(255, 205, 115, 0.22);
  border-radius: 8px;
  background: rgba(255, 205, 115, 0.08);
}

.override-form {
  margin-top: 12px;
  display: grid;
  gap: 12px;
}

.override-form select,
.override-form textarea {
  width: 100%;
  border: 1px solid rgba(255, 255, 255, 0.14);
  border-radius: 8px;
  background: rgba(6, 6, 6, 0.86);
  color: #f4f4f4;
  padding: 10px 12px;
  font: inherit;
}

.access-success {
  color: #8df5a6;
}

.access-warning {
  color: #ffd884;
}

.access-neutral {
  color: #d7dce3;
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

@media (max-width: 620px) {
  .wallet-copy,
  .wallet-card {
    padding: 16px;
  }

  .address-short {
    font-size: 1.18rem;
  }

  .wallet-actions {
    display: grid;
    grid-template-columns: minmax(0, 1fr);
  }

  .wallet-btn,
  .wallet-link-btn {
    width: 100%;
  }

  .wallet-summary-row {
    align-items: flex-start;
    flex-direction: column;
  }

  .history-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .transfer-field input,
  .transfer-field textarea {
    font-size: 16px;
  }
}
</style>
