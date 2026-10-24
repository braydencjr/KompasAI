"use client";

import { useEffect } from "react";
import { createPortal } from "react-dom";
import { useProfile } from "../Profile";
import { useJourney, type StepId } from "./JourneyProvider";

export type Gate = "cv" | "job";

/** What a step is still missing. AI & Skills Outlook and Career Impact need a CV (not the sample profile); the Learning
 * Route needs a CV and then a chosen job. null = ready, or still reading what this browser saved (so the popup doesn't
 * flash on every page load). */
export function useStepGate(step: StepId): Gate | null {
  const { source, ready } = useProfile();
  const { role, restored } = useJourney();
  if (!ready || !restored) return null;
  if ((step === "future" || step === "bets" || step === "route") && source !== "cv") return "cv";
  if (step === "route" && !role) return "job";
  return null;
}

const COPY: Record<Gate, { title: string; text: string; action: string; step: "you" | "bets" }> = {
  cv: {
    title: "Upload your CV first",
    text: "Kompas builds your AI outlook, career options and learning route from the skills in your CV, so it needs your CV first.",
    action: "Upload my CV",
    step: "you",
  },
  job: {
    title: "Choose a job first",
    text: "Pick the job you're aiming for on Career Impact. Kompas then builds the learning route to that job.",
    action: "Choose a job",
    step: "bets",
  },
};

/** Stands in for a step until the CV and the job are in place. Its one button goes to what's missing. */
export default function RouteGate({ gate }: { gate: Gate }) {
  const { go } = useJourney();
  const c = COPY[gate];

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && go(c.step);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [go, c.step]);

  return createPortal(
    <div className="modal-backdrop" role="presentation">
      <div className="modal glass route-gate" role="alertdialog" aria-modal="true" aria-labelledby="gate-title" aria-describedby="gate-text">
        <span className="route-gate-icon" aria-hidden>{gate === "cv" ? "↑" : "✦"}</span>
        <h2 id="gate-title">{c.title}</h2>
        <p id="gate-text" className="muted">{c.text}</p>
        <button className="btn btn-primary" onClick={() => go(c.step)} autoFocus>{c.action} →</button>
      </div>
    </div>,
    document.body,
  );
}
