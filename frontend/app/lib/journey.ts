// Client for the user journey (PRD 5): The Mirror, Ghost CV, Three Bets, The Route and The Ping.
// Everything is computed by the backend from a snapshot; the browser only holds the user's choices.

import { API_URL } from "./kompas";
import type { LiveStatus } from "./kompas";

export type Scenario = "moderate" | "fast";
export type Pile = "exposed" | "human";
export type BetKind = "safe" | "rising" | "impact";

export type Sdg = { sdg: number; name: string; target?: string | null; rationale?: string | null; origin?: "curated" | "ai" | "default" };

export type Catalog = {
  latest_snapshot: string;
  snapshots: { id: string; as_of: string }[];
  /** aliases: what people call jobs in this group (ESCO names), for the job search */
  occupations: { isco: string; title: string; occupation: string; aliases?: string[]; esco_occupation: string | null; tasks: number; mycol: string | null }[];
  sdgs: Sdg[];
  skills: { id: string; label: string }[];
  scenarios: { id: Scenario; label: string }[];
  rules: Record<string, string>;
};

export type Capability = { id: string; label: string; status: LiveStatus; status_now: LiveStatus; score: number; rationale: string };

export type Horizon = "now" | "moderate" | "fast";

export type TaskCard = {
  id: string;
  task: string;
  pile: Pile;
  auto_pile: Pile;
  score: number;
  /** when AI can take the task over: today, by 2028 under moderate progress, only if AI moves fast, or not yet */
  when: Horizon | "never";
  scores: Record<Horizon, number>;
  capabilities: Capability[];
  reason: string;
  override: { pile: Pile; reason: string } | null;
};

export type Mirror = {
  occupation: string | null;
  title: string | null;
  esco_occupation: string | null;
  esco_uri: string | null;
  cards: TaskCard[];
  exposed_share: number;
  /** share of tasks AI could do today, by 2028 under moderate progress, and if AI moves fast */
  shares: Record<Horizon, number>;
  exposed_capabilities: string[];
  exposed_task_count?: number;
  total_task_count?: number;
};

export type GhostLine = {
  id: string; label: string; status: LiveStatus; status_now: LiveStatus; evidence: string; state: "solid" | "faded";
  /** by the horizon: worth more, holds its value, fades, or is work AI takes over under the scenario */
  trend: "up" | "hold" | "fade" | "ai";
  /** the AI capabilities taking over its work, and why */
  ai?: { id: string; label: string; why: string }[];
  /** the LLM's reason, for a skill the data is silent on */
  why?: string | null;
};
export type GhostSlot = {
  id: string; label: string; status: LiveStatus; status_now: LiveStatus; state: "blank" | "filled";
  /** the role that needs it, when it came from a role's gaps */
  for_role: string | null;
  /** why it's on your CV: "Needed for Accountant", "Rising in finance and accounting", "Rising across the market" */
  why: string;
};
export type Ghost = { lines: GhostLine[]; slots: GhostSlot[]; horizon: string; filled: number };

export type SkillRow = {
  id: string;
  label: string;
  importance: number;
  status: LiveStatus;
  /** false when no snapshot has measured this skill yet, so `status` is only the Stable default */
  measured: boolean;
  weight: number;
  coverage: number;
  evidence: string | null;
  /** the SDGs Kompas has mapped for this skill (others are asked for when shown) */
  sdgs?: Sdg[];
};

export type Evidence =
  | { type: "quote"; label: string; text: string }
  | { type: "source"; label: string; text: string }
  | ({ type: "signal"; skill?: string } & SignalItem);

export type SignalItem = { title: string; url: string; date: string; source: string; value: number | null; value_label: string | null };

export type Reason = { kind: "fit" | "demand" | "trend" | "ai" | "sdg" | "gap"; title: string; text: string; evidence: Evidence[] };

