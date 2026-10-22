import type { CodeTask } from "../data/simulations";

export type TestResult = { ok: boolean; out: string };

const TIMEOUT_MS = 1500;

// runs in a throwaway worker so a broken loop can't freeze the page
const WORKER = `self.onmessage = (e) => {
  const { code, fn, helpers, tests } = e.data;
  let f;
  try {
    f = new Function(helpers + "\\n" + code + "\\n;return " + fn + ";")();
    if (typeof f !== "function") throw new Error(fn + " is not a function");
  } catch (err) {
    self.postMessage({ error: String(err && err.message || err) });
    return;
  }
  self.postMessage({
    results: tests.map((t) => {
      try {
        const out = f(...t.args);
        return { ok: JSON.stringify(out) === JSON.stringify(t.expected), out: JSON.stringify(out) ?? "undefined" };
      } catch (err) {
        return { ok: false, out: "Error: " + (err && err.message || err) };
      }
    }),
  });
};`;

/** Runs `code` against the task's tests in a worker; also used to check AI-written solutions. */
export function runInWorker(task: CodeTask, code: string) {
  return new Promise<{ results?: TestResult[]; error?: string }>((resolve) => {
    const url = URL.createObjectURL(new Blob([WORKER], { type: "text/javascript" }));
    const worker = new Worker(url);
    const finish = (r: { results?: TestResult[]; error?: string }) => {
      clearTimeout(timer);
      worker.terminate();
      URL.revokeObjectURL(url);
      resolve(r);
    };
    const timer = setTimeout(() => finish({ error: "Your code took too long. Is there an endless loop?" }), TIMEOUT_MS);
    worker.onmessage = (e) => finish(e.data);
    worker.onerror = (e) => finish({ error: e.message });
    worker.postMessage({ code, fn: task.fn, helpers: task.helpers.map((h) => h.source).join("\n"), tests: task.tests });
  });
}
