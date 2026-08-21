<template>
  <section :id="panelId" class="feedback-panel" :class="{ open: isOpen }">
    <div class="feedback-header">
      <div>
        <p class="section-label">Beta Feedback</p>
        <h2>{{ headline }}</h2>
        <p class="feedback-copy">
          {{ introCopy }}
        </p>
      </div>
      <button type="button" class="feedback-toggle" @click="isOpen = !isOpen">
        {{ isOpen ? 'Hide Form' : toggleLabel }}
      </button>
    </div>

    <p class="feedback-warning">
      Do not include private keys, seed phrases, passwords, invite codes, or other sensitive personal information.
    </p>

    <form v-if="isOpen" class="feedback-form" @submit.prevent="submitFeedbackForm">
      <div class="field-group">
        <label for="feedback-type">What kind of issue is this?</label>
        <select id="feedback-type" v-model="form.type" class="input-field">
          <option v-for="option in feedbackTypeOptions" :key="option.value" :value="option.value">
            {{ option.label }}
          </option>
        </select>
        <p v-if="errors.type" class="status-message error">{{ errors.type }}</p>
      </div>

      <div class="field-group">
        <label for="feedback-title">Short title</label>
        <input
          id="feedback-title"
          v-model.trim="form.title"
          type="text"
          class="input-field"
          placeholder="Example: Wallet verify button stalls on mobile"
        >
        <p v-if="errors.title" class="status-message error">{{ errors.title }}</p>
      </div>

      <div class="field-group">
        <label for="feedback-description">What happened?</label>
        <textarea
          id="feedback-description"
          v-model.trim="form.description"
          rows="5"
          class="input-field text-area"
          placeholder="Tell us what you expected, what happened instead, and how we can reproduce it."
        ></textarea>
        <p v-if="errors.description" class="status-message error">{{ errors.description }}</p>
      </div>

      <div class="field-grid">
        <div class="field-group">
          <label for="feedback-name">Name (optional)</label>
          <input id="feedback-name" v-model.trim="form.name" type="text" class="input-field">
        </div>
        <div class="field-group">
          <label for="feedback-email">Email (optional)</label>
          <input id="feedback-email" v-model.trim="form.email" type="email" class="input-field">
        </div>
        <div class="field-group">
          <label for="feedback-handle">Handle (optional)</label>
          <input id="feedback-handle" v-model.trim="form.handle" type="text" class="input-field">
        </div>
      </div>

      <label class="context-toggle">
        <input v-model="form.includeContext" type="checkbox">
        <span>Include wallet, page, device, and safe eligibility details automatically</span>
      </label>

      <div v-if="contextSummary.length > 0" class="context-summary">
        <p class="section-label">Included Context</p>
        <p v-for="line in contextSummary" :key="line" class="feedback-copy">{{ line }}</p>
      </div>

      <div class="feedback-actions">
        <button type="submit" class="primary-button" :disabled="feedback.state.isSubmitting">
          {{ feedback.state.isSubmitting ? 'Sending Feedback...' : 'Send Feedback' }}
        </button>
      </div>
    </form>

    <p v-if="feedback.state.successMessage" class="status-message success">
      {{ feedback.state.successMessage }}
    </p>
    <p v-if="feedback.state.errorMessage" class="status-message error">
      {{ feedback.state.errorMessage }}
    </p>
  </section>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue';
import { useRoute } from 'vue-router';
import { useAccess } from '../services/access';
import { useFeedback } from '../services/feedback';
import { useWallet } from '../services/wallet';
import {
  FEEDBACK_TYPE_OPTIONS,
  buildSafeEligibilitySnapshot,
  createDefaultFeedbackForm,
  summarizeFeedbackContext,
  validateFeedbackForm,
} from '../utils/feedback.js';
import { FEEDBACK_PANEL_OPEN_EVENT } from '../utils/feedbackPanel.js';

