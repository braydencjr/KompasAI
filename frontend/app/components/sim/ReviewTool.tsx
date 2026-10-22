"use client";

import { useState } from "react";
import type { ReviewTask } from "../../data/simulations";

type Props = { task: ReviewTask; onDone: (score: number, evidence: string[]) => void };
type Decision = "approve" | "send back";

export default function ReviewTool({ task, onDone }: Props) {
  const [flags, setFlags] = useState<Set<number>>(new Set());
  const [decision, setDecision] = useState<Decision | null>(null);
  const done = decision !== null;

  const issues = task.segments.filter((s) => s.issue).length;

  function toggle(i: number) {
    if (done) return;
    setFlags((f) => {
      const next = new Set(f);
      if (next.has(i)) next.delete(i);
      else next.add(i);
      return next;
    });
  }

  function decide(d: Decision) {
    const caught = task.segments.filter((s, i) => s.issue && flags.has(i)).length;
    const falseAlarms = task.segments.filter((s, i) => !s.issue && flags.has(i)).length;
    const right = d === task.verdict;
    // false alarms cost half a catch; approving a flawed draft is the costliest miss
    const found = Math.max(0, caught - falseAlarms / 2) / issues;
    setDecision(d);
    onDone(found * (right ? 1 : 0.6), [
      `Caught ${caught} of ${issues} AI mistakes`,
      falseAlarms ? `${falseAlarms} false alarm${falseAlarms > 1 ? "s" : ""}` : "No false alarms",
      right ? (d === "send back" ? "Sent it back ✓" : "Approved ✓") : d === "approve" ? "Approved a flawed draft ✗" : "Sent back a good draft ✗",
    ]);
  }

  function state(i: number) {
    const flagged = flags.has(i);
    const bad = !!task.segments[i].issue;
    if (!done) return flagged ? " flagged" : "";
    if (bad) return flagged ? " caught" : " missed";
    return flagged ? " false" : "";
  }

  return (
    <div className="tool tool-review">
      <div className="review-source">
        <div className="label">Source · {task.source.title}</div>
        <div className="sheet-wrap">
          <table className="tests">
            <thead>
              <tr>
                {task.source.columns.map((c) => (
                  <th key={c}>{c}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {task.source.rows.map((r) => (
                <tr key={r[0]}>
                  {r.map((c, j) => (
                    <td key={j}>{c}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="tool-bar">
        <span className="tool-file ai-name">
          <span className="ai-spark" aria-hidden>✦</span> {task.artifactName}
        </span>
        <span className="muted small">
          {done ? `${issues} mistakes were planted` : `${flags.size} flagged · click ${task.format === "code" ? "a line" : "a sentence"} to flag`}
        </span>
      </div>

      <div className={`review-doc ${task.format}`}>
        {task.segments.map((s, i) => (
          <span key={i} className={`review-seg${state(i)}`}>
            <button className="review-hit" onClick={() => toggle(i)} disabled={done} aria-pressed={flags.has(i)}>
              {task.format === "code" && <span className="review-ln">{i + 1}</span>}
              <span className="review-text">{s.text}</span>
            </button>
            {done && (s.issue ? <span className="review-why">{flags.has(i) ? "✓ " : "Missed: "}{s.issue}</span> : flags.has(i) && <span className="review-why">This one was fine.</span>)}
            {task.format === "prose" && " "}
          </span>
        ))}
      </div>

      {!done && (
        <div className="review-actions">
          <button className="btn btn-ghost" onClick={() => decide("approve")}>
            ✓ Approve as is
          </button>
          <button className="btn btn-primary" onClick={() => decide("send back")}>
            ↩ Send back to fix{flags.size ? ` (${flags.size})` : ""}
          </button>
        </div>
      )}
    </div>
  );
}
