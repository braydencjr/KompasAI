"use client";

import { useState } from "react";
import { runInWorker, type TestResult } from "../../lib/runCode";
import type { CodeTask } from "../../data/simulations";

type Props = { task: CodeTask; onDone: (score: number, evidence: string[]) => void };

const show = (v: unknown) => JSON.stringify(v);

export default function CodeTool({ task, onDone }: Props) {
  const [code, setCode] = useState(task.starter);
  const [results, setResults] = useState<TestResult[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [runs, setRuns] = useState(0);
  const [running, setRunning] = useState(false);
  const [done, setDone] = useState(false);

  async function run() {
    setRunning(true);
    const r = await runInWorker(task, code);
    setRunning(false);
    setRuns((n) => n + 1);
    setError(r.error ?? null);
    setResults(r.results ?? null);
    return r;
  }

  async function submit() {
    const r = await run();
    const passed = r.results?.filter((t) => t.ok).length ?? 0;
    setDone(true);
    onDone(passed / task.tests.length, [
      `${passed} of ${task.tests.length} test cases pass`,
      `Ran the tests ${runs + 1} time${runs ? "s" : ""} before submitting`,
    ]);
  }

  const passed = results?.filter((t) => t.ok).length ?? 0;

  return (
    <div className="tool tool-code">
      <div className="tool-bar">
        <span className="tool-file">{"</>"} {task.fn}.js</span>
        <span className="muted small">
          Helpers: {task.helpers.map((h) => h.signature).join(", ")}
        </span>
      </div>

      <textarea
        className="code-editor"
        value={code}
        readOnly={done}
        spellCheck={false}
        rows={Math.max(12, code.split("\n").length + 1)}
        aria-label="Code editor"
        onChange={(e) => setCode(e.target.value)}
        onKeyDown={(e) => {
          if (e.key !== "Tab") return;
          e.preventDefault();
          const el = e.currentTarget;
          const { selectionStart: s, selectionEnd: end } = el;
          setCode(code.slice(0, s) + "  " + code.slice(end));
          requestAnimationFrame(() => el.setSelectionRange(s + 2, s + 2));
        }}
      />

      <div className="code-actions">
        <button className="btn btn-ghost btn-sm" onClick={run} disabled={running || done}>
          {running ? "Running…" : "▶ Run tests"}
        </button>
        {results && (
          <span className={`code-summary${passed === task.tests.length ? " all" : ""}`}>
            {passed}/{task.tests.length} passing
          </span>
        )}
      </div>

      {error && <pre className="code-error">{error}</pre>}

      <div className="sheet-wrap">
        <table className="tests">
          <thead>
            <tr>
              <th />
              <th>Case</th>
              <th>Input</th>
              <th>Expected</th>
              <th>Your output</th>
            </tr>
          </thead>
          <tbody>
            {task.tests.map((t, i) => {
              const r = results?.[i];
              return (
                <tr key={t.label} className={r ? (r.ok ? "pass" : "fail") : ""}>
                  <td className="test-mark">{r ? (r.ok ? "✓" : "✗") : "·"}</td>
                  <td>{t.label}</td>
                  <td className="mono">{t.args.map(show).join(", ")}</td>
                  <td className="mono">{show(t.expected)}</td>
                  <td className="mono">{r?.out ?? "–"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {!done && (
        <button className="btn btn-primary tool-submit" onClick={submit} disabled={running || runs === 0}>
          {runs === 0 ? "Run the tests first" : "Submit to " + task.from.split(" ")[0]}
        </button>
      )}
    </div>
  );
}
