"use client";

import Link from "next/link";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useAuth } from "./Auth";
import { useJourney } from "./journey/JourneyProvider";
import { useStepGate } from "./journey/RouteGate";

const DISMISSED = "kompas:nudge-dismissed";

/** On the Learning Route, when nobody is signed in: a callout beside the sidebar's Sign in button, so people know
 * their progress is only safe with an account. Dismissed for the rest of the visit with "Not now". */
export default function AuthNudge({ anchor }: { anchor: React.RefObject<HTMLElement | null> }) {
  const { user, ready } = useAuth();
  const { step } = useJourney();
  const gate = useStepGate("route");
  const [dismissed, setDismissed] = useState(true);
  // `top` is the callout's own top edge, `arrow` how far down it the button's centre is
  const [at, setAt] = useState<{ top: number; left: number; arrow: number } | null>(null);
  const box = useRef<HTMLElement>(null);

  useEffect(() => {
    try {
      setDismissed(sessionStorage.getItem(DISMISSED) === "1");
    } catch {
      setDismissed(false);
    }
  }, []);

  const show = ready && !user && step === "route" && !gate && !dismissed;

  // centred on the button, then moved up or down so the whole callout stays in the window (the button sits near the
  // bottom of the sidebar, and a centred callout would run off the screen)
  useLayoutEffect(() => {
    if (!show) return;
    const place = () => {
      const r = anchor.current?.getBoundingClientRect();
      if (!r) return;
      const h = box.current?.offsetHeight ?? 0;
      const centre = r.top + r.height / 2;
      const top = Math.max(16, Math.min(centre - h / 2, window.innerHeight - h - 16));
      setAt({ top, left: r.right + 16, arrow: Math.max(20, Math.min(centre - top, h - 20)) });
    };
    place();
    window.addEventListener("resize", place);
    return () => window.removeEventListener("resize", place);
  }, [show, anchor]);

  // the button glows while the callout points at it
  useEffect(() => {
    const el = anchor.current;
    if (!show || !el) return;
    el.classList.add("nudged");
    return () => el.classList.remove("nudged");
  }, [show, anchor]);

  if (!show) return null;

  function dismiss() {
    setDismissed(true);
    try {
      sessionStorage.setItem(DISMISSED, "1");
    } catch {}
  }

  return createPortal(
    <aside ref={box} className="auth-nudge glass" role="status"
      style={(at ? { top: at.top, left: at.left, "--arrow": `${at.arrow}px` } : { top: 0, left: 0, visibility: "hidden" }) as React.CSSProperties}>
      <strong>Sign in to save your learning progress</strong>
      <p>Without an account, your progress can be lost if this browser&apos;s data is cleared or you switch device.</p>
      <div className="auth-nudge-actions">
        <Link href="/login" className="btn btn-primary btn-sm" onClick={() => rememberPage()}>Sign in / Sign up</Link>
        <button className="sim-link" onClick={dismiss}>Not now</button>
      </div>
    </aside>,
    document.body,
  );
}

const AFTER_LOGIN = "kompas:after-login";

/** so the sign-in page can send people back to the page they were on */
export function rememberPage() {
  try {
    sessionStorage.setItem(AFTER_LOGIN, window.location.hash);
  } catch {}
}

export function pageAfterLogin(): string {
  try {
    const hash = sessionStorage.getItem(AFTER_LOGIN) ?? "";
    sessionStorage.removeItem(AFTER_LOGIN);
    return /^#[a-z]*$/.test(hash) ? hash : "";
  } catch {
    return "";
  }
}
