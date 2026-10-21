/**
 * frontend/lib/advisor.ts — API client for the advisor / CA workspace (WS-11).
 *
 * Every call goes to ``/api/advisor/*`` with a bearer token taken from
 * localStorage (key ``advisor_token``). A bearer header is used (not a cookie)
 * because the app is deployed cross-origin (frontend on Vercel, backend on
 * Render); the security property is advisor isolation, enforced in the
 * repository layer regardless of transport.
 *
 * A 401 clears the token and sends the user to /workspace/login so a stale or
 * revoked session never leaves the user staring at a blank error.
 */

import { API_BASE } from "./api";

const TOKEN_KEY = "advisor_token";
type Json = Record<string, unknown>;

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(TOKEN_KEY, token);
  } catch {
    /* storage unavailable — token lives only in memory this session */
  }
}

export function clearToken(): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* ignore */
  }
}

function authHeaders(): HeadersInit {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function request(path: string, init: RequestInit = {}): Promise<Response> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { ...authHeaders(), ...(init.headers || {}) },
  });
  if (res.status === 401 && typeof window !== "undefined") {
    // Stale / revoked session — log out and send the user to sign in.
    clearToken();
    try {
      window.location.href = "/workspace/login";
    } catch {
      /* ignore */
    }
  }
  return res;
}

// ─────────────────────────────────────────────────────────────────────────────
// Auth
// ─────────────────────────────────────────────────────────────────────────────

export interface AdvisorAuth {
  id: string;
  email: string;
  name: string;
  org_name?: string;
  locale: string;
  plan: string;
  token: string;
}

export async function advisorSignup(body: {
  email: string;
  password: string;
  name: string;
  org_name?: string;
}): Promise<AdvisorAuth> {
  const res = await request("/api/advisor/auth/signup", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await res.text());
  const data = (await res.json()) as AdvisorAuth & { token?: string };
  if (data.token) setToken(data.token);
  return {
    id: data.id,
    email: data.email,
    name: data.name,
    org_name: data.org_name as string,
    locale: data.locale,
    plan: data.plan,
    token: data.token ?? "",
  };
}

