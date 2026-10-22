"use client";

import Ring from "../Ring";
import { FEELINGS, TOOL_LABEL, clock } from "./shared";
import { isAiTask, quadrantOf, reviewFor, type Outcome, type Simulation } from "../../data/simulations";

type Props = { sim: Simulation; outcomes: Outcome[]; onRestart: () => void; onClose: () => void };

function rating(score: number) {
  if (score >= 85) return { label: "Exceeds expectations", tone: "great" };
  if (score >= 65) return { label: "Meets expectations", tone: "good" };
  if (score >= 40) return { label: "Developing", tone: "mid" };
  return { label: "Not yet ready", tone: "low" };
}

const FIT_NOTE = {
  "Strong fit": "You did the work well and enjoyed it. This route is worth backing.",
  "Capable, may burn out":
    "You can do this work, but it didn't energise you. Compare it with your other bets before committing.",
  Learnable: "You enjoyed the work. The skills gap is exactly what your roadmap closes.",
  "Probably not for you": "Neither the work nor the feeling clicked. Better to learn that now than six months in.",
};

export default function PerformanceReport({ sim, outcomes, onRestart, onClose }: Props) {
  const can = Math.round((outcomes.reduce((s, o) => s + o.score, 0) / outcomes.length) * 100);
  const want = Math.round((outcomes.reduce((s, o) => s + o.enjoy, 0) / (outcomes.length * 2)) * 100);
  const fit = quadrantOf(can, want);
  const r = rating(can);
  const spent = outcomes.reduce((s, o) => s + o.seconds, 0);
  const target = sim.tasks.reduce((s, t) => s + t.minutes * 60, 0);
  const manager = sim.tasks[0].from;
  const tracks = (["core", "ai"] as const).map((track) => {
    const idx = sim.tasks.map((t, i) => (isAiTask(t) === (track === "ai") ? i : -1)).filter((i) => i >= 0);
    const score = idx.length ? Math.round((idx.reduce((s, i) => s + outcomes[i].score, 0) / idx.length) * 100) : 0;
    return { track, idx, score, title: track === "core" ? "Core work" : "✦ AI fluency" };
  });

  const ranked = outcomes.map((o, i) => ({ o, t: sim.tasks[i] })).sort((a, b) => b.o.score - a.o.score);
  const best = ranked[0];
  const growth = ranked.filter((x) => x.o.score < 0.8).reverse();

  return (
    <div className="report">
      <section className="report-top">
        <div>
          <span className="label">Performance report · Day 1 · Reviewed by {manager}</span>
          <h3 className={`report-rating tone-${r.tone}`}>{r.label}</h3>
          <p className="muted">
            {sim.title} · {outcomes.length} tasks · {clock(spent)} on task ({spent <= target ? "within" : "over"} the ~
            {Math.round(target / 60)} min a new hire would take)
          </p>
        </div>
        <div className="report-scores">
          <div className="report-score">
            <Ring value={can} size={84} stroke={6} />
            <span className="label">Overall</span>
          </div>
          {tracks.map((t) => (
            <div key={t.track} className="report-score small">
              <Ring value={t.score} size={60} stroke={4} />
              <span className="label">{t.title}</span>
            </div>
          ))}
        </div>
      </section>

      {tracks.map((track) => (
        <section key={track.track}>
          <div className="report-section-head">
            <div className="label">{track.title}</div>
            <span className="muted small">
              {track.track === "core"
                ? "The job as it's done today"
                : "How the job is changing: directing and checking AI tools"}{" "}
              · <strong>{track.score}%</strong>
            </span>
          </div>
          <ul className="report-rows">
            {track.idx.map((i) => {
              const t = sim.tasks[i];
              const o = outcomes[i];
              const pct = Math.round(o.score * 100);
              return (
                <li key={t.id} className="report-row">
                  <div className="report-row-head">
                    <div>
                      <strong>{t.competency}</strong>
                      <span className="muted small">
                        {t.title} · {TOOL_LABEL[t.tool]}
                      </span>
                    </div>
                    <span className="report-pct">{pct}%</span>
                  </div>
                  <div className="report-bar">
                    <span style={{ width: `${pct}%` }} className={pct >= 80 ? "hi" : pct >= 50 ? "mid" : "lo"} />
                  </div>
                  <div className="report-meta muted small">
                    ⏱ {clock(o.seconds)} (target ~{t.minutes} min) · Felt: {FEELINGS[o.enjoy]}
                  </div>
                  <ul className="report-evidence">
                    {o.evidence.map((e) => (
                      <li key={e}>{e}</li>
                    ))}
                  </ul>
                  <blockquote className="report-quote">
                    “{reviewFor(t, o.score)}”{" "}
                    <cite>
                      {t.from}, {t.fromRole}
                    </cite>
                  </blockquote>
                </li>
              );
            })}
          </ul>
        </section>
      ))}

      <section className="report-cols">
        <div className="report-card">
          <div className="label">Strongest</div>
          <strong>{best.t.competency}</strong>
          <p className="muted small">
            Scored {Math.round(best.o.score * 100)}% on “{best.t.title}”. Mention this in interviews.
          </p>
        </div>
        <div className="report-card">
          <div className="label">To develop</div>
          {growth.length ? (
            growth.map(({ t }) => (
              <p key={t.id} className="small">
                <strong>{t.competency}</strong>
                {t.gap ? (
                  <>
                    {" "}
                    · your roadmap&apos;s <strong>{t.gap}</strong> step builds this
                  </>
                ) : (
                  <> · practise this on the job</>
                )}
              </p>
            ))
          ) : (
            <p className="muted small">Nothing below 80%. You&apos;re ready for this kind of work.</p>
          )}
        </div>
      </section>

      <section className="report-fit">
        <div className="sim-quadrant" aria-label={`Can do ${can}%, want to do ${want}%`}>
          <span className="q q-tl">Capable, may burn out</span>
          <span className="q q-tr">Strong fit</span>
          <span className="q q-bl">Probably not for you</span>
          <span className="q q-br">Learnable</span>
          <span className="sim-dot" style={{ left: `${want}%`, bottom: `${can}%` }} />
          <span className="axis axis-x">Want to do →</span>
          <span className="axis axis-y">Can do →</span>
        </div>
        <div>
          <div className="label">Career fit</div>
          <h4 className="report-fit-title">{fit}</h4>
          <p className="muted small">{FIT_NOTE[fit]}</p>
          <div className="report-fit-stats">
            <span>
              Can do <strong>{can}%</strong>
            </span>
            <span>
              Want to do <strong>{want}%</strong>
            </span>
          </div>
        </div>
      </section>

      <p className="muted small">
        Scored automatically against the task brief. Fictional scenario for practice, not an assessment of record.
      </p>

      <div className="sim-actions">
        <button className="btn btn-ghost" onClick={onRestart}>
          Try again
        </button>
        <button className="btn btn-primary" onClick={onClose}>
          Back to Kompas
        </button>
      </div>
    </div>
  );
}
