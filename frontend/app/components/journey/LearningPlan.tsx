"use client";

import { rating } from "../../data/simulations";
import { useState } from "react";
import { signalClass } from "../Signals";
import { useSim, type SimRole } from "../SimulatorProvider";
import PracticeModal from "./PracticeModal";
import type { LearningPlan as Plan } from "../../lib/journey";

type Props = {
  plan: Plan;
  completed: string[];
  onToggle: (id: string) => void;
  /** the job, for the final project: a day of its work, two core tasks and two with its field's AI tools */
  capstone: SimRole | null;
};

function Icon({ d }: { d: string }) {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d={d} />
    </svg>
  );
}

const ICON = {
  learn: "M4 5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2zM4 21V5M8 7h7M8 11h5",
  courses: "M2 9l10-5 10 5-10 5zM6 11v5c0 1.5 3 3 6 3s6-1.5 6-3v-5",
  project: "M14.7 6.3a4 4 0 0 0-5.4 5.4L3 18l3 3 6.3-6.3a4 4 0 0 0 5.4-5.4l-2.5 2.5-2.4-.6-.6-2.4z",
  star: "M12 3l2.6 5.6 6.1.7-4.5 4.2 1.2 6L12 16.6 6.6 19.5l1.2-6L3.3 9.3l6.1-.7z",
  flag: "M5 21V4M5 4h11l-2 4 2 4H5",
};

/** The Route as an AI learning plan, drawn as a path: today, one stop per skill, then the job. Each stop says what
 * to learn (left) and which courses teach it (right), then a mini project that proves it. The stops and their order
 * come from Kompas's route; the advice is Gemini's; every course is a Coursera catalogue entry. */
