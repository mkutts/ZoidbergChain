export const REPORT_DOMAIN = 'zoidbergchain/community-report/v1';
export const REPORT_POLICY_ID = 'zoidberg-public-testnet-v1/community-report/1';
export const REPORT_NETWORK_ID = 'zoidberg-public-testnet-v1';

function canonical(value) {
  if (Array.isArray(value)) return value.map(canonical);
  if (value && typeof value === 'object') {
    return Object.fromEntries(Object.keys(value).sort().map((key) => [key, canonical(value[key])]));
  }
  return value;
}

export function assertCommunityReportChallenge(challenge, expected, now = Date.now()) {
  const payload = challenge?.payload;
  if (!payload || typeof payload !== 'object') throw new Error('Report challenge is missing.');
  if (payload.domain !== REPORT_DOMAIN || payload.network_id !== REPORT_NETWORK_ID
      || payload.policy_id !== REPORT_POLICY_ID || payload.policy_version !== 1) {
    throw new Error('Unexpected report signing policy.');
  }
  if (!/^[0-9a-f]{64}$/.test(payload.policy_digest || '')) throw new Error('Invalid report policy digest.');
  if (payload.wallet_address !== expected.walletAddress.toLowerCase()
      || payload.submission_id !== expected.submissionId
      || payload.content_hash !== expected.contentHash
      || payload.reason !== expected.reason) {
    throw new Error('Report challenge does not match the selected submission and reason.');
  }
  const expiresAt = Date.parse(payload.expires_at || '');
  if (!Number.isFinite(expiresAt) || expiresAt <= now) {
    throw new Error('Report challenge has expired. Request a fresh challenge.');
  }
  if (JSON.stringify(canonical(payload)) !== challenge.message) {
    throw new Error('Report challenge message is not canonical.');
  }
  return challenge.message;
}
