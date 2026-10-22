"use client";

import { useEffect, useRef, useState } from "react";
import { checkDoc, wordCount, type DocTask } from "../../data/simulations";

type Props = { task: DocTask; onDone: (score: number, evidence: string[]) => void };

export default function DocTool({ task, onDone }: Props) {
  const [text, setText] = useState(task.template);
  const [done, setDone] = useState(false);
  const editorRef = useRef<HTMLTextAreaElement>(null);

  // start typing after the greeting, like opening a fresh draft
  useEffect(() => {
    const el = editorRef.current;
    if (!el) return;
    el.focus({ preventScroll: true });
    el.setSelectionRange(el.value.length, el.value.length);
  }, []);

  const [min, max] = task.words;
  const words = wordCount(text) - wordCount(task.template);
  const inRange = words >= min && words <= max;

  function submit() {
    const hits = checkDoc(task, text);
    const covered = hits.filter(Boolean).length;
    // going far outside the brief's length is a real miss, but a smaller one than missing content
    const score = (covered / hits.length) * (inRange ? 1 : 0.85);
    setDone(true);
    onDone(score, [
      `Covered ${covered} of ${hits.length} things the brief asked for`,
      `${words} words${inRange ? " (within the brief)" : ` (brief asked for ${min}–${max})`}`,
    ]);
  }

  const hits = done ? checkDoc(task, text) : null;

  return (
    <div className="tool tool-doc">
      <div className="tool-bar">
        <span className="tool-file">≡ {task.docName}</span>
        <span className={`muted small${words > max ? " over" : ""}`}>
          {Math.max(words, 0)} words · aim for {min}–{max}
        </span>
      </div>

      <div className="doc-page">
        <h4 className="doc-title">{task.docName}</h4>
        <textarea
          ref={editorRef}
          className="doc-editor"
          value={text}
          readOnly={done}
          rows={12}
          aria-label="Document"
          onChange={(e) => setText(e.target.value)}
        />
      </div>

      {hits && (
        <ul className="sim-checklist">
          {task.checklist.map((c, i) => (
            <li key={c.label} className={hits[i] ? "hit" : "miss"}>
              <span aria-hidden>{hits[i] ? "✓" : "–"}</span>
              {c.label}
            </li>
          ))}
        </ul>
      )}

      {!done && (
        <button className="btn btn-primary tool-submit" disabled={words < 15} onClick={submit}>
          {words < 15 ? "Write a little more to send" : "Send to " + task.from.split(" ")[0]}
        </button>
      )}
    </div>
  );
}
