"use client";

import * as React from "react";

export interface NotificationAction {
  label: string;
  /** Shown in place of the buttons once this action is picked, e.g. "Opened". */
  done?: string;
}

interface NotificationBase {
  id: string;
  /** Source name shown above the title. */
  app: string;
  title: string;
  body?: string;
  /** Age label such as "4m". Items that land while the feed is open read "now". */
  time?: string;
  /** Brand color for the tile and the live detail. Any CSS color. */
  accent?: string;
  read?: boolean;
  actions?: NotificationAction[];
}

export type RepoNotification = NotificationBase & { kind: "repo"; perDay: number; stars?: number; language?: string };
export type DiscussionNotification = NotificationBase & { kind: "discussion"; points?: number; comments?: number; rate?: string };
export type KeywordNotification = NotificationBase & { kind: "keyword"; term: string; change: number; mentions: number };

export type LiveNotification = RepoNotification | DiscussionNotification | KeywordNotification;
export type NotificationKind = LiveNotification["kind"];

export interface LiveNotificationFeedProps extends React.ComponentProps<"div"> {
  /** Notifications in the order they arrived. The newest sits on top, and items appended later land with their story. */
  items: LiveNotification[];
  title?: string;
  /** Replay the items one by one as if they were arriving now, for demos. Off by default, so real notifications show as given. */
  autoplay?: boolean;
  /** With autoplay, how many items are already in the feed when it starts. */
  initial?: number;
  /** Milliseconds between arrivals while autoplaying. */
  interval?: number;
  /** With autoplay, clear the feed and start again after the last arrival. */
  loop?: boolean;
  /** Height of the scrolling list, any CSS length. */
  height?: string;
  onOpen?: (id: string) => void;
  onAction?: (id: string, label: string) => void;
  onDismiss?: (id: string) => void;
}

interface Entry {
  id: string;
  key: string;
  play: number;
  fresh: boolean;
  leaving: boolean;
  arrived: boolean;
  delay: number;
  leaveDelay: number;
}

type StoryProps = {
  play: number;
  delay: number;
  reduced: boolean;
};

const FIRST_ARRIVAL_MS = 450;
const ENTER_MS = 460;
const LEAVE_MS = 340;
const SWEEP_STAGGER_MS = 60;
const STORY_DELAY_MS = 260;
const RESTART_HOLD = 2.2;
const COUNT_MS = 1100;
const SPRING = "cubic-bezier(0.2, 0.9, 0.25, 1.12)";
const SETTLE = "cubic-bezier(0.2, 0.8, 0.2, 1)";
const EXIT = "cubic-bezier(0.4, 0, 0.2, 1)";
const DEFAULT_HEIGHT = "min(440px, calc(100svh - 12rem))";
const TINT = "color-mix(in oklab, currentColor 15%, transparent)";

const ICONS: { [K in NotificationKind]: string } = {
  repo: "M12 3.5l2.6 5.3 5.9.9-4.3 4.1 1 5.8L12 16.9 6.8 19.6l1-5.8-4.3-4.1 5.9-.9Z",
  discussion: "M5.5 19v-3.4A7 7 0 0 1 4 11.2C4 7.2 7.6 4 12 4s8 3.2 8 7.2-3.6 7.2-8 7.2a9 9 0 0 1-2.7-.4Z",
  keyword: "M4 17l5-5 4 4 7-8 M15 8h5v5",
};

function cx(...classes: (string | false | null | undefined)[]) {
  return classes.filter(Boolean).join(" ");
}

function staticEntry(id: string, generation: number, fresh = false, delay = 0): Entry {
  return { id, key: `${id}:${generation}`, play: 0, fresh, leaving: false, arrived: false, delay, leaveDelay: 0 };
}

function useReducedMotion() {
  const [reduced, setReduced] = React.useState(false);
  React.useEffect(() => {
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReduced(query.matches);
    update();
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);
  return reduced;
}

function Icon({ d, className }: { d: string; className?: string }) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden className={className} fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round">
      <path d={d} />
    </svg>
  );
}

const BELL = "M6 16.5V11a6 6 0 1 1 12 0v5.5l1.5 1.5h-15Z M10 20.5a2.2 2.2 0 0 0 4 0";
const CLOSE = "M7 7l10 10M17 7 7 17";
const CHECK = "M5 12.5l4.2 4.2L19 7";

