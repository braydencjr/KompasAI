// A tiny spreadsheet engine for the work simulator: literals, cell refs, + − * / ^, ranges and a few functions.

export type Fmt = "text" | "num" | "rm" | "pct" | "dec";
export type InputCell = { expect: number | string; tol?: number };
export type Cell = string | number | InputCell;
export type SheetSpec = { name: string; columns: { label: string; fmt: Fmt }[]; rows: Cell[][] };
export type Val = number | string | null;

export const isInput = (c: Cell): c is InputCell => typeof c === "object";

/** row index 0 is the first data row, which sits under the header in spreadsheet row 2 */
export const addr = (row: number, col: number) => String.fromCharCode(65 + col) + (row + 2);

export function parseLiteral(s: string): Val {
  const t = s.trim();
  if (!t) return null;
  const n = Number(t.replace(/^RM\s*/i, "").replace(/−/g, "-").replace(/[,%\s]/g, ""));
  if (/\d/.test(t) && !Number.isNaN(n)) return t.endsWith("%") ? n / 100 : n;
  return t;
}

class FormulaError extends Error {}

const FUNCS: Record<string, (args: number[]) => number> = {
  SUM: (a) => a.reduce((s, x) => s + x, 0),
  AVERAGE: (a) => (a.length ? a.reduce((s, x) => s + x, 0) / a.length : 0),
  MIN: (a) => Math.min(...a),
  MAX: (a) => Math.max(...a),
  ABS: (a) => Math.abs(a[0]),
  ROUND: (a) => {
    const f = 10 ** (a[1] ?? 0);
    return Math.round(a[0] * f) / f;
  },
};

function tokenize(src: string) {
  const re = /\s*(\d+(?:\.\d+)?%?|[A-Z]+\d+(?::[A-Z]+\d+)?|[A-Z]+|[-+*/^(),])/y;
  const out: string[] = [];
  let m: RegExpExecArray | null;
  while (re.lastIndex < src.length && (m = re.exec(src))) out.push(m[1]);
  if (re.lastIndex < src.trimEnd().length) throw new FormulaError("Unexpected character");
  return out;
}

function expandRange(range: string) {
  const [a, b] = range.split(":");
  const c1 = a.charCodeAt(0), c2 = b.charCodeAt(0);
  const r1 = +a.slice(1), r2 = +b.slice(1);
  const refs: string[] = [];
  for (let c = Math.min(c1, c2); c <= Math.max(c1, c2); c++)
    for (let r = Math.min(r1, r2); r <= Math.max(r1, r2); r++) refs.push(String.fromCharCode(c) + r);
  return refs;
}

function evalFormula(src: string, get: (ref: string) => Val): number {
  // $ only pins references when copying formulas, which this grid doesn't do
  const t = tokenize(src.toUpperCase().replace(/\$/g, ""));
  let i = 0;
  const num = (v: Val) => {
    if (v === null) return 0;
    if (typeof v === "string") throw new FormulaError("Text in a calculation");
    return v;
  };
  const expect = (tok: string) => {
    if (t[i++] !== tok) throw new FormulaError(`Expected ${tok}`);
  };

  function expr(): number {
    let v = term();
    while (t[i] === "+" || t[i] === "-") v = t[i++] === "+" ? v + term() : v - term();
    return v;
  }
  function term(): number {
    let v = power();
    while (t[i] === "*" || t[i] === "/") {
      const op = t[i++];
      const r = power();
      if (op === "/" && r === 0) throw new FormulaError("Divide by zero");
      v = op === "*" ? v * r : v / r;
    }
    return v;
  }
  function power(): number {
    const v = unary();
    return t[i] === "^" ? (i++, v ** power()) : v;
  }
  function unary(): number {
    if (t[i] === "-") return i++, -unary();
    if (t[i] === "+") return i++, unary();
    return atom();
  }
  function atom(): number {
    const tok = t[i++];
    if (tok === undefined) throw new FormulaError("Formula ends early");
    if (tok === "(") {
      const v = expr();
      expect(")");
      return v;
    }
    if (/^\d/.test(tok)) return tok.endsWith("%") ? parseFloat(tok) / 100 : parseFloat(tok);
    if (FUNCS[tok]) {
      expect("(");
      const args: number[] = [];
      while (t[i] !== ")") {
        if (t[i]?.includes(":")) args.push(...expandRange(t[i++]).map((r) => get(r)).filter((v) => v !== null).map(num));
        else args.push(expr());
        if (t[i] === ",") i++;
        else if (t[i] !== ")") throw new FormulaError("Expected , or )");
      }
      i++;
      return FUNCS[tok](args);
    }
    if (/^[A-Z]+\d+$/.test(tok)) return num(get(tok));
    throw new FormulaError(`Unknown name ${tok}`);
  }

  const v = expr();
  if (i < t.length) throw new FormulaError("Unexpected " + t[i]);
  return v;
}

export type Computed = Record<string, Val | { error: string }>;

/** Evaluates every input cell; fixed cells are read straight from the spec. */
export function evaluateSheet(spec: SheetSpec, inputs: Record<string, string>): Computed {
  const memo = new Map<string, Val>();
  const visiting = new Set<string>();

  function get(ref: string): Val {
    if (memo.has(ref)) return memo.get(ref)!;
    const col = ref.charCodeAt(0) - 65;
    const row = +ref.slice(1) - 2;
    if (row === -1) return spec.columns[col]?.label ?? null;
    const cell = spec.rows[row]?.[col];
    if (cell === undefined) throw new FormulaError(`${ref} is empty`);
    if (!isInput(cell)) return typeof cell === "number" ? cell : parseLiteral(cell);
    if (visiting.has(ref)) throw new FormulaError("Circular reference");
    visiting.add(ref);
    try {
      const raw = inputs[ref] ?? "";
      const v = raw.trim().startsWith("=") ? evalFormula(raw.trim().slice(1), get) : parseLiteral(raw);
      memo.set(ref, v);
      return v;
    } finally {
      visiting.delete(ref);
    }
  }

  const out: Computed = {};
  spec.rows.forEach((r, ri) =>
    r.forEach((c, ci) => {
      if (!isInput(c)) return;
      const a = addr(ri, ci);
      try {
        out[a] = get(a);
      } catch (e) {
        out[a] = { error: e instanceof FormulaError ? e.message : "Error" };
      }
    }),
  );
  return out;
}

export function isCorrect(cell: InputCell, v: Val | { error: string } | undefined) {
  if (v === null || v === undefined || typeof v === "object") return false;
  if (typeof cell.expect === "string") return String(v).trim().toLowerCase() === cell.expect.toLowerCase();
  if (typeof v !== "number") return false;
  return Math.abs(v - cell.expect) <= (cell.tol ?? Math.max(Math.abs(cell.expect) * 0.005, 0.005));
}

export function formatVal(v: Val, fmt: Fmt) {
  if (v === null) return "";
  if (typeof v === "string") return v;
  if (fmt === "pct") return `${+(v * 100).toFixed(1)}%`;
  if (fmt === "dec") return v.toFixed(2);
  return v.toLocaleString("en-MY", { maximumFractionDigits: 2 });
}
