"use client";

import { useEffect, useRef, useState } from "react";
import type { CvProfile, SkillSignal } from "../lib/kompas";
import { useJourney } from "./journey/JourneyProvider";
import { signalClass } from "./Signals";
import { matchJobs, type JobOption } from "../lib/jobMatch";

const STAGES = ["Read your CV", "Find your skills", "Your skills in the market"] as const;

// stand-in lines while a PDF/DOCX's text is on its way; widths in %
const PLACEHOLDER = [58, 34, 0, 92, 76, 88, 0, 64, 95, 81, 70, 0, 52, 90, 84, 0, 40, 86];

// stickers pop this far apart once the reader has answered (ms)
const STICKER_GAP = 140;

const RISING = ["Act now", "Emerging"];
const FALLING = ["Declining", "Stalled"];
// the overall status, in the buckets the tally counts
const BUCKETS = [
  { id: "up", label: "in demand", statuses: RISING },
  { id: "watch", label: "gaining attention", statuses: ["Watch"] },
  { id: "steady", label: "steady", statuses: ["Stable"] },
  { id: "down", label: "falling", statuses: FALLING },
];
// rising first, then steady, then falling; skills without data last
const ORDER: Record<string, number> = { "Act now": 0, Emerging: 1, Watch: 2, Stable: 3, Stalled: 4, Declining: 5 };

const norm = (s: string) => s.toLowerCase().replace(/\s+/g, " ").trim();

/** The first quote a CV line contains (or is part of), or -1. */
function quoteIn(line: string, quotes: string[]) {
  const l = norm(line);
  return quotes.findIndex((q) => {
    const n = norm(q);
    return n.length > 3 && (l.includes(n.slice(0, 28)) || (l.length > 12 && n.includes(l)));
  });
}

const fmtDate = (iso: string) =>
  new Date(`${iso.slice(0, 10)}T00:00:00`).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });

type Props = {
  fileName: string;
  /** the CV's own lines, when this session read it */
  lines: string[] | null;
  /** null while the reader is working */
  cv: CvProfile | null;
  /** play the stages (a fresh read) or show them finished (a restored profile) */
  animate: boolean;
};

/** You, step 1: the CV is read, its skills become stickers, and each skill is checked against the market. Which
 * job to aim for comes later (Your direction), after The Mirror has shown whether the current job is at risk. */
