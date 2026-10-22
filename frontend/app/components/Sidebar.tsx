"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useProfile } from "./Profile";
import { SidebarSnapshot } from "./Signals";
import { STEPS, useOptionalJourney } from "./journey/JourneyProvider";

const ICONS: Record<string, string> = {
  you: "M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM4 21a8 8 0 0 1 16 0",
  future: "M6 3h9l4 4v14H6zM9 12h7M9 16h5",
  bets: "M4 20V10M10 20V4M16 20v-7M22 20H2",
  route: "M5 19c4 0 4-14 8-14s4 14 6 14",
  ping: "M12 3a6 6 0 0 1 6 6v4l2 3H4l2-3V9a6 6 0 0 1 6-6zM10 20a2 2 0 0 0 4 0",
};

function Icon({ d }: { d: string }) {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d={d} />
    </svg>
  );
}

// Kompas never reads names from a CV (privacy), so the name is whatever the person types, kept in this browser
const NAME_KEY = "kompas:username";

function useUserName() {
  const [name, setName] = useState("");
  const [editing, setEditing] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    try {
      setName(localStorage.getItem(NAME_KEY) ?? "");
    } catch {}
  }, []);

  useEffect(() => {
    if (editing) inputRef.current?.select();
  }, [editing]);

  function save(value: string) {
    const clean = value.trim().slice(0, 40);
    setName(clean);
    setEditing(false);
    try {
      if (clean) localStorage.setItem(NAME_KEY, clean);
      else localStorage.removeItem(NAME_KEY);
    } catch {}
  }

  return { name: name || "User", editing, setEditing, save, inputRef };
}

export default function Sidebar() {
  const { source, cv } = useProfile();
  const journey = useOptionalJourney();
  const fromCv = source === "cv";
  const current = STEPS.findIndex((s) => s.id === journey?.step);
  const user = useUserName();
  const displayName = fromCv ? user.name : "Aisyah (sample)";

  return (
    <aside className="sidebar glass">
      <Link href="/" className="brand" aria-label="Kompas home">
        <img src="/kompas_logo.png" alt="Kompas logo" className="brand-mark" />
        Kompas
      </Link>

      <nav className="nav j-rail" aria-label="Your journey">
        <span className="j-rail-line" aria-hidden><span style={{ height: `${(Math.max(current, 0) / (STEPS.length - 1)) * 100}%` }} /></span>
        {STEPS.map((s, i) => (
          <a key={s.id} href={`#${s.id}`}
            className={`nav-item${i === current ? " active" : ""}${i < current ? " done" : ""}`}
            onClick={(e) => {
              if (!journey) return;
              e.preventDefault();
              journey.go(s.id);
            }}>
            <span className="nav-node"><Icon d={ICONS[s.id]} /></span>
            <span>{s.label}</span>
          </a>
        ))}
      </nav>

      <SidebarSnapshot />

      <div className="user">
        <div className="avatar" aria-hidden>{displayName[0].toUpperCase()}</div>
        <div className="user-text">
          {fromCv && user.editing ? (
            <input
              ref={user.inputRef}
              className="user-name-input"
              defaultValue={user.name === "User" ? "" : user.name}
              placeholder="Your name"
              aria-label="Your name"
              maxLength={40}
              onBlur={(e) => user.save(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") user.save(e.currentTarget.value);
                if (e.key === "Escape") user.setEditing(false);
              }}
            />
          ) : fromCv ? (
            <button className="user-name user-name-edit" onClick={() => user.setEditing(true)} title="Click to change your name">
              {displayName}
            </button>
          ) : (
            <div className="user-name">{displayName}</div>
          )}
          <div className="user-role">{fromCv ? cv?.jobs[0]?.title ?? "From your CV" : "Accounts Executive"}</div>
        </div>
      </div>
    </aside>
  );
}
