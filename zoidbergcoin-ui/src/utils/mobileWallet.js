const MOBILE_DEVICE_PATTERN = /android|iphone|ipad|ipod|iemobile|opera mini|mobile/i;
const METAMASK_MOBILE_PATTERN = /metamaskmobile|metamask/i;

export function isMobileDevice(userAgent = '') {
  return MOBILE_DEVICE_PATTERN.test(String(userAgent || ''));
}

export function buildMetaMaskDeepLink(currentUrl = '') {
  try {
    const parsed = new URL(String(currentUrl || ''));
    const withoutProtocol = parsed.toString().replace(/^https?:\/\//i, '');
    return withoutProtocol
      ? `https://metamask.app.link/dapp/${withoutProtocol}`
      : '';
  } catch {
    return '';
  }
}

export function describeWalletSupport({
  userAgent = '',
  ethereum = null,
  currentUrl = '',
} = {}) {
  const mobileDevice = isMobileDevice(userAgent);
  const injectedProvider = Boolean(ethereum);
  const metaMaskMobileBrowser = Boolean(
    mobileDevice
    && injectedProvider
    && (
      ethereum?.isMetaMask
      || METAMASK_MOBILE_PATTERN.test(String(userAgent || ''))
    )
  );
  const openInMetaMaskUrl = mobileDevice && !metaMaskMobileBrowser
    ? buildMetaMaskDeepLink(currentUrl)
    : '';

  return {
    isMobileDevice: mobileDevice,
    hasInjectedProvider: injectedProvider,
    isMetaMaskMobileBrowser: metaMaskMobileBrowser,
    helperText: mobileDevice
      ? 'For best mobile wallet support, open this site inside the MetaMask Mobile browser.'
      : '',
    noProviderMessage: mobileDevice && !injectedProvider
      ? 'MetaMask was not detected in this browser. Open this site in MetaMask Mobile or install MetaMask.'
      : '',
    openInMetaMaskUrl,
    shouldShowOpenInMetaMask: Boolean(openInMetaMaskUrl),
  };
}

export function buildReturningWalletGuidance({
  accessGranted = false,
  walletBound = false,
  isVerifiedSession = false,
  isConnected = false,
} = {}) {
  if (accessGranted) {
    return {
      headline: 'Approved wallet verified.',
      detail: 'Your approved wallet session is active and the controlled testnet should unlock now.',
      actionLabel: 'Refresh Approved Wallet Access',
    };
  }
  if (walletBound) {
    return {
      headline: 'Returning user? Connect your approved wallet.',
      detail: 'Use the same previously bound MetaMask wallet and sign to unlock without reusing the invite code.',
      actionLabel: isConnected
        ? (isVerifiedSession ? 'Refresh Approved Wallet Access' : 'Verify Approved Wallet')
        : 'Connect Approved Wallet',
    };
  }
  return {
    headline: 'Returning user? Connect your approved wallet.',
    detail: 'If this wallet was already approved before, reconnect it and sign to check access. If it was never approved, use the new-user path.',
    actionLabel: isConnected
      ? (isVerifiedSession ? 'Check Approved Wallet Access' : 'Verify Wallet')
      : 'Connect MetaMask',
  };
}
