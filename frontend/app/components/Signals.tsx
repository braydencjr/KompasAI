"use client";

import { createContext, useContext, useEffect, useState } from "react";
import { conceptIds, type Signal } from "../data/bets";
import { kompas, type ConceptStatus, type Health } from "../lib/kompas";

type Signals = { live: boolean; health: Health | null; concepts: Record<string, ConceptStatus> };

const SignalsContext = createContext<Signals>({ live: false, health: null, concepts: {} });

export function SignalsProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<Signals>({ live: false, health: null, concepts: {} });

  useEffect(() => {
    let cancelled = false;
    async function load() {
      const [health, res] = await Promise.all([kompas.health(), kompas.concepts()]);
      if (cancelled) return;
      setState({
        live: res !== null,
        health,
        concepts: Object.fromEntries((res?.concepts ?? []).map((c) => [c.id, c])),
      });
    }
    load();
    // picks up a new snapshot without a page reload
    const timer = setInterval(load, 60_000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, []);

  return <SignalsContext.Provider value={state}>{children}</SignalsContext.Provider>;
}

export const useSignals = () => useContext(SignalsContext);

export function signalClass(status: string) {
  return `signal-pill signal-${status.replace(" ", "-").toLowerCase()}`;
}

/** Live Signal Ladder status for an on-screen skill, or the sample value while the API is offline. */
export function useSkillSignal(skill: string, fallback?: Signal) {
  const { concepts } = useSignals();
  const c = concepts[conceptIds[skill]] ?? Object.values(concepts).find((x) => x.label === skill);
  if (!c) return { status: fallback, live: false, lowConfidence: false };
  const lowConfidence = Object.values(c.rungs).some((r) => r.active && r.low_confidence);
  return { status: c.status as Signal, live: true, lowConfidence };
}

export function SignalPill({ skill, fallback }: { skill: string; fallback?: Signal }) {
  const { health } = useSignals();
  const s = useSkillSignal(skill, fallback);
  if (!s.status) return null;
  const title = s.live
    ? `Signal Ladder · snapshot ${health?.latest_snapshot?.id ?? ""}${s.lowConfidence ? " · low confidence" : ""}`
    : "Sample data · signal API offline";
  return (
    <span className={signalClass(s.status)} title={title}>
      {s.status}
      {s.lowConfidence && "?"}
    </span>
  );
}

/** Shown next to a gap chip only when the live status says something beyond "Stable". */
export function GapSignal({ skill }: { skill: string }) {
  const s = useSkillSignal(skill);
  if (!s.live || s.status === "Stable") return null;
  return <span className="chip-signal">· {s.status}</span>;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function longDate(id: string) {
  const [y, m, d] = id.split("-");
  return `${Number(d)} ${MONTHS[Number(m) - 1]} ${y}`;
}

// sample values from the static demo, shown while the API is offline
const SAMPLE = { snapshot: "2026-10-20", sources: 6 };

function useSnapshotInfo() {
  const { live, health } = useSignals();
  const snapshot = health?.latest_snapshot?.id ?? SAMPLE.snapshot;
  const sources = health ? health.sources.filter((s) => s.data_as_of).length : SAMPLE.sources;
  return { live, snapshot, sources };
}

export function SnapshotHud() {
  const { live, snapshot, sources } = useSnapshotInfo();
  return (
    <div className="hud">
      <span>Snapshot <strong>{snapshot.replaceAll("-", ".")}</strong></span>
      <span>Sources <strong>{String(sources).padStart(2, "0")}</strong></span>
      <span>Scenario <strong>Moderate</strong></span>
      <span>{live ? <strong>Live</strong> : "Sample data"}</span>
    </div>
  );
}

export function SidebarSnapshot() {
  const { live, snapshot } = useSnapshotInfo();
  return (
    <div className="snapshot">
      <span className={`pulse${live ? "" : " pulse-off"}`} />
      <div>
        <div className="snapshot-title">{live ? "Live signals" : "Sample data"}</div>
        <div className="snapshot-date">Snapshot · {longDate(snapshot)}</div>
      </div>
    </div>
  );
}
