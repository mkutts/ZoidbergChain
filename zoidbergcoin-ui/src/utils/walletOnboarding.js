export function getWalletOnboardingOptions() {
  return [
    {
      id: 'metamask',
      title: 'Continue with MetaMask',
      description: 'For users who already have a wallet.',
      availability: 'available',
    },
    {
      id: 'portable_embedded_wallet',
      title: 'Alternative login coming soon',
      description: 'Email, social, or passkey onboarding is being designed around a portable wallet path for beta.',
      availability: 'coming_soon',
      warning: 'For this beta, MetaMask is currently required.',
    },
  ];
}
