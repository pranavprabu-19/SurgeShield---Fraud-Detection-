export const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8010";
export const KEY = process.env.NEXT_PUBLIC_API_KEY || "surgeshield-demo";
export const WS = API.replace(/^http/, "ws");

export async function api(path, options = {}) {
  const method = (options.method || "GET").toUpperCase();
  const headers = {
    "X-API-Key": KEY,
    ...(options.headers || {}),
  };
  const form = typeof FormData !== "undefined" && options.body instanceof FormData;
  if (method !== "GET" && method !== "HEAD" && !form) {
    headers["Content-Type"] = "application/json";
  }
  const response = await fetch(`${API}${path}`, {
    ...options,
    method,
    headers,
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json();
}

export function money(value) {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(value || 0);
}
