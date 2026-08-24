function isActiveAccount(accessState = {}) {
  const status = String(
    accessState?.me?.access_account?.status
    || accessState?.me?.status
    || '',
  ).trim().toLowerCase();
  return status === 'active';
}

function walletBindingStatus(accessState = {}) {
  return String(accessState?.me?.wallet_binding?.status || '').trim().toLowerCase();
}

export function getAccessGateWalletStatusText(walletState = {}) {
  const providerLabel = walletState?.providerLabel || 'wallet';
  if (walletState.isVerifiedSession) {
    return `${providerLabel} verified: ${walletState.verifiedWalletAddress}`;
  }
  if (walletState.isConnected) {
    return `${providerLabel} connected: ${walletState.normalizedWalletAddress}. Sign the verification message to continue.`;
  }
  return 'No wallet connected yet.';
}

export function getInviteAuthenticated(accessState = {}) {
  return Boolean(accessState?.me?.invite_authenticated || accessState?.accessSessionToken);
}

export function getControlledAccessActionState({
  mode = 'returning',
  walletState = {},
  accessState = {},
  selectedProviderId = '',
} = {}) {
  const inviteAuthenticated = getInviteAuthenticated(accessState);
  const walletBound = Boolean(accessState?.me?.wallet_bound);
  const accessGranted = Boolean(accessState?.me?.access_granted);
  const normalizedSelectedProviderId = String(selectedProviderId || '').trim();
  const providerMatchesSelection = Boolean(
    normalizedSelectedProviderId
    && walletState?.providerId === normalizedSelectedProviderId,
  );
  const selectedProviderConnected = Boolean(
    normalizedSelectedProviderId
    && providerMatchesSelection
    && walletState.isConnected,
  );
  const selectedProviderVerified = Boolean(
    normalizedSelectedProviderId
    && providerMatchesSelection
    && walletState.isVerifiedSession,
  );

  if (mode === 'returning') {
    return {
      showProviderChooser: !normalizedSelectedProviderId && !walletState.isVerifiedSession,
      showConnect: Boolean(normalizedSelectedProviderId && !selectedProviderConnected && !selectedProviderVerified),
      showVerify: Boolean(selectedProviderConnected && !selectedProviderVerified),
      showBind: false,
      inviteAuthenticated,
      walletBound,
      accessGranted,
      selectedProviderId: normalizedSelectedProviderId,
    };
  }

  return {
    showProviderChooser: Boolean(
      inviteAuthenticated
      && !walletBound
      && !accessGranted
      && !normalizedSelectedProviderId,
    ),
    showConnect: Boolean(
      inviteAuthenticated
      && !walletBound
      && !accessGranted
      && normalizedSelectedProviderId
      && !selectedProviderConnected
      && !selectedProviderVerified,
    ),
    showVerify: Boolean(
      inviteAuthenticated
      && !walletBound
      && !accessGranted
      && selectedProviderConnected
      && !selectedProviderVerified,
    ),
    showBind: Boolean(
      inviteAuthenticated
      && normalizedSelectedProviderId
      && selectedProviderVerified
      && !walletBound
      && !accessGranted
    ),
    inviteAuthenticated,
    walletBound,
    accessGranted,
    selectedProviderId: normalizedSelectedProviderId,
  };
}

export function getControlledAccessNextStepText({
  mode = 'returning',
  walletState = {},
  accessState = {},
  selectedProviderId = '',
} = {}) {
  const inviteAuthenticated = getInviteAuthenticated(accessState);
  const bindingStatus = walletBindingStatus(accessState);
  const accountStatus = String(
    accessState?.me?.access_account?.status
    || accessState?.me?.status
    || '',
  ).trim().toLowerCase();
  const walletSessionAuthenticated = Boolean(accessState?.me?.wallet_session_authenticated);
  const walletBound = Boolean(accessState?.me?.wallet_bound);
  const accessGranted = Boolean(accessState?.me?.access_granted);
  const normalizedSelectedProviderId = String(selectedProviderId || '').trim();
  const selectedProviderConnected = Boolean(
    normalizedSelectedProviderId
    && walletState?.providerId === normalizedSelectedProviderId
    && walletState.isConnected,
  );

  if (mode === 'returning') {
    if (!normalizedSelectedProviderId && !walletState.isVerifiedSession) {
      return 'Choose how you want to connect your approved wallet.';
    }
    if (!walletState.isConnected) {
      return 'Continue with your selected wallet method to connect your approved wallet.';
    }
    if (!selectedProviderConnected && !walletState.isVerifiedSession) {
      return 'Reconnect with the wallet method you selected so we can continue.';
    }
    if (!walletState.isVerifiedSession) {
      return 'Sign the wallet verification message so we can confirm this approved wallet.';
    }
    if (bindingStatus === 'revoked') {
      return 'This wallet connection was revoked. Ask the team for help or use a fresh invite if you were re-approved.';
    }
    if (accountStatus === 'suspended') {
      return 'This wallet belongs to a suspended beta account. Contact the team for reactivation.';
    }
    if (accountStatus === 'revoked') {
      return 'This wallet belongs to a revoked beta account. Contact the team before trying again.';
    }
    if (accessGranted || (walletBound && isActiveAccount(accessState))) {
      return 'Approved wallet verified. Opening the beta app.';
    }
    if (walletSessionAuthenticated) {
      return 'This wallet is verified, but it is not approved for beta access yet.';
    }
    return 'Sign the wallet verification message to continue.';
  }

  if (!inviteAuthenticated) {
    return 'Start with your invite code. Wallet setup begins after the invite is accepted.';
  }
  if (!normalizedSelectedProviderId) {
    return 'Choose how you want to connect your wallet before verifying it.';
  }
  if (!walletState.isConnected) {
    return 'Continue with your selected wallet method to connect the wallet you want to bind.';
  }
  if (!selectedProviderConnected && !walletState.isVerifiedSession) {
    return 'Reconnect with the wallet method you selected so we can verify the right wallet.';
  }
  if (!walletState.isVerifiedSession) {
    return 'Verify this wallet before linking it to your approved beta access.';
  }
  if (!walletBound) {
    return 'Finish setup by binding this verified wallet to your approved beta access.';
  }
  if (accessGranted) {
    return 'This wallet is already linked and ready for the beta app.';
  }
  return 'This approved account is not active right now. Contact the team for help.';
}
