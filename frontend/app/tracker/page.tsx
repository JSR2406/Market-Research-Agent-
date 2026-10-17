"use client";

/**
 * /tracker — the application tracker and deadline calendar (WS-6).
 *
 * Discovery ends when the user picks a scheme; this page answers the next
 * question, "did you actually apply". Every card moves through the same five
 * stages the backend stores, and every deadline shown here is either a window
 * the scheme's own documents publish (with its source link) or a date the user
 * set themselves.
 *
 * Two sources of truth on purpose:
 *  - the server (`/api/tracker/{session_id}`) computes the board, the 14-day
 *    "closing soon" flag and the alert text in code, so it can never disagree
 *    with the API;
 *  - localStorage mirrors the list so the page still works with the backend
 *    cold or offline, and a visitor without a session id still sees their work.
 */
import { useCallback, useEffect, useMemo, useState, type CSSProperties } from "react";
import Link from "next/link";
import { AnimatePresence, motion } from "framer-motion";
import {
  AlertTriangle,
  Bell,
  CalendarClock,
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  ListChecks,
  Loader2,
  Plus,
  Trash2,
  XCircle,
} from "lucide-react";
import { SiteHeader } from "@/components/SiteHeader";
import { API_BASE } from "@/lib/api";
import { track } from "@/lib/analytics";
import { useI18n } from "@/lib/i18n";
import { useSession } from "@/lib/useSession";

/** The stages a card moves through. `rejected` is terminal and set explicitly. */
const FLOW = ["planning", "docs_ready", "submitted", "approved"] as const;
const REJECTED = "rejected";
const LOCAL_KEY = "grameenai_tracker";
const ALL_EVENTS = ["deadline_soon", "new_match", "reverified"];

type Application = {
  scheme_id: string;
  scheme_name: string;
  status: string;
  target_date: string;
  notes: string;
  tier_group?: string;
};

type BoardRow = {
  source: string;
  scheme_id: string;
  scheme_name: string;
  kind: string;
  date: string;
  title: string;
  note: string;
  source_url: string;
  last_verified_at: string;
  state: string;
  days_left: number | null;
};

type Board = { rows: BoardRow[]; closing_soon: BoardRow[]; today: string; disclaimer: string };
type AlertPreview = { messages: { event: string; message: string }[]; summary: string };
type AlertSettings = { channel: string; value: string; events: string[]; consent: boolean };
type SchemeOption = { id: string; name: string; family: string; status?: string };

const EMPTY_ALERT: AlertSettings = { channel: "", value: "", events: ALL_EVENTS, consent: false };

const STATE_COLOR: Record<string, string> = {
  closing_soon: "var(--warn)",
  open: "var(--success)",
  lapsed: "var(--text-muted)",
  lapsed_pending: "var(--accent2)",
  rolling: "var(--text-muted)",
};

