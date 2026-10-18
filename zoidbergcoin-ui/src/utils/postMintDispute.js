export const DISPUTE_DOMAIN = 'zoidbergchain/post-mint-dispute/v1';
export const DISPUTE_POLICY_ID = 'zoidberg-public-testnet-v1/post-mint-dispute/1';
export const DISPUTE_NETWORK_ID = 'zoidberg-public-testnet-v1';

function canonical(value) {
  if (Array.isArray(value)) return value.map(canonical);
  if (value && typeof value === 'object') {
    return Object.fromEntries(Object.keys(value).sort().map((key) => [key, canonical(value[key])]));
  }
  return value;
}

export function assertPostMintDisputeChallenge(challenge, expected, now = Date.now()) {
  const payload = challenge?.payload;
  if (!payload || payload.domain !== DISPUTE_DOMAIN || payload.network_id !== DISPUTE_NETWORK_ID
      || payload.policy_id !== DISPUTE_POLICY_ID || payload.policy_version !== 1
      || !/^[0-9a-f]{64}$/.test(payload.policy_digest || '')) {
    throw new Error('Unexpected dispute signing policy.');
  }
  if (payload.wallet_address !== expected.walletAddress.toLowerCase()
      || payload.submission_id !== expected.submissionId
      || payload.block_height !== expected.blockHeight
      || payload.block_hash !== expected.blockHash
      || payload.media_hash !== expected.mediaHash
      || payload.reason !== expected.reason) {
    throw new Error('Dispute challenge does not match the finalized media and reason.');
  }
  const expiresAt = Date.parse(payload.expires_at || '');
  if (!Number.isFinite(expiresAt) || expiresAt <= now) {
    throw new Error('Dispute challenge has expired. Request a fresh challenge.');
  }
  if (JSON.stringify(canonical(payload)) !== challenge.message) {
    throw new Error('Dispute challenge message is not canonical.');
  }
  return challenge.message;
}
