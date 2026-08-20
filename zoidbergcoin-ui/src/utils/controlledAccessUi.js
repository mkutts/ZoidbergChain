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
    return `Verified wallet ${walletState.verifiedWalletAddress}`;
  }
  if (walletState.isConnected) {
    return `Connected wallet ${walletState.normalizedWalletAddress}. Sign the verification challenge to continue.`;
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
      return 'Returning user? Connect your approved wallet.';
    }
    if (!walletState.isVerifiedSession) {
      return 'Returning user? Sign the wallet verification challenge to check whether this wallet is already approved.';
    }
    if (bindingStatus === 'revoked') {
      return 'This wallet binding was revoked. Request access or enter a fresh invite code from the operator.';
    }
    if (accountStatus === 'suspended') {
      return 'This approved wallet belongs to a suspended access account. Contact the operator for reactivation.';
    }
    if (accountStatus === 'revoked') {
      return 'This approved wallet belongs to a revoked access account. Contact the operator before trying again.';
    }
    if (accessGranted || (walletBound && isActiveAccount(accessState))) {
      return 'Approved wallet verified. Loading controlled testnet access.';
    }
    if (walletSessionAuthenticated) {
      return 'This wallet is not approved. Request access or enter an invite code.';
    }
    return 'Sign the wallet verification challenge to continue.';
  }

  if (!inviteAuthenticated) {
    return 'Enter your invite code first. Wallet binding only starts after the invite is accepted.';
  }
  if (!walletState.isConnected) {
    return 'Connect MetaMask to continue.';
  }
  if (!walletState.isVerifiedSession) {
    return 'Verify this MetaMask wallet before binding it to the approved access account.';
  }
  if (!walletBound) {
    return 'Bind the first verified MetaMask wallet to the approved access account.';
  }
  if (accessGranted) {
    return 'This MetaMask wallet is already bound to the approved access account.';
  }
  return 'This approved account is not active right now. Contact the operator for help.';
}
