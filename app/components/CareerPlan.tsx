"use client";

import { useEffect, useRef, useState } from "react";
import Ring from "./Ring";
import type { Bet } from "../data/bets";

const HOURS_PER_WEEK = 5;

function useStepProgress(bet: Bet) {
  const storageKey = `kompas:roadmap:${bet.id}`;
  const [done, setDone] = useState<boolean[]>(() => bet.steps.map(() => false));

  useEffect(() => {
    let next = bet.steps.map(() => false);
    try {
      const saved = JSON.parse(localStorage.getItem(storageKey) ?? "null");
      if (Array.isArray(saved) && saved.length === bet.steps.length) next = saved;
    } catch {}
    setDone(next);
  }, [storageKey, bet.steps]);

  function toggle(i: number) {
    const next = done.map((d, n) => (n === i ? !d : d));
    setDone(next);
    try {
      localStorage.setItem(storageKey, JSON.stringify(next));
    } catch {}
  }

  return { done, toggle };
}

export default function CareerPlan({ bets }: { bets: Bet[] }) {
  const [selectedId, setSelectedId] = useState(bets[0].id);
  const planRef = useRef<HTMLElement>(null);
  const bet = bets.find((b) => b.id === selectedId) ?? bets[0];
  const { done, toggle } = useStepProgress(bet);

  const totalHours = bet.steps.reduce((h, s) => h + s.hours, 0);
  const completed = done.filter(Boolean).length;
  const gapClosed = (gap: string) => {
    const idx = bet.steps.flatMap((s, i) => (s.skill === gap ? [i] : []));
    return idx.length > 0 && idx.every((i) => done[i]);
  };

  function select(id: string) {
    setSelectedId(id);
    planRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  return (
    <>
      <section id="plan" ref={planRef} className="plan glass">
        <div key={bet.id} className="plan-inner">
          <header className="plan-head">
            <div className="plan-title">
              <div className="plan-tags">
                <span className="label">01 — {bet.id === bets[0].id ? "Best fit for you" : "Selected path"}</span>
                <span className="chip chip-blue">{bet.kind}</span>
                <span className="chip chip-blue">{bet.sdg.goal}</span>
              </div>
              <h2>{bet.title}</h2>
              <p className="muted">{bet.summary}</p>
            </div>
            <div className="plan-score">
              <Ring value={bet.match} size={84} stroke={6} />
              <div>
                <div className="profile-stat-title">Skill match</div>
                <div className="muted small">{bet.signal} demand · estimate</div>
              </div>
            </div>
          </header>

          <div className="plan-skills">
            <div>
              <div className="label">Skills you have · {bet.have.length}</div>
              <div className="chips">
                {bet.have.map((s) => (
                  <span key={s} className="chip chip-have">✓ {s}</span>
                ))}
              </div>
            </div>
            <div>
              <div className="label">Skill gaps · {bet.gaps.length}</div>
              <div className="chips">
                {bet.gaps.map((g) => (
                  <span key={g} className={`chip chip-gap${gapClosed(g) ? " closed" : ""}`}>
                    {gapClosed(g) ? "✓" : "+"} {g}
                  </span>
                ))}
              </div>
            </div>
          </div>

          <div className="plan-road">
            <div className="plan-road-head">
              <div className="label">
                Roadmap · {bet.steps.length} steps · {totalHours} h · ~{Math.ceil(totalHours / HOURS_PER_WEEK)} weeks at {HOURS_PER_WEEK} h/week
              </div>
              <div className="plan-progress">
                <span className="muted small">{completed}/{bet.steps.length} done</span>
                <div className="progress">
                  <div className="progress-fill" style={{ width: `${(completed / bet.steps.length) * 100}%` }} />
                </div>
              </div>
            </div>

            <ol className="track">
              {bet.steps.map((s, i) => (
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
        </div>
      </section>

      <section>
        <div className="section-head">
          <div>
            <span className="kicker">02 — Futures</span>
            <h2>Your three bets</h2>
            <p className="muted small">Three different futures. Pick one to see its roadmap above.</p>
          </div>
          <span className="muted small">Moderate scenario</span>
        </div>

        <div className="bets">
          {bets.map((b) => {
            const active = b.id === bet.id;
            return (
              <article key={b.id} className={`bet glass${active ? " bet-active" : ""}`}>
                <div className="bet-head">
                  <span className="bet-kind">{b.kind}</span>
                  <span className="chip chip-blue">{b.sdg.goal}</span>
                </div>

                <div className="bet-title">
                  <div>
                    <h3>{b.title}</h3>
                    <p className="muted small">{b.note}</p>
                  </div>
                  <Ring value={b.match} size={58} stroke={4} />
                </div>

                <div className="bet-signal">
                  <span className="dot" /> {b.signal}
                  <span className="muted small">· {b.steps.reduce((h, s) => h + s.hours, 0)} h of learning</span>
                </div>

                <div className="gaps">
                  <div className="label">Skill gaps to close</div>
                  <ol className="gap-list">
                    {b.gaps.map((g, n) => (
                      <li key={g}>
                        <span className="gap-num">{n + 1}</span>
                        {g}
                      </li>
                    ))}
                  </ol>
                </div>

                <button
                  onClick={() => select(b.id)}
                  className={`btn ${active ? "btn-primary" : "btn-ghost"} btn-block`}
                  aria-pressed={active}
                >
                  {active ? "Viewing roadmap ↑" : "View roadmap ↑"}
                </button>
              </article>
            );
          })}
        </div>
      </section>
    </>
  );
}
