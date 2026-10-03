from copy import deepcopy
from datetime import date, timedelta
from io import BytesIO
import json
from zipfile import ZipFile

import pandas as pd
import pytest

from rivalsignal.analysis import analyze_project, assessment_readiness, claim_readiness, compare_projects, response_audit, set_review
from rivalsignal.examples import demo_data, demo_project
from rivalsignal.exports import csv_bytes, evidence_pack, printable_html, project_bytes
from rivalsignal.prompts import build_research_prompt, research_skeleton
from rivalsignal.schema import DataProblem, import_research, new_project, parse_json, restore_project, safe_url, validate_data


def accept(project, kind, key):
    return set_review(project, kind, key, "accepted", "Test reviewer", "Source and coding checked for this fixture.", "2026-10-03")


def test_import_is_a_draft_and_keeps_every_cell_unknown():
    p = import_research(json.dumps(demo_data()))
    assert p["reviews"] == {"claims": {}, "assessments": {}}
    a = analyze_project(p)
    assert len(a["gaps"]) == 18
    assert (a["profiles"].market_low == 0).all()
    assert (a["profiles"].resource_high == 100).all()


def test_review_both_observation_and_coding_before_resolving():
    p = new_project(demo_data())
    row = p["data"]["assessments"][0]
    p = accept(p, "claims", row["claim_ids"][0])
    assert assessment_readiness(p, row)[0] == "unknown"
    p = accept(p, "assessments", "C1/M1")
    assert assessment_readiness(p, row)[0] == "yes"
    p = set_review(p, "claims", row["claim_ids"][0], "rejected", "Reviewer", "Source does not support it.", "2026-10-03")
    assert assessment_readiness(p, row)[0] == "unknown"


def test_known_weighted_bounds_with_inference_staleness_and_explicit_no():
    a = analyze_project(demo_project())["profiles"].set_index("competitor_id")
    assert list(a.loc["C1", ["market_low", "market_high", "resource_low", "resource_high"]]) == [80, 100, 75, 100]
    assert list(a.loc["C2", ["market_low", "market_high", "resource_low", "resource_high"]]) == [70, 70, 65, 65]
    assert list(a.loc["C3", ["market_low", "market_high", "resource_low", "resource_high"]]) == [0, 50, 35, 60]


def test_weights_are_normalized_per_dimension_and_scale_invariant():
    p = demo_project()
    original = analyze_project(p)["profiles"]
    for criterion in p["data"]["criteria"]:
        if criterion["dimension"] == "market":
            criterion["weight"] *= 3
    pd.testing.assert_frame_equal(original, analyze_project(p)["profiles"])


def test_accessing_old_source_does_not_refresh_evidence():
    p = demo_project()
    claim = next(c for c in p["data"]["claims"] if c["source_ids"] == ["S4"])
    assert p["data"]["sources"][-1]["accessed_date"] == p["data"]["brief"]["as_of"]
    assert claim_readiness(p, claim) == (False, "Evidence needs refreshing")
    p["policy"]["max_age_days"] = 240
    assert claim_readiness(p, claim)[0]
    p["policy"]["max_age_days"] = 239
    assert not claim_readiness(p, claim)[0]


@pytest.mark.parametrize("field,value,reason", [("observed_date", None, "date unknown"), ("kind", "inference", "Inference")])
def test_accepted_but_unusable_claim_stays_unknown(field, value, reason):
    p = demo_project()
    claim = p["data"]["claims"][0]
    claim[field] = value
    assert reason in claim_readiness(p, claim)[1]
    assert assessment_readiness(p, p["data"]["assessments"][0])[0] == "unknown"


def test_all_linked_observations_must_be_eligible():
    p = demo_project()
    row = p["data"]["assessments"][0]
    stale = next(c for c in p["data"]["claims"] if c["source_ids"] == ["S4"])
    row["claim_ids"].append(stale["id"])
    assert assessment_readiness(p, row)[0] == "unknown"


