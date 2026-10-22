"use client";

// The recommended role and why, each reason with its evidence (CV quotes, market signals, MyCOL, SDG), plus the
// roles filling up as their skills are checked. Built for the CV flow; moved here for the Three Bets step, which
// comes after The Mirror has shown whether the current job is at risk.

import { useState } from "react";
import type { Evidence, Reason } from "../../lib/journey";
import type { CvProfile, CvRole } from "../../lib/kompas";
import { Breakdown } from "../CvMatch";
import Ring from "../Ring";

const ICON: Record<Reason["kind"], string> = { fit: "✓", demand: "↗", trend: "⚡", ai: "◐", sdg: "◎", gap: "+" };

export function RoleRace({ cv }: { cv: CvProfile }) {
  return (
    <div className="race">
      {cv.roles.map((r, i) => (
        <div key={r.isco} className={`race-row${r.isco === cv.recommended ? " best" : ""}`} style={{ "--d": `${600 + i * 180}ms` } as React.CSSProperties}>
          <div className="race-title">
            <strong>{r.title}</strong>
            <span className="muted small">{r.family?.label ?? "Other"}{r.family_status ? ` · ${r.family_status} demand` : ""}</span>
          </div>
          <div className="race-bar"><i style={{ width: `${r.match}%` }} /><b>{r.match}%</b></div>
          <div className="race-skills">
            {r.breakdown.map((b) => (
              <span key={b.id} className={`race-chip${b.coverage ? " have" : ""}`}>{b.coverage ? "✓" : "+"} {b.label}</span>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function EvidenceItem({ e }: { e: Evidence }) {
  if (e.type === "quote") return <li className="rs-ev rs-ev-quote"><q>{e.text}</q><span>{e.label} · from your CV</span></li>;
  if (e.type === "source") return <li className="rs-ev"><strong>{e.label}</strong> {e.text}</li>;
  return (
    <li className="rs-ev rs-ev-signal">
      <a href={e.url} target="_blank" rel="noopener noreferrer">{e.title}</a>
      <span>{e.skill ? `${e.skill} · ` : ""}{e.source}{e.value != null ? ` · ${Math.round(e.value)} ${e.value_label ?? ""}` : ""} · {e.date}</span>
    </li>
  );
}

export function Direction({ cv, role }: { cv: CvProfile; role: CvRole }) {
  const [how, setHow] = useState(false);
  const recommended = role.isco === cv.recommended;
  return (
    <div className="direction">
      <div className="direction-head">
        <div>
          <span className="eyebrow">{recommended ? "Pursue" : "Comparing"}</span>
          <h2>{role.title}</h2>
          {role.family && <p className="muted">{role.family.label}</p>}
        </div>
        <div className="plan-score">
          <Ring value={role.match} size={84} stroke={6} />
          <div>
            <div className="profile-stat-title">Skill match</div>
            <div className="muted small">{role.family_status ? `${role.family_status} demand` : "No demand data yet"} · estimate</div>
            <button className="plan-how" onClick={() => setHow(!how)} aria-expanded={how}>
              {how ? "Hide the calculation" : "How is this calculated?"}
            </button>
          </div>
        </div>
      </div>
      {how && <Breakdown rows={role.breakdown} />}
      <ul className="reasons">
        {(role.reasons ?? []).map((r) => (
          <li key={r.kind} className={`reason reason-${r.kind}`}>
            <span className="reason-icon" aria-hidden>{ICON[r.kind]}</span>
            <div>
              <strong>{r.title}</strong>
              <p>{r.text}</p>
              {r.evidence.length > 0 && <ul className="rs-evidence">{r.evidence.map((e, i) => <EvidenceItem key={i} e={e} />)}</ul>}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
