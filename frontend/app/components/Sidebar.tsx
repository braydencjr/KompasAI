"use client";

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

export default function Sidebar() {
  const { source, cv } = useProfile();
  const journey = useOptionalJourney();
  const fromCv = source === "cv";
  const current = STEPS.findIndex((s) => s.id === journey?.step);

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
            <Icon d={ICONS[s.id]} />
            <span>{s.label}</span>
          </a>
        ))}
      </nav>

      <SidebarSnapshot />

      <div className="user">
        <div className="avatar">{fromCv ? "Y" : "A"}</div>
        <div>
          <div className="user-name">{fromCv ? "Your profile" : "Aisyah (sample)"}</div>
          <div className="user-role">{fromCv ? cv?.jobs[0]?.title ?? "From your CV" : "Accounts Executive"}</div>
        </div>
      </div>
    </aside>
  );
}
