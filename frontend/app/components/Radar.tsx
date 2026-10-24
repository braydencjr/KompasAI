"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { LiveNotificationFeed, type LiveNotification } from "@/components/ui/live-notification-feed";
import { onFeedStream, radar, type FeedEvent, type LiveStatus, type RadarBrief, type RadarFamily, type RadarNews, type RadarRepo, type RadarSince, type RadarTrendSkill, type RadarTrends } from "../lib/kompas";

function ago(iso: string | null) {
  if (!iso) return "no data yet";
  const hours = (Date.now() - new Date(iso).getTime()) / 3_600_000;
  if (hours < 1) return "just now";
  if (hours < 24) return `${Math.floor(hours)}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

const REFRESH_MS = 60_000;
const MAX_NOTIFICATIONS = 20;   // the live feed keeps the latest few
const DRIP_MS = 40_000;         // a burst of arrivals enters the feed one at a time, this far apart
const SEED = 6;                 // stories already in the feed when the page opens

const SOURCE_ACCENT: Record<RadarNews["source"], string> = { my_news: "#0ea5e9", reddit: "#ff4500", hn_front: "#f59e0b" };

/** "r/malaysia" means nothing to most people: say it is Malaysians talking on Reddit. */
function outletName(n: RadarNews) {
  return n.source === "reddit" ? `Reddit · ${n.outlet.replace(/^r\//, "")} forum` : n.outlet;
}

/** A shown story as a live-feed notification. */
function newsNotice(n: RadarNews): LiveNotification {
  const more = n.outlets.length - 1;
  return {
    id: `news:${n.id}`, kind: "discussion", app: outletName(n), title: n.headline, body: n.dek ?? undefined, time: ago(n.first_seen),
    accent: SOURCE_ACCENT[n.source], points: n.points ?? undefined, comments: n.comments ?? undefined,
    rate: more > 0 ? `Also covered by ${more} more outlet${more > 1 ? "s" : ""}` : n.career === 3 ? "About jobs, pay or skills" : "A change in an industry",
  };
}

function notify(e: FeedEvent): LiveNotification {
  if (e.type === "news") return newsNotice(e.item);
  const i = e.item;
  const base = { id: `${i.artifact_id}:${e.seq}`, app: i.kind === "repo" ? "GitHub" : "Hacker News", title: i.title, time: ago(i.published_at) };
  const concept = i.concepts?.[0]?.label;
  const body = e.type === "rising" ? `Picking up speed${concept ? ` · ${concept}` : ""}` : concept;
  return i.kind === "repo"
    ? { ...base, kind: "repo", accent: "#6366f1", body: body ?? i.description?.slice(0, 90), perDay: Math.round(i.momentum_raw), stars: i.stars }
    : { ...base, kind: "discussion", accent: "#f59e0b", body, points: i.points, rate: `${i.momentum_raw.toFixed(1)} ${i.momentum_label}` };
}

const GLOWS = [
  { className: "left-[4%] top-[8%] size-72", color: "#f59e0b" },
  { className: "right-[4%] top-[18%] size-80", color: "#6366f1" },
  { className: "bottom-[10%] left-[30%] size-72", color: "#ec4899" },
  { className: "bottom-[6%] right-[10%] size-64", color: "#0ea5e9" },
];
const TINT = "color-mix(in oklab, currentColor 15%, transparent)";

/** The component's own container: a soft rounded tray holding white cards. */
function Panel({ title, hint, icon, count, children }: { title: string; hint?: string; icon: string; count?: number; children: React.ReactNode }) {
  return (
    <section className="w-full rounded-[28px] border border-border bg-muted p-2 shadow-sm backdrop-blur-xl">
      <div className="flex items-center gap-2 px-3 pb-2.5 pt-2">
        <svg viewBox="0 0 24 24" aria-hidden className="size-[18px]" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round"><path d={icon} /></svg>
        <h2 className="m-0 text-sm font-semibold tracking-tight">{title}</h2>
        {count != null && <span className="min-w-5 rounded-full bg-foreground px-1.5 text-center text-[11px] font-semibold leading-5 text-white tabular-nums">{count}</span>}
        {hint && <span className="ml-auto text-xs text-muted-foreground">{hint}</span>}
      </div>
      <div className="flex flex-col gap-2 px-0.5 pb-1">{children}</div>
    </section>
  );
}

function Card({ href, children, className = "" }: { href?: string; children: React.ReactNode; className?: string }) {
  const cls = `relative block rounded-2xl border border-border bg-card p-3 text-card-foreground shadow-sm transition-shadow hover:shadow-md ${className}`;
  return href ? <a href={href} target="_blank" rel="noopener noreferrer" className={cls}>{children}</a> : <div className={cls}>{children}</div>;
}

function Chip({ children, color }: { children: React.ReactNode; color?: string }) {
  return <span className="rounded-full px-2 py-0.5 text-[11px] font-medium text-foreground" style={{ background: color ? TINT : "rgba(15,30,60,0.06)", color }}>{children}</span>;
}

function Move({ rank, prev }: { rank: number; prev: number | null }) {
  if (prev == null) return <span className="text-[11px] font-semibold text-indigo-600">NEW</span>;
  if (prev === rank) return <span className="text-[11px] text-muted-foreground">–</span>;
  return prev > rank
    ? <span className="text-[11px] font-semibold text-emerald-600">▲ {prev - rank}</span>
    : <span className="text-[11px] font-semibold text-rose-600">▼ {rank - prev}</span>;
}

const FIRST_SHOWN = 5;     // a list starts with this many and grows by MORE_STEP
const MORE_STEP = 10;

const TROPHY = "M8 4h8v5a4 4 0 0 1-8 0Z M8 6H5a3 3 0 0 0 3 4 M16 6h3a3 3 0 0 1-3 4 M12 13v4 M8.5 20h7 M10 17h4v3h-4Z";
const MEDALS = [
  { from: "#fde68a", to: "#f59e0b", ink: "#92400e", ring: "rgba(245, 158, 11, 0.45)" },
  { from: "#f1f5f9", to: "#94a3b8", ink: "#334155", ring: "rgba(148, 163, 184, 0.45)" },
  { from: "#fed7aa", to: "#c2410c", ink: "#7c2d12", ring: "rgba(194, 65, 12, 0.35)" },
];

/** Top three get a gold, silver or bronze tile; everyone else a plain number. */
function Medal({ rank, size = "lg" }: { rank: number; size?: "lg" | "sm" }) {
  const m = MEDALS[rank - 1];
  const box = size === "lg" ? "size-11 rounded-2xl" : "size-7 rounded-lg";
  if (!m) return <span className={`grid shrink-0 place-items-center bg-muted text-xs font-semibold tabular-nums text-muted-foreground ${box}`}>{rank}</span>;
  return (
    <span className={`relative grid shrink-0 place-items-center shadow-sm ${box}`}
      style={{ background: `linear-gradient(145deg, ${m.from}, ${m.to})`, color: m.ink, boxShadow: `0 4px 12px -4px ${m.ring}, inset 0 1px 0 rgba(255,255,255,0.7)` }}>
      {rank === 1
        ? <svg viewBox="0 0 24 24" aria-hidden className={size === "lg" ? "size-6" : "size-4"} fill="none" stroke="currentColor" strokeWidth={1.9} strokeLinecap="round" strokeLinejoin="round"><path d={TROPHY} /></svg>
        : <span className={`font-bold tabular-nums ${size === "lg" ? "text-base" : "text-xs"}`}>{rank}</span>}
    </span>
  );
}

function More({ shown, total, onMore, onLess }: { shown: number; total: number; onMore: () => void; onLess: () => void }) {
  if (total <= FIRST_SHOWN) return null;
  const left = total - shown;
  return (
    <button type="button" onClick={left > 0 ? onMore : onLess}
      className="mx-1 cursor-pointer rounded-2xl border border-dashed border-border bg-white/50 py-2 text-xs font-medium text-muted-foreground transition-colors hover:bg-card hover:text-foreground">
      {left > 0 ? `Show ${Math.min(MORE_STEP, left)} more · ${left} left` : "Show less"}
    </button>
  );
}

/** Starts at FIRST_SHOWN, grows by MORE_STEP; resets whenever `reset` changes. */
function useDisclosure(reset: unknown) {
  const [shown, setShown] = useState(FIRST_SHOWN);
  useEffect(() => setShown(FIRST_SHOWN), [reset]);
  return { shown, more: () => setShown((n) => n + MORE_STEP), less: () => setShown(FIRST_SHOWN) };
}

function Tabs<T extends string>({ value, options, onChange }: { value: T; options: { id: T; label: string; count?: number }[]; onChange: (v: T) => void }) {
  return (
    <div className="flex flex-wrap gap-1.5 px-2 pb-2">
      {options.map((o) => (
        <button key={o.id} type="button" onClick={() => onChange(o.id)}
          className={`cursor-pointer rounded-full border px-3 py-1 text-xs font-medium transition-colors ${value === o.id ? "border-foreground bg-foreground text-white" : "border-border bg-card text-muted-foreground hover:text-foreground"}`}>
          {o.label}{o.count != null && <span className="ml-1 tabular-nums opacity-60">{o.count}</span>}
        </button>
      ))}
    </div>
  );
}

/** A podium place: medal, what it is in plain words and the skill it teaches. */
function PodiumCard({ r, rank, prev }: { r: RadarRepo; rank: number; prev: number | null | undefined }) {
  const m = MEDALS[rank - 1];
  return (
    <a href={r.url} target="_blank" rel="noopener noreferrer"
      className="relative block rounded-2xl border border-border bg-card p-3 text-card-foreground shadow-sm transition-shadow hover:shadow-md"
      style={rank === 1 && m ? { background: `linear-gradient(135deg, ${m.from}40, #ffffff 55%)`, boxShadow: `0 0 0 1px ${m.ring}, 0 10px 24px -14px ${m.ring}` } : undefined}>
      <div className="flex gap-3">
        <Medal rank={rank} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
            <span className="font-medium">{r.language ?? "GitHub"}</span>
            {prev !== undefined && <Move rank={rank} prev={prev} />}
          </div>
          <div className="mt-1 truncate text-sm font-semibold leading-snug">{r.full_name}</div>
          <p className="m-0 mt-0.5 line-clamp-2 text-[13px] leading-snug text-muted-foreground">{r.plain || r.description || "GitHub repository"}</p>
          {r.skill && <div className="mt-2 flex flex-wrap gap-1.5"><Chip color="#6366f1">Skill: {r.skill.label}</Chip></div>}
        </div>
        <div className="shrink-0 text-right">
          <div className="text-xl font-semibold leading-none tracking-tight tabular-nums">+{r.period_stars.toLocaleString()}</div>
          <div className="mt-1 text-[11px] text-muted-foreground">★ gained</div>
          <div className="text-[11px] tabular-nums text-muted-foreground">{r.stars.toLocaleString()} total</div>
        </div>
      </div>
    </a>
  );
}

/** Below the podium: one line each, so a long ranking stays scannable. */
function RepoRow({ r, rank, prev }: { r: RadarRepo; rank: number; prev: number | null | undefined }) {
  return (
    <a href={r.url} target="_blank" rel="noopener noreferrer" title={r.plain ?? r.description}
      className="flex items-center gap-3 rounded-xl border border-border bg-card/80 px-3 py-2 text-card-foreground transition-colors hover:bg-card">
      <Medal rank={rank} size="sm" />
      <div className="min-w-0 flex-1">
        <div className="truncate text-[13px] font-semibold">{r.full_name}</div>
        <div className="truncate text-[11px] text-muted-foreground">{r.plain || r.description}</div>
      </div>
      {prev !== undefined && <Move rank={rank} prev={prev} />}
      <span className="shrink-0 text-sm font-semibold tabular-nums">+{r.period_stars.toLocaleString()} <span className="text-[11px] font-normal text-muted-foreground">★</span></span>
    </a>
  );
}

function Ranking({ items, showPrev, limit }: { items: RadarRepo[]; showPrev: boolean; limit: number }) {
  return (
    <>
      {items.slice(0, limit).map((r) => {
        const prev = showPrev ? r.prev_category_rank : undefined;
        return r.category_rank <= 3
          ? <PodiumCard key={r.full_name} r={r} rank={r.category_rank} prev={prev} />
          : <RepoRow key={r.full_name} r={r} rank={r.category_rank} prev={prev} />;
      })}
    </>
  );
}

/** GitHub Trending, one category at a time. */
function Repos({ data, since, onSince }: {
  data: { as_of: string | null; compared_to: string | null; categories: { label: string; count: number }[]; items: RadarRepo[] };
  since: RadarSince;
  onSince: (s: RadarSince) => void;
}) {
  const [tab, setTab] = useState<string | null>(null);
  const tabs = data.categories.map((c) => ({ id: c.label, label: c.label, count: c.count }));
  // the first category until one is picked, and again if the picked one is gone after a refresh
  const active = tabs.some((t) => t.id === tab) ? tab! : (tabs[0]?.id ?? "");
  const list = useDisclosure(`${active}|${since}`);
  const inTab = data.items.filter((r) => r.category === active);
  return (
    <Panel title="Trending on GitHub" hint={`${since === "daily" ? "stars gained today" : "stars gained this week"} · updated ${ago(data.as_of)} · refreshes hourly`} icon="M12 3.5l2.6 5.3 5.9.9-4.3 4.1 1 5.8L12 16.9 6.8 19.6l1-5.8-4.3-4.1 5.9-.9Z">
      <Tabs value={since} options={[{ id: "daily", label: "Today" }, { id: "weekly", label: "This week" }]} onChange={onSince} />
      {tabs.length > 0 && <Tabs value={active} options={tabs} onChange={setTab} />}
      {inTab.length === 0
        ? <Card><p className="m-0 text-sm text-muted-foreground">No trending repositories yet.</p></Card>
        : <>
          <Ranking items={inTab} showPrev={!!data.compared_to} limit={list.shown} />
          <More shown={list.shown} total={inTab.length} onMore={list.more} onLess={list.less} />
        </>}
    </Panel>
  );
}

const SERIF = { fontFamily: "var(--font-serif), Georgia, 'Times New Roman', serif" } as const;

const STATUS: Record<LiveStatus, { color: string }> = {
  "Act now": { color: "#059669" },
  Emerging: { color: "#d97706" },
  Watch: { color: "#64748b" },
  Stable: { color: "#94a3b8" },
  Declining: { color: "#e11d48" },
  Stalled: { color: "#be123c" },
};

function StatusPill({ status }: { status: LiveStatus }) {
  const c = STATUS[status].color;
  return <span className="rounded-full px-2 py-0.5 text-[11px] font-semibold" style={{ color: c, background: `color-mix(in oklab, ${c} 13%, transparent)` }}>{status}</span>;
}

function fmtMonth(iso: string | null) {
  return iso ? new Date(iso).toLocaleDateString("en-GB", { month: "short", year: "numeric" }) : "";
}

// ---------- widgets ----------

/** A tile on the Radar grid; `className` sets its size (column span). */
function Widget({ label, action, className = "", style, children }: {
  label?: string; action?: React.ReactNode; className?: string; style?: React.CSSProperties; children: React.ReactNode;
}) {
  return (
    <section className={`flex min-w-0 flex-col rounded-[24px] border border-border bg-white/85 p-5 shadow-sm backdrop-blur ${className}`} style={style}>
      {(label || action) && (
        <header className="mb-3 flex items-center justify-between gap-2">
          {label && <span className="text-[11px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">{label}</span>}
          {action}
        </header>
      )}
      {children}
    </section>
  );
}

// ---------- news of the day: the 3-month shift ----------

const FAMILY_PREVIEW = 3;

/** Skills that pass `keep`, grouped by field, fields that keep none left out. */
function byFamily(trends: RadarTrends, keep: (s: RadarTrendSkill) => boolean): RadarFamily[] {
  return trends.families.map((f) => ({ ...f, skills: f.skills.filter(keep) })).filter((f) => f.skills.length);
}

/** A list of skills, grouped by field, in a modal over the page. */
function SkillsModal({ eyebrow, title, intro, families, open, onClose }: {
  eyebrow: string; title: string; intro?: string; families: RadarFamily[]; open?: string; onClose: () => void;
}) {
  const dialogRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    dialogRef.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  // in a portal: the page's glass panels would otherwise become the fixed backdrop's containing block
  return createPortal(
    <div className="modal-backdrop" onClick={onClose}>
      <div ref={dialogRef} tabIndex={-1} className="modal glass" role="dialog" aria-modal="true" aria-labelledby="skills-title"
        onClick={(e) => e.stopPropagation()}>
        <header className="flex items-start gap-4">
          <div className="flex min-w-0 flex-1 flex-col gap-1">
            <span className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{eyebrow}</span>
            <h2 id="skills-title" className="m-0 py-0.5 text-[28px] font-semibold leading-snug tracking-tight text-foreground" style={SERIF}>{title}</h2>
            {intro && <p className="m-0 text-[13px] text-muted-foreground">{intro}</p>}
          </div>
          <button className="modal-close shrink-0 self-start" onClick={onClose} aria-label="Close">×</button>
        </header>
        {families.length === 0 && (
          <div className="rounded-2xl border border-dashed border-border bg-white/50 px-4 py-8 text-center text-sm text-muted-foreground">No skills yet.</div>
        )}
        {families.map((f) => <FamilyGroup key={f.id} f={f} open={open} />)}
      </div>
    </div>,
    document.body,
  );
}

/** One field's skills: the first few, the rest on request. */
function FamilyGroup({ f, open }: { f: RadarFamily; open?: string }) {
  const [all, setAll] = useState(false);
  const hidden = f.skills.length - FAMILY_PREVIEW;
  return (
    <div className="flex flex-col gap-2">
      <span className="text-[15px] font-semibold text-foreground" style={SERIF}>{f.label} <span className="font-sans text-xs font-normal text-muted-foreground">· {f.skills.length}</span></span>
      {(all ? f.skills : f.skills.slice(0, FAMILY_PREVIEW)).map((s) => <SkillRow key={s.id} s={s} defaultOpen={s.id === open} />)}
      {hidden > 0 && (
        <button type="button" onClick={() => setAll(!all)} className="cursor-pointer rounded-2xl border border-dashed border-border bg-white/50 py-2 text-xs font-medium text-muted-foreground hover:bg-card hover:text-foreground">
          {all ? "Show less" : `Show ${hidden} more in ${f.label}`}
        </button>
      )}
    </div>
  );
}

function BriefWidget({ b, className }: { b: RadarBrief; className: string }) {
  return (
    <Widget className={className} label="Highlight of The Day" style={{ background: "linear-gradient(135deg, rgba(255,255,255,0.96), rgba(238,242,255,0.9) 60%, rgba(254,243,199,0.7))" }}>
      <h2 className="m-0 text-[30px] font-semibold leading-[1.12] tracking-tight text-foreground sm:text-[36px]" style={SERIF}>{b.headline}</h2>
      <p className="m-0 mt-3 max-w-2xl text-[15px] leading-relaxed text-muted-foreground">{b.summary}</p>
    </Widget>
  );
}

/** The skills that moved on the ladder, most momentum first; a row opens that skill with its evidence. */
function MoversWidget({ trends, className, onOpen }: { trends: RadarTrends; className: string; onOpen: (m: { kind: "up" | "down"; skill?: string }) => void }) {
  const all = trends.families.flatMap((f) => f.skills);
  const up = all.filter((s) => s.move === "up").sort((a, b) => b.score - a.score);
  const down = all.filter((s) => s.move === "down");
  return (
    <Widget className={className} label={`Climbed since ${fmtMonth(trends.compared_to)}`}
      action={up.length > 5 && <button type="button" onClick={() => onOpen({ kind: "up" })} className="cursor-pointer border-0 bg-transparent p-0 text-[11px] font-medium text-muted-foreground hover:text-foreground">See all {up.length} →</button>}>
      {up.length === 0 && <p className="m-0 text-sm text-muted-foreground">No skill climbed.</p>}
      <ul className="m-0 flex list-none flex-col gap-1 p-0">
        {up.slice(0, 5).map((s) => (
          <li key={s.id}>
            <button type="button" onClick={() => onOpen({ kind: "up", skill: s.id })}
              className="flex w-full cursor-pointer items-center gap-2 rounded-xl border-0 bg-transparent px-2 py-1.5 text-left hover:bg-slate-500/5">
              <span className="text-emerald-600">↑</span>
              <span className="min-w-0 flex-1 truncate text-[13px] font-semibold text-foreground">{s.label}</span>
              {s.was && <span className="hidden text-[11px] text-muted-foreground sm:inline">{s.was} →</span>}
              <StatusPill status={s.status} />
            </button>
          </li>
        ))}
      </ul>
      {down.length > 0 && (
        <button type="button" onClick={() => onOpen({ kind: "down" })}
          className="mt-auto cursor-pointer border-0 bg-transparent px-2 pt-3 text-left text-[12px] font-medium text-rose-600 hover:underline">
          ↓ {down.length} skill{down.length === 1 ? "" : "s"} fell →
        </button>
      )}
    </Widget>
  );
}

// ---------- the front page ----------

function Byline({ s }: { s: RadarNews }) {
  const more = s.outlets.length - 1;
  return (
    <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-muted-foreground">
      <span className="font-semibold uppercase tracking-wide" style={{ color: SOURCE_ACCENT[s.source] }}>{outletName(s)}</span>
      <span>{ago(s.published_at)}</span>
      {s.points != null && <span>· {s.points.toLocaleString()} points</span>}
      {more > 0 && <span>· +{more} more outlet{more > 1 ? "s" : ""}</span>}
      {s.skill && <Chip color="#6366f1">{s.skill.label}</Chip>}
    </div>
  );
}

function StoryWidget({ s, read, onRead, className }: { s: RadarNews; read: boolean; onRead: () => void; className: string }) {
  return (
    <Widget className={`rd-land transition-opacity ${read ? "opacity-55" : ""} ${className}`} label={read ? "Read · next news lands soon" : s.career === 3 ? "Jobs & pay" : "In the news"}>
      <a href={s.url} target="_blank" rel="noopener noreferrer" onClick={onRead} className="group block text-foreground">
        <h4 className="m-0 text-[17px] font-bold leading-snug group-hover:underline" style={SERIF}>{s.headline}</h4>
        {s.dek && <p className="m-0 mt-1.5 line-clamp-3 text-[13px] leading-snug text-muted-foreground">{s.dek}</p>}
      </a>
      <div className="mt-auto pt-3"><Byline s={s} /></div>
    </Widget>
  );
}

const SLOTS = 4;
const DWELL_MS = 10 * 60_000;   // a story stays up this long unless it's read
const GAP_MS = 150_000;         // at most one slot changes in this time, so the page never churns
const TICK_MS = 15_000;
const READ_SWAP_MS = 2_500;     // how long a read card stays (dimmed) once you're back on the page
const READ_KEY = "kompas:news-read";
// at most this many of the four slots from one source or outlet, so no single feed takes over
const MAX_PER = { hn_front: 1, outlet: 2 } as const;

function loadRead(): Set<string> {
  try {
    return new Set(JSON.parse(localStorage.getItem(READ_KEY) ?? "[]") as string[]);
  } catch {
    return new Set();
  }
}

function saveRead(ids: Set<string>) {
  try {
    localStorage.setItem(READ_KEY, JSON.stringify([...ids].slice(-300)));
  } catch {}
}

type Slot = { id: string; shownAt: number };

/** Four stories from the ranked queue. A slot is replaced once its story is read, or after DWELL_MS; a much
 *  stronger story arriving replaces the weakest. Only one slot changes per GAP_MS. */
function NewsSlots({ queue, onShown }: { queue: RadarNews[]; onShown: (ids: string[]) => void }) {
  const [slots, setSlots] = useState<Slot[]>([]);
  const [read, setRead] = useState<Set<string>>(() => new Set());
  const retired = useRef(new Set<string>());   // rotated out unread: back only when the queue runs dry
  const lastChange = useRef(0);
  const byId = new Map(queue.map((n) => [n.id, n]));

  useEffect(() => setRead(loadRead()), []);

  const pick = useCallback((taken: string[], readNow: Set<string>): RadarNews | null => {
    const inSlots = taken.map((id) => byId.get(id)).filter(Boolean) as RadarNews[];
    const fits = (n: RadarNews) =>
      !taken.includes(n.id) && !readNow.has(n.id) &&
      (n.source !== "hn_front" || inSlots.filter((x) => x.source === "hn_front").length < MAX_PER.hn_front) &&
      inSlots.filter((x) => x.outlet === n.outlet).length < MAX_PER.outlet;
    return queue.find((n) => fits(n) && !retired.current.has(n.id))
      ?? (retired.current.clear(), queue.find(fits) ?? null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [queue]);

  // fill empty slots (first load, or stories that left the queue)
  useEffect(() => {
    setSlots((cur) => {
      const kept = cur.filter((sl) => byId.has(sl.id));
      const next = [...kept];
      while (next.length < SLOTS) {
        const n = pick(next.map((x) => x.id), read);
        if (!n) break;
        next.push({ id: n.id, shownAt: Date.now() });
      }
      return next.length === cur.length && next.every((x, i) => x.id === cur[i]?.id) ? cur : next;
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [queue, read, pick]);

  // timed rotation, one card at a time: the longest-shown first, then a much stronger newcomer
  useEffect(() => {
    const timer = window.setInterval(() => {
      if (document.hidden || Date.now() - lastChange.current < GAP_MS) return;
      setSlots((cur) => {
        const now = Date.now();
        const stale = cur.filter((sl) => read.has(sl.id) || now - sl.shownAt > DWELL_MS)
          .sort((a, b) => Number(read.has(b.id)) - Number(read.has(a.id)) || a.shownAt - b.shownAt)[0];
        let out = stale;
        if (!out) {
          const weakest = [...cur].sort((a, b) => (byId.get(a.id)?.rank_score ?? 0) - (byId.get(b.id)?.rank_score ?? 0))[0];
          const best = pick(cur.map((x) => x.id), read);
          if (weakest && best && best.rank_score > (byId.get(weakest.id)?.rank_score ?? 0) + 5) out = weakest;
        }
        if (!out) return cur;
        const others = cur.filter((x) => x.id !== out.id).map((x) => x.id);
        const n = pick(others, read);
        if (!n) return cur;
        if (!read.has(out.id)) retired.current.add(out.id);
        lastChange.current = now;
        return cur.map((x) => (x.id === out.id ? { id: n.id, shownAt: now } : x));
      });
    }, TICK_MS);
    return () => window.clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [read, pick, queue]);

  // a read card goes a few seconds after you're back on the page; the rotation gap is for unread cards only
  useEffect(() => {
    const due = slots.find((sl) => read.has(sl.id));
    if (!due) return;
    let timer = 0;
    const swap = () => {
      if (document.hidden) return;
      setSlots((cur) => {
        if (!cur.some((x) => x.id === due.id)) return cur;
        const n = pick(cur.filter((x) => x.id !== due.id).map((x) => x.id), read);
        if (!n) return cur;
        lastChange.current = Date.now();
        return cur.map((x) => (x.id === due.id ? { id: n.id, shownAt: Date.now() } : x));
      });
    };
    const later = () => { window.clearTimeout(timer); timer = window.setTimeout(swap, READ_SWAP_MS); };
    later();
    document.addEventListener("visibilitychange", later);
    return () => {
      window.clearTimeout(timer);
      document.removeEventListener("visibilitychange", later);
    };
  }, [slots, read, pick]);

  useEffect(() => onShown(slots.map((x) => x.id)), [slots, onShown]);

  const markRead = (id: string) => setRead((r) => {
    const next = new Set(r).add(id);
    saveRead(next);
    return next;
  });

  if (!slots.length) {
    return <Widget className="md:col-span-6 lg:col-span-12" label="In the news"><p className="m-0 text-sm text-muted-foreground">No career news yet. The next hourly update reads the latest stories.</p></Widget>;
  }
  return (
    <>
      {slots.map((sl) => {
        const n = byId.get(sl.id);
        return n && <StoryWidget key={sl.id} s={n} read={read.has(sl.id)} onRead={() => markRead(sl.id)} className="md:col-span-3 lg:col-span-3" />;
      })}
    </>
  );
}

// ---------- a skill and its evidence ----------

/** Talked about → hired abroad → hired in Malaysia: the three rungs of the Signal Ladder. */
function LadderSteps({ ladder }: { ladder: RadarTrendSkill["ladder"] }) {
  const steps = [
    { label: "Talked about", on: ladder.talk.active, tone: "#059669" },
    { label: "Hired abroad", on: ladder.abroad.active, tone: "#d97706" },
    { label: "Hired in Malaysia", on: ladder.malaysia.active, tone: "#059669" },
  ];
  return (
    <div className="flex flex-wrap items-center gap-1">
      {steps.map((st, i) => (
        <span key={st.label} className="flex items-center gap-1">
          {i > 0 && <span className="h-px w-3 bg-slate-300" />}
          <span className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium"
            style={st.on ? { color: st.tone, background: `color-mix(in oklab, ${st.tone} 13%, transparent)` } : { color: "#94a3b8", background: "rgba(148,163,184,0.1)" }}>
            <span className="size-1.5 rounded-full" style={{ background: st.on ? st.tone : "#cbd5e1" }} />{st.label}
          </span>
        </span>
      ))}
    </div>
  );
}

function Postings({ p }: { p: RadarTrendSkill["postings"] }) {
  if (!p || !p.roles.length) return <span className="text-[11px] text-muted-foreground">Not seen in our sample of Malaysian postings</span>;
  const top = p.roles[0];
  return <span className="text-[11px] text-muted-foreground">Malaysian postings: asked for in <strong className="font-semibold text-foreground">{top.count} of {top.of}</strong> {top.title} ads{p.roles.length > 1 ? ` and ${p.roles.length - 1} more role${p.roles.length > 2 ? "s" : ""}` : ""}</span>;
}

function SkillRow({ s, defaultOpen = false }: { s: RadarTrendSkill; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  const ev = s.evidence;
  const count = ev.news.length + ev.repos.length + (s.postings?.quote ? 1 : 0);
  return (
    <div className="rounded-2xl border border-border bg-card shadow-sm">
      <button type="button" onClick={() => setOpen(!open)} aria-expanded={open} className="flex w-full cursor-pointer gap-3 border-0 bg-transparent p-4 text-left text-card-foreground">
        <span className={`grid size-9 shrink-0 place-items-center rounded-xl text-base font-bold ${s.move === "up" ? "bg-emerald-500/12 text-emerald-600" : s.move === "down" ? "bg-rose-500/10 text-rose-600" : "bg-slate-500/8 text-slate-400"}`}>
          {s.move === "up" ? "↑" : s.move === "down" ? "↓" : "–"}
        </span>
        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-center gap-1.5">
            <span className="text-[15px] font-semibold">{s.label}</span>
            {s.was && <><StatusPill status={s.was} /><span className="text-[11px] text-muted-foreground">→</span></>}
            <StatusPill status={s.status} />
          </span>
          {s.plain && <span className="mt-0.5 block text-[13px] leading-snug text-foreground/80">{s.plain}</span>}
          <span className="mt-2 flex flex-col gap-1.5"><LadderSteps ladder={s.ladder} /><Postings p={s.postings} /></span>
        </span>
        {count > 0 && <span className="shrink-0 self-start text-[11px] font-medium text-muted-foreground">{open ? "Hide" : `Evidence · ${count}`}</span>}
      </button>
      {open && count > 0 && (
        <div className="grid gap-4 border-t border-border px-4 py-3 sm:grid-cols-3">
          <div>
            <span className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">In the news</span>
            {ev.news.length ? ev.news.map((n) => <a key={n.url} href={n.url} target="_blank" rel="noopener noreferrer" className="mt-1.5 block text-[13px] font-semibold leading-snug text-foreground hover:underline" style={SERIF}>{n.headline}</a>)
              : <p className="m-0 mt-1.5 text-[12px] text-muted-foreground">Nothing this week.</p>}
          </div>
          <div>
            <span className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">What people are building</span>
            {ev.repos.length ? ev.repos.map((r) => (
              <a key={r.url} href={r.url} target="_blank" rel="noopener noreferrer" className="mt-1.5 block text-[12px] leading-snug text-foreground/80 hover:underline">
                {r.plain} <span className="text-muted-foreground">({r.name}, +{r.stars_today.toLocaleString()} ★ today)</span>
              </a>
            )) : <p className="m-0 mt-1.5 text-[12px] text-muted-foreground">No trending project today.</p>}
          </div>
          <div>
            <span className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Malaysian employers</span>
            {s.postings?.quote ? <p className="m-0 mt-1.5 text-[12px] leading-snug text-foreground/80">“{s.postings.quote.text}” <span className="text-muted-foreground">— a {s.postings.quote.role} posting</span></p>
              : <p className="m-0 mt-1.5 text-[12px] text-muted-foreground">Not in our sample of postings.</p>}
          </div>
        </div>
      )}
    </div>
  );
}

export default function Radar() {
  const [brief, setBrief] = useState<RadarBrief | null>(null);
  const [trends, setTrends] = useState<RadarTrends | null>(null);
  const [news, setNews] = useState<RadarNews[] | null>(null);
  const [repos, setRepos] = useState<{ as_of: string | null; compared_to: string | null; categories: { label: string; count: number }[]; items: RadarRepo[] } | null>(null);
  const [since, setSince] = useState<RadarSince>("daily");
  const [failed, setFailed] = useState(false);
  const [modal, setModal] = useState<{ kind: "up" | "down"; skill?: string } | null>(null);
  const closeModal = useCallback(() => setModal(null), []);
  const [events, setEvents] = useState<LiveNotification[]>([]);
  const [feedReady, setFeedReady] = useState(false);
  const [connected, setConnected] = useState(false);
  const [replay, setReplay] = useState(false);
  const pending = useRef<LiveNotification[]>([]);
  const shown = useRef<string[]>([]);
  const urls = useRef(new Map<string, string>());
  const onShown = useCallback((ids: string[]) => { shown.current = ids; }, []);

  // arrivals wait here and enter the feed one by one, never as a burst
  const enqueue = useCallback((n: LiveNotification) => {
    setEvents((cur) => {
      if (!cur.some((x) => x.id === n.id) && !pending.current.some((x) => x.id === n.id)) pending.current.push(n);
      return cur;
    });
  }, []);
  useEffect(() => {
    const timer = window.setInterval(() => {
      const next = pending.current.shift();
      if (next) setEvents((cur) => [...cur, next].slice(-MAX_NOTIFICATIONS));
    }, DRIP_MS);
    return () => window.clearInterval(timer);
  }, []);

  const load = useCallback(() => {
    Promise.all([radar.brief(), radar.trends(), radar.news(), radar.repos(since)]).then(([b, t, n, r]) => {
      if (!b && !t && !n && !r) return setFailed(true);
      setFailed(false);
      if (b) setBrief(b);
      if (t) setTrends(t);
      setNews(n?.items ?? []);
      for (const item of n?.items ?? []) urls.current.set(`news:${item.id}`, item.url);
      setRepos(r ?? { as_of: null, compared_to: null, categories: [], items: [] });
    });
  }, [since]);

  useEffect(() => {
    load();
    const timer = window.setInterval(load, REFRESH_MS);
    return () => window.clearInterval(timer);
  }, [load]);

  useEffect(() => {
    let refresh = 0;
    const stop = onFeedStream(
      (e) => {
        setReplay(!!e.replay);
        if (e.type === "news") {
          urls.current.set(`news:${e.item.id}`, e.item.url);
          if (shown.current.includes(e.item.id)) return;   // already on the page
        } else {
          urls.current.set(notify(e).id, e.item.url);
        }
        enqueue(notify(e));
        window.clearTimeout(refresh);
        if (!e.replay) refresh = window.setTimeout(load, 5000);
      },
      setConnected,
    );
    return () => {
      stop();
      window.clearTimeout(refresh);
    };
  }, [load, enqueue]);

  // the feed opens with a few recent stories (not the ones in the slots), so it is never empty on arrival
  useEffect(() => {
    if (feedReady || !news) return;
    // the best-ranked stories not in the slots, at most a third from Hacker News; the strongest lands on top
    const seed: RadarNews[] = [];
    for (const n of news) {
      if (seed.length === SEED) break;
      if (shown.current.includes(n.id)) continue;
      if (n.source === "hn_front" && seed.filter((x) => x.source === "hn_front").length >= SEED / 3) continue;
      seed.push(n);
    }
    setEvents(seed.reverse().map(newsNotice));
    setFeedReady(true);
  }, [news, feedReady]);

  if (failed) {
    return <div className="feed-empty glass muted small">Can&apos;t reach the signal API. Start the backend (<code>cd backend &amp;&amp; .venv/bin/fastapi dev app/main.py</code>).</div>;
  }
  if (!news || !repos || !trends) return <div className="j-loading glass"><span className="sk sk-title" /><span className="sk sk-tile" /></div>;

  const modalProps = modal && {
    eyebrow: `since ${fmtMonth(trends.compared_to)}`,
    title: modal.kind === "up" ? "Skills that climbed" : "Skills that fell",
    families: byFamily(trends, (s) => s.move === modal.kind),
  };

  return (
    <div className="relative flex flex-col gap-4">
      <div aria-hidden className="pointer-events-none absolute inset-0 -z-10 overflow-hidden opacity-30">
        {GLOWS.map((g) => <span key={g.color} className={`absolute rounded-full blur-3xl ${g.className}`} style={{ background: g.color }} />)}
      </div>
      <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        <span className="inline-flex items-center gap-1.5 rounded-full border border-border bg-card px-2.5 py-1 font-medium text-foreground shadow-sm">
          <span className={`size-1.5 rounded-full ${connected ? "bg-emerald-500" : "bg-slate-400"}`} />
          {connected ? (replay ? "Replaying recorded events" : "Live") : "Stream offline"}
        </span>
        <span>Scores as of {trends.as_of ?? "–"} · news and projects refresh hourly</span>
      </div>

      {/* 12 columns on wide screens, 6 on tablets, 1 on phones; each widget's span is its size */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-6 lg:grid-cols-12">
        {brief?.headline && <BriefWidget b={brief} className="md:col-span-6 lg:col-span-8" />}
        <MoversWidget trends={trends} className="md:col-span-6 lg:col-span-4" onOpen={(o) => setModal(o)} />

        <NewsSlots queue={news} onShown={onShown} />

        <div className="min-w-0 self-start md:col-span-6 lg:col-span-8">
          <Repos data={repos} since={since} onSince={setSince} />
        </div>
        <div className="min-w-0 self-start md:col-span-6 lg:col-span-4">
          {feedReady && (
            <LiveNotificationFeed items={events} title="Live feed" height="420px"
              onOpen={(id) => { const url = urls.current.get(id); if (url) window.open(url, "_blank", "noopener"); }} />
          )}
        </div>
      </div>

      {modalProps && <SkillsModal {...modalProps} open={modal?.skill} onClose={closeModal} />}
    </div>
  );
}