export async function advisorLogin(body: {
  email: string;
  password: string;
}): Promise<AdvisorAuth> {
  const res = await request("/api/advisor/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await res.text());
  const data = (await res.json()) as AdvisorAuth & { token?: string };
  if (data.token) setToken(data.token);
  return {
    id: data.id,
    email: data.email,
    name: data.name,
    org_name: data.org_name as string,
    locale: data.locale,
    plan: data.plan,
    token: data.token ?? "",
  };
}

export async function advisorLogout(): Promise<void> {
  try {
    await request("/api/advisor/auth/logout", { method: "POST" });
  } finally {
    clearToken();
    if (typeof window !== "undefined") window.location.href = "/workspace/login";
  }
}

export async function advisorMe(): Promise<AdvisorAuth> {
  const res = await request("/api/advisor/auth/me");
  if (!res.ok) throw new Error(await res.text());
  const data = (await res.json()) as AdvisorAuth & { token?: string };
  return {
    id: data.id,
    email: data.email,
    name: data.name,
    org_name: data.org_name as string,
    locale: data.locale,
    plan: data.plan,
    token: getToken() ?? "",
  };
}

export async function updateAdvisor(advisorId: string, body: {
  name?: string;
  org_name?: string;
  locale?: string;
}): Promise<AdvisorAuth> {
  const res = await request(`/api/advisor/auth/me`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await res.text());
  const data = (await res.json()) as AdvisorAuth;
  return data;
}

// ─────────────────────────────────────────────────────────────────────────────
// Clients
// ─────────────────────────────────────────────────────────────────────────────

export interface TopScheme {
  scheme_id: string;
  name: string;
  status: string;
  status_label: string;
  score: number;
  tier_group?: string;
  source_url: string;
  last_verified_at: string;
}

export interface Client {
  id: string;
  label: string;
  sector?: string | null;
  state?: string | null;
  stage?: string | null;
  readiness?: number | null;
  /** Best scheme of the latest deterministic match (empty until a match runs). */
  top_scheme?: TopScheme | null;
  profile: Json;
  created_at: number;
  updated_at: number;
}

export interface ClientListResponse {
  clients: Client[];
}

export async function listClients(params?: {
  q?: string;
  sector?: string;
  state?: string;
  stage?: string;
  readiness?: string;
}): Promise<ClientListResponse> {
  const search = new URLSearchParams();
  if (params?.q) search.set("q", params.q);
  if (params?.sector) search.set("sector", params.sector);
  if (params?.state) search.set("state", params.state);
  if (params?.stage) search.set("stage", params.stage);
  if (params?.readiness) search.set("readiness", params.readiness);
  const path = `/api/advisor/clients${search.toString() ? "?" + search.toString() : ""}`;
  const res = await request(path);
  if (!res.ok) throw new Error(await res.text());
  return (await res.json()) as ClientListResponse;
}

export interface ClientProfileInput {
  label: string;
  sector?: string;
  state?: string;
  stage?: string;
  profile: Record<string, string>;
}

export async function createClient(body: ClientProfileInput): Promise<Client> {
  const res = await request("/api/advisor/clients", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await res.text());
  return (await res.json()) as Client;
}

export async function getClient(clientId: string): Promise<Client> {
  const res = await request(`/api/advisor/clients/${encodeURIComponent(clientId)}`);
  if (!res.ok) throw new Error(await res.text());
  return (await res.json()) as Client;
}

export interface ClientUpdateInput {
  label?: string;
  sector?: string;
  state?: string;
  stage?: string;
  profile?: Record<string, string>;
}

export async function updateClient(
  clientId: string,
  body: ClientUpdateInput,
): Promise<Client> {
  const res = await request(
    `/api/advisor/clients/${encodeURIComponent(clientId)}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
  );
  if (!res.ok) throw new Error(await res.text());
  return (await res.json()) as Client;
}

export async function deleteClient(clientId: string): Promise<void> {
  const res = await request(
    `/api/advisor/clients/${encodeURIComponent(clientId)}`,
    { method: "DELETE" },
  );
  if (!res.ok) throw new Error(await res.text());
}

// ─────────────────────────────────────────────────────────────────────────────
// Eligibility (match + bulk)
// ─────────────────────────────────────────────────────────────────────────────

export interface MatchInput {
  topic?: string;
  amount?: number;
  lang?: string;
  intake?: Record<string, string>;
}

export interface MatchResult {
  client_id: string;
  label: string;
  readiness?: number | null;
  business_class: string;
  business_label: string;
  ranked: SchemeVerdict[];
  snapshot_id: string;
}

export interface SchemeVerdict {
  scheme_id: string;
  name: string;
  status: string;
  status_label: string;
  score: number;
  tier_group?: string | null;
  documents: string[];
  matched: { label: string }[];
  failed: { label: string }[];
  source_url: string;
  last_verified_at: string;
}

export async function matchClient(clientId: string, body: MatchInput): Promise<MatchResult> {
  const res = await request(
    `/api/advisor/clients/${encodeURIComponent(clientId)}/match`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
  );
  if (!res.ok) throw new Error(await res.text());
  return (await res.json()) as MatchResult;
}

export interface BulkMatchRequest {
  client_ids: string[];
}

export interface BulkMatchResult {
  engine_version: string;
  results: Json[];
}

export async function bulkMatch(body: BulkMatchRequest): Promise<BulkMatchResult> {
  const res = await request("/api/advisor/eligibility/bulk", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await res.text());
  return (await res.json()) as BulkMatchResult;
}

// ─────────────────────────────────────────────────────────────────────────────
// Notes
// ─────────────────────────────────────────────────────────────────────────────

export interface Note {
  id: string;
  body: string;
  created_at: number;
}

export async function listNotes(clientId: string): Promise<Note[]> {
  const res = await request(`/api/advisor/clients/${encodeURIComponent(clientId)}/notes`);
  if (!res.ok) throw new Error(await res.text());
  const data = (await res.json()) as { notes: Note[] };
  return data.notes;
}

export async function addNote(clientId: string, body: string): Promise<Note> {
  const res = await request(
    `/api/advisor/clients/${encodeURIComponent(clientId)}/notes`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ body }),
    },
  );
  if (!res.ok) throw new Error(await res.text());
  return (await res.json()) as Note;
}

export async function deleteNote(noteId: string): Promise<void> {
  const res = await request(`/api/advisor/notes/${encodeURIComponent(noteId)}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error(await res.text());
}

// ─────────────────────────────────────────────────────────────────────────────
// Reports
// ─────────────────────────────────────────────────────────────────────────────

export interface Report {
  id: string;
  kind: string;
  client_ids: string[];
  locale: string;
  file_path: string;
  created_at: number;
}

export async function generateReport(body: {
  kind: "combined" | "single";
  client_ids: string[];
  locale: string;
}): Promise<Report> {
  const res = await request("/api/advisor/reports", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await res.text());
  return (await res.json()) as Report;
}

export async function listReports(): Promise<Report[]> {
  const res = await request("/api/advisor/reports");
  if (!res.ok) throw new Error(await res.text());
  const data = (await res.json()) as { reports: Report[] };
  return data.reports;
}

export async function downloadReport(reportId: string): Promise<void> {
  const res = await request(`/api/advisor/reports/${encodeURIComponent(reportId)}/pdf`);
  if (!res.ok) throw new Error(await res.text());
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `advisor-report-${reportId}.pdf`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
