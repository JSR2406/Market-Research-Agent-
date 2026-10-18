"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useI18n } from "@/lib/i18n";
import { createClient } from "@/lib/advisor";
import { Mail, Building, MapPin, Calendar, CreditCard, Loader2, TrendingUp, type LucideIcon } from "lucide-react";

const INTAKE_FIELDS: { id: string; label: string; icon: LucideIcon; placeholder: string }[] = [
  { id: "business", label: "What kind of business is this?", icon: Building, placeholder: "e.g. kirana store, tailoring, dairy farm" },
  { id: "offering", label: "What exactly do you sell or do?", icon: Mail, placeholder: "e.g. groceries and staples" },
  { id: "scale", label: "How big is the business?", icon: TrendingUp, placeholder: "e.g. about ₹3,000 a day" },
  { id: "age", label: "How long has it been running?", icon: Calendar, placeholder: "e.g. 3 years" },
  { id: "earnings", label: "Roughly how much do you earn in a month?", icon: CreditCard, placeholder: "e.g. ₹25,000/month" },
  { id: "location", label: "Where is your business?", icon: MapPin, placeholder: "e.g. Pune, Maharashtra" },
  { id: "loan", label: "Have you taken a business loan before?", icon: CreditCard, placeholder: "e.g. no, first time" },
  { id: "need", label: "What do you need most right now?", icon: Mail, placeholder: "e.g. working capital" },
  { id: "registered", label: "Is the business registered (Udyam / GST)?", icon: Building, placeholder: "e.g. yes, registered" },
];

export default function NewClientPage() {
  const { t } = useI18n();
  const router = useRouter();
  const [label, setLabel] = useState("");
  const [sector, setSector] = useState("");
  const [state, setState] = useState("");
  const [stage, setStage] = useState("");
  const [profile, setProfile] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const client = await createClient({ label, sector, state, stage, profile });
      router.replace(`/workspace/clients/${client.id}`);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : t("workspace.error"));
    } finally {
      setLoading(false);
    }
  };

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

      <h1 style={{ fontSize: "1.25rem", fontWeight: 800, marginBottom: "6px" }}>{t("workspace.add_client")}</h1>
      <p style={{ fontSize: "0.86rem", color: "var(--text-muted)", marginBottom: "20px" }}>
        {t("workspace.subtitle")}
      </p>

      {error && (
        <div style={{ marginBottom: "16px", padding: "10px 14px", borderRadius: "var(--radius-md)", background: "rgba(248,113,113,0.1)", border: "1px solid rgba(248,113,113,0.25)", color: "var(--error)", fontSize: "0.84rem" }}>
          {error}
        </div>
      )}

      <form onSubmit={handleSubmit}>
        <div style={{ marginBottom: "16px" }}>
          <label style={{ display: "block", fontSize: "0.8rem", color: "var(--text-secondary)", marginBottom: "6px" }}>{t("workspace.name")} / {t("workspace.name")}</label>
          <input
            type="text"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder="e.g. Sharma Kirana Store"
            required
            style={{ width: "100%", padding: "10px 12px", fontSize: "0.88rem", borderRadius: "var(--radius-md)", border: "1px solid var(--border-bright)", background: "var(--bg-surface)", color: "var(--text-primary)", outline: "none" }}
          />
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "14px", marginBottom: "20px" }}>
          <div>
            <label style={{ display: "block", fontSize: "0.8rem", color: "var(--text-secondary)", marginBottom: "6px" }}>{t("workspace.filter_sector")}</label>
            <select value={sector} onChange={(e) => setSector(e.target.value)} style={{ width: "100%", padding: "10px 12px", fontSize: "0.86rem", borderRadius: "var(--radius-md)", border: "1px solid var(--border-bright)", background: "var(--bg-surface)", color: "var(--text-primary)", outline: "none" }}>
              <option value="">{t("workspace.filter_sector")}</option>
              <option value="retail">Retail</option>
              <option value="textiles">Textiles</option>
              <option value="services">Services</option>
              <option value="manufacturing">Manufacturing</option>
              <option value="agriculture">Agriculture</option>
            </select>
          </div>
          <div>
            <label style={{ display: "block", fontSize: "0.8rem", color: "var(--text-secondary)", marginBottom: "6px" }}>{t("workspace.filter_state")}</label>
            <input
              type="text"
              value={state}
              onChange={(e) => setState(e.target.value)}
              placeholder="e.g. MH"
              style={{ width: "100%", padding: "10px 12px", fontSize: "0.86rem", borderRadius: "var(--radius-md)", border: "1px solid var(--border-bright)", background: "var(--bg-surface)", color: "var(--text-primary)", outline: "none" }}
            />
          </div>
          <div>
            <label style={{ display: "block", fontSize: "0.8rem", color: "var(--text-secondary)", marginBottom: "6px" }}>{t("workspace.filter_stage")}</label>
            <select value={stage} onChange={(e) => setStage(e.target.value)} style={{ width: "100%", padding: "10px 12px", fontSize: "0.86rem", borderRadius: "var(--radius-md)", border: "1px solid var(--border-bright)", background: "var(--bg-surface)", color: "var(--text-primary)", outline: "none" }}>
              <option value="">{t("workspace.filter_stage")}</option>
              <option value="idea">Idea</option>
              <option value="operating">Operating</option>
              <option value="expanding">Expanding</option>
            </select>
          </div>
        </div>

        <div style={{ fontSize: "0.8rem", color: "var(--text-muted)", marginBottom: "10px", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em" }}>{t("workspace.profile")}</div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: "14px" }}>
          {INTAKE_FIELDS.map((f) => (
            <div key={f.id} style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
              <label style={{ fontSize: "0.82rem", fontWeight: 600, color: "var(--text-secondary)" }}>{f.label}</label>
              <input
                type="text"
                value={profile[f.id] || ""}
                onChange={(e) => setProfile({ ...profile, [f.id]: e.target.value })}
                placeholder={f.placeholder}
                style={{ padding: "9px 12px", fontSize: "0.86rem", borderRadius: "var(--radius-md)", border: "1px solid var(--border-bright)", background: "var(--bg-surface)", color: "var(--text-primary)", outline: "none" }}
              />
            </div>
          ))}
        </div>

        <div style={{ marginTop: "26px", display: "flex", justifyContent: "flex-end", gap: "10px" }}>
          <button
            type="button"
            onClick={() => router.push("/workspace")}
            style={{ padding: "10px 16px", fontSize: "0.88rem", borderRadius: "var(--radius-md)", border: "1px solid var(--border)", background: "transparent", color: "var(--text-secondary)", cursor: "pointer" }}
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={loading}
            style={{ padding: "10px 18px", fontSize: "0.88rem", fontWeight: 700, borderRadius: "var(--radius-md)", border: "none", background: "var(--accent)", color: "#fff", cursor: loading ? "not-allowed" : "pointer", opacity: loading ? 0.7 : 1 }}
          >
            {loading ? <Loader2 size={16} style={{ animation: "spin 1s linear infinite", marginRight: "8px" }} /> : ""}{t("workspace.add_client")}
          </button>
        </div>
      </form>
    </div>
  );
}
