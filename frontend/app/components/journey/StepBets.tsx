"use client";

import { useState } from "react";
import { riskLabel, type Bet } from "../../data/bets";
import { toBet } from "../../lib/adapters";
import { isBet, type BetKind, type Evidence, type Journey, type Reason, type RoleScore, type StayOption } from "../../lib/journey";
import { useProfile } from "../Profile";
import JobsButton from "../JobsButton";
import Ring from "../Ring";
import { SimButton } from "../SimulatorProvider";
import Sparkline from "../Sparkline";
import { useJourney } from "./JourneyProvider";
import { Estimate } from "./shared";

/** Your Kompas: an upskilling suggestion for the current job, then the two best switches (the fastest-growing job you
 * fit and the safest move). The headline follows Your 2028's verdict; every option says why, with its evidence (PRD 5.4). */

type Kind = "stay" | BetKind;

const KIND: Record<Kind, { label: string; note: string }> = {
  stay: { label: "Stay and strengthen", note: "Your current job, with the skills that keep it strong" },
  safe: { label: "Safest switch", note: "Its key skills hold up whether AI moves at its current pace or fast" },
  rising: { label: "Fastest-growing", note: "Strongest demand among the jobs you fit" },
  impact: { label: "Biggest impact", note: "Best fit with the goals you chose" },
};

const COLUMNS = ["rising", "safe"] as const;

/** how each column is ranked, in words (the engine's rules: journey.WEIGHTS_DOC) */
const COLUMN_RULE: Record<(typeof COLUMNS)[number], string> = {
  rising: "Ranked by demand for the job times how well you fit it.",
  safe: "Ranked by fit, among jobs where most key skills hold up against AI.",
};

const HEAD: Record<Journey["direction"]["lead"], { title: string; body: string }> = {
  stay: {
    title: "Staying is your strongest move",
    body: "AI can do little of your job by 2028. Strengthen it with rising skills; the switches are here if you want a change.",
  },
  either: {
    title: "Stay or switch: both are open",
    body: "AI is taking over parts of your job. Strengthen it, or move to a job that uses your skills with less exposure.",
  },
  switch: {
    title: "It's time to look at switching",
    body: "AI could do much of your job by 2028. These jobs use the skills you have, with less of the work exposed.",
  },
};

const ICON: Record<Reason["kind"], string> = { fit: "✓", demand: "↗", trend: "⚡", ai: "◐", sdg: "◎", gap: "+" };

function EvidenceItem({ e }: { e: Evidence }) {
  if (e.type === "quote") return <li className="rs-ev rs-ev-quote"><q>{e.text}</q><span>{e.label} · from your CV</span></li>;
  if (e.type === "source") return <li className="rs-ev"><strong>{e.label}</strong> {e.text}</li>;
  return (
    <li className="rs-ev rs-ev-signal">
      <a href={e.url} target="_blank" rel="noopener noreferrer">{e.title}</a>
      <span>{e.skill ? `${e.skill} · ` : ""}{e.source} · {e.date}</span>
    </li>
  );
}

type Option = {
  kind: Kind;
  isco: string;
  title: string;
  match: number | null;
  aiShare: number | null;
  /** one line about this job, from its own numbers */
  blurb: string;
  learn: string[];
  reasons: Reason[];
  /** the dashboard card shape: trend, growth and the full roadmap */
  bet: Bet | null;
  /** shown when no job reaches the 40% bar for this kind: the closest one, a bigger step */
  stretch: boolean;
};

/** Why this job sits in its column, in its own numbers: the skills you have, and its demand (fastest-growing) or how
 * much of it holds up against AI (safest). */
function blurbFor(kind: BetKind, r: RoleScore, stretch: boolean) {
  const skills = `You have ${r.have.length} of its ${r.breakdown.length} skills`;
  const why =
    kind === "safe"
      ? `${Math.round(r.safe_share * 100)}% of its key skills hold up even if AI moves fast`
      : r.family_status
        ? `${r.family?.label ?? "Its field"} demand: ${r.family_status.toLowerCase()}${r.mycol ? ", on Malaysia's critical jobs list" : ""}`
        : "no hiring data for it yet";
  return `${stretch ? "A bigger step. " : ""}${skills}; ${why}.`;
}

