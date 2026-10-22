"use client";

import { cvMatch, resources, type Role, type Signal } from "../data/bets";
import CvMatch from "./CvMatch";
import CvScanner from "./CvScanner";
import { useProfile } from "./Profile";

/** Section 01: the scanner while a CV is read, then the best-fit role built from it (or the sample). */
export default function ProfilePanel() {
  const { source, cv, role, scan, skills, selectRole, removeSkill } = useProfile();

  if (scan) return <CvScanner fileName={scan.name} lines={scan.lines} result={scan.result} />;

  if (source !== "cv" || !cv) {
    return <CvMatch role={cvMatch} origin={<span className="chip chip-origin">Sample profile · Aisyah</span>} />;
  }

  const held = cv.skills.filter((s) => skills.includes(s.id));
  const summary = cv.summary ?? `${held.length} skills found in your CV.`;
  const fromCv: Role = role
    ? {
        id: `cv-${role.isco}`,
        title: role.title,
        summary,
        match: role.match,
        signal: (role.demand ?? "Stable") as Signal,
        have: held.map((s) => s.label),
        gaps: role.gaps.map((g) => g.label),
        steps: role.gaps.flatMap((g) => (resources[g.id] ?? []).map((step) => ({ ...step, skill: g.label }))),
      }
    : {
        id: "cv-none",
        title: "No close role in our catalogue yet",
        summary,
        match: 0,
        signal: "Stable",
        have: held.map((s) => s.label),
        gaps: [],
        steps: [],
      };

  const origin = (
    <span className="chip chip-origin">
      {cv.file ?? "Your CV"} · {cv.method === "llm" ? `read by ${cv.model}` : "keyword match"}
    </span>
  );

  const details = (cv.jobs.length > 0 || cv.exposed.length > 0) && (
    <div className="profile-details">
      {cv.jobs.length > 0 && (
        <div className="pd-row">
          <div className="label">Your experience</div>
          <div className="pd-items">
            {cv.jobs.map((j) => (
              <span key={j.quote} className="pd-job">
                <strong>{j.title}</strong>
                {j.period && <span className="muted small"> · {j.period}</span>}
                {j.occupation && <span className="pd-occ">{j.occupation.title}</span>}
              </span>
            ))}
          </div>
        </div>
      )}
      {cv.exposed.length > 0 && (
        <div className="pd-row">
          <div className="label">AI reaching your work</div>
          <div className="pd-items">
            {cv.exposed.map((e) => (
              <span key={e.id} className="pd-ai" title={e.because.map((b) => `${b.skill}: ${b.why}`).join("\n")}>
                {e.label}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );

  const footer = cv.roles.length > 1 && (
    <div className="alt-roles">
      <div className="label">Other close fits · tap to compare</div>
      <div className="alt-role-list">
        {cv.roles.map((r) => (
          <button key={r.isco} className={`alt-role${r.isco === role?.isco ? " on" : ""}`} onClick={() => selectRole(r.isco)}>
            <strong>{r.title}</strong>
            <span>{r.match}% match · {r.gaps.length} to learn</span>
          </button>
        ))}
      </div>
    </div>
  );

  return (
    <CvMatch
      key={fromCv.id}
      role={fromCv}
      origin={origin}
      details={details || null}
      footer={footer || null}
      skillQuotes={Object.fromEntries(held.map((s) => [s.label, s.quote]))}
      onRemoveSkill={(label) => {
        const s = held.find((h) => h.label === label);
        if (s) removeSkill(s.id);
      }}
      haveLabel="Your skills"
      animate
    />
  );
}
