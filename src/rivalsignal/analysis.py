"""Transparent evidence coverage and bounded, user-weighted competitor profiles.

These are application-defined descriptive proxies, not Chen's empirical measures,
validated psychometric scales, probabilities of attack, or confidence intervals.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date
import hashlib
import json

import pandas as pd

from rivalsignal import limits
from rivalsignal.schema import DataProblem, assessment_key


def fingerprint(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def set_review(project: dict, kind: str, record_id: str, status: str, reviewer: str, note: str, checked_on: str) -> dict:
    if kind not in {"claims", "assessments"} or status not in {"pending", "accepted", "rejected"}:
        raise DataProblem("Choose a valid review status and record type.")
    valid_ids = ({c["id"] for c in project["data"]["claims"]} if kind == "claims" else
                 {assessment_key(a["competitor_id"], a["criterion_id"]) for a in project["data"]["assessments"]})
    if record_id not in valid_ids:
        raise DataProblem("The record to review no longer exists.")
    try:
        date.fromisoformat(checked_on)
    except (ValueError, TypeError) as exc:
        raise DataProblem("The review date must be YYYY-MM-DD.") from exc
    if status == "accepted" and (not reviewer.strip() or not note.strip()):
        raise DataProblem("Record your name and a short note explaining what you checked before accepting.")
    name_cap, note_cap = limits.chars("name"), limits.chars("statement")
    if (name_cap and len(reviewer) > name_cap) or (note_cap and len(note) > note_cap):
        raise DataProblem(f"Keep the reviewer name under {name_cap} characters and the note under {note_cap:,}. "
                          + limits.DEMO_NOTE)
    result = deepcopy(project)
    result["reviews"][kind][record_id] = {"status": status, "reviewer": reviewer.strip(),
                                          "note": note.strip(), "checked_on": checked_on}
    return result


def claim_readiness(project: dict, claim: dict) -> tuple[bool, str]:
    review = project["reviews"]["claims"].get(claim["id"], {})
    status = review.get("status", "pending")
    if status != "accepted":
        return False, "Rejected claim" if status == "rejected" else "Claim awaiting review"
    if claim["kind"] != "observation":
        return False, "Inference, not an observation"
    if not claim["source_ids"]:
        return False, "No cited source"
    if not claim["observed_date"]:
        return False, "Evidence date unknown"
    age = (date.fromisoformat(project["data"]["brief"]["as_of"]) - date.fromisoformat(claim["observed_date"])).days
    if age < 0:
        return False, "Evidence after the as-of date"
    if age > project["policy"]["max_age_days"]:
        return False, "Evidence needs refreshing"
    return True, "Reviewed observation within age limit"


def assessment_readiness(project: dict, row: dict | None) -> tuple[str, str]:
    if row is None:
        return "unknown", "No assessment supplied"
    if row["judgment"] == "unknown":
        return "unknown", "Judgment unknown"
    key = assessment_key(row["competitor_id"], row["criterion_id"])
    status = project["reviews"]["assessments"].get(key, {}).get("status", "pending")
    if status != "accepted":
        return "unknown", "Assessment rejected" if status == "rejected" else "Assessment awaiting review"
    if not row["claim_ids"]:
        return "unknown", "No linked observations"
    claims = {c["id"]: c for c in project["data"]["claims"]}
    for claim_id in row["claim_ids"]:
        ready, reason = claim_readiness(project, claims[claim_id])
        if not ready:
            return "unknown", f"{claim_id}: {reason}"
    return row["judgment"], "Reviewed coding with reviewed, current observations"


def analyze_project(project: dict) -> dict:
    data = project["data"]
    assessments = {assessment_key(a["competitor_id"], a["criterion_id"]): a for a in data["assessments"]}
    cells, profiles = [], []
    for competitor in data["competitors"]:
        profile = {"competitor_id": competitor["id"], "competitor": competitor["name"], "type": competitor["type"]}
        for dimension in ["market", "resource"]:
            criteria = [c for c in data["criteria"] if c["dimension"] == dimension]
            total = sum(c["weight"] for c in criteria)
            yes = unknown = 0.0
            for criterion in criteria:
                key = assessment_key(competitor["id"], criterion["id"])
                row = assessments.get(key)
                effective, reason = assessment_readiness(project, row)
                weight = criterion["weight"] / total * 100
                yes += weight if effective == "yes" else 0
                unknown += weight if effective == "unknown" else 0
                cells.append({"competitor_id": competitor["id"], "competitor": competitor["name"],
                              "criterion_id": criterion["id"], "dimension": dimension, "criterion": criterion["label"],
                              "weight_percent": weight, "proposed_judgment": row["judgment"] if row else "unknown",
                              "effective_judgment": effective, "reason": reason,
                              "claim_ids": ", ".join(row["claim_ids"]) if row else ""})
            profile[f"{dimension}_low"] = yes
            profile[f"{dimension}_high"] = min(100.0, yes + unknown)
            profile[f"{dimension}_resolved"] = max(0.0, 100 - unknown)
        profiles.append(profile)
    claim_rows = []
    for claim in data["claims"]:
        ready, reason = claim_readiness(project, claim)
        claim_rows.append({**claim, "review_status": project["reviews"]["claims"].get(claim["id"], {}).get("status", "pending"),
                           "eligible_for_mapping": ready, "reason": reason})
    columns = ["id", "competitor_id", "kind", "topic", "statement", "observed_date", "source_ids",
               "review_status", "eligible_for_mapping", "reason"]
    cells = pd.DataFrame(cells)
    return {"profiles": pd.DataFrame(profiles), "cells": cells, "claims": pd.DataFrame(claim_rows, columns=columns),
            "gaps": cells[cells.effective_judgment.eq("unknown")].sort_values(
                ["weight_percent", "competitor", "criterion"], ascending=[False, True, True]).reset_index(drop=True)}


def response_audit(project: dict, response: dict) -> dict:
    claims = {c["id"]: c for c in project["data"]["claims"]}
    supporting = [c for c in response["supporting_claim_ids"] if claim_readiness(project, claims[c])[0]]
    counter = [c for c in response["counter_claim_ids"] if claim_readiness(project, claims[c])[0]]
    all_refs = response["supporting_claim_ids"] + response["counter_claim_ids"]
    unresolved = [c for c in all_refs if not claim_readiness(project, claims[c])[0]]
    missing = [name for name in ["awareness", "motivation", "capability", "watch_for", "our_contingency", "owner"]
               if not response[name].strip()]
    if not response["next_check"]:
        missing.append("next_check")
    due = bool(response["next_check"] and response["next_check"] <= project["data"]["brief"]["as_of"])
    return {"reviewed_support": supporting, "reviewed_counterevidence": counter,
            "unresolved_claims": unresolved, "missing": missing, "check_due": due}


def compare_projects(previous: dict, current: dict) -> dict:
    """Compare snapshots without merging them or interpreting edits as market events."""
    records = []
    for section in ["competitors", "criteria", "sources", "claims", "assessments", "responses"]:
        def keyed(project):
            return {(assessment_key(r["competitor_id"], r["criterion_id"]) if section == "assessments" else r["id"]): r
                    for r in project["data"][section]}
        before, after = keyed(previous), keyed(current)
        for key in sorted(before.keys() | after.keys()):
            change = "added" if key not in before else "removed" if key not in after else "changed" if before[key] != after[key] else None
            if change:
                records.append({"section": section, "record": key, "change": change})
    for kind in ["claims", "assessments"]:
        before, after = previous["reviews"][kind], current["reviews"][kind]
        for key in sorted(before.keys() | after.keys()):
            if before.get(key) != after.get(key):
                records.append({"section": f"{kind} reviews", "record": key, "change": "changed"})
    def basis(p):
        return {"brief": {k: v for k, v in p["data"]["brief"].items() if k != "as_of"},
                "criteria": sorted(p["data"]["criteria"], key=lambda c: c["id"]), "policy": p["policy"],
                "competitors": sorted(p["data"]["competitors"], key=lambda c: c["id"])}
    comparable = basis(previous) == basis(current)
    if previous["data"]["brief"] != current["data"]["brief"]:
        records.append({"section": "brief", "record": "brief", "change": "changed"})
    if previous["policy"] != current["policy"]:
        records.append({"section": "policy", "record": "freshness", "change": "changed"})
    deltas = pd.DataFrame()
    if comparable:
        before = analyze_project(previous)["profiles"].set_index("competitor_id")
        after = analyze_project(current)["profiles"].set_index("competitor_id")
        common = before.index.intersection(after.index)
        rows = []
        for key in common:
            row = {"competitor": after.loc[key, "competitor"]}
            for dimension in ["market", "resource"]:
                for edge in ["low", "high"]:
                    column = f"{dimension}_{edge}"
                    row[f"{column}_change"] = float(after.loc[key, column] - before.loc[key, column])
            rows.append(row)
        deltas = pd.DataFrame(rows)
    return {"changes": pd.DataFrame(records, columns=["section", "record", "change"]),
            "comparable": comparable, "deltas": deltas}
