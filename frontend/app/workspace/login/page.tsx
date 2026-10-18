"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useI18n } from "@/lib/i18n";
import { advisorSignup, advisorLogin } from "@/lib/advisor";
import { Mail, Lock, User, AlertCircle } from "lucide-react";

export default function LoginPage() {
  const { t } = useI18n();
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [orgName, setOrgName] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      if (mode === "signup") {
        await advisorSignup({ email, password, name, org_name: orgName || undefined });
      } else {
        await advisorLogin({ email, password });
      }
      router.replace("/workspace");
    } catch (err: unknown) {
      setError(
        err instanceof Error ? err.message : t("workspace.error"),
      );
    } finally {
      setLoading(false);
    }
  };

  // If already signed in, go straight to the dashboard.
  useEffect(() => {
    const token = (() => {
      try {
        return window.localStorage.getItem("advisor_token");
      } catch {
        return null;
      }
    })();
    if (token) router.replace("/workspace");
  }, [router]);

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        height: "100vh",
        background: "var(--bg-main)",
      }}
    >
      <div
        style={{
          width: "100%",
          maxWidth: "420px",
          padding: "0 20px",
          background: "var(--bg-card)",
          border: "1px solid var(--border)",
          borderRadius: "var(--radius-lg)",
        }}
      >
        <div style={{ padding: "28px 32px 10px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "6px" }}>
            <User size={22} color="var(--accent)" />
            <div style={{ fontWeight: 800, fontSize: "1.15rem" }}>
              Your AI Business Saathi
            </div>
          </div>
          <h1 style={{ fontSize: "1.1rem", fontWeight: 700, margin: "8px 0 2px", color: "var(--text-primary)" }}>
            {mode === "signup" ? t("workspace.signup.title") : t("workspace.login.title")}
          </h1>
          <p style={{ fontSize: "0.82rem", color: "var(--text-muted)", marginBottom: "20px" }}>
            {mode === "signup" ? t("workspace.login.subtitle") : t("workspace.login.subtitle")}
          </p>

          {error && (
            <div
              style={{
                padding: "8px 12px",
                marginBottom: "14px",
                borderRadius: "var(--radius-md)",
                background: "rgba(248,113,113,0.1)",
                border: "1px solid rgba(248,113,113,0.25)",
                color: "var(--error)",
                fontSize: "0.82rem",
                display: "flex",
                alignItems: "center",
                gap: "8px",
              }}
            >
              <AlertCircle size={14} /> {error}
            </div>
          )}

          <form onSubmit={handleSubmit}>
            <div style={{ marginBottom: "14px" }}>
              <label style={{ display: "block", fontSize: "0.8rem", color: "var(--text-secondary)", marginBottom: "6px" }}>
                {t("workspace.email")}
              </label>
              <input
                type="email"
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                style={{
                  width: "100%",
                  padding: "10px 12px",
                  fontSize: "0.88rem",
                  borderRadius: "var(--radius-md)",
                  border: "1px solid var(--border-bright)",
                  background: "var(--bg-surface)",
                  color: "var(--text-primary)",
                  outline: "none",
                }}
              />
              <Mail size={14} style={{ color: "var(--text-muted)" }} />
            </div>

            <div style={{ marginBottom: "16px" }}>
              <label style={{ display: "block", fontSize: "0.8rem", color: "var(--text-secondary)", marginBottom: "6px" }}>
                {t("workspace.password")}
              </label>
              <input
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                style={{
                  width: "100%",
                  padding: "10px 12px",
                  fontSize: "0.88rem",
                  borderRadius: "var(--radius-md)",
                  border: "1px solid var(--border-bright)",
                  background: "var(--bg-surface)",
                  color: "var(--text-primary)",
                  outline: "none",
                }}
              />
              <Lock size={14} style={{ color: "var(--text-muted)" }} />
            </div>

            {mode === "signup" && (
              <>
                <div style={{ marginBottom: "14px" }}>
                  <label style={{ display: "block", fontSize: "0.8rem", color: "var(--text-secondary)", marginBottom: "6px" }}>
                    {t("workspace.name")}
                  </label>
                  <input
                    type="text"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    style={{
                      width: "100%",
                      padding: "10px 12px",
                      fontSize: "0.88rem",
                      borderRadius: "var(--radius-md)",
                      border: "1px solid var(--border-bright)",
                      background: "var(--bg-surface)",
                      color: "var(--text-primary)",
                      outline: "none",
                    }}
                  />
                </div>
                <div style={{ marginBottom: "16px" }}>
                  <label style={{ display: "block", fontSize: "0.8rem", color: "var(--text-secondary)", marginBottom: "6px" }}>
                    {t("workspace.org_name")}
                  </label>
                  <input
                    type="text"
                    value={orgName}
                    onChange={(e) => setOrgName(e.target.value)}
                    style={{
                      width: "100%",
                      padding: "10px 12px",
                      fontSize: "0.88rem",
                      borderRadius: "var(--radius-md)",
                      border: "1px solid var(--border-bright)",
                      background: "var(--bg-surface)",
                      color: "var(--text-primary)",
                      outline: "none",
                    }}
                  />
                </div>
              </>
            )}

            <button
              type="submit"
              disabled={loading}
              style={{
                width: "100%",
                padding: "11px",
                fontSize: "0.95rem",
                fontWeight: 700,
                borderRadius: "var(--radius-md)",
                border: "none",
                background: "var(--accent)",
                color: "#fff",
                cursor: loading ? "not-allowed" : "pointer",
                opacity: loading ? 0.7 : 1,
              }}
            >
              {loading ? t("workspace.loading") : mode === "signup" ? t("workspace.signup") : t("workspace.login")}
            </button>
          </form>
        </div>
        <div style={{ padding: "10px 32px 26px", borderTop: "1px solid var(--border)" }}>
          <p style={{ fontSize: "0.82rem", color: "var(--text-muted)", marginBottom: "10px", textAlign: "center" }}>
            {mode === "signup"
              ? `${t("workspace.have_account")} `
              : `${t("workspace.no_account")} `}
            <button
              type="button"
              onClick={() => setMode(mode === "signup" ? "login" : "signup")}
              style={{
                background: "none",
                border: "none",
                color: "var(--accent)",
                cursor: "pointer",
                fontSize: "inherit",
                fontWeight: 600,
                padding: 0,
              }}
            >
              {mode === "signup" ? t("workspace.have_account") : t("workspace.no_account")}
            </button>
          </p>
        </div>
      </div>
    </div>
  );
}
