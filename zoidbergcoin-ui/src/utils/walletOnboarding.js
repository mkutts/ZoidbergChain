import { EMBEDDED_WALLET_CONFIG } from './embeddedWalletConfig.js';

export function getWalletOnboardingOptions(config = EMBEDDED_WALLET_CONFIG) {
  const embeddedWalletWarning = !config?.isPrivySelected
    ? 'Email / Social Wallet is not configured on this deployment yet. MetaMask is currently required.'
    : (!config?.privyAppId
      ? 'Email / Social Wallet is selected for this deployment, but the public Privy app id is missing. MetaMask is currently required.'
      : 'Email / Social Wallet is coming soon. Privy\'s supported web path for this Vue app is a small React island, so MetaMask remains the only live login for now.');

  return [
    {
      id: 'metamask',
      title: 'Continue with MetaMask',
      description: 'Use this if you already have a crypto wallet.',
      availability: 'available',
    },
    {
      id: 'privy_embedded',
      title: 'Continue with Email / Social Wallet',
      description: 'Use this if you are new to wallets. This creates or connects a portable beta wallet.',
      availability: 'coming_soon',
      warning: embeddedWalletWarning,
    },
  ];
}
