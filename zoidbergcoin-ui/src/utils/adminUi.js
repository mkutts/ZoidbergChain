export function shouldShowAdminDashboard(session) {
  return Boolean(session?.authenticated);
}

export function shouldUseStackedAdminCards(viewportWidth = 0) {
  const width = Number(viewportWidth) || 0;
  return width > 0 && width <= 900;
}

export function buildBoundWalletRows(walletAddresses = []) {
  return (Array.isArray(walletAddresses) ? walletAddresses : []).map((walletAddress) => {
    const value = String(walletAddress || '');
    return {
      walletAddress: value,
      shortLabel: value.length > 22 ? `${value.slice(0, 10)}...${value.slice(-8)}` : value,
    };
  });
}

export function adminSafetyLines() {
  return [
    'Invite codes are shown once. Copy before leaving this screen.',
    'This gate reduces spam but is not proof-of-personhood.',
    'Test ZOID has no real monetary value.',
    'Do not approve users you do not recognize.',
  ];
}