export type RoleScore = {
  isco: string;
  title: string;
  occupation: string;
  match: number;
  breakdown: SkillRow[];
  have: SkillRow[];
  gaps: SkillRow[];
  demand: number;
  mycol: string | null;
  safe_share: number;
  sdgs: Sdg[];
  alignment: number;
  covered: boolean;
  family?: { id: string; label: string } | null;
  family_status: LiveStatus | null;
  /** on CV roles: why this role, each reason with its evidence */
  reasons?: Reason[];
  /** share of the role's ESCO tasks that are AI-exposed, with your Mirror corrections */
  ai_exposure: number | null;
  scores: Record<BetKind, number | null>;
  // on bets only
  trend?: number[];
  growth?: number;
  trend_from?: string | null;
  route?: Route | null;
};

export type EmptyBet = { role: null; closest: { isco: string; title: string; match: number } | null };
export type Bet = RoleScore | EmptyBet;
export const isBet = (b: Bet | undefined): b is RoleScore => !!b && "isco" in b;

export type RouteStep = {
  order: number;
  id: string;
  label: string;
  status: LiveStatus;
  status_now: LiveStatus;
  prerequisite_for: string[];
  why: string;
  evidence_count: number;
  resource: { title: string; provider: string; url: string; hours: number; cost: string; language: string; hrdc_verified: boolean; checked: string } | null;
  alternatives: number;
  sdgs: Sdg[];
  completed: boolean;
};

export type Route = {
  role: { isco: string; title: string; match: number };
  steps: RouteStep[];
  hours: number;
  hours_left: number;
  weeks: number | null;
  pace: number;
  done: number;
  sdg_contribution: { sdg: number; name: string; steps: string[] }[];
};

export type Journey = {
  snapshot: { id: string; as_of: string };
  scenario: Scenario;
  sdgs: number[];
  mirror: Mirror;
  ghost: Ghost;
  bets: Record<BetKind, Bet>;
  /** Your Kompas's two columns: the top jobs per kind; stretch = below the bar, the closest that fits */
  suggestions?: Record<"rising" | "safe", { isco: string; stretch: boolean }[]>;
  roles: RoleScore[];
  route: Route | null;
  /** staying in the current job, as an option beside the switches */
  stay: StayOption | null;
  /** lead with staying or switching, from how much of the job AI can do by 2028 */
  direction: { level: "low" | "medium" | "high"; lead: "stay" | "either" | "switch" };
  feed_profile: { skills: { id: string }[]; route: string[]; exposed: string[] };
};

export type StayOption = {
  isco: string;
  title: string;
  match: number | null;
  family: { id: string; label: string } | null;
  family_status: LiveStatus | null;
  shares: Record<Horizon, number>;
  /** rising skills that strengthen the current job */
  learn: string[];
  reasons: Reason[];
};

export type Ping = {
  from: { id: string; as_of: string };
  to: { id: string; as_of: string };
  skills: { id: string; label: string; from: LiveStatus; to: LiveStatus; projected_from: LiveStatus; projected_to: LiveStatus; reason: string }[];
  bets: { kind: BetKind; from: { title: string; match: number } | null; to: { title: string; match: number } | null }[];
  route: { from: string[]; to: string[]; changed: boolean; labels: Record<string, string> };
  ghost: { new_slots: { id: string; label: string }[]; gone_slots: { id: string; label: string }[] };
  mirror: { from: number; to: number };
  changed: boolean;
  journey: Journey;
};

export type Brief = { text: string; by: string; note?: string };

/** What the backend needs: the user's choices. */
export type JourneyRequest = {
  skills: { id: string; evidence?: "claimed" | "demonstrated" }[];
  occupation: string | null;
  overrides: Record<string, { pile: Pile; reason: string }>;
  scenario: Scenario;
  sdgs: number[];
  role: string | null;
  completed: string[];
  pace: number;
  snapshot: string | null;
};

