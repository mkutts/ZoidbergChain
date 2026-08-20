import { reactive, readonly } from 'vue';
import { adminApiClient, getApiErrorMessage } from '../config/api.js';

function createInitialState() {
  return {
    session: null,
    requests: [],
    accounts: [],
    selectedAccount: null,
    lastInviteCode: '',
    inviteWarning: '',
    errorMessage: '',
    successMessage: '',
    isLoadingSession: false,
    isLoggingIn: false,
    isLoadingRequests: false,
    isLoadingAccounts: false,
    isSubmitting: false,
  };
}

export function createAdminService(options = {}) {
  const adminApi = options.adminApi || adminApiClient;
  const state = reactive(createInitialState());

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
      state.selectedAccount = null;
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
    loadAccountDetail,
    updateAccountStatus,
    revokeWalletBinding,
  };
}

const adminService = createAdminService();

export function useAdmin() {
  return adminService;
}
