import axios from "axios";

const IMPORT_META_ENV = {
  MODE: typeof import.meta !== "undefined" && import.meta.env ? import.meta.env.MODE : undefined,
  PROD: typeof import.meta !== "undefined" && import.meta.env ? import.meta.env.PROD : undefined,
  VITE_API_BASE_URL: typeof import.meta !== "undefined" && import.meta.env ? import.meta.env.VITE_API_BASE_URL : undefined,
  VITE_API_BASE: typeof import.meta !== "undefined" && import.meta.env ? import.meta.env.VITE_API_BASE : undefined,
  VITE_BACKEND_URL: typeof import.meta !== "undefined" && import.meta.env ? import.meta.env.VITE_BACKEND_URL : undefined,
};
const BROWSER_LOCATION = typeof window !== "undefined" ? window.location : null;

export function createDefaultApiBaseUrl(importMetaEnv = {}, browserLocation = null) {
  const devApiHost = browserLocation?.hostname === "localhost"
    ? "localhost"
    : "127.0.0.1";

  return importMetaEnv.PROD
    ? "https://zoidbergcoin.com/api"
    : `http://${devApiHost}:8000`;
}

function normalizeApiBaseUrl(value) {
  return String(value || "").trim();
}

export function resolveApiBaseUrl(importMetaEnv = {}, browserLocation = null) {
  const configuredBaseUrl = [
    importMetaEnv.VITE_API_BASE_URL,
    importMetaEnv.VITE_API_BASE,
    importMetaEnv.VITE_BACKEND_URL,
  ]
    .map(normalizeApiBaseUrl)
    .find(Boolean);

  if (configuredBaseUrl) {
    return configuredBaseUrl;
  }

  return createDefaultApiBaseUrl(importMetaEnv, browserLocation);
}

export const API_BASE_URL = resolveApiBaseUrl(IMPORT_META_ENV, BROWSER_LOCATION);

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
