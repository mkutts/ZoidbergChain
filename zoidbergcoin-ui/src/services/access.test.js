import test from 'node:test';
import assert from 'node:assert/strict';
import { createAccessService } from './access.js';

function createMemoryStorage() {
  const values = new Map();
  return {
    getItem(key) {
      return values.has(key) ? values.get(key) : null;
    },
    setItem(key, value) {
      values.set(key, value);
    },
    removeItem(key) {
      values.delete(key);
    },
  };
}

function createMockClient() {
  return {
    getCalls: [],
    postCalls: [],
    getHandlers: new Map(),
    postHandlers: new Map(),
    async get(path, options = {}) {
      this.getCalls.push({ path, options });
      const handler = this.getHandlers.get(path);
      if (!handler) {
        throw new Error(`Unexpected GET ${path}`);
      }
      return handler(options);
    },
    async post(path, payload = null, options = {}) {
      this.postCalls.push({ path, payload, options });
      const handler = this.postHandlers.get(path);
      if (!handler) {
        throw new Error(`Unexpected POST ${path}`);
      }
      return handler(payload, options);
    },
  };
}

function setEligibilityHandler(publicApi, payload = {}) {
  publicApi.getHandlers.set('/eligibility/status', async () => ({
    data: {
      access_granted: Boolean(payload.access_granted),
      connected_wallet: payload.connected_wallet || null,
      wallet_bound: Boolean(payload.wallet_bound),
      can_submit: Boolean(payload.can_submit),
      can_vote: Boolean(payload.can_vote),
      can_receive_rewards: Boolean(payload.can_receive_rewards),
      blocked_reasons: payload.blocked_reasons || [],
      allowlist_overrides_applied: payload.allowlist_overrides_applied || [],
      possible_next_steps: payload.possible_next_steps || [],
      override_requests_enabled: payload.override_requests_enabled !== false,
      submission: payload.submission || {
        can_submit: Boolean(payload.can_submit),
        eligibility_status: payload.can_submit ? 'eligible' : 'blocked',
        eligibility_source: payload.can_submit ? 'normal_access_verified_wallet' : 'blocked',
        blocked_reason: payload.can_submit ? null : (payload.blocked_reasons?.[0]?.reason || null),
        message: payload.can_submit
          ? 'Submission is allowed because this wallet has controlled beta access and the wallet session is verified.'
          : 'Submission is currently blocked.',
        recommended_action: null,
        policy_rule: 'Submissions currently require controlled beta access for submissions plus a verified wallet session.',
        allowlist_override_applied: false,
        allowlist_scope: null,
      },
    },
  }));
}

test('development-style public status does not gate the app', async () => {
  const publicApi = createMockClient();
  const api = createMockClient();

  publicApi.getHandlers.set('/access/status', async () => ({
    data: {
      require_access_for_app: false,
      access_requests_enabled: true,
      access_control_mode: 'open',
    },
  }));
  publicApi.getHandlers.set('/access/me', async () => ({
    data: {
      access_granted: false,
      access_account: null,
      wallet_binding: null,
    },
  }));
  setEligibilityHandler(publicApi);

  const access = createAccessService({
    api,
    publicApi,
    storage: createMemoryStorage(),
  });

  await access.initialize();

  assert.equal(access.requiresAppAccess(), false);
  assert.equal(access.isAppUnlocked(), true);
  assert.equal(access.state.errorMessage, '');
});

