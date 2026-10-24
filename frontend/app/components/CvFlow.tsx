"use client";

import { useEffect, useRef, useState } from "react";
import { listWords, type CvProfile, type CvRead, type MalaysiaMarket, type SkillSignal } from "../lib/kompas";
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
  /** the skills the CV shows; null while the reader is working (and for a restored profile, which has `cv`) */
  read: CvRead | null;
  /** the skills matched against the market; null while matching */
  cv: CvProfile | null;
  /** play the stages (a fresh read) or show them finished (a restored profile) */
  animate: boolean;
};

/** You, step 1: the CV is read, its skills become stickers, and each skill is checked against the market. Which
 * job to aim for comes later (Your direction), after The Mirror has shown whether the current job is at risk. */

export default function CvFlow({ fileName, lines, read , cv, animate }: Props) {
  const { next } = useJourney();
  const [play, setPlay] = useState(animate);
  const [stage, setStage] = useState(cv && !animate ? 3 : 1);
  const refs = useRef<(HTMLElement | null)[]>([]);
  // the skills to show: from the reader as soon as it answers, before they're matched
  const found = read ?? cv;

  // stage 2 opens when the CV is read; stage 3 once its stickers are in, matching (or matched) by then
  useEffect(() => {
    if (!found) return setStage(1);
    if (!play) return setStage(3);
    setStage(2);
    const timer = setTimeout(() => setStage(3), 900 + stickersOf(found).length * STICKER_GAP);
    return () => clearTimeout(timer);
  }, [found, play]);

  // follow the flow down the page as each stage opens
  useEffect(() => {
    if (play && stage > 1) refs.current[stage - 1]?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [stage, play]);

  const quotes = found?.skills.map((s) => s.quote) ?? [];
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
        {found && (stage < 3 ? (
          <button className="btn btn-ghost btn-sm" onClick={() => setPlay(false)}>Skip</button>
        ) : (
          <button className="btn btn-ghost btn-sm" onClick={() => { setPlay(false); setTimeout(() => setPlay(true)); }}>Replay</button>
        ))}
      </header>

      {/* 1 · read */}
      <div className="flow-stage" ref={(el) => { refs.current[0] = el; }}>
        <StageHead n={1} title="Read your CV" busy={!found}>
          {!found && <>Reading <strong>{fileName}</strong>…</>}
        </StageHead>
        {(lines || !found) && (
          <div className="flow-doc" role="region" aria-label="The text read from your CV" tabIndex={0}>
            <div className="flow-doc-lines">
              {lines
                ? lines.map((line, i) => {
                    const q = stage >= 2 ? quoteIn(line, quotes) : -1;
                    return (
                      <div key={i} className={`flow-line${q >= 0 ? " hit" : ""}`} style={{ "--d": `${Math.max(q, 0) * STICKER_GAP}ms` } as React.CSSProperties}>
                        {line}
                      </div>
                    );
                  })
                : PLACEHOLDER.map((w, i) => <div key={i} className={`flow-bar${w ? "" : " gap"}`} style={{ width: `${w}%` }} aria-hidden />)}
            </div>
            {!found && <div className="scan-beam" />}
          </div>
        )}
        {cv && !lines && (
          <p className="muted small">The text of a CV read in an earlier visit isn&apos;t kept. Upload it again to see it here.</p>
        )}
      </div>

      {/* 2 · skills */}
      {found && stage >= 2 && (
        <div className="flow-stage" ref={(el) => { refs.current[1] = el; }}>
          <StageHead n={2} title="Find your skills" />
          <Stickers cv={found} />
          {/* the job is set on the journey once the profile is saved, after matching */}
          {cv && <CurrentJob cv={cv} />}
        </div>
      )}

      {/* 3 · market: matching, then matched */}
      {found && !cv && stage >= 3 && (
        <div className="flow-stage" ref={(el) => { refs.current[2] = el; }}>
          <StageHead n={3} title="Your skills in the market" busy>
            Matching your {stickersOf(found).filter((g) => !g.tool && (g.skillIds.length || g.untracked.length)).length} skill categories against hiring posts, Malaysian job postings and the ILO&apos;s
            AI exposure scores…
          </StageHead>
          <Matching cv={found} />
        </div>
      )}
      {cv && stage >= 3 && (
        <div className="flow-stage" ref={(el) => { refs.current[2] = el; }}>
          <StageHead n={3} title="Your skills in the market">
            For each skill we check three signals, from weakest to strongest: people talking about it, companies
            abroad hiring for it, and Malaysian employers hiring for it
            {cv.snapshot && <> (data as of <strong>{fmtDate(cv.snapshot.as_of)}</strong>)</>}.
          </StageHead>
          {cv.malaysia_market && <MalaysiaMarket m={cv.malaysia_market} />}
          <Market cv={cv} />
          <NextUp cv={cv} />
        </div>
      )}
    </section>
  );
}

