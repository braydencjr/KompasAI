"use client";

import { useEffect, useRef, useState } from "react";
import CalendarTool from "./sim/CalendarTool";
import CodeTool from "./sim/CodeTool";
import DocTool from "./sim/DocTool";
import PerformanceReport from "./sim/PerformanceReport";
import PromptTool from "./sim/PromptTool";
import ReviewTool from "./sim/ReviewTool";
import SheetTool from "./sim/SheetTool";
import { FEELINGS, TOOL_LABEL, clock, initials } from "./sim/shared";
import type { SimSource } from "./SimulatorProvider";
import { isAiTask, quadrantOf, reviewFor, type Outcome, type SimResult, type Simulation } from "../data/simulations";

type Props = {
  sim: Simulation;
  source: SimSource;
  /** why the sample is showing, when AI generation failed */
  note?: string;
  onUseSample: () => void;
  onRegenerate: () => void;
  onClose: () => void;
  onFinish: (r: SimResult) => void;
};

const GENERATING = [
  "Reading the role and your skills…",
  "Writing your first-day inbox…",
  "Building the data for your tasks…",
  "Choosing an AI tool from this field…",
  "Planting mistakes for you to catch…",
  "Checking every answer works…",
];

function Generating({ onUseSample }: { onUseSample: () => void }) {
  const [i, setI] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setI((n) => (n + 1) % GENERATING.length), 2600);
    return () => clearInterval(t);
  }, []);
  return (
    <div className="sim-generating">
      <span className="ai-spark big gen-spin" aria-hidden>
        ✦
      </span>
      <div>
        <strong>Writing a day in this job for you</strong>
        <p className="muted small" aria-live="polite">
          {GENERATING[i]}
        </p>
      </div>
      <p className="muted small">This usually takes under a minute.</p>
      <button className="sim-link" onClick={onUseSample}>
        Skip and use a sample day instead
      </button>
    </div>
  );
}

