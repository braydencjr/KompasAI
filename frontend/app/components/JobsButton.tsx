"use client";

import { useCallback, useEffect, useState } from "react";
import { createPortal } from "react-dom";
import JobsPanel from "./JobsPanel";
import type { Bet } from "../data/bets";

/** "Job boards · Find open jobs →": opens a role's live openings in a popup. The same tile as in the roadmap popup,
 * for places that have no roadmap beside them (Your Kompas cards, The Route). */
export default function JobsButton({ bet }: { bet: Bet }) {
  const [open, setOpen] = useState(false);
  const close = useCallback(() => setOpen(false), []);

  // the page behind stays put while the popup is open
  useEffect(() => {
    if (!open) return;
    const main = document.querySelector<HTMLElement>(".main");
    const before = main?.style.overflow;
    if (main) main.style.overflow = "hidden";
    return () => {
      if (main) main.style.overflow = before ?? "";
    };
  }, [open]);

  return (
    <>
      <button className={`modal-stat jobs-cta${open ? " active" : ""}`} onClick={() => setOpen(true)} aria-haspopup="dialog">
        <span className="jobs-cta-icon" aria-hidden>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
            <rect x="3" y="7" width="18" height="13" rx="2.5" />
            <path d="M9 7V5.5A1.5 1.5 0 0 1 10.5 4h3A1.5 1.5 0 0 1 15 5.5V7M3 12.5h18" />
          </svg>
        </span>
        <div>
          <div className="label">Job boards</div>
          <span className="jobs-cta-text">Find open jobs →</span>
        </div>
      </button>
      {open &&
        // rendered at the page root: a glass card's backdrop-filter would otherwise trap the fixed popup inside it
        createPortal(
          <div className="modal-backdrop jobs-popup" onClick={close}>
            <JobsPanel bet={bet} closing={false} onClose={close} standalone />
          </div>,
          document.body,
        )}
    </>
  );
}
