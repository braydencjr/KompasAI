"use client";

import { useEffect, useRef, useState } from "react";
import { authApi } from "../lib/auth";
import type { SimResult } from "../data/simulations";
import { useAuth } from "./Auth";
import { useJourney } from "./journey/JourneyProvider";
import { useSim } from "./SimulatorProvider";

type Choices = Parameters<ReturnType<typeof useJourney>["set"]>[0];
type Saved = { journey?: Choices; sim?: Record<string, SimResult> };

const SAVE_DELAY_MS = 1500;

/** What the signed-in person's account holds after signing in: their saved progress, plus anything done here before
 * signing in (steps ticked off, mini-project and simulation scores). Same job chosen: steps are combined; a different
 * job: the account's progress wins. For each simulation the better score is kept. */
function merge(local: Saved, server: Saved | null): Saved {
  if (!server) return local;
  const l = local.journey ?? {};
  const s = server.journey ?? {};
  const sameJob = !l.role || l.role === s.role;
  const journey: Choices = sameJob
    ? { ...l, ...s, role: s.role ?? l.role, completed: [...new Set([...(s.completed ?? []), ...(l.completed ?? [])])] }
    : { ...l, ...s };
  const sim = { ...(local.sim ?? {}) };
  for (const [id, r] of Object.entries(server.sim ?? {})) if (!sim[id] || r.can > sim[id].can) sim[id] = r;
  return { journey, sim };
}

/** Keeps a signed-in person's progress in their account: loaded and merged once after signing in, then saved a moment
 * after every change. Draws nothing. Without an account, progress stays in this browser only. */
export default function ProgressSync() {
  const { user, token } = useAuth();
  const j = useJourney();
  const { results, restore } = useSim();

  const journey: Choices = {
    overrides: j.overrides, sdgs: j.sdgs, role: j.role, completed: j.completed, pace: j.pace,
    snapshot: j.snapshot,
  };
  const latest = useRef<Saved>({});
  latest.current = { journey, sim: results };

  const [ready, setReady] = useState(false);
  const syncedFor = useRef<number | null>(null);

  useEffect(() => {
    if (!user || !token) {
      syncedFor.current = null;
      setReady(false);
      return;
    }
    if (!j.restored || syncedFor.current === user.id) return;
    syncedFor.current = user.id;
    (async () => {
      try {
        const server = (await authApi.getProgress(token)).data as Saved | null;
        const merged = merge(latest.current, server);
        if (merged.journey) j.set({ ...merged.journey, scenario: "moderate" });   // the pace switch is gone
        if (merged.sim) restore(merged.sim);
        await authApi.putProgress(token, merged as Record<string, unknown>);
        if (syncedFor.current === user.id) setReady(true);
      } catch (e) {
        console.warn("Kompas couldn't sync your progress", e);
        syncedFor.current = null;
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user, token, j.restored]);

  const blob = JSON.stringify({ journey, sim: results });
  useEffect(() => {
    if (!ready || !token) return;
    const t = setTimeout(() => authApi.putProgress(token, JSON.parse(blob)).catch(() => {}), SAVE_DELAY_MS);
    return () => clearTimeout(t);
  }, [blob, ready, token]);

  return null;
}
