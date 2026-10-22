"use client";

import { useMemo, useState } from "react";
import { riskLabel, type Bet } from "../../data/bets";
import { toBet } from "../../lib/adapters";
import { isBet, type BetKind, type Evidence, type Journey, type Reason, type RoleScore, type StayOption } from "../../lib/journey";
import { useProfile } from "../Profile";
import RoadmapModal from "../RoadmapModal";
import Ring from "../Ring";
import { SimButton } from "../SimulatorProvider";
import Sparkline from "../Sparkline";
import { useJourney } from "./JourneyProvider";
import { Estimate, ScenarioToggle } from "./shared";

/** Your Kompas: stay and strengthen the current job, or switch (the safest move, the fastest-growing one, the one with
 * the biggest impact). Which leads follows Your 2028's verdict; every option says why, with its evidence (PRD 5.4). */

type Kind = "stay" | BetKind;

const KIND: Record<Kind, { label: string; note: string }> = {
  stay: { label: "Stay and strengthen", note: "Your current job, with the skills that keep it strong" },
  safe: { label: "Safest switch", note: "Its key skills hold up whether AI moves at its current pace or fast" },
  rising: { label: "Fastest-growing", note: "Strongest demand among the jobs you fit" },
  impact: { label: "Biggest impact", note: "Best fit with the goals you chose" },
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
  sdg: { sdg: number; name: string } | null;
  learn: string[];
  reasons: Reason[];
  /** the dashboard card shape: trend, growth and the full roadmap */
  bet: Bet | null;
  /** shown when no job reaches the 40% bar for this kind: the closest one, a bigger step */
  stretch: boolean;
};

function fromRole(kind: BetKind, r: RoleScore, stretch = false): Option {
  return {
    kind, isco: r.isco, title: r.title, match: r.match, aiShare: r.ai_exposure,
    sdg: r.sdgs[0] ? { sdg: r.sdgs[0].sdg, name: r.sdgs[0].name } : null,
    learn: r.gaps.map((g) => g.label), reasons: r.reasons ?? [], bet: r.trend ? toBet(kind, r) : null, stretch,
  };
}

function fromStay(s: StayOption, r: RoleScore | undefined): Option {
  return {
    kind: "stay", isco: s.isco, title: s.title, match: s.match, aiShare: s.shares.moderate,
    sdg: r?.sdgs[0] ? { sdg: r.sdgs[0].sdg, name: r.sdgs[0].name } : null, learn: s.learn, reasons: s.reasons,
    bet: r?.trend ? { ...toBet("safe", r), kind: "Stay and strengthen", gaps: s.learn } : null, stretch: false,
  };
}

function OptionCard({ o, chosen, onChoose, onRoadmap }: { o: Option; chosen: boolean; onChoose: () => void; onRoadmap: () => void }) {
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

  return (
    <article className={`kp-card bet ${o.kind}${chosen ? " chosen" : ""}`}>
      <header className="kp-card-head">
        <span className={`kp-kind ${o.kind}`}>{KIND[o.kind].label}</span>
        {o.sdg && (
          <span className={`kp-sdg sdg-${o.sdg.sdg}`} title={`Serves UN Sustainable Development Goal ${o.sdg.sdg}: ${o.sdg.name}`}>
            <b>SDG {o.sdg.sdg}</b> {o.sdg.name}
          </span>
        )}
      </header>

      <div className="kp-title">
        <div>
          <h3>{o.title}</h3>
          <p className="muted">{o.stretch ? "A bigger step: no job reaches a 40% match for this yet" : KIND[o.kind].note}</p>
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

      <div className="kp-actions">
        {o.bet && o.bet.steps.length > 0 && (
          <button className="btn btn-ghost" onClick={onRoadmap}>View full roadmap →</button>
        )}
        <button className={`btn ${chosen ? "btn-ghost" : "btn-primary"}`} onClick={onChoose}>
          {chosen ? "Your route →" : o.kind === "stay" ? "Plan to strengthen it →" : "Choose this →"}
        </button>
      </div>
    </article>
  );
}

