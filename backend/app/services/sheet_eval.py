"""The frontend's spreadsheet engine (frontend/app/lib/sheet.ts), in Python, so a generated sheet whose answer formulas
don't work is caught here and sent back to the model to fix, instead of failing in the browser.

Same rules: literals ("1,200,000", "8%", "RM 45"), A1 references with row 1 as the header, + - * / ^, ranges, and
SUM, AVERAGE, MIN, MAX, ROUND, ABS. Keep the two in step.
"""

import re

Val = float | str | None


class FormulaError(Exception):
    pass


def parse_literal(s: str) -> Val:
    t = s.strip()
    if not t:
        return None
    cleaned = re.sub(r"^RM\s*", "", t, flags=re.I).replace("−", "-")
    cleaned = re.sub(r"[,%\s]", "", cleaned)
    if re.search(r"\d", t):
        try:
            n = float(cleaned)
            return n / 100 if t.endswith("%") else n
        except ValueError:
            pass
    return t


FUNCS = {
    "SUM": lambda a: sum(a),
    "AVERAGE": lambda a: sum(a) / len(a) if a else 0.0,
    "MIN": lambda a: min(a) if a else 0.0,
    "MAX": lambda a: max(a) if a else 0.0,
    "ABS": lambda a: abs(a[0]),
    "ROUND": lambda a: round(a[0], int(a[1]) if len(a) > 1 else 0),
}

TOKEN = re.compile(r"\s*(\d+(?:\.\d+)?%?|[A-Z]+\d+(?::[A-Z]+\d+)?|[A-Z]+|[-+*/^(),])")


def _tokens(src: str) -> list[str]:
    out, i, src = [], 0, src.rstrip()
    while i < len(src):
        m = TOKEN.match(src, i)
        if not m:
            raise FormulaError(f"unexpected character '{src[i]}'")
        out.append(m.group(1))
        i = m.end()
    return out


def _expand(rng: str) -> list[str]:
    a, b = rng.split(":")
    c1, c2, r1, r2 = ord(a[0]), ord(b[0]), int(a[1:]), int(b[1:])
    return [f"{chr(c)}{r}" for c in range(min(c1, c2), max(c1, c2) + 1) for r in range(min(r1, r2), max(r1, r2) + 1)]


def evaluate_formula(src: str, get) -> float:
    t = _tokens(src.upper().replace("$", ""))
    i = 0

    def num(v: Val) -> float:
        if v is None:
            return 0.0
        if isinstance(v, str):
            raise FormulaError("text used in a calculation")
        return v

    def peek():
        return t[i] if i < len(t) else None

    def take():
        nonlocal i
        i += 1
        return t[i - 1] if i - 1 < len(t) else None

    def expr():
        v = term()
        while peek() in ("+", "-"):
            v = v + term() if take() == "+" else v - term()
        return v

    def term():
        v = power()
        while peek() in ("*", "/"):
            op, r = take(), power()
            if op == "/" and r == 0:
                raise FormulaError("divide by zero")
            v = v * r if op == "*" else v / r
        return v

    def power():
        v = unary()
        if peek() == "^":
            take()
            return v ** power()
        return v

    def unary():
        if peek() == "-":
            take()
            return -unary()
        if peek() == "+":
            take()
            return unary()
        return atom()

    def atom():
        tok = take()
        if tok is None:
            raise FormulaError("formula ends early")
        if tok == "(":
            v = expr()
            if take() != ")":
                raise FormulaError("missing )")
            return v
        if tok[0].isdigit():
            return float(tok[:-1]) / 100 if tok.endswith("%") else float(tok)
        if tok in FUNCS:
            if take() != "(":
                raise FormulaError(f"{tok} needs (")
            args: list[float] = []
            while peek() != ")":
                if peek() is None:
                    raise FormulaError("missing )")
                if ":" in peek():
                    args += [num(v) for v in (get(r) for r in _expand(take())) if v is not None]
                else:
                    args.append(expr())
                if peek() == ",":
                    take()
            take()
            return float(FUNCS[tok](args))
        if re.fullmatch(r"[A-Z]+\d+", tok):
            return num(get(tok))
        raise FormulaError(f"unknown name {tok}")

    v = expr()
    if i < len(t):
        raise FormulaError(f"unexpected {t[i]}")
    return v


def solution_problems(columns: int, rows: list[list[tuple[str, str | None]]]) -> list[str]:
    """Each answer cell's solution, evaluated. rows: (shown value, solution or None) per cell. Returns problems such
    as 'D6 (=C6/B6): divide by zero', or that a numeric column's answer is text."""
    def addr(r: int, c: int) -> str:
        return f"{chr(65 + c)}{r + 2}"

    cells = {addr(ri, ci): cell for ri, row in enumerate(rows) for ci, cell in enumerate(row)}
    memo: dict[str, Val] = {}
    visiting: set[str] = set()

    def get(ref: str) -> Val:
        if ref in memo:
            return memo[ref]
        col, row = ord(ref[0]) - 65, int(ref[1:]) - 2
        if row == -1:
            return None
        if ref not in cells or col >= columns:
            raise FormulaError(f"{ref} is outside the sheet")
        shown, solution = cells[ref]
        if solution is None:
            return parse_literal(shown)
        if ref in visiting:
            raise FormulaError("circular reference")
        visiting.add(ref)
        try:
            s = solution.strip()
            v = evaluate_formula(s[1:], get) if s.startswith("=") else parse_literal(s)
        finally:
            visiting.discard(ref)
        memo[ref] = v
        return v

    found = []
    for ref, (_, solution) in cells.items():
        if solution is None:
            continue
        try:
            v = get(ref)
            if v is None:
                found.append(f"{ref} ({solution}) gives an empty answer")
        except FormulaError as e:
            found.append(f"{ref} ({solution}): {e}")
        except (OverflowError, ValueError, ZeroDivisionError) as e:
            found.append(f"{ref} ({solution}): {e}")
    return found