/** Counts from 0 to `target` when the story plays; shows the final value straight away without animation. */
function useCount(target: number, play: number, delay: number, reduced: boolean) {
  const animate = play > 0 && !reduced;
  const [value, setValue] = React.useState(animate ? 0 : target);
  React.useEffect(() => {
    if (!animate) {
      setValue(target);
      return;
    }
    const start = performance.now() + Math.max(80, delay);
    let frame = 0;
    const tick = (now: number) => {
      const k = Math.min(1, Math.max(0, (now - start) / COUNT_MS));
      setValue(Math.round(target * (1 - (1 - k) ** 3)));
      if (k < 1) frame = window.requestAnimationFrame(tick);
    };
    frame = window.requestAnimationFrame(tick);
    return () => window.cancelAnimationFrame(frame);
  }, [animate, play, delay, target]);
  return value;
}

function AppTile({ kind, accent, play, delay, reduced }: { kind: NotificationKind; accent?: string; play: number; delay: number; reduced: boolean }) {
  const ringRef = React.useRef(null as HTMLSpanElement | null);
  React.useEffect(() => {
    if (play === 0 || reduced) return;
    const animation = ringRef.current?.animate(
      [
        { transform: "scale(1)", opacity: 0.6 },
        { transform: "scale(1.75)", opacity: 0 },
      ],
      { duration: 900, delay, easing: "cubic-bezier(0.2, 0.7, 0.3, 1)" },
    );
    return () => animation?.cancel();
  }, [play, delay, reduced]);
  return (
    <span data-tile className={cx("relative grid size-9 shrink-0 place-items-center rounded-xl", !accent && "text-primary")} style={{ color: accent, background: TINT }}>
      <Icon d={ICONS[kind]} className="size-[18px]" />
      <span ref={ringRef} aria-hidden className="pointer-events-none absolute inset-0 rounded-xl border-2 border-current opacity-0" />
    </span>
  );
}

function RepoDetail({ item, play, delay, reduced }: StoryProps & { item: RepoNotification }) {
  const perDay = useCount(item.perDay, play, delay, reduced);
  return (
    <div data-detail="repo" className="flex items-baseline gap-2">
      <span className="text-2xl font-semibold leading-none tracking-tight text-foreground tabular-nums">+{perDay.toLocaleString("en-US")}</span>
      <span className="text-xs text-muted-foreground">★ a day{item.stars ? ` · ${item.stars.toLocaleString("en-US")} total` : ""}{item.language ? ` · ${item.language}` : ""}</span>
    </div>
  );
}

function DiscussionDetail({ item, play, delay, reduced }: StoryProps & { item: DiscussionNotification }) {
  const points = useCount(item.points ?? 0, play, delay, reduced);
  if (item.points == null) {
    return <div data-detail="discussion" className="text-xs text-muted-foreground">{item.rate ?? "Climbing on Hacker News"}</div>;
  }
  return (
    <div data-detail="discussion" className="flex items-baseline gap-2">
      <span className="text-2xl font-semibold leading-none tracking-tight text-foreground tabular-nums">{points.toLocaleString("en-US")} ▲</span>
      <span className="text-xs text-muted-foreground">{item.comments != null ? `${item.comments.toLocaleString("en-US")} comments` : "upvotes"}</span>
    </div>
  );
}

function KeywordDetail({ item, play, delay, reduced }: StoryProps & { item: KeywordNotification }) {
  const change = useCount(Math.abs(item.change), play, delay, reduced);
  return (
    <div data-detail="keyword" className="flex items-center gap-2">
      <span className="rounded-full px-2.5 py-1 font-mono text-sm font-semibold text-foreground" style={{ background: TINT }}>{item.term}</span>
      <span className="text-sm font-semibold tabular-nums text-foreground">{item.change < 0 ? "−" : "+"}{change}%</span>
      <span className="text-xs text-muted-foreground">{item.mentions.toLocaleString("en-US")} mentions</span>
    </div>
  );
}

function Detail({ item, play, delay, reduced }: { item: LiveNotification; play: number; delay: number; reduced: boolean }) {
  switch (item.kind) {
    case "repo":
      return <RepoDetail item={item} play={play} delay={delay} reduced={reduced} />;
    case "discussion":
      return <DiscussionDetail item={item} play={play} delay={delay} reduced={reduced} />;
    case "keyword":
      return <KeywordDetail item={item} play={play} delay={delay} reduced={reduced} />;
  }
}