async function post<T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> {
  try {
    const res = await fetch(`${API_URL}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal,
    });
    const data = await res.json().catch(() => null);
    if (!res.ok) throw new Error(typeof data?.detail === "string" ? data.detail : `Request failed (${res.status})`);
    return data as T;
  } catch (err: unknown) {
    if (signal?.aborted || (err instanceof Error && (err.name === "AbortError" || err.name === "TimeoutError"))) {
      return null as unknown as T;
    }
    throw err;
  }
}

export type PlanCourse = {
  id: string; title: string; provider: string; platform: string; url: string; workload: string | null;
  /** from a free learning site (costs nothing) */
  free?: boolean;
};

/** The Route as an AI learning plan (POST /journey/plan): Gemini's advice per step, courses from Coursera's catalogue */
export type LearningPlan = {
  role: { isco: string; title: string };
  summary: string;
  steps: {
    id: string;
    label: string;
    status: LiveStatus;
    order: number;
    goal: string;
    learn: string[];
    practice: string;
    weeks: number;
    courses: PlanCourse[];
    course_note: string;
    /** the rule-based route's course for this step, shown when the search found none */
    resource: RouteStep["resource"];
  }[];
  weeks: number;
  by: string;
  courses_from: string | null;
  note: string | null;
  cached: boolean;
};

export const journeyApi = {
  catalog: async (): Promise<Catalog> => {
    const res = await fetch(`${API_URL}/journey/catalog`);
    if (!res.ok) throw new Error(res.status === 503 ? "No snapshot yet: run `kompas snapshot` in backend/." : `Request failed (${res.status})`);
    return res.json();
  },
  build: (req: JourneyRequest, signal?: AbortSignal) => post<Journey>("/journey", req, signal),
  ping: (req: JourneyRequest & { from_snapshot: string; to_snapshot: string | null }, signal?: AbortSignal) =>
    post<Ping>("/journey/ping", req, signal),
  brief: (req: JourneyRequest & { kind: "bets" | "ping"; from_snapshot?: string | null }, signal?: AbortSignal) =>
    post<Brief>("/journey/brief", req, signal),
  plan: (req: JourneyRequest, signal?: AbortSignal) => post<LearningPlan>("/journey/plan", req, signal),
};

export type ConceptDetail = {
  snapshot: string;
  id: string;
  label: string;
  kind: string | null;
  status: LiveStatus;
  family_status: LiveStatus | null;
  projected: Record<Scenario, LiveStatus>;
  rungs: Record<"1" | "2" | "3", { active: boolean; declining: boolean; trend: number | null; low_confidence: boolean; sources: string[]; active_sources: string[]; level: "concept" | "family" | "group"; groups?: string[] }>;
};

export type EvidenceItem = {
  id: string;
  source: string;
  kind: string;
  title: string;
  url: string | null;
  published_at: string;
  value: number | null;
  value_label: string | null;
  coverage_note: string | null;
  /** with a task: one sentence on how this record bears on it */
  why?: string | null;
};

/** The Signal Ladder view for one skill (PRD 5.3): status, rungs and the evidence behind them. */
export type LadderTask = { label: string; task: string; why: string };

export async function ladder(
  id: string, snapshot: string | null, task?: LadderTask,
): Promise<{ concept: ConceptDetail; evidence: EvidenceItem[]; specific?: boolean; overall?: EvidenceItem[] }> {
  const q = snapshot ? `?snapshot=${encodeURIComponent(snapshot)}` : "";
  // with a task, the backend returns only the records that bear on it
  const forTask = task ? `${q ? "&" : "?"}task=${encodeURIComponent(task.task)}&why=${encodeURIComponent(task.why)}` : "";
  const [c, e] = await Promise.all([fetch(`${API_URL}/concepts/${id}${q}`), fetch(`${API_URL}/concepts/${id}/evidence${q}${forTask}`)]);
  if (!c.ok) throw new Error(`No ladder data for this skill (${c.status})`);
  const body = e.ok ? await e.json() : { evidence: [] };
  return { concept: await c.json(), evidence: body.evidence, specific: task ? body.specific : undefined, overall: task ? body.overall : undefined };
}
