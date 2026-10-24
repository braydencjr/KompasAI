"use client";

import { useEffect, useState, type CSSProperties, type KeyboardEvent, type PointerEvent } from "react";

const KEY = "kompas:brief-width";
const DEFAULT = 360;
const MIN = 260;
const MAX = 640;
const MIN_WORK = 360;

const clamp = (n: number, room: number) => Math.round(Math.min(Math.max(n, MIN), Math.max(MIN, Math.min(MAX, room - MIN_WORK))));

/** A draggable divider between the brief and the workspace. The width is a per-viewer preference, kept in the browser. */
export function useSplit(): { style: CSSProperties; handle: React.ReactNode } {
  const [width, setWidth] = useState(DEFAULT);

  useEffect(() => {
    try {
      const saved = Number(localStorage.getItem(KEY));
      if (saved) setWidth(clamp(saved, Infinity));
    } catch {}
  }, []);

  const save = (n: number) => {
    setWidth(n);
    try {
      localStorage.setItem(KEY, String(n));
    } catch {}
  };

  function drag(e: PointerEvent<HTMLDivElement>) {
    const box = e.currentTarget.parentElement!.getBoundingClientRect();
    const target = e.currentTarget;
    target.setPointerCapture(e.pointerId);
    const move = (m: globalThis.PointerEvent) => setWidth(clamp(m.clientX - box.left, box.width));
    const up = (m: globalThis.PointerEvent) => {
      target.removeEventListener("pointermove", move);
      target.removeEventListener("pointerup", up);
      save(clamp(m.clientX - box.left, box.width));
    };
    target.addEventListener("pointermove", move);
    target.addEventListener("pointerup", up);
  }

  function key(e: KeyboardEvent<HTMLDivElement>) {
    const step = e.key === "ArrowLeft" ? -24 : e.key === "ArrowRight" ? 24 : 0;
    if (!step) return;
    e.preventDefault();
    save(clamp(width + step, e.currentTarget.parentElement!.getBoundingClientRect().width));
  }

  return {
    style: { "--brief-w": `${width}px` } as CSSProperties,
    handle: (
      <div className="split-handle" role="separator" aria-orientation="vertical" aria-label="Resize the brief"
        aria-valuenow={width} aria-valuemin={MIN} aria-valuemax={MAX} tabIndex={0}
        onPointerDown={drag} onKeyDown={key} onDoubleClick={() => save(DEFAULT)} title="Drag to resize · double-click to reset">
        <span />
      </div>
    ),
  };
}
