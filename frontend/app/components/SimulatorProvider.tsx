"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import WorkSimulator from "./WorkSimulator";
import { ApiError, postJson } from "../lib/api";
import { prepareSimulation } from "../lib/prepare";
import { bets, cvMatch, type Role } from "../data/bets";
import { rating, simulations, type SimResult, type Simulation } from "../data/simulations";

const STORAGE_KEY = "kompas:sim-results";
const ROLES: Role[] = [cvMatch, ...bets];

/** "ai": written for this user by the backend; "sample": the built-in fallback; "error": generation failed and this
 * job has no sample to fall back on */
export type SimSource = "loading" | "ai" | "sample" | "error";
type Loaded = { source: SimSource; sim: Simulation; note?: string };

/** what the generator needs to know about a job that isn't one of the built-in samples */
export type SimRole = { id: string; title: string; summary: string; have: string[]; gaps: string[]; aiOnly?: boolean };

type SimContext = {
  /** `role`: for any job (e.g. The Route's final project); without it, only the built-in sample roles open */
  open: (roleId: string, role?: SimRole) => void;
  results: Record<string, SimResult>;
  hasSim: (roleId: string) => boolean;
};

const Ctx = createContext<SimContext | null>(null);

export function useSim() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useSim must be used inside <SimulatorProvider>");
  return ctx;
}

const sampleFor = (roleId: string) => simulations.find((s) => s.roleId === roleId);

/** an empty simulation to hold the title while a job without a sample is being written */
const placeholder = (role: SimRole): Simulation => ({
  roleId: role.id, title: role.title, setting: "", welcome: { from: "", text: "" }, tasks: [],
});

function errorNote(e: unknown) {
  if (e instanceof ApiError && e.status === 503) return "AI isn't set up yet: add an API key in backend/.env.";
  if (e instanceof ApiError && e.status === 0) return e.message;
  return `The AI couldn't write this day (${e instanceof Error ? e.message : "unknown error"}).`;
}

function fallbackNote(e: unknown) {
  if (e instanceof ApiError && e.status === 503) return "AI isn't set up yet (add an API key in backend/.env), so this is a sample day.";
  if (e instanceof ApiError && e.status === 0) return `${e.message} This is a sample day.`;
  return `AI generation didn't work this time (${e instanceof Error ? e.message : "unknown error"}). This is a sample day.`;
}

export default function SimulatorProvider({ children }: { children: React.ReactNode }) {
  const [openId, setOpenId] = useState<string | null>(null);
  const [results, setResults] = useState<Record<string, SimResult>>({});
  const [loaded, setLoaded] = useState<Record<string, Loaded>>({});
  const requests = useRef<Record<string, AbortController>>({});
  const loadedRef = useRef(loaded);
  loadedRef.current = loaded;
  const customRoles = useRef<Record<string, SimRole>>({});

  useEffect(() => {
    try {
      setResults(JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "{}"));
    } catch {}
  }, []);

  const generate = useCallback(async (roleId: string, fresh: boolean) => {
    const role: SimRole | undefined = customRoles.current[roleId] ?? ROLES.find((r) => r.id === roleId);
    if (!role) return;
    const sample = sampleFor(roleId);
    requests.current[roleId]?.abort();
    const ctrl = new AbortController();
    requests.current[roleId] = ctrl;
    setLoaded((p) => ({ ...p, [roleId]: { source: "loading", sim: sample ?? placeholder(role) } }));

    try {
      const sim = await postJson<Simulation>(
        "/api/simulations",
        { role_id: role.id, title: role.title, summary: role.summary, skills: role.have, gaps: role.gaps, fresh, ai_only: !!role.aiOnly },
        ctrl.signal,
      );
      const ready = await prepareSimulation(sim);
      if (!ctrl.signal.aborted) setLoaded((p) => ({ ...p, [roleId]: { source: "ai", sim: ready } }));
    } catch (e) {
      if (ctrl.signal.aborted) return;
      setLoaded((p) => ({
        ...p,
        [roleId]: sample
          ? { source: "sample", sim: sample, note: fallbackNote(e) }
          : { source: "error", sim: placeholder(role), note: errorNote(e) },
      }));
    }
  }, []);

  const open = useCallback(
    (roleId: string, role?: SimRole) => {
      if (role) customRoles.current[roleId] = role;
      setOpenId(roleId);
      // reuse a scenario already written this session; otherwise ask the AI for one
      const prev = loadedRef.current[roleId];
      if (!prev || prev.source === "error" || (prev.source === "sample" && prev.note)) void generate(roleId, false);
    },
    [generate],
  );

  const pickSample = useCallback((roleId: string) => {
    const sample = sampleFor(roleId);
    if (!sample) return;
    requests.current[roleId]?.abort();
    setLoaded((p) => ({ ...p, [roleId]: { source: "sample", sim: sample } }));
  }, []);

  // links like /#simulate-fpa-analyst (used by the sidebar) open a simulation directly
  useEffect(() => {
    const fromHash = () => {
      const id = window.location.hash.replace("#simulate-", "");
      if (simulations.some((s) => s.roleId === id)) open(id);
    };
    fromHash();
    window.addEventListener("hashchange", fromHash);
    return () => window.removeEventListener("hashchange", fromHash);
  }, [open]);

  const close = useCallback(() => {
    setOpenId(null);
    if (window.location.hash.startsWith("#simulate-")) {
      history.replaceState(null, "", window.location.pathname + window.location.search);
    }
  }, []);

  const finish = useCallback((roleId: string, result: SimResult) => {
    setResults((prev) => {
      const next = { ...prev, [roleId]: result };
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
      } catch {}
      return next;
    });
  }, []);

  const pending = (id: string): Loaded | null => {
    const sim = sampleFor(id) ?? (customRoles.current[id] ? placeholder(customRoles.current[id]) : null);
    return sim ? { source: "loading", sim } : null;
  };
  const current = openId ? (loaded[openId] ?? pending(openId)) : null;

  return (
    <Ctx.Provider
      value={{
        open,
        results,
        hasSim: (id) => simulations.some((s) => s.roleId === id),
      }}
    >
      {children}
      {openId && current && (
        <WorkSimulator
          // a new scenario starts the day over
          key={`${openId}-${current.source}`}
          sim={current.sim}
          source={current.source}
          note={current.note}
          onUseSample={sampleFor(openId) ? () => pickSample(openId) : undefined}
          onRegenerate={() => generate(openId, true)}
          onClose={close}
          onFinish={(r) => finish(openId, r)}
        />
      )}
    </Ctx.Provider>
  );
}

const FIT_CLASS: Record<string, string> = { great: "strong", good: "strong", mid: "capable", low: "probably" };

/** "Try a day in this job" button, or the fit badge once the user has tried it */
export function SimButton({ roleId, variant = "button" }: { roleId: string; variant?: "button" | "link" }) {
  const { open, results, hasSim } = useSim();
  if (!hasSim(roleId)) return null;
  const result = results[roleId];

  return (
    <div className={`sim-entry sim-entry-${variant}`}>
      {result && (
        <span className={`fit-badge fit-${FIT_CLASS[rating(result.can).tone]}`}>
          Simulated · {rating(result.can).label}
        </span>
      )}
      <button className={variant === "button" ? "btn btn-ghost btn-sm sim-btn" : "sim-link"} onClick={() => open(roleId)}>
        <span className="sim-play" aria-hidden>▶</span>
        {result ? "Try again" : variant === "button" ? "Try a day in this job" : "Try the job hands-on · 15 min"}
      </button>
    </div>
  );
}
