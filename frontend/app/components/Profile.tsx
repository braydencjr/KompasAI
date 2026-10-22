"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { profile as sampleProfile } from "../data/bets";
import { extractProfile, readLines, type CvProfile, type CvRole, type Profile } from "../lib/kompas";

// No login: the profile lives in this browser only (PRD NFR-3).
const STORAGE_KEY = "kompas:profile";

type Stored = {
  source: "sample" | "cv";
  cv: CvProfile | null;
  skills: string[];
  /** ISCO code of the role the user is looking at */
  roleIsco: string | null;
};

const SAMPLE: Stored = { source: "sample", cv: null, skills: sampleProfile.skills.map((s) => s.id), roleIsco: null };

/** The CV read in this session: drives the reading flow (scan, extract, match, direction). Kept until the next
 * upload so the flow can play through; a profile restored from storage has no scan and shows the flow finished. */
export type Scan = { name: string; lines: string[] | null; result: CvProfile | null };

type ProfileState = Stored & {
  role: CvRole | null;
  /** the shape POST /match expects */
  matchProfile: Profile;
  scan: Scan | null;
  error: string | null;
  analyse: (file: File) => Promise<void>;
  selectRole: (isco: string) => void;
  removeSkill: (id: string) => void;
  addSkill: (id: string) => void;
  /** goes up when a new CV is read or the user returns to the sample (not when a saved profile is restored) */
  generation: number;
  reset: () => void;
};

const ProfileContext = createContext<ProfileState | null>(null);

const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));

/** The CV's first lines, shown in the scanner. Only plain-text files can be read in the browser. */
function textLines(text: string) {
  return text
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean)
    .slice(0, 80)
    .map((l) => (l.length > 96 ? `${l.slice(0, 95)}…` : l));
}

export function ProfileProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<Stored>(SAMPLE);
  const [scan, setScan] = useState<Scan | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [generation, setGeneration] = useState(0);

  useEffect(() => {
    try {
      const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "null");
      // profiles saved before the API added `trace` have the old role shape: drop them
      if (saved?.source === "cv" && Array.isArray(saved.cv?.roles) && saved.cv?.signals) setState(saved);
      else localStorage.removeItem(STORAGE_KEY);
    } catch {}
  }, []);

  const save = useCallback((next: Stored) => {
    setState(next);
    try {
      if (next.source === "sample") localStorage.removeItem(STORAGE_KEY);
      else localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    } catch {}
  }, []);

  async function analyse(file: File) {
    setError(null);
    const local = /\.(txt|md)$/i.test(file.name) ? textLines(await file.text()) : null;
    setScan({ name: file.name, lines: local, result: null });
    try {
      // the real lines of a PDF/DOCX arrive quickly from the API, while the reader is still working
      if (!local) {
        readLines(file).then((lines) => lines && setScan((s) => (s && s.name === file.name && !s.result ? { ...s, lines } : s)));
      }
      // a floor on the scan so it reads even when the API answers instantly
      const [res] = await Promise.all([extractProfile(file), wait(2200)]);
      if ("error" in res) {
        setError(res.error);
        setScan(null);
        return;
      }
      if (!Array.isArray(res.profile.roles) || !res.profile.trace || !res.profile.signals) {
        setError("The Kompas API is out of date. Restart it and try again.");
        setScan(null);
        return;
      }
      const cv = res.profile;
      setScan((s) => ({ name: file.name, lines: s?.lines ?? local, result: cv }));
      save({ source: "cv", cv, skills: cv.skills.map((s) => s.id), roleIsco: cv.recommended ?? cv.roles[0]?.isco ?? null });
      setGeneration((g) => g + 1);
    } catch {
      setError("Something went wrong reading this CV. Please try again.");
      setScan(null);
    }
  }

  const role = state.cv?.roles.find((r) => r.isco === state.roleIsco) ?? null;
  const fromCv = state.source === "cv" && state.cv;

  const value: ProfileState = {
    ...state,
    role,
    scan,
    error,
    matchProfile: fromCv
      ? {
          skills: state.skills.map((id) => ({ id })),
          route: role?.gaps.map((g) => g.id) ?? [],
          exposed: state.cv!.exposed.map((e) => e.id),
        }
      : sampleProfile,
    analyse,
    selectRole: (isco) => save({ ...state, roleIsco: isco }),
    removeSkill: (id) => save({ ...state, skills: state.skills.filter((s) => s !== id) }),
    addSkill: (id) => {
      if (!state.skills.includes(id)) save({ ...state, skills: [...state.skills, id] });
    },
    reset: () => {
      setError(null);
      setScan(null);
      save(SAMPLE);
      setGeneration((g) => g + 1);
    },
    generation,
  };

  return <ProfileContext.Provider value={value}>{children}</ProfileContext.Provider>;
}

export function useProfile() {
  const ctx = useContext(ProfileContext);
  if (!ctx) throw new Error("useProfile must be used inside ProfileProvider");
  return ctx;
}
