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
  if (walletState.isVerifiedSession) {
    return `Wallet verified: ${walletState.verifiedWalletAddress}`;
  }
  if (walletState.isConnected) {
    return `Wallet connected: ${walletState.normalizedWalletAddress}. Sign the verification message to continue.`;
  }
  return 'No MetaMask wallet connected yet.';
}

export function getInviteAuthenticated(accessState = {}) {
  return Boolean(accessState?.me?.invite_authenticated || accessState?.accessSessionToken);
}

export function getControlledAccessActionState({
  mode = 'returning',
  walletState = {},
  accessState = {},
} = {}) {
  const inviteAuthenticated = getInviteAuthenticated(accessState);
  const walletBound = Boolean(accessState?.me?.wallet_bound);
  const accessGranted = Boolean(accessState?.me?.access_granted);

  if (mode === 'returning') {
    return {
      showConnect: !walletState.isConnected,
      showVerify: Boolean(walletState.isConnected && !walletState.isVerifiedSession),
      showBind: false,
      inviteAuthenticated,
      walletBound,
      accessGranted,
    };
  }

  return {
    showConnect: Boolean(inviteAuthenticated && !walletState.isConnected),
    showVerify: Boolean(inviteAuthenticated && walletState.isConnected && !walletState.isVerifiedSession),
    showBind: Boolean(
      inviteAuthenticated
      && walletState.isVerifiedSession
      && !walletBound
      && !accessGranted
    ),
    inviteAuthenticated,
    walletBound,
    accessGranted,
  };
}

export function getControlledAccessNextStepText({
  mode = 'returning',
  walletState = {},
  accessState = {},
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

  if (mode === 'returning') {
    if (!walletState.isConnected) {
      return 'Returning tester? Connect your approved wallet.';
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
  if (!walletState.isConnected) {
    return 'Connect MetaMask to continue.';
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