export default function LearningPlan({ plan, completed, onToggle, capstone }: Props) {
  const [practising, setPractising] = useState<Plan["steps"][number] | null>(null);
  const sim = useSim();
  const markDone = (id: string) => !completed.includes(id) && onToggle(id);
  const capstoneId = capstone ? `route-${capstone.id}` : null;
  const finalResult = capstoneId ? sim.results[capstoneId] : undefined;
  const done = plan.steps.filter((s) => completed.includes(s.id)).length;
  const weeksLeft = plan.steps.filter((s) => !completed.includes(s.id)).reduce((t, s) => t + s.weeks, 0);

  return (
    <div className="lp">
      <div className="lp-head">
        <span className="lp-badge">✦ AI learning plan</span>
        <span className="muted small">
          {plan.steps.length} stops · ~{weeksLeft} week{weeksLeft === 1 ? "" : "s"} to go at 5 h a week · {done} of {plan.steps.length} done
        </span>
      </div>
      {plan.summary && <p className="lp-summary">{plan.summary}</p>}

      <ol className="lp-path">
        {plan.steps.map((s) => {
          const isDone = completed.includes(s.id);
          return (
            <li key={s.id} className={`lp-stop${isDone ? " done" : ""}`}>
              <button className="lp-node" onClick={() => onToggle(s.id)} aria-pressed={isDone}
                title={isDone ? "Mark as not done" : "Mark as done"} aria-label={`Step ${s.order}: ${s.label}`}>
                {isDone ? "✓" : s.order}
              </button>

              <article className="lp-card">
                <header className="lp-card-head">
                  <div>
                    <span className="label">Stop {s.order} · about {s.weeks} week{s.weeks === 1 ? "" : "s"}</span>
                    <h4>{s.label}</h4>
                  </div>
                  <span className={signalClass(s.status)}>{s.status}</span>
                </header>
                <p className="lp-goal">{s.goal}</p>

                <div className="lp-grid">
                  <section className="lp-box">
                    <h5><Icon d={ICON.learn} /> What to learn</h5>
                    {s.learn.length ? (
                      <ol className="lp-learn">{s.learn.map((x) => <li key={x}>{x}</li>)}</ol>
                    ) : (
                      <p className="muted small">The courses cover it.</p>
                    )}
                  </section>

                  <section className="lp-box">
                    <h5><Icon d={ICON.courses} /> Courses</h5>
                    {s.courses.length > 0 ? (
                      <ul className="lp-courses">
                        {s.courses.map((c) => (
                          <li key={c.id}>
                            <a href={c.url} target="_blank" rel="noopener noreferrer">{c.title} ↗</a>
                            <span>
                              {c.provider === c.platform ? c.platform : `${c.provider} · ${c.platform}`}
                              {c.workload ? ` · ${c.workload}` : ""}
                            </span>
                          </li>
                        ))}
                      </ul>
                    ) : s.resource ? (
                      <ul className="lp-courses">
                        <li>
                          <a href={s.resource.url} target="_blank" rel="noopener noreferrer">{s.resource.title} ↗</a>
                          <span>{s.resource.provider} · {s.resource.hours} h · {s.resource.cost}</span>
                        </li>
                      </ul>
                    ) : (
                      <p className="muted small">No matching course in the catalogue yet.</p>
                    )}
                    {s.courses.length > 0 && s.course_note && <p className="lp-why">{s.course_note}</p>}
                    {s.courses.length === 0 && s.resource && (
                      <p className="lp-why">No close match in the Coursera search, so this is from Kompas&apos;s own course list.</p>
                    )}
                  </section>
                </div>

                {s.practice && (
                  <section className="lp-project">
                    <h5><Icon d={ICON.project} /> Mini project</h5>
                    <p>{s.practice}</p>
                    <p className="muted small">
                      A small piece of real work that proves you&apos;ve learned this step. Do it here, after the courses:
                      it&apos;s checked automatically, and passing completes this stop.
                    </p>
                    <button className="btn btn-primary btn-sm lp-start" onClick={() => setPractising(s)}>
                      ▶ {isDone ? "Do it again" : "Start mini project"}
                    </button>
                  </section>
                )}

                <button className="lp-done" onClick={() => onToggle(s.id)} aria-pressed={isDone}>
                  {isDone ? "✓ Done · undo" : "Mark this stop as done"}
                </button>
              </article>
            </li>
          );
        })}

        {capstone && capstoneId && (
          <li className="lp-stop lp-capstone">
            <span className="lp-node lp-node-final" aria-hidden><Icon d={ICON.star} /></span>
            <article className="lp-card">
              <header className="lp-card-head">
                <div>
                  <span className="label">Your work with AI · about 20 minutes</span>
                  <h4>{capstone.title} with AI tools</h4>
                </div>
                {finalResult && <span className="lp-final-result">Last time: {rating(finalResult.can).label}</span>}
              </header>
              <p className="lp-goal">
                Put it into practice the way the job is changing: four short tasks, all with AI tools. Brief an AI to get
                real work done, then catch the mistakes in what it wrote. You finish with a report on how you worked with it.
              </p>
              <div className="lp-grid">
                <section className="lp-box">
                  <h5><Icon d={ICON.project} /> Direct the AI</h5>
                  <p className="small">Write a brief, see how the AI answers, and sharpen it until the result is useful.</p>
                </section>
                <section className="lp-box">
                  <h5><Icon d={ICON.courses} /> Check its work</h5>
                  <p className="small">Spot the wrong numbers and invented facts in an AI-written draft before it goes out.</p>
                </section>
              </div>
              <button className="btn btn-primary lp-start" onClick={() => sim.open(capstoneId, { ...capstone, id: capstoneId, aiOnly: true })}>
                ▶ {finalResult ? "Try another round" : "Start your work with AI"}
              </button>
            </article>
          </li>
        )}

        <li className="lp-end lp-goal-end">
          <span className="lp-flag" aria-hidden><Icon d={ICON.flag} /></span>
          <strong>{plan.role.title}</strong>
          <span className="muted small">where this route leads</span>
        </li>
      </ol>

      {practising && (
        <PracticeModal role={plan.role.title} step={practising} onPassed={() => markDone(practising.id)}
          onClose={() => setPractising(null)} />
      )}

      <p className="muted small lp-foot">
        Plan written by AI ({plan.by}) from your route.
        {plan.courses_from ? ` Courses are real ${plan.courses_from} listings, found by search and picked by the AI.` : ""}
        {plan.note ? ` ${plan.note}.` : ""}
      </p>
    </div>
  );
}
