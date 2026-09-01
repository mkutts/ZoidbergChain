const IMPORT_META_ENV = {
  MODE: import.meta.env?.MODE,
  PROD: import.meta.env?.PROD,
  VITE_API_BASE_URL: import.meta.env?.VITE_API_BASE_URL,
  VITE_API_BASE: import.meta.env?.VITE_API_BASE,
  VITE_BACKEND_URL: import.meta.env?.VITE_BACKEND_URL,
  VITE_ENVIRONMENT: import.meta.env?.VITE_ENVIRONMENT,
  VITE_APP_ENVIRONMENT: import.meta.env?.VITE_APP_ENVIRONMENT,
  VITE_PUBLIC_DEMO_MODE: import.meta.env?.VITE_PUBLIC_DEMO_MODE,
  VITE_ENABLE_DEV_TOOLS: import.meta.env?.VITE_ENABLE_DEV_TOOLS,
};

function normalizeEnvironment(rawEnvironment, env = IMPORT_META_ENV) {
  const normalized = String(rawEnvironment || '').trim().toLowerCase();
  if (['development', 'testnet', 'production'].includes(normalized)) {
    return normalized;
  }
  return env.PROD ? 'production' : 'development';
}

function envFlag(rawValue) {
  if (typeof rawValue !== 'string' || !rawValue.trim()) {
    return null;
  }
  const normalized = rawValue.trim().toLowerCase();
  if (['1', 'true', 'yes', 'on'].includes(normalized)) {
    return true;
  }
  if (['0', 'false', 'no', 'off'].includes(normalized)) {
    return false;
  }
  return null;
}

function normalizeApiBaseUrl(value) {
  return String(value || '').trim().replace(/\/+$/, '');
}

export function getAppEnvironment(env = IMPORT_META_ENV) {
  return normalizeEnvironment(
    env.VITE_ENVIRONMENT
    || env.VITE_APP_ENVIRONMENT
    || env.MODE,
    env,
  );
}

export function createDefaultApiBaseUrl(env = IMPORT_META_ENV) {
  return '/api';
}

export function resolveApiBaseUrl(env = IMPORT_META_ENV) {
  if (!env.PROD) {
    return createDefaultApiBaseUrl(env);
  }

  const configuredBaseUrl = [
    env.VITE_API_BASE_URL,
    env.VITE_API_BASE,
    env.VITE_BACKEND_URL,
  ]
    .map(normalizeApiBaseUrl)
    .find(Boolean);

  return configuredBaseUrl || createDefaultApiBaseUrl(env);
}

export function isPublicDemoMode(env = IMPORT_META_ENV) {
  const explicit = envFlag(env.VITE_PUBLIC_DEMO_MODE);
  if (explicit !== null) {
    return explicit;
  }
  return getAppEnvironment(env) !== 'development';
}

export function showDevelopmentTools(env = IMPORT_META_ENV) {
  if (isPublicDemoMode(env)) {
    return false;
  }
  const explicit = envFlag(env.VITE_ENABLE_DEV_TOOLS);
  if (explicit !== null) {
    return explicit;
  }
  return getAppEnvironment(env) === 'development';
}

export function publicDemoBannerLines() {
  return [
    'ZoidbergChain controlled testnet',
    'Test ZOID has no real monetary value',
    'This network may reset',
    'Not mainnet',
    'Wallets are used for identity and signatures',
    'Native ZOID lives on ZoidbergChain, not Ethereum',
    'Never enter a seed phrase or private key in this app',
  ];
}
