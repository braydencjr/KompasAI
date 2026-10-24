import type { SimTask } from "../../data/simulations";

export const FEELINGS = ["Drained me", "It was OK", "I enjoyed it"];

export const TOOL_LABEL: Record<SimTask["tool"], string> = {
  sheet: "Spreadsheet",
  code: "Code",
  doc: "Document",
  calendar: "Calendar",
  prompt: "AI assistant",
  review: "AI review",
};

const MAKES: Record<SimTask["tool"], string> = {
  sheet: "Build a spreadsheet and work out the answers",
  code: "Write a short function that passes its tests",
  doc: "Write a short document",
  calendar: "Plan a schedule that satisfies every constraint",
  prompt: "Brief an AI assistant until its answer is useful",
  review: "Check an AI draft and flag what's wrong",
};

/** the core of the task in plain words, whatever professional title it was given */
export const deliverableOf = (t: SimTask) => t.deliverable ?? MAKES[t.tool];

export const clock = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;

export function initials(name: string) {
  return name
    .split(" ")
    .map((w) => w[0])
    .slice(0, 2)
    .join("");
}