export default function CvFlow({ fileName, lines, cv, animate }: Props) {
  const { next } = useJourney();
  const [play, setPlay] = useState(animate);
  const [stage, setStage] = useState(cv && !animate ? 3 : 1);
  const refs = useRef<(HTMLElement | null)[]>([]);

  useEffect(() => {
    if (!cv) return setStage(1);
    if (!play) return setStage(3);
    setStage(2);
    const timer = setTimeout(() => setStage(3), 900 + (cv.skills.length + cv.ai_tools.length) * STICKER_GAP);
    return () => clearTimeout(timer);
  }, [cv, play]);

  // follow the flow down the page as each stage opens
  useEffect(() => {
    if (play && stage > 1) refs.current[stage - 1]?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [stage, play]);

  const quotes = cv?.skills.map((s) => s.quote) ?? [];
  const finished = !!cv && stage === 3;

  return (
    <section className={`flow glass${play ? "" : " static"}`} aria-live="polite">
      <header className="flow-head">
        <ol className="flow-steps">
          {STAGES.map((s, i) => {
            const done = i + 1 < stage || (finished && i === 2);
            return (
              <li key={s} className={done ? "done" : i + 1 === stage ? "active" : ""}>
                <span className="flow-dot">{done ? "✓" : i + 1}</span>
                {s}
              </li>
            );
          })}
        </ol>
        {cv && (stage < 3 ? (
          <button className="btn btn-ghost btn-sm" onClick={() => setPlay(false)}>Skip</button>
        ) : (
          <button className="btn btn-ghost btn-sm" onClick={() => { setPlay(false); setTimeout(() => setPlay(true)); }}>Replay</button>
        ))}
      </header>

      {/* 1 · read */}
      <div className="flow-stage" ref={(el) => { refs.current[0] = el; }}>
        <StageHead n={1} title="Read your CV" busy={!cv}>
          {!cv && <>Reading <strong>{fileName}</strong>…</>}
        </StageHead>
        {(lines || !cv) && (
          <div className="flow-doc" aria-hidden>
            <div className="flow-doc-lines">
              {lines
                ? lines.slice(0, 40).map((line, i) => {
                    const q = stage >= 2 ? quoteIn(line, quotes) : -1;
                    return (
                      <div key={i} className={`flow-line${q >= 0 ? " hit" : ""}`} style={{ "--d": `${Math.max(q, 0) * STICKER_GAP}ms` } as React.CSSProperties}>
                        {line}
                      </div>
                    );
                  })
                : PLACEHOLDER.map((w, i) => <div key={i} className={`flow-bar${w ? "" : " gap"}`} style={{ width: `${w}%` }} />)}
            </div>
            {!cv && <div className="scan-beam" />}
          </div>
        )}
      </div>

      {/* 2 · skills */}
      {cv && stage >= 2 && (
        <div className="flow-stage" ref={(el) => { refs.current[1] = el; }}>
          <StageHead n={2} title="Find your skills" />
          <Stickers cv={cv} />
          <CurrentJob cv={cv} />
        </div>
      )}

      {/* 3 · market */}
      {cv && stage >= 3 && (
        <div className="flow-stage" ref={(el) => { refs.current[2] = el; }}>
          <StageHead n={3} title="Your skills in the market">
            For each skill we check three signals, from weakest to strongest: people talking about it, companies
            abroad hiring for it, and Malaysian employers hiring for it
            {cv.snapshot && <> (data as of <strong>{fmtDate(cv.snapshot.as_of)}</strong>)</>}.
          </StageHead>
          <Market cv={cv} />
          <NextUp cv={cv} onNext={next} />
        </div>
      )}
    </section>
  );
}

function StageHead({ n, title, busy, children }: { n: number; title: string; busy?: boolean; children?: React.ReactNode }) {
  return (
    <div className="flow-stage-head">
      <span className={`flow-num${busy ? " busy" : ""}`}>{n}</span>
      <div>
        <h3>{title}</h3>
        {children && <p className="muted">{children}</p>}
      </div>
    </div>
  );
}

function Stickers({ cv }: { cv: CvProfile }) {
  const [open, setOpen] = useState<string | null>(null);
  const all = [...cv.skills.map((s) => ({ ...s, tool: false })), ...cv.ai_tools.map((s) => ({ ...s, tool: true }))];
  const picked = all.find((s) => s.id === open);
  return (
    <div className="stickers">
      <div className="sticker-tray">
        {all.map((s, i) => (
          <button key={s.id} className={`sticker${s.tool ? " tool" : ""}${open === s.id ? " on" : ""}`}
            style={{ "--d": `${i * STICKER_GAP}ms` } as React.CSSProperties} onClick={() => setOpen(open === s.id ? null : s.id)}>
            <span className="sticker-label">{s.label}</span>
            <span className="sticker-sub">{s.tool ? "AI tool you used" : s.family?.label ?? "Skill"}</span>
          </button>
        ))}
      </div>
      <p className="sticker-quote">
        {picked ? <>From your CV: <q>{picked.quote}</q></> : <span className="muted small">Tap a skill to see the line of your CV it came from.</span>}
      </p>
      {cv.unrecognised.length > 0 && (
        <p className="muted small">Also in your CV, not tracked by Kompas yet: {cv.unrecognised.map((u) => u.name).join(", ")}.</p>
      )}
    </div>
  );
}

/** The job The Mirror looks at: read from the CV, or typed by the user. People between jobs, or changing career,
 * pick the job they're aiming for instead. */
function CurrentJob({ cv }: { cv: CvProfile }) {
  const { catalog, occupation, set } = useJourney();
  const [editing, setEditing] = useState(false);
  const job = cv.jobs.find((j) => j.occupation);
  const title = catalog?.occupations.find((o) => o.isco === occupation)?.title
    ?? (job?.occupation?.isco === occupation ? job?.occupation?.title : undefined);
  const fromCv = job?.occupation?.isco === occupation;

  return (
    <div className="current-job">
      <span className="label">Your current job, or the job you&apos;re aiming for</span>
      {editing || !(occupation && title) ? (
        <JobSearch
          jobs={catalog?.occupations ?? []}
          intro={occupation && title ? null : "We couldn't tell your job from your CV."}
          onPick={(isco) => {
            set({ occupation: isco, overrides: {} });
            setEditing(false);
          }}
          onCancel={occupation && title ? () => setEditing(false) : undefined}
        />
      ) : (
        <div className="current-job-row">
          <p>
            <strong>{title}</strong>
            {fromCv && <span className="muted"> · from &ldquo;{job!.title}&rdquo; on your CV</span>}
          </p>
          <button className="current-job-change" onClick={() => setEditing(true)}>Change</button>
        </div>
      )}
    </div>
  );
}

/** Type a job, see the closest ones Kompas knows, pick one. */
function JobSearch({ jobs, intro, onPick, onCancel }: {
  jobs: JobOption[];
  intro: string | null;
  onPick: (isco: string) => void;
  onCancel?: () => void;
}) {
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const results = query.trim() ? matchJobs(query, jobs) : [];

  useEffect(() => inputRef.current?.focus(), []);
  useEffect(() => setActive(0), [query]);

  return (
    <div className="job-search">
      <p className="muted small">
        {intro ? `${intro} ` : ""}Type your job title. Not working right now, or changing career? Type the job
        you&apos;re most interested in.
      </p>
      <div className="job-search-box">
        <input
          ref={inputRef}
          value={query}
          placeholder="e.g. PR executive, nurse, Java engineer"
          aria-label="Your job, or the job you're aiming for"
          role="combobox"
          aria-expanded={results.length > 0}
          aria-controls="job-search-results"
          aria-activedescendant={results[active] ? `job-${results[active].job.isco}` : undefined}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown") {
              e.preventDefault();
              setActive((i) => Math.min(i + 1, results.length - 1));
            } else if (e.key === "ArrowUp") {
              e.preventDefault();
              setActive((i) => Math.max(i - 1, 0));
            } else if (e.key === "Enter" && results[active]) {
              onPick(results[active].job.isco);
            } else if (e.key === "Escape") {
              onCancel?.();
            }
          }}
        />
        {onCancel && <button className="link small" onClick={onCancel}>Cancel</button>}
      </div>

      {query.trim() && (
        results.length ? (
          <>
          {!results[0].complete && (
            <p className="muted small">No exact match: Kompas covers {jobs.length} jobs so far. These are the closest:</p>
          )}
          <ul id="job-search-results" className="job-search-results" role="listbox" aria-label="Closest jobs">
            {results.map(({ job: o, via }, i) => (
              <li key={o.isco} id={`job-${o.isco}`} role="option" aria-selected={i === active}
                className={i === active ? "on" : ""} onMouseEnter={() => setActive(i)} onMouseDown={(e) => {
                  e.preventDefault();
                  onPick(o.isco);
                }}>
                <strong>{o.title}</strong>
                <span className="muted small">{via ? `Also called “${via}” · ` : ""}{o.occupation}</span>
              </li>
            ))}
          </ul>
          </>
        ) : (
          <div className="job-search-none">
            <p className="muted small">No close match yet: Kompas covers {jobs.length} jobs so far. Pick the nearest one:</p>
            <div className="job-search-all">
              {jobs.map((o) => <button key={o.isco} className="chip" onClick={() => onPick(o.isco)}>{o.title}</button>)}
            </div>
          </div>
        )
      )}
    </div>
  );
}

