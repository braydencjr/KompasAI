"use client";

import { createContext, useContext, useEffect, useState } from "react";
import { listWords, type LiveStatus } from "../../lib/kompas";
import { journeyApi, ladder, type Brief, type ConceptDetail, type EvidenceItem, type JourneyRequest } from "../../lib/journey";
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

const LadderCtx = createContext<(id: string) => void>(() => {});
export const useLadder = () => useContext(LadderCtx);

const RUNGS = [
  { key: "1", name: "Talked about", sub: "research, open source, tech news" },
  { key: "2", name: "Hiring abroad", sub: "job posts outside Malaysia" },
  { key: "3", name: "Hiring in Malaysia", sub: "Malaysian job openings posted online" },
] as const;

// DOSM / MASCO 2020 major occupation groups, in everyday words (as journey.GROUP_WORDS)
const MAJOR_GROUPS: Record<string, string> = {
  "1": "manager", "2": "professional", "3": "technician", "4": "clerical", "5": "service and sales",
  "6": "farming and fishing", "7": "trades", "8": "machine operator", "9": "elementary",
};

const SOURCE_NAMES: Record<string, string> = {
  arxiv: "arXiv", github: "GitHub", hn_front: "Hacker News", hn_hiring: "HN Who is hiring", dosm_jmi: "Malaysia Job Market Insights",
};

export function LadderProvider({ children }: { children: React.ReactNode }) {
  const { snapshot, scenario } = useJourney();
  const [open, setOpen] = useState<string | null>(null);
  const [state, setState] = useState<{ concept: ConceptDetail; evidence: EvidenceItem[] } | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setState(null);
    setError(null);
    ladder(open, snapshot).then(setState).catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, [open, snapshot]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(null);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const c = state?.concept;
  return (
    <LadderCtx.Provider value={setOpen}>
      {children}
      {open && (
        <div className="j-drawer-backdrop" onClick={() => setOpen(null)}>
          <aside className="j-drawer glass" role="dialog" aria-label="Signal Ladder" onClick={(e) => e.stopPropagation()}>
            <button className="j-drawer-close" onClick={() => setOpen(null)} aria-label="Close">×</button>
            <span className="kicker">Signal Ladder · hype or real?</span>
            {error && <p className="muted">{error}</p>}
            {!c && !error && <div className="j-drawer-loading"><span className="sk sk-title" /><span className="sk sk-tile" /><span className="sk sk-tile" /></div>}
            {c && (
              <>
                <h2>{c.label}</h2>
                <div className="j-drawer-status">
                  <span className="muted small">Now</span> <Status status={c.status} />
                  <span className="muted small">2028 ({scenario})</span> <Status status={c.projected[scenario]} />
                </div>
                <ol className="j-rungs">
                  {RUNGS.map((r, i) => {
                    const rung = c.rungs[r.key];
                    const family = r.key === "3" && rung?.level === "family";
                    return (
                      <li key={r.key} className={`${rung?.active ? "on" : ""}${family ? " family" : ""}`} style={{ "--i": i } as React.CSSProperties}>
                        <span className="j-rung-dot" />
                        <div>
                          <strong>{r.name}</strong>
                          <span className="muted small">
                            {r.sub}
                            {rung?.sources.length ? ` · ${rung.sources.map((s) => SOURCE_NAMES[s] ?? s).join(", ")}` : " · no data"}
                            {family ? " · measured for the job family" : ""}
                            {r.key === "3" && rung?.level === "group" && rung.groups?.length
                              ? ` · based on all ${listWords(rung.groups.map((g) => MAJOR_GROUPS[g] ?? g))} job openings, so it doesn't change the status`
                              : ""}
                            {rung?.active && rung.low_confidence ? " · low confidence" : ""}
                          </span>
                        </div>
                        {/* a whole-group Malaysian rung's score is for its share of openings, which can rise while
                            openings fall: the skill cards show the change in openings instead, so no score here */}
                        <span className="j-rung-trend">{rung?.trend == null || rung.level === "group" ? "–" : `${rung.trend > 0 ? "+" : ""}${rung.trend.toFixed(1)}`}</span>
                      </li>
                    );
                  })}
                </ol>
                <h3 className="label">Evidence · snapshot {c.snapshot}</h3>
                {state.evidence.length === 0 && <p className="muted small">No stored records behind this status in this snapshot.</p>}
                <ul className="j-evidence">
                  {state.evidence.map((e, i) => (
                    <li key={e.id} style={{ "--i": i } as React.CSSProperties}>
                      <span className="j-ev-source">{SOURCE_NAMES[e.source] ?? e.source}</span>
                      {e.url ? <a href={e.url} target="_blank" rel="noopener noreferrer">{e.title}</a> : <span>{e.title}</span>}
                      <span className="muted small">
                        {e.published_at.slice(0, 10)}
                        {e.value != null && ` · ${e.value.toLocaleString()} ${e.value_label ?? ""}`}
                      </span>
                      {e.coverage_note && <span className="j-ev-note">{e.coverage_note}</span>}
                    </li>
                  ))}
                </ul>
              </>
            )}
          </aside>
        </div>
      )}
    </LadderCtx.Provider>
  );
}
