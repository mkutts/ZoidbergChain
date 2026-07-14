import { reactive, readonly } from 'vue';
import { normalizeWalletAddress, shortenWalletAddress } from '../utils/walletAddress.js';
import { apiClient, configureWalletApiAuth, getApiErrorMessage } from '../config/api.js';

const LAST_CONNECTED_ADDRESS_KEY = 'zoidberg:last-wallet-address';
const VERIFIED_SESSION_KEY = 'zoidberg:verified-wallet-session';

function defaultProviderGetter() {
  if (typeof window === 'undefined') {
    return null;
  }
  return window.ethereum || null;
}

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
    isMetaMaskAvailable: false,
    isConnected: false,
    walletAddress: '',
    normalizedWalletAddress: '',
    chainId: '',
    connectionStatus: 'idle',
    errorMessage: '',
    isVerifiedSession: false,
    lastConnectedAddress: '',
    sessionToken: '',
    sessionExpiresAt: '',
    verifiedWalletAddress: '',
    identitySource: 'none',
    authError: '',
    connected_wallet_address: '',
    normalized_wallet_address: '',
    is_connected: false,
    is_verified_session: false,
    session_token: '',
    session_expires_at: '',
    verified_wallet_address: '',
    identity_source: 'none',
    auth_error: '',
  };
}

function mapWalletError(error) {
  const code = error?.code;
  if (code === 4001) {
    return 'Connection request was rejected in MetaMask.';
  }
  if (code === -32002) {
    return 'A MetaMask connection request is already pending.';
  }
  if (code === 4900 || code === 4901) {
    return 'MetaMask is connected to an unavailable network right now.';
  }
  if (error?.message) {
    return error.message;
  }
  return 'Unable to connect to MetaMask right now.';
}

