from fastapi.testclient import TestClient

from kompas import sdg
from kompas.api import create_app


def fake_model(monkeypatch, items):
    calls = []

    def generate(system, contents, schema, client, **_):
        calls.append(contents)
        return {"items": items}, None

    monkeypatch.setattr(sdg.llm, "_generate", generate)
    return calls


def good(sdg_no=9, target="9.5", why="Writing software is how new tools and services reach businesses and people."):
    return {"sdg": sdg_no, "target": target, "rationale": why}


def test_curated_tags_come_first_and_say_so(conn, cur, monkeypatch):
    calls = fake_model(monkeypatch, [])
    skill = next(e for (k, e) in cur.sdg_tags if k == "skill")
    out = sdg.resolve(conn, cur, [{"kind": "skill", "id": skill, "label": "x"}])
    assert out[f"skill:{skill}"] and all(t["origin"] == "curated" and t["rationale"] for t in out[f"skill:{skill}"])
    assert calls == []                                    # nothing to ask a model


def test_an_untagged_skill_gets_the_ais_tag_once_then_it_is_saved(conn, cur, monkeypatch):
    calls = fake_model(monkeypatch, [{"id": "S9.9", "kind": "skill", "tags": [good()]}])
    item = {"kind": "skill", "id": "S9.9", "label": "Use presentation software"}
    first = sdg.resolve(conn, cur, [item])["skill:S9.9"]
    assert first[0]["sdg"] == 9 and first[0]["origin"] == "ai" and first[0]["name"] == "Industry, innovation and infrastructure"
    again = sdg.resolve(conn, cur, [item])["skill:S9.9"]
    assert again == first and len(calls) == 1             # the second time reads what was saved


def test_answers_that_dont_hold_up_are_dropped_and_the_default_is_used(conn, cur, monkeypatch):
    fake_model(monkeypatch, [{"id": "S1", "kind": "skill", "tags": [
        good(sdg_no=99), good(target="3.4"), good(why="short"), good(target="nine"), {"sdg": True, "target": "1.1", "rationale": "x" * 40}]}])
    out = sdg.resolve(conn, cur, [{"kind": "skill", "id": "S1", "label": "Something"}])["skill:S1"]
    assert [(t["sdg"], t["target"], t["origin"]) for t in out] == [(4, "4.4", "default")]
    assert sdg.saved(conn, "skill", "S1") == []           # a default isn't kept, so the model is asked again next time


def test_at_most_two_goals_and_no_repeats(conn, cur, monkeypatch):
    fake_model(monkeypatch, [{"id": "S2", "kind": "skill", "tags": [good(9, "9.1"), good(9, "9.5"), good(4, "4.4"), good(8, "8.2")]}])
    out = sdg.resolve(conn, cur, [{"kind": "skill", "id": "S2", "label": "x"}])["skill:S2"]
    assert [t["sdg"] for t in out] == [9, 4]


def test_the_model_is_called_without_thinking(conn, cur, monkeypatch):
    seen = {}

    def generate(system, contents, schema, client, **kw):
        seen.update(kw)
        return {"items": []}, None

    monkeypatch.setattr(sdg.llm, "_generate", generate)
    sdg.resolve(conn, cur, [{"kind": "skill", "id": "S5", "label": "x"}])
    assert seen == {"thinking": 0}


def test_the_model_can_only_tag_what_was_asked(conn, cur, monkeypatch):
    fake_model(monkeypatch, [{"id": "other", "kind": "skill", "tags": [good()]}])
    out = sdg.resolve(conn, cur, [{"kind": "role", "id": "R1", "label": "A job"}])
    assert out["role:R1"][0]["origin"] == "default" and out["role:R1"][0]["sdg"] == 8
    assert sdg.saved(conn, "skill", "other") == []


def test_no_model_means_every_item_still_has_a_tag(conn, cur, monkeypatch):
    monkeypatch.setattr(sdg.llm, "_generate", lambda *a, **k: (None, "no Gemini API key configured"))
    out = sdg.resolve(conn, cur, [{"kind": "skill", "id": "S3", "label": "x"}, {"kind": "role", "id": "R3", "label": "y"}])
    assert out["skill:S3"][0]["sdg"] == 4 and out["role:R3"][0]["sdg"] == 8


def test_every_catalogue_role_and_skill_has_a_curated_tag(cur):
    roles = set(cur.role_titles)
    skills = {c for c, concept in cur.concepts.items() if concept.kind == "skill" and concept.origin not in ("esco", "name")}
    tagged = {(k, e) for (k, e) in cur.sdg_tags}
    assert [r for r in roles if ("role", r) not in tagged] == []
    assert [s for s in skills if ("skill", s) not in tagged] == []


def test_the_endpoint_names_things_itself_and_skips_unknown_ids(conn, cur, monkeypatch):
    monkeypatch.setattr(sdg.llm, "_generate", lambda *a, **k: (None, "no key"))
    client = TestClient(create_app(live_mode=False, replay=False))
    role = next(iter(cur.role_titles))
    r = client.post("/sdg/tags", json={"items": [{"kind": "role", "id": role}, {"kind": "role", "id": "no-such-job"},
                                                {"kind": "skill", "id": "not a skill"}]})
    assert r.status_code == 200
    assert list(r.json()["tags"]) == [f"role:{role}"] and r.json()["tags"][f"role:{role}"][0]["origin"] == "curated"
    assert client.post("/sdg/tags", json={"items": [{"kind": "role", "id": "x"}] * 41}).status_code == 422
