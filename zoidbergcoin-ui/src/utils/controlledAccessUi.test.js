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
    },
    accessState: {
      me: null,
      accessSessionToken: '',
    },
  });

  assert.equal(state.showConnect, true);
  assert.equal(state.showVerify, false);
  assert.equal(state.showBind, false);
  assert.match(
    getControlledAccessNextStepText({
      mode: 'returning',
      walletState: {
        isConnected: false,
        isVerifiedSession: false,
      },
      accessState: {
        me: null,
        accessSessionToken: '',
      },
    }),
    /returning user\? connect your approved wallet/i,
  );
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

  assert.match(nextStep, /approved wallet verified/i);
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

  assert.match(nextStep, /wallet is not approved/i);
});

test('disconnect path clears wallet session locally without implying invite reuse', () => {
  const nextStep = getControlledAccessNextStepText({
    mode: 'returning',
    walletState: {
      isConnected: false,
      isVerifiedSession: false,
    },
    accessState: {
      accessSessionToken: '',
      me: null,
    },
  });

  assert.match(nextStep, /connect your approved wallet/i);
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

  assert.match(nextStep, /enter your invite code first/i);
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

  assert.match(suspended, /suspended access account/i);
  assert.match(revokedBinding, /binding was revoked/i);
});

test('wallet status text stays friendly for connected and verified returning users', () => {
  assert.match(
    getAccessGateWalletStatusText({
      isConnected: true,
      isVerifiedSession: false,
      normalizedWalletAddress: '0x1234',
    }),
    /connected wallet 0x1234/i,
  );
  assert.match(
    getAccessGateWalletStatusText({
      isConnected: true,
      isVerifiedSession: true,
      verifiedWalletAddress: '0x5678',
    }),
    /verified wallet 0x5678/i,
  );
});
