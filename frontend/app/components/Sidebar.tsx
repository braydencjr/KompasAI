"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useProfile } from "./Profile";
import { useAuth } from "./Auth";
import AuthNudge, { rememberPage } from "./AuthNudge";
import { SidebarSnapshot } from "./Signals";
import { STEPS, useOptionalJourney } from "./journey/JourneyProvider";

const ICONS: Record<string, string> = {
  you: "M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM4 21a8 8 0 0 1 16 0",
  future: "M6 3h9l4 4v14H6zM9 12h7M9 16h5",
  bets: "M4 20V10M10 20V4M16 20v-7M22 20H2",
  route: "M5 19c4 0 4-14 8-14s4 14 6 14",
  radar: "M12 12l6-6M12 21a9 9 0 1 1 9-9M12 17a5 5 0 1 1 5-5M12 12h.01",
};

function Icon({ d }: { d: string }) {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d={d} />
    </svg>
  );
}

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
  const pathname = usePathname();
  const onRadar = pathname.startsWith("/radar");
  const current = onRadar ? -1 : STEPS.findIndex((s) => s.id === journey?.step);
  const user = useUserName();
  const displayName = fromCv ? user.name : "Aisyah (sample)";
  const auth = useAuth();
  const cta = useRef<HTMLAnchorElement>(null);

  return (
    <aside className="sidebar glass">
      <Link href="/" className="brand" aria-label="Kompas home">
        <img src="/kompas_logo.png" alt="Kompas logo" className="brand-mark" />
        Kompas
      </Link>

      <nav className="nav j-rail" aria-label="Your journey">
        <span className="j-rail-line" aria-hidden><span style={{ height: `${(Math.max(current, 0) / (STEPS.length - 1)) * 100}%` }} /></span>
        {STEPS.map((s, i) => (
          <a key={s.id} href={`/#${s.id}`}
            className={`nav-item${i === current ? " active" : ""}${i < current ? " done" : ""}`}
            onClick={(e) => {
              if (!journey || onRadar) return;
              e.preventDefault();
              journey.go(s.id);
            }}>
            <span className="nav-node"><Icon d={ICONS[s.id]} /></span>
            <span>{s.label}</span>
          </a>
        ))}
      </nav>

      <nav className="nav" aria-label="Live">
        <Link href="/radar" className={`nav-item${onRadar ? " active" : ""}`}>
          <span className="nav-node"><Icon d={ICONS.radar} /></span>
          <span>AI Live Trend</span>
          <span className="nav-live" aria-hidden />
        </Link>
      </nav>

      <SidebarSnapshot />

      {auth.ready && !auth.user && (
        <Link href="/login" ref={cta} className="btn btn-primary btn-sm auth-cta" onClick={rememberPage}>
          Sign in / Sign up
        </Link>
      )}
      {journey && <AuthNudge anchor={cta} />}

      {auth.user && (
        <div className="user">
          <div className="avatar" aria-hidden>{auth.user.name[0].toUpperCase()}</div>
          <div className="user-text">
            <div className="user-name">{auth.user.name}</div>
            <div className="user-role">{auth.user.email}</div>
            <button className="user-signout" onClick={() => void auth.signOut()}>Sign out</button>
          </div>
        </div>
      )}
    </aside>
  );
}
