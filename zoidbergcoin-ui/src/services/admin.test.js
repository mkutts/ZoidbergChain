import test from 'node:test';
import assert from 'node:assert/strict';

import { createAdminService } from './admin.js';

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

test('invalid admin login shows error and keeps dashboard locked', async () => {
  const adminApi = createMockClient();
  adminApi.postHandlers.set('/admin/login', async () => {
    const error = new Error('Unauthorized');
    error.response = {
      status: 401,
      data: {
        detail: 'Invalid admin credential.',
      },
    };
    throw error;
  });

  const admin = createAdminService({ adminApi });
  const result = await admin.login('wrong-password');

  assert.equal(result, null);
  assert.match(admin.state.errorMessage, /invalid admin credential/i);
  assert.equal(admin.state.session, null);
});

test('authenticated admin dashboard can load pending requests', async () => {
  const adminApi = createMockClient();
  adminApi.getHandlers.set('/admin/session', async () => ({
    data: {
      authenticated: true,
      admin_ui_enabled: true,
      admin_auth_enabled: true,
    },
  }));
  adminApi.getHandlers.set('/admin/access/requests?status=pending', async () => ({
    data: {
      requests: [
        {
          request_id: 'req-1',
          name: 'Pending Tester',
          email: 'pending@example.test',
          status: 'pending',
        },
      ],
    },
  }));

  const admin = createAdminService({ adminApi });
  await admin.loadSession();
  const requests = await admin.loadRequests('pending');

  assert.equal(admin.state.session.authenticated, true);
  assert.equal(requests.length, 1);
  assert.equal(admin.state.requests[0].request_id, 'req-1');
});

test('approve request shows one-time invite code', async () => {
  const adminApi = createMockClient();
  adminApi.postHandlers.set('/admin/access/requests/req-approve/approve', async () => ({
    data: {
      message: 'Access request approved.',
      warning: 'Invite codes are shown once. Copy before leaving this screen.',
      invite_code: 'ZC-APPROVE1234',
      access_account: {
        access_account_id: 'acct-approve',
        status: 'active',
      },
    },
  }));
  adminApi.getHandlers.set('/admin/access/requests?status=pending', async () => ({
    data: { requests: [] },
  }));
  adminApi.getHandlers.set('/admin/access/accounts', async () => ({
    data: { accounts: [] },
  }));

  const admin = createAdminService({ adminApi });
  const result = await admin.approveRequest('req-approve', {
    reviewed_by: 'operator',
    operator_notes: 'Approved',
    max_wallets: 1,
  });

  assert.equal(result.invite_code, 'ZC-APPROVE1234');
  assert.equal(admin.state.lastInviteCode, 'ZC-APPROVE1234');
  assert.match(admin.state.inviteWarning, /shown once/i);
});

test('account list includes bound wallets for admin review', async () => {
  const adminApi = createMockClient();
  adminApi.getHandlers.set('/admin/access/accounts', async () => ({
    data: {
      accounts: [
        {
          access_account_id: 'acct-1',
          name: 'Bound Tester',
          bound_wallets: ['0x1111111111111111111111111111111111111111'],
          wallet_count: 1,
          status: 'active',
        },
      ],
    },
  }));

  const admin = createAdminService({ adminApi });
  const accounts = await admin.loadAccounts();

  assert.equal(accounts.length, 1);
  assert.equal(accounts[0].wallet_count, 1);
  assert.equal(accounts[0].bound_wallets[0], '0x1111111111111111111111111111111111111111');
});

test('admin logout returns the UI to login state', async () => {
  const adminApi = createMockClient();
  adminApi.postHandlers.set('/admin/logout', async () => ({
    data: {
      message: 'Admin session ended.',
      authenticated: false,
    },
  }));

  const admin = createAdminService({ adminApi });
  const result = await admin.logout();

  assert.equal(result.authenticated, false);
  assert.equal(admin.state.session.authenticated, false);
  assert.equal(admin.state.requests.length, 0);
  assert.equal(admin.state.accounts.length, 0);
});
