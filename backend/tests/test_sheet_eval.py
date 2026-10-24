from app.services.sheet_eval import evaluate_formula, parse_literal, solution_problems


def test_literals_match_the_frontend():
    assert parse_literal("1,200,000") == 1200000
    assert parse_literal("8%") == 0.08
    assert parse_literal("RM 45") == 45
    assert parse_literal("Yes") == "Yes"
    assert parse_literal("") is None


def test_formulas():
    cells = {"B2": 100.0, "B3": 0.08, "C2": 50.0}
    get = cells.get
    assert evaluate_formula("B2*(1+B3)", get) == 108.0
    assert evaluate_formula("SUM(B2:C2)", get) == 150.0
    assert evaluate_formula("ROUND(B2/3,2)", get) == 33.33
    assert evaluate_formula("$B$2-C2", get) == 50.0


def test_working_sheet_has_no_problems():
    rows = [[("Revenue", None), ("100", None), ("", "=B2*2")],
            [("Cost", None), ("40", None), ("", "=C2-B3")]]
    assert solution_problems(3, rows) == []


def test_broken_answers_are_reported():
    rows = [[("Revenue", None), ("0", None), ("", "=10/B2")],
            [("Cost", None), ("40", None), ("", "=Z9+1")],
            [("Loop", None), ("", None), ("", "=C4")]]
    found = " | ".join(solution_problems(3, rows))
    assert "C2" in found and "divide by zero" in found
    assert "C3" in found and "outside the sheet" in found
    assert "C4" in found and "circular" in found
