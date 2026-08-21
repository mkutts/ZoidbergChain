import test from 'node:test';
import assert from 'node:assert/strict';

import { createAdminService } from './admin.js';

function createMockClient() {
  return {
    getCalls: [],
    postCalls: [],
    patchCalls: [],
    getHandlers: new Map(),
    postHandlers: new Map(),
    patchHandlers: new Map(),
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
    async patch(path, payload = null, options = {}) {
      this.patchCalls.push({ path, payload, options });
      const handler = this.patchHandlers.get(path);
      if (!handler) {
        throw new Error(`Unexpected PATCH ${path}`);
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

test('authenticated admin can load ops status and audit log', async () => {
  const adminApi = createMockClient();
  adminApi.getHandlers.set('/admin/ops/status', async () => ({
    data: {
      environment: 'testnet',
      health: { status: 'ok' },
      metrics: { chain_height: 12 },
    },
  }));
  adminApi.getHandlers.set('/admin/audit-log?limit=20&action=admin_login_success', async () => ({
    data: {
      audit_log: [
        {
          timestamp: '2026-08-21T09:00:00+00:00',
          action: 'admin_login_success',
          result: 'ok',
        },
      ],
    },
  }));

  const admin = createAdminService({ adminApi });
  const opsStatus = await admin.loadOpsStatus();
  const auditLog = await admin.loadAuditLog({ limit: 20, action: 'admin_login_success' });

  assert.equal(opsStatus.environment, 'testnet');
  assert.equal(admin.state.opsStatus.metrics.chain_height, 12);
  assert.equal(auditLog.length, 1);
  assert.equal(admin.state.auditLog[0].action, 'admin_login_success');
});

test('admin logout returns the UI to login state', async () => {
  const adminApi = createMockClient();
  adminApi.getHandlers.set('/admin/ops/status', async () => ({
    data: {
      environment: 'testnet',
      health: { status: 'ok' },
    },
  }));
  adminApi.getHandlers.set('/admin/audit-log?limit=5', async () => ({
    data: {
      audit_log: [{ action: 'admin_login_success' }],
    },
  }));
  adminApi.postHandlers.set('/admin/logout', async () => ({
    data: {
      message: 'Admin session ended.',
      authenticated: false,
    },
  }));

  const admin = createAdminService({ adminApi });
  await admin.loadOpsStatus();
  await admin.loadAuditLog({ limit: 5 });
  const result = await admin.logout();

  assert.equal(result.authenticated, false);
  assert.equal(admin.state.session.authenticated, false);
  assert.equal(admin.state.requests.length, 0);
  assert.equal(admin.state.accounts.length, 0);
  assert.equal(admin.state.opsStatus, null);
  assert.equal(admin.state.auditLog.length, 0);
});

test('admin can load and create allowlist entries', async () => {
  const adminApi = createMockClient();
  adminApi.getHandlers.set('/admin/allowlist?scope=access&status=active', async () => ({
    data: {
      allowlist_entries: [
        {
          allowlist_entry_id: 'allow-1',
          scope: 'access',
          subject_type: 'wallet',
          subject_value: '0x1111111111111111111111111111111111111111',
          normalized_subject_value: '0x1111111111111111111111111111111111111111',
          status: 'active',
          effective_status: 'active',
          diagnostic_messages: ['This wallet is currently recognized as allowlisted for app access.'],
        },
      ],
    },
  }));
  adminApi.postHandlers.set('/admin/allowlist', async () => ({
    data: {
      message: 'Allowlist entry created.',
      allowlist_entry: { allowlist_entry_id: 'allow-1', status: 'active' },
    },
  }));
  adminApi.getHandlers.set('/admin/allowlist', async () => ({
    data: { allowlist_entries: [{ allowlist_entry_id: 'allow-1', status: 'active' }] },
  }));

  const admin = createAdminService({ adminApi });
  const entries = await admin.loadAllowlist({ scope: 'access', status: 'active' });
  const created = await admin.createAllowlistEntry({
    scope: 'access',
    subject_type: 'wallet',
    subject_value: '0x1111111111111111111111111111111111111111',
  });

  assert.equal(entries.length, 1);
  assert.equal(entries[0].normalized_subject_value, '0x1111111111111111111111111111111111111111');
  assert.match(entries[0].diagnostic_messages[0], /allowlisted for app access/i);
  assert.equal(created.allowlist_entry.allowlist_entry_id, 'allow-1');
  assert.equal(admin.state.allowlistEntries[0].allowlist_entry_id, 'allow-1');
});

test('admin can revoke and reactivate allowlist entries', async () => {
  const adminApi = createMockClient();
  adminApi.postHandlers.set('/admin/allowlist/allow-2/revoke', async () => ({
    data: {
      message: 'Allowlist entry revoked.',
      allowlist_entry: { allowlist_entry_id: 'allow-2', status: 'revoked' },
    },
  }));
  adminApi.postHandlers.set('/admin/allowlist/allow-2/reactivate', async () => ({
    data: {
      message: 'Allowlist entry reactivated.',
      allowlist_entry: { allowlist_entry_id: 'allow-2', status: 'active' },
    },
  }));
  adminApi.getHandlers.set('/admin/allowlist', async () => ({
    data: { allowlist_entries: [{ allowlist_entry_id: 'allow-2', status: 'active' }] },
  }));

  const admin = createAdminService({ adminApi });
  const revoked = await admin.revokeAllowlistEntry('allow-2', { revoked_reason: 'pause' });
  const reactivated = await admin.reactivateAllowlistEntry('allow-2', { reason: 'resume' });

  assert.equal(revoked.allowlist_entry.status, 'revoked');
  assert.equal(reactivated.allowlist_entry.status, 'active');
});

test('admin can load and approve override requests', async () => {
  const adminApi = createMockClient();
  adminApi.getHandlers.set('/admin/override-requests?status=pending', async () => ({
    data: {
      override_requests: [
        {
          override_request_id: 'override-1',
          requested_scope: 'review',
          status: 'pending',
        },
      ],
    },
  }));
  adminApi.postHandlers.set('/admin/override-requests/override-1/approve', async () => ({
    data: {
      message: 'Override request approved.',
      override_request: { override_request_id: 'override-1', status: 'approved' },
      allowlist_entry: { allowlist_entry_id: 'allow-override-1', status: 'active' },
    },
  }));
  adminApi.getHandlers.set('/admin/allowlist', async () => ({
    data: { allowlist_entries: [{ allowlist_entry_id: 'allow-override-1', status: 'active' }] },
  }));

  const admin = createAdminService({ adminApi });
  const requests = await admin.loadOverrideRequests({ status: 'pending' });
  const approved = await admin.approveOverrideRequest('override-1', {
    reviewed_by: 'operator',
    admin_note: 'approved',
    resolved_scope: 'review',
  });

  assert.equal(requests.length, 1);
  assert.equal(approved.override_request.status, 'approved');
  assert.equal(admin.state.allowlistEntries[0].allowlist_entry_id, 'allow-override-1');
});

test('admin can reject override requests', async () => {
  const adminApi = createMockClient();
  adminApi.postHandlers.set('/admin/override-requests/override-2/reject', async () => ({
    data: {
      message: 'Override request rejected.',
      override_request: { override_request_id: 'override-2', status: 'rejected' },
    },
  }));
  adminApi.getHandlers.set('/admin/override-requests', async () => ({
    data: { override_requests: [] },
  }));

  const admin = createAdminService({ adminApi });
  const rejected = await admin.rejectOverrideRequest('override-2', {
    reviewed_by: 'operator',
    admin_note: 'not approved',
    resolved_scope: 'access',
  });

  assert.equal(rejected.override_request.status, 'rejected');
});

test('admin can load feedback and summary counts', async () => {
  const adminApi = createMockClient();
  adminApi.getHandlers.set('/admin/feedback?status=new&type=bug&priority=high&limit=50', async () => ({
    data: {
      summary: {
        new_feedback_count: 3,
        open_feedback_count: 4,
        high_priority_feedback_count: 2,
      },
      feedback_items: [
        {
          feedback_id: 'fb-1',
          type: 'bug',
          title: 'Mobile overlap',
          status: 'new',
          priority: 'high',
        },
      ],
    },
  }));

  const admin = createAdminService({ adminApi });
  const feedback = await admin.loadFeedback({ status: 'new', type: 'bug', priority: 'high', limit: 50 });

  assert.equal(feedback.length, 1);
  assert.equal(admin.state.feedbackItems[0].feedback_id, 'fb-1');
  assert.equal(admin.state.feedbackSummary.high_priority_feedback_count, 2);
});

test('admin can update feedback and add notes', async () => {
  const adminApi = createMockClient();
  adminApi.patchHandlers.set('/admin/feedback/fb-2', async () => ({
    data: {
      message: 'Feedback updated.',
      feedback: {
        feedback_id: 'fb-2',
        status: 'in_progress',
        priority: 'urgent',
      },
    },
  }));
  adminApi.postHandlers.set('/admin/feedback/fb-2/note', async () => ({
    data: {
      message: 'Feedback note added.',
      feedback: {
        feedback_id: 'fb-2',
        admin_notes: [
          { note_id: 'note-1', note: 'Reproduced locally.' },
        ],
      },
    },
  }));
  adminApi.getHandlers.set('/admin/feedback', async () => ({
    data: {
      summary: { new_feedback_count: 0, open_feedback_count: 1, high_priority_feedback_count: 1 },
      feedback_items: [{ feedback_id: 'fb-2', status: 'in_progress', priority: 'urgent' }],
    },
  }));

  const admin = createAdminService({ adminApi });
  const updated = await admin.updateFeedback('fb-2', {
    status: 'in_progress',
    priority: 'urgent',
    reviewed_by: 'operator',
  });
  const noted = await admin.addFeedbackNote('fb-2', {
    note: 'Reproduced locally.',
    created_by: 'operator',
  });

  assert.equal(updated.feedback.status, 'in_progress');
  assert.equal(updated.feedback.priority, 'urgent');
  assert.equal(noted.feedback.admin_notes[0].note, 'Reproduced locally.');
});
