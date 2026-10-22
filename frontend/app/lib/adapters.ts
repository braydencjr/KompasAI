// Turns computed journey results into the shapes the dashboard components were built for (data/bets.ts),
// so the journey reuses their design with real data.

import type { Bet, Role, Signal, Step } from "../data/bets";
import type { BetKind, RoleScore, Route } from "./journey";

const KIND: Record<BetKind, Bet["kind"]> = { safe: "Safest switch", rising: "Fastest-growing", impact: "Biggest impact" };
const NOTE: Record<BetKind, string> = {
  safe: "Its key skills hold up under both scenarios",
  rising: "Strongest demand among the roles you fit",
  impact: "Best fit with the goals you chose",
};
const COST: Record<string, Step["cost"]> = { free: "Free", "free-to-audit": "Free to audit", "low-cost": "Low-cost", paid: "Low-cost" };

export function routeSteps(route: Route | null | undefined): Step[] {
  return (route?.steps ?? []).map((s) => ({
    skill: s.label,
    title: s.resource?.title ?? "No verified course yet",
    provider: s.resource ? `${s.resource.provider} · checked ${s.resource.checked}` : "Still worth learning; look for a course you trust",
    url: s.resource?.url ?? "",
    hours: s.resource?.hours ?? 0,
    cost: s.resource ? COST[s.resource.cost] ?? "Free" : "Free",
    why: s.why,
    signal: s.status as Signal,
  }));
}

export function toBet(kind: BetKind, r: RoleScore): Bet {
  const sdg = r.sdgs[0];
  return {
    id: r.isco,
    kind: KIND[kind],
    title: r.title,
    note: NOTE[kind],
    summary: `${r.occupation} (MASCO ${r.isco})${r.mycol ? ` · on Malaysia's Critical Occupations List ${r.mycol}` : ""}`,
    match: r.match,
    signal: r.family_status as Signal | null,
    sdg: sdg ? { goal: `SDG ${sdg.sdg}`, reason: sdg.rationale ?? sdg.name } : { goal: "SDG", reason: "" },
    have: r.have.map((h) => h.label),
    gaps: r.gaps.map((g) => g.label),
    steps: routeSteps(r.route),
    aiRisk: r.ai_exposure ?? 0,
    growth: r.growth ?? 0,
    trend: (r.trend ?? []).map((v) => Math.round(v * 100)),
    trendNote: r.trend_from
      ? `skill demand since ${new Date(`${r.trend_from}T00:00:00`).toLocaleDateString("en-GB", { month: "short", year: "numeric" })}`
      : "skill demand",
    // job openings aren't ingested yet: the jobs panel links to real job boards instead of showing samples
    openings: [],
  };
}

export function toRole(route: Route, r: RoleScore | undefined): Role {
  return {
    id: `route-${route.role.isco}`,
    title: route.role.title,
    summary: r ? `${r.occupation} (MASCO ${r.isco})` : "",
    match: route.role.match,
    signal: (r?.family_status ?? null) as Signal | null,
    sdg: r?.sdgs[0] ? { goal: `SDG ${r.sdgs[0].sdg}`, reason: r.sdgs[0].rationale ?? "" } : undefined,
    have: r?.have.map((h) => h.label) ?? [],
    gaps: r?.gaps.map((g) => g.label) ?? [],
    steps: routeSteps(route),
  };
}