def test_missing_assessments_are_unknown_not_zero():
    p = demo_project()
    p["data"]["assessments"] = []
    result = analyze_project(p)
    assert len(result["gaps"]) == 18
    assert (result["profiles"].market_high == 100).all()


def test_acceptance_requires_a_human_note_and_name():
    p = new_project(demo_data())
    with pytest.raises(DataProblem, match="name"):
        set_review(p, "claims", "E1", "accepted", "", "", "2026-10-03")
    with pytest.raises(DataProblem, match="no longer"):
        accept(p, "claims", "missing")


@pytest.mark.parametrize("payload", ['{"a":1,"a":2}', '{"weight":NaN}', '{"weight":Infinity}', '[]', 'Here is the JSON: {}'])
def test_rejects_ambiguous_or_non_json_responses(payload):
    with pytest.raises(DataProblem):
        parse_json(payload)


def test_json_size_limit_matches_the_50_mb_upload_cap():
    padded = "{" + " " * (6 * 1024 * 1024) + '"ok": true}'  # above the old 5 MB limit
    assert parse_json(padded) == {"ok": True}
    with pytest.raises(DataProblem, match="50 MB"):
        parse_json("{" + " " * (50 * 1024 * 1024) + "}")


def test_oversized_collections_fail_fast_with_a_clear_message():
    d = demo_data()
    d["sources"] = [dict(d["sources"][0], id=f"S{i}") for i in range(101)]
    with pytest.raises(DataProblem, match="sources: at most 100 records"):
        validate_data(d)


def test_fenced_and_bom_json_supported():
    assert parse_json(b'\xef\xbb\xbf```json\n{"ok":true}\n```') == {"ok": True}


@pytest.mark.parametrize("weight", [0, -1, True, float("nan"), float("inf")])
def test_weights_must_be_finite_positive_numbers(weight):
    d = demo_data()
    d["criteria"][0]["weight"] = weight
    with pytest.raises(DataProblem):
        validate_data(d)


@pytest.mark.parametrize("url", ["javascript:alert(1)", "file:///secret", "https://user:pass@example.org", "http://localhost:8519", "http://192.168.1.2", "https://example.org\\@localhost", "https://example.org/a b"])
def test_only_safe_public_source_links(url):
    assert not safe_url(url)
    assert safe_url("https://example.org/report?a=1&b=2")


def test_no_review_flags_in_ai_research_contract():
    d = demo_data()
    d["claims"][0]["verified"] = True
    with pytest.raises(DataProblem, match="Additional properties"):
        import_research(json.dumps(d))
    with pytest.raises(DataProblem):
        import_research(project_bytes(demo_project()))


@pytest.mark.parametrize("mutation", [
    lambda d: d["claims"][0].update(source_ids=["DOES_NOT_EXIST"]),
    lambda d: d["claims"][0].update(source_ids=[]),
    lambda d: d["claims"][0].update(competitor_id="C9"),
    lambda d: d["claims"][0].update(observed_date="2030-01-01"),
    lambda d: d["sources"][0].update(published_date="2030-01-01"),
    lambda d: d["sources"][0].update(accessed_date="2030-01-01"),
    lambda d: d["competitors"][0].update(name="  "),
    lambda d: d["criteria"][0].update(dimension="madeup"),
    lambda d: d["assessments"].append(deepcopy(d["assessments"][0])),
    lambda d: d["sources"].append(deepcopy(d["sources"][0])),
    lambda d: d["assessments"][0].update(claim_ids=["E6"]),
    lambda d: d["responses"][0].update(counter_claim_ids=["MOVE1"]),
])
def test_inconsistent_research_rejected(mutation):
    d = demo_data()
    mutation(d)
    with pytest.raises(DataProblem):
        validate_data(d)