const SIGNAL_LABEL: Record<number, string> = { 1: "Talked about", 2: "Hired abroad", 3: "Hired in Malaysia" };

/** One of the three signals, as a bar filled by how strongly it moves. */
function Rung({ rung }: { rung: SkillSignal["rungs"][number] }) {
  return (
    <div className={`rung mv-${rung.movement.replaceAll(" ", "-")}`} title={rung.sources.length ? `From ${rung.sources.join(", ")}` : undefined}>
      <span className="rung-name">{SIGNAL_LABEL[rung.rung]}</span>
      <span className="rung-bar"><i /></span>
      <span className="rung-move">{rung.movement === "no data" ? "No data yet" : rung.movement}</span>
    </div>
  );
}

function Market({ cv }: { cv: CvProfile }) {
  const rank = (id: string) => ORDER[cv.signals[id]?.status ?? ""] ?? 9;
  const skills = [...cv.skills].sort((a, b) => rank(a.id) - rank(b.id));
  return (
    <div className="market-cards">
      {skills.map((s, i) => {
        const sig = cv.signals[s.id];
        const top = sig?.evidence[0];
        return (
          <article key={s.id} className={`mcard${sig && RISING.includes(sig.status) ? " up" : sig?.status === "Watch" ? " watch" : ""}`} style={{ "--d": `${i * 110}ms` } as React.CSSProperties}>
            <header className="mcard-head">
              <h4>{s.label}</h4>
              {sig ? <span className={signalClass(sig.status)}>{sig.status}</span> : <span className="muted small">No data yet</span>}
            </header>
            {sig?.meaning && <p className="mcard-meaning">{sig.meaning}</p>}
            {sig && <div className="rungs">{sig.rungs.map((r) => <Rung key={r.rung} rung={r} />)}</div>}
            {top && (
              <a className="mcard-ev" href={top.url} target="_blank" rel="noopener noreferrer">
                <span className="mcard-ev-label">Strongest evidence</span>
                <span className="mcard-ev-title">{top.title}</span>
                <span className="mcard-ev-meta">{top.source} · {fmtDate(top.date)}</span>
              </a>
            )}
          </article>
        );
      })}
    </div>
  );
}

/** Where the skills stand, and the question The Mirror answers next. */
function NextUp({ cv, onNext }: { cv: CvProfile; onNext: () => void }) {
  const status = (id: string) => cv.signals[id]?.status ?? "";
  return (
    <div className="flow-next">
      <div className="flow-tally">
        {BUCKETS.map((b) => (
          <span key={b.id} className={`tally ${b.id}`}>
            <b>{cv.skills.filter((s) => b.statuses.includes(status(s.id))).length}</b> {b.label}
          </span>
        ))}
      </div>
      <div className="flow-next-cta">
        <p>
          <strong>Next: is your job safe from AI?</strong>
          <span className="muted"> See which of its tasks AI is learning to do, before deciding whether to stay or switch.</span>
        </p>
        <button className="btn btn-primary" onClick={onNext}>Check my job →</button>
      </div>
    </div>
  );
}
