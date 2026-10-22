"use client";

import { useRef } from "react";
import { useProfile } from "./Profile";

const ACCEPT = ".pdf,.docx,.txt,.md";

/** The upload bar. The resulting profile shows in section 01. */
export default function CvUpload() {
  const { source, cv, scan, error, analyse, reset } = useProfile();
  const input = useRef<HTMLInputElement>(null);
  // a scan stays after it finishes (the reading flow plays it through); only one without a result is still busy
  const busy = scan && !scan.result ? scan.name : null;

  async function trySample() {
    const text = await (await fetch("/sample-cv.txt")).text();
    analyse(new File([text], "sample-cv.txt", { type: "text/plain" }));
  }

  return (
    <section className="upload glass">
      <div className="upload-row">
      <div className={`upload-icon${busy ? " busy" : ""}`}>
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden>
          <path d="M12 16V4m0 0-4 4m4-4 4 4M5 20h14" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </div>
      <div className="upload-text">
        <h3>{busy ? `Analysing ${busy}…` : source === "cv" ? `Profile from ${cv?.file ?? "your CV"}` : "Upload your resume"}</h3>
        <p>
          {error ? (
            <span className="upload-error">{error}</span>
          ) : busy ? (
            "Finding your skills and the jobs they belong to. This takes a few seconds."
          ) : source === "cv" ? (
            "Your skills and how they're doing in the market, read from this CV. The file was never stored."
          ) : (
            "PDF, DOCX or TXT, up to 5 MB. Read in memory and never stored. We never use age, gender or photos."
          )}
        </p>
        {busy && <div className="upload-progress" />}
      </div>
      <div className="upload-actions">
        {source === "cv" ? (
          <button className="btn btn-ghost" onClick={reset} disabled={!!busy}>Back to sample</button>
        ) : (
          <button className="btn btn-ghost" onClick={trySample} disabled={!!busy}>Try a sample</button>
        )}
        <button className="btn btn-primary" onClick={() => input.current?.click()} disabled={!!busy}>
          {source === "cv" ? "Upload another" : "Upload file"}
        </button>
        <input
          ref={input}
          type="file"
          accept={ACCEPT}
          hidden
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) analyse(f);
            e.target.value = "";
          }}
        />
      </div>
      </div>
    </section>
  );
}
