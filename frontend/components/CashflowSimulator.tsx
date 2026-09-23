"use client";
import { useMemo, useState } from "react";
import { motion } from "framer-motion";
import { AlertCircle, CalendarClock, PiggyBank, TrendingUp, Wallet } from "lucide-react";

const inr = (n: number) => "₹" + Math.round(n).toLocaleString("en-IN");

function NumField({
  label,
  value,
  onChange,
  step,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
  step?: number;
}) {
  return (
    <label style={{ display: "flex", flexDirection: "column", gap: "4px", flex: 1, minWidth: "140px" }}>
      <span style={{ fontSize: "0.72rem", color: "var(--text-muted)", fontWeight: 600 }}>{label}</span>
      <div style={{ display: "flex", alignItems: "center", gap: "6px", background: "var(--bg-surface)", border: "1px solid var(--border)", borderRadius: "10px", padding: "6px 10px" }}>
        <Wallet size={13} color="var(--accent)" style={{ flexShrink: 0 }} />
        <input
          type="number"
          min={0}
          step={step ?? 1000}
          value={Number.isFinite(value) ? value : ""}
          onChange={(e) => onChange(Number(e.target.value) || 0)}
          aria-label={label}
          style={{
            width: "100%", background: "transparent", border: "none", outline: "none",
            color: "var(--text-primary)", fontSize: "0.9rem", fontWeight: 700, fontFamily: "inherit",
          }}
        />
      </div>
    </label>
  );
}