function NotificationCard({
  item,
  entry,
  read,
  done,
  reduced,
  onOpen,
  onAction,
  onDismiss,
}: {
  item: LiveNotification;
  entry: Entry;
  read: boolean;
  done: string | undefined;
  reduced: boolean;
  onOpen: () => void;
  onAction: (action: NotificationAction) => void;
  onDismiss: () => void;
}) {
  const [entered, setEntered] = React.useState(!entry.fresh || reduced);
  React.useEffect(() => {
    if (entered) return;
    let second = 0;
    const first = window.requestAnimationFrame(() => {
      second = window.requestAnimationFrame(() => setEntered(true));
    });
    return () => {
      window.cancelAnimationFrame(first);
      window.cancelAnimationFrame(second);
    };
  }, [entered]);

  const shown = entered && !entry.leaving;
  const duration = entry.leaving ? LEAVE_MS : ENTER_MS;
  const lag = entry.leaving ? entry.leaveDelay : entry.delay;
  const rowTransition = reduced ? "none" : `grid-template-rows ${duration}ms ${entry.leaving ? EXIT : SETTLE} ${lag}ms`;
  const cardTransition = reduced
    ? "none"
    : `transform ${duration}ms ${entry.leaving ? EXIT : SPRING} ${lag}ms, opacity ${Math.round(duration * 0.7)}ms ease ${lag}ms`;
  const storyDelay = entry.fresh ? STORY_DELAY_MS + entry.delay : 0;
  const accentScope = { color: item.accent };
  const accentClass = item.accent ? undefined : "text-primary";

  return (
    <div
      role="listitem"
      data-notification={item.id}
      data-kind={item.kind}
      data-read={read ? "" : undefined}
      data-leaving={entry.leaving ? "" : undefined}
      data-play={entry.play}
      className="grid"
      style={{ gridTemplateRows: shown ? "1fr" : "0fr", transition: rowTransition }}
    >
      <div className="min-h-0 overflow-hidden">
        <div className="px-1 pb-2 pt-0.5">
          <article
            aria-label={`${item.app}: ${item.title}`}
            className="group relative rounded-2xl border border-border bg-card p-3 text-card-foreground shadow-sm"
            style={{ transform: shown ? "none" : entry.leaving ? "translateX(18%) scale(0.98)" : "translateY(-16px) scale(0.96)", opacity: shown ? 1 : 0, transition: cardTransition }}
          >
            <div className="flex gap-3">
              <AppTile kind={item.kind} accent={item.accent} play={entry.play} delay={storyDelay} reduced={reduced} />
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-1.5 pr-6 text-xs text-muted-foreground">
                  <span className="truncate font-medium">{item.app}</span>
                  <span aria-hidden>·</span>
                  <span data-time className="shrink-0 tabular-nums">
                    {entry.arrived ? "now" : (item.time ?? "")}
                  </span>
                </div>
                <button
                  type="button"
                  data-open
                  onClick={onOpen}
                  onKeyDown={(event) => {
                    if (event.key !== "Delete" && event.key !== "Backspace") return;
                    event.preventDefault();
                    onDismiss();
                  }}
                  className="mt-0.5 block w-full cursor-pointer border-0 bg-transparent p-0 text-left text-sm font-semibold leading-snug text-inherit outline-none after:absolute after:inset-0 after:rounded-2xl after:content-[''] focus-visible:after:ring-2 focus-visible:after:ring-ring"
                >
                  {item.title}
                </button>
                {item.body && <p className="mt-0.5 text-[13px] leading-snug text-muted-foreground">{item.body}</p>}
                <div className={cx("mt-2.5", accentClass)} style={accentScope}>
                  <Detail item={item} play={entry.play} delay={storyDelay} reduced={reduced} />
                  {item.actions && item.actions.length > 0 && (
                    <div className="relative z-[1] mt-2.5 flex flex-wrap items-center gap-2">
                      {done ? (
                        <span data-done className="inline-flex h-7 items-center gap-1.5 rounded-full px-2.5 text-xs font-medium" style={{ background: TINT }}>
                          <Icon d={CHECK} className="size-3.5" />
                          <span className="text-foreground">{done}</span>
                        </span>
                      ) : (
                        item.actions.map((action, i) => (
                          <button
                            key={action.label}
                            type="button"
                            data-action={action.label}
                            onClick={(event) => {
                              event.stopPropagation();
                              onAction(action);
                            }}
                            className={cx(
                              "h-7 cursor-pointer rounded-full px-3 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                              i === 0 ? "border-0 bg-foreground text-white hover:opacity-85" : "border border-border bg-white/60 text-foreground hover:bg-muted",
                            )}
                          >
                            {action.label}
                          </button>
                        ))
                      )}
                    </div>
                  )}
                </div>
              </div>
            </div>
            {!read && (
              <span
                data-unread
                aria-hidden
                className={cx("absolute right-3.5 top-3.5 size-2 rounded-full transition-opacity group-hover:opacity-0", !item.accent && "bg-primary")}
                style={item.accent ? { background: item.accent } : undefined}
              />
            )}
            <button
              type="button"
              data-dismiss
              aria-label={`Dismiss ${item.title}`}
              onClick={(event) => {
                event.stopPropagation();
                onDismiss();
              }}
              className="absolute right-2 top-2 z-[2] grid size-6 cursor-pointer place-items-center rounded-full border-0 bg-transparent text-muted-foreground opacity-0 transition-opacity hover:bg-muted hover:text-foreground focus-visible:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring group-hover:opacity-100"
            >
              <Icon d={CLOSE} className="size-3.5" />
            </button>
          </article>
        </div>
      </div>
    </div>
  );
}

