"use client";

import { useEffect, useRef, useState } from "react";
import { useProfile } from "./Profile";
import { SimButton } from "./SimulatorProvider";
import { jobSearchLinks, type Bet } from "../data/bets";
import { liveJobs, type LiveJobs } from "../lib/kompas";

const fmt = (iso: string) => new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });

type Props = { bet: Bet; closing: boolean; onClose: () => void };

export default function JobsPanel({ bet, closing, onClose }: Props) {
  const panelRef = useRef<HTMLDivElement>(null);
  const { skills } = useProfile();
  // live openings for journey roles (their id is the ISCO code); the dashboard's sample bets keep their sample list
  const isRole = /^\d{4}$/.test(bet.id);
  const [live, setLive] = useState<LiveJobs | null | "loading">(isRole ? "loading" : null);

  useEffect(() => {
    if (!isRole) return;
    let gone = false;
    liveJobs(bet.id, skills).then((r) => !gone && setLive(r));
    return () => {
      gone = true;
    };
  }, [bet.id, isRole, skills]);

  const jobs = live && live !== "loading" ? live.jobs : [];

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
            <span className="chip chip-blue">{bet.growth >= 0 ? "+" : ""}{bet.growth}% {bet.trendNote ?? "YoY"}</span>
          </div>
          <h2 id="jobs-title">
            {live === "loading" ? `Finding ${bet.title} jobs…` : jobs.length ? `${jobs.length} open ${bet.title} jobs`
              : bet.openings.length ? `${bet.openings.length} openings` : `Search ${bet.title} jobs`}
          </h2>
          <p className="muted small">Your matching skills are highlighted. Not sure yet? Try the work first.</p>
          <SimButton roleId={bet.id} variant="link" />
        </header>

        {live === "loading" && (
          <div className="jobs-loading" aria-live="polite">
            <p className="muted small">
              <span className="jobs-spinner" aria-hidden /> Searching live openings in Malaysia…
            </p>
            <ul className="jobs" aria-hidden>
              {[0, 1, 2].map((i) => (
                <li key={i} className="job job-skeleton" style={{ "--i": i } as React.CSSProperties}>
                  <span className="sk sk-title" />
                  <span className="sk sk-line" />
                  <span className="sk sk-chip" />
                </li>
              ))}
            </ul>
          </div>
        )}

        {jobs.length > 0 && (
          <ul className="jobs">
            {jobs.map((job) => (
              <li key={job.id ?? job.title + job.employer} className="job">
                <div className="job-top">
                  <h4>{job.title}</h4>
                  <span className="meta">{job.remote ? "Remote" : job.type?.toLowerCase().replace("fulltime", "full-time") ?? ""}</span>
                </div>
                <div className="muted small">{job.employer}{job.location ? ` · ${job.location}` : ""}</div>
                <div className="job-bottom">
                  <div className="chips">
                    {job.matched.map((s) => <span key={s} className="chip chip-have">✓ {s}</span>)}
                  </div>
                  <div className="job-pay">
                    {job.salary && <strong className="job-salary">{job.salary}</strong>}
                    {job.posted && <span className="muted small">Posted {fmt(job.posted)}</span>}
                  </div>
                </div>
                {job.url && (
                  <a className="job-link" href={job.url} target="_blank" rel="noopener noreferrer">
                    Apply{job.via ? ` on ${job.via}` : ""} ↗
                  </a>
                )}
              </li>
            ))}
          </ul>
        )}
        {live && live !== "loading" && (
          <p className="muted small job-source">
            {jobs.length ? `Live from ${live.source}` : `No live listings for this role right now${live.note ? ` (${live.note})` : ""}.`}
            {live.fetched_at && ` · fetched ${fmt(live.fetched_at)}`}
          </p>
        )}

        <ul className="jobs">
          {!jobs.length && bet.openings.map((job) => (
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
          <p className="muted small">
            {!jobs.length && bet.openings.length ? "Sample openings shown for the demo. " : ""}More listings open on each job board.
          </p>
        </div>
      </div>
    </div>
  );
}
