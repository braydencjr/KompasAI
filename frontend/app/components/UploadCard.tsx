"use client";

import { useRef, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const MAX_BYTES = 5 * 1024 * 1024;

type UploadResult = {
  filename: string;
  pages: number;
  text: string;
  chars: number;
  warnings: string[];
};

type State =
  | { status: "idle" }
  | { status: "uploading"; filename: string }
  | { status: "done"; result: UploadResult }
  | { status: "error"; message: string };

export default function UploadCard() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [state, setState] = useState<State>({ status: "idle" });
  const [dragging, setDragging] = useState(false);

  async function upload(file: File) {
    if (file.type !== "application/pdf" && !file.name.toLowerCase().endsWith(".pdf")) {
      setState({ status: "error", message: "Please choose a PDF file. Other formats are coming soon." });
      return;
    }
    if (file.size > MAX_BYTES) {
      setState({ status: "error", message: "That file is larger than 5 MB." });
      return;
    }

    setState({ status: "uploading", filename: file.name });
    const form = new FormData();
    form.append("file", file);

    try {
      const res = await fetch(`${API_URL}/api/upload`, { method: "POST", body: form });
      const body = await res.json().catch(() => null);
      if (!res.ok) {
        setState({ status: "error", message: body?.detail ?? `Upload failed (${res.status}).` });
        return;
      }
      setState({ status: "done", result: body as UploadResult });
    } catch {
      setState({ status: "error", message: `Can't reach the Kompas server at ${API_URL}. Is the backend running?` });
    }
  }

  async function trySample() {
    const res = await fetch("/sample-cv.pdf");
    const blob = await res.blob();
    upload(new File([blob], "sample-cv.pdf", { type: "application/pdf" }));
  }

  function pick() {
    inputRef.current?.click();
  }

  const busy = state.status === "uploading";

  return (
    <section
      className={`upload glass${dragging ? " dragging" : ""}${state.status === "done" ? " uploaded" : ""}`}
      onDragOver={(e) => {
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragging(false);
        const file = e.dataTransfer.files[0];
        if (file && !busy) upload(file);
      }}
    >
      <input
        ref={inputRef}
        type="file"
        accept="application/pdf,.pdf"
        hidden
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) upload(file);
          e.target.value = "";
        }}
      />

      <div className="upload-row">
        <div className={`upload-icon${busy ? " spinning" : ""}`}>
          {state.status === "done" ? (
            <span aria-hidden>✓</span>
          ) : (
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden>
              <path d="M12 16V4m0 0-4 4m4-4 4 4M5 20h14" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          )}
        </div>

        <div className="upload-text" aria-live="polite">
          {state.status === "idle" && (
            <>
              <h3>Upload your resume</h3>
              <p>Drop a PDF here or choose a file, up to 5 MB. We never use age, gender or photos.</p>
            </>
          )}
          {state.status === "uploading" && (
            <>
              <h3>Reading {state.filename}…</h3>
              <p>Extracting the text from your resume.</p>
            </>
          )}
          {state.status === "done" && (
            <>
              <h3>{state.result.filename}</h3>
              <p>
                {state.result.pages} page{state.result.pages === 1 ? "" : "s"} · {state.result.chars.toLocaleString()} characters read
              </p>
            </>
          )}
          {state.status === "error" && (
            <>
              <h3>Couldn&apos;t read that file</h3>
              <p className="upload-error">{state.message}</p>
            </>
          )}
        </div>

        <div className="upload-actions">
          {state.status !== "done" && (
            <button className="btn btn-ghost" onClick={trySample} disabled={busy}>
              Try a sample
            </button>
          )}
          <button className="btn btn-primary" onClick={pick} disabled={busy}>
            {busy ? "Uploading…" : state.status === "done" ? "Replace file" : "Upload file"}
          </button>
        </div>
      </div>

      {state.status === "done" && (
        <div className="upload-result">
          {state.result.warnings.map((w) => (
            <p key={w} className="upload-warning">⚠ {w}</p>
          ))}
          {state.result.text && (
            <details className="upload-text-preview">
              <summary>View extracted text</summary>
              <pre>{state.result.text}</pre>
            </details>
          )}
        </div>
      )}
    </section>
  );
}
