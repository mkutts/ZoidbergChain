export const COMMUNITY_REVIEW_DOMAIN = 'zoidbergchain/community-review/v2';
export const COMMUNITY_REVIEW_NETWORK_ID = 'zoidberg-public-testnet-v1';

function canonical(value) {
  if (Array.isArray(value)) return value.map(canonical);
  if (value && typeof value === 'object') {
    return Object.fromEntries(Object.keys(value).sort().map((key) => [key, canonical(value[key])]));
  }
  return value;
}

export function assertCommunityReviewChallenge(challenge, expected, now = Date.now()) {
  let payload;
  try {
    payload = JSON.parse(challenge?.message || '');
  } catch {
    throw new Error('Review challenge message is not valid canonical JSON.');
  }
  if (payload.domain !== COMMUNITY_REVIEW_DOMAIN
      || payload.network_id !== COMMUNITY_REVIEW_NETWORK_ID
      || payload.vote_version !== 2
      || payload.policy_version !== 1
      || payload.reviewer_policy_version !== 1
      || payload.reputation_rule_version !== 1
      || !/^[0-9a-f]{64}$/.test(payload.policy_digest || '')) {
    throw new Error('Unexpected community-review signing policy.');
  }
  if (payload.wallet_address !== expected.walletAddress.toLowerCase()
      || payload.submission_id !== expected.submissionId
      || payload.content_hash !== expected.contentHash
      || payload.dimension !== expected.dimension
      || payload.choice !== expected.choice) {
    throw new Error('Review challenge does not match the selected wallet, media, dimension, and choice.');
  }
  if (challenge.wallet_address !== payload.wallet_address
      || challenge.submission_id !== payload.submission_id
      || challenge.content_hash !== payload.content_hash
      || challenge.dimension !== payload.dimension
      || challenge.vote !== payload.choice
      || challenge.network_id !== payload.network_id
      || challenge.vote_version !== payload.vote_version) {
    throw new Error('Review challenge summary does not match its signed payload.');
  }
  const expiresAt = Date.parse(payload.expires_at || '');
  if (!Number.isFinite(expiresAt) || expiresAt <= now) {
    throw new Error('Review challenge has expired. Request a fresh challenge.');
  }
  if (JSON.stringify(canonical(payload)) !== challenge.message) {
    throw new Error('Review challenge message is not canonical.');
  }
  return challenge.message;
}

