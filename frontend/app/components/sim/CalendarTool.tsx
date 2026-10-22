"use client";

import { useState } from "react";
import type { CalendarTask } from "../../data/simulations";

type Props = { task: CalendarTask; onDone: (score: number, evidence: string[]) => void };
type Slot = { day: number; hour: number };

const hh = (h: number) => `${String(h).padStart(2, "0")}:00`;
const slotKey = (s: Slot) => s.day * 24 + s.hour;

export function calendarIssues(task: CalendarTask, placed: Record<string, Slot>) {
  const issues: Record<string, string[]> = {};
  for (const ev of task.events) {
    const p = placed[ev.id];
    const list: string[] = (issues[ev.id] = []);
    if (!p) {
      list.push("Not booked");
      continue;
    }
    const busy = ev.people.filter((n) => task.busy[n]?.[p.day]?.includes(p.hour));
    if (busy.length) list.push(`${busy.join(", ")} ${busy.length > 1 ? "are" : "is"} busy`);
    const d = ev.deadline;
    if (d && (p.day > d.day || (p.day === d.day && p.hour + 1 > d.hour))) list.push(`Finishes after the ${d.label} deadline`);
    for (const other of task.events)
      if (other.id !== ev.id && placed[other.id] && slotKey(placed[other.id]) === slotKey(p)) list.push(`Clashes with ${other.title}`);
    if (ev.after) {
      const dep = placed[ev.after];
      const title = task.events.find((e) => e.id === ev.after)?.title;
      if (dep && slotKey(dep) >= slotKey(p)) list.push(`Must come after ${title}`);
    }
  }
  return issues;
}

export default function CalendarTool({ task, onDone }: Props) {
  const [placed, setPlaced] = useState<Record<string, Slot>>({});
  const [selected, setSelected] = useState(task.events[0].id);
  const [moves, setMoves] = useState(0);
  const [done, setDone] = useState(false);

  const ev = task.events.find((e) => e.id === selected)!;
  const issues = done ? calendarIssues(task, placed) : null;

  function place(day: number, hour: number) {
    if (done) return;
    setPlaced((p) => ({ ...p, [selected]: { day, hour } }));
    setMoves((m) => m + 1);
    // jump to the next unbooked meeting
    const next = task.events.find((e) => e.id !== selected && !placed[e.id]);
    if (next) setSelected(next.id);
  }

  function submit() {
    const all = calendarIssues(task, placed);
    const ok = task.events.filter((e) => all[e.id].length === 0).length;
    const extra = moves - task.events.length;
    setDone(true);
    onDone(ok / task.events.length, [
      `${ok} of ${task.events.length} meetings booked with no conflicts`,
      extra > 0 ? `Rescheduled ${extra} time${extra > 1 ? "s" : ""} before sending` : "Booked first time, no reshuffling",
    ]);
  }

  const allPlaced = task.events.every((e) => placed[e.id]);

  return (
    <div className="tool tool-cal">
      <div className="tool-bar">
        <span className="tool-file">▤ Calendar · this week</span>
        <span className="muted small">Pick a meeting, then click a slot</span>
      </div>

      <div className="cal-events">
        {task.events.map((e) => {
          const p = placed[e.id];
          const bad = issues?.[e.id] ?? [];
          return (
            <button
              key={e.id}
              className={`cal-chip${selected === e.id && !done ? " on" : ""}${issues ? (bad.length ? " bad" : " good") : ""}`}
              onClick={() => setSelected(e.id)}
              disabled={done}
            >
              <strong>{e.title}</strong>
              <span>{e.people.join(", ")} · 1 h</span>
              <span className="cal-when">{p ? `${task.days[p.day]} ${hh(p.hour)}` : "Not booked yet"}</span>
              {bad.length > 0 && <span className="cal-issue">{bad.join(" · ")}</span>}
            </button>
          );
        })}
      </div>

      <div className="sheet-wrap">
        <div className="cal-grid" style={{ gridTemplateColumns: `56px repeat(${task.days.length}, minmax(84px, 1fr))` }}>
          <span />
          {task.days.map((d) => (
            <span key={d} className="cal-day">
              {d}
            </span>
          ))}
          {task.hours.map((h) => (
            <div key={h} className="cal-row">
              <span className="cal-hour">{hh(h)}</span>
              {task.days.map((_, day) => {
                const busy = ev.people.filter((n) => task.busy[n]?.[day]?.includes(h));
                const here = task.events.filter((e) => placed[e.id]?.day === day && placed[e.id]?.hour === h);
                return (
                  <button
                    key={day}
                    className={`cal-cell${busy.length && !done ? " busy" : ""}`}
                    onClick={() => place(day, h)}
                    disabled={done}
                    title={busy.length ? `Busy: ${busy.join(", ")}` : "Free"}
                    aria-label={`${task.days[day]} ${hh(h)}${busy.length ? `, busy: ${busy.join(", ")}` : ""}`}
                  >
                    {!done && busy.length > 0 && !here.length && <span className="cal-busy">{busy.map((n) => n.split(" ")[0]).join(", ")}</span>}
                    {here.map((e) => (
                      <span key={e.id} className={`cal-block${e.id === selected && !done ? " on" : ""}`}>
                        {e.title}
                      </span>
                    ))}
                  </button>
                );
              })}
            </div>
          ))}
        </div>
      </div>

      {!done && (
        <button className="btn btn-primary tool-submit" disabled={!allPlaced} onClick={submit}>
          {allPlaced ? "Send invites" : `Book all ${task.events.length} meetings to send`}
        </button>
      )}
    </div>
  );
}