def test_saved_project_roundtrip_preserves_reviews_but_reimport_does_not():
    p = demo_project()
    assert restore_project(project_bytes(p)) == p
    assert import_research(json.dumps(p["data"]))["reviews"]["claims"] == {}
    p["reviews"]["claims"]["E1"]["note"] = ""
    with pytest.raises(DataProblem, match="Accepted reviews"):
        restore_project(project_bytes(p))


def test_response_reasoning_keeps_counterevidence_and_due_dates():
    p = demo_project()
    r = p["data"]["responses"][0]
    r["next_check"] = p["data"]["brief"]["as_of"]
    audit = response_audit(p, r)
    assert audit["reviewed_support"] == ["MOVE1"]
    assert audit["reviewed_counterevidence"] == ["MOVE2"]
    assert audit["check_due"]
    r["owner"] = ""
    assert "owner" in response_audit(p, r)["missing"]


def test_snapshot_aging_can_change_profiles_without_changed_claims():
    old = demo_project()
    new = deepcopy(old)
    new["data"]["brief"]["as_of"] = (date.fromisoformat(old["data"]["brief"]["as_of"]) + timedelta(days=200)).isoformat()
    diff = compare_projects(old, new)
    assert diff["comparable"]
    assert list(diff["changes"].section) == ["brief"]
    assert diff["deltas"].market_low_change.min() < 0


@pytest.mark.parametrize("changed", ["weights", "scope", "policy", "competitor_identity"])
def test_snapshot_deltas_withheld_for_incomparable_basis(changed):
    p, q = demo_project(), demo_project()
    if changed == "weights":
        q["data"]["criteria"][0]["weight"] += 1
    elif changed == "scope":
        q["data"]["brief"]["market"] = "A different country"
    elif changed == "policy":
        q["policy"]["max_age_days"] = 90
    else:
        q["data"]["competitors"][0]["name"] = "Another business"
    diff = compare_projects(p, q)
    assert not diff["comparable"]
    assert diff["deltas"].empty


def test_snapshot_review_changes_reported():
    p = new_project(demo_data())
    q = accept(p, "claims", "E1")
    diff = compare_projects(p, q)
    assert diff["changes"].to_dict("records") == [{"section": "claims reviews", "record": "E1", "change": "changed"}]


def test_export_escapes_active_content_and_is_self_contained():
    p = demo_project()
    attack = '<script>alert("x")</script><img src="https://example.org/x">'
    p["data"]["brief"]["focal_company"] = attack
    p["data"]["claims"][0]["statement"] = attack
    html = printable_html(p)
    assert "<script" not in html and "<img" not in html
    assert "&lt;script&gt;" in html
    assert "@media print" in html and "project SHA-256" in html
    assert "Market" in html


def test_evidence_pack_reproducible_inputs_and_safe_csv():
    p = demo_project()
    with ZipFile(BytesIO(evidence_pack(p))) as z:
        assert set(z.namelist()) == {"project.json", "research-draft.json", "brief.html", "profiles.csv", "cells.csv", "claims.csv", "gaps.csv", "method.json"}
        assert restore_project(z.read("project.json")) == p
        assert len(json.loads(z.read("method.json"))["references"]) == 5
    csv = csv_bytes(pd.DataFrame({"text": ["=1+2", " @SUM(A1)", "normal"], "numeric": [-2, 0, 1]})).decode("utf-8-sig")
    assert "'=1+2" in csv and "' @SUM" in csv and "normal,1" in csv


def test_prompt_has_exact_user_scope_and_unknown_skeleton():
    d = demo_data()
    d["brief"]["focal_company"] = "Our company"
    skeleton = research_skeleton(d["brief"], d["criteria"], d["competitors"])
    assert all(a["judgment"] == "unknown" and not a["claim_ids"] for a in skeleton["assessments"])
    prompt = build_research_prompt(d["brief"], d["criteria"], d["competitors"], "https://example.org/research")
    assert "Our company" in prompt and "https://example.org/research" in prompt
    assert "UNREVIEWED" in prompt and "Lack of online evidence NEVER means no" in prompt
