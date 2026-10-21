"use client";

import { useCallback, useEffect, useState } from "react";
import Ring from "./Ring";
import Sparkline from "./Sparkline";
import RoadmapModal from "./RoadmapModal";
import { riskLabel, type Bet } from "../data/bets";

export default function TrendingCareers({ bets }: { bets: Bet[] }) {
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
          <span className="kicker">02 — Market signals</span>
          <h2>Careers on the rise</h2>
          <p className="muted small">Ranked by job-market trend and AI replacement risk, then matched to your skills.</p>
        </div>
        <span className="muted small">Moderate scenario</span>
      </div>

      <div className="bets">
        {bets.map((b) => (
          <article key={b.id} className="bet glass">
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
                  <strong>+{b.growth}%</strong>
                  <Sparkline values={b.trend} width={64} height={26} />
                </div>
                <div className="metric-sub">postings YoY</div>
              </div>
              <div className="metric">
                <div className="label">AI risk</div>
                <strong>{b.aiRisk}%</strong>
                <div className="metric-sub">{riskLabel(b.aiRisk)} · 5 yrs</div>
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

            <button onClick={() => setOpenId(b.id)} className="btn btn-ghost btn-block">
              View full roadmap →
            </button>
          </article>
        ))}
      </div>

      {open && <RoadmapModal bet={open} onClose={close} />}
    </section>
  );
}
