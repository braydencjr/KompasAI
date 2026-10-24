import type { SimTask } from "../../data/simulations";
import { isInput } from "../../lib/sheet";

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

/** What's on the learner's screen, as text for the coach. Answer cells are hidden, so the coach can't leak them. */
export function materialOf(t: SimTask): string {
  switch (t.tool) {
    case "sheet":
      return [
        `Spreadsheet "${t.sheet.name}". Columns: ${t.sheet.columns.map((c) => c.label).join(" | ")}`,
        ...t.sheet.rows.map((r, i) => `Row ${i + 2}: ${r.map((c) => (isInput(c) ? "[to fill in]" : String(c))).join(" | ")}`),
      ].join("\n");
    case "code":
      return `Function ${t.fn}. Starter code:\n${t.starter}\nTests: ${t.tests.map((x) => `${x.label}: ${JSON.stringify(x.args)} -> ${JSON.stringify(x.expected)}`).join("; ")}`;
    case "doc":
      return `Writing ${t.words[0]}-${t.words[1]} words in "${t.docName}". Starts with:\n${t.template}\nIt will be checked for: ${t.checklist.map((c) => c.label).join("; ")}`;
    case "calendar":
      return `Meetings to place: ${t.events.map((e) => `${e.title} (${e.people.join(", ")}${e.deadline ? `, by ${e.deadline.label}` : ""})`).join("; ")}`;
    case "prompt":
      return `The learner is briefing ${t.aiName}. A good brief covers: ${t.rubric.map((r) => r.label).join("; ")}`;
    default:
      return "";
  }
}
