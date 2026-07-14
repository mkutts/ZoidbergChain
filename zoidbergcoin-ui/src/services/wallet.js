import { reactive, readonly } from 'vue';
import { normalizeWalletAddress, shortenWalletAddress } from '../utils/walletAddress.js';
import { apiClient, getApiErrorMessage } from '../config/api.js';

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
  };

  let provider = null;
  let listenersAttached = false;
  let onAccountsChanged = null;
  let onChainChanged = null;
  let onDisconnect = null;

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

  function clearVerifiedSession() {
    persistVerifiedSession(null);
  }

  function restoreVerifiedSession() {
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
        clearVerifiedSession();
        return;
      }
      if (normalized === state.normalizedWalletAddress) {
        persistVerifiedSession({
          sessionToken: parsed.sessionToken,
          expiresAt: parsed.expiresAt,
        });
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
    state.connectionStatus = state.isMetaMaskAvailable ? 'disconnected' : 'unavailable';
    persistAddress('');
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
    persistAddress(normalized);
    restoreVerifiedSession();
    return normalized;
  }

  function attachProviderListeners() {
    provider = getProvider();
    if (!provider || listenersAttached || typeof provider.on !== 'function') {
      return;
    }

    onAccountsChanged = async (accounts) => {
      try {
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
      clearVerifiedSession();
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

  function disconnectWallet() {
    state.errorMessage = '';
    state.chainId = '';
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
      return verification;
    } catch (error) {
      state.connectionStatus = 'error';
      clearVerifiedSession();
      if (error?.code === 4001) {
        state.errorMessage = 'Signature request was rejected in MetaMask.';
      } else {
        state.errorMessage = getApiErrorMessage(error, 'Wallet verification failed.');
      }
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
    clearVerifiedSession();
    return state.chainId;
  }

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
      if (!state.sessionToken || sessionIsExpired(state.sessionExpiresAt)) {
        return {};
      }
      return { Authorization: `Bearer ${state.sessionToken}` };
    },
  };
}

const walletManager = createWalletManager();

export function useWallet() {
  return walletManager;
}