/** The same three stages before any CV is uploaded, with nothing in them yet. */
export function EmptyFlow() {
  return (
    <section className="flow glass static" aria-label="What Kompas shows once your CV is uploaded">
      <header className="flow-head">
        <ol className="flow-steps">
          {STAGES.map((s, i) => (
            <li key={s}>
              <span className="flow-dot">{i + 1}</span>
              {s}
            </li>
          ))}
        </ol>
      </header>

      <div className="flow-stage">
        <StageHead n={1} title="Read your CV" />
        <div className="flow-doc flow-doc-empty">
          <p className="muted">The text of your CV will appear here once you upload it.</p>
        </div>
      </div>

      <div className="flow-stage">
        <StageHead n={2} title="Find your skills" />
        <p className="muted small">The skills Kompas finds in your CV will appear here.</p>
      </div>

      <div className="flow-stage">
        <StageHead n={3} title="Your skills in the market" />
        <p className="muted small">How each of your skills is doing in the job market will appear here.</p>
      </div>
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

/** Stage 3 while matching: each skill's card, being checked. */
function Matching({ cv }: { cv: Pick<CvRead, "skills" | "ai_tools" | "unrecognised" | "groups"> }) {
  // one card per category, the same as the finished view
  const groups = stickersOf(cv).filter((g) => !g.tool && (g.skillIds.length || g.untracked.length));
  return (
    <div className="market-cards" aria-hidden>
      {groups.map((g, i) => (
        <article key={g.name} className="mcard checking" style={{ "--d": `${i * 110}ms` } as React.CSSProperties}>
          <div className="mcard-head">
            <h4>{g.name}</h4>
            <span className="checking-dots"><i /><i /><i /></span>
          </div>
          <span className="sk sk-line" />
          <span className="sk sk-line short" />
        </article>
      ))}
    </div>
  );
}

type Sticker = { name: string; quote: string; skillIds: string[]; untracked: string[]; tool: boolean; labels?: string[] };

/** One entry per broad group of the CV's skills: its name, the one CV line that best shows it, and the tracked
 * skills in it. Profiles saved before the reader grouped skills fall back to their job families. */
export function stickersOf(cv: Pick<CvRead, "skills" | "ai_tools" | "unrecognised" | "groups">): Sticker[] {
  const quote = new Map(cv.skills.map((s) => [s.id, s.quote]));
  const groups = cv.groups?.length ? cv.groups : Object.values(
    [...cv.skills.map((s) => ({ g: s.group ?? s.family?.label ?? "Skills", id: s.id, name: null as string | null })),
     ...cv.unrecognised.map((u) => ({ g: u.group ?? "Other skills", id: null, name: u.name }))]
      .reduce<Record<string, { name: string; skills: string[]; untracked: string[] }>>((acc, x) => {
        const g = (acc[x.g] ??= { name: x.g, skills: [], untracked: [] });
        if (x.id) g.skills.push(x.id);
        else if (x.name) g.untracked.push(x.name);
        return acc;
      }, {}));
  const out: Sticker[] = groups.map((g) => {
    const line = g.skills.map((id) => quote.get(id)).find(Boolean)
      ?? cv.unrecognised.find((u) => g.untracked.includes(u.name))?.quote ?? "";
    return { name: g.name, quote: line, skillIds: g.skills, untracked: g.untracked, tool: false };
  });
  // "capabilities" are tasks in your work that AI can already do (report generation, customer enquiries), found in
  // the CV's wording: not tools you used, and not skills the market scores
  if (cv.ai_tools.length) {
    out.push({ name: "Tasks AI can help with", quote: cv.ai_tools[0].quote, skillIds: cv.ai_tools.map((t) => t.id),
               untracked: [], tool: true, labels: cv.ai_tools.map((t) => t.label) });
  }
  return out.filter((g) => g.quote);
}

function Stickers({ cv }: { cv: Pick<CvRead, "skills" | "ai_tools" | "unrecognised" | "groups"> }) {
  const [open, setOpen] = useState<string | null>(null);
  const all = stickersOf(cv);
  const picked = all.find((g) => g.name === open);
  return (
    <div className="stickers">
      <div className="sticker-tray">
        {all.map((g, i) => (
          <button key={g.name} className={`sticker${g.tool ? " tool" : ""}${open === g.name ? " on" : ""}`}
            style={{ "--d": `${i * STICKER_GAP}ms` } as React.CSSProperties} onClick={() => setOpen(open === g.name ? null : g.name)}>
            <span className="sticker-label">{g.name}</span>
          </button>
        ))}
      </div>
      <p className="sticker-quote">
        {picked?.tool
          ? <>AI can already do: <strong>{picked.labels?.join(", ")}</strong>. From your CV: <q>{picked.quote}</q></>
          : picked ? <>From your CV: <q>{picked.quote}</q></>
          : <span className="muted small">Tap a group to see the line of your CV it came from.</span>}
      </p>
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
      <span className="rung-name">
        {SIGNAL_LABEL[rung.rung]}
        {rung.groups?.length ? (
          <span className="rung-basis">
            Based on all {listWords(rung.groups)} job openings
            {rung.share_pct != null && rung.previous_share_pct != null && rung.previous
              ? `: ${rung.share_pct}% of all openings, ${rung.share_pct > rung.previous_share_pct ? "up from" : rung.share_pct < rung.previous_share_pct ? "down from" : "the same as"} ${rung.previous_share_pct}% in ${quarter(rung.previous).split(" ")[0]}`
              : ""}
          </span>
        ) : null}
      </span>
      <span className="rung-bar"><i /></span>
      <span className="rung-move">{rung.movement === "no data" ? "No data yet" : rung.movement}</span>
    </div>
  );
}

/** "2026Q2" -> "Q2 2026" */
const quarter = (q: string) => `${q.slice(4)} ${q.slice(0, 4)}`;

const pct = (n: number | null) => (n == null ? "" : `${n > 0 ? "+" : n < 0 ? "−" : "±"}${Math.abs(n)}%`);

/** Online job openings in Malaysia for the occupation groups behind your skills, shown once: many skills share a
 *  group, so per-card figures would repeat. It leads with each group's share of all openings, which is what the
 *  cards' "Hired in Malaysia" row follows; the count comes second and neutral, because it can fall in a shrinking
 *  market while the share rises. */
function MalaysiaMarket({ m }: { m: MalaysiaMarket }) {
  const prev = quarter(m.previous).split(" ")[0];
  const dir = (mv: string | undefined) => (mv?.includes("up") ? "up" : mv?.includes("down") ? "down" : "flat");
  return (
    <a className="my-market" href={m.url} target="_blank" rel="noopener noreferrer">
      <span className="mcard-ev-label">Malaysian job market · {quarter(m.quarter)}</span>
      <span className="mcard-ev-meta">
        Share of all job openings posted online, compared with {prev}. A bigger share means more demand than for
        other jobs, even when the whole market shrinks.
      </span>
      <ul>
        {m.groups.map((g) => (
          <li key={g.group}>
            <span className="my-group">{g.group[0].toUpperCase() + g.group.slice(1)} jobs</span>
            <span className={`my-share-now ${dir(g.movement)}`}>
              {g.share_pct}% of all openings{" "}
              {dir(g.movement) === "up" ? "▲" : dir(g.movement) === "down" ? "▼" : "●"}{" "}
              <span className="my-was">{g.share_pct === g.previous_share_pct ? "same as" : dir(g.movement) === "down" || g.share_pct < g.previous_share_pct ? "down from" : "up from"} {g.previous_share_pct}%</span>
            </span>
            <span className="my-count muted">{g.ads.toLocaleString("en-MY")} openings, {pct(g.change_pct)} (all jobs {pct(m.all.change_pct)})</span>
          </li>
        ))}
      </ul>
      <span className="mcard-ev-meta">All jobs: {m.all.ads.toLocaleString("en-MY")} openings in {quarter(m.quarter)}, {pct(m.all.change_pct)} on {prev}</span>
    </a>
  );
}

const MARKET_SHOWN = 6;   // categories shown before "Show more"; the strongest come first

function Market({ cv }: { cv: CvProfile }) {
  const [all, setAll] = useState(false);
  const rank = (id: string) => ORDER[cv.signals[id]?.status ?? ""] ?? 9;
  // one card per broad group: the group's best skill sets its status, meaning, rungs and evidence
  const groups = stickersOf(cv)
    .filter((g) => !g.tool && (g.skillIds.length || g.untracked.length))
    .map((g) => {
      const best = [...g.skillIds].sort((x, y) => rank(x) - rank(y))[0];
      return { ...g, best, sig: best ? cv.signals[best] : undefined, count: g.skillIds.length + g.untracked.length };
    })
    .sort((a, b) => (a.best ? rank(a.best) : 10) - (b.best ? rank(b.best) : 10));
  const hidden = groups.length - MARKET_SHOWN;
  return (
    <>
    <div className="market-cards">
      {(all ? groups : groups.slice(0, MARKET_SHOWN)).map((g, i) => {
        const { sig } = g;
        const top = sig?.evidence[0];
        const label = cv.skills.find((s) => s.id === g.best)?.label ?? g.untracked[0] ?? g.name;
        if (!g.best) {
          return (
            <article key={g.name} className="mcard" style={{ "--d": `${i * 110}ms` } as React.CSSProperties}>
              <header className="mcard-head">
                <h4>{g.name}</h4>
                <span className="muted small">Not measured yet</span>
              </header>
              <p className="muted small">{g.count} {g.count === 1 ? "skill" : "skills"}: {g.untracked.join(", ")}</p>
              <p className="mcard-meaning">
                {cv.esco_down || cv.llm_note?.includes("ESCO")
                  ? "The skills catalogue we match these against is unreachable right now. Kompas tries again the next time you open it."
                  : "These skills aren't in the catalogues Kompas measures yet, so there's no hiring signal to show."}
              </p>
            </article>
          );
        }
        return (
          <article key={g.name} className={`mcard${sig && RISING.includes(sig.status) ? " up" : sig?.status === "Watch" ? " watch" : ""}`} style={{ "--d": `${i * 110}ms` } as React.CSSProperties}>
            <header className="mcard-head">
              <h4>{g.name}</h4>
              {sig ? <span className={signalClass(sig.status)}>{sig.status}</span> : <span className="muted small">No data yet</span>}
            </header>
            <p className="muted small">{g.count} {g.count === 1 ? "skill" : "skills"}, led by {label}</p>
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
    {hidden > 0 && (
      <button type="button" className="btn btn-ghost market-more" onClick={() => setAll(!all)}>
        {all ? "Show fewer categories" : `Show ${hidden} more ${hidden === 1 ? "category" : "categories"}`}
      </button>
    )}
    </>
  );
}

/** Where the skills stand: how many are in demand, gaining attention, steady or falling. */
function NextUp({ cv }: { cv: CvProfile }) {
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
    </div>
  );
}
