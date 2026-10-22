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

export const clock = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;

export function initials(name: string) {
  return name
    .split(" ")
    .map((w) => w[0])
    .slice(0, 2)
    .join("");
}
