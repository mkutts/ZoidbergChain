import test from 'node:test';
import assert from 'node:assert/strict';

import {
  getAccessGateWalletStatusText,
  getControlledAccessActionState,
  getControlledAccessNextStepText,
} from './controlledAccessUi.js';

test('access gate shows returning-user wallet login path', () => {
  const state = getControlledAccessActionState({
    mode: 'returning',
    walletState: {
      isConnected: false,
      isVerifiedSession: false,
      providerId: 'metamask',
    },
    accessState: {
      me: null,
      accessSessionToken: '',
    },
  });

  assert.equal(state.showProviderChooser, true);
  assert.equal(state.showConnect, false);
  assert.equal(state.showVerify, false);
  assert.equal(state.showBind, false);
  assert.match(
    getControlledAccessNextStepText({
      mode: 'returning',
      walletState: {
        isConnected: false,
        isVerifiedSession: false,
        providerId: 'metamask',
      },
      accessState: {
        me: null,
        accessSessionToken: '',
      },
    }),
    /choose how you want to connect your approved wallet/i,
  );
});

test('invite flow keeps the provider chooser visible until a wallet method is explicitly selected', () => {
  const state = getControlledAccessActionState({
    mode: 'login',
    walletState: {
      isConnected: true,
      isVerifiedSession: false,
      providerId: 'metamask',
    },
    accessState: {
      accessSessionToken: 'access-session-1',
      me: {
        invite_authenticated: true,
        wallet_bound: false,
        access_granted: false,
      },
    },
    selectedProviderId: '',
  });

  assert.equal(state.showProviderChooser, true);
  assert.equal(state.showConnect, false);
  assert.equal(state.showVerify, false);
  assert.equal(state.showBind, false);
  assert.match(
    getControlledAccessNextStepText({
      mode: 'login',
      walletState: {
        isConnected: true,
        isVerifiedSession: false,
        providerId: 'metamask',
      },
      accessState: {
        accessSessionToken: 'access-session-1',
        me: {
          invite_authenticated: true,
          wallet_bound: false,
          access_granted: false,
        },
      },
      selectedProviderId: '',
    }),
    /choose how you want to connect your wallet before verifying it/i,
  );
});

test('invite flow only advances to verification after the user selects MetaMask explicitly', () => {
  const state = getControlledAccessActionState({
    mode: 'login',
    walletState: {
      isConnected: true,
      isVerifiedSession: false,
      providerId: 'metamask',
    },
    accessState: {
      accessSessionToken: 'access-session-1',
      me: {
        invite_authenticated: true,
        wallet_bound: false,
        access_granted: false,
      },
    },
    selectedProviderId: 'metamask',
  });

  assert.equal(state.showProviderChooser, false);
  assert.equal(state.showConnect, false);
  assert.equal(state.showVerify, true);
  assert.equal(state.showBind, false);
});

test('invite flow keeps Email / Social Wallet visible even when MetaMask is already connected', () => {
  const state = getControlledAccessActionState({
    mode: 'login',
    walletState: {
      isConnected: true,
      isVerifiedSession: false,
      providerId: 'metamask',
    },
    accessState: {
      accessSessionToken: 'access-session-1',
      me: {
        invite_authenticated: true,
        wallet_bound: false,
        access_granted: false,
      },
    },
    selectedProviderId: 'privy_embedded',
  });

  assert.equal(state.showProviderChooser, false);
  assert.equal(state.showConnect, true);
  assert.equal(state.showVerify, false);
  assert.equal(state.showBind, false);
});

test('previously bound wallet can reconnect and unlock without invite code prompt', () => {
  const nextStep = getControlledAccessNextStepText({
    mode: 'returning',
    walletState: {
      isConnected: true,
      isVerifiedSession: true,
      verifiedWalletAddress: '0xabc',
    },
    accessState: {
      accessSessionToken: '',
      me: {
        wallet_session_authenticated: true,
        wallet_bound: true,
        access_granted: true,
        access_account: { status: 'active' },
        wallet_binding: { status: 'active' },
      },
    },
  });

  assert.match(nextStep, /opening the beta app/i);
  assert.doesNotMatch(nextStep, /invite code/i);
});

test('unapproved wallet stays locked', () => {
  const nextStep = getControlledAccessNextStepText({
    mode: 'returning',
    walletState: {
      isConnected: true,
      isVerifiedSession: true,
      verifiedWalletAddress: '0xdef',
    },
    accessState: {
      accessSessionToken: '',
      me: {
        wallet_session_authenticated: true,
        wallet_bound: false,
        access_granted: false,
        access_account: null,
        wallet_binding: null,
      },
    },
  });

  assert.match(nextStep, /not approved for beta access/i);
});

test('disconnect path clears wallet session locally without implying invite reuse', () => {
  const nextStep = getControlledAccessNextStepText({
    mode: 'returning',
    walletState: {
      isConnected: false,
      isVerifiedSession: false,
      providerId: 'metamask',
    },
    accessState: {
      accessSessionToken: '',
      me: null,
    },
  });

  assert.match(nextStep, /choose how you want to connect your approved wallet/i);
  assert.doesNotMatch(nextStep, /enter your invite code first/i);
});

test('new-user invite flow still exposes invite-first bind guidance', () => {
  const nextStep = getControlledAccessNextStepText({
    mode: 'login',
    walletState: {
      isConnected: false,
      isVerifiedSession: false,
    },
    accessState: {
      accessSessionToken: '',
      me: null,
    },
  });

  assert.match(nextStep, /start with your invite code/i);
});

test('suspended or revoked returning wallets show clear denial copy', () => {
  const suspended = getControlledAccessNextStepText({
    mode: 'returning',
    walletState: {
      isConnected: true,
      isVerifiedSession: true,
    },
    accessState: {
      me: {
        wallet_session_authenticated: true,
        wallet_bound: false,
        access_granted: false,
        access_account: { status: 'suspended' },
        wallet_binding: { status: 'active' },
      },
    },
  });
  const revokedBinding = getControlledAccessNextStepText({
    mode: 'returning',
    walletState: {
      isConnected: true,
      isVerifiedSession: true,
    },
    accessState: {
      me: {
        wallet_session_authenticated: true,
        wallet_bound: false,
        access_granted: false,
        access_account: { status: 'active' },
        wallet_binding: { status: 'revoked' },
      },
    },
  });

  assert.match(suspended, /suspended beta account/i);
  assert.match(revokedBinding, /connection was revoked/i);
});

test('wallet status text stays friendly for connected and verified returning users', () => {
  assert.match(
    getAccessGateWalletStatusText({
      isConnected: true,
      isVerifiedSession: false,
      providerLabel: 'MetaMask',
      normalizedWalletAddress: '0x1234',
    }),
    /metamask connected: 0x1234/i,
  );
  assert.match(
    getAccessGateWalletStatusText({
      isConnected: true,
      isVerifiedSession: true,
      providerLabel: 'Email \/ Social Wallet',
      verifiedWalletAddress: '0x5678',
    }),
    /email \/ social wallet verified: 0x5678/i,
  );
});

test('invite-authenticated users are prompted to choose either wallet path', () => {
  const nextStep = getControlledAccessNextStepText({
    mode: 'login',
    walletState: {
      isConnected: false,
      isVerifiedSession: false,
    },
    accessState: {
      accessSessionToken: 'invite-session',
      me: {
        invite_authenticated: true,
      },
    },
  });

  assert.match(nextStep, /choose how you want to connect your wallet/i);
});
