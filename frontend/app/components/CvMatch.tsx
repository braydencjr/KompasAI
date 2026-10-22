"use client";

import Ring from "./Ring";
import Roadmap, { SkillColumns, useStepProgress } from "./Roadmap";
import { SimButton } from "./SimulatorProvider";
import type { Role } from "../data/bets";

export default function CvMatch({ role }: { role: Role }) {
  const { done, toggle, gapClosed } = useStepProgress(role);

  return (
    <section id="plan" className="plan glass">
      <div className="plan-inner">
        <header className="plan-head">
          <div className="plan-title">
            <div className="plan-tags">
              <span className="label">01 — Best fit from your CV</span>
              <span className="chip chip-blue">{role.sdg.goal}</span>
            </div>
            <h2>{role.title}</h2>
            <p className="muted">{role.summary}</p>
            <SimButton roleId={role.id} />
          </div>
          <div className="plan-score">
            <Ring value={role.match} size={84} stroke={6} />
            <div>
              <div className="profile-stat-title">Skill match</div>
              <div className="muted small">{role.signal} demand · estimate</div>
            </div>
          </div>
        </header>

        <SkillColumns role={role} gapClosed={gapClosed} />
        <Roadmap role={role} done={done} toggle={toggle} />
      </div>
    </section>
  );
}
