"""Data limits (Signal app contract, section 9): none locally, hard caps only with SIGNAL_PUBLIC=1."""
import json

import pytest
from streamlit.testing.v1 import AppTest

from rivalsignal import limits
from rivalsignal.analysis import analyze_project, set_review
from rivalsignal.examples import demo_data, demo_project
from rivalsignal.exports import printable_html
from rivalsignal.prompts import build_research_prompt, repair_prompt
from rivalsignal.schema import SCHEMA, DataProblem, active_schema, import_research, parse_json, validate_data

RENDER = "from rivalsignal.ui import render\n\nrender()\n"


@pytest.fixture
def local(monkeypatch):
    monkeypatch.delenv("SIGNAL_PUBLIC", raising=False)


@pytest.fixture
def public(monkeypatch):
    monkeypatch.setenv("SIGNAL_PUBLIC", "1")


def big_case(competitors=15, criteria_per_dimension=13, claims_per_cell=2):
    """A case beyond every demo record cap: 15 rivals, 26 criteria, 390 assessments, 780 claims, 40 responses."""
    d = demo_data()
    base = d["criteria"]
    d["criteria"] = [dict(base[0] if dim == "market" else base[3], id=f"{dim[0].upper()}{i}", label=f"{dim} {i}")
                     for dim in ("market", "resource") for i in range(criteria_per_dimension)]
    d["competitors"] = [{"id": f"C{i}", "name": f"Rival {i}", "type": "direct", "description": "x" * 900}
                        for i in range(competitors)]
    d["sources"] = [dict(d["sources"][0], id=f"S{i}", title="t" * 400) for i in range(120)]
    d["claims"], d["assessments"], d["responses"] = [], [], []
    for comp in d["competitors"]:
        for crit in d["criteria"]:
            ids = []
            for j in range(claims_per_cell):
                cid = f"E_{comp['id']}_{crit['id']}_{j}"
                ids.append(cid)
                d["claims"].append({"id": cid, "competitor_id": comp["id"], "kind": "observation", "topic": "market",
                                    "statement": "s" * 1600, "observed_date": d["brief"]["as_of"],
                                    "source_ids": [f"S{k}" for k in range(25)]})
            d["assessments"].append({"competitor_id": comp["id"], "criterion_id": crit["id"], "judgment": "yes",
                                     "claim_ids": ids, "rationale": ""})
    first = d["competitors"][0]["id"]
    d["responses"] = [{"id": f"H{i}", "competitor_id": first, "response": f"Hypothesis {i}", "awareness": "",
                       "motivation": "", "capability": "", "supporting_claim_ids": [], "counter_claim_ids": [],
                       "watch_for": "", "our_contingency": "", "owner": "", "next_check": None} for i in range(40)]
    return d


def test_local_mode_has_no_caps(local):
    assert not limits.public()
    assert all(limits.cap(name) is None for name in limits.DEMO)
    assert all(limits.chars(name) is None for name in limits.TEXT)
    assert "maxItems" not in json.dumps(active_schema()) and "maxLength" not in json.dumps(active_schema())


def test_local_mode_accepts_input_beyond_every_demo_cap(local):
    d = big_case()
    for name in ("criteria", "competitors", "sources", "claims", "assessments", "responses"):
        assert len(d[name]) > limits.DEMO[name], name
    project = import_research(json.dumps(d))
    assert len(analyze_project(project)["cells"]) == 15 * 26
    # Reviews have no length cap either, and a JSON file above the demo byte cap parses.
    set_review(project, "claims", d["claims"][0]["id"], "accepted", "r" * 500, "n" * 5000, "2026-10-03")
    assert parse_json("{" + " " * ((limits.DEMO["json_mb"] + 1) * 1024 * 1024) + '"ok": true}') == {"ok": True}
    # Pasted source material and the repair prompt are passed through whole.
    long_text = "z" * (limits.DEMO["source_material_chars"] + 5000)
    assert json.dumps(long_text) in build_research_prompt(d["brief"], d["criteria"], d["competitors"], long_text)
    reply = "y" * (limits.DEMO["repair_chars"] + 5000)
    assert json.dumps(reply) in repair_prompt("error", reply)


def test_public_demo_enforces_record_byte_and_text_caps(public):
    assert active_schema() is SCHEMA
    with pytest.raises(DataProblem, match=r"criteria: at most 24 records are allowed; found 26. This is a limit of the public demo"):
        validate_data(big_case())
    d = demo_data()
    d["claims"][0]["statement"] = "s" * (limits.TEXT["statement"] + 1)
    with pytest.raises(DataProblem, match="public demo"):
        validate_data(d)
    with pytest.raises(DataProblem, match=r"smaller than 10 MB\. This is a limit of the public demo"):
        parse_json("{" + " " * (limits.DEMO["json_mb"] * 1024 * 1024) + "}")
    with pytest.raises(DataProblem, match="public demo"):
        set_review(demo_project(), "claims", "E1", "accepted", "r" * 121, "note", "2026-10-03")
    long_text = "z" * (limits.DEMO["source_material_chars"] + 5000)
    prompt = build_research_prompt(d["brief"], d["criteria"], d["competitors"], long_text)
    assert json.dumps(long_text) not in prompt and json.dumps(long_text[:25_000]) in prompt
    assert "public demo limits" in prompt


def test_public_demo_ui_caps_the_paste_box_and_says_why(public):
    app = AppTest.from_string(RENDER, default_timeout=120).run()
    app.sidebar.radio(key="rival:page").set_value("2 · Import & review").run()
    assert app.text_area(key="rival:ai_response").max_chars == limits.DEMO["paste_chars"]
    assert any("Public demo" in str(c.value) for c in app.caption)
    app.sidebar.radio(key="rival:page").set_value("Research & limits").run()
    assert any("downloaded app has none" in str(c.value) for c in app.caption)
    for page in app.sidebar.radio(key="rival:page").options:
        app.sidebar.radio(key="rival:page").set_value(page).run()
        assert not app.exception and not app.error, page


def test_local_ui_has_no_paste_cap_and_shortens_only_the_screen(local):
    app = AppTest.from_string(RENDER, default_timeout=120).run()
    app.session_state["rival:project"] = import_research(json.dumps(big_case(claims_per_cell=1)))
    app.sidebar.radio(key="rival:page").set_value("2 · Import & review").run()
    assert not app.exception
    assert not app.text_area(key="rival:ai_response").max_chars  # 0 = no limit in the widget protocol
    app.sidebar.radio(key="rival:page").set_value("3 · Rival map").run()
    assert not app.exception
    app.session_state["rival:project"] = import_research(json.dumps(big_case(competitors=30, claims_per_cell=1)))
    app.sidebar.radio(key="rival:page").set_value("4 · Response lab").run()
    assert any("first 25 of 40 hypotheses" in str(i.value) for i in app.info)
    app.sidebar.radio(key="rival:page").set_value("3 · Rival map").run()
    assert any("first 25 of 30 rivals" in str(i.value) for i in app.info)
    project = app.session_state["rival:project"]
    assert printable_html(project).count("Hypothesis ") >= 40  # exports keep everything


def test_memory_error_becomes_a_clear_message(local, monkeypatch):
    import rivalsignal.schema as schema

    def boom(*args, **kwargs):
        raise MemoryError

    monkeypatch.setattr(schema.json, "loads", boom)
    with pytest.raises(DataProblem, match="not enough memory"):
        parse_json('{"a": 1}')
