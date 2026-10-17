"use client";
import { useCallback, useEffect, useState } from "react";
import { useI18n } from "@/lib/i18n";
import { motion } from "framer-motion";
import { API_BASE } from "@/lib/api";
import { track } from "@/lib/analytics";
import {
  AlertCircle,
  Clock,
  ExternalLink,
  Landmark,
  Loader2,
  MapPin,
  Search,
  Sprout,
} from "lucide-react";

/**
 * "Check today's market" — a published-data lookup with an honest freshness
 * label.
 *
 * The whole point of this card is the date. A mandi price is quoted together
 * with the day it belongs to ("Live, as of 2026-10-16 — 2 days old"), and when
 * the feed cannot be reached it says so rather than showing yesterday's number
 * as today's. Nothing here is estimated.
 */

type Kind = "mandi_price" | "pincode" | "ifsc";

type Row = Record<string, string | number | boolean | null>;

type Result = {
  dataset: string;
  available: boolean;
  live: boolean;
  stale: boolean;
  cached: boolean;
  as_of: string | null;
  as_of_known: boolean;
  fetched_at: string | null;
  lag_days: number | null;
  records: Row[];
  count: number;
  source_name: string;
  source_url: string;
  official_url: string;
  reason: string;
  note: string;
  error: string;
  disclaimer: string;
};

/** Chips show Hindi but send the canonical English name the feed expects. */
const CROPS: { id: string; key: string }[] = [
  { id: "Onion", key: "market.crop.onion" },
  { id: "Potato", key: "market.crop.potato" },
  { id: "Tomato", key: "market.crop.tomato" },
  { id: "Wheat", key: "market.crop.wheat" },
  { id: "Paddy", key: "market.crop.paddy" },
  { id: "Cotton", key: "market.crop.cotton" },
];

const KINDS: { id: Kind; key: string }[] = [
  { id: "mandi_price", key: "market.kind.mandi" },
  { id: "pincode", key: "market.kind.pincode" },
  { id: "ifsc", key: "market.kind.ifsc" },
];

const STORE_KEY = "saathi_market_query";

const inr = (n: unknown) => "₹" + Number(n || 0).toLocaleString("en-IN");

const txt = (v: unknown) => (v === null || v === undefined ? "" : String(v));

