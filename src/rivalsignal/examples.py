"""A complete fictional case with reviewed, missing, inferred and stale evidence."""
from datetime import date, timedelta

from rivalsignal.analysis import set_review
from rivalsignal.prompts import research_skeleton
from rivalsignal.schema import new_project


def demo_data(as_of: str = "2026-10-03") -> dict:
    now = date.fromisoformat(as_of)
    recent = (now - timedelta(days=14)).isoformat()
    old = (now - timedelta(days=240)).isoformat()
    brief = {"focal_company": "FjordDesk (fictional)",
             "market": "Job scheduling for service-trade businesses in Norway, with 5–100 field workers.",
             "decision": "Introduce a fixed-price dispatch package for multi-crew Norwegian service businesses.",
             "as_of": as_of, "horizon_days": 90}
    criteria = [
        {"id": "M1", "dimension": "market", "label": "Small service crews", "definition": "Serves Norwegian service-trade firms with 5–20 field workers, a current focal market.", "weight": 50},
        {"id": "M2", "dimension": "market", "label": "Multi-branch operators", "definition": "Serves Norwegian service firms with 21–100 field workers across branches, a current focal market.", "weight": 30},
        {"id": "M3", "dimension": "market", "label": "Recurring maintenance", "definition": "Serves firms scheduling recurring maintenance visits, a current focal use case.", "weight": 20},
        {"id": "R1", "dimension": "resource", "label": "Field-work capability", "definition": "Functionally comparable offline field-work and job-history capability to FjordDesk.", "weight": 40},
        {"id": "R2", "dimension": "resource", "label": "Local implementation", "definition": "Comparable access to Norwegian implementation and onboarding support.", "weight": 35},
        {"id": "R3", "dimension": "resource", "label": "Accounting connections", "definition": "Comparable integration relationships with local accounting platforms.", "weight": 25},
    ]
    competitors = [
        {"id": "C1", "name": "RoutePilot", "type": "direct", "description": "Fictional specialist field-service supplier."},
        {"id": "C2", "name": "SuiteWorks", "type": "indirect", "description": "Fictional broad business suite with scheduling."},
        {"id": "C3", "name": "Spreadsheet + phone", "type": "substitute", "description": "Fictional composite manual workflow, not a particular company."},
    ]
    data = research_skeleton(brief, criteria, competitors)
    for i, competitor in enumerate(competitors, start=1):
        data["sources"].append({"id": f"S{i}", "title": f"Fictional {competitor['name']} evidence packet",
                               "url": f"https://rival-demo.example/{competitor['id']}/evidence", "publisher": "Fictional demonstration",
                               "published_date": recent, "accessed_date": as_of, "origin_group": f"fictional-origin-{i}"})
    data["sources"].append({"id": "S4", "title": "Fictional older integration announcement",
                           "url": "https://rival-demo.example/C1/old-integrations", "publisher": "Fictional demonstration",
                           "published_date": old, "accessed_date": as_of, "origin_group": "fictional-origin-1"})
    values = {"C1": ["yes", "yes", "unknown", "yes", "yes", "yes"],
              "C2": ["yes", "no", "yes", "yes", "no", "yes"],
              "C3": ["yes", "no", "no", "no", "yes", "unknown"]}
    counter = 0
    for row in data["assessments"]:
        index = next(i for i, c in enumerate(criteria) if c["id"] == row["criterion_id"])
        value = values[row["competitor_id"]][index]
        row["judgment"] = value
        if value == "unknown":
            row["rationale"] = "The fictional packet leaves this question unresolved."
            continue
        counter += 1
        claim_id = f"E{counter}"
        row["claim_ids"] = [claim_id]
        row["rationale"] = "Illustrative coding from invented evidence; never a claim about an actual business."
        inferred = row["competitor_id"] == "C3" and row["criterion_id"] == "M1"
        stale = row["competitor_id"] == "C1" and row["criterion_id"] == "R3"
        source_id = "S4" if stale else "S" + row["competitor_id"][1:]
        data["claims"].append({"id": claim_id, "competitor_id": row["competitor_id"],
                               "kind": "inference" if inferred else "observation", "topic": criteria[index]["dimension"],
                               "statement": f"Fictional evidence {'suggests' if inferred else 'explicitly describes'} "
                                            f"{'a match' if value == 'yes' else 'a difference or exclusion'} for: {criteria[index]['label']}.",
                               "observed_date": old if stale else recent, "source_ids": [source_id]})
    data["claims"].extend([
        {"id": "MOVE1", "competitor_id": "C1", "kind": "observation", "topic": "move",
         "statement": "Fictional RoutePilot announcement promotes branch-level contract discounts.", "observed_date": recent, "source_ids": ["S1"]},
        {"id": "MOVE2", "competitor_id": "C1", "kind": "observation", "topic": "move",
         "statement": "Fictional RoutePilot announcement also says implementation teams are fully booked for six weeks.", "observed_date": recent, "source_ids": ["S1"]},
    ])
    next_check = (now + timedelta(days=14)).isoformat()
    data["responses"] = [
        {"id": "H1", "competitor_id": "C1", "response": "Offer selective discounts to contested multi-branch accounts",
         "awareness": "Shared account competitions could expose the proposed package; direct awareness is not observed.",
         "motivation": "Existing branch discounts suggest commercial attention to this segment; margin tolerance is unknown.",
         "capability": "Pricing can change faster than implementation capacity; internal approval rules are unknown.",
         "supporting_claim_ids": ["MOVE1"], "counter_claim_ids": ["MOVE2"],
         "watch_for": "A dated public offer with branch-specific contract discounts, or documented customer-provided offer evidence.",
         "our_contingency": "Review contested deals and test a service bundle before changing the list price.",
         "owner": "Fictional commercial lead", "next_check": next_check},
        {"id": "H2", "competitor_id": "C1", "response": "Keep pricing stable and delay a response",
         "awareness": "The rival may see the offer but wait for evidence that it affects customer decisions.",
         "motivation": "A short-term share loss may matter less than protecting contribution; this is an assumption.",
         "capability": "The fictional implementation backlog may constrain new onboarding even if sales wishes to respond.",
         "supporting_claim_ids": ["MOVE2"], "counter_claim_ids": ["MOVE1"],
         "watch_for": "Public prices remain unchanged at the next check while onboarding lead times stay extended.",
         "our_contingency": "Track actual rival behavior and customer outcomes before escalating promotional spend.",
         "owner": "Fictional research lead", "next_check": next_check},
    ]
    return data


def demo_project(as_of: str = "2026-10-03") -> dict:
    project = new_project(demo_data(as_of), "FICTIONAL DEMO — invented companies, evidence and review decisions")
    for claim in project["data"]["claims"]:
        project = set_review(project, "claims", claim["id"], "accepted", "Fictional reviewer",
                             "Invented source alignment for demonstration; no real source was checked.", as_of)
    for row in project["data"]["assessments"]:
        project = set_review(project, "assessments", f"{row['competitor_id']}/{row['criterion_id']}", "accepted",
                             "Fictional reviewer", "Illustrative coding, not a real assessment.", as_of)
    return project
