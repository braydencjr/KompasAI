"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import WorkSimulator from "./WorkSimulator";
import { simulations, type SimResult } from "../data/simulations";

const STORAGE_KEY = "kompas:sim-results";

type SimContext = {
  open: (roleId: string) => void;
  results: Record<string, SimResult>;
  hasSim: (roleId: string) => boolean;
};

const Ctx = createContext<SimContext | null>(null);

export function useSim() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useSim must be used inside <SimulatorProvider>");
  return ctx;
}

export default function SimulatorProvider({ children }: { children: React.ReactNode }) {
  const [openId, setOpenId] = useState<string | null>(null);
  const [results, setResults] = useState<Record<string, SimResult>>({});

  useEffect(() => {
    try {
      setResults(JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "{}"));
    } catch {}
  }, []);

  // links like /#simulate-fpa-analyst (used by the sidebar) open a simulation directly
  useEffect(() => {
    const fromHash = () => {
      const id = window.location.hash.replace("#simulate-", "");
      if (simulations.some((s) => s.roleId === id)) setOpenId(id);
    };
    fromHash();
    window.addEventListener("hashchange", fromHash);
    return () => window.removeEventListener("hashchange", fromHash);
  }, []);

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

  const sim = simulations.find((s) => s.roleId === openId);

  return (
    <Ctx.Provider
      value={{
        open: setOpenId,
        results,
        hasSim: (id) => simulations.some((s) => s.roleId === id),
      }}
    >
      {children}
      {sim && <WorkSimulator key={sim.roleId} sim={sim} onClose={close} onFinish={(r) => finish(sim.roleId, r)} />}
    </Ctx.Provider>
  );
}

/** "Try a day in this job" button, or the fit badge once the user has tried it */
export function SimButton({ roleId, variant = "button" }: { roleId: string; variant?: "button" | "link" }) {
  const { open, results, hasSim } = useSim();
  if (!hasSim(roleId)) return null;
  const result = results[roleId];

  return (
    <div className={`sim-entry sim-entry-${variant}`}>
      {result && (
        <span className={`fit-badge fit-${result.quadrant.split(" ")[0].replace(",", "").toLowerCase()}`}>
          Simulated · {result.quadrant}
        </span>
      )}
      <button className={variant === "button" ? "btn btn-ghost btn-sm sim-btn" : "sim-link"} onClick={() => open(roleId)}>
        <span className="sim-play" aria-hidden>▶</span>
        {result ? "Try again" : variant === "button" ? "Try a day in this job" : "Try a 15-min work simulation"}
      </button>
    </div>
  );
}