test('invite login stores the access session token for later app unlocks', async () => {
  const publicApi = createMockClient();
  const api = createMockClient();
  const storage = createMemoryStorage();
  publicApi.getHandlers.set('/access/status', async () => ({
    data: {
      require_access_for_app: true,
      access_requests_enabled: true,
      access_control_mode: 'invite_only',
    },
  }));

  publicApi.postHandlers.set('/access/login', async () => ({
    data: {
      message: 'Invite accepted.',
      access_session_token: 'access-session-1',
      access_account: {
        access_account_id: 'acct-1',
        status: 'active',
      },
    },
  }));
  publicApi.getHandlers.set('/access/me', async () => ({
    data: {
      invite_authenticated: true,
      wallet_bound: false,
      access_granted: false,
      access_account: {
        access_account_id: 'acct-1',
        status: 'active',
      },
      wallet_binding: null,
    },
  }));
  setEligibilityHandler(publicApi, {
    blocked_reasons: [{ scope: 'access', reason: 'wallet_not_bound' }],
  });

  const access = createAccessService({
    api,
    publicApi,
    storage,
  });

  await access.loadPublicStatus();
  const result = await access.loginWithCode('ZC-TESTCODE');

  assert.equal(result.access_session_token, 'access-session-1');
  assert.equal(access.state.accessSessionToken, 'access-session-1');
  assert.equal(storage.getItem('zoidberg:access-session'), 'access-session-1');
  assert.equal(access.state.me.invite_authenticated, true);
  assert.equal(access.state.me.wallet_bound, false);
  assert.equal(access.isAppUnlocked(), false);
  assert.deepEqual(access.getAccessHeaders(), {
    'X-ZOID-Access-Session': 'access-session-1',
  });
});

test('binding a wallet sends access-session and wallet auth headers together', async () => {
  const publicApi = createMockClient();
  const api = createMockClient();
  const storage = createMemoryStorage();
  storage.setItem('zoidberg:access-session', 'access-session-2');
  publicApi.getHandlers.set('/access/status', async () => ({
    data: {
      require_access_for_app: true,
      access_control_mode: 'invite_only',
    },
  }));

  publicApi.getHandlers.set('/access/me', async (options) => ({
    data: {
      invite_authenticated: false,
      wallet_bound: true,
      access_granted: true,
      access_account: {
        access_account_id: 'acct-2',
        status: 'active',
      },
      wallet_binding: {
        wallet_address: '0xabcdefabcdefabcdefabcdefabcdefabcdef1234',
        status: 'active',
      },
      echoed_headers: options.headers,
    },
  }));
  setEligibilityHandler(publicApi, {
    access_granted: true,
    wallet_bound: true,
    can_submit: true,
    can_vote: true,
    can_receive_rewards: true,
  });

  api.postHandlers.set('/access/bind-wallet', async (_payload, options) => ({
    data: {
      message: 'Wallet bound.',
      headers_seen: options.headers,
      access: {
        invite_authenticated: true,
        wallet_bound: true,
        access_granted: true,
        access_account: {
          access_account_id: 'acct-2',
          status: 'active',
        },
        wallet_binding: {
          wallet_address: '0xabcdefabcdefabcdefabcdefabcdefabcdef1234',
          status: 'active',
        },
      },
    },
  }));

  const access = createAccessService({
    api,
    publicApi,
    storage,
  });

  await access.initialize({
    Authorization: 'Bearer wallet-session-1',
  });

  const result = await access.bindWallet({
    Authorization: 'Bearer wallet-session-1',
  });

  assert.deepEqual(result.headers_seen, {
    'X-ZOID-Access-Session': 'access-session-2',
    Authorization: 'Bearer wallet-session-1',
  });
  assert.equal(access.state.me.access_granted, true);
  assert.equal(access.state.accessSessionToken, '');
  assert.equal(storage.getItem('zoidberg:access-session'), null);
  assert.equal(access.isAppUnlocked(), true);
});

