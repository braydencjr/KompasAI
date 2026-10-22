"use client";

import { useEffect, useRef, useState } from "react";
import { postJson } from "../../lib/api";
import { checkBrief, replyFor, type AiReply, type PromptTask } from "../../data/simulations";

type Props = { task: PromptTask; field: string; onDone: (score: number, evidence: string[]) => void };
/** live: answered by the real model through the backend; otherwise a scripted reply */
type Turn = { prompt: string; hits: boolean[]; reply: AiReply; live: boolean };

const MAX_TRIES = 3;
const THINK_MS = 900;

// once the backend says no, stay scripted for the rest of the session instead of waiting on it every time
let liveAvailable = true;

async function askAi(task: PromptTask, field: string, turns: Turn[], prompt: string) {
  if (liveAvailable) {
    try {
      const r = await postJson<{ reply: AiReply; covered: boolean[] }>("/api/simulations/brief", {
        ai_name: task.aiName,
        field,
        task: task.brief,
        rubric: task.rubric,
        history: turns.map((t) => ({ prompt: t.prompt, reply: t.reply.text })),
        prompt,
      });
      return { prompt, hits: r.covered, reply: r.reply, live: true };
    } catch {
      liveAvailable = false;
    }
  }
  await new Promise((r) => setTimeout(r, THINK_MS));
  const hits = checkBrief(task, prompt);
  return { prompt, hits, reply: replyFor(task, hits), live: false };
}

export default function PromptTool({ task, field, onDone }: Props) {
  const [draft, setDraft] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [thinking, setThinking] = useState(false);
  // characters of the latest reply shown so far, for the typing effect
  const [shown, setShown] = useState(0);
  const [done, setDone] = useState(false);
  const chatRef = useRef<HTMLDivElement>(null);

  const last = turns[turns.length - 1];
  const typing = !!last && shown < last.reply.text.length;

  useEffect(() => {
    if (!last || shown >= last.reply.text.length) return;
    const t = setTimeout(() => setShown((s) => s + 3), 12);
    return () => clearTimeout(t);
  }, [last, shown]);

  useEffect(() => {
    chatRef.current?.scrollTo({ top: chatRef.current.scrollHeight, behavior: "smooth" });
  }, [turns, thinking, shown]);

  async function send() {
    const prompt = draft.trim();
    if (!prompt || thinking || typing) return;
    setDraft("");
    setThinking(true);
    const turn = await askAi(task, field, turns, prompt);
    setTurns((t) => [...t, turn]);
    setShown(0);
    setThinking(false);
  }

  function submit() {
    const scores = turns.map((t) => t.hits.filter(Boolean).length / t.hits.length);
    const best = Math.max(...scores);
    const bestHits = turns[scores.indexOf(best)].hits.filter(Boolean).length;
    setDone(true);
    onDone(best, [
      `Best brief covered ${bestHits} of ${task.rubric.length} essentials`,
      turns.length > 1 && scores[scores.length - 1] > scores[0]
        ? `Improved the brief over ${turns.length} attempts`
        : `${turns.length} attempt${turns.length > 1 ? "s" : ""}`,
    ]);
  }

  const out = turns.length >= MAX_TRIES;

  return (
    <div className="tool tool-ai">
      <div className="tool-bar">
        <span className="tool-file ai-name">
          <span className="ai-spark" aria-hidden>✦</span> {task.aiName}
        </span>
        <span className="muted small">
          {last?.live ? "Live AI" : "Simulated AI"} · {Math.max(MAX_TRIES - turns.length, 0)} tries left
        </span>
      </div>

      <div className="ai-chat" ref={chatRef}>
        {turns.length === 0 && !thinking && (
          <div className="ai-empty">
            <span className="ai-spark big" aria-hidden>✦</span>
            <p>Hi, I&apos;m {task.aiName}. What do you need?</p>
            <span className="muted small">I only know what you put in your message.</span>
          </div>
        )}

        {turns.map((t, i) => {
          const latest = i === turns.length - 1;
          const text = latest ? t.reply.text.slice(0, shown) : t.reply.text;
          const complete = !latest || !typing;
          return (
            <div key={i} className="ai-turn">
              <div className="ai-msg user">{t.prompt}</div>
              <div className="ai-msg bot">
                <span className="ai-spark" aria-hidden>✦</span>
                <div>
                  <p>
                    {text}
                    {!complete && <span className="ai-caret" />}
                  </p>
                  {complete && t.reply.steps && (
                    <ol className="ai-steps">
                      {t.reply.steps.map((s) => (
                        <li key={s}>{s}</li>
                      ))}
                    </ol>
                  )}
                  {complete && t.reply.table && (
                    <div className="sheet-wrap">
                      <table className="tests">
                        <thead>
                          <tr>
                            {t.reply.table.columns.map((c) => (
                              <th key={c}>{c}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {t.reply.table.rows.map((r) => (
                            <tr key={r[0]}>
                              {r.map((c, j) => (
                                <td key={j}>{c}</td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                  {complete && t.reply.note && <p className="ai-note">{t.reply.note}</p>}
                </div>
              </div>
              {complete && (
                <div className="brief-check">
                  <span className="label">Your brief</span>
                  {task.rubric.map((r, j) => (
                    <span key={r.label} className={`brief-chip${t.hits[j] ? " hit" : ""}`}>
                      {t.hits[j] ? "✓" : "○"} {r.label}
                    </span>
                  ))}
                </div>
              )}
            </div>
          );
        })}

        {thinking && (
          <div className="ai-msg bot thinking">
            <span className="ai-spark" aria-hidden>✦</span>
            <span className="ai-dots" aria-label="Thinking">
              <i />
              <i />
              <i />
            </span>
          </div>
        )}
      </div>

      {!done && !out && (
        <div className="ai-composer">
          <textarea
            value={draft}
            rows={3}
            placeholder={turns.length ? "Refine your brief…" : `Brief ${task.aiName}…`}
            aria-label={`Message ${task.aiName}`}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) send();
            }}
          />
          <button className="btn btn-primary btn-sm" onClick={send} disabled={!draft.trim() || thinking || typing}>
            Send ↵
          </button>
        </div>
      )}

      {!done && turns.length > 0 && (
        <button className="btn btn-ghost tool-submit" onClick={submit} disabled={thinking || typing}>
          Use this result →
        </button>
      )}
    </div>
  );
}
