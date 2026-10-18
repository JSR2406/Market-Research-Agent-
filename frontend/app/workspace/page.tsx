"use client";

import { useEffect, useState, useCallback } from "react";
import { useI18n } from "@/lib/i18n";
import { listClients, type Client } from "@/lib/advisor";
import { Search, Plus, Circle, AlertTriangle, TrendingUp } from "lucide-react";
export default function WorkspacePage() {
  const { t } = useI18n();
  const [clients, setClients] = useState<Client[]>([]);
  const [q, setQ] = useState("");
  const [sector, setSector] = useState("");
  const [readiness, setReadiness] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const clientsRes = await listClients({ q, sector, readiness });
      setClients(clientsRes.clients);
      setError("");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : t("workspace.error"));
    } finally {
      setLoading(false);
    }
  }, [q, sector, readiness, t]);

  useEffect(() => {
    load();
  }, [load]);

  const readinessBand = (r: number | null | undefined) => {
    if (r == null) return "unknown";
    if (r >= 70) return "high";
    if (r >= 40) return "medium";
    return "low";
  };

  const bandColor = (band: string) => {
    switch (band) {
      case "high": return "var(--success)";
      case "medium": return "var(--warn)";
      case "low": return "var(--error)";
      default: return "var(--text-muted)";
    }
  };

  const avgReadiness = clients.filter((c) => c.readiness != null).reduce((a, c) => a + (c.readiness ?? 0), 0) / Math.max(clients.filter((c) => c.readiness != null).length, 1);

  if (loading) {
    return (
      <div style={{ padding: "32px 20px", textAlign: "center", color: "var(--text-muted)" }}>
        {t("workspace.loading")}
      </div>
    );
  }

  return (
    <div>
      <header style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "20px" }}>
        <div>
          <h1 style={{ fontSize: "1.25rem", fontWeight: 800, letterSpacing: "-0.02em", marginBottom: "2px" }}>
            {t("workspace.dashboard")}
          </h1>
          <p style={{ fontSize: "0.86rem", color: "var(--text-muted)" }}>
            {t("workspace.subtitle")}
          </p>
        </div>
        <button
          onClick={() => window.location.href = "/workspace/clients/new"}
          style={{
            display: "flex", alignItems: "center", gap: "8px", padding: "9px 14px",
            fontSize: "0.88rem", fontWeight: 700, borderRadius: "var(--radius-md)",
            border: "1px solid var(--border-bright)", background: "var(--accent)", color: "#fff",
            cursor: "pointer",
          }}
        >
          <Plus size={16} /> {t("workspace.add_client")}
        </button>
      </header>

      {/* Stats */}
      <div style={{ display: "flex", gap: "12px", marginBottom: "24px", flexWrap: "wrap" }}>
        <div style={{ flex: 1, minWidth: "150px", padding: "16px 18px", borderRadius: "var(--radius-lg)", background: "var(--bg-card)", border: "1px solid var(--border)" }}>
          <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.06em" }}>Clients</div>
          <div style={{ fontSize: "1.75rem", fontWeight: 800, marginTop: "4px" }}>{clients.length}</div>
        </div>
        <div style={{ flex: 1, minWidth: "150px", padding: "16px 18px", borderRadius: "var(--radius-lg)", background: "var(--bg-card)", border: "1px solid var(--border)" }}>
          <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.06em" }}>Avg readiness</div>
          <div style={{ fontSize: "1.75rem", fontWeight: 800, marginTop: "4px" }}>{Number.isFinite(avgReadiness) ? avgReadiness.toFixed(0) : "—"} / 100</div>
        </div>
        <div style={{ flex: 1, minWidth: "150px", padding: "16px 18px", borderRadius: "var(--radius-lg)", background: "var(--bg-card)", border: "1px solid var(--border)" }}>
          <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.06em" }}>{t("workspace.readiness_score")}</div>
          <div style={{ fontSize: "1.75rem", fontWeight: 800, marginTop: "4px", color: bandColor(readinessBand(avgReadiness || null)) }}>{Number.isFinite(avgReadiness) ? avgReadiness.toFixed(0) : "—"}</div>
        </div>
      </div>

      {error && (
        <div style={{ marginBottom: "16px", padding: "10px 14px", borderRadius: "var(--radius-md)", background: "rgba(248,113,113,0.1)", border: "1px solid rgba(248,113,113,0.25)", color: "var(--error)", fontSize: "0.84rem" }}>
          <AlertTriangle size={16} style={{ marginRight: "8px" }} /> {error}
        </div>
      )}

      {/* Filters */}
      <div style={{ display: "flex", gap: "10px", marginBottom: "18px", flexWrap: "wrap", alignItems: "end" }}>
        <div style={{ flex: 1, minWidth: "200px" }}>
          <label style={{ display: "block", fontSize: "0.75rem", color: "var(--text-muted)", marginBottom: "6px" }}>{t("workspace.search")}</label>
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder={t("workspace.search")}
            style={{ width: "100%", padding: "9px 12px", fontSize: "0.86rem", borderRadius: "var(--radius-md)", border: "1px solid var(--border-bright)", background: "var(--bg-surface)", color: "var(--text-primary)", outline: "none" }}
          />
          <Search size={16} style={{ color: "var(--text-muted)" }} />
        </div>
        <div style={{ minWidth: "150px" }}>
          <label style={{ display: "block", fontSize: "0.75rem", color: "var(--text-muted)", marginBottom: "6px" }}>{t("workspace.filter_sector")}</label>
          <select
            value={sector}
            onChange={(e) => setSector(e.target.value)}
            style={{ width: "100%", padding: "9px 12px", fontSize: "0.86rem", borderRadius: "var(--radius-md)", border: "1px solid var(--border-bright)", background: "var(--bg-surface)", color: "var(--text-primary)", outline: "none" }}
          >
            <option value="">{t("workspace.filter_sector")}</option>
            <option value="retail">Retail</option>
            <option value="textiles">Textiles</option>
            <option value="services">Services</option>
            <option value="manufacturing">Manufacturing</option>
            <option value="agriculture">Agriculture</option>
          </select>
        </div>
        <div style={{ minWidth: "150px" }}>
          <label style={{ display: "block", fontSize: "0.75rem", color: "var(--text-muted)", marginBottom: "6px" }}>{t("workspace.filter_readiness")}</label>
          <select
            value={readiness}
            onChange={(e) => setReadiness(e.target.value)}
            style={{ width: "100%", padding: "9px 12px", fontSize: "0.86rem", borderRadius: "var(--radius-md)", border: "1px solid var(--border-bright)", background: "var(--bg-surface)", color: "var(--text-primary)", outline: "none" }}
          >
            <option value="">{t("workspace.filter_readiness")}</option>
            <option value="high">{t("workspace.readiness_high")}</option>
            <option value="medium">{t("workspace.readiness_medium")}</option>
            <option value="low">{t("workspace.readiness_low")}</option>
          </select>
        </div>
      </div>

      {/* Client list */}
      <div>
        <div style={{ fontSize: "0.8rem", color: "var(--text-muted)", marginBottom: "10px", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em" }}>
          Managed clients
        </div>
        {clients.length === 0 ? (
          <div style={{ padding: "32px 24px", textAlign: "center", color: "var(--text-muted)", border: "1px dashed var(--border)", borderRadius: "var(--radius-lg)", background: "var(--bg-surface)" }}>
            <Circle size={32} style={{ marginBottom: "10px", color: "var(--text-muted)" }} />
            <p style={{ fontSize: "0.9rem" }}>{t("workspace.clients_empty")}</p>
          </div>
        ) : (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))", gap: "14px" }}>
            {clients.map((c) => (
              <a
                key={c.id}
                href={`/workspace/clients/${c.id}`}
                onClick={(e) => { e.preventDefault(); window.location.href = `/workspace/clients/${c.id}`; }}
                style={{
                  display: "block", padding: "16px 18px", borderRadius: "var(--radius-lg)",
                  border: "1px solid var(--border)", background: "var(--bg-card)",
                  color: "inherit", textDecoration: "none", transition: "all 0.15s",
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "8px" }}>
                  <div style={{ fontWeight: 800, fontSize: "0.95rem", color: "var(--text-primary)" }}>{c.label}</div>
                  <span
                    style={{
                      display: "inline-flex", alignItems: "center", gap: "6px", padding: "3px 9px",
                      borderRadius: "999px", fontSize: "0.72rem", fontWeight: 700,
                      color: bandColor(readinessBand(c.readiness)),
                      background: `${bandColor(readinessBand(c.readiness))}1a`,
                      border: `1px solid ${bandColor(readinessBand(c.readiness))}44`,
                    }}
                  >
                    <Circle size={10} fill={bandColor(readinessBand(c.readiness))} />
                    {c.readiness != null ? c.readiness : "—"}
                  </span>
                </div>
                {c.sector && <div style={{ fontSize: "0.78rem", color: "var(--text-secondary)", marginBottom: "2px" }}>{t("workspace.sector")}: {c.sector}</div>}
                {c.state && <div style={{ fontSize: "0.78rem", color: "var(--text-secondary)", marginBottom: "2px" }}>{t("workspace.state")}: {c.state}</div>}
                {c.stage && <div style={{ fontSize: "0.78rem", color: "var(--text-secondary)", marginBottom: "10px" }}>{t("workspace.stage")}: {c.stage}</div>}
                <div style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>
                  <TrendingUp size={14} style={{ marginRight: "6px" }} /> {t("workspace.matches")}
                </div>
              </a>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
