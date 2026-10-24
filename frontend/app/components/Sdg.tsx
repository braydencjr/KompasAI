"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { createPortal } from "react-dom";
import {
  goalBg, goalUrl, ON_GOAL, readSdgTags, SDG_NAMES, sdgSettled, subscribeSdg, wantSdgTags, type SdgTagData,
} from "../lib/sdg";

type Subject = {
  subject: string;
  kind: "skill" | "role";
  tag: SdgTagData;
  /** for a group of skills: how each one contributes to this goal */
  reasons?: { subject: string; rationale: string }[];
};
const PopupCtx = createContext<(s: Subject) => void>(() => {});

/** Click an SDG tag anywhere in the app to see how that skill or job contributes to the goal. */
export function SdgProvider({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState<Subject | null>(null);
  const close = useCallback(() => setOpen(null), []);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && close();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, close]);

  const t = open?.tag;
  const noun = open?.kind === "role" ? "job" : "skill";
  const origin =
    t?.origin === "ai" ? `Suggested by AI from the name of this ${noun}. Treat it as a starting point.`
      : t?.origin === "default" ? `A general link: Kompas has no specific link for this ${noun} yet.`
        : "From Kompas's SDG mapping.";

  return (
    <PopupCtx.Provider value={setOpen}>
      {children}
      {open && t &&
        createPortal(
          <div className="modal-backdrop sim-backdrop" onClick={close}>
            <div className="modal glass sdg-pop" role="dialog" aria-modal="true" aria-labelledby="sdg-title" onClick={(e) => e.stopPropagation()}>
              <button className="modal-close" onClick={close} aria-label="Close">×</button>
              <header className="sdg-pop-head" style={{ background: goalBg(t.sdg), color: ON_GOAL }}>
                <span className="sdg-pop-num" aria-hidden>{t.sdg}</span>
                <div>
                  <span className="sdg-pop-kicker">Sustainable Development Goal {t.sdg}</span>
                  <h2 id="sdg-title">{t.name || SDG_NAMES[t.sdg]}</h2>
                </div>
              </header>
              <div className="sdg-pop-body">
                <div>
                  <span className="label">How {open.subject} contributes</span>
                  {open.reasons ? (
                    <ul className="sdg-reasons">
                      {open.reasons.map((r) => (
                        <li key={r.subject}><strong>{r.subject}</strong> {r.rationale}</li>
                      ))}
                    </ul>
                  ) : (
                    <p>{t.rationale || `${open.subject} supports this goal.`}</p>
                  )}
                </div>
                {t.target && (
                  <p className="muted small">
                    UN target {t.target} ·{" "}
                    <a href={goalUrl(t.sdg)} target="_blank" rel="noopener noreferrer">Goal {t.sdg} on the UN site ↗</a>
                  </p>
                )}
                <p className="muted small">{origin}</p>
              </div>
            </div>
          </div>,
          document.body,
        )}
    </PopupCtx.Provider>
  );
}

function useTags(kind: "skill" | "role", id: string, given?: SdgTagData[]): SdgTagData[] | null {
  const [, refresh] = useState(0);
  const has = !!given?.length;
  useEffect(() => subscribeSdg(() => refresh((n) => n + 1)), []);
  useEffect(() => {
    if (!has) wantSdgTags(kind, id);
  }, [has, kind, id]);
  if (has) return given!;
  return readSdgTags(kind, id) ?? (sdgSettled(kind, id) ? [] : null);
}

/** The SDG tags of one skill or job, each in its goal's colour. They come with the page when Kompas has them mapped,
 * and are asked for otherwise. */
export function SdgTags({ kind, id, subject, tags }: { kind: "skill" | "role"; id: string; subject: string; tags?: SdgTagData[] }) {
  const found = useTags(kind, id, tags);
  const open = useContext(PopupCtx);
  if (found === null) return <span className="sdg-tags" aria-hidden><span className="sdg-tag sdg-loading" /></span>;
  return (
    <span className="sdg-tags">
      {found.map((t) => (
        <button key={t.sdg} type="button" className="sdg-tag" style={{ background: goalBg(t.sdg), color: ON_GOAL }}
          title={`SDG ${t.sdg}: ${t.name || SDG_NAMES[t.sdg]}. Click to see how ${subject} contributes.`} aria-haspopup="dialog"
          onClick={(e) => {
            e.stopPropagation();
            open({ subject, kind, tag: t });
          }}>
          SDG {t.sdg}
        </button>
      ))}
    </span>
  );
}

/** The SDG tags of a group of skills (a resume group like "Web Development"): the goals its skills contribute to, most
 * skills first. Clicking one lists how each skill contributes to that goal. */
export function SdgGroupTags({ skills, subject }: { skills: { id: string; label: string }[]; subject: string }) {
  const [, refresh] = useState(0);
  const open = useContext(PopupCtx);
  const key = skills.map((s) => s.id).join("|");
  useEffect(() => subscribeSdg(() => refresh((n) => n + 1)), []);
  useEffect(() => {
    skills.forEach((s) => wantSdgTags("skill", s.id));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  const byGoal = new Map<number, { tag: SdgTagData; reasons: { subject: string; rationale: string }[] }>();
  let waiting = false;
  for (const s of skills) {
    const tags = readSdgTags("skill", s.id);
    if (!tags) {
      waiting ||= !sdgSettled("skill", s.id);
      continue;
    }
    for (const t of tags) {
      const g = byGoal.get(t.sdg) ?? { tag: t, reasons: [] };
      g.reasons.push({ subject: s.label, rationale: t.rationale ?? "" });
      byGoal.set(t.sdg, g);
    }
  }
  const goals = [...byGoal.values()].sort((a, b) => b.reasons.length - a.reasons.length || a.tag.sdg - b.tag.sdg).slice(0, 4);
  if (!goals.length && !waiting) return null;
  return (
    <span className="sdg-tags">
      {goals.map(({ tag: t, reasons }) => (
        <button key={t.sdg} type="button" className="sdg-tag" style={{ background: goalBg(t.sdg), color: ON_GOAL }}
          title={`SDG ${t.sdg}: ${t.name || SDG_NAMES[t.sdg]}. Click to see how ${subject} contributes.`} aria-haspopup="dialog"
          onClick={(e) => {
            e.stopPropagation();
            open({ subject, kind: "skill", tag: t, reasons });
          }}>
          SDG {t.sdg}
        </button>
      ))}
      {waiting && <span className="sdg-tag sdg-loading" aria-hidden />}
    </span>
  );
}

/** One tag you already hold (a sample job's single goal and reason). */
export function SdgChip({ tag, kind, subject }: { tag: SdgTagData; kind: "skill" | "role"; subject: string }) {
  return <SdgTags kind={kind} id={`static-${tag.sdg}`} subject={subject} tags={[tag]} />;
}
