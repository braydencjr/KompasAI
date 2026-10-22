"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { kompas, onFeedEvent, type FeedItem, type LiveStatus, type Match, type SignalCard } from "../lib/kompas";
import { useOptionalJourney } from "./journey/JourneyProvider";
import { useProfile } from "./Profile";
import { signalClass, useSignals } from "./Signals";

function ago(iso: string) {
  const hours = (Date.now() - new Date(iso).getTime()) / 3_600_000;
  if (hours < 1) return "just now";
  if (hours < 24) return `${Math.floor(hours)}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

const GITHUB_MARK =
  "M12 .5C5.7.5.5 5.7.5 12c0 5.1 3.3 9.4 7.9 10.9.6.1.8-.3.8-.6v-2c-3.2.7-3.9-1.4-3.9-1.4-.5-1.3-1.3-1.7-1.3-1.7-1-.7.1-.7.1-.7 1.2.1 1.8 1.2 1.8 1.2 1 1.8 2.7 1.3 3.4 1 .1-.8.4-1.3.7-1.5-2.6-.3-5.2-1.3-5.2-5.7 0-1.3.5-2.3 1.2-3.1-.1-.3-.5-1.5.1-3 0 0 1-.3 3.2 1.2a11 11 0 0 1 5.8 0c2.2-1.5 3.2-1.2 3.2-1.2.6 1.6.2 2.8.1 3 .7.8 1.2 1.8 1.2 3.1 0 4.4-2.7 5.4-5.3 5.7.4.4.8 1.1.8 2.1v3.2c0 .3.2.7.8.6A11.5 11.5 0 0 0 23.5 12C23.5 5.7 18.3.5 12 .5z";

/** One trending item, shown as evidence: what it is, and how fast it's gaining attention. */
function Evidence({ item }: { item: FeedItem }) {
  const repo = item.kind === "repo";
  return (
    <li>
      <a className="evidence" href={item.url} target="_blank" rel="noopener noreferrer">
        <span className={`evidence-icon ${repo ? "gh" : "hn"}`} aria-hidden>
          {repo ? (
            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d={GITHUB_MARK} /></svg>
          ) : (
            "Y"
          )}
        </span>
        <span className="evidence-text">
          <span className="evidence-title">{item.title}</span>
          <span className="evidence-sub">
            {repo ? item.description || "GitHub repository" : `Hacker News · ${ago(item.published_at)}`}
          </span>
        </span>
        <span className="evidence-metric">
          {repo ? (
            <>
              <strong>+{Math.round(item.momentum_raw).toLocaleString()} ★</strong>
              <span>a day · {(item.stars ?? 0).toLocaleString()} total</span>
            </>
          ) : (
            <>
              <strong>{(item.points ?? 0).toLocaleString()} ▲</strong>
              <span>upvotes</span>
            </>
          )}
        </span>
      </a>
    </li>
  );
}

/** Card accent follows the ladder status: blue for hiring, amber for buzz only, rose for fading. */
function tone(status: LiveStatus) {
  if (status === "Act now") return "tone-hot";
  if (status === "Emerging") return "tone-rising";
  if (status === "Watch") return "tone-watch";
  if (status === "Declining" || status === "Stalled") return "tone-down";
  return "tone-calm";
}

const RELATION_ICON: Record<SignalCard["relation"], string> = {
  exposed: "M12 3v4M12 17v4M3 12h4M17 12h4M6.3 6.3l2.5 2.5M15.2 15.2l2.5 2.5M6.3 17.7l2.5-2.5M15.2 8.8l2.5-2.5",
  route: "M5 19c4 0 4-14 8-14s4 14 6 14",
  have: "M5 12.5l4.5 4.5L19 7.5",
  related: "M9.5 14.5l5-5M8 17a3.5 3.5 0 0 1-5-5l2.5-2.5M16 7a3.5 3.5 0 0 1 5 5l-2.5 2.5",
};

/** The Signal Ladder in miniature: how far this skill has got from talk to Malaysian hiring. */
function Ladder({ ladder }: { ladder: SignalCard["ladder"] }) {
  const malaysia = ladder.malaysia === "concept" ? "on" : ladder.malaysia === "family" ? "half" : "";
  const malaysiaTitle =
    ladder.malaysia === "family" && ladder.family_label
      ? `Hiring in Malaysia is rising for ${ladder.family_label} roles that use this skill`
      : undefined;
  return (
    <ol className="ladder" aria-label="Signal Ladder">
      <li className="on">Talked about</li>
      <li className={ladder.abroad ? "on" : ""}>Hiring abroad</li>
      <li className={malaysia} title={malaysiaTitle}>Hiring in Malaysia</li>
    </ol>
  );
}

function Card({ card, fresh, index }: { card: SignalCard; fresh: boolean; index: number }) {
  return (
    <li className={`signal-card glass reveal ${tone(card.status)}${fresh ? " fresh" : ""}`}
      style={{ "--i": index } as React.CSSProperties}>
      <div className="signal-card-head">
        <span className={`relation rel-${card.relation}`}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
            strokeLinecap="round" strokeLinejoin="round" aria-hidden>
            <path d={RELATION_ICON[card.relation]} />
          </svg>
          {card.relation_label}
        </span>
        <span className={signalClass(card.status)}>{card.status}</span>
      </div>
      <h3>{card.headline}</h3>

      <div className="trending">
        <div className="label">Trending now</div>
        <ul>
          {card.items.map((item) => (
            <Evidence key={item.artifact_id} item={item} />
          ))}
        </ul>
      </div>

      <div className="hiring">
        <div className="label">Is anyone hiring for it?</div>
        {card.ladder && <Ladder ladder={card.ladder} />}
        <p className="muted small">{card.meaning}</p>
      </div>

      <p className="signal-action">
        <span className="signal-action-arrow" aria-hidden>→</span>
        {card.action}
      </p>
    </li>
  );
}

export default function LiveFeed() {
  const [data, setData] = useState<Match | null>(null);
  const [offline, setOffline] = useState(false);
  const [loading, setLoading] = useState(true);
  const [fresh, setFresh] = useState<Set<string>>(new Set());
  const pending = useRef<Set<string>>(new Set());
  const { matchProfile: sampleOrCv } = useProfile();
  // inside the journey, follow its profile: Mirror corrections and the chosen route
  const journey = useOptionalJourney();
  const matchProfile = journey?.data?.feed_profile ?? sampleOrCv;
  // the server answers but has nothing scored yet: say so, rather than "offline"
  const { health } = useSignals();
  const noSnapshot = health !== null && !health.latest_snapshot;
  // re-match whenever the profile's contents change, not on every render
  const profileKey = JSON.stringify(matchProfile);

  const load = useCallback(async () => {
    setLoading(true);
    const res = await kompas.match({ ...JSON.parse(profileKey), limit: 5 });
    setLoading(false);
    setOffline(res === null);
    if (res) {
      setData(res);
      setFresh(new Set(pending.current));
      pending.current.clear();
    }
  }, [profileKey]);

  useEffect(() => {
    load();
    let timer: ReturnType<typeof setTimeout> | undefined;
    // re-match shortly after a burst of stream events, then highlight the cards they touched
    const stop = onFeedEvent((id) => {
      pending.current.add(id);
      clearTimeout(timer);
      timer = setTimeout(load, 1500);
    });
    return () => {
      stop();
      clearTimeout(timer);
    };
  }, [load]);

  const statusChanges = data?.ping.filter((c) => c.field === "status") ?? [];

  return (
    <section>
      <div className="section-head">
        <div>
          <span className="kicker">03 — Live feed</span>
          <h2>What moved for you</h2>
          <p className="muted small">
            What people are building and talking about, checked against who is actually hiring.
          </p>
        </div>
        {data && <span className="muted small">Hiring data as of {data.snapshot}</span>}
      </div>

      {offline && noSnapshot && (
        <div className="feed-empty glass muted small">
          No signal snapshot yet. Ingest and score one: <code>cd backend &amp;&amp; .venv/bin/kompas fetch all &amp;&amp; .venv/bin/kompas snapshot</code>
        </div>
      )}

      {offline && !noSnapshot && (
        <div className="feed-empty glass muted small">
          Live signals are offline. Start the backend (<code>cd backend &amp;&amp; .venv/bin/fastapi dev app/main.py</code>) to see what&apos;s moving.
        </div>
      )}

      {!data && !offline && (
        <ul className="feed" aria-label="Loading your feed">
          {[0, 1].map((i) => (
            <li key={i} className="signal-card glass skeleton">
              <span className="sk sk-chip" />
              <span className="sk sk-title" />
              <span className="sk sk-tile" />
              <span className="sk sk-tile" />
              <span className="sk sk-line" />
              <span className="sk sk-action" />
            </li>
          ))}
        </ul>
      )}

      {data && (
        <div className={`feed-summary glass${loading ? " refreshing" : ""}`}>
          <span className="pulse" />
          <p>
            {/* the backend writes "Verdict: detail"; the verdict is what the eye should catch */}
            {data.summary.includes(":") ? (
              <>
                <strong>{data.summary.split(":")[0]}.</strong> {data.summary.split(":").slice(1).join(":").trim()}
              </>
            ) : (
              <strong>{data.summary}</strong>
            )}
          </p>
        </div>
      )}

      {statusChanges.length > 0 && (
        <div className="ping glass">
          <div className="label">Changed since the last update</div>
          <ul>
            {statusChanges.map((c) => (
              <li key={c.concept_id}>
                <strong>{c.label}</strong> moved from {c.from} to {c.to}
              </li>
            ))}
          </ul>
        </div>
      )}

      {data && data.signals.length > 0 && (
        <ul className={`feed${loading ? " refreshing" : ""}`}>
          {data.signals.map((card, i) => (
            <Card key={`${data.snapshot}:${card.concept_id}`} card={card} index={i}
              fresh={card.items.some((item) => fresh.has(item.artifact_id))} />
          ))}
        </ul>
      )}
    </section>
  );
}
