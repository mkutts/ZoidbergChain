export function normalizeReviewPolicyResponse(payload = {}) {
  return {
    environment: payload.environment || 'development',
    eligibilityMode: payload.eligibility_mode || 'open',
    publicLabel: payload.public_label || 'Open local review voting',
    allowlistModeEnabled: Boolean(payload.allowlist_mode_enabled),
    denylistConfigured: Boolean(payload.denylist_configured),
    thresholds: payload.thresholds || {},
    notes: Array.isArray(payload.notes) ? payload.notes : [],
    eligibility: payload.eligibility && typeof payload.eligibility === 'object'
      ? payload.eligibility
      : null,
    warnings: Array.isArray(payload.warnings) ? payload.warnings : [],
  };
}

export function buildReviewPolicySummary(policy) {
  const normalized = normalizeReviewPolicyResponse(policy);
  const modeLabel = normalized.eligibilityMode.replace(/_/g, ' ');
  return `${normalized.publicLabel} (${modeLabel} mode)`;
}

export function buildReviewPolicyWarning(policy) {
  const normalized = normalizeReviewPolicyResponse(policy);
  if (normalized.eligibilityMode === 'open') {
    return 'Controlled testnet voting can tighten later. Today this node is accepting otherwise-valid reviewers.';
  }
  return 'Controlled testnet voting may require allowlist or activity eligibility before you can sign a vote.';
}

export function buildReviewerEligibilityMessage(policy) {
  const normalized = normalizeReviewPolicyResponse(policy);
  const eligibility = normalized.eligibility;
  if (!eligibility || eligibility.eligible !== false) {
    return '';
  }
  const reason = eligibility.reason
    ? `Reason: ${String(eligibility.reason).replace(/_/g, ' ')}.`
    : '';
  const action = eligibility.recommended_action || 'Ask the operator for access.';
  return `This wallet is not currently eligible to review. ${reason} ${action}`.trim();
}
