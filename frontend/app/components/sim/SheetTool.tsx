"use client";

import { useMemo, useRef, useState } from "react";
import { addr, evaluateSheet, formatVal, isCorrect, isInput, parseLiteral, type Val } from "../../lib/sheet";
import type { SheetTask } from "../../data/simulations";

type Props = { task: SheetTask; onDone: (score: number, evidence: string[]) => void };

export default function SheetTool({ task, onDone }: Props) {
  const { sheet } = task;
  const [inputs, setInputs] = useState<Record<string, string>>({});
  const [focus, setFocus] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const cellRefs = useRef<Record<string, HTMLInputElement | null>>({});

  const computed = useMemo(() => evaluateSheet(sheet, inputs), [sheet, inputs]);

  // input cells in reading order, for Enter-to-move
  const order = useMemo(
    () => sheet.rows.flatMap((r, ri) => r.map((c, ci) => (isInput(c) ? addr(ri, ci) : null))).filter(Boolean) as string[],
    [sheet],
  );
  const filled = order.filter((a) => (inputs[a] ?? "").trim()).length;

  function moveDown(a: string) {
    const col = a[0];
    const row = +a.slice(1);
    const below = order.find((o) => o[0] === col && +o.slice(1) > row) ?? order[order.indexOf(a) + 1];
    if (below) cellRefs.current[below]?.focus();
  }

  function submit() {
    const cells = sheet.rows.flatMap((r, ri) => r.map((c, ci) => ({ c, a: addr(ri, ci) }))).filter((x) => isInput(x.c));
    const right = cells.filter(({ c, a }) => isInput(c) && isCorrect(c, computed[a])).length;
    const formulas = order.filter((a) => (inputs[a] ?? "").trim().startsWith("=")).length;
    setDone(true);
    onDone(right / cells.length, [
      `${right} of ${cells.length} cells correct`,
      `Used formulas in ${formulas} of ${cells.length} cells${formulas === cells.length ? " (model stays live)" : ""}`,
    ]);
  }

  const focusRaw = focus ? inputs[focus] ?? "" : "";

  return (
    <div className="tool tool-sheet">
      <div className="tool-bar">
        <span className="tool-file">▦ {sheet.name}</span>
        <span className="muted small">
          {filled}/{order.length} cells filled
        </span>
      </div>

      <div className="formula-bar">
        <span className="formula-addr">{focus ?? ""}</span>
        <span className="formula-fx">fx</span>
        <span className="formula-text">{focus ? focusRaw || " " : "Select a highlighted cell"}</span>
      </div>

      <div className="sheet-wrap">
        <table className="sheet">
          <thead>
            <tr>
              <th className="sheet-corner" />
              {sheet.columns.map((_, ci) => (
                <th key={ci} className="sheet-col">
                  {String.fromCharCode(65 + ci)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            <tr>
              <th className="sheet-row">1</th>
              {sheet.columns.map((c) => (
                <td key={c.label} className="sheet-head">
                  {c.label}
                </td>
              ))}
            </tr>
            {sheet.rows.map((r, ri) => (
              <tr key={ri}>
                <th className="sheet-row">{ri + 2}</th>
                {r.map((cell, ci) => {
                  const a = addr(ri, ci);
                  const fmt = sheet.columns[ci].fmt;
                  if (!isInput(cell)) {
                    const shown = typeof cell === "number" ? formatVal(cell, fmt) : cell;
                    return (
                      <td key={ci} className={ci > 0 && typeof parseLiteral(String(cell)) === "number" ? "num" : ""}>
                        {shown}
                      </td>
                    );
                  }
                  const v = computed[a];
                  const err = v && typeof v === "object" ? v.error : null;
                  const shown = focus === a ? inputs[a] ?? "" : err ? "#ERR" : formatVal(v as Val, fmt);
                  const state = done ? (isCorrect(cell, v) ? " right" : " wrong") : "";
                  return (
                    <td key={ci} className={`sheet-input${fmt === "text" ? " text" : ""}${state}`} title={err ?? (done && !isCorrect(cell, v) ? "Not quite" : undefined)}>
                      <input
                        ref={(el) => {
                          cellRefs.current[a] = el;
                        }}
                        value={shown}
                        readOnly={done}
                        aria-label={`Cell ${a}`}
                        onFocus={() => setFocus(a)}
                        onBlur={() => setFocus((f) => (f === a ? null : f))}
                        onChange={(e) => setInputs((p) => ({ ...p, [a]: e.target.value }))}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") {
                            e.preventDefault();
                            moveDown(a);
                          }
                        }}
                      />
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {!done && (
        <button className="btn btn-primary tool-submit" disabled={filled < order.length} onClick={submit}>
          {filled < order.length ? `Fill all ${order.length} cells to submit` : "Submit to " + task.from.split(" ")[0]}
        </button>
      )}
    </div>
  );
}
