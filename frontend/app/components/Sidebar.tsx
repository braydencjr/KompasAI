"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const nav = [
  { label: "Home", href: "/", icon: "M3 11l9-7 9 7v9a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z" },
  { label: "The Mirror", href: "#", icon: "M12 3v18M5 5h14v14H5z" },
  { label: "Ghost CV", href: "#", icon: "M6 3h9l4 4v14H6zM9 12h7M9 16h5" },
  { label: "Signal Ladder", href: "#", icon: "M7 3v18M17 3v18M7 8h10M7 13h10M7 18h10" },
  { label: "My Roadmap", href: "/#plan", icon: "M5 19c4 0 4-14 8-14s4 14 6 14" },
];

function Icon({ d }: { d: string }) {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d={d} />
    </svg>
  );
}

export default function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="sidebar glass">
      <Link href="/" className="brand" aria-label="Kompas home">
        <img src="/kompas_logo.png" alt="Kompas logo" className="brand-mark" />
        Kompas
      </Link>

      <nav className="nav">
        {nav.map((item) => {
          const active = pathname === item.href;
          return (
            <Link key={item.label} href={item.href} className={`nav-item${active ? " active" : ""}`}>
              <Icon d={item.icon} />
              {item.label}
            </Link>
          );
        })}
      </nav>

      <div className="snapshot">
        <span className="pulse" />
        <div>
          <div className="snapshot-title">Live signals</div>
          <div className="snapshot-date">Snapshot · 20 Oct 2026</div>
        </div>
      </div>

      <div className="user">
        <div className="avatar">A</div>
        <div>
          <div className="user-name">Aisyah</div>
          <div className="user-role">Accounts Executive</div>
        </div>
      </div>
    </aside>
  );
}
