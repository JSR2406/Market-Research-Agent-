"use client";

import { API_BASE } from "@/lib/api";

/**
 * First-party, aggregate-only usage analytics.
 *
 * This is deliberately tiny and deliberately dumb: it sends *names of things
 * that happened* (a page was viewed, a research run started) and a couple of
 * scalar props. It never sends intake answers, chat text, or anything the user
 * typed — the backend drops anything not on its allowlist anyway.
 *
 * Privacy:
 *  - off by default when the browser sends Do-Not-Track;
 *  - a one-click opt-out persisted in localStorage (surfaced in the footer);
 *  - the only identifier attached is the same anonymous session id the rest of
 *    the app already uses.
 *
 * It must never be able to break the product: every path is wrapped, there is no
 * blocking call, and a failed send is silently ignored.
 */
const OPTOUT_KEY = "saathi_analytics_optout";
const SESSION_KEY = "grameenai_session";
const MAX_BATCH = 20;
const FLUSH_DELAY_MS = 2500;

export type AnalyticsProps = Record<string, string | number>;
type QueuedEvent = { name: string; props?: AnalyticsProps; ts: number };

let queue: QueuedEvent[] = [];
let flushTimer: ReturnType<typeof setTimeout> | null = null;

function readStorage(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

/** True when the user has explicitly opted out via the footer toggle. */
export function isOptedOut(): boolean {
  if (typeof window === "undefined") return false;
  return readStorage(OPTOUT_KEY) === "1";
}

/** True when analytics may run: not opted out and not sending Do-Not-Track. */
export function analyticsAllowed(): boolean {
  if (typeof window === "undefined") return false;
  if (isOptedOut()) return false;
  const nav = window.navigator as Navigator & { doNotTrack?: string };
  const dnt = nav.doNotTrack ?? (window as Window & { doNotTrack?: string }).doNotTrack;
  if (dnt === "1" || dnt === "yes") return false;
  return true;
}

/** Persist the opt-out choice. Turning it off clears anything already queued. */
export function setOptOut(optOut: boolean): void {
  if (typeof window === "undefined") return;
  try {
    if (optOut) window.localStorage.setItem(OPTOUT_KEY, "1");
    else window.localStorage.removeItem(OPTOUT_KEY);
  } catch {
    /* ignore */
  }
  if (optOut) queue = [];
}

/** Record one event. Fire-and-forget; safe to call anywhere in the UI. */
export function track(name: string, props?: AnalyticsProps): void {
  if (!analyticsAllowed()) return;
  queue.push({ name, props, ts: Date.now() });
  if (queue.length >= MAX_BATCH) {
    void flush();
    return;
  }
  if (flushTimer) return;
  flushTimer = setTimeout(() => {
    void flush();
  }, FLUSH_DELAY_MS);
}

/** Send whatever is queued. Never throws. */
export async function flush(): Promise<void> {
  if (flushTimer) {
    clearTimeout(flushTimer);
    flushTimer = null;
  }
  if (!queue.length) return;
  const batch = queue.splice(0, MAX_BATCH);
  const sessionId = readStorage(SESSION_KEY) || undefined;
  try {
    await fetch(`${API_BASE}/api/analytics/events`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId, events: batch }),
      keepalive: true,
    });
  } catch {
    /* analytics is best-effort — never surface a failure to the user */
  }
}
