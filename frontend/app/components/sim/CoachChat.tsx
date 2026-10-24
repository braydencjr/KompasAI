"use client";

import { useEffect, useRef, useState } from "react";
import { ApiError, postJson } from "../../lib/api";
import type { SimTask } from "../../data/simulations";
import { initials, materialOf } from "./shared";

type Turn = { prompt: string; reply: string };
type Props = { task: SimTask; evidence?: string[] };

/** Ask the sender how to do the task. They explain the method and never hand over the answer. */
export default function CoachChat({ task, evidence = [] }: Props) {
  const [open, setOpen] = useState(false);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const logRef = useRef<HTMLDivElement>(null);
  const first = task.from.split(" ")[0];

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: "smooth" });
  }, [turns.length, busy]);

  async function ask(question: string) {
    const q = question.trim();
    if (!q || busy) return;
    setBusy(true);
    setError(null);
    setDraft("");
    try {
      const r = await postJson<{ reply: string }>("/api/simulations/coach", {
        sender: task.from, sender_role: task.fromRole, title: task.title, brief: task.brief,
        requirements: task.requirements, material: materialOf(task), evidence,
        history: turns, question: q,
      });
      setTurns((t) => [...t, { prompt: q, reply: r.reply }]);
    } catch (e) {
      setDraft(q);
      setError(e instanceof ApiError && e.status === 503 ? "The AI helper isn't set up yet." : "Couldn't reach the helper. Try again.");
    } finally {
      setBusy(false);
    }
  }

  if (!open) {
    return (
      <button className="coach-open" onClick={() => setOpen(true)}>
        <span className="ai-spark" aria-hidden>✦</span> Stuck? Ask {first} how to do it
      </button>
    );
  }

  const ideas = ["Where do I start?", "What does this mean?", ...(evidence.length ? ["Why was it marked wrong?"] : [])];

  return (
    <section className="coach" aria-label={`Ask ${first} for help`}>
      <header className="coach-head">
        <span className="sim-avatar" aria-hidden>{initials(task.from)}</span>
        <div>
          <strong>Ask {first}</strong>
          <span className="muted small"> · explains how, so you can do it yourself</span>
        </div>
        <button className="sim-link" onClick={() => setOpen(false)}>Hide</button>
      </header>

      <div className="coach-log" ref={logRef} aria-live="polite">
        {!turns.length && <p className="muted small">Ask anything about this task. I&apos;ll point you in the right direction without giving the answer away.</p>}
        {turns.map((t, i) => (
          <div key={i} className="coach-turn">
            <p className="coach-you">{t.prompt}</p>
            <p className="coach-them">{t.reply}</p>
          </div>
        ))}
        {busy && <p className="coach-them muted">{first} is typing…</p>}
      </div>

      {!turns.length && (
        <div className="coach-ideas">
          {ideas.map((x) => <button key={x} className="chip" onClick={() => void ask(x)} disabled={busy}>{x}</button>)}
        </div>
      )}
      {error && <p className="sim-note">{error}</p>}
      <form className="coach-form" onSubmit={(e) => { e.preventDefault(); void ask(draft); }}>
        <input value={draft} onChange={(e) => setDraft(e.target.value)} maxLength={600}
          placeholder={`Ask ${first}…`} aria-label={`Ask ${first} a question`} />
        <button className="btn btn-primary" type="submit" disabled={busy || !draft.trim()}>Send</button>
      </form>
    </section>
  );
}
