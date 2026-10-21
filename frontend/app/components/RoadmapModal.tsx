"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import JobsPanel from "./JobsPanel";
import Ring from "./Ring";
import Roadmap, { SkillColumns, useStepProgress } from "./Roadmap";
import { riskLabel, type Bet } from "../data/bets";

// keep in sync with the jobs-slot / panel-out animation length in globals.css
const JOBS_CLOSE_MS = 380;

export default function RoadmapModal({ bet, onClose }: { bet: Bet; onClose: () => void }) {
  const { done, toggle, gapClosed } = useStepProgress(bet);
  const dialogRef = useRef<HTMLDivElement>(null);
  const [jobs, setJobs] = useState<"closed" | "open" | "closing">("closed");

  const closeJobs = useCallback(() => {
    setJobs("closing");
    setTimeout(() => setJobs("closed"), JOBS_CLOSE_MS);
    dialogRef.current?.focus({ preventScroll: true });
  }, []);

  function toggleJobs() {
    if (jobs === "open") closeJobs();
    else if (jobs === "closed") setJobs("open");
  }

  useEffect(() => {
    dialogRef.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const jobsOpen = jobs === "open";

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className={`modal-stage${jobsOpen ? " split" : ""}`}>
        <div
          ref={dialogRef}
          tabIndex={-1}
          className="modal modal-main glass"
          role="dialog"
          aria-modal="true"
          aria-labelledby="modal-title"
          onClick={(e) => e.stopPropagation()}
        >
          <button className="modal-close" onClick={onClose} aria-label="Close roadmap">
            ×
          </button>

          <header className="modal-head">
            <div>
              <div className="plan-tags">
                <span className="label">{bet.kind} · Full roadmap</span>
                <span className="chip chip-blue">{bet.sdg.goal}</span>
              </div>
              <h2 id="modal-title">{bet.title}</h2>
              <p className="muted">{bet.summary}</p>
            </div>
          </header>

          <div className="modal-stats">
            <div className="modal-stat">
              <Ring value={bet.match} size={56} stroke={4} />
              <div>
                <div className="label">Skill match</div>
                <strong>{bet.match}%</strong>
              </div>
            </div>
            <div className="modal-stat">
              <div>
                <div className="label">AI risk · 5 yrs</div>
                <strong>{bet.aiRisk}%</strong> <span className="risk-pill">{riskLabel(bet.aiRisk)}</span>
              </div>
            </div>
            <button
              className={`modal-stat jobs-cta${jobsOpen ? " active" : ""}`}
              onClick={toggleJobs}
              aria-expanded={jobsOpen}
            >
              <span className="jobs-cta-icon" aria-hidden>
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="3" y="7" width="18" height="13" rx="2.5" />
                  <path d="M9 7V5.5A1.5 1.5 0 0 1 10.5 4h3A1.5 1.5 0 0 1 15 5.5V7M3 12.5h18" />
                </svg>
              </span>
              <div>
                <div className="label">{bet.openings.length} openings</div>
                <span className="jobs-cta-text">{jobsOpen ? "Hide jobs ←" : "Find open jobs →"}</span>
              </div>
            </button>
          </div>

          <SkillColumns role={bet} gapClosed={gapClosed} />
          <Roadmap role={bet} done={done} toggle={toggle} vertical />
        </div>

        {jobs !== "closed" && <JobsPanel bet={bet} closing={jobs === "closing"} onClose={closeJobs} />}
      </div>
    </div>
  );
}
