"use client";

import { useEffect, useRef, useState } from "react";
import type { Ghost, GhostLine, Horizon, Mirror, Pile, TaskCard } from "../../lib/journey";
import { useProfile } from "../Profile";
import { useJourney } from "./JourneyProvider";
import { ScenarioToggle, useLadder } from "./shared";

/* AI Exposure: is your job safe (the verdict), what your CV is worth (the paper), and the tasks behind both.
   One step for what used to be The Mirror and the Ghost CV: they read the same AI signals, as tasks and as skills. */

type Group = Horizon | "never";

const GROUPS: { id: Group; title: string; sub: string }[] = [
  { id: "now", title: "AI can do this today", sub: "Generative AI could already do much of this." },
  { id: "moderate", title: "Likely by 2028", sub: "AI that does this is spreading." },
  { id: "fast", title: "Only if AI moves fast", sub: "AI does this at a basic level today. If progress speeds up, it could take it over." },
  { id: "never", title: "Still needs you", sub: "AI can do little of this, even if it moves fast." },
];

const HORIZONS: { id: Horizon; label: string }[] = [
  { id: "now", label: "Today" },
  { id: "moderate", label: "By 2028" },
  { id: "fast", label: "If AI moves fast" },
];

// a status, in words: for AI capabilities (how far along they are) and for skills (demand)
const CAP_PLAIN: Record<string, string> = {
  "Act now": "in wide use", Emerging: "spreading", Watch: "early days", Stable: "basic level", Declining: "fading", Stalled: "stalled",
};
const SKILL_PLAIN: Record<string, string> = {
  "Act now": "in demand", Emerging: "growing", Watch: "early buzz", Stable: "steady", Declining: "falling", Stalled: "stalled",
};

// the paper's choreography (ms): after a pause, each change is drawn in turn
const PAUSE = 1100;
const STEP = 380;
const TYPE_SPEED = 45;
const MAX_SLOTS = 3;

const sentence = (s: string) => s.charAt(0).toUpperCase() + s.slice(1).replace(/\.?$/, ".");

/** The user's call wins: a task they moved sits where they put it. */
const groupOf = (c: TaskCard): Group => (c.override ? (c.override.pile === "exposed" ? "now" : "never") : c.when);

/** Read from the "By 2028" share. The numbers sit in the horizon boxes beside it, so the text only gives the advice. */
function verdict(m: Mirror) {
  if (m.shares.moderate >= 50) {
    return { level: "high", title: "Much of your job is at risk", body: "It's worth looking at jobs that use your skills with less exposure." };
  }
  if (m.shares.moderate >= 25) {
    return { level: "medium", title: "Parts of your job are changing", body: "Staying is realistic if you lean into the tasks that still need you." };
  }
  return { level: "low", title: "Your job looks fairly safe", body: "No need to switch. Adding a rising skill keeps you ahead." };
}

/** Text typed onto the page, a character at a time, after `delay`. */
function Typed({ text, delay }: { text: string; delay: number }) {
  const [n, setN] = useState(0);
  useEffect(() => {
    setN(0);
    let timer: ReturnType<typeof setInterval> | undefined;
    const start = setTimeout(() => {
      timer = setInterval(() => setN((i) => {
        if (i + 1 >= text.length && timer) clearInterval(timer);
        return Math.min(i + 1, text.length);
      }), TYPE_SPEED);
    }, delay);
    return () => {
      clearTimeout(start);
      if (timer) clearInterval(timer);
    };
  }, [text, delay]);
  return (
    <span className="cvp-typed">
      {text.slice(0, n)}
      <span className={`cvp-caret${n >= text.length ? " done" : ""}`} aria-hidden />
      <span className="sr-only">{text}</span>
    </span>
  );
}

