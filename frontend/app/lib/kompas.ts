// Client for the Kompas signal API: the signal engine (backend/pipeline), served by the main backend under
// /api/signals. Every call returns null when the API is unreachable, so the UI can fall back to the sample
// data in app/data/bets.ts.

import { API_URL as BACKEND_URL } from "./api";
import type { RoleScore, SignalItem } from "./journey";

export const API_URL = `${BACKEND_URL}/api/signals`;

export type LiveStatus = "Watch" | "Emerging" | "Act now" | "Stable" | "Declining" | "Stalled";

type Rung = { active: boolean; low_confidence: boolean; level: "concept" | "family"; sources: string[] };

export type ConceptStatus = {
  id: string;
  label: string;
  status: LiveStatus;
  family_id: string | null;
  family_status: LiveStatus | null;
  projected: { moderate: LiveStatus; fast: LiveStatus };
  rungs: Record<"1" | "2" | "3", Rung>;
};

export type Health = {
  latest_snapshot: { id: string; created_at: string } | null;
  live: boolean;
  sources: { id: string; data_as_of: string | null; running_since: string | null }[];
};

export type FeedItem = {
  artifact_id: string;
  source: string;
  kind: "story" | "repo";
  title: string;
  url: string;
  published_at: string;
  momentum: number;
  momentum_raw: number;
  momentum_label: string;
  points?: number; // Hacker News upvotes
  stars?: number; // GitHub stars
  description?: string; // repo description
};

/** One explained card in the personal feed: a skill, what's happening, what it means, what to do. */
export type SignalCard = {
  concept_id: string;
  label: string;
  status: LiveStatus;
  relation: "exposed" | "route" | "have" | "related";
  relation_label: string;
  headline: string;
  meaning: string;
  action: string;
  /** Hiring steps reached; "talked about" is implied by the card existing. */
  ladder: { abroad: boolean; malaysia: "concept" | "family" | null; family_label: string | null };
  items: FeedItem[];
};

export type Change = { concept_id: string; label: string; field: string; from: string | null; to: string | null; reason: string };

export type Match = { snapshot: string; summary: string; signals: SignalCard[]; ping: Change[] };

export type Profile = {
  skills: { id: string; evidence?: "claimed" | "demonstrated" }[];
  route: string[];
  exposed: string[];
  limit?: number;
};

async function call<T>(path: string, init?: RequestInit): Promise<T | null> {
  try {
    const res = await fetch(`${API_URL}${path}`, { signal: AbortSignal.timeout(5000), ...init });
    return res.ok ? ((await res.json()) as T) : null;
  } catch {
    return null;
  }
}

export const kompas = {
  health: () => call<Health>("/health"),
  concepts: () => call<{ snapshot: string; concepts: ConceptStatus[] }>("/concepts"),
  match: (profile: Profile) =>
    call<Match>("/match", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(profile) }),
};

/** ["professional", "technician", "clerical"] -> "professional, technician and clerical" */
export function listWords(words: string[]): string {
  return words.length < 2 ? words.join("") : `${words.slice(0, -1).join(", ")} and ${words[words.length - 1]}`;
}

/** Subscribes to new and rising feed items. Returns an unsubscribe function. */
export function onFeedEvent(handler: (artifactId: string) => void): () => void {
  if (typeof EventSource === "undefined") return () => {};
  const es = new EventSource(`${API_URL}/feed/stream`);
  const listener = (e: MessageEvent) => {
    try {
      handler(JSON.parse(e.data).item.artifact_id);
    } catch {}
  };
  es.addEventListener("new", listener);
  es.addEventListener("rising", listener);
  return () => es.close();
}

export type CvSkill = {
  id: string;
  label: string;
  /** null when no snapshot has measured it yet */
  status: LiveStatus | null;
  projected: { moderate: LiveStatus; fast: LiveStatus } | null;
  evidence_count: number;
  family: { id: string; label: string } | null;
  quote: string;
  found_by: "llm" | "dictionary";
};

export type CvTrace = {
  text: { chars: number; lines: number };
  reader: { method: "llm" | "dictionary"; model: string | null; note: string | null };
  skills: { llm: number; dictionary: number; dropped_unverified: number; unrecognised: number; ai_tools: number };
  jobs: { found: number; mapped: number };
  signals: { measured: number; of: number; sources: { id: string; name: string; rung: number; data_as_of: string | null }[] };
  roles: { scored: number; catalogue: number; shown: number };
};

