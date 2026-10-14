const STAGE_COPY = {
  technical_rejected: ['Technical Rejection', 'The file did not pass technical validation and cannot enter community review.', 'warning-chip'],
  awaiting_attestation: ['Attestation Required', 'Technical validation passed; the submitter rights and permanence attestation is still required.', 'pending'],
  invalid_attestation: ['Attestation Invalid', 'The signed submitter attestation is invalid or no longer matches the admitted media.', 'warning-chip'],
  policy_mismatch: ['Policy Mismatch', 'The signed evidence does not match the active media-admission policy.', 'warning-chip'],
  awaiting_review: ['Community Review Pending', 'Originality and admissibility are separate review questions. Neither result implies the other.', 'pending'],
  review_unresolved: ['Review Unresolved', 'One or both review dimensions have not reached a protocol outcome.', 'pending'],
  review_rejected_originality: ['Not Original', 'Originality review resolved not_original. This is separate from admissibility.', 'warning-chip'],
  review_rejected_admissibility: ['Not Admissible', 'Admissibility review resolved not_admissible. This is separate from originality.', 'warning-chip'],
  review_qualified: ['Review Qualified', 'Both review dimensions resolved positively; the admission certificate has not yet been frozen.', 'pending'],
  admission_qualified: ['Admission Qualified', 'The current dual-admission certificate is frozen and valid.', 'ready'],
  mintable: ['Mintable', 'Admission is qualified and the submission is eligible for the current mint queue.', 'ready'],
  minted: ['Minted', 'The submission has an immutable block; finality status is shown separately.', 'ready'],
  finalized: ['Finalized', 'The media block is canonical and finalized.', 'ready'],
  post_mint_disputed: ['Finalized · Disputed', 'A post-mint dispute warning is established. The block remains immutable and finalized.', 'warning-chip'],
  quarantined: ['Quarantined', 'This pre-mint submission cannot mint in its current review round. It has not been deleted.', 'warning-chip'],
  legacy_pre_activation: ['Legacy · Pre-Activation', 'This record predates current dual-admission enforcement; missing current fields are not inferred.', 'pending'],
};

export function normalizeMediaLifecycle(source = {}) {
  const value = source?.lifecycle && typeof source.lifecycle === 'object' ? source.lifecycle : source;
  return {
    stage: String(value?.stage || 'loading'),
    blockingStage: value?.blocking_stage || null,
    technicalValidation: value?.technical_validation || { status: 'unavailable' },
    attestation: value?.attestation || { status: 'missing' },
    review: value?.review || { originality: null, admissibility: null },
    reporting: value?.reporting || { status: 'unavailable', count: 0, threshold_met: false },
    quarantine: value?.quarantine || { quarantined: false },
    admission: value?.admission || { state: 'unavailable', certificate: { status: 'missing' } },
    activation: value?.activation || { state: 'unavailable' },
    mint: value?.mint || { state: 'not_ready', eligible: false },
    finality: value?.finality || { state: 'unavailable', finalized: false },
    postMintDispute: value?.post_mint_dispute || { status: 'not_applicable', threshold_met: false },
    mediaIntegrity: value?.media_integrity || { status: 'unavailable' },
    legacy: value?.legacy || { pre_activation: false, missing_fields_are_not_inferred: true },
  };
}

export function buildMediaLifecycleDisplay(source = {}) {
  const lifecycle = normalizeMediaLifecycle(source);
  const [label, detail, tone] = STAGE_COPY[lifecycle.stage] || [
    lifecycle.stage === 'loading' ? 'Loading lifecycle…' : 'Lifecycle unavailable',
    'No positive protocol state is assumed while lifecycle data is incomplete.',
    'pending',
  ];
  return { ...lifecycle, label, detail, tone };
}

export function buildActivationDisplay(source = {}) {
  const activation = source?.admission_activation || source?.activation || source || {};
  if (activation.state === 'misconfigured') {
    return { label: 'Admission enforcement misconfigured', tone: 'warning-chip', detail: 'This node must not be presented as fully enforcing current Public Testnet admission.' };
  }
  if (activation.state === 'active') {
    return { label: 'Admission enforcement active', tone: 'ready', detail: `Current admission rules apply from block ${activation.activation_height}.` };
  }
  if (activation.state === 'pre_activation') {
    return { label: 'Pre-activation', tone: 'pending', detail: activation.activation_height == null
      ? 'No admission activation height is configured for this development node.'
      : `Current admission rules begin at block ${activation.activation_height}; block ${activation.last_legacy_height} is the last legacy height.` };
  }
  return { label: 'Activation status unavailable', tone: 'pending', detail: 'The node did not provide admission-enforcement status.' };
}

export function buildIntegrityDisplay(source = {}) {
  const integrity = source?.media_integrity || source || {};
  if (integrity.status === 'verified') {
    return { label: 'Media Integrity Verified', tone: 'ready', detail: 'These bytes exactly match the immutable block record. This does not mean lawful, safe, original, admissible, or undisputed.' };
  }
  if (integrity.status === 'failed') {
    return { label: 'Media Integrity Failed', tone: 'warning-chip', detail: 'The bytes do not match the immutable block commitments. Do not rely on this artifact.' };
  }
  return { label: 'Media Integrity Unavailable', tone: 'pending', detail: integrity.download_url
    ? 'Use the exact-byte download to verify the immutable block commitments.'
    : 'This record does not provide current byte-integrity data.' };
}

export function certificateScopeLabel(scope) {
  if (scope === 'current_dual_admission') return 'Current admission-certified';
  if (scope === 'legacy_originality_only') return 'Legacy originality-only';
  return 'Certificate scope unavailable';
}

