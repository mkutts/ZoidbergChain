const PUBLIC_TESTNET_V1_NETWORK_ID = 'zoidberg-public-testnet-v1';
const PUBLIC_TESTNET_V1_LABEL = 'Public Testnet v1';

function normalizeToken(value) {
  return String(value || '').trim().toLowerCase();
}

function pluralize(value, singular) {
  return Number(value) === 1 ? singular : `${singular}s`;
}

function formatConfirmationCount(confirmations) {
  if (confirmations === null || confirmations === undefined || confirmations === '') {
    return 'no recorded confirmations yet';
  }
  return `${confirmations} ${pluralize(confirmations, 'confirmation')}`;
}

export function buildProtocolNetworkIdentity(source = {}) {
  const rawProtocolVersion = source?.protocol_version;
  const numericProtocolVersion = Number(rawProtocolVersion);
  const protocolVersion = Number.isFinite(numericProtocolVersion) ? numericProtocolVersion : null;
  const networkId = String(source?.network_id || '').trim();
  const networkAlias = String(source?.network_name || '').trim();
  const genesisHash = String(source?.canonical_genesis_hash || source?.genesis_hash || '').trim();
  const displayName = (
    networkId === PUBLIC_TESTNET_V1_NETWORK_ID
    && protocolVersion === 1
  )
    ? PUBLIC_TESTNET_V1_LABEL
    : (networkAlias || networkId || 'Unknown network');

  return {
    displayName,
    networkId,
    networkAlias,
    protocolVersion,
    protocolLabel: protocolVersion === null ? 'Unknown protocol version' : `Protocol v${protocolVersion}`,
    genesisHash,
  };
}

export function isProtocolImageContent(record = {}) {
  const value = String(record?.mime_type || record?.content_type || '').trim().toLowerCase();
  return value.startsWith('image/');
}

export function isProtocolTextContent(record = {}) {
  const mimeType = String(record?.mime_type || '').trim().toLowerCase();
  const contentType = String(record?.content_type || '').trim().toLowerCase();
  return mimeType === 'text/plain' || contentType === 'text' || contentType === 'mixed';
}

export function resolveProtocolTextPreview(record = {}) {
  const candidates = [
    record?.text_content,
    record?.meme?.text,
  ];

  for (const candidate of candidates) {
    if (typeof candidate === 'string' && candidate.trim()) {
      return candidate;
    }
  }
  return '';
}

export function hasRenderableProtocolPreview(record = {}) {
  if (isProtocolImageContent(record) && record?.download_url) {
    return true;
  }
  return Boolean(resolveProtocolTextPreview(record));
}

export function isProtocolGenesisBlock(record = {}) {
  return Boolean(
    record?.is_genesis === true
    || normalizeToken(record?.object_type) === 'genesis'
    || Number(record?.index) === 0
  );
}

export function buildFinalityDisplay(record = {}) {
  const confirmationDepth = Number(record?.confirmation_depth ?? 2) || 2;
  const finalityDepth = Number(record?.finality_depth ?? 6) || 6;
  const confirmations = record?.confirmations ?? null;
  const canonical = Boolean(record?.canonical);
  const accepted = Boolean(record?.accepted ?? record?.block_accepted ?? record?.block_created);
  const confirmed = Boolean(record?.confirmed);
  const finalized = Boolean(record?.finalized);

  if (finalized) {
    return {
      label: 'Operationally Finalized',
      tone: 'ready',
      detail: `Canonical with ${formatConfirmationCount(confirmations)}. Public Testnet v1 treats ${finalityDepth}+ descendants as operational finality.`,
    };
  }
  if (confirmed) {
    return {
      label: 'Confirmed',
      tone: 'ready',
      detail: `Canonical with ${formatConfirmationCount(confirmations)}. Confirmation begins at ${confirmationDepth} descendants and operational finality begins at ${finalityDepth}.`,
    };
  }
  if (canonical) {
    return {
      label: 'Canonical',
      tone: 'ready',
      detail: `Accepted and currently on the selected chain with ${formatConfirmationCount(confirmations)}.`,
    };
  }
  if (accepted) {
    return {
      label: 'Accepted',
      tone: 'pending',
      detail: 'Validated and accepted by this node.',
    };
  }
  return {
    label: 'Created',
    tone: 'pending',
    detail: 'A candidate block exists but is not yet accepted on this node.',
  };
}

export function buildSubmissionLifecycleDisplay(submission = {}) {
  const lifecycle = submission?.protocol_v1_lifecycle || {};
  const phase = normalizeToken(lifecycle.phase || submission?.block_status || submission?.mint_status || submission?.submission_status || submission?.status);
  const finality = buildFinalityDisplay({
    accepted: lifecycle.block_accepted,
    block_created: lifecycle.block_created,
    canonical: lifecycle.canonical,
    confirmations: lifecycle.confirmations,
    confirmed: lifecycle.confirmed,
    finalized: lifecycle.finalized,
    confirmation_depth: lifecycle.confirmation_depth,
    finality_depth: lifecycle.finality_depth,
  });

  if (lifecycle.rejected || phase === 'rejected') {
    return {
      label: 'Rejected',
      tone: 'warning-chip',
      detail: submission?.decision_reason
        ? `Originality review rejected this submission: ${submission.decision_reason}.`
        : 'Originality review rejected this submission.',
    };
  }
  if (lifecycle.finalized || lifecycle.confirmed || lifecycle.canonical) {
    return finality;
  }
  if (lifecycle.block_accepted) {
    return {
      label: 'Block Accepted',
      tone: 'pending',
      detail: 'A block was created and accepted for this submission. Chain selection and descendant depth still determine later confirmation and finality.',
    };
  }
  if (lifecycle.block_created) {
    return {
      label: 'Block Created',
      tone: 'pending',
      detail: 'A candidate block was created for this submission.',
    };
  }
  if (lifecycle.mint_eligible || phase === 'mint-eligible') {
    return {
      label: 'Mint Eligible',
      tone: 'ready',
      detail: 'Voting is complete, the certificate is valid, and this submission is ready for block creation.',
    };
  }
  if (lifecycle.certified || phase === 'certified') {
    return {
      label: 'Certified',
      tone: 'ready',
      detail: 'Voting is complete and a valid originality certificate exists.',
    };
  }
  if (lifecycle.voting || phase === 'voting') {
    return {
      label: 'Voting',
      tone: 'pending',
      detail: 'Waiting for community originality votes.',
    };
  }
  return {
    label: 'Submitted',
    tone: 'pending',
    detail: 'Submission recorded and waiting to move through the Protocol v1 review flow.',
  };
}

