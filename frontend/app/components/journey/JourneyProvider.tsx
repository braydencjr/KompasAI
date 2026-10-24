"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { useProfile } from "../Profile";
import {
  journeyApi,
  type Catalog,
  type Journey,
  type JourneyRequest,
  type Pile,
  type Scenario,
} from "../../lib/journey";

export const STEPS = [
  { id: "you", label: "You", title: "Your profile" },
  { id: "future", label: "AI Exposure", title: "AI & Skills Outlook" },
  { id: "bets", label: "Your Kompas", title: "Where your Kompas points" },
  { id: "route", label: "The Route", title: "Your learning route" },
  { id: "ping", label: "The Ping", title: "The world moved" },
] as const;
export type StepId = (typeof STEPS)[number]["id"];

// Aisyah, the sample persona, is an accounts executive: MASCO/ISCO 3313, accounting associate professionals
const SAMPLE_OCCUPATION = "3313";
const STORAGE_KEY = "kompas:journey";

type Choices = {
  occupation: string | null;
  overrides: Record<string, { pile: Pile; reason: string }>;
  scenario: Scenario;
  sdgs: number[];
  role: string | null;
  completed: string[];
  pace: number;
  snapshot: string | null;
};

const FRESH: Choices = {
  occupation: null, overrides: {}, scenario: "moderate", sdgs: [], role: null, completed: [], pace: 5, snapshot: null,
};

type JourneyState = Choices & {
  step: StepId;
  direction: 1 | -1;
  catalog: Catalog | null;
  data: Journey | null;
  loading: boolean;
  error: string | null;
  request: JourneyRequest;
  go: (step: StepId) => void;
  next: () => void;
  back: () => void;
  set: (patch: Partial<Choices>) => void;
  move: (taskId: string, pile: Pile, reason: string) => void;
  undoMove: (taskId: string) => void;
  toggleSdg: (sdg: number) => void;
  toggleStep: (skillId: string) => void;
  chooseRole: (isco: string) => void;
};

const Ctx = createContext<JourneyState | null>(null);

export function useJourney() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useJourney must be used inside <JourneyProvider>");
  return ctx;
}

/** For components that also work outside the journey (the live feed). */
export function useOptionalJourney() {
  return useContext(Ctx);
}

function stepFromHash(): StepId {
  if (typeof window === "undefined") return "you";
  const raw = window.location.hash.replace("#", "");
  // The Mirror and the Ghost CV became one step: old links land on it
  const id = raw === "mirror" || raw === "ghost" ? "future" : raw;
  return (STEPS.find((s) => s.id === id)?.id ?? "you") as StepId;
}

export function JourneyProvider({ children }: { children: React.ReactNode }) {
  const profile = useProfile();
  const cvOccupation = profile.cv?.jobs.find((j) => j.occupation)?.occupation?.isco ?? null;
  const defaultOccupation = profile.source === "cv" ? cvOccupation : SAMPLE_OCCUPATION;

  // occupation null = the profile's own job (read from the CV, or the sample's); set only when the user changes it
  const [choices, setChoices] = useState<Choices>(FRESH);
  const occupation = choices.occupation ?? defaultOccupation;
  const [step, setStep] = useState<StepId>("you");
  const [direction, setDirection] = useState<1 | -1>(1);
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [data, setData] = useState<Journey | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const loaded = useRef(false);

  // restore choices and the step from the last visit
  useEffect(() => {
    try {
      const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "null");
      if (saved && typeof saved === "object") setChoices({ ...FRESH, ...saved });
    } catch {}
    setStep(stepFromHash());
    loaded.current = true;
    const onHash = () => setStep(stepFromHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  // a new CV (or going back to the sample) starts the journey's choices over; keep scenario and goals
  useEffect(() => {
    if (profile.generation === 0) return;
    setChoices((c) => ({ ...FRESH, scenario: c.scenario, sdgs: c.sdgs }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [profile.generation]);

  useEffect(() => {
    if (!loaded.current) return;
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(choices));
    } catch {}
  }, [choices]);

  useEffect(() => {
    journeyApi.catalog().then(setCatalog).catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, []);

  const request: JourneyRequest = useMemo(
    () => ({
      skills: profile.skills.map((id) => ({ id, evidence: "claimed" as const })),
      occupation,
      overrides: choices.overrides,
      scenario: choices.scenario,
      sdgs: choices.sdgs,
      role: choices.role,
      completed: choices.completed,
      pace: choices.pace,
      snapshot: choices.snapshot,
    }),
    [profile.skills, choices, occupation],
  );

  // recompute whenever a choice changes; only the latest answer is kept
  const key = JSON.stringify(request);
  useEffect(() => {
    if (!catalog) return;
    const ctrl = new AbortController();
    setLoading(true);
    const timer = setTimeout(() => {
      journeyApi
        .build(JSON.parse(key), ctrl.signal)
        .then((j) => {
          setData(j);
          setError(null);
        })
        .catch((e) => {
          if (!ctrl.signal.aborted) setError(e instanceof Error ? e.message : String(e));
        })
        .finally(() => {
          if (!ctrl.signal.aborted) setLoading(false);
        });
    }, 120);
    return () => {
      clearTimeout(timer);
      ctrl.abort();
    };
  }, [key, catalog]);

  const go = useCallback((target: StepId) => {
    const from = STEPS.findIndex((s) => s.id === stepFromHash());
    const to = STEPS.findIndex((s) => s.id === target);
    setDirection(to >= from ? 1 : -1);
    setStep(target);
    if (window.location.hash !== `#${target}`) history.pushState(null, "", `#${target}`);
    document.querySelector(".main")?.scrollTo({ top: 0, behavior: "smooth" });
  }, []);

  const index = STEPS.findIndex((s) => s.id === step);
  const set = useCallback((patch: Partial<Choices>) => setChoices((c) => ({ ...c, ...patch })), []);

  const value: JourneyState = {
    ...choices,
    occupation,
    step,
    direction,
    catalog,
    data,
    loading,
    error,
    request,
    go,
    next: () => index < STEPS.length - 1 && go(STEPS[index + 1].id),
    back: () => index > 0 && go(STEPS[index - 1].id),
    set,
    move: (taskId, pile, reason) => set({ overrides: { ...choices.overrides, [taskId]: { pile, reason } } }),
    undoMove: (taskId) => {
      const { [taskId]: _, ...rest } = choices.overrides;
      set({ overrides: rest });
    },
    toggleSdg: (sdg) =>
      set({ sdgs: choices.sdgs.includes(sdg) ? choices.sdgs.filter((g) => g !== sdg) : [...choices.sdgs, sdg].sort((a, b) => a - b) }),
    toggleStep: (skillId) =>
      set({ completed: choices.completed.includes(skillId) ? choices.completed.filter((s) => s !== skillId) : [...choices.completed, skillId] }),
    chooseRole: (isco) => set({ role: isco, completed: [] }),
  };

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
