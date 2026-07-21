import axios from "axios";

const IMPORT_META_ENV = import.meta?.env || {};
const BROWSER_LOCATION = typeof window !== "undefined" ? window.location : null;
const DEV_API_HOST = BROWSER_LOCATION?.hostname === "localhost"
  ? "localhost"
  : "127.0.0.1";

const DEFAULT_API_BASE_URL = IMPORT_META_ENV.PROD
  ? "https://zoidbergcoin.com"
  : `http://${DEV_API_HOST}:8000`;

export const API_BASE_URL =
  IMPORT_META_ENV.VITE_API_BASE_URL || DEFAULT_API_BASE_URL;

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
});

export const publicApiClient = axios.create({
  baseURL: API_BASE_URL,
});

let authHeadersProvider = null;
let sessionUnauthorizedHandler = null;

apiClient.interceptors.request.use((requestConfig) => {
  const config = { ...requestConfig };
  const headers = {
    ...(requestConfig?.headers || {}),
  };

  if (typeof authHeadersProvider === "function") {
    const providedHeaders = authHeadersProvider() || {};
    Object.assign(headers, providedHeaders);
  }

  config.headers = headers;
  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const requestUrl = String(error?.config?.url || "");
    if (
      error?.response?.status === 401
      && requestUrl.includes("/auth/wallet/session")
      && typeof sessionUnauthorizedHandler === "function"
    ) {
      sessionUnauthorizedHandler(error);
    }
    return Promise.reject(error);
  },
);

export function configureWalletApiAuth(options = {}) {
  authHeadersProvider = typeof options.getAuthHeaders === "function"
    ? options.getAuthHeaders
    : null;
  sessionUnauthorizedHandler = typeof options.onSessionUnauthorized === "function"
    ? options.onSessionUnauthorized
    : null;
}

export function buildApiUrl(path) {
  if (!path) {
    return "";
  }
  if (/^https?:\/\//i.test(path)) {
    return path;
  }
  return `${API_BASE_URL.replace(/\/$/, "")}/${String(path).replace(/^\//, "")}`;
}

export function getApiErrorMessage(error, fallback = "Something went wrong.") {
  const data = error?.response?.data;

  if (Array.isArray(data?.detail)) {
    return data.detail
      .map((item) => item.msg || item.message || JSON.stringify(item))
      .join(" ");
  }

  if (typeof data?.detail === "string") {
    return data.detail;
  }

  if (data?.detail && typeof data.detail === "object") {
    return formatObjectMessage(data.detail, fallback);
  }

  if (typeof data?.error === "string") {
    return data.error;
  }

  if (typeof data?.message === "string") {
    return data.message;
  }

  if (data && typeof data === "object") {
    const objectMessage = formatObjectMessage(data, "");
    if (objectMessage) {
      return objectMessage;
    }
  }

  if (error?.response?.statusText) {
    return error.response.statusText;
  }

  if (error?.message) {
    return error.message;
  }

  return fallback;
}

function formatObjectMessage(data, fallback) {
  const pieces = [];

  if (typeof data.message === "string") {
    pieces.push(data.message);
  }
  if (typeof data.error === "string") {
    pieces.push(data.error);
  }
  if (typeof data.status === "string") {
    pieces.push(`Status: ${formatToken(data.status)}`);
  }
  if (typeof data.reason === "string") {
    pieces.push(`Reason: ${formatToken(data.reason)}`);
  }
  if (typeof data.recommended_action === "string") {
    pieces.push(`Action: ${formatToken(data.recommended_action)}`);
  }

  const hashFields = [
    ["local_latest_hash", "Local latest"],
    ["received_previous_hash", "Received previous"],
    ["received_block_hash", "Received block"],
  ];

  hashFields.forEach(([field, label]) => {
    if (typeof data[field] === "string") {
      pieces.push(`${label}: ${shortenValue(data[field])}`);
    }
  });

  if (pieces.length > 0) {
    return pieces.join(" ");
  }

  try {
    return JSON.stringify(data);
  } catch {
    return fallback;
  }
}

function formatToken(value) {
  return value.replace(/_/g, " ");
}

function shortenValue(value) {
  if (!value || value.length <= 18) {
    return value;
  }
  return `${value.slice(0, 10)}...${value.slice(-8)}`;
}