export function buildBlockDisplay(block = {}) {
  const isGenesis = isProtocolGenesisBlock(block);
  const finality = buildFinalityDisplay(block);

  return {
    isGenesis,
    title: isGenesis ? 'Public Testnet v1 Genesis' : 'Accepted Protocol v1 Block',
    categoryLabel: isGenesis ? 'Protocol v1 genesis object' : 'Accepted meme-mined block',
    statusLabel: isGenesis && finality.label === 'Canonical' ? 'Canonical Genesis' : finality.label,
    statusTone: isGenesis && finality.tone === 'pending' ? 'ready' : finality.tone,
    detail: isGenesis
      ? `Block height 0 anchors ${PUBLIC_TESTNET_V1_LABEL}. ${finality.detail}`
      : finality.detail,
  };
}

export function buildBlockContentAvailability(block = {}) {
  if (isProtocolGenesisBlock(block)) {
    return {
      chipLabel: block?.media_embedded ? 'Immutable Genesis Media' : 'Genesis Record',
      chipTone: 'ready',
      detail: block?.media_embedded
        ? 'Genesis embeds the exact original Zoidberg meme bytes in block 0. It remains a special non-certified genesis object, not an originality-voted submission.'
        : 'Genesis does not use submission media, certificates, or originality vote state.',
    };
  }
  if (block?.media_embedded) {
    return {
      chipLabel: 'Immutable In Block',
      chipTone: 'ready',
      detail: block?.download_url
        ? 'Accepted media is stored in the immutable block record. This node also serves a convenience download.'
        : 'Accepted media is stored in the immutable block record. This node does not currently have an auxiliary downloadable copy, but the block remains authoritative.',
    };
  }

  const status = normalizeToken(block?.storage_status);
  if (block?.download_url) {
    return {
      chipLabel: 'Download Available',
      chipTone: 'ready',
      detail: 'This node can currently serve a downloadable content copy for this block.',
    };
  }
  if (status === 'remote') {
    return {
      chipLabel: 'Auxiliary Copy Remote',
      chipTone: 'warning-chip',
      detail: 'This node knows the content reference, but it needs an auxiliary sync before it can serve a local download.',
    };
  }
  if (status === 'missing') {
    return {
      chipLabel: 'Auxiliary Copy Missing',
      chipTone: 'warning-chip',
      detail: 'This node cannot serve an auxiliary content copy right now.',
    };
  }
  if (status === 'local') {
    return {
      chipLabel: 'Local Copy Present',
      chipTone: 'pending',
      detail: 'A local content copy exists on this node but is not yet marked verified.',
    };
  }

  return {
    chipLabel: 'Content Status Unknown',
    chipTone: '',
    detail: 'Content availability is not available for this record.',
  };
}

export function shouldRetryProtocolAction(message = '') {
  const normalized = normalizeToken(message);
  return normalized.includes('expired') || normalized.includes('already been used');
}

export function humanizeProtocolActionError(message, options = {}) {
  const normalized = String(message || '').trim();
  const lower = normalized.toLowerCase();
  const action = String(options.action || 'action').trim().toLowerCase() || 'action';
  const actionLabel = action.charAt(0).toUpperCase() + action.slice(1);

  if (shouldRetryProtocolAction(normalized)) {
    return `${actionLabel} signing window expired. Try again to request a fresh Protocol v1 message.`;
  }
  if (lower.includes('wallet_address must match the verified wallet session')) {
    return 'The signed wallet does not match your verified session. Reconnect the same wallet and try again.';
  }
  if (lower.includes('submission creator cannot vote on their own submission')) {
    return 'Submission creator cannot vote on their own submission.';
  }
  if (lower.includes('already voted')) {
    return 'This wallet has already voted on that submission.';
  }
  if (lower.includes('finalized or certified submissions cannot receive votes')) {
    return 'Voting is closed because this submission is already certified or finalized.';
  }
  if (lower.includes('wrong_network') || lower.includes('different network') || lower.includes('network does not match')) {
    return 'This request belongs to a different ZoidbergChain network. Refresh and try again on Public Testnet v1.';
  }
  if (lower.includes('invalid_signature') || lower.includes('signature could not be verified')) {
    return `The ${action} signature could not be verified. Sign the exact backend message again in MetaMask.`;
  }
  if (lower.includes('already minted')) {
    return 'This submission already has a Protocol v1 block.';
  }
  if (lower.includes('submission rejected')) {
    return 'This submission was rejected and cannot continue through the Protocol v1 lifecycle.';
  }
  if (lower.includes('content file not found') || lower.includes('content unavailable') || lower.includes('content file failed integrity verification')) {
    return 'This node cannot serve that content copy right now.';
  }
  if (lower.includes('access') && (lower.includes('required') || lower.includes('approved') || lower.includes('eligible'))) {
    return normalized;
  }
  return normalized || `${actionLabel} failed.`;
}
