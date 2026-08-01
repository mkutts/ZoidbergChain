export function buildNativeBalanceSummary(balance = {}) {
  const symbol = balance.symbol || 'ZOID';
  const rows = [];
  const finalBalance = balance.final_balance ?? balance.native_balance;

  if (finalBalance !== undefined && finalBalance !== null && finalBalance !== '') {
    rows.push({
      label: 'Final native ZOID balance',
      value: `${finalBalance} ${symbol}`,
    });
  }

  if (balance.available_balance !== undefined && balance.available_balance !== null && balance.available_balance !== '') {
    rows.push({
      label: 'Available to spend',
      value: `${balance.available_balance} ${symbol}`,
    });
  }

  if (balance.pending_outgoing && balance.pending_outgoing !== '0') {
    rows.push({
      label: 'Pending Outgoing',
      value: `${balance.pending_outgoing} ${symbol}`,
    });
  }

  if (balance.pending_incoming && balance.pending_incoming !== '0') {
    rows.push({
      label: 'Pending Incoming',
      value: `${balance.pending_incoming} ${symbol}`,
    });
  }

  return rows;
}

export function describeTransferIntentDirection(transfer, verifiedWalletAddress) {
  const wallet = String(verifiedWalletAddress || '').toLowerCase();
  const fromAddress = String(transfer?.from_address || '').toLowerCase();
  const toAddress = String(transfer?.to_address || '').toLowerCase();

  if (wallet && fromAddress === wallet) {
    return 'Outgoing';
  }
  if (wallet && toAddress === wallet) {
    return 'Incoming';
  }
  return 'Related';
}

export function describeTransferIntentStatus(status) {
  const normalized = String(status || '').trim().toLowerCase();
  if (normalized === 'signed_pending') {
    return 'Signed, not in mempool';
  }
  if (normalized === 'validated_pending') {
    return 'Validated, pending mempool';
  }
  if (normalized === 'mempool') {
    return 'In local mempool';
  }
  if (normalized === 'included') {
    return 'Included in meme-mined block';
  }
  if (normalized === 'settled') {
    return 'Settled on ZoidbergChain';
  }
  if (normalized === 'rejected') {
    return 'Rejected';
  }
  if (normalized === 'failed') {
    return 'Failed';
  }
  if (normalized === 'expired') {
    return 'Expired';
  }
  if (!normalized) {
    return 'Native ZOID transaction';
  }
  return normalized.replace(/_/g, ' ');
}

export function formatTransferIntentTimestamp(transfer) {
  return transfer?.settled_at || transfer?.admitted_at || transfer?.signed_at || transfer?.created_at || '';
}

export function humanizeNativeTransferError(message) {
  const normalized = String(message || '').trim();
  const lower = normalized.toLowerCase();

  if (lower.includes('insufficient_available_balance') || lower.includes('insufficient available balance')) {
    return 'Available to spend is too low for that native ZOID transfer.';
  }
  if (lower.includes('nonce_too_low') || lower.includes('lower than the next expected nonce')) {
    return 'The transfer nonce is too low. Refresh the account and try again.';
  }
  if (lower.includes('nonce_gap') || lower.includes('ahead of the next expected nonce')) {
    return 'The transfer nonce is ahead of the next expected value. Refresh the account and try again.';
  }
  if (lower.includes('duplicate_nonce') || lower.includes('nonce already used or reserved')) {
    return 'That nonce is already used or reserved. Refresh the account and try again.';
  }
  if (lower.includes('duplicate_transaction_id')) {
    return 'This native ZOID transaction is already recorded on this node.';
  }
  if (lower.includes('invalid_signature')) {
    return 'The native ZOID signature could not be verified.';
  }
  if (lower.includes('wrong_network') || lower.includes('different network') || lower.includes('network does not match')) {
    return 'This transfer belongs to a different ZoidbergChain network.';
  }
  if (lower.includes('invalid_fee') || lower.includes('nonzero fee')) {
    return 'Native ZOID transfer fees are not enabled on this network yet.';
  }
  if (lower.includes('transaction_already_settled') || lower.includes('already settled')) {
    return 'This transaction is already settled on ZoidbergChain.';
  }
  if (lower.includes('transaction not found')) {
    return 'The requested native ZOID transaction was not found.';
  }
  if (lower.includes('peer_broadcast_failed')) {
    return 'Peer broadcast failed. The transaction may still remain local to this node.';
  }
  if (lower.includes('mempool_admission_failed') || lower.includes('not eligible for mempool admission')) {
    return 'The transaction could not be admitted to the local mempool.';
  }

  return normalized;
}

export function buildRewardSummary(reward) {
  return [
    { label: 'Native ZOID Reward Amount', value: reward?.reward_amount ?? 'Missing' },
    { label: 'Reward Type', value: reward?.reward_type || 'Missing' },
    { label: 'Submission ID', value: reward?.submission_id || 'Missing' },
    { label: 'Certificate ID', value: reward?.certificate_id || 'Missing' },
    { label: 'Block Height', value: reward?.block_height ?? 'Missing' },
    { label: 'Block Hash', value: reward?.block_hash || 'Missing' },
    { label: 'Minted At', value: reward?.minted_at || 'Missing' },
  ];
}
