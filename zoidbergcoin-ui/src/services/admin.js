import { reactive, readonly } from 'vue';
import { adminApiClient, getApiErrorMessage } from '../config/api.js';

function createInitialState() {
  return {
    session: null,
    requests: [],
    accounts: [],
    allowlistEntries: [],
    overrideRequests: [],
    feedbackItems: [],
    feedbackSummary: null,
    selectedAccount: null,
    opsStatus: null,
    auditLog: [],
    lastInviteCode: '',
    inviteWarning: '',
    errorMessage: '',
    successMessage: '',
    isLoadingSession: false,
    isLoggingIn: false,
    isLoadingRequests: false,
    isLoadingAccounts: false,
    isLoadingAllowlist: false,
    isLoadingOverrideRequests: false,
    isLoadingFeedback: false,
    isLoadingOpsStatus: false,
    isLoadingAuditLog: false,
    isSubmitting: false,
  };
}

export function createAdminService(options = {}) {
  const adminApi = options.adminApi || adminApiClient;
  const state = reactive(createInitialState());
  let lastFeedbackQuery = {};

  function clearMessages() {
    state.errorMessage = '';
    state.successMessage = '';
  }

  function setInviteResult(payload = {}) {
    state.lastInviteCode = payload?.invite_code || '';
    state.inviteWarning = payload?.warning || '';
  }

  async function loadSession() {
    state.isLoadingSession = true;
    clearMessages();
    try {
      const response = await adminApi.get('/admin/session');
      state.session = response.data;
      return response.data;
    } catch (error) {
      state.session = null;
      state.errorMessage = getApiErrorMessage(error, 'Failed to load admin session.');
      return null;
    } finally {
      state.isLoadingSession = false;
    }
  }

  async function login(password) {
    state.isLoggingIn = true;
    clearMessages();
    try {
      const response = await adminApi.post('/admin/login', { password });
      state.session = response.data;
      state.successMessage = response.data?.message || 'Admin session started.';
      return response.data;
    } catch (error) {
      state.errorMessage = getApiErrorMessage(error, 'Admin login failed.');
      return null;
    } finally {
      state.isLoggingIn = false;
    }
  }

  async function logout() {
    state.isSubmitting = true;
    clearMessages();
    try {
      const response = await adminApi.post('/admin/logout');
      state.session = response.data;
      state.requests = [];
      state.accounts = [];
      state.allowlistEntries = [];
      state.overrideRequests = [];
      state.feedbackItems = [];
      state.feedbackSummary = null;
      state.selectedAccount = null;
      state.opsStatus = null;
      state.auditLog = [];
      state.lastInviteCode = '';
      state.inviteWarning = '';
      state.successMessage = response.data?.message || 'Admin session ended.';
      return response.data;
    } catch (error) {
      state.errorMessage = getApiErrorMessage(error, 'Admin logout failed.');
      return null;
    } finally {
      state.isSubmitting = false;
    }
  }

  async function loadRequests(status = 'pending') {
    state.isLoadingRequests = true;
    clearMessages();
    try {
      const query = status ? `?status=${encodeURIComponent(status)}` : '';
      const response = await adminApi.get(`/admin/access/requests${query}`);
      state.requests = Array.isArray(response.data?.requests) ? response.data.requests : [];
      return state.requests;
    } catch (error) {
      state.errorMessage = getApiErrorMessage(error, 'Failed to load access requests.');
      return [];
    } finally {
      state.isLoadingRequests = false;
    }
  }

  async function approveRequest(requestId, payload) {
    state.isSubmitting = true;
    clearMessages();
    try {
      const response = await adminApi.post(`/admin/access/requests/${requestId}/approve`, payload);
      setInviteResult(response.data);
      state.successMessage = response.data?.message || 'Access request approved.';
      await loadRequests('pending');
      await loadAccounts();
      return response.data;
    } catch (error) {
      state.errorMessage = getApiErrorMessage(error, 'Failed to approve access request.');
      return null;
    } finally {
      state.isSubmitting = false;
    }
  }

  async function rejectRequest(requestId, payload) {
    state.isSubmitting = true;
    clearMessages();
    try {
      const response = await adminApi.post(`/admin/access/requests/${requestId}/reject`, payload);
      state.successMessage = response.data?.message || 'Access request rejected.';
      await loadRequests('pending');
      return response.data;
    } catch (error) {
      state.errorMessage = getApiErrorMessage(error, 'Failed to reject access request.');
      return null;
    } finally {
      state.isSubmitting = false;
    }
  }

  async function createInvite(payload) {
    state.isSubmitting = true;
    clearMessages();
    try {
      const response = await adminApi.post('/admin/access/invites', payload);
      setInviteResult(response.data);
      state.successMessage = response.data?.message || 'Access invite created.';
      await loadAccounts();
      return response.data;
    } catch (error) {
      state.errorMessage = getApiErrorMessage(error, 'Failed to create direct invite.');
      return null;
    } finally {
      state.isSubmitting = false;
    }
  }

  async function loadAccounts(status = '') {
    state.isLoadingAccounts = true;
    clearMessages();
    try {
      const query = status ? `?status=${encodeURIComponent(status)}` : '';
      const response = await adminApi.get(`/admin/access/accounts${query}`);
      state.accounts = Array.isArray(response.data?.accounts) ? response.data.accounts : [];
      return state.accounts;
    } catch (error) {
      state.errorMessage = getApiErrorMessage(error, 'Failed to load access accounts.');
      return [];
    } finally {
      state.isLoadingAccounts = false;
    }
  }

  async function loadAllowlist(params = {}) {
    state.isLoadingAllowlist = true;
    clearMessages();
    try {
      const search = new URLSearchParams();
      if (params.scope) {
        search.set('scope', String(params.scope));
      }
      if (params.subjectType) {
        search.set('subject_type', String(params.subjectType));
      }
      if (params.subjectValue) {
        search.set('subject_value', String(params.subjectValue));
      }
      if (params.status) {
        search.set('status', String(params.status));
      }
      const query = search.size ? `?${search.toString()}` : '';
      const response = await adminApi.get(`/admin/allowlist${query}`);
      state.allowlistEntries = Array.isArray(response.data?.allowlist_entries) ? response.data.allowlist_entries : [];
      return state.allowlistEntries;
    } catch (error) {
      state.errorMessage = getApiErrorMessage(error, 'Failed to load allowlist entries.');
      return [];
    } finally {
      state.isLoadingAllowlist = false;
    }
  }

  async function createAllowlistEntry(payload) {
    state.isSubmitting = true;
    clearMessages();
    try {
      const response = await adminApi.post('/admin/allowlist', payload);
      state.successMessage = response.data?.message || 'Allowlist entry created.';
      await loadAllowlist();
      return response.data;
    } catch (error) {
      state.errorMessage = getApiErrorMessage(error, 'Failed to create allowlist entry.');
      return null;
    } finally {
      state.isSubmitting = false;
    }
  }

  async function updateAllowlistEntry(allowlistEntryId, payload) {
    state.isSubmitting = true;
    clearMessages();
    try {
      const response = await adminApi.patch(`/admin/allowlist/${allowlistEntryId}`, payload);
      state.successMessage = response.data?.message || 'Allowlist entry updated.';
      await loadAllowlist();
      return response.data;
    } catch (error) {
      state.errorMessage = getApiErrorMessage(error, 'Failed to update allowlist entry.');
      return null;
    } finally {
      state.isSubmitting = false;
    }
  }

  async function revokeAllowlistEntry(allowlistEntryId, payload = {}) {
    state.isSubmitting = true;
    clearMessages();
    try {
      const response = await adminApi.post(`/admin/allowlist/${allowlistEntryId}/revoke`, payload);
      state.successMessage = response.data?.message || 'Allowlist entry revoked.';
      await loadAllowlist();
      return response.data;
    } catch (error) {
      state.errorMessage = getApiErrorMessage(error, 'Failed to revoke allowlist entry.');
      return null;
    } finally {
      state.isSubmitting = false;
    }
  }

  async function reactivateAllowlistEntry(allowlistEntryId, payload = {}) {
    state.isSubmitting = true;
    clearMessages();
    try {
      const response = await adminApi.post(`/admin/allowlist/${allowlistEntryId}/reactivate`, payload);
      state.successMessage = response.data?.message || 'Allowlist entry reactivated.';
      await loadAllowlist();
      return response.data;
    } catch (error) {
      state.errorMessage = getApiErrorMessage(error, 'Failed to reactivate allowlist entry.');
      return null;
    } finally {
      state.isSubmitting = false;
    }
  }

  async function loadOverrideRequests(params = {}) {
    state.isLoadingOverrideRequests = true;
    clearMessages();
    try {
      const search = new URLSearchParams();
      if (params.status) {
        search.set('status', String(params.status));
      }
      if (params.requestedScope) {
        search.set('requested_scope', String(params.requestedScope));
      }
      const query = search.size ? `?${search.toString()}` : '';
      const response = await adminApi.get(`/admin/override-requests${query}`);
      state.overrideRequests = Array.isArray(response.data?.override_requests) ? response.data.override_requests : [];
      return state.overrideRequests;
    } catch (error) {
      state.errorMessage = getApiErrorMessage(error, 'Failed to load override requests.');
      return [];
    } finally {
      state.isLoadingOverrideRequests = false;
    }
  }

  async function loadFeedback(params = {}) {
    state.isLoadingFeedback = true;
    clearMessages();
    try {
      lastFeedbackQuery = { ...params };
      const search = new URLSearchParams();
      if (params.status) {
        search.set('status', String(params.status));
      }
      if (params.type) {
        search.set('type', String(params.type));
      }
      if (params.priority) {
        search.set('priority', String(params.priority));
      }
      if (params.limit) {
        search.set('limit', String(params.limit));
      }
      const query = search.size ? `?${search.toString()}` : '';
      const response = await adminApi.get(`/admin/feedback${query}`);
      state.feedbackItems = Array.isArray(response.data?.feedback_items) ? response.data.feedback_items : [];
      state.feedbackSummary = response.data?.summary || null;
      return state.feedbackItems;
    } catch (error) {
      state.errorMessage = getApiErrorMessage(error, 'Failed to load feedback.');
      return [];
    } finally {
      state.isLoadingFeedback = false;
    }
  }

  async function loadFeedbackDetail(feedbackId) {
    state.isSubmitting = true;
    clearMessages();
    try {
      const response = await adminApi.get(`/admin/feedback/${feedbackId}`);
      return response.data?.feedback || null;
    } catch (error) {
      state.errorMessage = getApiErrorMessage(error, 'Failed to load feedback detail.');
      return null;
    } finally {
      state.isSubmitting = false;
    }
  }

  async function updateFeedback(feedbackId, payload) {
    state.isSubmitting = true;
    clearMessages();
    try {
      const response = await adminApi.patch(`/admin/feedback/${feedbackId}`, payload);
      state.successMessage = response.data?.message || 'Feedback updated.';
      await loadFeedback(lastFeedbackQuery);
      return response.data;
    } catch (error) {
      state.errorMessage = getApiErrorMessage(error, 'Failed to update feedback.');
      return null;
    } finally {
      state.isSubmitting = false;
    }
  }

  async function updateFeedbackStatus(feedbackId, payload) {
    state.isSubmitting = true;
    clearMessages();
    try {
      const response = await adminApi.post(`/admin/feedback/${feedbackId}/status`, payload);
      state.successMessage = response.data?.message || 'Feedback status updated.';
      await loadFeedback(lastFeedbackQuery);
      return response.data;
    } catch (error) {
      state.errorMessage = getApiErrorMessage(error, 'Failed to update feedback status.');
      return null;
    } finally {
      state.isSubmitting = false;
    }
  }

  async function addFeedbackNote(feedbackId, payload) {
    state.isSubmitting = true;
    clearMessages();
    try {
      const response = await adminApi.post(`/admin/feedback/${feedbackId}/note`, payload);
      state.successMessage = response.data?.message || 'Feedback note added.';
      await loadFeedback(lastFeedbackQuery);
      return response.data;
    } catch (error) {
      state.errorMessage = getApiErrorMessage(error, 'Failed to add feedback note.');
      return null;
    } finally {
      state.isSubmitting = false;
    }
  }

  async function approveOverrideRequest(overrideRequestId, payload) {
    state.isSubmitting = true;
    clearMessages();
    try {
      const response = await adminApi.post(`/admin/override-requests/${overrideRequestId}/approve`, payload);
      state.successMessage = response.data?.message || 'Override request approved.';
      await Promise.all([loadOverrideRequests(), loadAllowlist()]);
      return response.data;
    } catch (error) {
      state.errorMessage = getApiErrorMessage(error, 'Failed to approve override request.');
      return null;
    } finally {
      state.isSubmitting = false;
    }
  }

  async function rejectOverrideRequest(overrideRequestId, payload) {
    state.isSubmitting = true;
    clearMessages();
    try {
      const response = await adminApi.post(`/admin/override-requests/${overrideRequestId}/reject`, payload);
      state.successMessage = response.data?.message || 'Override request rejected.';
      await loadOverrideRequests();
      return response.data;
    } catch (error) {
      state.errorMessage = getApiErrorMessage(error, 'Failed to reject override request.');
      return null;
    } finally {
      state.isSubmitting = false;
    }
  }

  async function loadOpsStatus() {
    state.isLoadingOpsStatus = true;
    clearMessages();
    try {
      const response = await adminApi.get('/admin/ops/status');
      state.opsStatus = response.data || null;
      return state.opsStatus;
    } catch (error) {
      state.errorMessage = getApiErrorMessage(error, 'Failed to load admin ops status.');
      return null;
    } finally {
      state.isLoadingOpsStatus = false;
    }
  }

  async function loadAuditLog(params = {}) {
    state.isLoadingAuditLog = true;
    clearMessages();
    try {
      const search = new URLSearchParams();
      if (params.limit) {
        search.set('limit', String(params.limit));
      }
      if (params.action) {
        search.set('action', String(params.action));
      }
      if (params.since) {
        search.set('since', String(params.since));
      }
      if (params.before) {
        search.set('before', String(params.before));
      }
      const query = search.size ? `?${search.toString()}` : '';
      const response = await adminApi.get(`/admin/audit-log${query}`);
      state.auditLog = Array.isArray(response.data?.audit_log) ? response.data.audit_log : [];
      return state.auditLog;
    } catch (error) {
      state.errorMessage = getApiErrorMessage(error, 'Failed to load admin audit log.');
      return [];
    } finally {
      state.isLoadingAuditLog = false;
    }
  }

  async function loadAccountDetail(accessAccountId) {
    state.isSubmitting = true;
    clearMessages();
    try {
      const response = await adminApi.get(`/admin/access/accounts/${accessAccountId}`);
      state.selectedAccount = response.data;
      return response.data;
    } catch (error) {
      state.errorMessage = getApiErrorMessage(error, 'Failed to load access account detail.');
      return null;
    } finally {
      state.isSubmitting = false;
    }
  }

  async function updateAccountStatus(accessAccountId, action) {
    state.isSubmitting = true;
    clearMessages();
    try {
      const response = await adminApi.post(`/admin/access/accounts/${accessAccountId}/${action}`);
      state.successMessage = response.data?.message || 'Access account updated.';
      await loadAccounts();
      if (state.selectedAccount?.access_account?.access_account_id === accessAccountId) {
        await loadAccountDetail(accessAccountId);
      }
      return response.data;
    } catch (error) {
      state.errorMessage = getApiErrorMessage(error, 'Failed to update access account.');
      return null;
    } finally {
      state.isSubmitting = false;
    }
  }

  async function revokeWalletBinding(walletAddress) {
    state.isSubmitting = true;
    clearMessages();
    try {
      const response = await adminApi.post(`/admin/access/wallet-bindings/${walletAddress}/revoke`);
      state.successMessage = response.data?.message || 'Wallet binding revoked.';
      await loadAccounts();
      if (state.selectedAccount?.access_account?.access_account_id) {
        await loadAccountDetail(state.selectedAccount.access_account.access_account_id);
      }
      return response.data;
    } catch (error) {
      state.errorMessage = getApiErrorMessage(error, 'Failed to revoke wallet binding.');
      return null;
    } finally {
      state.isSubmitting = false;
    }
  }

  return {
    state: readonly(state),
    loadSession,
    login,
    logout,
    loadRequests,
    approveRequest,
    rejectRequest,
    createInvite,
    loadAccounts,
    loadAllowlist,
    createAllowlistEntry,
    updateAllowlistEntry,
    revokeAllowlistEntry,
    reactivateAllowlistEntry,
    loadOverrideRequests,
    approveOverrideRequest,
    rejectOverrideRequest,
    loadFeedback,
    loadFeedbackDetail,
    updateFeedback,
    updateFeedbackStatus,
    addFeedbackNote,
    loadOpsStatus,
    loadAuditLog,
    loadAccountDetail,
    updateAccountStatus,
    revokeWalletBinding,
  };
}

const adminService = createAdminService();

export function useAdmin() {
  return adminService;
}
