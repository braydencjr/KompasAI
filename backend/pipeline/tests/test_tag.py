from kompas.tag import Tagger


def ids(tagger, text):
    return set(tagger.tag_text(text))


def test_alias_maps_tool_names_to_concepts(cur):
    t = Tagger(cur)
    assert ids(t, "You'll pair with Claude Code and Cursor every day") == {"agentic-coding"}
    assert ids(t, "Reporting in Power BI, data in PostgreSQL") == {"power-bi", "sql"}


def test_case_sensitive_aliases_ignore_everyday_words(cur):
    t = Tagger(cur)
    assert "excel" not in ids(t, "Candidates who excel in fast-paced teams")
    assert "excel" in ids(t, "Advanced Excel and pivot tables")
    assert "react" not in ids(t, "able to react quickly")
    assert "rust" not in ids(t, "rust on the old pipes")


def test_longest_alias_wins(cur):
    hits = Tagger(cur).tag_text("Experience with agentic coding tools")
    assert "agentic-coding" in hits
    assert "llm-agents" not in hits  # "agentic" alone would map here


def test_hyphenated_suffix_still_matches(cur):
    assert "rag" in ids(Tagger(cur), "Build RAG-based search")
    assert "llm-applications" in ids(Tagger(cur), "LLM-powered features")


def test_topics_tag_repos(cur):
    doc = {"kind": "repo", "title": "mattpocock/skills", "text": "Skills for coding agents",
           "topics": ["claude-code", "agent-skills"], "metrics": {}}
    hits = Tagger(cur).tag_doc(doc)
    assert hits["agentic-coding"][0] == "topic"


def test_pre_assigned_docs_keep_their_concept(cur):
    doc = {"kind": "paper", "title": "x", "text": "uses Excel", "topics": [], "metrics": {"concept_id": "rag"}}
    assert set(Tagger(cur).tag_doc(doc)) == {"rag"}


def test_language_topics_count_for_trends_but_are_marked_weak(cur):
    doc = {"kind": "repo", "title": "someone/blender-addon", "text": "", "topics": ["python", "mcp"], "metrics": {}}
    hits = Tagger(cur).tag_doc(doc)
    assert hits["python"][0] == "topic_weak"   # built in Python, not about Python
    assert hits["mcp"][0] == "topic"