export default function StepBets() {
  const { data, catalog, sdgs, chooseRole, go, role: chosen } = useJourney();
  const [all, setAll] = useState(false);
  const [sort, setSort] = useState<"match" | "demand" | "alignment">("match");
  const [roadmap, setRoadmap] = useState<Bet | null>(null);
  const ranked = useMemo(
    () => [...(data?.roles ?? [])].sort((a, b) => (b[sort] as number) - (a[sort] as number) || b.match - a.match),
    [data?.roles, sort],
  );
  if (!data) return <div className="j-loading glass"><span className="sk sk-title" /><span className="sk sk-tile" /></div>;

  // "Biggest impact" needs goals to aim at; with none picked, leave it out rather than show an empty card
  const kinds = (["safe", "rising", "impact"] as const).filter((k) => k !== "impact" || sdgs.length > 0);
  const switches: (Option | { kind: BetKind; empty: string })[] = kinds.map((k) => {
    const b = data.bets[k];
    if (isBet(b)) return fromRole(k, b);
    const closest = b.closest && data.roles.find((r) => r.isco === b.closest!.isco);
    return closest ? fromRole(k, closest, true) : { kind: k, empty: "No job fits this yet." };
  });
  const stay = data.stay ? fromStay(data.stay, data.roles.find((r) => r.isco === data.stay!.isco)) : null;
  const lead = data.direction.lead;
  const cards = lead === "switch" ? [...switches, ...(stay ? [stay] : [])] : [...(stay ? [stay] : []), ...switches];
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
        <div className="gh-pace">
          <span className="label">How fast does AI move?</span>
          <ScenarioToggle />
        </div>
      </section>

      <section className="kp-options-head">
        <span className="label">Suggested jobs</span>
        <h3>Thinking of switching? Here are your best moves</h3>
        <p className="muted">
          Jobs your skills already fit, ranked by where hiring is heading. Your current job is here too, if you&apos;d
          rather grow where you are.
        </p>
      </section>

      <div className="kp-options">
        {cards.map((o) => ("empty" in o ? (
          <article key={o.kind} className={`kp-card ${o.kind} empty`}>
            <span className={`kp-kind ${o.kind}`}>{KIND[o.kind].label}</span>
            <p className="muted">{o.empty}</p>
          </article>
        ) : (
          <OptionCard key={o.kind} o={o} chosen={current === o.isco} onChoose={() => choose(o.isco)} onRoadmap={() => setRoadmap(o.bet)} />
        )))}
      </div>

      <button className="link j-all-toggle" onClick={() => setAll(!all)}>{all ? "Hide the full ranking" : `See all ${data.roles.length} jobs ranked`}</button>
      {all && (
        <section className="j-ranking glass reveal">
          <div className="j-ranking-sort">
            Sort by
            {(["match", "demand", "alignment"] as const).map((s) => (
              <button key={s} className={sort === s ? "on" : ""} onClick={() => setSort(s)}>{s === "alignment" ? "your goals" : s}</button>
            ))}
          </div>
          <ol>
            {ranked.map((r) => (
              <li key={r.isco}>
                <span className="j-rank-title">{r.title}</span>
                <span className="j-rank-bar"><span style={{ width: `${r.match}%` }} /></span>
                <span className="j-rank-num">{r.match}%</span>
                <span className="muted small">{r.family_status ? `${r.family_status} demand` : "no demand data"}{sdgs.length ? ` · ${Math.round(r.alignment * 100)}% of your goals` : ""}</span>
                {r.covered ? <span className="muted small">you have every skill</span> : <button className="link" onClick={() => choose(r.isco)}>Plan a route</button>}
              </li>
            ))}
          </ol>
          <p className="muted small">{catalog?.rules.match} {catalog?.rules.weight}</p>
        </section>
      )}
      {roadmap && <RoadmapModal bet={roadmap} onClose={() => setRoadmap(null)} />}
      <Estimate>Match scores are estimates from your skills and today&apos;s market signals, not predictions. You decide.</Estimate>
    </div>
  );
}
