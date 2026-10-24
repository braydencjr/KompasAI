"use client";

import Ring from "../Ring";
import { TOOL_LABEL, clock } from "./shared";
import { isAiTask, rating, reviewFor, type Outcome, type Simulation } from "../../data/simulations";

type Props = { sim: Simulation; outcomes: Outcome[]; onRestart: () => void; onClose: () => void };

export default function PerformanceReport({ sim, outcomes, onRestart, onClose }: Props) {
  const can = Math.round((outcomes.reduce((s, o) => s + o.score, 0) / outcomes.length) * 100);
  const r = rating(can);
  const spent = outcomes.reduce((s, o) => s + o.seconds, 0);
  const target = sim.tasks.reduce((s, t) => s + t.minutes * 60, 0);
  const manager = sim.tasks[0].from;
  const tracks = (["core", "ai"] as const).map((track) => {
    const idx = sim.tasks.map((t, i) => (isAiTask(t) === (track === "ai") ? i : -1)).filter((i) => i >= 0);
    const score = idx.length ? Math.round((idx.reduce((s, i) => s + outcomes[i].score, 0) / idx.length) * 100) : 0;
    return { track, idx, score, title: track === "core" ? "Core work" : "✦ AI fluency" };
  }).filter((t) => t.idx.length > 0);

  const ranked = outcomes.map((o, i) => ({ o, t: sim.tasks[i] })).sort((a, b) => b.o.score - a.o.score);
  const best = ranked[0];
  const growth = ranked.filter((x) => x.o.score < 0.8).reverse();

  return (
    <div className="report">
      <section className="report-top">
        <div>
          <span className="label">{sim.aiOnly ? "Your work with AI" : "Performance report · Day 1"} · Reviewed by {manager}</span>
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
                    ⏱ {clock(o.seconds)} (target ~{t.minutes} min)
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