/** What the API read from an uploaded CV. Nothing here is stored on the server. */
export type CvProfile = {
  file: string | null;
  method: "llm" | "dictionary";
  model: string | null;
  /** why the LLM wasn't used, when it wasn't */
  llm_note: string | null;
  summary: string | null;
  jobs: { title: string; employer: string; period: string; quote: string; occupation: { isco: string; title: string } | null }[];
  skills: CvSkill[];
  /** AI capabilities the CV names (tools the person used), kept apart from skills */
  ai_tools: CvSkill[];
  unrecognised: { name: string; quote: string }[];
  discarded_unverified: number;
  exposed: { id: string; label: string; status: LiveStatus | null; because: { skill: string; why: string }[] }[];
  /** best-fit roles, scored exactly as on the Your direction step (PRD FR-4.2) */
  roles: CvRole[];
  /** ISCO of the role to pursue: highest demand x match among roles you fit 40%+ */
  recommended: string | null;
  /** market evidence per concept: your skills, the roles' skills and their job families */
  signals: Record<string, SkillSignal>;
  /** absent on CV results saved before it existed */
  malaysia_market?: MalaysiaMarket | null;
  /** short computed findings, each traceable to a number on the page */
  insights: { kind: "focus" | "rising" | "falling" | "ai" | "fit"; text: string }[];
  snapshot: { id: string; as_of: string } | null;
  trace: CvTrace;
};

export type CvRole = RoleScore;

export type SkillSignal = {
  status: LiveStatus;
  projected: { moderate: LiveStatus; fast: LiveStatus };
  // "up"/"down" only for a Malaysian rung measured for the skill's whole occupation groups (`groups`), which is
  // context and never moves the status
  rungs: {
    rung: 1 | 2 | 3; name: string; movement: "rising fast" | "up" | "slightly up" | "flat" | "slightly down" | "down" | "falling" | "no data";
    sources: string[]; groups: string[];
    /** with `groups`: those groups' share of all job openings now and in the `previous` quarter; `movement` follows it */
    share_pct?: number | null; previous_share_pct?: number | null; previous?: string | null;
  }[];
  meaning: string | null;
  evidence: SignalItem[];
  evidence_count: number;
};

/** Malaysian online job ads (DOSM) for the occupation groups behind your skills, latest quarter vs the one before */
export type MalaysiaMarket = {
  quarter: string;
  previous: string;
  url: string;
  all: { ads: number; change_pct: number | null };
  groups: {
    group: string; ads: number; change_pct: number | null; share_pct: number; previous_share_pct: number;
    /** the share's direction, in the same words as the skill cards' "Hired in Malaysia" row */
    movement: SkillSignal["rungs"][number]["movement"];
  }[];
};

/** The CV's text lines, fast, for the scanner. null when the API can't read it (the scanner then shows bars). */
export async function readLines(file: File): Promise<string[] | null> {
  const body = new FormData();
  body.append("file", file);
  try {
    const res = await fetch(`${API_URL}/profile/text`, { method: "POST", body, signal: AbortSignal.timeout(15_000) });
    return res.ok ? ((await res.json()).lines as string[]) : null;
  } catch {
    return null;
  }
}

/** Uploads a CV. Returns the profile, or a message to show the user. */
export async function extractProfile(file: File): Promise<{ profile: CvProfile } | { error: string }> {
  const body = new FormData();
  body.append("file", file);
  try {
    // reading a CV with the LLM takes a few seconds, longer than the default API timeout here
    const res = await fetch(`${API_URL}/profile/extract`, { method: "POST", body, signal: AbortSignal.timeout(60_000) });
    const data = await res.json();
    return res.ok ? { profile: data as CvProfile } : { error: typeof data.detail === "string" ? data.detail : "Couldn't read this CV." };
  } catch {
    return { error: "Can't reach the Kompas API. Is it running?" };
  }
}

/** A saved profile re-scored against the latest market snapshot (no CV needed). null when the API can't help. */
export async function rescoreProfile(cv: CvProfile): Promise<CvProfile | null> {
  try {
    const res = await fetch(`${API_URL}/profile/rescore`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(cv),
      signal: AbortSignal.timeout(20_000),
    });
    return res.ok ? ((await res.json()) as CvProfile) : null;
  } catch {
    return null;
  }
}

export type LiveJob = {
  id: string | null;
  title: string;
  employer: string;
  location: string;
  remote: boolean;
  type: string | null;
  posted: string | null;
  /** the original posting, on the board that published it */
  url: string | null;
  via: string | null;
  salary: string | null;
  /** the user's skills the posting mentions */
  matched: string[];
};

export type LiveJobs = { role: string; jobs: LiveJob[]; source: string; fetched_at: string | null; cached: boolean; note: string | null };

/** Live openings in Malaysia for a role (JSearch, cached a day). null when the API can't be reached. */
export async function liveJobs(isco: string, skills: string[]): Promise<LiveJobs | null> {
  const params = new URLSearchParams({ isco, skills: skills.join(",") });
  return call<LiveJobs>(`/jobs?${params}`, { signal: AbortSignal.timeout(25_000) });
}
