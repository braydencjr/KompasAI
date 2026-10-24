"use client";

import { useEffect, useState } from "react";
import type { Role } from "../data/bets";
import { SdgTags } from "./Sdg";
import { GapSignal, SignalPill } from "./Signals";

const HOURS_PER_WEEK = 5;

export function useStepProgress(role: Role) {
  const storageKey = `kompas:roadmap:${role.id}`;
  const [done, setDone] = useState<boolean[]>(() => role.steps.map(() => false));

  useEffect(() => {
    let next = role.steps.map(() => false);
    try {
      const saved = JSON.parse(localStorage.getItem(storageKey) ?? "null");
      if (Array.isArray(saved) && saved.length === role.steps.length) next = saved;
    } catch {}
    setDone(next);
  }, [storageKey, role.steps]);

  function toggle(i: number) {
    const next = done.map((d, n) => (n === i ? !d : d));
    setDone(next);
    try {
      localStorage.setItem(storageKey, JSON.stringify(next));
    } catch {}
  }

  const gapClosed = (gap: string) => {
    const idx = role.steps.flatMap((s, i) => (s.skill === gap ? [i] : []));
    return idx.length > 0 && idx.every((i) => done[i]);
  };

  return { done, toggle, gapClosed };
}

type SkillColumnsProps = {
  role: Role;
  gapClosed: (gap: string) => boolean;
  /** skill -> the resume line it came from, shown on hover */
  quotes?: Record<string, string>;
  onRemove?: (skill: string) => void;
  haveLabel?: string;
};

export function SkillColumns({ role, gapClosed, quotes, onRemove, haveLabel = "Skills you have" }: SkillColumnsProps) {
  return (
    <div className="plan-skills">
      <div>
        <div className="label">{haveLabel} · {role.have.length}</div>
        <div className="chips">
          {role.have.map((s, i) => (
            <span key={s} className={`chip chip-have${quotes ? " pop" : ""}`} style={{ "--i": i } as React.CSSProperties}
              title={quotes?.[s] ? `From your resume: “${quotes[s]}”` : undefined}>
              ✓ {s}
              {role.skillMeta?.[s] && <SdgTags kind="skill" id={role.skillMeta[s].id} tags={role.skillMeta[s].sdgs} subject={s} />}
              {onRemove && (
                <button className="chip-x" aria-label={`Remove ${s}`} onClick={() => onRemove(s)}>×</button>
              )}
            </span>
          ))}
        </div>
      </div>
      <div>
        <div className="label">Skill gaps · {role.gaps.length}</div>
        {role.gaps.length === 0 && (
          <p className="muted small">None. You have every skill Kompas tracks for this role.</p>
        )}
        <div className="chips">
          {role.gaps.map((g) => (
            <span key={g} className={`chip chip-gap${gapClosed(g) ? " closed" : ""}`}>
              {gapClosed(g) ? "✓" : "+"} {g}
              <GapSignal skill={g} />
              {role.skillMeta?.[g] && <SdgTags kind="skill" id={role.skillMeta[g].id} tags={role.skillMeta[g].sdgs} subject={g} />}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}

type RoadmapProps = {
  role: Role;
  done: boolean[];
  toggle: (i: number) => void;
  vertical?: boolean;
};

export default function Roadmap({ role, done, toggle, vertical = false }: RoadmapProps) {
  const totalHours = role.steps.reduce((h, s) => h + s.hours, 0);
  const completed = done.filter(Boolean).length;

  return (
    <div className="plan-road">
      <div className="plan-road-head">
        <div className="label">
          Roadmap · {role.steps.length} steps · {totalHours} h · ~{Math.ceil(totalHours / HOURS_PER_WEEK)} weeks at {HOURS_PER_WEEK} h/week
        </div>
        <div className="plan-progress">
          <span className="muted small">{completed}/{role.steps.length} done</span>
          <div className="progress">
            <div className="progress-fill" style={{ width: `${(completed / role.steps.length) * 100}%` }} />
          </div>
        </div>
      </div>

      <ol className={`track${vertical ? " track-vertical" : ""}`}>
        {role.steps.map((s, i) => (
          <li key={`${s.skill}|${s.url}|${s.title}`} className={`track-step${done[i] ? " done" : ""}`}>
            <button
              className="step-node"
              onClick={() => toggle(i)}
              aria-label={`${done[i] ? "Unmark" : "Mark"} step ${i + 1} as done`}
            >
              {done[i] ? "✓" : i + 1}
            </button>
            <div className="track-card">
              <div className="track-top">
                <span className="track-skill">{s.skill}</span>
                <SignalPill skill={s.skill} fallback={s.signal} />
              </div>
              <h4>{s.title}</h4>
              <div className="muted small">{s.provider}</div>
              <p className="track-why">{s.why}</p>
              <div className="track-foot">
                <span className="meta">{s.url ? `${s.hours} h · ${s.cost}` : "No verified course"}</span>
                {s.url && (
                  <a href={s.url} target="_blank" rel="noopener noreferrer" className="btn btn-primary btn-sm">
                    Learn ↗
                  </a>
                )}
              </div>
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}
