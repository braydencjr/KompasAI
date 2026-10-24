"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import CalendarTool from "../sim/CalendarTool";
import CodeTool from "../sim/CodeTool";
import DocTool from "../sim/DocTool";
import PromptTool from "../sim/PromptTool";
import ReviewTool from "../sim/ReviewTool";
import SheetTool from "../sim/SheetTool";
import { clock, initials } from "../sim/shared";
import { ApiError, postJson } from "../../lib/api";
import { prepareSimulation } from "../../lib/prepare";
import { reviewFor, type SimTask } from "../../data/simulations";
import type { LearningPlan } from "../../lib/journey";

type Step = LearningPlan["steps"][number];
type Props = { role: string; step: Step; onPassed: () => void; onClose: () => void };
type State =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; task: SimTask };

/** passing a mini project marks its stop on The Route as done */
export const PASS = 0.7;

/** how many times a mini project is regenerated behind the loading screen before the user sees an error */
const MAX_TRIES = 3;

const LOADING = ["Reading what you studied…", "Writing a realistic brief…", "Preparing the data…", "Checking every answer works…"];

/** One stop's mini project: an AI-written task for that skill, done in the browser and checked automatically
 * (spreadsheet answers from formulas, code against tests, a document against a checklist). */
export default function PracticeModal({ role, step, onPassed, onClose }: Props) {
  const [state, setState] = useState<State>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);
  const [result, setResult] = useState<{ score: number; evidence: string[]; seconds: number } | null>(null);
  const [tick, setTick] = useState(0);
  const startedAt = useRef(Date.now());
  const dialogRef = useRef<HTMLDivElement>(null);

  const load = useCallback(
    async (fresh: boolean, signal?: AbortSignal) => {
      setState({ status: "loading" });
      setResult(null);
      // a generated project can fail its own checks: quietly write another one before bothering the user
      let lastError: unknown;
      for (let i = 0; i < MAX_TRIES; i++) {
        if (signal?.aborted) return;
        try {
          const task = await postJson<SimTask>(
            "/api/simulations/practice",
            { role, skill: step.label, goal: step.goal, learn: step.learn, project: step.practice, fresh: fresh || i > 0 },
            signal,
          );
          // the same checks as a generated simulation: sheet answers from formulas, code passes its own tests
          const [ready] = (await prepareSimulation({ roleId: "", title: "", setting: "", welcome: { from: "", text: "" }, tasks: [task] })).tasks;
          if (!signal?.aborted) {
            startedAt.current = Date.now();
            setState({ status: "ready", task: ready });
          }
          return;
        } catch (e) {
          if (signal?.aborted) return;
          lastError = e;
          if (e instanceof ApiError && e.status === 503) break; // not configured: retrying can't help
        }
      }
      const e = lastError;
      const message =
        e instanceof ApiError && e.status === 503 ? "AI isn't set up yet: add an API key in backend/.env."
          : "It took a few tries and still didn't come out right. Give it another go.";
      setState({ status: "error", message });
    },
    [role, step],
  );

  useEffect(() => {
    const ctrl = new AbortController();
    void load(false, ctrl.signal);
    return () => ctrl.abort();
  }, [load]);

  useEffect(() => {
    dialogRef.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    const main = document.querySelector<HTMLElement>(".main");
    const before = main?.style.overflow;
    if (main) main.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      if (main) main.style.overflow = before ?? "";
    };
  }, [onClose]);

  useEffect(() => {
    if (state.status !== "loading") return;
    const t = setInterval(() => setTick((n) => n + 1), 2600);
    return () => clearInterval(t);
  }, [state.status]);

  function done(score: number, evidence: string[]) {
    const r = { score, evidence, seconds: Math.round((Date.now() - startedAt.current) / 1000) };
    setResult(r);
    if (score >= PASS) onPassed();
  }

  function retry() {
    setResult(null);
    setAttempt((a) => a + 1);
    startedAt.current = Date.now();
  }

  const task = state.status === "ready" ? state.task : null;
  const passed = result && result.score >= PASS;

  return createPortal(
    <div className="modal-backdrop sim-backdrop" onClick={onClose}>
      <div ref={dialogRef} tabIndex={-1} className="modal sim glass" role="dialog" aria-modal="true"
        aria-labelledby="practice-title" onClick={(e) => e.stopPropagation()}>
        <button className="modal-close" onClick={onClose} aria-label="Close mini project">×</button>

        <header className="sim-head">
          <div className="plan-tags">
            <span className="label">Mini project · Stop {step.order}: {step.label}</span>
            {task && <span className="chip sim-source ai">✦ Written by AI · checked automatically</span>}
          </div>
          <h2 id="practice-title">{task ? task.title : `Mini project: ${step.label}`}</h2>
        </header>

        {state.status === "loading" && (
          <div className="sim-generating">
            <span className="ai-spark big gen-spin" aria-hidden>✦</span>
            <div>
              <strong>Writing your mini project</strong>
              <p className="muted small" aria-live="polite">{LOADING[tick % LOADING.length]}</p>
            </div>
            <p className="muted small">The first time takes a minute or two: every answer is checked before you see it.</p>
          </div>
        )}

        {state.status === "error" && (
          <div className="sim-intro">
            <p className="sim-note">Couldn&apos;t write the mini project: {state.message}</p>
            <div className="sim-intro-actions">
              <button className="btn btn-primary" onClick={() => void load(true)}>✦ Try again</button>
            </div>
          </div>
        )}

        {task && (
          <div className="workspace" key={attempt}>
            <aside className="inbox">
              <div className="label">Brief</div>
              <article className="sim-email">
                <div className="sim-email-head">
                  <span className="sim-avatar" aria-hidden>{initials(task.from)}</span>
                  <div>
                    <div className="sim-from">{task.from} <span className="muted">· {task.fromRole}</span></div>
                    <strong className="sim-subject">{task.subject}</strong>
                  </div>
                </div>
                <p>{task.brief}</p>
              </article>
              <div className="sim-reqs">
                <div className="label">What counts as done</div>
                <ul>{task.requirements.map((r) => <li key={r}>{r}</li>)}</ul>
              </div>
              <p className="muted small">About {task.minutes} minutes. Pass with {Math.round(PASS * 100)}% to complete this stop.</p>
            </aside>

            <div className="workspace-main">
              {task.tool === "sheet" && <SheetTool task={task} onDone={done} />}
              {task.tool === "code" && <CodeTool task={task} onDone={done} />}
              {task.tool === "doc" && <DocTool task={task} onDone={done} />}
              {task.tool === "calendar" && <CalendarTool task={task} onDone={done} />}
              {task.tool === "prompt" && <PromptTool task={task} field={step.label} onDone={done} />}
              {task.tool === "review" && <ReviewTool task={task} onDone={done} />}

              {result && (
                <div className={`practice-result${passed ? " pass" : ""}`}>
                  <div className="practice-score">
                    <strong>{Math.round(result.score * 100)}%</strong>
                    <span>{passed ? "Passed · stop completed" : `Not yet · ${Math.round(PASS * 100)}% to pass`}</span>
                  </div>
                  <div className="sim-bubble">
                    <span className="sim-avatar" aria-hidden>{initials(task.from)}</span>
                    <div>
                      <div className="sim-from">{task.from} <span className="muted">· replied</span></div>
                      <p>{reviewFor(task, result.score)}</p>
                    </div>
                  </div>
                  <ul className="sim-evidence">
                    {[...result.evidence, `Took ${clock(result.seconds)}`].map((e) => <li key={e}>{e}</li>)}
                  </ul>
                  <div className="sim-intro-actions">
                    {passed ? (
                      <button className="btn btn-primary" onClick={onClose}>Back to my route →</button>
                    ) : (
                      <button className="btn btn-primary" onClick={retry}>Try again</button>
                    )}
                    <button className="sim-link" onClick={() => void load(true)}>✦ Give me a different project</button>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>,
    document.body,
  );
}
