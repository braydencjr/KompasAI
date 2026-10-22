"use client";

import Ring from "./Ring";
import Roadmap, { SkillColumns, useStepProgress } from "./Roadmap";
import { SimButton } from "./SimulatorProvider";
import type { Role } from "../data/bets";

type Props = {
  role: Role;
  /** where this profile came from (sample, or which CV and how it was read) */
  origin?: React.ReactNode;
  /** experience and AI exposure, between the header and the skills */
  details?: React.ReactNode;
  /** other close fits, after the roadmap */
  footer?: React.ReactNode;
  /** skill label -> the CV line it was found in */
  skillQuotes?: Record<string, string>;
  onRemoveSkill?: (label: string) => void;
  haveLabel?: string;
  animate?: boolean;
};

const FORMULA =
  "Match = Σ weight × coverage ÷ Σ weight. Weight = importance (essential 1.0, optional 0.5) × demand. " +
  "Coverage: demonstrated 1.0, claimed on a CV 0.7, missing 0.";

export default function CvMatch({ role, origin, details, footer, skillQuotes, onRemoveSkill, haveLabel, animate }: Props) {
  const { done, toggle, gapClosed } = useStepProgress(role);

  return (
    <section id="plan" className={`plan glass${animate ? " reveal" : ""}`}>
      <div className="plan-inner">
        <header className="plan-head">
          <div className="plan-title">
            <div className="plan-tags">
              <span className="label">01 — Best fit from your CV</span>
              {origin}
              {role.sdg && <span className="chip chip-blue">{role.sdg.goal}</span>}
            </div>
            <h2>{role.title}</h2>
            <p className="muted">{role.summary}</p>
            <SimButton roleId={role.id} />
          </div>
          <div className="plan-score" title={FORMULA}>
            <Ring value={role.match} size={84} stroke={6} />
            <div>
              <div className="profile-stat-title">Skill match</div>
              <div className="muted small">{role.signal} demand · estimate</div>
              <div className="plan-how">How is this calculated?</div>
            </div>
          </div>
        </header>

        {details}

        <SkillColumns role={role} gapClosed={gapClosed} quotes={skillQuotes} onRemove={onRemoveSkill} haveLabel={haveLabel} />
        {role.steps.length > 0 ? (
          <Roadmap role={role} done={done} toggle={toggle} />
        ) : (
          <p className="muted small plan-empty">No verified course for these gaps yet. They&apos;re still worth learning.</p>
        )}

        {footer}
      </div>
    </section>
  );
}