/** Your CV at the horizon, edited in place: highlighted, tagged, struck through, new skills typed in. */
function Paper({ g, job, onTasks }: { g: Ghost; job: string; onTasks: (capabilities: string[]) => void }) {
  const { scenario } = useJourney();
  const profile = useProfile();
  const openLadder = useLadder();
  const cv = profile.source === "cv" ? profile.cv : null;
  const headline = cv?.jobs[0]?.title ?? (profile.source === "cv" ? "Your CV" : "Aisyah");

  const of = (t: GhostLine["trend"]) => g.lines.filter((l) => (l.trend ?? "hold") === t);
  const [up, ai, hold, fade] = [of("up"), of("ai"), of("hold"), of("fade")];
  const changes = [...up, ...ai, ...fade];
  const at = (i: number) => PAUSE + i * STEP;
  const slots = g.slots.slice(0, MAX_SLOTS);

  return (
    // keyed on the scenario: switching the pace redraws the changes
    <article key={scenario} className={`cvp ${scenario}`} aria-label={`Your CV as employers may read it in ${g.horizon}`}>
      <div className="j-paper-watermark" aria-hidden>{g.horizon}</div>

      <header className="cvp-head">
        <h2 className="cvp-name">{headline}</h2>
        <p className="cvp-role">{job} · as employers may read it in {g.horizon}</p>
      </header>

      {/* profile and experience only make it read like a CV: kept short, the skills are the point */}
      {cv?.summary && (
        <section className="cvp-section cvp-minor">
          <h3>Profile</h3>
          <p className="cvp-text">{cv.summary.match(/^.*?[.!?](\s|$)/)?.[0].trim() ?? cv.summary}</p>
        </section>
      )}
      {cv && cv.jobs.length > 0 && (
        <section className="cvp-section cvp-minor">
          <h3>Experience</h3>
          <ul className="cvp-jobs">
            {cv.jobs.slice(0, 2).map((j) => (
              <li key={j.quote}>
                <span className="cvp-job-title">{j.title}</span>
                {j.employer && <span className="cvp-job-org">, {j.employer}</span>}
                {j.period && <span className="cvp-job-period">{j.period}</span>}
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="cvp-section">
        <h3>Skills</h3>
        <ul className="cvp-skills">
          {[...up, ...ai, ...hold, ...fade].map((l) => {
            const i = changes.indexOf(l);
            const t = l.trend ?? "hold";
            return (
              <li key={l.id} className={`cvp-skill ${t}`} style={{ "--d": `${i >= 0 ? at(i) : 0}ms` } as React.CSSProperties}>
                <button onClick={() => openLadder(l.id)}
                  title={l.why ? `${l.label}: ${l.why}` : `${l.label}: ${SKILL_PLAIN[l.status_now] ?? l.status_now} now, ${SKILL_PLAIN[l.status] ?? l.status} by ${g.horizon}. See the evidence.`}>
                  <span className="cvp-skill-text">{l.label}</span>
                </button>
                {t === "up" && <span className="cvp-tag up">↑ worth more · {SKILL_PLAIN[l.status] ?? l.status}</span>}
                {t === "fade" && <span className="cvp-tag fade">↓ fading</span>}
                {t === "ai" && (
                  <button className="cvp-tag ai" onClick={() => onTasks((l.ai ?? []).map((a) => a.id))}
                    title={`${(l.ai ?? []).map((a) => `${a.label}: ${a.why}`).join("\n")}\nClick to see the tasks it covers.`}>
                    ⚠ AI can take over
                  </button>
                )}
              </li>
            );
          })}
          {/* skills on the CV that no catalogue could match yet: still on the CV, just not measured */}
          {(cv?.unrecognised ?? []).map((u) => (
            <li key={`u:${u.name}`} className="cvp-skill unmeasured">
              <span className="cvp-skill-text" title={`${u.name}: from your CV, but not in the skills catalogues Kompas measures, so there's no 2028 outlook for it yet.`}>{u.name}</span>
              <span className="cvp-tag unmeasured">not measured yet</span>
            </li>
          ))}
        </ul>
      </section>

      {slots.length > 0 && (
        <section className="cvp-section cvp-ghost">
          <h3>To add by {g.horizon}</h3>
          <ul className="cvp-slots">
            {slots.map((s, i) => (
              <li key={s.id} className={`cvp-slot ${s.state}`} style={{ "--d": `${at(changes.length + i)}ms` } as React.CSSProperties}>
                <button onClick={() => openLadder(s.id)} title="See the evidence">
                  {s.state === "filled" ? <span className="cvp-skill-text">{s.label}</span> : <Typed text={s.label} delay={at(changes.length + i)} />}
                </button>
                <span className="cvp-tag new">{s.state === "filled" ? "✓ learned on your route" : `${s.why} · ${SKILL_PLAIN[s.status] ?? s.status}`}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <p className="cvp-foot">Estimates from today&apos;s signals, not predictions. Tap any skill to see the evidence behind it.</p>
    </article>
  );
}

function TaskCardView({ card, index, focused, arrived, onMove, onUndo }: {
  card: TaskCard;
  index: number;
  focused: boolean;
  arrived: boolean;
  onMove: (reason: string) => void;
  onUndo: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [reason, setReason] = useState("");
  const openLadder = useLadder();
  const target: Pile = card.pile === "exposed" ? "human" : "exposed";
  const cap = [...card.capabilities].sort((a, b) => b.score - a.score)[0];

  return (
    <li className={`mr-card${arrived ? " arrived" : ""}${focused ? " focused" : ""}${card.override ? " overridden" : ""}`}
      style={{ "--d": `${index * 60}ms` } as React.CSSProperties}>
      <h4>{sentence(card.task).slice(0, -1)}</h4>
      {!card.override && <p className="mr-why">{card.reason}</p>}
      {cap && !card.override && (
        <>
          <button className="mr-cap" onClick={() => openLadder(cap.id)} title="See the evidence for this AI">
            <span>AI: {cap.label}</span>
            <em>{CAP_PLAIN[cap.status_now] ?? cap.status_now}</em>
          </button>
        </>
      )}
      {card.override && (
        <p className="mr-why">
          You moved this: &ldquo;{card.override.reason}&rdquo; <button className="link" onClick={onUndo}>Undo</button>
        </p>
      )}
      {editing ? (
        <form className="j-move-form" onSubmit={(e) => {
          e.preventDefault();
          if (reason.trim().length < 3) return;
          onMove(reason.trim());
          setEditing(false);
          setReason("");
        }}>
          <input autoFocus value={reason} onChange={(e) => setReason(e.target.value)} maxLength={160}
            placeholder={target === "human" ? "Why does this still need you?" : "Why could AI do this?"} />
          <button className="btn btn-primary btn-sm" disabled={reason.trim().length < 3}>Move</button>
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => setEditing(false)}>Cancel</button>
        </form>
      ) : (
        !card.override && (
          <button className="mr-move" onClick={() => setEditing(true)}>
            {target === "human" ? "Disagree? This still needs me" : "Disagree? AI could do this"}
          </button>
        )
      )}
    </li>
  );
}

export default function StepFuture() {
  const { data, occupation, catalog, set, move, undoMove } = useJourney();
  const profile = useProfile();
  const [arrived, setArrived] = useState<string | null>(null);
  const [focus, setFocus] = useState<string[] | null>(null);
  const tasksRef = useRef<HTMLElement>(null);

  useEffect(() => {
    if (!arrived) return;
    const t = setTimeout(() => setArrived(null), 900);
    return () => clearTimeout(t);
  }, [arrived]);

  const m = data?.mirror;
  const g = data?.ghost;
  if (!occupation) {
    return (
      <section className="j-empty glass">
        <p>Choose your current job first, so Kompas can look at its tasks.</p>
        <select value="" onChange={(e) => set({ occupation: e.target.value || null })}>
          <option value="">Choose your job…</option>
          {catalog?.occupations.map((o) => <option key={o.isco} value={o.isco}>{o.title}</option>)}
        </select>
      </section>
    );
  }
  if (!m || !g) return <div className="j-loading glass"><span className="sk sk-title" /><span className="sk sk-tile" /></div>;

  const v = verdict(m);
  // your skills that the AI behind the exposed tasks overlaps with (from the CV)
  const touched = [...new Set((profile.cv?.exposed ?? [])
    .filter((e) => m.exposed_capabilities.includes(e.id))
    .flatMap((e) => e.because.map((b) => b.skill)))];
  const isFocused = (c: TaskCard) => !!focus && c.capabilities.some((cap) => focus.includes(cap.id));
  const doMove = (card: TaskCard, reason: string) => {
    move(card.id, card.pile === "exposed" ? "human" : "exposed", reason);
    setArrived(card.id);
  };
  const showTasks = (capabilities: string[]) => {
    setFocus(capabilities);
    setTimeout(() => tasksRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }));
  };

  return (
    <div className="mr">
      {/* 1 · is your job safe? */}
      <section className={`mr-verdict glass ${v.level}`}>
        <div className="mr-verdict-text">
          <h2>{v.title}</h2>
          <p>{v.body}</p>
          {touched.length > 0 && (
            <p className="mr-touched">
              The AI behind these tasks overlaps with your skills: <strong>{touched.join(", ")}</strong>.
            </p>
          )}
        </div>
        <div className="mr-horizons">
          {HORIZONS.map((h) => (
            <div key={h.id} className={`mr-horizon ${h.id}`}>
              <span className="mr-h-label">{h.label}</span>
              <span className="mr-h-num">{m.shares[h.id]}%</span>
              <span className="mr-h-bar"><i style={{ width: `${m.shares[h.id]}%` }} /></span>
              <span className="mr-h-sub">of your tasks AI could do</span>
            </div>
          ))}
        </div>
        <p className="mr-note">
          Estimates, not predictions: based on research into what AI can do in each task, and on how fast AI tools
          are spreading today. &ldquo;By 2028&rdquo; assumes AI keeps its current pace. Disagree with a task? Move it
          below: your call counts in every step after this.
        </p>
      </section>

      {/* 2 · what your CV is worth */}
      <section className="fx-cv">
        <header className="fx-head">
          <div>
            <h3>Your skills outlook for {g.horizon}</h3>
            <p className="muted">Which skills gain value, which AI can take over, and what to add.</p>
          </div>
          <ScenarioToggle />
        </header>
        <Paper g={g} job={m.title ?? ""} onTasks={showTasks} />
      </section>

      {/* 3 · the tasks behind it */}
      <section className="fx-tasks" ref={tasksRef}>
        <header className="fx-head">
          <div>
            <h3>The tasks behind it</h3>
            <p className="muted">Every task in your job, by when AI can do it.</p>
          </div>
          {focus && <button className="btn btn-ghost btn-sm" onClick={() => setFocus(null)}>Show all tasks</button>}
        </header>
        {GROUPS.map((grp) => {
          const cards = m.cards.filter((c) => groupOf(c) === grp.id);
          if (cards.length === 0) return null;
          const hasFocus = cards.some(isFocused);
          if (focus && !hasFocus) return null;
          return (
            <section key={grp.id} className={`mr-group ${grp.id}`}>
              <header>
                <h3>{grp.title} <span className="mr-count">{cards.length}</span></h3>
                <p className="muted">{grp.sub}</p>
              </header>
              <ul className="mr-cards">
                {cards.filter((c) => !focus || isFocused(c)).map((c, i) => (
                  <TaskCardView key={c.id} card={c} index={i} focused={isFocused(c)} arrived={arrived === c.id}
                    onMove={(r) => doMove(c, r)} onUndo={() => undoMove(c.id)} />
                ))}
              </ul>
            </section>
          );
        })}
      </section>
    </div>
  );
}