const props = defineProps({
  headline: {
    type: String,
    default: 'Found a bug or something confusing? Send feedback.',
  },
  introCopy: {
    type: String,
    default: 'This is a controlled beta, so rough edges are expected. Your notes help us tighten the testnet faster.',
  },
  toggleLabel: {
    type: String,
    default: 'Open Feedback Form',
  },
  entryPoint: {
    type: String,
    default: 'dashboard',
  },
  defaultOpen: {
    type: Boolean,
    default: false,
  },
  panelId: {
    type: String,
    default: 'feedback-panel',
  },
});

const route = useRoute();
const wallet = useWallet();
const access = useAccess();
const feedback = useFeedback();
const isOpen = ref(Boolean(props.defaultOpen));
const form = reactive(createDefaultFeedbackForm());
const errors = reactive({});

const feedbackTypeOptions = FEEDBACK_TYPE_OPTIONS;

const walletAddress = computed(
  () => wallet.state.verifiedWalletAddress
    || wallet.state.normalizedWalletAddress
    || access.state.eligibility?.connected_wallet
    || '',
);

const accessAccountId = computed(
  () => access.state.me?.access_account?.access_account_id
    || access.state.eligibility?.access_account?.access_account_id
    || '',
);

const contextPayload = computed(() => {
  if (!form.includeContext) {
    return {};
  }
  const browserMetadata = typeof window === 'undefined'
    ? null
    : {
        browser_label: typeof navigator !== 'undefined' ? navigator.userAgent : '',
        platform: typeof navigator !== 'undefined' ? navigator.platform : '',
        language: typeof navigator !== 'undefined' ? navigator.language : '',
        timezone: typeof Intl !== 'undefined' ? Intl.DateTimeFormat().resolvedOptions().timeZone : '',
        screen_width: window.screen?.width ?? null,
        screen_height: window.screen?.height ?? null,
        prefers_reduced_motion: typeof window.matchMedia === 'function'
          ? window.matchMedia('(prefers-reduced-motion: reduce)').matches
          : false,
      };

  return {
    current_page: route.fullPath || (typeof window !== 'undefined' ? window.location.pathname : ''),
    current_flow: props.entryPoint,
    wallet_address: walletAddress.value || null,
    access_account_id: accessAccountId.value || null,
    eligibility_snapshot: buildSafeEligibilitySnapshot(access.state.eligibility),
    browser_metadata: browserMetadata,
    viewport_width: typeof window !== 'undefined' ? window.innerWidth : null,
    viewport_height: typeof window !== 'undefined' ? window.innerHeight : null,
    is_mobile: typeof window !== 'undefined' ? window.innerWidth <= 900 : null,
  };
});

const contextSummary = computed(() => summarizeFeedbackContext({
  currentPage: contextPayload.value.current_page,
  currentFlow: contextPayload.value.current_flow,
  walletAddress: contextPayload.value.wallet_address,
  accessAccountId: contextPayload.value.access_account_id,
  isMobile: Boolean(contextPayload.value.is_mobile),
  eligibilityIncluded: Boolean(contextPayload.value.eligibility_snapshot),
}));

