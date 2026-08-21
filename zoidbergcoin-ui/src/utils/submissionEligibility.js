function normalizeSource(value) {
  return String(value || '').trim().toLowerCase();
}

export function buildSubmissionEligibilityView(eligibility = {}) {
  const submission = eligibility?.submission || {};
  if (Object.keys(submission).length === 0) {
    return {
      tone: 'info',
      headline: '',
      detail: '',
      policyNote: '',
    };
  }
  const source = normalizeSource(submission.eligibility_source);
  const policyNote = String(submission.policy_rule || '').trim();
  const blockedHeadline = String(submission.message || 'Submission is currently blocked.').trim();
  const blockedDetail = String(submission.recommended_action || '').trim();

  if (submission.can_submit) {
    if (source === 'admin_submission_override') {
      return {
        tone: 'success',
        headline: 'Submission is enabled by an admin submission override.',
        detail: 'A direct submission override is active for this wallet on the current beta node.',
        policyNote,
      };
    }
    if (source === 'review_override') {
      return {
        tone: 'success',
        headline: 'Submission is enabled by a review override.',
        detail: 'A review-scoped admin override is currently allowing submissions for this wallet.',
        policyNote,
      };
    }
    if (source === 'all_beta_override') {
      return {
        tone: 'success',
        headline: 'Submission is enabled by an all beta override.',
        detail: 'An all beta permissions override is currently allowing submissions for this wallet.',
        policyNote,
      };
    }
    return {
      tone: 'success',
      headline: 'Submission is enabled for this verified wallet.',
      detail: String(
        submission.message
        || 'Submission is allowed because controlled beta access is active and the wallet session is verified.',
      ).trim(),
      policyNote,
    };
  }

  return {
    tone: 'error',
    headline: blockedHeadline,
    detail: blockedDetail,
    policyNote,
  };
}