export function LiveNotificationFeed({
  items,
  title = "Live",
  autoplay = false,
  initial = 2,
  interval = 1500,
  loop = false,
  height = DEFAULT_HEIGHT,
  onOpen,
  onAction,
  onDismiss,
  ref,
  className,
  onPointerEnter,
  onPointerLeave,
  onFocus,
  onBlur,
  ...rest
}: LiveNotificationFeedProps) {
  const reduced = useReducedMotion();
  const startCount = autoplay ? Math.min(Math.max(0, Math.round(initial)), items.length) : items.length;
  const [entries, setEntries] = React.useState(() => items.slice(0, startCount).map((item) => staticEntry(item.id, 0)));
  const [readIds, setReadIds] = React.useState(() => new Set(items.filter((item) => item.read).map((item) => item.id)));
  const [done, setDone] = React.useState((): { [id: string]: string } => ({}));
  const [announcement, setAnnouncement] = React.useState("");
  const cursor = React.useRef(startCount);
  const generation = React.useRef(0);
  const paused = React.useRef(false);
  const timers = React.useRef([] as number[]);
  const bellRef = React.useRef(null as SVGSVGElement | null);
  const itemsRef = React.useRef(items);
  itemsRef.current = items;
  const initialRef = React.useRef(initial);
  initialRef.current = initial;
  const reducedRef = React.useRef(reduced);
  reducedRef.current = reduced;
  const entriesRef = React.useRef(entries);
  entriesRef.current = entries;
  const handlers = React.useRef({ onOpen, onAction, onDismiss });
  handlers.current = { onOpen, onAction, onDismiss };

  const itemsKey = items.map((item) => item.id).join("\u0000");
  const byId = React.useMemo(() => new Map(items.map((item) => [item.id, item])), [items]);
  const showAll = !autoplay || reduced;

  React.useEffect(() => {
    const pending = timers.current;
    return () => pending.forEach((timer) => window.clearTimeout(timer));
  }, []);

  const later = React.useCallback((run: () => void, ms: number) => {
    timers.current.push(window.setTimeout(run, ms));
  }, []);

  const ringBell = React.useCallback(() => {
    if (reducedRef.current) return;
    bellRef.current?.animate(
      [
        { transform: "rotate(0deg)" },
        { transform: "rotate(16deg)" },
        { transform: "rotate(-12deg)" },
        { transform: "rotate(7deg)" },
        { transform: "rotate(-3deg)" },
        { transform: "rotate(0deg)" },
      ],
      { duration: 720, easing: "ease-out" },
    );
  }, []);

  const arrive = React.useCallback(
    (id: string) => {
      const item = itemsRef.current.find((candidate) => candidate.id === id);
      if (!item) return;
      generation.current += 1;
      const entry: Entry = { id, key: `${id}:${generation.current}`, play: 1, fresh: !reducedRef.current, leaving: false, arrived: true, delay: 0, leaveDelay: 0 };
      setEntries((prev) => [...prev.filter((e) => e.id !== id), entry]);
      setReadIds((prev) => {
        if (prev.has(id) === Boolean(item.read)) return prev;
        const next = new Set(prev);
        if (item.read) next.add(id);
        else next.delete(id);
        return next;
      });
      setDone((prev) => {
        if (!(id in prev)) return prev;
        const next = { ...prev };
        delete next[id];
        return next;
      });
      setAnnouncement(`${item.app}: ${item.title}`);
      ringBell();
    },
    [ringBell],
  );

  const removeKeys = React.useCallback(
    (keys: string[], after: number) => {
      later(() => setEntries((prev) => prev.filter((e) => !keys.includes(e.key))), after);
    },
    [later],
  );

  const clearAll = React.useCallback(() => {
    const visible = entriesRef.current.filter((e) => !e.leaving).reverse();
    if (visible.length === 0) return 0;
    const step = reducedRef.current ? 0 : SWEEP_STAGGER_MS;
    const order = new Map(visible.map((e, i) => [e.key, i]));
    setEntries((prev) => prev.map((e) => (order.has(e.key) ? { ...e, leaving: true, leaveDelay: order.get(e.key)! * step } : e)));
    const total = reducedRef.current ? 0 : LEAVE_MS + (visible.length - 1) * step;
    removeKeys(
      visible.map((e) => e.key),
      total,
    );
    return total;
  }, [removeKeys]);

  const restart = React.useCallback(() => {
    const list = itemsRef.current;
    const count = Math.min(Math.max(0, Math.round(initialRef.current)), list.length);
    cursor.current = count;
    generation.current += 1;
    const gen = generation.current;
    setEntries(list.slice(0, count).map((item, i) => staticEntry(item.id, gen, !reducedRef.current, (count - 1 - i) * 90)));
    setReadIds(new Set(list.filter((item) => item.read).map((item) => item.id)));
    setDone({});
  }, []);

  React.useEffect(() => {
    if (showAll || itemsRef.current.length === 0) return;
    let timer = 0;
    const step = () => {
      if (paused.current) {
        timer = window.setTimeout(step, 300);
        return;
      }
      const list = itemsRef.current;
      if (cursor.current < list.length) {
        const next = list[cursor.current]!;
        cursor.current += 1;
        arrive(next.id);
        timer = window.setTimeout(step, cursor.current < list.length ? interval : interval * RESTART_HOLD);
        return;
      }
      if (!loop) return;
      const took = clearAll();
      timer = window.setTimeout(() => {
        restart();
        timer = window.setTimeout(step, FIRST_ARRIVAL_MS + 500);
      }, took + 200);
    };
    timer = window.setTimeout(step, FIRST_ARRIVAL_MS);
    return () => window.clearTimeout(timer);
  }, [showAll, interval, loop, itemsKey, arrive, clearAll, restart]);

  const lastShowAll = React.useRef(showAll);
  const lastItemsKey = React.useRef(itemsKey);
  React.useEffect(() => {
    const modeChanged = lastShowAll.current !== showAll;
    const itemsChanged = lastItemsKey.current !== itemsKey;
    const previousIds = new Set(lastItemsKey.current.split("\u0000"));
    lastShowAll.current = showAll;
    lastItemsKey.current = itemsKey;
    if (!modeChanged && !itemsChanged) return;
    const list = itemsRef.current;
    if (!showAll) {
      restart();
      return;
    }
    if (modeChanged) {
      generation.current += 1;
      const gen = generation.current;
      setEntries((prev) => {
        const kept = new Map(prev.filter((e) => !e.leaving).map((e) => [e.id, e]));
        return list.map((item) => kept.get(item.id) ?? staticEntry(item.id, gen));
      });
      cursor.current = list.length;
      return;
    }
    const ids = new Set(list.map((item) => item.id));
    setEntries((prev) => prev.filter((e) => ids.has(e.id)));
    list.filter((item) => !previousIds.has(item.id)).forEach((item) => arrive(item.id));
  }, [showAll, itemsKey, restart, arrive]);

  const markRead = (id: string) => setReadIds((prev) => (prev.has(id) ? prev : new Set(prev).add(id)));

  const live = entries.filter((e) => !e.leaving);
  const unread = live.filter((e) => !readIds.has(e.id)).length;
  const ordered = [...entries].reverse();
  const pause = (value: boolean) => {
    paused.current = value;
  };

  return (
    <div
      ref={ref}
      data-slot="live-notification-feed"
      data-unread={unread}
      className={cx("w-full rounded-[28px] border border-border bg-muted p-2 text-foreground shadow-sm backdrop-blur-xl", className)}
      onPointerEnter={(event) => {
        pause(true);
        onPointerEnter?.(event);
      }}
      onPointerLeave={(event) => {
        pause(event.currentTarget.contains(document.activeElement));
        onPointerLeave?.(event);
      }}
      onFocus={(event) => {
        pause(true);
        onFocus?.(event);
      }}
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node | null)) pause(event.currentTarget.matches(":hover"));
        onBlur?.(event);
      }}
      {...rest}
    >
      <div className="flex items-center gap-2 px-3 pb-2.5 pt-2">
        <svg
          ref={bellRef}
          viewBox="0 0 24 24"
          aria-hidden
          className="size-[18px]"
          style={{ transformOrigin: "50% 12%" }}
          fill="none"
          stroke="currentColor"
          strokeWidth={1.8}
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d={BELL} />
        </svg>
        <h2 className="m-0 text-sm font-semibold tracking-tight">{title}</h2>
        <span
          data-count
          aria-label={`${unread} unread`}
          className={cx("min-w-5 rounded-full bg-foreground px-1.5 text-center text-[11px] font-semibold leading-5 text-white tabular-nums transition-opacity", unread === 0 && "opacity-0")}
        >
          {unread}
        </span>
        <div className="ml-auto flex items-center gap-0.5">
          <button
            type="button"
            data-read-all
            disabled={unread === 0}
            onClick={() => setReadIds((prev) => new Set([...prev, ...live.map((e) => e.id)]))}
            className="cursor-pointer rounded-full border-0 bg-transparent px-2.5 py-1 text-xs font-medium text-muted-foreground transition-colors hover:bg-white/70 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-40"
          >
            Read all
          </button>
          <button
            type="button"
            data-clear
            disabled={live.length === 0}
            onClick={clearAll}
            className="cursor-pointer rounded-full border-0 bg-transparent px-2.5 py-1 text-xs font-medium text-muted-foreground transition-colors hover:bg-white/70 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-40"
          >
            Clear
          </button>
        </div>
      </div>
      <div className="relative">
        <div
          role="list"
          aria-label={title}
          className="overflow-y-auto overscroll-contain px-0.5 pb-6 [scrollbar-width:thin]"
          style={{
            height,
            maskImage: "linear-gradient(to bottom, black calc(100% - 28px), transparent)",
            WebkitMaskImage: "linear-gradient(to bottom, black calc(100% - 28px), transparent)",
          }}
        >
          {ordered.map((entry) => {
            const item = byId.get(entry.id);
            if (!item) return null;
            return (
              <NotificationCard
                key={entry.key}
                item={item}
                entry={entry}
                read={readIds.has(entry.id)}
                done={done[entry.id]}
                reduced={reduced}
                onOpen={() => {
                  markRead(entry.id);
                  setEntries((prev) => prev.map((e) => (e.key === entry.key ? { ...e, play: e.play + 1, fresh: false, delay: 0 } : e)));
                  handlers.current.onOpen?.(entry.id);
                }}
                onAction={(action) => {
                  markRead(entry.id);
                  setDone((prev) => ({ ...prev, [entry.id]: action.done ?? action.label }));
                  handlers.current.onAction?.(entry.id, action.label);
                }}
                onDismiss={() => {
                  setEntries((prev) => prev.map((e) => (e.key === entry.key ? { ...e, leaving: true, leaveDelay: 0 } : e)));
                  removeKeys([entry.key], reduced ? 0 : LEAVE_MS);
                  handlers.current.onDismiss?.(entry.id);
                }}
              />
            );
          })}
        </div>
        {entries.length === 0 && (
          <div data-empty className="pointer-events-none absolute inset-0 grid place-items-center text-center">
            <div>
              <span className="mx-auto grid size-10 place-items-center rounded-full bg-white/70 text-muted-foreground">
                <Icon d={CHECK} className="size-5" />
              </span>
              <p className="mt-2 text-sm font-medium">Quiet for now</p>
              <p className="text-xs text-muted-foreground">New signals will land here as they happen.</p>
            </div>
          </div>
        )}
      </div>
      <p aria-live="polite" className="sr-only">
        {announcement}
      </p>
    </div>
  );
}

export default LiveNotificationFeed;
