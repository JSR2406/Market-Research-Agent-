// Single source of truth for backend URLs.
// P0 fix: this logic was duplicated ×5 files with slightly different env vars
// (NEXT_PUBLIC_API_BASE vs NEXT_PUBLIC_BACKEND_URL), which could produce a
// split-brain where one component talked http:// and another https://.

const DEFAULT_BASE = "http://localhost:8000";

function resolveBase(): string {
  const raw = (
    process.env.NEXT_PUBLIC_API_BASE ??
    process.env.NEXT_PUBLIC_BACKEND_URL ??
    DEFAULT_BASE
  ).trim();

  // On an HTTPS page, plain http:// requests are blocked (mixed content) —
  // upgrade automatically, exactly once, here.
  if (
    typeof window !== "undefined" &&
    window.location.protocol === "https:" &&
    raw.startsWith("http://")
  ) {
    return raw.replace("http://", "https://");
  }
  return raw;
}

/** REST base, e.g. `https://backend.example.com` (no trailing slash). */
export const API_BASE = resolveBase();

function resolveWs(): string {
  const fallback = `${API_BASE.replace(/^http/, "ws")}/ws/market`;
  const raw = (process.env.NEXT_PUBLIC_WS_URL?.trim() || fallback).replace(
    /\/+$/,
    ""
  );

  if (typeof window !== "undefined") {
    const isHttps = window.location.protocol === "https:";
    if (isHttps && raw.startsWith("ws://")) return raw.replace("ws://", "wss://");
    // Local dev over http:// against a wss:// endpoint fails too — downgrade.
    if (!isHttps && raw.startsWith("wss://")) return raw.replace("wss://", "ws://");
  }
  return raw;
}

/** Full WebSocket endpoint for the market research workflow. */
export const WS_URL = resolveWs();