function maybeOpenFromHash() {
  if (typeof window === 'undefined') {
    return;
  }
  const currentHash = String(window.location.hash || '').replace(/^#/, '').trim();
  if (currentHash && currentHash === props.panelId) {
    isOpen.value = true;
  }
}

function handleOpenEvent(event) {
  const detail = event?.detail || {};
  const requestedPanelId = String(detail.panelId || 'feedback-panel').trim();
  if (requestedPanelId && requestedPanelId !== props.panelId) {
    return;
  }
  isOpen.value = true;
  if (detail.scrollIntoView && typeof window !== 'undefined') {
    window.requestAnimationFrame(() => {
      const element = document.getElementById(props.panelId);
      element?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  }
}

function clearErrors() {
  Object.keys(errors).forEach((key) => {
    delete errors[key];
  });
}

async function submitFeedbackForm() {
  clearErrors();
  const validationErrors = validateFeedbackForm(form);
  Object.assign(errors, validationErrors);
  if (Object.keys(validationErrors).length > 0) {
    return;
  }

  const payload = {
    type: form.type,
    title: form.title.trim(),
    description: form.description.trim(),
    name: form.name.trim() || null,
    email: form.email.trim() || null,
    handle: form.handle.trim() || null,
    ...(form.includeContext ? contextPayload.value : {}),
  };

  const result = await feedback.submitFeedback(payload, {
    ...wallet.getAuthorizationHeader(),
    ...access.getAccessHeaders(),
  });

  if (result?.feedback?.feedback_id) {
    const includeContext = form.includeContext;
    Object.assign(form, createDefaultFeedbackForm());
    form.includeContext = includeContext;
    clearErrors();
  }
}

onMounted(() => {
  maybeOpenFromHash();
  if (typeof window !== 'undefined') {
    window.addEventListener('hashchange', maybeOpenFromHash);
    window.addEventListener(FEEDBACK_PANEL_OPEN_EVENT, handleOpenEvent);
  }
});

onBeforeUnmount(() => {
  if (typeof window !== 'undefined') {
    window.removeEventListener('hashchange', maybeOpenFromHash);
    window.removeEventListener(FEEDBACK_PANEL_OPEN_EVENT, handleOpenEvent);
  }
});
</script>

<style scoped>
.feedback-panel {
  border: 1px solid rgba(255, 205, 115, 0.18);
  border-radius: 24px;
  background: rgba(8, 12, 20, 0.88);
  padding: 22px;
  display: grid;
  gap: 16px;
}

.feedback-header {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
}

.section-label {
  text-transform: uppercase;
  letter-spacing: 0.18em;
  color: #ffcd73;
  font-size: 0.8rem;
}

.feedback-header h2 {
  margin: 8px 0;
  font-size: clamp(1.35rem, 2vw, 1.8rem);
}

.feedback-copy,
.feedback-warning {
  color: #d8d1c0;
  line-height: 1.6;
}

.feedback-warning {
  padding: 12px 14px;
  border-radius: 16px;
  background: rgba(255, 170, 102, 0.08);
  border: 1px solid rgba(255, 170, 102, 0.12);
}

.feedback-toggle,
.primary-button {
  border: none;
  border-radius: 999px;
  padding: 12px 18px;
  font-weight: 700;
  cursor: pointer;
}

.feedback-toggle {
  background: rgba(255, 205, 115, 0.14);
  color: #ffcd73;
}

.primary-button {
  background: linear-gradient(135deg, #ffcd73, #ff8a5b);
  color: #16110a;
}

.feedback-form {
  display: grid;
  gap: 16px;
}

.field-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.field-group {
  display: grid;
  gap: 8px;
}

.field-group label,
.context-toggle {
  color: #f7f0de;
  font-weight: 600;
}

.input-field {
  width: 100%;
  border-radius: 16px;
  border: 1px solid rgba(255, 205, 115, 0.18);
  background: rgba(15, 22, 34, 0.92);
  color: #f7f0de;
  padding: 12px 14px;
}

.text-area {
  min-height: 132px;
  resize: vertical;
}

.context-toggle {
  display: flex;
  gap: 10px;
  align-items: flex-start;
}

.context-summary {
  border-radius: 18px;
  padding: 14px;
  background: rgba(255, 205, 115, 0.06);
  border: 1px solid rgba(255, 205, 115, 0.12);
  display: grid;
  gap: 6px;
}

.feedback-actions {
  display: flex;
  justify-content: flex-start;
}

.status-message.success {
  color: #8be28d;
}

.status-message.error {
  color: #ff9c7a;
}

@media (max-width: 900px) {
  .field-grid {
    grid-template-columns: 1fr;
  }

  .feedback-header {
    flex-direction: column;
  }
}
</style>
