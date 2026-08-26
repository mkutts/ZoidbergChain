import { EMBEDDED_WALLET_CONFIG } from '../utils/embeddedWalletConfig.js';
import { createPrivyReactBridge } from './privyReactIsland.js';

const PRIVY_COMING_SOON_MESSAGE = 'Email / Social Wallet coming soon';
const PRIVY_MISSING_APP_ID_MESSAGE = 'Email / Social Wallet coming soon';
const PRIVY_PROVIDER_DISABLED_MESSAGE = 'Email / Social Wallet coming soon';
const PRIVY_TEMPORARY_UNAVAILABLE_MESSAGE = 'Email / Social Wallet is temporarily unavailable. Continue with MetaMask or try again later.';
const PRIVY_LOGIN_CANCELLED_MESSAGE = 'Email / Social Wallet login was not completed.';
const PRIVY_SIGN_CANCELLED_MESSAGE = 'Signature request was not completed in Email / Social Wallet.';

function normalizeErrorMessage(error) {
  return String(error?.message || '').trim();
}

function isUserCancelledError(error) {
  return /rejected|cancelled|canceled|closed|dismissed/i.test(normalizeErrorMessage(error));
}

function classifyUnavailableReason(config = {}, error) {
  if (!config?.isPrivySelected) {
    return 'provider_disabled';
  }
  if (!config?.privyAppId) {
    return 'missing_app_id';
  }

  const message = normalizeErrorMessage(error).toLowerCase();
  if (!message) {
    return 'sdk_init_failed';
  }
  if (message.includes('browser context')) {
    return 'unsupported_browser';
  }
  if (message.includes('origin')) {
    return 'origin_not_allowed';
  }
  if (message.includes('import')) {
    return 'sdk_import_failed';
  }
  return 'sdk_init_failed';
}

function buildUnavailableMessage(config = {}, unavailableReason = '', lastErrorMessage = '') {
  switch (unavailableReason) {
    case 'provider_disabled':
      return PRIVY_PROVIDER_DISABLED_MESSAGE;
    case 'missing_app_id':
      return PRIVY_MISSING_APP_ID_MESSAGE;
    case 'sdk_import_failed':
    case 'sdk_init_failed':
    case 'origin_not_allowed':
    case 'unsupported_browser':
      return PRIVY_TEMPORARY_UNAVAILABLE_MESSAGE;
    default:
      return lastErrorMessage || PRIVY_COMING_SOON_MESSAGE;
  }
}

