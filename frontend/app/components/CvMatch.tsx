"use client";

import type { SkillRow } from "../lib/journey";
import Ring from "./Ring";
import Roadmap, { SkillColumns, useStepProgress } from "./Roadmap";
import { SimButton } from "./SimulatorProvider";
import type { Role } from "../data/bets";

type Props = {
  role: Role;
  /** what Kompas read about the person, shown above the role */
  intro?: React.ReactNode;
  /** the role's per-skill score rows (no longer shown here) */
  breakdown?: SkillRow[];
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
  /** section label (default: best fit from the CV) */
  label?: string;
  /** shown instead of the roadmap when the role has no steps (null: nothing) */
  emptyNote?: React.ReactNode;
  /** progress kept elsewhere (the journey); default: this browser's per-role progress */
  progress?: ReturnType<typeof useStepProgress>;
  /** two cards instead of one: the skill match first, then the route under its own heading; `extra` goes under
   * the score (e.g. the job boards button) */
  split?: { label: string; tags?: React.ReactNode; extra?: React.ReactNode; body?: React.ReactNode };
};

const FORMULA =
  "Match = Σ weight × coverage ÷ Σ weight. Weight = importance (essential 1.0, optional 0.5) × demand. " +
  "Coverage: demonstrated 1.0, claimed on a CV 0.7, missing 0.";

const EVIDENCE: Record<string, string> = { demonstrated: "shown", claimed: "on your CV" };

/** Each skill's share of the match: weight x coverage over the total weight, so the rows add up to the score. */
export function Breakdown({ rows }: { rows: SkillRow[] }) {
  const total = rows.reduce((t, r) => t + r.weight, 0) || 1;
  return (
    <div className="plan-breakdown">
      <div className="pb-row pb-head">
        <span>Skill</span><span>Role needs it</span><span>Demand</span><span>You</span><span>Points</span>
      </div>
      {rows.map((r) => (
        <div key={r.id} className={`pb-row${r.coverage ? "" : " missing"}`}>
          <span>{r.label}</span>
          <span>{r.importance === 1 ? "Essential" : "Optional"}</span>
          <span>{r.measured ? r.status : "No signal"}</span>
          <span>{r.coverage ? `${EVIDENCE[r.evidence ?? ""] ?? "yes"} · ${Math.round(r.coverage * 100)}%` : "Missing"}</span>
          <span>{Math.round((100 * r.weight * r.coverage) / total)} / {Math.round((100 * r.weight) / total)}</span>
        </div>
      ))}
      <p className="muted small">{FORMULA}</p>
    </div>
  );
}

export default function CvMatch({ role, intro, origin, details, footer, skillQuotes, onRemoveSkill, haveLabel, animate, label, emptyNote, progress, split }: Props) {
  const local = useStepProgress(role);
  const { done, toggle, gapClosed } = progress ?? local;

  const match = (
    <>
      {intro}
      <header className="plan-head">
        <div className="plan-title">
          <div className="plan-tags">
            <span className="label">{label ?? "Best fit from your CV"}</span>
            {origin}
            {role.sdg && <span className="chip chip-blue">{role.sdg.goal}</span>}
          </div>
          <h2>{role.title}</h2>
          <p className="muted">{role.summary}</p>
          <SimButton roleId={role.id} />
        </div>
        <div className="plan-score">
          <Ring value={role.match} size={84} stroke={6} />
          <div>
            <div className="profile-stat-title">Skill match</div>
            <div className="muted small">{role.signal ? `${role.signal} demand` : "No demand signal yet"} · estimate</div>
          </div>
        </div>
      </header>

      {details}

      <SkillColumns role={role} gapClosed={gapClosed} quotes={skillQuotes} onRemove={onRemoveSkill} haveLabel={haveLabel} />
    </>
  );

  // split mode: the page already names the job, so this card is just the score (left) and the skills behind it (right)
  const splitMatch = (
    <>
      <div className="plan-match">
        <div className="plan-match-score">
          <span className="label">{label ?? "Your skill match"}</span>
          <Ring value={role.match} size={112} stroke={7} />
          <div>
            <div className="profile-stat-title">Skill match</div>
            <div className="muted small">{role.signal ? `${role.signal} demand` : "No demand signal yet"} · estimate</div>
          </div>
          <SimButton roleId={role.id} />
          {split?.extra}
        </div>
        <SkillColumns role={role} gapClosed={gapClosed} quotes={skillQuotes} onRemove={onRemoveSkill} haveLabel={haveLabel} />
      </div>

      {details}
    </>
  );

  const route = (
    <>
      {role.steps.length > 0 ? (
        <Roadmap role={role} done={done} toggle={toggle} />
      ) : emptyNote !== undefined ? (
        emptyNote
      ) : (
        <p className="muted small plan-empty">No verified course for these gaps yet. They&apos;re still worth learning.</p>
      )}

      {footer}
    </>
  );

  if (split) {
    return (
      <div className="plan-split">
        <section id="plan" className={`plan glass${animate ? " reveal" : ""}`}>
          <div className="plan-inner">{splitMatch}</div>
        </section>
        <section className={`plan glass${animate ? " reveal" : ""}`}>
          <div className="plan-inner">
            <div className="plan-tags">
              <span className="label">{split.label}</span>
              {split.tags}
            </div>
            {split.body ?? route}
          </div>
        </section>
      </div>
    );
  }

  return (
    <section id="plan" className={`plan glass${animate ? " reveal" : ""}`}>
      <div className="plan-inner">
        {match}
        {route}
      </div>
    </section>
  );
}
