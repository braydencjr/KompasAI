"""Plain-language messages for the personal feed. Fixed templates keyed on the user's relation to a
skill and the skill's ladder status, so every sentence is traceable to a computed result (PRD FR-10.4)."""

RELATION_LABEL = {
    "exposed": "Affects your work",
    "route": "On your learning route",
    "have": "A skill you have",
    "related": "Related to your skills",
}

# what the hiring data says, by ladder status
MEANING = {
    "Act now": "Malaysian employers are hiring for this now.",
    "Emerging": "Companies abroad are hiring for this. Malaysian demand hasn't caught up yet.",
    "Watch": "Talk about it is rising fast, but hiring hasn't clearly picked up yet.",
    "Stable": "Hiring for it is holding steady, whatever the buzz is doing.",
    "Declining": "Hiring for this is falling.",
    "Stalled": "It's been hyped for months without turning into jobs.",
}

HOT, QUIET, DOWN = ("Act now", "Emerging"), ("Watch", "Stable"), ("Declining", "Stalled")

# what to do about it, by relation and status group
ACTION = {
    ("exposed", HOT): "Tools like this are starting to change jobs like yours. Lean into the parts of your work that need judgement.",
    ("exposed", QUIET): "It isn't changing jobs yet. Worth knowing what these tools can do.",
    ("exposed", DOWN): "Less pressure on your tasks from this for now.",
    ("route", HOT): "Good time to move this step up your route.",
    ("route", QUIET): "Keep it on your route. No need to rush it.",
    ("route", DOWN): "Consider doing your other steps first.",
    ("have", HOT): "Your skill is gaining value. Make it visible on your resume.",
    ("have", QUIET): "Nothing to change. Here's what's new in it.",
    ("have", DOWN): "Pair it with a rising skill to keep your options open.",
    ("related", HOT): "A neighbour of your skills is in demand. It could be an easy step.",
    ("related", QUIET): "Background reading, no action needed.",
    ("related", DOWN): "Background reading, no action needed.",
}


def _group(status: str):
    return next(g for g in (HOT, QUIET, DOWN) if status in g)


def headline(relation: str, label: str) -> str:
    if relation == "exposed":
        return f"AI is getting better at {label[0].lower() + label[1:]}"
    if relation == "have":
        return f"What's new in {label}"
    return f"{label} is getting attention"


def explain(relation: str, label: str, status: str, family_label: str | None, family_status: str | None) -> dict:
    meaning = MEANING.get(status, MEANING["Stable"])
    if family_label and family_status == "Act now" and status != "Act now":
        meaning += f" {family_label} roles are in demand in Malaysia, and this skill is part of them."
    return {
        "relation": relation,
        "relation_label": RELATION_LABEL[relation],
        "headline": headline(relation, label),
        "meaning": meaning,
        "action": ACTION[(relation, _group(status if status in MEANING else "Stable"))],
    }


def summary(signals: list[dict]) -> str:
    """One line for the top of the feed."""
    if not signals:
        return "Quiet week: nothing trending touches your skills or route."
    hot = [s for s in signals if s["status"] in HOT]
    exposed = [s for s in signals if s["relation"] == "exposed"]
    if any(s["status"] == "Act now" for s in hot):
        names = ", ".join(s["label"] for s in hot if s["status"] == "Act now")
        return f"Worth acting on: Malaysian employers are hiring for {names}."
    if hot:
        return f"{len(hot)} of {len(signals)} trending skills have hiring behind them abroad. None in Malaysia yet."
    verb = "involves" if len(exposed) == 1 else "involve"
    tail = f" {len(exposed)} of them {verb} AI that reaches your tasks." if exposed else ""
    return (f"Nothing urgent: {len(signals)} skills you care about are getting attention, "
            f"but none has hiring behind it yet.{tail}")