export default function TrackerPage() {
  const { t, locale } = useI18n();
  const { intake, ready, ensureSessionId } = useSession();

  const [apps, setApps] = useState<Application[]>([]);
  const [alertCfg, setAlertCfg] = useState<AlertSettings>(EMPTY_ALERT);
  const [board, setBoard] = useState<Board | null>(null);
  const [preview, setPreview] = useState<AlertPreview | null>(null);
  const [options, setOptions] = useState<SchemeOption[]>([]);
  const [pick, setPick] = useState("");
  const [busy, setBusy] = useState(false);
  const [offline, setOffline] = useState(false);
  const [alertError, setAlertError] = useState("");

  /** Persist locally always, then to the server when it answers. */
  const persist = useCallback(
    async (nextApps: Application[], nextAlert: AlertSettings, saveAlert: boolean) => {
      try {
        window.localStorage.setItem(LOCAL_KEY, JSON.stringify({ applications: nextApps, alert: nextAlert }));
      } catch {
        /* private mode — the page still works for this visit */
      }
      const sessionId = ensureSessionId();
      const body: Record<string, unknown> = {
        applications: nextApps.map((a) => ({
          scheme_id: a.scheme_id,
          status: a.status,
          target_date: a.target_date || "",
          notes: a.notes || "",
        })),
        intake,
        topic: "",
        lang: locale,
      };
      if (saveAlert && nextAlert.channel) {
        body.alert = {
          channel: nextAlert.channel,
          value: nextAlert.value,
          events: nextAlert.events,
          consent: nextAlert.consent,
        };
      }
      setBusy(true);
      setAlertError("");
      try {
        const res = await fetch(`${API_BASE}/api/tracker/${sessionId}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        if (res.status === 422) {
          const detail = await res.json().catch(() => ({}));
          setAlertError(typeof detail?.detail === "string" ? detail.detail : t("tracker.invalidContact"));
          setBusy(false);
          return false;
        }
        if (!res.ok) throw new Error("save failed");
        const data = await res.json();
        setApps(data.applications ?? nextApps);
        setBoard(data.board ?? null);
        setPreview(data.alerts ?? null);
        setOffline(false);
        setBusy(false);
        return true;
      } catch {
        setOffline(true);
        setBusy(false);
        return false;
      }
    },
    [ensureSessionId, intake, locale, t]
  );

  // Restore the local mirror, then let the server win when it has something.
  useEffect(() => {
    if (!ready) return;
    let localApps: Application[] = [];
    let localAlert = EMPTY_ALERT;
    try {
      const raw = window.localStorage.getItem(LOCAL_KEY);
      if (raw) {
        const parsed = JSON.parse(raw);
        if (Array.isArray(parsed?.applications)) localApps = parsed.applications;
        if (parsed?.alert) localAlert = { ...EMPTY_ALERT, ...parsed.alert };
      }
    } catch {
      /* corrupt mirror — start clean */
    }
    setApps(localApps);
    setAlertCfg(localAlert);

    const sessionId = ensureSessionId();
    (async () => {
      try {
        const res = await fetch(`${API_BASE}/api/tracker/${sessionId}?lang=${locale}`);
        if (!res.ok) throw new Error("load failed");
        const data = await res.json();
        const stored: Application[] = data.applications ?? [];
        if (!stored.length && localApps.length) {
          // First visit after a local-only session: push the mirror up so the
          // board, the alerts and the 14-day flags exist.
          await persist(localApps, localAlert, Boolean(localAlert.channel));
          return;
        }
        setApps(stored);
        if (data.alert?.channel) {
          setAlertCfg({
            channel: data.alert.channel,
            value: data.alert.value ?? "",
            events: data.alert.events ?? ALL_EVENTS,
            consent: Boolean(data.alert.consent),
          });
        }
        setBoard(data.board ?? null);
        setPreview(data.alerts ?? null);
        setOffline(false);
      } catch {
        setOffline(true);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, locale]);

  // The scheme picker: every curated scheme, with the ones this business
  // matches hoisted to the top and labelled by the rule engine.
  useEffect(() => {
    if (!ready) return;
    const controller = new AbortController();
    (async () => {
      try {
        const res = await fetch(`${API_BASE}/api/schemes`, { signal: controller.signal });
        if (!res.ok) return;
        const data = await res.json();
        const byFamily = new Map<string, SchemeOption>();
        for (const record of data.schemes ?? []) {
          const family = record.tier_group || record.id;
          if (family && !byFamily.has(family)) {
            byFamily.set(family, { id: record.id, name: record.scheme_name, family });
          }
        }
        if (Object.keys(intake).length) {
          try {
            const er = await fetch(`${API_BASE}/api/eligibility`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ intake, lang: locale }),
              signal: controller.signal,
            });
            if (er.ok) {
              const ed = await er.json();
              // `ranked` holds the open (eligible/likely) schemes, best first;
              // it also names the right tier of a tiered programme.
              for (const verdict of ed.ranked ?? []) {
                const family = verdict.tier_group || verdict.scheme_id;
                byFamily.set(family, {
                  id: verdict.scheme_id,
                  name: verdict.name,
                  family,
                  status: verdict.status_label,
                });
              }
            }
          } catch {
            /* no matches to hoist — the full list still works */
          }
        }
        setOptions(
          [...byFamily.values()].sort(
            (a, b) => Number(Boolean(b.status)) - Number(Boolean(a.status)) || a.name.localeCompare(b.name)
          )
        );
      } catch {
        /* picker stays empty; the rest of the page still works */
      }
    })();
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, locale, JSON.stringify(intake)]);

  const matched = useMemo(() => options.filter((o) => o.status), [options]);
  const trackedFamilies = useMemo(
    () => new Set(apps.map((a) => a.tier_group || a.scheme_id)),
    [apps]
  );

  const addScheme = useCallback(
    (option: SchemeOption) => {
      if (trackedFamilies.has(option.family)) return;
      const next: Application[] = [
        ...apps,
        {
          scheme_id: option.id,
          scheme_name: option.name,
          status: "planning",
          target_date: "",
          notes: "",
          tier_group: option.family,
        },
      ];
      setApps(next);
      track("tracker_scheme_added", { scheme: option.id });
      void persist(next, alertCfg, false);
    },
    [apps, alertCfg, persist, trackedFamilies]
  );

  const update = useCallback(
    (schemeId: string, patch: Partial<Application>, save = true) => {
      const next = apps.map((a) => (a.scheme_id === schemeId ? { ...a, ...patch } : a));
      setApps(next);
      if (save) void persist(next, alertCfg, false);
    },
    [apps, alertCfg, persist]
  );

  const remove = useCallback(
    (schemeId: string) => {
      const next = apps.filter((a) => a.scheme_id !== schemeId);
      setApps(next);
      void persist(next, alertCfg, false);
    },
    [apps, alertCfg, persist]
  );

  const move = useCallback(
    (app: Application, direction: 1 | -1) => {
      if (app.status === REJECTED) {
        update(app.scheme_id, { status: "submitted" });
        return;
      }
      const index = FLOW.indexOf(app.status as (typeof FLOW)[number]);
      if (index < 0) return;
      const next = FLOW[Math.min(Math.max(index + direction, 0), FLOW.length - 1)];
      if (next !== app.status) update(app.scheme_id, { status: next });
    },
    [update]
  );

  const saveAlerts = useCallback(async () => {
    if (!alertCfg.channel) {
      // "Not now" clears any stored subscription.
      await persist(apps, { ...alertCfg, value: "", consent: false }, true);
      return;
    }
    const value = alertCfg.value.trim();
    if (!value) {
      setAlertError(t("tracker.needContact"));
      return;
    }
    if (alertCfg.channel === "whatsapp" && !/^\d{10,15}$/.test(value)) {
      setAlertError(t("tracker.invalidContact"));
      return;
    }
    if (alertCfg.channel === "email" && (!value.includes("@") || value.length > 200 || /\s/.test(value))) {
      setAlertError(t("tracker.invalidContact"));
      return;
    }
    if (!alertCfg.consent) {
      setAlertError(t("tracker.needConsent"));
      return;
    }
    setAlertError("");
    const ok = await persist(apps, alertCfg, true);
    if (ok) track("tracker_alerts_saved", { channel: alertCfg.channel });
  }, [alertCfg, apps, persist, t]);

  const rows = board?.rows ?? [];
  const dated = rows.filter((row) => row.state !== "rolling");
  const rolling = rows.filter((row) => row.state === "rolling");
  const matchedToAdd = matched.filter((o) => !trackedFamilies.has(o.family));

  return (
    <>
      <SiteHeader />
      <main style={{ maxWidth: "calc(var(--content-max) + 240px)", marginInline: "auto", padding: "0 clamp(12px, 4vw, 20px) 60px" }}>
        <div style={{ padding: "28px 0 8px" }}>
          <h1 style={{ fontSize: "clamp(1.4rem, 3.2vw, 1.9rem)", fontWeight: 800, letterSpacing: "-0.02em", marginBottom: "8px", display: "flex", alignItems: "center", gap: "10px" }}>
            <ListChecks size={24} color="var(--accent)" aria-hidden="true" />
            {t("tracker.title")}
          </h1>
          <p style={{ color: "var(--text-secondary)", maxWidth: "660px", lineHeight: 1.6 }}>{t("tracker.subtitle")}</p>
        </div>

        {/* ── add a scheme ─────────────────────────────────────────────── */}
        <section
          aria-label={t("tracker.addTitle")}
          style={{ ...cardStyle, marginTop: "18px", display: "flex", flexWrap: "wrap", alignItems: "flex-end", gap: "12px" }}
        >
          <div style={{ flex: "1 1 260px", minWidth: 0 }}>
            <label htmlFor="tracker-pick" style={labelStyle}>
              {t("tracker.addTitle")}
            </label>
            <select id="tracker-pick" value={pick} onChange={(e) => setPick(e.target.value)} style={inputStyle}>
              <option value="">{t("tracker.choose")}</option>
              {matched.length > 0 && (
                <optgroup label={t("tracker.matchedHint")}>
                  {matched.map((option) => (
                    <option key={option.id} value={option.family}>
                      {option.name} — {option.status}
                    </option>
                  ))}
                </optgroup>
              )}
              <optgroup label={t("tracker.title")}>
                {options
                  .filter((o) => !o.status)
                  .map((option) => (
                    <option key={option.id} value={option.family}>
                      {option.name}
                    </option>
                  ))}
              </optgroup>
            </select>
          </div>
          <button
            type="button"
            onClick={() => {
              const option = options.find((o) => o.family === pick);
              if (option) addScheme(option);
              setPick("");
            }}
            disabled={!pick || busy}
            style={{ ...ctaStyle, border: "none", opacity: !pick || busy ? 0.6 : 1, cursor: !pick || busy ? "default" : "pointer" }}
          >
            <Plus size={15} aria-hidden="true" />
            {t("tracker.add")}
          </button>
          {matchedToAdd.length > 0 && (
            <button
              type="button"
              onClick={() => {
                const next = [...apps];
                for (const option of matchedToAdd) {
                  next.push({
                    scheme_id: option.id,
                    scheme_name: option.name,
                    status: "planning",
                    target_date: "",
                    notes: "",
                    tier_group: option.family,
                  });
                }
                setApps(next);
                void persist(next, alertCfg, false);
              }}
              style={{ ...ghostStyle, cursor: "pointer" }}
            >
              {t("tracker.addAll")}
            </button>
          )}
        </section>

        {busy && (
          <p style={{ marginTop: "10px", display: "flex", alignItems: "center", gap: "7px", fontSize: "0.78rem", color: "var(--text-muted)" }}>
            <Loader2 size={13} className="spin" aria-hidden="true" />
            {t("tracker.saving")}
          </p>
        )}
        {offline && (
          <p style={{ marginTop: "10px", display: "flex", alignItems: "center", gap: "7px", fontSize: "0.78rem", color: "var(--warn)" }}>
            <AlertTriangle size={14} aria-hidden="true" />
            {t("tracker.saveFailed")}
          </p>
        )}

        {/* ── the board ────────────────────────────────────────────────── */}
        <section style={{ marginTop: "26px" }}>
          <h2 style={h2Style}>
            <ListChecks size={17} aria-hidden="true" />
            {t("tracker.tracking")}
          </h2>

          {apps.length === 0 ? (
            <p style={{ ...cardStyle, color: "var(--text-secondary)", fontSize: "0.86rem", lineHeight: 1.6 }}>
              {t("tracker.empty")}
            </p>
          ) : (
            <>
              <p style={{ fontSize: "0.74rem", color: "var(--text-muted)", marginBottom: "8px" }}>{t("tracker.stageHint")}</p>
              <div style={{ display: "grid", gap: "12px", gridTemplateColumns: "repeat(auto-fit, minmax(232px, 1fr))" }}>
                {[...FLOW, REJECTED].map((stage) => {
                  const stageApps = apps.filter((a) => a.status === stage);
                  return (
                    <div key={stage} style={{ display: "grid", gap: "8px", alignContent: "start" }}>
                      <h3 style={{ fontSize: "0.76rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--text-muted)" }}>
                        {t(`tracker.stage.${stage}`)} · {stageApps.length}
                      </h3>
                      <AnimatePresence initial={false}>
                        {stageApps.map((app) => (
                          <motion.article
                            key={app.scheme_id}
                            layout
                            initial={{ opacity: 0, y: 6 }}
                            animate={{ opacity: 1, y: 0 }}
                            exit={{ opacity: 0, scale: 0.97 }}
                            transition={{ duration: 0.22 }}
                            style={{ ...cardStyle, padding: "12px", display: "grid", gap: "8px" }}
                          >
                            <p style={{ fontSize: "0.84rem", fontWeight: 650, lineHeight: 1.35, wordBreak: "break-word" }}>{app.scheme_name}</p>

                            <div style={{ display: "flex", gap: "5px" }}>
                              <IconButton
                                label={t("tracker.movePrevAria", { name: app.scheme_name })}
                                onClick={() => move(app, -1)}
                                disabled={app.status === FLOW[0]}
                              >
                                <ChevronLeft size={15} />
                              </IconButton>
                              <IconButton
                                label={t("tracker.moveNextAria", { name: app.scheme_name })}
                                onClick={() => move(app, 1)}
                                disabled={app.status === "approved"}
                              >
                                <ChevronRight size={15} />
                              </IconButton>
                              <IconButton
                                label={t("tracker.markRejectedAria", { name: app.scheme_name })}
                                onClick={() => update(app.scheme_id, { status: REJECTED })}
                                disabled={app.status === REJECTED}
                              >
                                <XCircle size={15} />
                              </IconButton>
                              <button
                                type="button"
                                aria-label={t("tracker.removeAria", { name: app.scheme_name })}
                                title={t("tracker.remove")}
                                onClick={() => remove(app.scheme_id)}
                                style={{ ...iconButtonStyle, marginLeft: "auto" }}
                              >
                                <Trash2 size={15} />
                              </button>
                            </div>

                            <div>
                              <label htmlFor={`date-${app.scheme_id}`} style={miniLabelStyle}>
                                {t("tracker.target")}
                              </label>
                              <input
                                id={`date-${app.scheme_id}`}
                                type="date"
                                aria-label={t("tracker.targetAria", { name: app.scheme_name })}
                                value={app.target_date || ""}
                                onChange={(e) => update(app.scheme_id, { target_date: e.target.value }, false)}
                                onBlur={() => persist(apps, alertCfg, false)}
                                style={{ ...inputStyle, padding: "6px 8px", fontSize: "0.78rem" }}
                              />
                            </div>

                            <div>
                              <label htmlFor={`notes-${app.scheme_id}`} style={miniLabelStyle}>
                                {t("tracker.notes")}
                              </label>
                              <input
                                id={`notes-${app.scheme_id}`}
                                aria-label={t("tracker.notesAria", { name: app.scheme_name })}
                                value={app.notes || ""}
                                onChange={(e) => update(app.scheme_id, { notes: e.target.value.slice(0, 500) }, false)}
                                onBlur={() => persist(apps, alertCfg, false)}
                                placeholder={t("tracker.notesPlaceholder")}
                                style={{ ...inputStyle, padding: "6px 8px", fontSize: "0.78rem" }}
                              />
                            </div>
                          </motion.article>
                        ))}
                      </AnimatePresence>
                    </div>
                  );
                })}
              </div>
            </>
          )}
        </section>

        {/* ── deadlines ────────────────────────────────────────────────── */}
        <section style={{ marginTop: "30px" }}>
          <h2 style={h2Style}>
            <CalendarClock size={17} aria-hidden="true" />
            {t("tracker.deadlines")}
          </h2>

          {dated.length === 0 && rolling.length === 0 ? (
            <p style={{ ...cardStyle, color: "var(--text-secondary)", fontSize: "0.86rem", lineHeight: 1.6 }}>
              {board ? t("tracker.noDeadlines") : t("tracker.loading")}
            </p>
          ) : (
            <ul style={{ listStyle: "none", display: "grid", gap: "8px" }}>
              {dated.map((row) => (
                <DeadlineRow key={`${row.source}-${row.scheme_id}-${row.date}`} row={row} t={t} />
              ))}
            </ul>
          )}

          {rolling.length > 0 && (
            <details style={{ marginTop: "10px" }}>
              <summary style={{ cursor: "pointer", fontSize: "0.78rem", color: "var(--text-secondary)" }}>
                {t("tracker.state.rolling")} · {rolling.length}
              </summary>
              <ul style={{ listStyle: "none", display: "grid", gap: "8px", marginTop: "8px" }}>
                {rolling.map((row) => (
                  <DeadlineRow key={`rolling-${row.scheme_id}`} row={row} t={t} />
                ))}
              </ul>
            </details>
          )}

          {board?.disclaimer && (
            <p style={{ marginTop: "10px", fontSize: "0.72rem", color: "var(--text-muted)", lineHeight: 1.55 }}>{board.disclaimer}</p>
          )}
        </section>

        {/* ── alerts ───────────────────────────────────────────────────── */}
        <section style={{ marginTop: "30px" }}>
          <h2 style={h2Style}>
            <Bell size={17} aria-hidden="true" />
            {t("tracker.alertsTitle")}
          </h2>
          <div style={{ ...cardStyle, display: "grid", gap: "12px" }}>
            <p style={{ fontSize: "0.82rem", color: "var(--text-secondary)", lineHeight: 1.6 }}>{t("tracker.alertsSubtitle")}</p>

            <div style={{ display: "grid", gap: "10px", gridTemplateColumns: "repeat(auto-fit, minmax(210px, 1fr))" }}>
              <div>
                <label htmlFor="tracker-channel" style={labelStyle}>
                  {t("tracker.channel")}
                </label>
                <select
                  id="tracker-channel"
                  value={alertCfg.channel}
                  onChange={(e) => setAlertCfg((c) => ({ ...c, channel: e.target.value }))}
                  style={inputStyle}
                >
                  <option value="">{t("tracker.channelNone")}</option>
                  <option value="whatsapp">WhatsApp</option>
                  <option value="email">{t("tracker.channelEmail")}</option>
                </select>
              </div>
              {alertCfg.channel && (
                <div>
                  <label htmlFor="tracker-contact" style={labelStyle}>
                    {t("tracker.contact")}
                  </label>
                  <input
                    id="tracker-contact"
                    value={alertCfg.value}
                    onChange={(e) => setAlertCfg((c) => ({ ...c, value: e.target.value }))}
                    placeholder={
                      alertCfg.channel === "whatsapp" ? t("tracker.contactPhoneHint") : t("tracker.contactEmailHint")
                    }
                    inputMode={alertCfg.channel === "whatsapp" ? "numeric" : "email"}
                    style={inputStyle}
                  />
                </div>
              )}
            </div>

            <fieldset style={{ border: "none", display: "grid", gap: "6px" }}>
              <legend style={labelStyle}>{t("tracker.events")}</legend>
              {ALL_EVENTS.map((event) => (
                <label key={event} style={{ display: "flex", alignItems: "center", gap: "8px", fontSize: "0.82rem", color: "var(--text-secondary)" }}>
                  <input
                    type="checkbox"
                    checked={alertCfg.events.includes(event)}
                    onChange={(e) =>
                      setAlertCfg((c) => ({
                        ...c,
                        events: e.target.checked ? [...c.events, event] : c.events.filter((x) => x !== event),
                      }))
                    }
                  />
                  {t(`tracker.event.${event}`)}
                </label>
              ))}
            </fieldset>

            {alertCfg.channel && (
              <label style={{ display: "flex", alignItems: "center", gap: "8px", fontSize: "0.82rem", color: "var(--text-secondary)" }}>
                <input
                  type="checkbox"
                  checked={alertCfg.consent}
                  onChange={(e) => setAlertCfg((c) => ({ ...c, consent: e.target.checked }))}
                />
                {t("tracker.consent")}
              </label>
            )}

            {alertError && (
              <p style={{ display: "flex", alignItems: "center", gap: "7px", fontSize: "0.78rem", color: "var(--warn)" }}>
                <AlertTriangle size={14} aria-hidden="true" />
                {alertError}
              </p>
            )}

            <div>
              <button type="button" onClick={saveAlerts} disabled={busy} style={{ ...ctaStyle, border: "none", opacity: busy ? 0.6 : 1, cursor: busy ? "default" : "pointer" }}>
                <Bell size={15} aria-hidden="true" />
                {busy ? t("tracker.saving") : t("tracker.saveAlerts")}
              </button>
            </div>

            <div style={{ borderTop: "1px solid var(--border)", paddingTop: "12px" }}>
              <p style={{ fontSize: "0.78rem", fontWeight: 700, marginBottom: "6px" }}>{t("tracker.preview")}</p>
              {preview?.messages.length ? (
                <ul style={{ listStyle: "none", display: "grid", gap: "5px" }}>
                  {preview.messages.map((message, index) => (
                    <li key={`${message.event}-${index}`} style={{ fontSize: "0.82rem", color: "var(--text-secondary)", lineHeight: 1.5 }}>
                      • {message.message}
                    </li>
                  ))}
                </ul>
              ) : (
                <p style={{ fontSize: "0.82rem", color: "var(--text-secondary)" }}>{t("tracker.noAlerts")}</p>
              )}
              <p style={{ marginTop: "8px", fontSize: "0.72rem", color: "var(--text-muted)", lineHeight: 1.55 }}>{t("tracker.alertsNote")}</p>
            </div>
          </div>

          <p style={{ marginTop: "12px", fontSize: "0.74rem", color: "var(--text-muted)", lineHeight: 1.6 }}>
            {t("tracker.privacy")}{" "}
            <Link href="/history" style={{ color: "var(--accent)" }}>
              History
            </Link>
          </p>
        </section>
      </main>
    </>
  );
}

function DeadlineRow({ row, t }: { row: BoardRow; t: (key: string, vars?: Record<string, string | number>) => string }) {
  const days = row.days_left;
  const timing =
    days === null
      ? ""
      : days === 0
        ? t("tracker.dueToday")
        : days > 0
          ? t("tracker.daysLeft", { days })
          : t("tracker.overdueBy", { days: Math.abs(days) });
  const color = STATE_COLOR[row.state] ?? "var(--text-muted)";

  return (
    <li style={{ ...cardStyle, padding: "12px 14px", display: "grid", gap: "6px" }}>
      <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: "8px" }}>
        <span
          style={{
            fontSize: "0.68rem",
            fontWeight: 700,
            letterSpacing: "0.04em",
            textTransform: "uppercase",
            color,
            border: `1px solid ${color}`,
            borderRadius: "999px",
            padding: "2px 9px",
            whiteSpace: "nowrap",
          }}
        >
          {t(`tracker.state.${row.state}`)}
        </span>
        {row.source === "yours" && (
          <span style={{ fontSize: "0.68rem", color: "var(--accent2)", textTransform: "uppercase", letterSpacing: "0.04em" }}>
            {t("tracker.yours")}
          </span>
        )}
        <strong style={{ fontSize: "0.85rem", fontWeight: 650 }}>{row.scheme_name}</strong>
        {row.date && <span style={{ fontSize: "0.78rem", color: "var(--text-secondary)" }}>{row.date}</span>}
        {timing && <span style={{ fontSize: "0.74rem", color }}>{timing}</span>}
      </div>
      {row.title && <p style={{ fontSize: "0.8rem", color: "var(--text-secondary)", lineHeight: 1.5 }}>{row.title}</p>}
      {row.note && <p style={{ fontSize: "0.76rem", color: "var(--text-muted)", lineHeight: 1.55 }}>{row.note}</p>}
      {row.source_url && (
        <a
          href={row.source_url}
          target="_blank"
          rel="noopener noreferrer"
          style={{ display: "inline-flex", alignItems: "center", gap: "5px", fontSize: "0.74rem", color: "var(--accent)", textDecoration: "none" }}
        >
          <ExternalLink size={11} aria-hidden="true" />
          {t("tracker.source")}
          {row.last_verified_at ? ` · ${t("tracker.verified", { date: row.last_verified_at })}` : ""}
        </a>
      )}
    </li>
  );
}

function IconButton({
  label,
  onClick,
  disabled,
  children,
}: {
  label: string;
  onClick: () => void;
  disabled?: boolean;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      onClick={onClick}
      disabled={disabled}
      style={{ ...iconButtonStyle, opacity: disabled ? 0.4 : 1, cursor: disabled ? "default" : "pointer" }}
    >
      {children}
    </button>
  );
}

const cardStyle: CSSProperties = {
  padding: "16px",
  borderRadius: "var(--radius-md)",
  border: "1px solid var(--border)",
  background: "var(--bg-card)",
};

const h2Style: CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: "8px",
  fontSize: "0.95rem",
  fontWeight: 750,
  color: "var(--text-primary)",
  marginBottom: "10px",
};

const labelStyle: CSSProperties = {
  display: "block",
  fontSize: "0.72rem",
  fontWeight: 600,
  color: "var(--text-muted)",
  marginBottom: "5px",
};

const miniLabelStyle: CSSProperties = { ...labelStyle, fontSize: "0.68rem", marginBottom: "3px" };

const inputStyle: CSSProperties = {
  width: "100%",
  background: "var(--bg-surface)",
  border: "1px solid var(--border)",
  borderRadius: "var(--radius-sm)",
  padding: "9px 11px",
  fontSize: "0.85rem",
  color: "var(--text-primary)",
  fontFamily: "inherit",
};

const iconButtonStyle: CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  justifyContent: "center",
  width: "30px",
  height: "30px",
  borderRadius: "var(--radius-sm)",
  border: "1px solid var(--border)",
  background: "var(--bg-surface)",
  color: "var(--text-secondary)",
  cursor: "pointer",
  padding: 0,
};

const ctaStyle: CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  gap: "8px",
  padding: "11px 20px",
  borderRadius: "var(--radius-md)",
  background: "linear-gradient(135deg, var(--accent), var(--accent-dim))",
  color: "#fff",
  textDecoration: "none",
  fontWeight: 700,
  fontSize: "0.87rem",
};

const ghostStyle: CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  gap: "8px",
  padding: "10px 16px",
  borderRadius: "var(--radius-md)",
  background: "transparent",
  border: "1px solid var(--border-bright)",
  color: "var(--text-secondary)",
  fontWeight: 600,
  fontSize: "0.83rem",
};
