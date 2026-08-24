const IMPORT_META_ENV = {
  VITE_EMBEDDED_WALLET_PROVIDER: typeof import.meta !== 'undefined' && import.meta.env
    ? import.meta.env.VITE_EMBEDDED_WALLET_PROVIDER
    : undefined,
  VITE_PRIVY_APP_ID: typeof import.meta !== 'undefined' && import.meta.env
    ? import.meta.env.VITE_PRIVY_APP_ID
    : undefined,
  VITE_PRIVY_CLIENT_ID: typeof import.meta !== 'undefined' && import.meta.env
    ? import.meta.env.VITE_PRIVY_CLIENT_ID
    : undefined,
  VITE_PRIVY_SOCIAL_PROVIDER: typeof import.meta !== 'undefined' && import.meta.env
    ? import.meta.env.VITE_PRIVY_SOCIAL_PROVIDER
    : undefined,
};

function normalizeValue(value) {
  return String(value || '').trim();
}

export function resolveEmbeddedWalletConfig(importMetaEnv = {}) {
  const provider = normalizeValue(importMetaEnv.VITE_EMBEDDED_WALLET_PROVIDER).toLowerCase();
  const privyAppId = normalizeValue(importMetaEnv.VITE_PRIVY_APP_ID);
  const privyClientId = normalizeValue(importMetaEnv.VITE_PRIVY_CLIENT_ID);
  const socialProvider = normalizeValue(importMetaEnv.VITE_PRIVY_SOCIAL_PROVIDER).toLowerCase();
  const isPrivySelected = provider === 'privy';
  const hasRequiredPrivyPublicConfig = isPrivySelected && Boolean(privyAppId);

  return {
    provider,
    isPrivySelected,
    isConfigured: hasRequiredPrivyPublicConfig,
    hasRequiredPrivyPublicConfig,
    isSupportedInVueApp: false,
    integrationStatus: isPrivySelected ? 'deferred' : 'disabled',
    providerLabel: isPrivySelected ? 'Privy Embedded Wallet' : '',
    authOptionLabel: 'Email / Social Wallet',
    privyAppId,
    privyClientId,
    socialProvider,
    supportsSocialLogin: Boolean(socialProvider),
    portabilityHelpUrl: 'https://docs.privy.io/wallets/wallets/export',
    portabilityHelpCopy: 'Privy supports embedded wallet export and recovery flows. Use the provider portability flow before any mainnet-value launch.',
  };
}

export const EMBEDDED_WALLET_CONFIG = resolveEmbeddedWalletConfig(IMPORT_META_ENV);
