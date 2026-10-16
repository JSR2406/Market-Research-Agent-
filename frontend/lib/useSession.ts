"use client";

import { useCallback, useEffect, useState } from "react";
import { migrateIntake, type IntakeAnswers } from "@/lib/intake";

/**
 * One browser session, shared by every page.
 *
 * The session id ties together the research run, the saved advisory, the
 * advisor chat and the export/delete controls, so it must be created and read
 * the same way everywhere. The Business Check-up answers live beside it and are
 * reused by the advisor so follow-up questions know the business.
 *
 * Site language is deliberately NOT here — `useI18n()` owns that, and two
 * sources of truth for the language is exactly how a site ends up half
 * translated.
 */
const SESSION_KEY = "grameenai_session";
const PROFILE_KEY = "grameenai_profile";

export function useSession() {
  const [sessionId, setSessionId] = useState("");
  const [intake, setIntake] = useState<IntakeAnswers>({});
  const [ready, setReady] = useState(false);

  useEffect(() => {
    try {
      const existing = window.localStorage.getItem(SESSION_KEY);
      if (existing) setSessionId(existing);

      const savedProfile = window.localStorage.getItem(PROFILE_KEY);
      if (savedProfile) {
        const parsed = migrateIntake(JSON.parse(savedProfile));
        if (parsed && Object.keys(parsed).length) setIntake(parsed);
      }
    } catch {
      // Private mode / corrupt data — the app still works, just without memory.
    }
    setReady(true);
  }, []);

  /** Return the current id, creating and persisting one the first time. */
  const ensureSessionId = useCallback((): string => {
    let id = sessionId;
    if (!id) {
      id = `s-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
      setSessionId(id);
      try {
        window.localStorage.setItem(SESSION_KEY, id);
      } catch {
        /* ignore */
      }
    }
    return id;
  }, [sessionId]);

  const updateIntake = useCallback((next: IntakeAnswers) => {
    setIntake(next);
    try {
      window.localStorage.setItem(PROFILE_KEY, JSON.stringify(next));
    } catch {
      /* ignore */
    }
  }, []);

  return { sessionId, ready, ensureSessionId, intake, updateIntake };
}