export function createWalletManager(options = {}) {
  const state = reactive(createInitialState());
  const getProvider = options.getProvider || defaultProviderGetter;
  const storage = options.storage ?? defaultStorage();
  const authApi = options.authApi || {
    async createChallenge(walletAddress) {
      const response = await apiClient.post('/auth/wallet/challenge', { wallet_address: walletAddress });
      return response.data;
    },
    async verifyChallenge(payload) {
      const response = await apiClient.post('/auth/wallet/verify', payload);
      return response.data;
    },
    async getSession() {
      const response = await apiClient.get('/auth/wallet/session');
      return response.data;
    },
    async logout() {
      const response = await apiClient.post('/auth/wallet/logout');
      return response.data;
    },
  };

  let provider = null;
  let listenersAttached = false;
  let onAccountsChanged = null;
  let onChainChanged = null;
  let onDisconnect = null;

  function syncIdentityFields() {
    state.connectedWalletAddress = state.walletAddress;
    state.connected_wallet_address = state.walletAddress;
    state.normalized_wallet_address = state.normalizedWalletAddress;
    state.is_connected = state.isConnected;
    state.is_verified_session = state.isVerifiedSession;
    state.session_token = state.sessionToken;
    state.session_expires_at = state.sessionExpiresAt;
    state.verified_wallet_address = state.verifiedWalletAddress;
    state.identity_source = state.identitySource;
    state.auth_error = state.authError;
  }

  function setIdentitySource() {
    if (state.isVerifiedSession && state.verifiedWalletAddress) {
      state.identitySource = 'metamask_verified';
    } else if (state.isConnected && state.normalizedWalletAddress) {
      state.identitySource = 'metamask_unverified';
    } else {
      state.identitySource = 'none';
    }
  }

  function persistAddress(address) {
    state.lastConnectedAddress = address || '';
    if (!storage) {
      return;
    }
    if (!address) {
      storage.removeItem(LAST_CONNECTED_ADDRESS_KEY);
      return;
    }
    storage.setItem(LAST_CONNECTED_ADDRESS_KEY, address);
  }

  function sessionIsExpired(expiresAt) {
    if (!expiresAt) {
      return true;
    }
    const parsed = Date.parse(expiresAt);
    if (Number.isNaN(parsed)) {
      return true;
    }
    return parsed <= Date.now();
  }

  function persistVerifiedSession(session) {
    state.sessionToken = session?.sessionToken || '';
    state.sessionExpiresAt = session?.expiresAt || '';
    state.isVerifiedSession = Boolean(session?.sessionToken && !sessionIsExpired(session?.expiresAt));
    state.verifiedWalletAddress = state.isVerifiedSession ? state.normalizedWalletAddress : '';
    setIdentitySource();
    syncIdentityFields();

    if (!storage) {
      return;
    }
    if (!state.isVerifiedSession || !state.normalizedWalletAddress) {
      storage.removeItem(VERIFIED_SESSION_KEY);
      return;
    }
    storage.setItem(
      VERIFIED_SESSION_KEY,
      JSON.stringify({
        walletAddress: state.normalizedWalletAddress,
        sessionToken: state.sessionToken,
        expiresAt: state.sessionExpiresAt,
      }),
    );
  }

  function clearVerifiedSession(reason = '') {
    persistVerifiedSession(null);
    state.authError = reason || '';
    if (reason) {
      state.connectionStatus = 'expired';
    }
    syncIdentityFields();
  }

  async function restoreVerifiedSession() {
    if (!storage) {
      return;
    }
    const raw = storage.getItem(VERIFIED_SESSION_KEY);
    if (!raw) {
      return;
    }
    try {
      const parsed = JSON.parse(raw);
      const normalized = normalizeWalletAddress(parsed.walletAddress);
      if (!normalized || sessionIsExpired(parsed.expiresAt)) {
        state.connectionStatus = 'expired';
        clearVerifiedSession('Session expired - verify again.');
        return;
      }
      if (normalized === state.normalizedWalletAddress) {
        persistVerifiedSession({ sessionToken: parsed.sessionToken, expiresAt: parsed.expiresAt });
        try {
          const session = await authApi.getSession();
          state.isVerifiedSession = Boolean(session.valid);
          state.verifiedWalletAddress = session.normalized_wallet_address || normalized;
          state.sessionExpiresAt = session.expires_at || parsed.expiresAt;
          state.authError = '';
          setIdentitySource();
          syncIdentityFields();
        } catch (error) {
          state.connectionStatus = 'expired';
          clearVerifiedSession(getApiErrorMessage(error, 'Session expired - verify again.'));
        }
      } else {
        clearVerifiedSession();
      }
    } catch {
      clearVerifiedSession();
    }
  }

  function restorePersistedAddress() {
    if (!storage) {
      return '';
    }
    const saved = storage.getItem(LAST_CONNECTED_ADDRESS_KEY) || '';
    const normalized = normalizeWalletAddress(saved);
    state.lastConnectedAddress = normalized || '';
    return state.lastConnectedAddress;
  }

  function applyDisconnectedState() {
    state.isConnected = false;
    state.walletAddress = '';
    state.normalizedWalletAddress = '';
    clearVerifiedSession();
    state.authError = '';
    state.connectionStatus = state.isMetaMaskAvailable ? 'disconnected' : 'unavailable';
    persistAddress('');
    setIdentitySource();
    syncIdentityFields();
  }

  async function readChainId(activeProvider) {
    if (!activeProvider) {
      return '';
    }
    if (typeof activeProvider.chainId === 'string') {
      return activeProvider.chainId;
    }
    try {
      const chainId = await activeProvider.request({ method: 'eth_chainId' });
      return typeof chainId === 'string' ? chainId : '';
    } catch {
      return '';
    }
  }

  async function syncAccounts(accounts = null) {
    provider = getProvider();
    state.isMetaMaskAvailable = Boolean(provider);

    if (!provider) {
      state.connectionStatus = 'unavailable';
      state.errorMessage = 'MetaMask is not installed or the browser wallet provider is unavailable.';
      applyDisconnectedState();
      return null;
    }

    const nextAccounts = Array.isArray(accounts)
      ? accounts
      : await provider.request({ method: 'eth_accounts' });

    if (!Array.isArray(nextAccounts)) {
      state.connectionStatus = 'error';
      state.errorMessage = 'MetaMask returned an unsupported account response.';
      applyDisconnectedState();
      return null;
    }

    const selectedAddress = nextAccounts[0];
    const normalized = normalizeWalletAddress(selectedAddress);
    state.chainId = await readChainId(provider);

    if (!selectedAddress || !normalized) {
      state.errorMessage = nextAccounts.length > 0
        ? 'MetaMask returned an invalid wallet address.'
        : '';
      applyDisconnectedState();
      return null;
    }

    state.walletAddress = selectedAddress;
    state.normalizedWalletAddress = normalized;
    state.isConnected = true;
    state.connectionStatus = 'connected';
    state.errorMessage = '';
    state.authError = '';
    state.verifiedWalletAddress = '';
    persistAddress(normalized);
    await restoreVerifiedSession();
    setIdentitySource();
    syncIdentityFields();
    return normalized;
  }

  function attachProviderListeners() {
    provider = getProvider();
    if (!provider || listenersAttached || typeof provider.on !== 'function') {
      return;
    }

    onAccountsChanged = async (accounts) => {
      try {
        if (state.sessionToken) {
          await authApi.logout();
        }
        await syncAccounts(accounts);
      } catch (error) {
        state.connectionStatus = 'error';
        state.errorMessage = mapWalletError(error);
        applyDisconnectedState();
      }
    };

    onChainChanged = async (chainId) => {
      state.chainId = typeof chainId === 'string' ? chainId : '';
      state.errorMessage = '';
      if (state.sessionToken) {
        await authApi.logout();
      }
      clearVerifiedSession('Network changed - verify again.');
      if (state.isConnected) {
        state.connectionStatus = 'connected';
      }
    };

    onDisconnect = () => {
      state.errorMessage = 'MetaMask disconnected from this app.';
      applyDisconnectedState();
    };

    provider.on('accountsChanged', onAccountsChanged);
    provider.on('chainChanged', onChainChanged);
    provider.on('disconnect', onDisconnect);
    listenersAttached = true;
  }

  async function detectMetaMask() {
    restorePersistedAddress();
    provider = getProvider();
    state.isMetaMaskAvailable = Boolean(provider);

    if (!provider) {
      state.connectionStatus = 'unavailable';
      state.errorMessage = 'MetaMask is not installed or the browser wallet provider is unavailable.';
      applyDisconnectedState();
      return false;
    }

    attachProviderListeners();
    state.connectionStatus = 'checking';
    await syncAccounts();
    if (!state.isConnected) {
      state.connectionStatus = 'disconnected';
    }
    return state.isMetaMaskAvailable;
  }

  async function connectWallet() {
    provider = getProvider();
    state.isMetaMaskAvailable = Boolean(provider);

    if (!provider) {
      state.connectionStatus = 'unavailable';
      state.errorMessage = 'MetaMask is not installed. Install MetaMask to connect a wallet.';
      return null;
    }

    attachProviderListeners();
    state.connectionStatus = 'connecting';
    state.errorMessage = '';

    try {
      const accounts = await provider.request({ method: 'eth_requestAccounts' });
      const normalized = await syncAccounts(accounts);
      if (!normalized) {
        state.connectionStatus = 'error';
        state.errorMessage = 'MetaMask did not return a usable wallet address.';
      }
      return normalized;
    } catch (error) {
      applyDisconnectedState();
      state.connectionStatus = 'error';
      state.errorMessage = mapWalletError(error);
      return null;
    }
  }

  async function disconnectWallet() {
    state.errorMessage = '';
    state.chainId = '';
    if (state.sessionToken) {
      try {
        await authApi.logout();
      } catch {
        // Ignore logout errors during local state cleanup.
      }
    }
    applyDisconnectedState();
  }

  async function verifyWallet() {
    provider = getProvider();
    if (!provider || !state.isConnected || !state.normalizedWalletAddress) {
      state.errorMessage = 'Connect MetaMask before verifying this wallet.';
      return null;
    }

    state.connectionStatus = 'verifying';
    state.errorMessage = '';
    state.authError = '';
    clearVerifiedSession();

    try {
      const challenge = await authApi.createChallenge(state.normalizedWalletAddress);
      const signature = await provider.request({
        method: 'personal_sign',
        params: [challenge.message, state.walletAddress],
      });
      const verification = await authApi.verifyChallenge({
        wallet_address: state.normalizedWalletAddress,
        message: challenge.message,
        signature,
      });

      persistVerifiedSession({
        sessionToken: verification.session_token,
        expiresAt: verification.expires_at,
      });
      state.connectionStatus = 'verified';
      state.errorMessage = '';
      state.authError = '';
      state.verifiedWalletAddress = verification.normalized_wallet_address || state.normalizedWalletAddress;
      setIdentitySource();
      syncIdentityFields();
      return verification;
    } catch (error) {
      state.connectionStatus = 'error';
      clearVerifiedSession();
      if (error?.code === 4001) {
        state.errorMessage = 'Signature request was rejected in MetaMask.';
      } else {
        state.errorMessage = getApiErrorMessage(error, 'Wallet verification failed.');
      }
      state.authError = state.errorMessage;
      syncIdentityFields();
      return null;
    }
  }

  function handleAccountsChanged(accounts) {
    return onAccountsChanged ? onAccountsChanged(accounts) : syncAccounts(accounts);
  }

  function handleChainChanged(chainId) {
    if (onChainChanged) {
      return onChainChanged(chainId);
    }
    state.chainId = typeof chainId === 'string' ? chainId : '';
    clearVerifiedSession('Network changed - verify again.');
    return state.chainId;
  }

  function clearSessionFromUnauthorized(error) {
    state.connectionStatus = 'expired';
    state.errorMessage = '';
    clearVerifiedSession(getApiErrorMessage(error, 'Session expired - verify again.'));
  }

  configureWalletApiAuth({
    getAuthHeaders() {
      if (!state.isVerifiedSession || !state.sessionToken || sessionIsExpired(state.sessionExpiresAt)) {
        return {};
      }
      return { Authorization: `Bearer ${state.sessionToken}` };
    },
    onSessionUnauthorized(error) {
      clearSessionFromUnauthorized(error);
    },
  });

  return {
    state: readonly(state),
    detectMetaMask,
    connectWallet,
    disconnectWallet,
    verifyWallet,
    normalizeAddress: normalizeWalletAddress,
    shortenAddress: shortenWalletAddress,
    handleAccountsChanged,
    handleChainChanged,
    getAuthorizationHeader() {
      if (!state.isVerifiedSession || !state.sessionToken || sessionIsExpired(state.sessionExpiresAt)) {
        return {};
      }
      return { Authorization: `Bearer ${state.sessionToken}` };
    },
    async refreshVerifiedSession() {
      if (!state.sessionToken || !state.normalizedWalletAddress) {
        clearVerifiedSession();
        return null;
      }
      try {
        const session = await authApi.getSession();
        state.isVerifiedSession = Boolean(session.valid);
        state.verifiedWalletAddress = session.normalized_wallet_address || state.normalizedWalletAddress;
        state.sessionExpiresAt = session.expires_at || state.sessionExpiresAt;
        state.connectionStatus = state.isVerifiedSession ? 'verified' : 'expired';
        state.authError = '';
        setIdentitySource();
        syncIdentityFields();
        return session;
      } catch (error) {
        clearSessionFromUnauthorized(error);
        return null;
      }
    },
  };
}

const walletManager = createWalletManager();

export function useWallet() {
  return walletManager;
}
