"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { Mic, MicOff, Radio, PhoneOff, Sparkles } from "lucide-react";
import { Room, RoomEvent, Track } from "livekit-client";

// Use wss:// in production (HTTPS pages block ws:// for LiveKit too)
const rawApiBase = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";
const API_BASE =
  typeof window !== "undefined" &&
  window.location.protocol === "https:" &&
  rawApiBase.startsWith("http://")
    ? rawApiBase.replace("http://", "https://")
    : rawApiBase;

type Status = "idle" | "connecting" | "connected" | "error";

export default function LiveAdvisorPanel() {
  const roomRef = useRef<Room | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [status, setStatus] = useState<Status>("idle");
  const [micOn, setMicOn] = useState(false);
  const [message, setMessage] = useState("");

  const cleanupTracks = useCallback(() => {
    const room = roomRef.current;
    if (!room) return;
    room.remoteParticipants.forEach((participant) => {
      participant.trackPublications.forEach((pub) => {
        const track = pub.track;
        if (track && track.kind === Track.Kind.Audio && audioRef.current) {
          try {
            track.detach(audioRef.current);
          } catch {
            /* noop */
          }
        }
      });
    });
  }, []);

  // Autoplay-safe: the audio element plays after a user gesture (the click).
  const attachAgentAudio = useCallback(
    (track: Track) => {
      const el = audioRef.current;
      if (!el) return;
      try {
        track.attach(el);
        el.play().catch(() => {
          /* browsers may block autoplay until first gesture; it is a click */
        });
      } catch {
        /* noop */
      }
    },
    []
  );

  const connect = useCallback(async () => {
    setStatus("connecting");
    setMessage("");
    try {
      const res = await fetch(`${API_BASE}/api/voice/livekit-token`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      if (!res.ok) {
        let detail = `LiveKit setup failed (${res.status}).`;
        try {
          const body = await res.json();
          if (typeof body?.detail === "string") detail = body.detail;
        } catch {
          /* keep default */
        }
        throw new Error(detail);
      }
      const { url, token } = await res.json();

      const room = new Room();
      roomRef.current = room;

      room
        .on(RoomEvent.TrackSubscribed, (track) => {
          if (track.kind === Track.Kind.Audio) attachAgentAudio(track);
        })
        .on(RoomEvent.TrackUnsubscribed, (track) => {
          if (track.kind === Track.Kind.Audio && audioRef.current) {
            try {
              track.detach(audioRef.current);
            } catch {
              /* noop */
            }
          }
        })
        .on(RoomEvent.Connected, () => {
          setStatus("connected");
          setMessage(
            "Connected. Ask about loans, schemes and documents — the advisor will reply out loud."
          );
        });

      await room.connect(url, token);
      await room.localParticipant.setMicrophoneEnabled(true);
      setMicOn(true);
    } catch (err) {
      setStatus("error");
      setMessage(
        err instanceof Error ? err.message : "Could not connect to the voice advisor."
      );
    }
  }, [attachAgentAudio]);

  const disconnect = useCallback(() => {
    const room = roomRef.current;
    if (room) {
      room.disconnect().catch(() => {
        /* noop */
      });
      roomRef.current = null;
    }
    cleanupTracks();
    setMicOn(false);
    setStatus("idle");
    setMessage("");
  }, [cleanupTracks]);

  const toggleMic = useCallback(async () => {
    const room = roomRef.current;
    if (!room || status !== "connected") return;
    try {
      const next = !micOn;
      await room.localParticipant.setMicrophoneEnabled(next);
      setMicOn(next);
    } catch {
      /* noop */
    }
  }, [micOn, status]);

  useEffect(() => {
    return () => {
      roomRef.current?.disconnect().catch(() => {
        /* noop */
      });
      roomRef.current = null;
    };
  }, []);

  const connected = status === "connected";
  const buttonsEnabled = status === "idle" || status === "connected" || status === "error";

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      style={{
        marginTop: "16px",
        width: "100%",
        maxWidth: "760px",
        padding: "20px 24px",
        background: "rgba(139,92,246,0.05)",
        border: "1px solid rgba(139,92,246,0.25)",
        borderRadius: "var(--radius-xl)",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: "12px", flexWrap: "wrap" }}>
        <div
          style={{
            width: "44px",
            height: "44px",
            borderRadius: "22px",
            background:
              status === "connected"
                ? "linear-gradient(135deg,#4ade80,#16a34a)"
                : "linear-gradient(135deg,#a78bfa,#7c3aed)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            flexShrink: 0,
          }}
        >
          <Radio size={20} color="#fff" />
        </div>
        <div style={{ flex: 1, minWidth: "200px" }}>
          <div style={{ fontSize: "0.9rem", fontWeight: 700, color: "var(--text-primary)" }}>
            Talk to your Loan Advisor
            <span style={{ marginLeft: "8px", fontSize: "0.6rem", color: "var(--accent)", textTransform: "uppercase", letterSpacing: "0.08em" }}>Live</span>
          </div>
          <div style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>
            Real-time voice via LiveKit — hear the advisor, speak back naturally.
          </div>
        </div>

        <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
          {connected && (
            <button
              type="button"
              onClick={toggleMic}
              title={micOn ? "Mute microphone" : "Unmute microphone"}
              style={{
                border: "1px solid rgba(255,255,255,0.15)",
                background: "rgba(255,255,255,0.06)",
                borderRadius: "12px",
                padding: "10px",
                cursor: "pointer",
                color: "var(--text-primary)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              {micOn ? <Mic size={16} /> : <MicOff size={16} color="var(--error)" />}
            </button>
          )}
          {!connected ? (
            <button
              type="button"
              disabled={status === "connecting" || !buttonsEnabled}
              onClick={connect}
              style={{
                border: "none",
                background: "linear-gradient(135deg,#a78bfa,#7c3aed)",
                color: "#fff",
                fontWeight: 700,
                borderRadius: "12px",
                padding: "10px 18px",
                cursor: status === "connecting" ? "wait" : "pointer",
                display: "flex",
                alignItems: "center",
                gap: "8px",
                opacity: buttonsEnabled ? 1 : 0.5,
              }}
            >
              <Sparkles size={15} />
              {status === "connecting" ? "Connecting…" : "Start Voice"}
            </button>
          ) : (
            <button
              type="button"
              onClick={disconnect}
              style={{
                border: "none",
                background: "rgba(248,113,113,0.15)",
                color: "var(--error)",
                fontWeight: 700,
                borderRadius: "12px",
                padding: "10px 18px",
                cursor: "pointer",
                display: "flex",
                alignItems: "center",
                gap: "8px",
              }}
            >
              <PhoneOff size={15} />
              End Call
            </button>
          )}
        </div>
      </div>

      {message && (
        <p
          style={{
            marginTop: "12px",
            fontSize: "0.78rem",
            color: status === "error" ? "var(--error)" : "var(--text-muted)",
            lineHeight: 1.5,
          }}
        >
          {message}
        </p>
      )}
      {status === "error" && (
        <p
          style={{
            marginTop: "6px",
            fontSize: "0.72rem",
            color: "var(--text-muted)",
          }}
        >
          Setup: add LIVEKIT_URL / LIVEKIT_API_KEY / LIVEKIT_API_SECRET to backend/.env,
          run <code style={{ color: "var(--accent)" }}>pip install -r backend/requirements-voice.txt</code>,
          then <code style={{ color: "var(--accent)" }}>python -m backend.voice_agent.worker</code>.
        </p>
      )}

      <audio ref={audioRef} style={{ display: "none" }} />
    </motion.div>
  );
}