"use client";

import CvMatch from "../CvMatch";
import { toRole } from "../../lib/adapters";
import { useJourney } from "./JourneyProvider";
import { ScenarioToggle } from "./shared";

/** The Route in the dashboard's plan-card design: skills, gaps and the step track, with progress kept in the
 * journey so finished steps fill the Ghost CV (PRD 5.6). */
export default function StepRoute() {
  const { data, completed, toggleStep, go, next } = useJourney();
  const r = data?.route;
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
        <ScenarioToggle />
        <span className="muted small">Steps run prerequisites first, then by how far up the Signal Ladder each skill is.</span>
      </div>
      <CvMatch
        key={`${role.id}-${r.steps.length}`}
        role={role}
        label="04 — Your route"
        origin={<span className="chip chip-origin">{r.hours_left} h left · {r.done}/{r.steps.length} done</span>}
        progress={progress}
        animate
        footer={r.sdg_contribution.length > 0 && (
          <div className="alt-roles">
            <div className="label">What this route contributes to</div>
            <div className="j-bet-sdgs">
              {r.sdg_contribution.map((c) => (
                <span key={c.sdg} className={`j-sdg sdg-${c.sdg}`} title={`Through ${c.steps.join(", ")}`}><b>{c.sdg}</b> {c.name}</span>
              ))}
            </div>
          </div>
        )}
      />
      <div className="j-cta">
        <button className="btn btn-ghost" onClick={() => go("future")}>See your 2028 CV fill in</button>
        <button className="btn btn-primary" onClick={next}>What if the world moves? →</button>
      </div>
    </>
  );
}