test('invite acceptance alone does not unlock a gated app', async () => {
  const publicApi = createMockClient();
  const api = createMockClient();
  const storage = createMemoryStorage();

  publicApi.getHandlers.set('/access/status', async () => ({
    data: {
      require_access_for_app: true,
      access_control_mode: 'invite_only',
    },
  }));
  publicApi.postHandlers.set('/access/login', async () => ({
    data: {
      message: 'Invite accepted.',
      access_session_token: 'access-session-3',
      access_account: {
        access_account_id: 'acct-3',
        status: 'active',
      },
    },
  }));
  publicApi.getHandlers.set('/access/me', async () => ({
    data: {
      invite_authenticated: true,
      wallet_bound: false,
      access_granted: false,
      access_account: {
        access_account_id: 'acct-3',
        status: 'active',
      },
      wallet_binding: null,
    },
  }));
  setEligibilityHandler(publicApi, {
    blocked_reasons: [{ scope: 'access', reason: 'wallet_not_bound' }],
  });

  const access = createAccessService({
    api,
    publicApi,
    storage,
  });

  await access.loadPublicStatus();
  await access.loginWithCode('ZC-LOCKED');

  assert.equal(access.requiresAppAccess(), true);
  assert.equal(access.state.me.invite_authenticated, true);
  assert.equal(access.state.me.wallet_bound, false);
  assert.equal(access.isAppUnlocked(), false);
});

test('previously bound wallet can reconnect and unlock without invite code', async () => {
  const publicApi = createMockClient();
  const api = createMockClient();
  const storage = createMemoryStorage();

  publicApi.getHandlers.set('/access/status', async () => ({
    data: {
      require_access_for_app: true,
      access_control_mode: 'invite_only',
    },
  }));
  publicApi.getHandlers.set('/access/me', async (options) => ({
    data: {
      invite_authenticated: false,
      wallet_session_authenticated: true,
      wallet_bound: true,
      access_granted: true,
      access_account: {
        access_account_id: 'acct-returning',
        status: 'active',
      },
      wallet_binding: {
        wallet_address: '0xabcdefabcdefabcdefabcdefabcdefabcdef1234',
        status: 'active',
      },
      echoed_headers: options.headers,
    },
  }));
  setEligibilityHandler(publicApi, {
    access_granted: true,
    wallet_bound: true,
    can_submit: true,
    can_vote: true,
    can_receive_rewards: true,
  });

  const access = createAccessService({
    api,
    publicApi,
    storage,
  });

  await access.initialize({
    Authorization: 'Bearer returning-wallet-session',
  });

  assert.equal(access.state.accessSessionToken, '');
  assert.equal(access.state.me.invite_authenticated, false);
  assert.equal(access.state.me.wallet_bound, true);
  assert.equal(access.state.me.access_granted, true);
  assert.equal(access.isAppUnlocked(), true);
});

test('unapproved wallet stays locked even after wallet verification refresh', async () => {
  const publicApi = createMockClient();
  const api = createMockClient();

  publicApi.getHandlers.set('/access/status', async () => ({
    data: {
      require_access_for_app: true,
      access_control_mode: 'invite_only',
    },
  }));
  publicApi.getHandlers.set('/access/me', async () => ({
    data: {
      invite_authenticated: false,
      wallet_session_authenticated: true,
      wallet_bound: false,
      access_granted: false,
      access_account: null,
      wallet_binding: null,
    },
  }));
  setEligibilityHandler(publicApi, {
    blocked_reasons: [{ scope: 'access', reason: 'wallet_not_bound' }],
  });

  const access = createAccessService({
    api,
    publicApi,
    storage: createMemoryStorage(),
  });

  await access.initialize({
    Authorization: 'Bearer unapproved-wallet-session',
  });

  assert.equal(access.state.me.wallet_bound, false);
  assert.equal(access.state.me.access_granted, false);
  assert.equal(access.isAppUnlocked(), false);
});

