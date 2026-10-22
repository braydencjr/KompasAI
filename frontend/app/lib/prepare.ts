import { resolveSolutions } from "./sheet";
import { runInWorker } from "./runCode";
import type { Simulation } from "../data/simulations";

/**
 * Makes an AI-written simulation playable and checks it: spreadsheet answers are computed from the
 * AI's formulas (never its arithmetic), and code tasks must pass their own tests. Throws if anything fails.
 */
export async function prepareSimulation(sim: Simulation): Promise<Simulation> {
  const tasks = await Promise.all(
    sim.tasks.map(async (t) => {
      if (t.tool === "sheet") return { ...t, sheet: resolveSolutions(t.sheet) };
      if (t.tool === "code" && t.solution) {
        const r = await runInWorker(t, t.solution);
        if (r.error || !r.results?.every((x) => x.ok)) throw new Error(`"${t.title}" failed its own tests`);
      }
      return t;
    }),
  );
  return { ...sim, tasks };
}