export default function WorkSimulator({ sim, source, note, onUseSample, onRegenerate, onClose, onFinish }: Props) {
  // -1 = welcome, 0..n-1 = tasks, n = report
  const [step, setStep] = useState(-1);
  const [attempt, setAttempt] = useState(0);
  const [outcomes, setOutcomes] = useState<Outcome[]>([]);
  const [pending, setPending] = useState<{ score: number; evidence: string[]; seconds: number } | null>(null);
  const [enjoy, setEnjoy] = useState<number | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const startedAt = useRef(0);
  const dialogRef = useRef<HTMLDivElement>(null);

  const n = sim.tasks.length;
  const task = step >= 0 && step < n ? sim.tasks[step] : null;

  useEffect(() => {
    dialogRef.current?.focus();
    // capture phase so Esc closes only the simulator, not a roadmap open underneath
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      e.stopImmediatePropagation();
      onClose();
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [onClose]);

  useEffect(() => {
    dialogRef.current?.scrollTo({ top: 0, behavior: "smooth" });
    if (!task) return;
    startedAt.current = Date.now();
    setElapsed(0);
    const t = setInterval(() => setElapsed(Math.round((Date.now() - startedAt.current) / 1000)), 1000);
    return () => clearInterval(t);
  }, [task, attempt]);

  function taskDone(score: number, evidence: string[]) {
    setPending({ score, evidence, seconds: Math.round((Date.now() - startedAt.current) / 1000) });
  }

  function next() {
    if (!pending || enjoy === null) return;
    const all = [...outcomes, { ...pending, enjoy }];
    setOutcomes(all);
    setPending(null);
    setEnjoy(null);
    if (step < n - 1) {
      setStep(step + 1);
      return;
    }
    const can = Math.round((all.reduce((s, o) => s + o.score, 0) / n) * 100);
    const want = Math.round((all.reduce((s, o) => s + o.enjoy, 0) / (n * 2)) * 100);
    const low = all.reduce((lo, o, i) => (o.score < all[lo].score ? i : lo), 0);
    onFinish({
      can,
      want,
      quadrant: quadrantOf(can, want),
      weakest: all[low].score < 1 ? { skill: sim.tasks[low].competency, gap: sim.tasks[low].gap } : undefined,
      at: new Date().toISOString(),
    });
    setStep(n);
  }

  function restart() {
    setOutcomes([]);
    setPending(null);
    setEnjoy(null);
    setAttempt((a) => a + 1);
    setStep(0);
  }

  return (
    <div className="modal-backdrop sim-backdrop" onClick={onClose}>
      <div
        ref={dialogRef}
        tabIndex={-1}
        className={`modal sim glass${step === n ? " sim-report-mode" : ""}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby="sim-title"
        onClick={(e) => e.stopPropagation()}
      >
        <button className="modal-close" onClick={onClose} aria-label="Close simulation">
          ×
        </button>

        <header className="sim-head">
          <div className="plan-tags">
            <span className="label">Work simulation{source === "loading" ? "" : ` · ${sim.setting}`}</span>
            {source === "ai" && <span className="chip sim-source ai">✦ Written by AI for you</span>}
            {source === "sample" && <span className="chip sim-source">Sample scenario</span>}
            {task && <span className="chip chip-blue">⏱ {clock(pending ? pending.seconds : elapsed)}</span>}
          </div>
          <h2 id="sim-title">{sim.title}</h2>
          {source !== "loading" && (
            <ol className="sim-progress" aria-label="Progress" style={{ gridTemplateColumns: `repeat(${n}, 1fr)` }}>
              {sim.tasks.map((t, i) => (
                <li
                  key={t.id}
                  className={`${i < step ? "done" : i === step ? "current" : ""}${isAiTask(t) ? " ai" : ""}`}
                >
                  <span>{isAiTask(t) ? "✦" : i + 1}</span>
                  {t.title}
                </li>
              ))}
            </ol>
          )}
        </header>

        {step === -1 && source === "loading" && <Generating onUseSample={onUseSample} />}

        {step === -1 && source !== "loading" && (
          <div className="sim-intro">
            {note && <p className="sim-note">{note}</p>}
            <div className="sim-bubble">
              <span className="sim-avatar" aria-hidden>
                {initials(sim.welcome.from)}
              </span>
              <div>
                <div className="sim-from">{sim.welcome.from}</div>
                <p>{sim.welcome.text}</p>
              </div>
            </div>
            <p className="muted">
              It&apos;s your first day as {sim.title}. You&apos;ll do four real pieces of work in a mini workspace: two
              from the core of the job, and two using the AI tools now arriving in this field, because how this work
              gets done is changing. At the end you get a performance report.
            </p>
            {(["core", "ai"] as const).map((track) => (
              <div key={track} className="sim-plan-group">
                <div className="label">{track === "core" ? "Core work" : "✦ Working with AI"}</div>
                <ul className="sim-plan">
                  {sim.tasks.map((t, i) =>
                    isAiTask(t) === (track === "ai") ? (
                      <li key={t.id} className={track === "ai" ? "ai" : ""}>
                        <span className="sim-plan-n">{track === "ai" ? "✦" : i + 1}</span>
                        <div>
                          <strong>{t.title}</strong>
                          <span className="muted small">
                            {isAiTask(t) ? t.aiName : TOOL_LABEL[t.tool]} · ~{t.minutes} min · {t.competency}
                          </span>
                        </div>
                      </li>
                    ) : null,
                  )}
                </ul>
              </div>
            ))}
            <p className="muted small">Names, companies and figures are fictional.</p>
            <div className="sim-intro-actions">
              <button className="btn btn-primary" onClick={() => setStep(0)}>
                Start my first day →
              </button>
              <button className="sim-link" onClick={onRegenerate}>
                ✦ {source === "ai" ? "Generate a different scenario" : "Try generating one with AI"}
              </button>
            </div>
          </div>
        )}

        {task && (
          <div className="workspace" key={`${task.id}-${attempt}`}>
            <aside className="inbox">
              <div className="label">Inbox</div>
              <article className="sim-email">
                <div className="sim-email-head">
                  <span className="sim-avatar" aria-hidden>
                    {initials(task.from)}
                  </span>
                  <div>
                    <div className="sim-from">
                      {task.from} <span className="muted">· {task.fromRole}</span>
                    </div>
                    <strong className="sim-subject">{task.subject}</strong>
                  </div>
                </div>
                <p>{task.brief}</p>
              </article>
              {isAiTask(task) && (
                <div className="sim-why">
                  <div className="label">✦ Why this matters now</div>
                  <p>{task.why}</p>
                </div>
              )}
              <div className="sim-reqs">
                <div className="label">What&apos;s needed</div>
                <ul>
                  {task.requirements.map((r) => (
                    <li key={r}>{r}</li>
                  ))}
                </ul>
              </div>
            </aside>

            <div className="workspace-main">
              {task.tool === "sheet" && <SheetTool task={task} onDone={taskDone} />}
              {task.tool === "code" && <CodeTool task={task} onDone={taskDone} />}
              {task.tool === "doc" && <DocTool task={task} onDone={taskDone} />}
              {task.tool === "calendar" && <CalendarTool task={task} onDone={taskDone} />}
              {task.tool === "prompt" && <PromptTool task={task} field={sim.title} onDone={taskDone} />}
              {task.tool === "review" && <ReviewTool task={task} onDone={taskDone} />}

              {pending && (
                <div className="sim-after">
                  <div className="sim-bubble">
                    <span className="sim-avatar" aria-hidden>
                      {initials(task.from)}
                    </span>
                    <div>
                      <div className="sim-from">
                        {task.from} <span className="muted">· replied</span>
                      </div>
                      <p>{reviewFor(task, pending.score)}</p>
                    </div>
                  </div>
                  <ul className="sim-evidence">
                    {pending.evidence.map((e) => (
                      <li key={e}>{e}</li>
                    ))}
                  </ul>
                  <div className="sim-feel">
                    <div className="sim-question">Honestly, how did that task feel?</div>
                    <div className="sim-feel-row">
                      {FEELINGS.map((f, i) => (
                        <button
                          key={f}
                          className={`sim-feel-btn${enjoy === i ? " on" : ""}`}
                          onClick={() => setEnjoy(i)}
                          aria-pressed={enjoy === i}
                        >
                          {f}
                        </button>
                      ))}
                    </div>
                    <button className="btn btn-primary tool-submit" disabled={enjoy === null} onClick={next}>
                      {step === n - 1 ? "End the day: see my report →" : "Next task →"}
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {step === n && outcomes.length === n && (
          <PerformanceReport sim={sim} outcomes={outcomes} onRestart={restart} onClose={onClose} />
        )}
      </div>
    </div>
  );
}
