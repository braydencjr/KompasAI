"use client";

import { useCallback, useEffect, useState } from "react";
import Ring from "./Ring";
import Sparkline from "./Sparkline";
import RoadmapModal from "./RoadmapModal";
import { SimButton } from "./SimulatorProvider";
import { riskLabel, type Bet } from "../data/bets";

type Props = {
  bets: Bet[];
  kicker?: string;
  title?: string;
  subtitle?: string;
  scenarioLabel?: string;
  /** the journey: choose a bet to build its route */
  onChoose?: (id: string) => void;
  chosenId?: string | null;
};

export default function TrendingCareers({ bets, kicker = "02 — Market signals", title = "Careers on the rise",
  subtitle = "Ranked by job-market trend and AI replacement risk, then matched to your skills.",
  scenarioLabel = "Moderate scenario", onChoose, chosenId }: Props) {
  const [openId, setOpenId] = useState<string | null>(null);
  const open = bets.find((b) => b.id === openId);
  const close = useCallback(() => setOpenId(null), []);

  // a link like /#roadmap-esg-reporting opens that roadmap directly
  useEffect(() => {
    const id = window.location.hash.replace("#roadmap-", "");
    if (bets.some((b) => b.id === id)) setOpenId(id);
  }, [bets]);

  return (
    <section>
      <div className="section-head">
        <div>
          <span className="kicker">{kicker}</span>
          <h2>{title}</h2>
          <p className="muted small">{subtitle}</p>
        </div>
        <span className="muted small">{scenarioLabel}</span>
      </div>

      <div className="bets">
        {bets.map((b) => (
          <article key={b.id} className={`bet glass${chosenId === b.id ? " bet-active" : ""}`}>
            <div className="bet-head">
              <span className="bet-kind">{b.kind}</span>
              <span className="chip chip-blue">{b.sdg.goal}</span>
            </div>

            <div className="bet-title">
              <div>
                <h3 className="bet-name">{b.title}</h3>
                <p className="muted small">{b.note}</p>
              </div>
              <Ring value={b.match} size={56} stroke={4} />
            </div>

            <div className="metrics">
              <div className="metric">
                <div className="label">Trend</div>
                <div className="metric-row">
                  <strong>{b.growth >= 0 ? "+" : ""}{b.growth}%</strong>
                  <Sparkline values={b.trend} width={64} height={26} />
                </div>
                <div className="metric-sub">{b.trendNote ?? "postings YoY"}</div>
              </div>
              <div className="metric">
                <div className="label">AI risk</div>
                <strong>{b.aiRisk}%</strong>
                <div className="metric-sub">{riskLabel(b.aiRisk)} · {b.trendNote ? "tasks exposed" : "5 yrs"}</div>
              </div>
            </div>

            <div className="gaps">
              <div className="label">Skill gaps to close</div>
              <ol className="gap-list">
                {b.gaps.map((g, n) => (
                  <li key={g}>
                    <span className="gap-num">{n + 1}</span>
                    {g}
                  </li>
                ))}
              </ol>
            </div>

            <SimButton roleId={b.id} variant="link" />

            <button onClick={() => setOpenId(b.id)} className="btn btn-ghost btn-block">
              View full roadmap →
            </button>
            {onChoose && (
              <button onClick={() => onChoose(b.id)} className={`btn btn-block ${chosenId === b.id ? "btn-ghost" : "btn-primary"}`}>
                {chosenId === b.id ? "Your route →" : "Choose this bet →"}
              </button>
            )}
          </article>
        ))}
      </div>

      {open && <RoadmapModal bet={open} onClose={close} />}
    </section>
  );
}