function fromRole(kind: BetKind, r: RoleScore, stretch = false): Option {
  return {
    kind, isco: r.isco, title: r.title, match: r.match, aiShare: r.ai_exposure, blurb: blurbFor(kind, r, stretch),
    learn: r.gaps.map((g) => g.label), reasons: r.reasons ?? [], bet: r.trend ? toBet(kind, r) : null, stretch,
  };
}

function fromStay(s: StayOption, r: RoleScore | undefined): Option {
  return {
    kind: "stay", isco: s.isco, title: s.title, match: s.match, aiShare: s.shares.moderate, blurb: KIND.stay.note,
    learn: s.learn, reasons: s.reasons,
    bet: r?.trend ? { ...toBet("safe", r), kind: "Stay and strengthen", gaps: s.learn } : null, stretch: false,
  };
}

type CardProps = { o: Option; chosen: boolean; onChoose: () => void; wide?: boolean; rank?: number };

function OptionCard({ o, chosen, onChoose, wide = false, rank }: CardProps) {
  const profile = useProfile();
  const [why, setWhy] = useState(false);
  // the fit reason's evidence: the CV lines that show each skill the job needs
  const quotes = Object.fromEntries((profile.cv?.skills ?? []).map((s) => [s.label, s.quote]));
  const shown = o.reasons.filter((r) => r.kind !== "sdg" && r.kind !== "gap");
  const evidence = (r: Reason): Evidence[] => {
    if (r.kind !== "fit" || r.evidence.length) return r.evidence;
    const have = r.text.replace(/\.$/, "").split(", ");
    return have.filter((h) => quotes[h]).map((h) => ({ type: "quote", label: h, text: quotes[h] }));
  };

  const summary = (
    <>
      <div className="kp-title">
        <div>
          <h3>{o.title}</h3>
          <p className="muted">{o.blurb}</p>
        </div>
        {o.match !== null && <Ring value={o.match} size={64} stroke={5} />}
      </div>

      <div className="metrics">
        {o.bet && (
          <div className="metric">
            <div className="label">Trend</div>
            <div className="metric-row">
              <strong>{o.bet.growth >= 0 ? "+" : ""}{o.bet.growth}%</strong>
              <Sparkline values={o.bet.trend} width={64} height={26} />
            </div>
            <div className="metric-sub">{o.bet.trendNote}</div>
          </div>
        )}
        {o.aiShare !== null && (
          <div className="metric">
            <div className="label">AI risk</div>
            <strong>{o.aiShare}%</strong>
            <div className="metric-sub">{riskLabel(o.aiShare)} · tasks AI can do by 2028</div>
          </div>
        )}
      </div>
    </>
  );

  const detail = (
    <>

      {o.learn.length > 0 && (
        <div className="gaps">
          <div className="label">{o.kind === "stay" ? "Skills to strengthen it" : "Skill gaps to close"}</div>
          <ol className="gap-list">
            {o.learn.map((g, n) => (
              <li key={g}><span className="gap-num">{n + 1}</span>{g}</li>
            ))}
          </ol>
        </div>
      )}

      {shown.length > 0 && (
        <div className="kp-why">
          <button className="kp-evidence-toggle" onClick={() => setWhy(!why)} aria-expanded={why}>
            {why ? "Hide why" : `Why this job? ${shown.length} reasons with evidence`}
          </button>
          {why && (
            <ul className="kp-reasons">
              {shown.map((r) => (
                <li key={r.kind} className={`reason reason-${r.kind}`}>
                  <span className="reason-icon" aria-hidden>{ICON[r.kind]}</span>
                  <div>
                    <strong>{r.title}</strong>
                    <p>{r.text}</p>
                    {evidence(r).length > 0 && <ul className="rs-evidence">{evidence(r).map((e, i) => <EvidenceItem key={i} e={e} />)}</ul>}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      <SimButton roleId={o.isco} variant="link" />

      {o.bet && <JobsButton bet={o.bet} />}

    </>
  );

  // the label on the left and the roadmap button at the top right, across the whole card
  const head = (
    <header className="kp-card-head">
      {rank ? <span className={`kp-rank ${o.kind}`}>#{rank}</span> : <span className={`kp-kind ${o.kind}`}>{KIND[o.kind].label}</span>}
      {/* picks this job and opens its route, where the AI learning plan is written */}
      <button className="btn btn-ghost btn-sm" onClick={onChoose}>View full roadmap →</button>
    </header>
  );

  return (
    <article className={`kp-card bet ${o.kind}${chosen ? " chosen" : ""}${wide ? " wide" : ""}`}>
      {head}
      {wide ? (
        <>
          <div className="kp-col">{summary}</div>
          <div className="kp-col">{detail}</div>
        </>
      ) : (
        <>
          {summary}
          {detail}
        </>
      )}
    </article>
  );
}

export default function StepBets() {
  const { data, chooseRole, go, role: chosen } = useJourney();
  if (!data) return <div className="j-loading glass"><span className="sk sk-title" /><span className="sk sk-tile" /></div>;

  const byIsco = new Map(data.roles.map((r) => [r.isco, r]));
  // each column: the engine's top picks for that kind; an older backend sends only its single bet
  const columns = COLUMNS.map((k) => {
    const b = data.bets[k];
    const picks =
      data.suggestions?.[k] ??
      (isBet(b) ? [{ isco: b.isco, stretch: false }] : b.closest ? [{ isco: b.closest.isco, stretch: true }] : []);
    return { kind: k, options: picks.flatMap((p) => (byIsco.has(p.isco) ? [fromRole(k, byIsco.get(p.isco)!, p.stretch)] : [])) };
  });
  const stay = data.stay ? fromStay(data.stay, byIsco.get(data.stay.isco)) : null;
  const lead = data.direction.lead;
  const choose = (isco: string) => {
    chooseRole(isco);
    go("route");
  };
  const current = chosen ?? data.route?.role.isco ?? null;

  return (
    <div className="kp">
      <section className={`kp-head glass ${data.direction.level}`}>
        <div>
          {data.stay && <span className="label">Your job: {data.stay.title}</span>}
          <h2>{HEAD[lead].title}</h2>
          <p>{HEAD[lead].body}</p>
        </div>
      </section>

      {stay && (
        <>
          <section className="kp-options-head">
            <span className="label">Upskilling suggestion</span>
            <h3>Grow where you are</h3>
            <p className="muted">The skills that keep your current job strong as AI changes it.</p>
          </section>
          <OptionCard o={stay} wide chosen={current === stay.isco} onChoose={() => choose(stay.isco)} />
        </>
      )}

      <section className="kp-options-head">
        <span className="label">Suggested jobs</span>
        <h3>Thinking of switching? Here are your best moves</h3>
        <p className="muted">Jobs your skills already fit, in two lists: where demand is growing fastest, and where your skills are safest from AI.</p>
      </section>

      <div className="kp-columns">
        {columns.map((c) => (
          <section key={c.kind} className={`kp-column ${c.kind}`}>
            <header className="kp-column-head">
              <span className={`kp-kind ${c.kind}`}>{KIND[c.kind].label}</span>
              <p className="muted small">{COLUMN_RULE[c.kind]}</p>
            </header>
            {c.options.length ? (
              c.options.map((o, i) => (
                <OptionCard key={o.isco} o={o} rank={i + 1} chosen={current === o.isco} onChoose={() => choose(o.isco)} />
              ))
            ) : (
              <p className="muted kp-column-empty">No job fits this yet.</p>
            )}
          </section>
        ))}
      </div>

      <Estimate>Match scores are estimates from your skills and today&apos;s market signals, not predictions. You decide.</Estimate>
    </div>
  );
}
