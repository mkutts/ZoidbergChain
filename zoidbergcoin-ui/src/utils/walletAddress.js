const ADDRESS_PATTERN = /^0x[a-fA-F0-9]{40}$/;

export function normalizeWalletAddress(address) {
  const candidate = String(address || '').trim();
  if (!ADDRESS_PATTERN.test(candidate)) {
    return null;
  }
  return candidate.toLowerCase();
}

export function shortenWalletAddress(address, start = 4, end = 4) {
  const normalized = normalizeWalletAddress(address);
  if (!normalized) {
    return '';
  }
  return `${normalized.slice(0, start + 2)}...${normalized.slice(-end)}`;
}

export function isWalletAddress(address) {
  return normalizeWalletAddress(address) !== null;
}
