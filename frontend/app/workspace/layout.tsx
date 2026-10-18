"use client";

import { useEffect, useState, type ReactNode } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useI18n } from "@/lib/i18n";
import { getToken, clearToken } from "@/lib/advisor";
import { Layout, LogOut, Users, FileText, Settings } from "lucide-react";

const NAV = [
  { href: "/workspace", label: "workspace.dashboard", icon: Layout },
  { href: "/workspace/clients", label: "workspace.clients", icon: Users },
  { href: "/workspace/reports", label: "workspace.reports", icon: FileText },
  { href: "/workspace/settings", label: "workspace.settings", icon: Settings },
];

export default function WorkspaceLayout({ children }: { children: ReactNode }) {
  const { t, locale, setLocale } = useI18n();
  const router = useRouter();
  const pathname = usePathname();
  const [token, setTokenState] = useState<string | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    setTokenState(getToken());
    setReady(true);
  }, []);

  // Not signed in: only the login page may render; everything else redirects.
  if (!ready) return null;
  if (!token && pathname !== "/workspace/login") {
    router.replace("/workspace/login");
    return null;
  }

  const handleLogout = () => {
    clearToken();
    router.replace("/workspace/login");
  };

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100vh",
        background: "var(--bg-main)",
        color: "var(--text-primary)",
      }}
    >
      <nav
        style={{
          width: "220px",
          flexShrink: 0,
          background: "var(--bg-surface)",
          borderRight: "1px solid var(--border)",
          padding: "20px 0",
        }}
      >
        <div style={{ padding: "0 18px 20px", marginBottom: "24px" }}>
          <div style={{ fontWeight: 800, fontSize: "1.1rem", letterSpacing: "-0.02em" }}>
            Your AI Business Saathi
          </div>
          <div style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginTop: "2px" }}>
            Advisor workspace
          </div>
        </div>
        {NAV.map((item) => {
          const Icon = item.icon;
          const active = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              onClick={() => router.push(item.href)}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "10px",
                padding: "10px 18px",
                fontSize: "0.86rem",
                color: active ? "var(--accent)" : "var(--text-secondary)",
                background: active ? "rgba(79,142,247,0.08)" : "transparent",
                borderRight: active ? "3px solid var(--accent)" : "none",
                textDecoration: "none",
                cursor: "pointer",
                border: "none",
                outline: "none",
              }}
            >
              <Icon size={16} />
              {t(item.label)}
            </Link>
          );
        })}
        <div style={{ padding: "0 18px" }}>
          <button
            onClick={handleLogout}
            style={{
              display: "flex",
              alignItems: "center",
              gap: "10px",
              width: "100%",
              padding: "10px 18px",
              fontSize: "0.86rem",
              color: "var(--text-secondary)",
              background: "transparent",
              border: "none",
              outline: "none",
              cursor: "pointer",
              textAlign: "left",
            }}
          >
            <LogOut size={16} /> {t("workspace.logout")}
          </button>
        </div>
      </nav>

      <main
        style={{
          flex: 1,
          overflowY: "auto",
          padding: "24px clamp(16px, 4vw, 32px)",
          background: "var(--bg-main)",
        }}
      >
        {children}
      </main>

      <div
        style={{
          padding: "14px 24px",
          borderTop: "1px solid var(--border)",
          fontSize: "0.72rem",
          color: "var(--text-muted)",
          display: "flex",
          alignItems: "center",
          gap: "8px",
        }}
      >
        <span style={{ textTransform: "uppercase", letterSpacing: "0.05em", fontWeight: 700 }}>
          {t("workspace.free_plan")}
        </span>
        <label
          style={{
            display: "flex",
            alignItems: "center",
            gap: "6px",
            marginLeft: "auto",
            cursor: "pointer",
            fontSize: "0.78rem",
            color: "var(--text-secondary)",
          }}
        >
          {t("workspace.locale")}:{" "}
          <select
            value={locale}
            onChange={(e) => {
              setLocale(e.target.value as "en" | "hi");
            }}
            style={{
              background: "transparent",
              border: "none",
              color: "inherit",
              fontSize: "inherit",
              cursor: "pointer",
              outline: "none",
            }}
          >
            <option value="en">{t("workspace.locale_en")}</option>
            <option value="hi">{t("workspace.locale_hi")}</option>
          </select>
        </label>
      </div>
    </div>
  );
}
