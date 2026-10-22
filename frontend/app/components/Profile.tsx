"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { profile as sampleProfile } from "../data/bets";
import { extractProfile, type CvProfile, type CvRole, type Profile } from "../lib/kompas";

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

/** A CV being read: drives the scanner animation in section 01. */
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
    .slice(0, 22)
    .map((l) => (l.length > 96 ? `${l.slice(0, 95)}…` : l));
}

export function ProfileProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<Stored>(SAMPLE);
  const [scan, setScan] = useState<Scan | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    try {
      const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "null");
      if (saved?.source === "cv" && Array.isArray(saved.cv?.roles)) setState(saved);
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
    try {
      const lines = /\.(txt|md)$/i.test(file.name) ? textLines(await file.text()) : null;
      setScan({ name: file.name, lines, result: null });
      // a floor on the scan so the animation reads even when the API answers instantly
      const [res] = await Promise.all([extractProfile(file), wait(2000)]);
      if ("error" in res) {
        setError(res.error);
        return;
      }
      if (!Array.isArray(res.profile.roles) || !Array.isArray(res.profile.skills)) {
        setError("The Kompas API is out of date. Restart it and try again.");
        return;
      }
      setScan({ name: file.name, lines, result: res.profile });
      await wait(1700); // let the found lines light up before the panel replaces the scanner
      save({ source: "cv", cv: res.profile, skills: res.profile.skills.map((s) => s.id), roleIsco: res.profile.roles[0]?.isco ?? null });
    } catch {
      setError("Something went wrong reading this CV. Please try again.");
    } finally {
      // whatever happened, never leave the scanner on screen
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
    reset: () => {
      setError(null);
      save(SAMPLE);
    },
  };

  return <ProfileContext.Provider value={value}>{children}</ProfileContext.Provider>;
}

export function useProfile() {
  const ctx = useContext(ProfileContext);
  if (!ctx) throw new Error("useProfile must be used inside ProfileProvider");
  return ctx;
}
