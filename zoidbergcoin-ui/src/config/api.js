import axios from "axios";

const DEFAULT_API_BASE_URL = import.meta.env.PROD
  ? "https://zoidbergcoin.com"
  : "http://127.0.0.1:8000";

export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || DEFAULT_API_BASE_URL;

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
});

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

  if (typeof data?.error === "string") {
    return data.error;
  }

  if (typeof data?.message === "string") {
    return data.message;
  }

  if (error?.message) {
    return error.message;
  }

  return fallback;
}
