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
  concepts?: { id: string; label: string }[];
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

async function call<T>(path: string, init?: RequestInit, timeoutMs = 15000): Promise<T | null> {
  try {
    const res = await fetch(`${API_URL}${path}`, { signal: AbortSignal.timeout(timeoutMs), ...init });
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
  /** the skill as the resume names it, and the broad group the reader put it in (absent on older profiles) */
  name?: string;
  group?: string | null;
};

export type CvTrace = {
  text: { chars: number; lines: number };
  reader: { method: "llm" | "dictionary"; model: string | null; note: string | null };
  skills: { llm: number; dictionary: number; dropped_unverified: number; unrecognised: number; ai_tools: number };
  jobs: { found: number; mapped: number };
  signals: { measured: number; of: number; sources: { id: string; name: string; rung: number; data_as_of: string | null }[] };
  roles: { scored: number; catalogue: number; shown: number };
};

/** Upload step 1: what the resume says, before it is matched against the market (POST /profile/read). */
export type CvRead = Pick<CvProfile, "file" | "method" | "model" | "llm_note" | "summary" | "jobs" | "unrecognised" | "groups" | "discarded_unverified"> & {
  skills: CvReadSkill[];
  ai_tools: CvReadSkill[];
  trace: Pick<CvTrace, "text" | "reader" | "skills" | "jobs">;
};

export type CvReadSkill = Pick<CvSkill, "id" | "label" | "family" | "quote" | "found_by" | "name" | "group">;

/** A broad group of the resume's skills, as the reader grouped them (display only: matching uses the skills) */
export type SkillGroup = { name: string; skills: string[]; untracked: string[] };

/** What the API read from an uploaded resume, matched against the market. Nothing here is stored on the server. */
export type CvProfile = {
  file: string | null;
  method: "llm" | "dictionary";
  model: string | null;
  /** why the LLM wasn't used, when it wasn't */
  llm_note: string | null;
  /** the ESCO skills catalogue was unreachable: skills only it can match wait for a later visit */
  esco_down?: boolean;
  summary: string | null;
  jobs: { title: string; employer: string; period: string; quote: string; occupation: { isco: string; title: string } | null }[];
  skills: CvSkill[];
  /** AI capabilities the resume names (tools the person used), kept apart from skills */
  ai_tools: CvSkill[];
  unrecognised: { name: string; quote: string; group?: string | null }[];
  /** the skills in broad groups, for the stickers; absent on profiles saved before it existed */
  groups?: SkillGroup[];
  discarded_unverified: number;
  exposed: { id: string; label: string; status: LiveStatus | null; because: { skill: string; why: string }[] }[];
  /** best-fit roles, scored exactly as on the Your direction step (PRD FR-4.2) */
  roles: CvRole[];
  /** ISCO of the role to pursue: highest demand x match among roles you fit 40%+ */
  recommended: string | null;
  /** market evidence per concept: your skills, the roles' skills and their job families */
  signals: Record<string, SkillSignal>;
  /** absent on resume results saved before it existed */
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
    /** the LLM's estimate where the market data is silent */
    estimated?: boolean;
    /** with `groups`: those groups' share of all job openings now and in the `previous` quarter; `movement` follows it */
    share_pct?: number | null; previous_share_pct?: number | null; previous?: string | null;
  }[];
  meaning: string | null;
  /** the whole status is the LLM's estimate (no measured data), with its one-sentence reason */
  estimated?: boolean; basis?: string | null;
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

/** The resume's text lines, fast, for the scanner. null when the API can't read it (the scanner then shows bars). */
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

/** Upload step 1: the LLM reads the resume's skills and jobs. Returns them, or a message to show the user. */
export async function readProfile(file: File): Promise<{ read: CvRead } | { error: string }> {
  const body = new FormData();
  body.append("file", file);
  try {
    // reading a resume with the LLM takes a while, longer than the default API timeout here
    const res = await fetch(`${API_URL}/profile/read`, { method: "POST", body, signal: AbortSignal.timeout(120_000) });
    const data = await res.json();
    return res.ok ? { read: data as CvRead } : { error: typeof data.detail === "string" ? data.detail : "Couldn't read this resume." };
  } catch {
    return { error: "Can't reach the Kompas API. Is it running?" };
  }
}

/** Upload step 2: the read skills matched against the market (statuses, roles and their reasons, evidence). */
export async function matchProfile(read: CvRead): Promise<{ profile: CvProfile } | { error: string }> {
  try {
    const res = await fetch(`${API_URL}/profile/match`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(read),
      signal: AbortSignal.timeout(120_000),
    });
    const data = await res.json();
    return res.ok ? { profile: data as CvProfile } : { error: typeof data.detail === "string" ? data.detail : "Couldn't match your skills." };
  } catch {
    return { error: "Can't reach the Kompas API. Is it running?" };
  }
}

