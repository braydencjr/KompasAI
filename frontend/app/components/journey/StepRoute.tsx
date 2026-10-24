"use client";

import { useEffect, useState } from "react";
import CvMatch from "../CvMatch";
import { toRole } from "../../lib/adapters";
import { journeyApi, type LearningPlan as Plan } from "../../lib/journey";
import { useJourney } from "./JourneyProvider";
import LearningPlan from "./LearningPlan";

type PlanState = { status: "loading" } | { status: "ready"; plan: Plan } | { status: "error"; message: string };

/** The Route in the dashboard's plan-card design: the skill match, then the route to the chosen job as an AI learning
 * plan (with the rule-based track while it's written, or if it can't be), with progress kept in the journey so
 * finished steps fill the Ghost CV (PRD 5.6). */
export default function StepRoute() {
  const { data, completed, toggleStep, go, next, request } = useJourney();
  const r = data?.route;
  const [plan, setPlan] = useState<PlanState>({ status: "loading" });

  // the plan depends on the job, your skills and the scenario, not on which steps you've ticked off. Right after a
  // job is picked, the route on screen is still the old job's until the journey reloads: wait for it.
  const stale = !!request.role && r?.role.isco !== request.role;
  const planKey = r && !stale ? JSON.stringify({ ...request, completed: [], pace: 5, role: r.role.isco }) : null;
  useEffect(() => {
    if (!planKey) return;
    const ctrl = new AbortController();
    setPlan({ status: "loading" });
    journeyApi
      .plan(JSON.parse(planKey), ctrl.signal)
      .then((p) => {
        if (ctrl.signal.aborted || !p) return;     // leaving the page cancels the request, and a cancelled one answers null
        setPlan({ status: "ready", plan: p });
      })
      .catch((e) => !ctrl.signal.aborted && setPlan({ status: "error", message: e instanceof Error ? e.message : String(e) }));
    return () => ctrl.abort();
  }, [planKey]);

  if (!data) return <div className="j-loading glass"><span className="sk sk-title" /><span className="sk sk-tile" /></div>;
  if (!r) {
    return (
      <section className="j-empty glass">
        <p>Pick a bet first, and Kompas will build the route to it.</p>
        <button className="btn btn-primary" onClick={() => go("bets")}>See your bets</button>
      </section>
    );
  }
  const score = data.roles.find((x) => x.isco === r.role.isco);
  const role = toRole(r, score);
  const done = r.steps.map((s) => completed.includes(s.id));
  const progress = {
    done,
    toggle: (i: number) => toggleStep(r.steps[i].id),
    gapClosed: (label: string) => r.steps.some((s) => s.label === label && completed.includes(s.id)),
  };

  return (
    <>
      <div className="j-ghost-bar">
        <span className="muted small">Steps run prerequisites first, then by how far up the Signal Ladder each skill is.</span>
      </div>
      <CvMatch
        key={`${role.id}-${r.steps.length}`}
        role={role}
        label="Your skill match"
        split={{
          label: "Your route",
          tags:
            plan.status === "ready" && plan.plan ? null : plan.status === "error" ? (
              <span className="chip chip-origin" title={plan.message}>Rule-based route · AI plan unavailable</span>
            ) : (
              <span className="chip chip-origin">{r.hours_left} h left · {r.done}/{r.steps.length} done</span>
            ),
          body:
            plan.status === "ready" && plan.plan ? (
              <LearningPlan
                plan={plan.plan}
                completed={completed}
                onToggle={toggleStep}
                capstone={score ? {
                  id: score.isco, title: score.title, summary: score.occupation,
                  have: score.have.map((h) => h.label), gaps: score.gaps.map((g) => g.label),
                } : null}
              />
            ) : plan.status === "loading" && r.steps.length > 0 ? (
              <div className="lp-loading" aria-live="polite">
                <span className="ai-spark gen-spin" aria-hidden>✦</span>
                <div>
                  <strong>Writing your learning plan for {r.role.title}…</strong>
                  <p className="muted small">Planning each step, then searching real courses. The first time takes about 20 seconds.</p>
                </div>
              </div>
            ) : undefined,
        }}
        progress={progress}
        animate
      />
      <div className="j-cta">
        <button className="btn btn-primary" onClick={next}>What if the world moves? →</button>
      </div>
    </>
  );
}