export default function MarketCheck() {
  const { t, backendLang } = useI18n();
  const [kind, setKind] = useState<Kind>("mandi_price");
  const [commodity, setCommodity] = useState("");
  const [market, setMarket] = useState("");
  const [state, setState] = useState("");
  const [pincode, setPincode] = useState("");
  const [ifsc, setIfsc] = useState("");
  const [result, setResult] = useState<Result | null>(null);
  const [loading, setLoading] = useState(false);
  const [offline, setOffline] = useState(false);

  // Remember the last thing they looked up, so a returning user can re-check
  // the same crop in one tap.
  useEffect(() => {
    try {
      const raw = localStorage.getItem(STORE_KEY);
      if (!raw) return;
      const saved = JSON.parse(raw) as Partial<Record<string, string>>;
      if (saved.kind === "mandi_price" || saved.kind === "pincode" || saved.kind === "ifsc") {
        setKind(saved.kind);
      }
      setCommodity(saved.commodity || "");
      setMarket(saved.market || "");
      setState(saved.state || "");
      setPincode(saved.pincode || "");
      setIfsc(saved.ifsc || "");
    } catch {
      /* a corrupt value must never break the page */
    }
  }, []);

  const ready =
    kind === "mandi_price" ? commodity.trim().length > 1 : kind === "pincode" ? /^\d{6}$/.test(pincode.trim()) : /^[A-Za-z]{4}0[A-Za-z0-9]{6}$/.test(ifsc.trim());

  const run = useCallback(async () => {
    if (!ready || loading) return;
    const q = new URLSearchParams({ dataset: kind, lang: backendLang });
    if (kind === "mandi_price") {
      q.set("commodity", commodity.trim());
      if (market.trim()) q.set("market", market.trim());
      if (state.trim()) q.set("state", state.trim());
    } else if (kind === "pincode") {
      q.set("pincode", pincode.trim());
    } else {
      q.set("ifsc", ifsc.trim().toUpperCase());
    }

    setLoading(true);
    setOffline(false);
    setResult(null);
    try {
      const res = await fetch(`${API_BASE}/api/market?${q.toString()}`);
      if (!res.ok) throw new Error("bad response");
      const body: Result = await res.json();
      setResult(body);
      track("market_view", { dataset: kind });
      try {
        localStorage.setItem(
          STORE_KEY,
          JSON.stringify({ kind, commodity, market, state, pincode, ifsc })
        );
      } catch {
        /* storage is optional */
      }
    } catch {
      setOffline(true);
    } finally {
      setLoading(false);
    }
  }, [ready, loading, kind, backendLang, commodity, market, state, pincode, ifsc]);

  const fieldStyle = {
    display: "flex",
    alignItems: "center",
    gap: "6px",
    flex: 1,
    minWidth: "150px",
    background: "var(--bg-surface)",
    border: "1px solid var(--border)",
    borderRadius: "10px",
    padding: "7px 10px",
  } as const;

  const inputStyle = {
    width: "100%",
    background: "transparent",
    border: "none",
    outline: "none",
    color: "var(--text-primary)",
    fontSize: "0.88rem",
    fontFamily: "inherit",
  } as const;

  function renderRecords() {
    if (!result || !result.records.length) return null;
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: "8px", marginTop: "12px" }}>
        {result.records.slice(0, 8).map((row, i) => (
          <div
            key={i}
            style={{
              background: "var(--bg-surface)",
              border: "1px solid var(--border)",
              borderRadius: "12px",
              padding: "10px 12px",
            }}
          >
            {kind === "mandi_price" && (
              <>
                <div style={{ display: "flex", justifyContent: "space-between", gap: "10px", flexWrap: "wrap" }}>
                  <span style={{ fontSize: "0.86rem", fontWeight: 700, color: "var(--text-primary)" }}>
                    {txt(row.commodity)}
                    {row.variety ? ` · ${txt(row.variety)}` : ""}
                  </span>
                  <span style={{ fontSize: "0.9rem", fontWeight: 800, color: "var(--success)" }}>
                    {inr(row.modal_price)}
                    <span style={{ fontSize: "0.68rem", color: "var(--text-muted)", fontWeight: 600 }}>
                      {" "}
                      {t("market.modal")}
                    </span>
                  </span>
                </div>
                <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "3px" }}>
                  {[row.market, row.district, row.state].map(txt).filter(Boolean).join(" · ")}
                </div>
                <div style={{ fontSize: "0.72rem", color: "var(--text-secondary)", marginTop: "3px" }}>
                  {t("market.range", { min: inr(row.min_price), max: inr(row.max_price) })}
                  {row.date ? ` · ${txt(row.date)}` : ""}
                </div>
              </>
            )}

            {kind === "pincode" && (
              <>
                <div style={{ fontSize: "0.86rem", fontWeight: 700, color: "var(--text-primary)" }}>
                  {txt(row.office)} <span style={{ color: "var(--text-muted)", fontWeight: 600 }}>· {txt(row.pincode)}</span>
                </div>
                <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "3px" }}>
                  {[row.taluk, row.district, row.state].map(txt).filter(Boolean).join(" · ")}
                </div>
                {row.delivery ? (
                  <div style={{ fontSize: "0.72rem", color: "var(--text-secondary)", marginTop: "3px" }}>
                    {t("market.delivery")}: {txt(row.delivery)}
                  </div>
                ) : null}
              </>
            )}

            {kind === "ifsc" && (
              <>
                <div style={{ fontSize: "0.86rem", fontWeight: 700, color: "var(--text-primary)" }}>
                  {txt(row.bank)} <span style={{ color: "var(--text-muted)", fontWeight: 600 }}>· {txt(row.ifsc)}</span>
                </div>
                <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "3px" }}>
                  {txt(row.branch)}
                </div>
                <div style={{ fontSize: "0.72rem", color: "var(--text-secondary)", marginTop: "3px" }}>
                  {[row.city, row.state].map(txt).filter(Boolean).join(" · ")}
                  {row.micr ? ` · MICR ${txt(row.micr)}` : ""}
                </div>
              </>
            )}
          </div>
        ))}
      </div>
    );
  }

  const badge = (() => {
    if (!result) return null;
    if (result.stale) return { text: t("market.badge.stale"), color: "var(--warn)" };
    if (!result.available) return { text: t("market.badge.off"), color: "var(--text-muted)" };
    if (result.lag_days === null) return { text: t("market.badge.undated"), color: "var(--accent2)" };
    return { text: t("market.badge.live"), color: "var(--success)" };
  })();

  return (
    <motion.section
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      aria-labelledby="market-title"
      style={{
        marginTop: "16px",
        width: "100%",
        maxWidth: "760px",
        padding: "20px clamp(16px, 5vw, 24px)",
        background: "rgba(52,211,153,0.05)",
        border: "1px solid rgba(52,211,153,0.22)",
        borderRadius: "var(--radius-xl)",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
        <div
          aria-hidden="true"
          style={{
            width: "34px",
            height: "34px",
            borderRadius: "10px",
            background: "linear-gradient(135deg, var(--success), var(--accent))",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            flexShrink: 0,
          }}
        >
          <Sprout size={16} color="#fff" />
        </div>
        <div style={{ minWidth: 0 }}>
          <p id="market-title" style={{ fontSize: "0.9rem", fontWeight: 700, color: "var(--text-primary)" }}>
            {t("market.title")}
          </p>
          <p style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>{t("market.sub")}</p>
        </div>
      </div>

      {/* What are we checking? */}
      <div role="group" aria-label={t("market.title")} style={{ display: "flex", gap: "8px", flexWrap: "wrap", marginTop: "14px" }}>
        {KINDS.map((k) => {
          const active = kind === k.id;
          return (
            <button
              key={k.id}
              type="button"
              onClick={() => {
                setKind(k.id);
                setResult(null);
                setOffline(false);
              }}
              aria-pressed={active}
              style={{
                cursor: "pointer",
                fontSize: "0.76rem",
                fontWeight: 700,
                fontFamily: "inherit",
                padding: "6px 12px",
                borderRadius: "999px",
                border: `1px solid ${active ? "var(--success)" : "var(--border)"}`,
                background: active ? "rgba(52,211,153,0.12)" : "transparent",
                color: active ? "var(--success)" : "var(--text-secondary)",
              }}
            >
              {t(k.key)}
            </button>
          );
        })}
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          void run();
        }}
        style={{ marginTop: "12px" }}
      >
        <div style={{ display: "flex", flexWrap: "wrap", gap: "10px" }}>
          {kind === "mandi_price" && (
            <>
              <label style={fieldStyle}>
                <Sprout size={13} color="var(--success)" style={{ flexShrink: 0 }} />
                <input
                  value={commodity}
                  onChange={(e) => setCommodity(e.target.value)}
                  placeholder={t("market.ph.commodity")}
                  aria-label={t("market.ph.commodity")}
                  maxLength={60}
                  style={inputStyle}
                />
              </label>
              <label style={fieldStyle}>
                <MapPin size={13} color="var(--text-muted)" style={{ flexShrink: 0 }} />
                <input
                  value={market}
                  onChange={(e) => setMarket(e.target.value)}
                  placeholder={t("market.ph.market")}
                  aria-label={t("market.ph.market")}
                  maxLength={60}
                  style={inputStyle}
                />
              </label>
              <label style={fieldStyle}>
                <MapPin size={13} color="var(--text-muted)" style={{ flexShrink: 0 }} />
                <input
                  value={state}
                  onChange={(e) => setState(e.target.value)}
                  placeholder={t("market.ph.state")}
                  aria-label={t("market.ph.state")}
                  maxLength={60}
                  style={inputStyle}
                />
              </label>
            </>
          )}

          {kind === "pincode" && (
            <label style={fieldStyle}>
              <MapPin size={13} color="var(--success)" style={{ flexShrink: 0 }} />
              <input
                value={pincode}
                onChange={(e) => setPincode(e.target.value.replace(/\D/g, "").slice(0, 6))}
                inputMode="numeric"
                placeholder={t("market.ph.pincode")}
                aria-label={t("market.ph.pincode")}
                maxLength={6}
                style={inputStyle}
              />
            </label>
          )}

          {kind === "ifsc" && (
            <label style={fieldStyle}>
              <Landmark size={13} color="var(--success)" style={{ flexShrink: 0 }} />
              <input
                value={ifsc}
                onChange={(e) => setIfsc(e.target.value.toUpperCase().slice(0, 11))}
                placeholder={t("market.ph.ifsc")}
                aria-label={t("market.ph.ifsc")}
                maxLength={11}
                style={inputStyle}
              />
            </label>
          )}

          <button
            type="submit"
            disabled={!ready || loading}
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "6px",
              cursor: ready && !loading ? "pointer" : "not-allowed",
              opacity: ready && !loading ? 1 : 0.55,
              fontSize: "0.8rem",
              fontWeight: 700,
              fontFamily: "inherit",
              padding: "8px 16px",
              borderRadius: "10px",
              border: "1px solid var(--success)",
              background: "rgba(52,211,153,0.14)",
              color: "var(--success)",
            }}
          >
            {loading ? <Loader2 size={14} className="animate-spin" /> : <Search size={14} />}
            {t("market.check")}
          </button>
        </div>

        {/* Quick chips — a street vendor types two words, not a sentence */}
        {kind === "mandi_price" && (
          <div style={{ display: "flex", gap: "6px", flexWrap: "wrap", marginTop: "10px" }}>
            {CROPS.map((c) => (
              <button
                key={c.id}
                type="button"
                onClick={() => setCommodity(c.id)}
                style={{
                  cursor: "pointer",
                  fontSize: "0.72rem",
                  fontWeight: 600,
                  fontFamily: "inherit",
                  padding: "4px 10px",
                  borderRadius: "999px",
                  border: "1px solid var(--border)",
                  background: "transparent",
                  color: "var(--text-secondary)",
                }}
              >
                {t(c.key)}
              </button>
            ))}
          </div>
        )}
      </form>

      {/* Result — announced politely so a screen reader hears the date too */}
      <div aria-live="polite" style={{ marginTop: result || offline ? "12px" : 0 }}>
        {offline && (
          <p style={{ display: "flex", alignItems: "center", gap: "8px", fontSize: "0.8rem", color: "var(--error)" }}>
            <AlertCircle size={14} style={{ flexShrink: 0 }} />
            {t("market.offline")}
          </p>
        )}

        {result && (
          <>
            <div style={{ display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap" }}>
              <span
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "5px",
                  fontSize: "0.7rem",
                  fontWeight: 800,
                  letterSpacing: "0.02em",
                  textTransform: "uppercase",
                  color: badge?.color,
                  border: `1px solid ${badge?.color}`,
                  borderRadius: "999px",
                  padding: "3px 10px",
                }}
              >
                <Clock size={11} />
                {badge?.text}
              </span>
              <span style={{ fontSize: "0.78rem", color: "var(--text-secondary)" }}>{result.note}</span>
            </div>

            {!result.available && result.error && (
              <p style={{ marginTop: "8px", fontSize: "0.8rem", color: "var(--text-secondary)" }}>{result.error}</p>
            )}

            {renderRecords()}

            {result.count > 8 && (
              <p style={{ marginTop: "6px", fontSize: "0.72rem", color: "var(--text-muted)" }}>
                {t("market.more", { n: result.count - 8 })}
              </p>
            )}

            <div style={{ display: "flex", gap: "14px", flexWrap: "wrap", marginTop: "10px" }}>
              {result.official_url && (
                <a
                  href={result.official_url}
                  target="_blank"
                  rel="noreferrer noopener"
                  style={{ display: "inline-flex", alignItems: "center", gap: "5px", fontSize: "0.74rem", color: "var(--accent)", textDecoration: "none" }}
                >
                  <ExternalLink size={12} />
                  {t("market.official")}
                </a>
              )}
              {result.source_url && (
                <a
                  href={result.source_url}
                  target="_blank"
                  rel="noreferrer noopener"
                  style={{ display: "inline-flex", alignItems: "center", gap: "5px", fontSize: "0.74rem", color: "var(--text-muted)", textDecoration: "none" }}
                >
                  <ExternalLink size={12} />
                  {result.source_name || t("market.source")}
                </a>
              )}
            </div>

            {result.disclaimer && (
              <p style={{ marginTop: "8px", fontSize: "0.68rem", color: "var(--text-muted)", lineHeight: 1.5 }}>
                {result.disclaimer}
              </p>
            )}
          </>
        )}
      </div>
    </motion.section>
  );
}
