"use client";

import { useEffect, useState } from "react";
import type { CvProfile } from "../lib/kompas";

const STEPS = [
  "Reading your file",
  "Finding skills by meaning",
  "Checking every quote against your CV",
  "Matching your jobs to standard occupations",
  "Looking for AI that reaches your work",
];

// stand-in lines for PDF/DOCX, which the browser can't read; widths in %
const PLACEHOLDER = [58, 34, 0, 92, 76, 88, 0, 64, 95, 81, 70, 0, 52, 90, 84, 0, 40, 86, 73];

const norm = (s: string) => s.toLowerCase().replace(/\s+/g, " ").trim();

/** Does a CV line contain (part of) a quote the model found? */
function isHit(line: string, quotes: string[]) {
  const l = norm(line);
  return quotes.some((q) => {
    const n = norm(q);
    return n.length > 3 && (l.includes(n.slice(0, 28)) || (l.length > 12 && n.includes(l)));
  });
}

type Props = {
  fileName: string;
  /** the CV's own lines when the file is plain text, else null */
  lines: string[] | null;
  /** set once the API has answered: the scanner finishes and highlights what it found */
  result: CvProfile | null;
};

export default function CvScanner({ fileName, lines, result }: Props) {
  const [step, setStep] = useState(0);

  // walk through the stages while waiting; the last one stays active until the answer arrives
  useEffect(() => {
    if (result) return;
    const timer = setInterval(() => setStep((s) => Math.min(s + 1, STEPS.length - 1)), 1100);
    return () => clearInterval(timer);
  }, [result]);

  const done = result !== null;
  const quotes = result?.skills.map((s) => s.quote) ?? [];

  return (
    <section className={`scanner glass${done ? " done" : ""}`} aria-live="polite">
      <div className="scan-doc" aria-hidden>
        <div className="scan-doc-name">{fileName}</div>
        <div className="scan-lines">
          {lines
            ? lines.map((line, i) => (
                <div key={i} className={`scan-line text${done && isHit(line, quotes) ? " hit" : ""}`}
                  style={{ "--i": i } as React.CSSProperties}>
                  <span>{line}</span>
                </div>
              ))
            : PLACEHOLDER.map((w, i) => (
                <div key={i} className={`scan-line bar${w === 0 ? " gap" : ""}${done && i % 4 === 1 ? " hit" : ""}`}
                  style={{ "--i": i, width: `${w}%` } as React.CSSProperties} />
              ))}
        </div>
        {!done && <div className="scan-beam" />}
      </div>

      <div className="scan-side">
        <span className="kicker">{done ? "Analysis complete" : "Analysing your CV"}</span>
        <ol className="scan-steps">
          {STEPS.map((label, i) => {
            const state = done || i < step ? "done" : i === step ? "active" : "todo";
            return (
              <li key={label} className={state}>
                <span className="scan-mark" aria-hidden />
                {label}
              </li>
            );
          })}
        </ol>
        {done && (
          <div className="scan-found">
            <strong>{result.skills.length}</strong> skills found
            {result.jobs.length > 0 && <> · <strong>{result.jobs.length}</strong> jobs mapped</>}
          </div>
        )}
      </div>
    </section>
  );
}