export function createPrivyEmbeddedWalletService(options = {}) {
  const config = options.config || EMBEDDED_WALLET_CONFIG;
  const createBridge = options.createBridge || ((bridgeOptions = {}) => createPrivyReactBridge(bridgeOptions));

  let bridge = null;
  let availability = config?.isPrivySelected
    ? (config?.isConfigured ? 'available' : 'coming_soon')
    : 'coming_soon';
  let connectionStatus = config?.isConfigured ? 'idle' : 'coming_soon';
  let lastErrorMessage = '';
  let unavailableReason = !config?.isPrivySelected
    ? 'provider_disabled'
    : (config?.privyAppId ? '' : 'missing_app_id');
  let sdkImportAttempted = false;
  let sdkImportSucceeded = false;
  let initAttempted = false;
  let initSucceeded = false;
  let walletAddress = '';
  let loginMetadata = null;

  function ensureConfigured() {
    if (!config?.isPrivySelected) {
      const error = new Error(PRIVY_PROVIDER_DISABLED_MESSAGE);
      error.code = 'privy_provider_disabled';
      throw error;
    }
    if (!config?.privyAppId) {
      const error = new Error(PRIVY_MISSING_APP_ID_MESSAGE);
      error.code = 'privy_missing_app_id';
      throw error;
    }
  }

  function getBridge() {
    if (!bridge) {
      bridge = createBridge({
        config: {
          enabled: Boolean(config?.isPrivySelected),
          configured: Boolean(config?.isConfigured),
          label: config?.authOptionLabel || 'Email / Social Wallet',
          privy: {
            appId: config?.privyAppId || '',
            clientId: config?.privyClientId || '',
          },
        },
      });
    }
    return bridge;
  }

  function syncBridgeState() {
    if (!bridge || typeof bridge.getState !== 'function') {
      return;
    }
    const state = bridge.getState();
    walletAddress = String(state?.walletAddress || '').trim();
    loginMetadata = state?.loginMetadata || null;
  }

  function getDiagnostics() {
    return {
      providerConfigured: Boolean(config?.isPrivySelected),
      appIdPresent: Boolean(config?.privyAppId),
      providerName: String(config?.provider || '').trim(),
      sdkImportAttempted,
      sdkImportSucceeded,
      initAttempted,
      initSucceeded,
      unavailableReason,
      lastErrorMessage,
    };
  }

  function getAvailability() {
    return availability;
  }

  function getUnavailableMessage() {
    if (availability === 'available') {
      return '';
    }
    return buildUnavailableMessage(config, unavailableReason, lastErrorMessage);
  }

  async function initialize() {
    initAttempted = true;
    if (!config?.isConfigured) {
      initSucceeded = false;
      availability = 'coming_soon';
      return false;
    }
    initSucceeded = true;
    availability = 'available';
    return true;
  }

  async function probeAvailability() {
    ensureConfigured();
    sdkImportAttempted = true;
    try {
      await getBridge().probeAvailability();
      sdkImportSucceeded = true;
      initAttempted = true;
      initSucceeded = true;
      availability = 'available';
      unavailableReason = '';
      lastErrorMessage = '';
      return true;
    } catch (error) {
      sdkImportSucceeded = false;
      initAttempted = true;
      initSucceeded = false;
      availability = 'error';
      unavailableReason = classifyUnavailableReason(config, error);
      lastErrorMessage = normalizeErrorMessage(error);
      const unavailableError = new Error(PRIVY_TEMPORARY_UNAVAILABLE_MESSAGE);
      unavailableError.cause = error;
      throw unavailableError;
    }
  }

  async function connect(options = {}) {
    ensureConfigured();
    connectionStatus = 'connecting';
    try {
      if (!sdkImportSucceeded) {
        await probeAvailability();
      }
      const loginMethods = Array.isArray(options?.loginMethods) && options.loginMethods.length > 0
        ? options.loginMethods
        : undefined;
      const result = await getBridge().connect({
        loginMethods,
      });
      syncBridgeState();
      walletAddress = String(result?.wallet_address || walletAddress || '').trim();
      loginMetadata = result?.login_metadata || loginMetadata;
      connectionStatus = walletAddress ? 'connected' : 'disconnected';
      availability = 'available';
      unavailableReason = '';
      lastErrorMessage = '';
      return walletAddress ? [walletAddress] : [];
    } catch (error) {
      syncBridgeState();
      if (isUserCancelledError(error)) {
        connectionStatus = 'disconnected';
        lastErrorMessage = normalizeErrorMessage(error);
        throw new Error(PRIVY_LOGIN_CANCELLED_MESSAGE);
      }
      const cause = error?.cause || error;
      connectionStatus = 'error';
      availability = 'error';
      unavailableReason = unavailableReason || classifyUnavailableReason(config, cause);
      lastErrorMessage = normalizeErrorMessage(cause);
      throw new Error(PRIVY_TEMPORARY_UNAVAILABLE_MESSAGE);
    }
  }

  async function restoreConnection() {
    if (!bridge) {
      return [];
    }
    syncBridgeState();
    return walletAddress ? [walletAddress] : [];
  }

  async function sendEmailCode() {
    return connect({ loginMethods: ['email'] });
  }

  async function startOAuthLogin(providerId = '') {
    const provider = String(providerId || config?.socialProvider || '').trim().toLowerCase();
    const loginMethods = provider ? [provider] : undefined;
    return connect({ loginMethods });
  }

  async function getAccounts() {
    syncBridgeState();
    return walletAddress ? [walletAddress] : [];
  }

  async function getAddress() {
    syncBridgeState();
    return walletAddress;
  }

  async function getChainId() {
    return '';
  }

  async function requestSignature(message, walletAddressOverride = '') {
    ensureConfigured();
    try {
      if (!sdkImportSucceeded) {
        await probeAvailability();
      }
      const signature = await getBridge().requestSignature(message, walletAddressOverride || walletAddress);
      syncBridgeState();
      connectionStatus = walletAddress ? 'connected' : connectionStatus;
      return signature;
    } catch (error) {
      syncBridgeState();
      if (isUserCancelledError(error)) {
        throw new Error(PRIVY_SIGN_CANCELLED_MESSAGE);
      }
      const cause = error?.cause || error;
      connectionStatus = 'error';
      availability = 'error';
      unavailableReason = unavailableReason || classifyUnavailableReason(config, cause);
      lastErrorMessage = normalizeErrorMessage(cause);
      throw new Error(PRIVY_TEMPORARY_UNAVAILABLE_MESSAGE);
    }
  }

  async function disconnect() {
    if (!bridge) {
      connectionStatus = availability === 'available' ? 'idle' : 'coming_soon';
      walletAddress = '';
      loginMetadata = null;
      return;
    }
    await bridge.disconnect();
    syncBridgeState();
    walletAddress = '';
    loginMetadata = null;
    connectionStatus = availability === 'available' ? 'idle' : 'coming_soon';
  }

  return {
    initialize,
    getAvailability,
    getUnavailableMessage,
    getDiagnostics,
    getConnectionStatus() {
      return connectionStatus;
    },
    isConfigured() {
      return Boolean(config?.isConfigured);
    },
    restoreConnection,
    connect,
    sendEmailCode,
    startOAuthLogin,
    getAccounts,
    getAddress,
    getChainId,
    requestSignature,
    disconnect,
    getPortabilityInfo() {
      return {
        helpUrl: config?.portabilityHelpUrl || '',
        helpCopy: config?.portabilityHelpCopy || '',
      };
    },
    getAuthState() {
      syncBridgeState();
      return {
        isAuthenticated: Boolean(walletAddress),
        method: walletAddress ? 'privy' : 'none',
        loginMetadata,
      };
    },
  };
}
