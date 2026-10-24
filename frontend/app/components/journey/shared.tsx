"use client";

import { createContext, useContext, useEffect, useState } from "react";
import type { LiveStatus } from "../../lib/kompas";
import { journeyApi, ladder, type Brief, type ConceptDetail, type EvidenceItem, type JourneyRequest, type LadderTask } from "../../lib/journey";
import { signalClass } from "../Signals";
import { useJourney } from "./JourneyProvider";

export function Status({ status, from }: { status: LiveStatus; from?: LiveStatus }) {
  if (from && from !== status) {
    return (
      <span className="j-status-move">
        <span className={signalClass(from)}>{from}</span>
        <span className="j-arrow" aria-label="becomes">→</span>
        <span className={signalClass(status)}>{status}</span>
      </span>
    );
  }
  return <span className={signalClass(status)}>{status}</span>;
}

export function ScenarioToggle() {
  const { scenario, set, loading } = useJourney();
  return (
    <div className={`j-toggle${loading ? " busy" : ""}`} role="radiogroup" aria-label="AI adoption scenario">
      <span className="j-toggle-pill" style={{ transform: `translateX(${scenario === "fast" ? 100 : 0}%)` }} aria-hidden />
      {(["moderate", "fast"] as const).map((s) => (
        <button key={s} role="radio" aria-checked={scenario === s} className={scenario === s ? "on" : ""}
          onClick={() => set({ scenario: s })}>
          {s === "moderate" ? "AI at its current pace" : "AI moves fast"}
        </button>
      ))}
    </div>
  );
}

export function Estimate({ children }: { children?: React.ReactNode }) {
  return (
    <div className="j-estimate">
      <span aria-hidden>◔</span>
      {children ?? "Projections are estimates based on current signals, not predictions."}
    </div>
  );
}

/** A plain-language summary of computed results: Gemini-written and checked, or the fixed template. */
export function BriefBox({ request }: { request: (JourneyRequest & { kind: "bets" | "ping"; from_snapshot?: string | null }) | null }) {
  const [brief, setBrief] = useState<Brief | null>(null);
  const key = JSON.stringify(request);
  useEffect(() => {
    if (!request) return;
    const ctrl = new AbortController();
    setBrief(null);
    const timer = setTimeout(() => {
      journeyApi.brief(JSON.parse(key), ctrl.signal).then(setBrief).catch(() => {});
    }, 400);
    return () => {
      clearTimeout(timer);
      ctrl.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  return (
    <div className={`j-brief glass${brief ? "" : " loading"}`} aria-live="polite">
      <span className="j-brief-mark" aria-hidden>✦</span>
      <div>
        {brief ? <p key={brief.text} className="j-type">{brief.text}</p> : <p className="muted">Writing a summary…</p>}
        {brief && (
          <span className="j-brief-by">
            {brief.by === "template"
              ? "Summary from fixed templates"
              : `Written by ${brief.by}, checked against the computed result`}
          </span>
        )}
      </div>
    </div>
  );
}

// ---------- Signal Ladder drawer (PRD 5.3) ----------

const LadderCtx = createContext<(id: string, task?: LadderTask) => void>(() => {});
export const useLadder = () => useContext(LadderCtx);

const SOURCE_NAMES: Record<string, string> = {
  arxiv: "arXiv", github: "GitHub", hn_front: "Hacker News", hn_hiring: "HN Who is hiring", dosm_jmi: "Malaysia Job Market Insights",
};

export function LadderProvider({ children }: { children: React.ReactNode }) {
  const { snapshot, scenario } = useJourney();
  const [target, setTarget] = useState<{ id: string; task?: LadderTask } | null>(null);
  const [state, setState] = useState<{ concept: ConceptDetail; evidence: EvidenceItem[]; specific?: boolean; overall?: EvidenceItem[] } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const open = (id: string, task?: LadderTask) => setTarget({ id, task });
  const close = () => setTarget(null);

  useEffect(() => {
    if (!target) return;
    setState(null);
    setError(null);
    ladder(target.id, snapshot, target.task).then(setState).catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, [target, snapshot]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && close();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const c = state?.concept;
  return (
    <LadderCtx.Provider value={open}>
      {children}
      {target && (
        <div className="j-drawer-backdrop" onClick={close}>
          <aside className="j-drawer glass" role="dialog" aria-label="Signal Ladder" onClick={(e) => e.stopPropagation()}>
            <button className="j-drawer-close" onClick={close} aria-label="Close">×</button>
            <span className="kicker">{target.task ? "Evidence for this task" : "Signal Ladder · hype or real?"}</span>
            {error && <p className="muted">{error}</p>}
            {!c && !error && <div className="j-drawer-loading"><span className="sk sk-title" /><span className="sk sk-tile" /><span className="sk sk-tile" /></div>}
            {c && (
              <>
                <h2>{target.task ? target.task.label : c.label}</h2>
                {target.task && <p className="muted small j-drawer-ai">The AI that could do it: {c.label}. {target.task.why}.</p>}
                <div className="j-drawer-status">
                  <span className="muted small">Now</span> <Status status={c.status} />
                  <span className="muted small">2028 ({scenario})</span> <Status status={c.projected[scenario]} />
                </div>
                <h3 className="label">{target.task ? "Evidence for this task" : "Evidence"} · snapshot {c.snapshot}</h3>
                {state.evidence.length === 0 && (
                  <p className="muted small">
                    {target.task ? "No record we hold is specific to this task yet." : "No stored records behind this status in this snapshot."}
                  </p>
                )}
                <ul className="j-evidence">
                  {state.evidence.map((e, i) => (
                    <li key={e.id} style={{ "--i": i } as React.CSSProperties}>
                      <span className="j-ev-source">{SOURCE_NAMES[e.source] ?? e.source}</span>
                      {e.url ? <a href={e.url} target="_blank" rel="noopener noreferrer">{e.title}</a> : <span>{e.title}</span>}
                      <span className="muted small">
                        {e.published_at.slice(0, 10)}
                        {e.value != null && ` · ${e.value.toLocaleString()} ${e.value_label ?? ""}`}
                      </span>
                      {e.why && <span className="j-ev-why">{e.why}</span>}
                      {e.coverage_note && <span className="j-ev-note">{e.coverage_note}</span>}
                    </li>
                  ))}
                </ul>
                {target.task && !!state.overall?.length && (
                  <>
                    <h3 className="label">The AI overall · {c.label}</h3>
                    <ul className="j-evidence">
                      {state.overall.map((e, i) => (
                        <li key={e.id} style={{ "--i": i } as React.CSSProperties}>
                          <span className="j-ev-source">{SOURCE_NAMES[e.source] ?? e.source}</span>
                          <span>{e.title}</span>
                          {e.coverage_note && <span className="j-ev-note">{e.coverage_note}</span>}
                        </li>
                      ))}
                    </ul>
                  </>
                )}
              </>
            )}
          </aside>
        </div>
      )}
    </LadderCtx.Provider>
  );
}
