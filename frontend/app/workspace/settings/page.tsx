"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useI18n } from "@/lib/i18n";
import { advisorMe, updateAdvisor, advisorLogout, type AdvisorAuth } from "@/lib/advisor";
import { LogOut, AlertCircle, CheckCircle2 } from "lucide-react";
export default function SettingsPage() {
  const { t, locale, setLocale } = useI18n();
  const router = useRouter();
  const [me, setMe] = useState<AdvisorAuth | null>(null);
  const [name, setName] = useState("");
  const [orgName, setOrgName] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    advisorMe()
      .then((m) => {
        setMe(m);
        setName(m.name);
        setOrgName(m.org_name || "");
      })
      .catch(() => {
        router.replace("/workspace/login");
      });
  }, [router]);

  const updateProfile = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setSaved(false);
    setLoading(true);
    try {
      await updateAdvisor(me!.id, { name, org_name: orgName || undefined });
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : t("workspace.error"));
    } finally {
      setLoading(false);
    }
  };

  const handleLogout = () => {
    advisorLogout();
  };

  if (!me) {
    return (
      <div style={{ padding: "32px 20px", textAlign: "center", color: "var(--text-muted)" }}>
        {t("workspace.loading")}
      </div>
    );
  }

  return (
    <div style={{ padding: "24px 20px", maxWidth: "720px", margin: "0 auto" }}>
      <nav style={{ marginBottom: "16px" }}>
        <a
          href="/workspace"
          onClick={() => router.push("/workspace")}
          style={{ display: "inline-flex", alignItems: "center", gap: "8px", fontSize: "0.84rem", color: "var(--text-secondary)", textDecoration: "none" }}
        >
          <svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>
          {t("workspace.back")}
        </a>
      </nav>

      <h1 style={{ fontSize: "1.25rem", fontWeight: 800, marginBottom: "6px" }}>{t("workspace.settings")}</h1>
      <p style={{ fontSize: "0.86rem", color: "var(--text-muted)", marginBottom: "20px" }}>{me.email}</p>

      {error && (
        <div style={{ marginBottom: "16px", padding: "10px 14px", borderRadius: "var(--radius-md)", background: "rgba(248,113,113,0.1)", border: "1px solid rgba(248,113,113,0.25)", color: "var(--error)", fontSize: "0.84rem" }}>
          <AlertCircle size={16} style={{ marginRight: "8px" }} /> {error}
        </div>
      )}
      {saved && (
        <div style={{ marginBottom: "16px", padding: "10px 14px", borderRadius: "var(--radius-md)", background: "rgba(34,211,165,0.1)", border: "1px solid rgba(34,211,165,0.25)", color: "var(--success)", fontSize: "0.84rem", display: "flex", alignItems: "center", gap: "8px" }}>
          <CheckCircle2 size={16} /> Saved.
        </div>
      )}

      <form onSubmit={updateProfile}>
        <div style={{ marginBottom: "20px" }}>
          <label style={{ display: "block", fontSize: "0.8rem", color: "var(--text-secondary)", marginBottom: "6px" }}>{t("workspace.name")}</label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            style={{ width: "100%", padding: "10px 12px", fontSize: "0.88rem", borderRadius: "var(--radius-md)", border: "1px solid var(--border-bright)", background: "var(--bg-surface)", color: "var(--text-primary)", outline: "none" }}
          />
        </div>
        <div style={{ marginBottom: "20px" }}>
          <label style={{ display: "block", fontSize: "0.8rem", color: "var(--text-secondary)", marginBottom: "6px" }}>{t("workspace.org_name")}</label>
          <input
            type="text"
            value={orgName}
            onChange={(e) => setOrgName(e.target.value)}
            style={{ width: "100%", padding: "10px 12px", fontSize: "0.88rem", borderRadius: "var(--radius-md)", border: "1px solid var(--border-bright)", background: "var(--bg-surface)", color: "var(--text-primary)", outline: "none" }}
          />
        </div>
        <div style={{ marginBottom: "6px" }}>
          <label style={{ display: "block", fontSize: "0.8rem", color: "var(--text-secondary)", marginBottom: "6px" }}>{t("workspace.locale")}</label>
          <select
            value={locale}
            onChange={(e) => setLocale(e.target.value as "en" | "hi")}
            style={{ width: "100%", padding: "10px 12px", fontSize: "0.88rem", borderRadius: "var(--radius-md)", border: "1px solid var(--border-bright)", background: "var(--bg-surface)", color: "var(--text-primary)", outline: "none" }}
          >
            <option value="en">{t("workspace.locale_en")}</option>
            <option value="hi">{t("workspace.locale_hi")}</option>
          </select>
        </div>
        <button
          type="submit"
          disabled={loading}
          style={{ width: "100%", padding: "11px", fontSize: "0.9rem", fontWeight: 700, borderRadius: "var(--radius-md)", border: "none", background: "var(--accent)", color: "#fff", cursor: loading ? "not-allowed" : "pointer" }}
        >
          {loading ? t("workspace.loading") : "Save profile"}
        </button>
      </form>

      <div style={{ marginTop: "30px" }}>
        <button
          onClick={handleLogout}
          style={{ display: "flex", alignItems: "center", gap: "8px", padding: "10px 16px", fontSize: "0.88rem", color: "var(--error)", border: "1px solid var(--error)", borderRadius: "var(--radius-md)", background: "transparent", cursor: "pointer" }}
        >
          <LogOut size={16} /> {t("workspace.logout")}
        </button>
      </div>
    </div>
  );
}
