export const FEEDBACK_TYPE_OPTIONS = [
  { value: 'bug', label: 'Bug' },
  { value: 'confusing_ui', label: 'Confusing UI' },
  { value: 'wallet_connection_issue', label: 'Wallet Connection Issue' },
  { value: 'mobile_issue', label: 'Mobile Issue' },
  { value: 'access_allowlist_issue', label: 'Access / Allowlist Issue' },
  { value: 'submission_upload_issue', label: 'Submission / Upload Issue' },
  { value: 'voting_review_issue', label: 'Voting / Review Issue' },
  { value: 'rewards_balance_issue', label: 'Rewards / Balance Issue' },
  { value: 'general_suggestion', label: 'General Suggestion' },
  { value: 'other', label: 'Other' },
];

export function createDefaultFeedbackForm() {
  return {
    type: 'bug',
    title: '',
    description: '',
    name: '',
    email: '',
    handle: '',
    includeContext: true,
  };
}

export function validateFeedbackForm(form = {}) {
  const errors = {};
  if (!String(form.type || '').trim()) {
    errors.type = 'Choose the feedback type that fits best.';
  }
  if (!String(form.title || '').trim()) {
    errors.title = 'Add a short title so we can triage this faster.';
  }
  if (!String(form.description || '').trim()) {
    errors.description = 'Describe what happened or what felt confusing.';
  }
  return errors;
}

export function buildSafeEligibilitySnapshot(eligibility = {}) {
  if (!eligibility || typeof eligibility !== 'object') {
    return null;
  }
  const blockedReasons = Array.isArray(eligibility.blocked_reasons)
    ? eligibility.blocked_reasons.slice(0, 5).map((item) => ({
        scope: item?.scope || null,
        reason: item?.reason || null,
        rule_id: item?.rule_id || null,
      }))
    : [];

  return {
    access_granted: Boolean(eligibility.access_granted),
    can_access_app: Boolean(eligibility.can_access_app),
    wallet_bound: Boolean(eligibility.wallet_bound),
    can_submit: Boolean(eligibility.can_submit),
    can_vote: Boolean(eligibility.can_vote),
    can_receive_rewards: Boolean(eligibility.can_receive_rewards),
    blocked_reasons: blockedReasons,
    submission: eligibility.submission
      ? {
          can_submit: Boolean(eligibility.submission.can_submit),
          eligibility_source: eligibility.submission.eligibility_source || null,
          blocked_reason: eligibility.submission.blocked_reason || null,
        }
      : null,
  };
}

export function summarizeFeedbackContext(context = {}) {
  const parts = [];
  if (context.currentPage) {
    parts.push(`Page: ${context.currentPage}`);
  }
  if (context.currentFlow) {
    parts.push(`Flow: ${context.currentFlow}`);
  }
  if (context.walletAddress) {
    parts.push(`Wallet: ${context.walletAddress}`);
  }
  if (context.accessAccountId) {
    parts.push(`Account: ${context.accessAccountId}`);
  }
  if (context.isMobile) {
    parts.push('Mobile device details included');
  }
  if (context.eligibilityIncluded) {
    parts.push('Eligibility snapshot included');
  }
  return parts;
}
