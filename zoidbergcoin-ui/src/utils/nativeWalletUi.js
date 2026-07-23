export function buildNativeBalanceSummary(balance = {}) {
  const symbol = balance.symbol || 'ZOID';
  const rows = [];

  if (balance.native_balance !== undefined && balance.native_balance !== null && balance.native_balance !== '') {
    rows.push({
      label: 'Final Native ZOID Balance',
      value: `${balance.native_balance} ${symbol}`,
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

  if (balance.available_balance !== undefined && balance.available_balance !== null && balance.available_balance !== '') {
    rows.push({
      label: 'Available Balance',
      value: `${balance.available_balance} ${symbol}`,
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
    return 'Signed transfer intent';
  }
  if (normalized === 'validated_pending') {
    return 'Validated pending transaction';
  }
  if (normalized === 'mempool') {
    return 'Pending transaction processing';
  }
  if (!normalized) {
    return 'Transfer intent';
  }
  return normalized.replace(/_/g, ' ');
}

export function formatTransferIntentTimestamp(transfer) {
  return transfer?.signed_at || transfer?.created_at || '';
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