export default function CashflowSimulator() {
  const [capital, setCapital] = useState(50000);
  const [sales, setSales] = useState(15000);
  const [expenses, setExpenses] = useState(10000);
  const [weeks, setWeeks] = useState(12);

  const { balances, net, min, max, breakEven } = useMemo(() => {
    const net = sales - expenses;
    const balances: number[] = [capital];
    for (let i = 1; i <= weeks; i++) balances.push(balances[i - 1] + net);
    let breakEven = -1;
    if (net > 0) {
      for (let i = 1; i <= weeks; i++) {
        if (balances[i] >= capital) {
          breakEven = i;
          break;
        }
      }
    }
    return {
      balances,
      net,
      min: Math.min(...balances, 0, capital),
      max: Math.max(...balances, capital),
      breakEven,
    };
  }, [capital, sales, expenses, weeks]);

  const monthlySurplus = net * 4.33;
  const W = 440;
  const H = 180;
  const pad = 16;
  const x = (i: number) => pad + (i / weeks) * (W - 2 * pad);
  const y = (v: number) =>
    H - pad - ((v - min) / ((max - min) || 1)) * (H - 2 * pad);
  const linePoints = balances.map((b, i) => `${x(i).toFixed(1)},${y(b).toFixed(1)}`).join(" ");
  const baseline = y(capital);
  const areaPath = `M ${x(0)} ${y(balances[0])} L ${linePoints.replace(/ /g, " L ")} L ${x(weeks)} ${H - pad} L ${x(0)} ${H - pad} Z`;

  const ranges = Math.max(1, Math.round(weeks * 0.14));
  const xTicks = Array.from(new Set([0, ...Array.from({ length: ranges + 1 }, (_, i) => Math.round((i / (ranges || 1)) * weeks))])).slice(0, 7);

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      style={{
        marginTop: "16px", width: "100%", maxWidth: "760px",
        padding: "20px 24px",
        background: "rgba(139,92,246,0.05)",
        border: "1px solid rgba(139,92,246,0.22)",
        borderRadius: "var(--radius-xl)",
      }}
    >
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "4px" }}>
        <div style={{ width: "34px", height: "34px", borderRadius: "10px", background: "linear-gradient(135deg, var(--accent2), var(--accent))", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
          <TrendingUp size={16} color="#fff" />
        </div>
        <div>
          <p style={{ fontSize: "0.9rem", fontWeight: 700, color: "var(--text-primary)" }}>Cash-Flow Simulator</p>
          <p style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>
            Guess your numbers — see if the business survives and when it breaks even. No internet needed.
          </p>
        </div>
      </div>

      {/* Inputs */}
      <div style={{ display: "flex", flexWrap: "wrap", gap: "12px", margin: "14px 0 6px" }}>
        <NumField label="Starting capital (₹)" value={capital} onChange={setCapital} />
        <NumField label="Weekly sales (₹)" value={sales} onChange={setSales} />
        <NumField label="Weekly expenses (₹)" value={expenses} onChange={setExpenses} />
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: "10px", marginTop: "10px" }}>
        <CalendarClock size={13} color="var(--text-muted)" style={{ flexShrink: 0 }} />
        <input
          type="range" min={4} max={24} value={weeks}
          onChange={(e) => setWeeks(Number(e.target.value))}
          aria-label="Weeks to project"
          style={{ flex: 1, accentColor: "var(--accent2)" }}
        />
        <span style={{ fontSize: "0.78rem", color: "var(--text-secondary)", fontWeight: 700, minWidth: "34px", textAlign: "right" }}>
          {weeks} wk
        </span>
      </div>

      {/* Chart */}
      <div style={{ marginTop: "12px", background: "var(--bg-surface)", border: "1px solid var(--border)", borderRadius: "12px", padding: "10px 8px 4px" }}>
        <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: "auto", display: "block" }} role="img" aria-label="Projected cash balance over weeks">
          <defs>
            <linearGradient id="cfFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="rgba(139,92,246,0.35)" />
              <stop offset="100%" stopColor="rgba(139,92,246,0)" />
            </linearGradient>
          </defs>
          <path d={areaPath} fill="url(#cfFill)" />
          <line x1={x(0)} y1={baseline} x2={x(weeks)} y2={baseline} stroke="rgba(232,237,245,0.25)" strokeWidth="1" strokeDasharray="4 4" />
          <polyline points={linePoints} fill="none" stroke="var(--accent2)" strokeWidth="2.5" strokeLinejoin="round" strokeLinecap="round" />
          {breakEven > 0 && (
            <>
              <circle cx={x(breakEven)} cy={baseline} r="4.5" fill="var(--success)" stroke="var(--bg-surface)" strokeWidth="1.5" />
              <text x={x(breakEven)} y={baseline - 10} textAnchor="middle" fontSize="9" fontWeight="700" fill="var(--success)">
                break-even wk {breakEven}
              </text>
            </>
          )}
          {xTicks.map((t) => (
            <text key={t} x={x(t)} y={H - 2} textAnchor="middle" fontSize="8" fill="var(--text-muted)">
              wk {t}
            </text>
          ))}
          <text x="6" y={y(max)} fontSize="8" fill="var(--text-muted)">{inr(max)}</text>
          <text x="6" y={y(min) + 10} fontSize="8" fill="var(--text-muted)">{inr(min)}</text>
        </svg>
      </div>

      {/* Stats */}
      <div style={{ display: "flex", flexWrap: "wrap", gap: "10px", marginTop: "12px" }}>
        <div style={{ flex: 1, minWidth: "130px", background: "rgba(45,212,191,0.08)", border: "1px solid rgba(45,212,191,0.25)", borderRadius: "10px", padding: "10px 12px" }}>
          <p style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Monthly surplus</p>
          <p style={{ fontSize: "1rem", fontWeight: 700, color: monthlySurplus >= 0 ? "var(--success)" : "var(--error)" }}>
            {monthlySurplus >= 0 ? "+" : ""}{inr(monthlySurplus)}
          </p>
        </div>
        <div style={{ flex: 1, minWidth: "130px", background: "rgba(251,146,60,0.06)", border: "1px solid rgba(251,146,60,0.2)", borderRadius: "10px", padding: "10px 12px" }}>
          <p style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Break-even</p>
          <p style={{ fontSize: "1rem", fontWeight: 700, color: "var(--text-primary)" }}>
            {breakEven > 0 ? `Week ${breakEven}` : monthlySurplus < 0 ? "Not happening" : "Immediate"}
          </p>
        </div>
        <div style={{ flex: 1, minWidth: "130px", background: "rgba(79,142,247,0.06)", border: "1px solid rgba(79,142,247,0.2)", borderRadius: "10px", padding: "10px 12px" }}>
          <p style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Balance after {weeks} weeks</p>
          <p style={{ fontSize: "1rem", fontWeight: 700, color: "var(--text-primary)" }}>{inr(balances[balances.length - 1])}</p>
        </div>
      </div>

      {monthlySurplus < 0 && (
        <div style={{ display: "flex", alignItems: "center", gap: "8px", marginTop: "12px", padding: "10px 12px", background: "rgba(248,113,113,0.08)", border: "1px solid rgba(248,113,113,0.25)", borderRadius: "10px" }}>
          <AlertCircle size={14} color="var(--error)" style={{ flexShrink: 0 }} />
          <span style={{ fontSize: "0.76rem", color: "var(--error)" }}>
            Expenses are above sales — cash is draining every week. Cut costs or grow sales before applying for a loan.
          </span>
        </div>
      )}

      <div style={{ display: "flex", alignItems: "center", gap: "6px", marginTop: "10px" }}>
        <PiggyBank size={13} color="var(--text-muted)" />
        <span style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>
          Bankers like a consistent positive surplus — it proves the loan can be repaid.
        </span>
      </div>
    </motion.div>
  );
}