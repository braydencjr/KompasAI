"use client";

import { useEffect, useRef } from "react";
import { jobSearchLinks, type Bet } from "../data/bets";

type Props = { bet: Bet; closing: boolean; onClose: () => void };

export default function JobsPanel({ bet, closing, onClose }: Props) {
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    panelRef.current?.focus({ preventScroll: true });
    // capture phase + stopImmediatePropagation so Esc closes only this panel, not the roadmap beside it
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      e.stopImmediatePropagation();
      onClose();
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [onClose]);

  return (
    <div className={`jobs-slot${closing ? " closing" : ""}`}>
      <div
        ref={panelRef}
        tabIndex={-1}
        className="modal modal-jobs glass"
        role="dialog"
        aria-labelledby="jobs-title"
        onClick={(e) => e.stopPropagation()}
      >
        <button className="modal-close" onClick={onClose} aria-label="Close job openings">
          ×
        </button>

        <header className="modal-head">
          <div className="plan-tags">
            <span className="label">Open jobs · Malaysia</span>
            <span className="chip chip-blue">+{bet.growth}% YoY</span>
          </div>
          <h2 id="jobs-title">{bet.openings.length} openings</h2>
          <p className="muted small">Your matching skills are highlighted.</p>
        </header>

        <ul className="jobs">
          {bet.openings.map((job) => (
            <li key={job.title + job.employer} className="job">
              <div className="job-top">
                <h4>{job.title}</h4>
                <span className="meta">{job.mode}</span>
              </div>
              <div className="muted small">
                {job.employer} · {job.location}
              </div>
              <div className="job-bottom">
                <div className="chips">
                  {job.matched.map((s) => (
                    <span key={s} className="chip chip-have">✓ {s}</span>
                  ))}
                </div>
                <div className="job-pay">
                  <strong className="job-salary">{job.salary}</strong>
                  <span className="muted small">{job.posted}</span>
                </div>
              </div>
            </li>
          ))}
        </ul>

        <div className="job-search">
          <div className="label">Search live openings</div>
          <div className="job-boards">
            {jobSearchLinks(bet.title).map((b) => (
              <a key={b.name} href={b.url} target="_blank" rel="noopener noreferrer" className="btn btn-ghost btn-sm">
                {b.name} ↗
              </a>
            ))}
          </div>
          <p className="muted small">Sample openings shown for the demo. Live listings open on each job board.</p>
        </div>
      </div>
    </div>
  );
}