/** A saved profile re-scored against the latest market snapshot (no resume needed). null when the API can't help. */
export async function rescoreProfile(cv: CvProfile): Promise<CvProfile | null> {
  try {
    const res = await fetch(`${API_URL}/profile/rescore`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(cv),
      // the first re-score after new skills are found measures them and asks the LLM (about 20 s for a 26-skill resume)
      signal: AbortSignal.timeout(60_000),
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

// ---------- Radar: what is moving right now ----------

export type RadarRepo = {
  full_name: string;
  url: string;
  description: string;
  /** what it is in plain words, written by the LLM for non-programmers (null until it has read the repo) */
  plain: string | null;
  language: string | null;
  stars: number;
  forks: number;
  /** stars gained today or this week, as GitHub reports it */
  period_stars: number;
  category: string;
  rank: number;
  category_rank: number;
  /** rank in the same category at the previous scrape; null when new to it */
  prev_category_rank: number | null;
  skill: { id: string; label: string } | null;
};

export type RadarSince = "daily" | "weekly";

export type RadarKeyword = {
  term: string;
  mentions: number;
  baseline: number;
  change: number;
  new: boolean;
  spark: number[];
  concept_id: string | null;
  evidence: { title: string; url: string }[];
};

export type RadarStory = {
  id: string;
  title: string;
  url: string;
  hn_url: string;
  published_at: string;
  points: number;
  comments: number;
  points_per_hour: number;
  keywords: string[];
};

type LadderRung = { active: boolean; trend: number | null; level: "concept" | "family" | null };

export type RadarTrendSkill = {
  id: string;
  label: string;
  /** what it is in one plain sentence (null until the LLM has written it) */
  plain: string | null;
  status: LiveStatus;
  /** the status at the comparison snapshot, when it differs */
  was: LiveStatus | null;
  move: "up" | "down" | null;
  /** momentum: ladder moves, status and rising trends; the order within a field */
  score: number;
  ladder: { talk: LadderRung; abroad: LadderRung; malaysia: LadderRung };
  /** how often a sample of Malaysian job postings asks for it */
  postings: { postings: number; roles: { title: string; count: number; of: number }[]; quote: { text: string; role: string } | null } | null;
  evidence: {
    news: { headline: string; url: string; points?: number }[];
    repos: { name: string; plain: string; stars_today: number; url: string }[];
  };
};

export type RadarFamily = { id: string; label: string; status: LiveStatus | null; moving: number; skills: RadarTrendSkill[] };
export type RadarTrends = { as_of: string | null; compared_to: string | null; families: RadarFamily[]; sample: { postings: number; roles: number } | null };

export type RadarBrief = {
  as_of: string | null;
  compared_to: string | null;
  headline: string;
  summary: string;
  by: string;
  meters: { talk: { rising: number }; abroad: { rising: number }; malaysia: { rising: number; sample: { postings: number; roles: number } | null } };
  climbed: number;
  fell: number;
};

/** A shown story: read by the LLM and scored as mattering to people's careers. One per event. */
export type RadarNews = {
  id: string;
  /** the event it tells; several outlets' stories about one event are shown once */
  topic: string | null;
  source: "my_news" | "reddit" | "hn_front";
  outlet: string;
  /** every outlet that covered the event */
  outlets: string[];
  headline: string;
  dek: string | null;
  title: string;
  url: string;
  published_at: string;
  /** when the LLM first read it: when it reached Kompas */
  first_seen: string;
  /** votes where the source has them (Hacker News; Reddit with an API key) */
  points: number | null;
  comments: number | null;
  /** how much it matters to a career: 2 = an industry change, 3 = jobs, pay, hiring, skills */
  career: 2 | 3;
  skill: { id: string; label: string } | null;
  rank_score: number;
};

export const radar = {
  brief: () => call<RadarBrief>("/radar/brief", undefined, 30000),
  trends: () => call<RadarTrends>("/radar/trends", undefined, 30000),
  news: () => call<{ as_of: string | null; items: RadarNews[] }>("/radar/news?limit=40", undefined, 20000),
  repos: (since: RadarSince = "daily") =>
    call<{ as_of: string | null; since: RadarSince; compared_to: string | null; categories: { label: string; count: number }[]; items: RadarRepo[] }>(
      `/radar/repos?since=${since}`, undefined, 20000),
  keywords: () => call<{ as_of: string | null; window_days: number; items: RadarKeyword[] }>("/radar/keywords?limit=20", undefined, 20000),
};

export type FeedEvent =
  | { seq: number | string; type: "new" | "rising"; at: string; replay?: boolean; item: FeedItem }
  | { seq: string; type: "news"; at: string; replay?: boolean; item: RadarNews };

/** Subscribes to the whole live-feed event (not just the id). `onState` reports whether the stream is connected. */
export function onFeedStream(handler: (event: FeedEvent) => void, onState?: (connected: boolean) => void): () => void {
  if (typeof EventSource === "undefined") return () => {};
  const es = new EventSource(`${API_URL}/feed/stream`);
  const listener = (e: MessageEvent) => {
    try {
      handler(JSON.parse(e.data));
    } catch {}
  };
  es.addEventListener("new", listener);
  es.addEventListener("rising", listener);
  es.addEventListener("news", listener);
  es.onopen = () => onState?.(true);
  es.onerror = () => onState?.(false);
  return () => es.close();
}
