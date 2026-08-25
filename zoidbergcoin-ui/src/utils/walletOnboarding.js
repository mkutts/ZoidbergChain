import { EMBEDDED_WALLET_CONFIG } from './embeddedWalletConfig.js';

export function getWalletOnboardingOptions(config = EMBEDDED_WALLET_CONFIG) {
  const embeddedWalletWarning = !config?.isPrivySelected || !config?.privyAppId
    ? 'More login options are coming soon. MetaMask is currently the live beta login.'
    : 'Email / Social Wallet is coming soon. MetaMask remains the live beta login for now.';

  return [
    {
      id: 'metamask',
      title: 'Continue with MetaMask',
      description: 'Use this if you already have a crypto wallet.',
      availability: 'available',
    },
    {
      id: 'privy_embedded',
      title: 'Email / Social Wallet',
      description: 'A simpler wallet option for new testers.',
      availability: 'coming_soon',
      warning: embeddedWalletWarning,
    },
  ];
}
