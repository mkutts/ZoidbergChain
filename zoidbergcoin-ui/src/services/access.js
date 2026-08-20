import { reactive, readonly } from 'vue';
import { apiClient, publicApiClient, getApiErrorMessage } from '../config/api.js';

const ACCESS_SESSION_KEY = 'zoidberg:access-session';

function defaultStorage() {
  if (typeof window === 'undefined') {
    return null;
  }
  try {
    return window.localStorage || null;
  } catch {
    return null;
  }
}

function createInitialState() {
  return {
    publicStatus: null,
    me: null,
    accessSessionToken: '',
    errorMessage: '',
    successMessage: '',
    isLoadingStatus: false,
    isSubmittingRequest: false,
    isLoggingIn: false,
    isBindingWallet: false,
  };
}

export function createAccessService(options = {}) {
  const api = options.api || apiClient;
  const publicApi = options.publicApi || publicApiClient;
  const storage = options.storage ?? defaultStorage();
  const state = reactive(createInitialState());

  function persistSessionToken(token) {
    state.accessSessionToken = String(token || '').trim();
    if (!storage) {
      return;
    }
    if (!state.accessSessionToken) {
      storage.removeItem(ACCESS_SESSION_KEY);
      return;
    }
    storage.setItem(ACCESS_SESSION_KEY, state.accessSessionToken);
  }

  function restoreSessionToken() {
    if (!storage) {
      return '';
    }
    persistSessionToken(storage.getItem(ACCESS_SESSION_KEY) || '');
    return state.accessSessionToken;
  }

  function getAccessHeaders() {
    if (!state.accessSessionToken) {
      return {};
    }
    return {
      'X-ZOID-Access-Session': state.accessSessionToken,
    };
  }

  async function loadPublicStatus() {
    state.isLoadingStatus = true;
    state.errorMessage = '';
    try {
      const response = await publicApi.get('/access/status');
      state.publicStatus = response.data;
      return response.data;
    } catch (error) {
      state.errorMessage = getApiErrorMessage(error, 'Failed to load access status.');
      return null;
    } finally {
      state.isLoadingStatus = false;
    }
  }

  async function refreshMe(authHeaders = {}) {
    state.errorMessage = '';
    try {
      const response = await publicApi.get('/access/me', {
        headers: {
          ...getAccessHeaders(),
          ...(authHeaders || {}),
        },
      });
      state.me = response.data;
      return response.data;
    } catch (error) {
      if (error?.response?.status === 401) {
        persistSessionToken('');
      }
      state.errorMessage = getApiErrorMessage(error, 'Failed to load controlled access status.');
      return null;
    }
  }

  async function initialize(authHeaders = {}) {
    restoreSessionToken();
    await loadPublicStatus();
    return refreshMe(authHeaders);
  }

  async function submitAccessRequest(payload) {
    state.isSubmittingRequest = true;
    state.errorMessage = '';
    state.successMessage = '';
    try {
      const response = await publicApi.post('/access/request', payload);
      state.successMessage = response.data?.message || 'Access request submitted.';
      return response.data;
    } catch (error) {
      state.errorMessage = getApiErrorMessage(error, 'Access request failed.');
      return null;
    } finally {
      state.isSubmittingRequest = false;
    }
  }

  async function loginWithCode(accessCode) {
    state.isLoggingIn = true;
    state.errorMessage = '';
    state.successMessage = '';
    try {
      const response = await publicApi.post('/access/login', { access_code: accessCode });
      persistSessionToken(response.data?.access_session_token || '');
      state.successMessage = response.data?.message || 'Invite accepted.';
      await refreshMe();
      return response.data;
    } catch (error) {
      state.errorMessage = getApiErrorMessage(error, 'Invite login failed.');
      return null;
    } finally {
      state.isLoggingIn = false;
    }
  }

  async function bindWallet(authHeaders = {}) {
    state.isBindingWallet = true;
    state.errorMessage = '';
    state.successMessage = '';
    try {
      const response = await api.post('/access/bind-wallet', null, {
        headers: {
          ...getAccessHeaders(),
          ...(authHeaders || {}),
        },
      });
      state.successMessage = response.data?.message || 'Wallet bound.';
      state.me = response.data?.access || state.me;
      if (state.me?.access_granted) {
        persistSessionToken('');
      }
      await refreshMe(authHeaders);
      return response.data;
    } catch (error) {
      state.errorMessage = getApiErrorMessage(error, 'Wallet binding failed.');
      return null;
    } finally {
      state.isBindingWallet = false;
    }
  }

  function clearAccessSession() {
    persistSessionToken('');
    state.me = null;
    state.successMessage = '';
  }

  function requiresAppAccess() {
    return Boolean(state.publicStatus?.require_access_for_app);
  }

  function isAppUnlocked() {
    return !requiresAppAccess() || Boolean(state.me?.access_granted);
  }

  return {
    state: readonly(state),
    loadPublicStatus,
    refreshMe,
    initialize,
    submitAccessRequest,
    loginWithCode,
    bindWallet,
    clearAccessSession,
    getAccessHeaders,
    requiresAppAccess,
    isAppUnlocked,
  };
}

const accessService = createAccessService();

export function useAccess() {
  return accessService;
}