test('401 access session responses clear the cached invite session token', async () => {
  const publicApi = createMockClient();
  const api = createMockClient();
  const storage = createMemoryStorage();
  storage.setItem('zoidberg:access-session', 'stale-token');

  publicApi.getHandlers.set('/access/status', async () => ({
    data: {
      require_access_for_app: true,
      access_control_mode: 'invite_only',
    },
  }));
  publicApi.getHandlers.set('/access/me', async () => {
    const error = new Error('Expired');
    error.response = {
      status: 401,
      data: {
        detail: 'No active access session found.',
      },
    };
    throw error;
  });
  publicApi.getHandlers.set('/eligibility/status', async () => ({
    data: {
      access_granted: false,
      wallet_bound: false,
      blocked_reasons: [],
      allowlist_overrides_applied: [],
      possible_next_steps: [],
      override_requests_enabled: true,
    },
  }));

  const access = createAccessService({
    api,
    publicApi,
    storage,
  });

  await access.initialize();

  assert.equal(access.state.accessSessionToken, '');
  assert.equal(storage.getItem('zoidberg:access-session'), null);
  assert.match(access.state.errorMessage, /no active access session/i);
});

test('override request submits through the shared access service and refreshes eligibility', async () => {
  const publicApi = createMockClient();
  const api = createMockClient();
  const storage = createMemoryStorage();
  storage.setItem('zoidberg:access-session', 'override-session');

  publicApi.postHandlers.set('/eligibility/override-requests', async (payload, options) => ({
    data: {
      message: 'Override request submitted.',
      echoedPayload: payload,
      echoedHeaders: options.headers,
    },
  }));
  setEligibilityHandler(publicApi, {
    blocked_reasons: [{ scope: 'voting', reason: 'wallet_not_allowlisted' }],
    possible_next_steps: ['Ask an admin for a review override.'],
  });

  const access = createAccessService({
    api,
    publicApi,
    storage,
  });

  const result = await access.submitOverrideRequest(
    {
      requested_scope: 'voting',
      reason: 'Need early beta voting access',
    },
    { Authorization: 'Bearer wallet-session' },
  );

  assert.equal(result.message, 'Override request submitted.');
  assert.deepEqual(result.echoedHeaders, {
    'X-ZOID-Access-Session': 'override-session',
    Authorization: 'Bearer wallet-session',
  });
  assert.equal(access.state.eligibility.blocked_reasons[0].scope, 'voting');
});

test('submission eligibility details are preserved from the backend payload', async () => {
  const publicApi = createMockClient();
  const api = createMockClient();

  publicApi.getHandlers.set('/access/status', async () => ({
    data: {
      require_access_for_app: true,
      access_control_mode: 'invite_only',
    },
  }));
  publicApi.getHandlers.set('/access/me', async () => ({
    data: {
      invite_authenticated: false,
      wallet_session_authenticated: true,
      wallet_bound: true,
      access_granted: true,
      access_account: {
        access_account_id: 'acct-submit',
        status: 'active',
      },
      wallet_binding: {
        wallet_address: '0xabcdefabcdefabcdefabcdefabcdefabcdef1234',
        status: 'active',
      },
    },
  }));
  setEligibilityHandler(publicApi, {
    access_granted: true,
    wallet_bound: true,
    can_submit: true,
    submission: {
      can_submit: true,
      eligibility_status: 'eligible',
      eligibility_source: 'normal_access_verified_wallet',
      blocked_reason: null,
      message: 'Submission is allowed because this wallet has controlled beta access and the wallet session is verified.',
      recommended_action: null,
      policy_rule: 'Submissions currently require controlled beta access for submissions plus a verified wallet session. This node does not apply a separate submission-only override gate.',
      allowlist_override_applied: false,
      allowlist_scope: null,
    },
  });

  const access = createAccessService({
    api,
    publicApi,
    storage: createMemoryStorage(),
  });

  await access.initialize({
    Authorization: 'Bearer submission-wallet-session',
  });

  assert.equal(access.state.eligibility.submission.can_submit, true);
  assert.equal(access.state.eligibility.submission.eligibility_source, 'normal_access_verified_wallet');
  assert.match(access.state.eligibility.submission.policy_rule, /does not apply a separate submission-only override gate/i);
});
