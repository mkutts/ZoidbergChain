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
        headline: 'Submission is open because admin approval is active for this wallet.',
        detail: 'A direct beta approval is currently allowing this wallet to submit.',
        policyNote,
      };
    }
    if (source === 'review_override') {
      return {
        tone: 'success',
        headline: 'Submission is open because review approval is active for this wallet.',
        detail: 'A review-scoped beta approval is currently allowing this wallet to submit.',
        policyNote,
      };
    }
    if (source === 'all_beta_override') {
      return {
        tone: 'success',
        headline: 'Submission is open because full beta approval is active for this wallet.',
        detail: 'An all-beta approval is currently allowing this wallet to submit.',
        policyNote,
      };
    }
    return {
      tone: 'success',
      headline: 'You can submit with this verified wallet.',
      detail: String(
        submission.message
        || 'Submission is allowed because beta access is active and this wallet is verified.',
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
