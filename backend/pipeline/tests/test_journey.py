from kompas.journey import pick_suggestions


def role(isco, match, rising, safe, gaps=True):
    return {"isco": isco, "title": isco, "match": match, "gaps": [{"id": "x"}] if gaps else [],
            "scores": {"rising": rising, "safe": safe, "impact": None}}


ROLES = [
    role("a", 60, 70, 60), role("b", 55, 80, None), role("c", 50, 50, 50), role("d", 45, 40, 45),
    role("e", 30, None, 30), role("f", 20, None, None),
    role("current", 90, 99, 90), role("nothing-to-learn", 80, 90, 80, gaps=False),
]


def iscos(picks):
    return [p["isco"] for p in picks]


def test_columns_rank_by_their_own_score():
    s = pick_suggestions(ROLES, "current")
    assert iscos(s["rising"]) == ["b", "a", "c"]   # demand x match, best first
    assert iscos(s["safe"])[:2] == ["d", "e"]       # match among safe roles, after the fastest-growing ones


def test_current_job_and_finished_roles_are_never_suggested():
    s = pick_suggestions(ROLES, "current")
    shown = iscos(s["rising"]) + iscos(s["safe"])
    assert "current" not in shown and "nothing-to-learn" not in shown


def test_columns_do_not_repeat_a_job():
    s = pick_suggestions(ROLES, "current")
    assert not set(iscos(s["rising"])) & set(iscos(s["safe"]))


def test_short_column_is_filled_with_a_flagged_stretch():
    s = pick_suggestions(ROLES, "current")
    assert s["safe"][-1] == {"isco": "f", "stretch": True}
    assert all(not p["stretch"] for p in s["rising"])
