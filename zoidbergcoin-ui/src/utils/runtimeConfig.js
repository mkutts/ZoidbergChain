const IMPORT_META_ENV = import.meta?.env || {};

function normalizeEnvironment(rawEnvironment) {
  const normalized = String(rawEnvironment || '').trim().toLowerCase();
  if (['development', 'testnet', 'production'].includes(normalized)) {
    return normalized;
  }
  return IMPORT_META_ENV.PROD ? 'production' : 'development';
}

export function getAppEnvironment() {
  return normalizeEnvironment(
    IMPORT_META_ENV.VITE_ENVIRONMENT
    || IMPORT_META_ENV.VITE_APP_ENVIRONMENT
    || IMPORT_META_ENV.MODE,
  );
}

export function isPublicDemoMode() {
  const explicit = IMPORT_META_ENV.VITE_PUBLIC_DEMO_MODE;
  if (typeof explicit === 'string' && explicit.trim()) {
    return ['1', 'true', 'yes', 'on'].includes(explicit.trim().toLowerCase());
  }
  return getAppEnvironment() !== 'development';
}

export function showDevelopmentTools() {
  const explicit = IMPORT_META_ENV.VITE_ENABLE_DEV_TOOLS;
  if (typeof explicit === 'string' && explicit.trim()) {
    return ['1', 'true', 'yes', 'on'].includes(explicit.trim().toLowerCase());
  }
  return getAppEnvironment() === 'development' && !isPublicDemoMode();
}

export function publicDemoBannerLines() {
  return [
    'ZoidbergChain controlled testnet',
    'Test ZOID has no real monetary value',
    'This network may reset',
    'Not mainnet',
    'Native ZOID lives on ZoidbergChain, not Ethereum',
    'MetaMask signs ZoidbergChain actions',
  ];
}
