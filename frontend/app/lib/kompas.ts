// Client for the Kompas signal API: the signal engine (backend/pipeline), served by the main backend under
// /api/signals. Every call returns null when the API is unreachable, so the UI can fall back to the sample
// data in app/data/bets.ts.

import { API_URL as BACKEND_URL } from "./api";

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
    const res = await fetch(`${API_URL}${path}`, { ...init, signal: AbortSignal.timeout(5000) });
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

export type CvSkill = { id: string; label: string; status: LiveStatus | null; quote: string; found_by: "llm" | "dictionary" };

/** What the API read from an uploaded CV. Nothing here is stored on the server. */
export type CvProfile = {
  file: string | null;
  method: "llm" | "dictionary";
  model: string | null;
  llm_note: string | null;
  summary: string | null;
  jobs: { title: string; employer: string; period: string; quote: string; occupation: { isco: string; title: string } | null }[];
  skills: CvSkill[];
  unrecognised: { name: string; quote: string }[];
  discarded_unverified: number;
  exposed: { id: string; label: string; because: { skill: string; why: string }[] }[];
  /** best-fit next roles, ranked by the PRD FR-4.2 match score */
  roles: CvRole[];
};

type RoleSkill = { id: string; label: string; status: LiveStatus | null };

export type CvRole = {
  isco: string;
  title: string;
  occupation: string;
  match: number;
  demand: LiveStatus | null;
  have: RoleSkill[];
  gaps: RoleSkill[];
};

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
