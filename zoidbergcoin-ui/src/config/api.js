const DEFAULT_API_BASE_URL = import.meta.env.PROD
  ? "https://zoidbergcoin.com"
  : "http://127.0.0.1:8000";

export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || DEFAULT_API_BASE_URL;

export const API_KEY =
  import.meta.env.VITE_API_KEY || "admin_key_123";
