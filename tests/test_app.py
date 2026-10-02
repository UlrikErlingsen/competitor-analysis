from pathlib import Path
import json

import pytest
from streamlit.testing.v1 import AppTest

from rivalsignal.analysis import analyze_project
from rivalsignal.examples import demo_data

APP = Path(__file__).resolve().parents[1] / "app.py"


def page(app, index):
    app.sidebar.radio[0].set_value(app.sidebar.radio[0].options[index]).run()
    assert not app.exception
    return app


def labeled(items, label):
    return next(item for item in items if item.label == label)


@pytest.mark.parametrize("index", range(7))
def test_every_page_renders(index):
    app = AppTest.from_file(str(APP), default_timeout=30).run()
    page(app, index)
    assert not app.exception
    assert not app.error


def test_ai_import_review_and_coding_flow():
    app = AppTest.from_file(str(APP), default_timeout=30).run()
    page(app, 2)
    app.text_area(key="rival:ai_response").set_value(json.dumps(demo_data()))
    app.button(key="rival:validate_import").click().run()
    assert not app.exception and not app.error
    app.button(key="rival:load_draft").click().run()
    assert app.session_state["rival:project"]["reviews"] == {"claims": {}, "assessments": {}}
    # Both tabs are rendered; first set of widgets is the claim review.
    [s for s in app.selectbox if s.label == "Review decision"][0].set_value("accepted")
    [t for t in app.text_input if t.label == "Reviewed by"][0].set_value("Reviewer")
    [t for t in app.text_area if t.label == "What did you check?"][0].set_value("Checked source wording and date.")
    [b for b in app.button if b.label == "Save review"][0].click().run()
    assert app.session_state["rival:project"]["reviews"]["claims"]["E1"]["status"] == "accepted"
    assert len(analyze_project(app.session_state["rival:project"])["gaps"]) == 18
    [s for s in app.selectbox if s.label == "Review decision"][1].set_value("accepted")
    [t for t in app.text_input if t.label == "Reviewed by"][1].set_value("Reviewer")
    [t for t in app.text_area if t.label == "What did you check?"][1].set_value("Evidence meets M1 definition.")
    [b for b in app.button if b.label == "Save review"][1].click().run()
    assert not app.exception and not app.error
    assert len(analyze_project(app.session_state["rival:project"])["gaps"]) == 17
    labeled(app.selectbox, "Judgment").set_value("no")
    labeled(app.button, "Save correction and reset its review").click().run()
    assert "C1/M1" not in app.session_state["rival:project"]["reviews"]["assessments"]
    assert len(analyze_project(app.session_state["rival:project"])["gaps"]) == 18


def test_new_brief_rejects_ai_scope_drift_and_empty_case_renders():
    app = AppTest.from_file(str(APP), default_timeout=30).run()
    page(app, 1)
    labeled(app.text_input, "Your company or offering").set_value("My company")
    labeled(app.button, "Start case from this brief").click().run()
    assert not app.exception and not app.error
    assert app.session_state["rival:project"]["data"]["brief"]["focal_company"] == "My company"
    assert not app.session_state["rival:project"]["data"]["claims"]
    for index in [3, 4, 5, 0, 2]:
        page(app, index)
    app.text_area(key="rival:ai_response").set_value(json.dumps(demo_data()))
    app.button(key="rival:validate_import").click().run()
    assert "changed your saved brief" in app.error[0].value
    d = demo_data()
    d["brief"]["focal_company"] = "My company"
    app.text_area(key="rival:ai_response").set_value(json.dumps(d))
    app.button(key="rival:validate_import").click().run()
    assert not app.error
    app.button(key="rival:load_draft").click().run()
    assert not app.exception


def test_response_hypothesis_save_and_overlap_validation():
    app = AppTest.from_file(str(APP), default_timeout=30).run()
    page(app, 4)
    labeled(app.text_input, "Possible competitor response").set_value("Trial a longer contract")
    labeled(app.multiselect, "Supporting claim IDs").set_value(["MOVE1"])
    labeled(app.multiselect, "Counterevidence claim IDs").set_value(["MOVE1"])
    labeled(app.button, "Save hypothesis").click().run()
    assert "both support and counterevidence" in app.error[0].value
    labeled(app.multiselect, "Counterevidence claim IDs").set_value(["MOVE2"])
    labeled(app.button, "Save hypothesis").click().run()
    assert not app.exception and not app.error
    assert len(app.session_state["rival:project"]["data"]["responses"]) == 3


def test_invalid_ai_json_offers_repair_without_changing_project():
    app = AppTest.from_file(str(APP), default_timeout=30).run()
    page(app, 2)
    before = app.session_state["rival:project"]
    app.text_area(key="rival:ai_response").set_value("not JSON")
    app.button(key="rival:validate_import").click().run()
    assert app.error and not app.exception
    assert app.session_state["rival:project"] == before
    assert any("Repair the JSON" in c.value for c in app.code)


def test_sparse_import_can_add_unknown_assessments_for_manual_coding():
    app = AppTest.from_file(str(APP), default_timeout=30).run()
    page(app, 2)
    d = demo_data()
    d["assessments"] = []
    app.text_area(key="rival:ai_response").set_value(json.dumps(d))
    app.button(key="rival:validate_import").click().run()
    app.button(key="rival:load_draft").click().run()
    app.button(key="rival:add_missing_coding").click().run()
    assert not app.exception and not app.error
    p = app.session_state["rival:project"]
    assert len(p["data"]["assessments"]) == 18
    assert len(analyze_project(p)["gaps"]) == 18
