"use client";

import { useEffect, useState } from "react";
import type { Role } from "../data/bets";

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

export function SkillColumns({ role, gapClosed }: { role: Role; gapClosed: (gap: string) => boolean }) {
  return (
    <div className="plan-skills">
      <div>
        <div className="label">Skills you have · {role.have.length}</div>
        <div className="chips">
          {role.have.map((s) => (
            <span key={s} className="chip chip-have">✓ {s}</span>
          ))}
        </div>
      </div>
      <div>
        <div className="label">Skill gaps · {role.gaps.length}</div>
        <div className="chips">
          {role.gaps.map((g) => (
            <span key={g} className={`chip chip-gap${gapClosed(g) ? " closed" : ""}`}>
              {gapClosed(g) ? "✓" : "+"} {g}
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
          <li key={s.url + s.title} className={`track-step${done[i] ? " done" : ""}`}>
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
                <span className={`signal-pill signal-${s.signal.replace(" ", "-").toLowerCase()}`}>{s.signal}</span>
              </div>
              <h4>{s.title}</h4>
              <div className="muted small">{s.provider}</div>
              <p className="track-why">{s.why}</p>
              <div className="track-foot">
                <span className="meta">{s.hours} h · {s.cost}</span>
                <a href={s.url} target="_blank" rel="noopener noreferrer" className="btn btn-primary btn-sm">
                  Learn ↗
                </a>
              </div>
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}
