"use client";

import { useEffect, useState } from "react";
import LiveFeed from "../LiveFeed";
import { journeyApi, type Ping } from "../../lib/journey";
import { useJourney } from "./JourneyProvider";
import { BriefBox, Status, useLadder } from "./shared";

const BET_NAMES = { safe: "Safest switch", rising: "Fastest-growing", impact: "Biggest impact" } as const;

export default function StepPing() {
  const { catalog, request, snapshot, set } = useJourney();
  const openLadder = useLadder();
  const snapshots = catalog?.snapshots ?? [];
  const latest = catalog?.latest_snapshot ?? null;
  const active = snapshot ?? latest;
  // default comparison: about three months before the active snapshot
  const activeIndex = snapshots.findIndex((s) => s.id === active);
  const [from, setFrom] = useState<string | null>(null);
  const fromId = from ?? snapshots[Math.max(0, activeIndex - 3)]?.id ?? null;
  const [ping, setPing] = useState<Ping | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);

  const key = JSON.stringify({ ...request, fromId, active });
  useEffect(() => {
    if (!fromId || !active || fromId === active) return;
    const ctrl = new AbortController();
    setRunning(true);
    journeyApi
      .ping({ ...request, from_snapshot: fromId, to_snapshot: active }, ctrl.signal)
      .then((p) => {
        setPing(p);
        setError(null);
      })
      .catch((e) => !ctrl.signal.aborted && setError(e instanceof Error ? e.message : String(e)))
      .finally(() => !ctrl.signal.aborted && setRunning(false));
    return () => ctrl.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  return (
    <div className="j-ping-step">
      <section className="j-demo glass">
        <div>
          <span className="label">Snapshots · demo control</span>
          <p className="muted small">Kompas re-scores the market on every snapshot. Pick two and see what changed for you.</p>
        </div>
        <div className="j-demo-controls">
          <label>
            <span className="muted small">From</span>
            <select value={fromId ?? ""} onChange={(e) => setFrom(e.target.value)}>
              {snapshots.filter((s) => s.id !== active).map((s) => <option key={s.id} value={s.id}>{s.as_of}</option>)}
            </select>
          </label>
          <span className="j-arrow big" aria-hidden>→</span>
          <label>
            <span className="muted small">To (the whole app uses this)</span>
            <select value={active ?? ""} onChange={(e) => set({ snapshot: e.target.value === latest ? null : e.target.value })}>
              {snapshots.map((s) => <option key={s.id} value={s.id}>{s.as_of}{s.id === latest ? " · latest" : ""}</option>)}
            </select>
          </label>
        </div>
      </section>

      {error && <p className="muted">{error}</p>}
      {running && !ping && <div className="j-loading glass"><span className="sk sk-title" /><span className="sk sk-tile" /></div>}

      {ping && (
        <div className={`j-ping${running ? " refreshing" : ""}`} key={`${ping.from.id}-${ping.to.id}`}>
          <BriefBox request={{ ...request, kind: "ping", from_snapshot: ping.from.id, snapshot: ping.to.id }} />
          {!ping.changed && <p className="muted">Nothing that affects you changed between {ping.from.as_of} and {ping.to.as_of}.</p>}

          {ping.skills.length > 0 && (
            <section className="j-changes glass">
              <span className="label">Your skills on the Signal Ladder</span>
              <ul>
                {ping.skills.map((s, i) => (
                  <li key={s.id} className="reveal" style={{ "--i": i } as React.CSSProperties}>
                    <button className="link" onClick={() => openLadder(s.id)}>{s.label}</button>
                    <Status status={s.to} from={s.from} />
                    <span className="muted small">{s.reason}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}

          <div className="j-ping-grid">
            <section className="j-changes glass">
              <span className="label">Your bets</span>
              {ping.bets.length === 0 ? <p className="muted small">No change.</p> : (
                <ul>
                  {ping.bets.map((b, i) => (
                    <li key={b.kind} className="reveal" style={{ "--i": i } as React.CSSProperties}>
                      <strong>{BET_NAMES[b.kind]}</strong>
                      <span className="j-was">{b.from ? `${b.from.title} ${b.from.match}%` : "none"}</span>
                      <span className="j-arrow">→</span>
                      <span>{b.to ? `${b.to.title} ${b.to.match}%` : "none"}</span>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            <section className="j-changes glass">
              <span className="label">Your CV in 2028</span>
              {ping.ghost.new_slots.length + ping.ghost.gone_slots.length === 0 ? <p className="muted small">No change.</p> : (
                <ul>
                  {ping.ghost.new_slots.map((s) => <li key={s.id}>New blank: <strong>{s.label}</strong></li>)}
                  {ping.ghost.gone_slots.map((s) => <li key={s.id} className="j-was">No longer a gap the market is moving to: {s.label}</li>)}
                </ul>
              )}
              <p className="muted small">AI-exposed tasks: {ping.mirror.from}% → {ping.mirror.to}%</p>
            </section>
          </div>

          {ping.route.changed && (
            <section className="j-changes glass">
              <span className="label">Your route, re-planned</span>
              <div className="j-reorder">
                {[ping.route.from, ping.route.to].map((order, col) => (
                  <ol key={col} className={col ? "after" : "before"}>
                    <span className="muted small">{col ? ping.to.as_of : ping.from.as_of}</span>
                    {order.map((id, i) => <li key={id} style={{ "--i": i } as React.CSSProperties}>{i + 1}. {ping.route.labels[id] ?? id}</li>)}
                  </ol>
                ))}
              </div>
            </section>
          )}
        </div>
      )}

      <LiveFeed />
    </div>
  );
}
