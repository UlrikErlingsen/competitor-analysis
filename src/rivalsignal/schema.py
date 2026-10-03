"""Strict, portable JSON contract for bring-your-own-AI research."""
from __future__ import annotations

from copy import deepcopy
from datetime import date
import ipaddress
import json
import math
import re
from urllib.parse import urlsplit

from jsonschema import Draft202012Validator, FormatChecker


MAX_JSON_MB = 50  # matches the local upload cap; the record limits in SCHEMA keep valid files far smaller


class DataProblem(ValueError):
    """An actionable contract or evidence problem."""


def obj(properties):
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


def text(maximum=1500, minimum=1):
    return {"type": "string", "minLength": minimum, "maxLength": maximum,
            **({"pattern": r"\S"} if minimum else {})}


def enum(*values):
    return {"enum": list(values)}


def array(items, maximum=300, minimum=0):
    return {"type": "array", "items": items, "minItems": minimum, "maxItems": maximum}


ID = {"type": "string", "pattern": "^[A-Za-z][A-Za-z0-9_-]{0,39}$"}
DATE = {"type": "string", "format": "date"}
OPTIONAL_DATE = {"anyOf": [DATE, {"type": "null"}]}
REFS = {**array(ID, 20), "uniqueItems": True}
BRIEF = obj({"focal_company": text(120), "market": text(600), "decision": text(1000),
             "as_of": DATE, "horizon_days": {"type": "integer", "minimum": 1, "maximum": 1095}})
CRITERION = obj({"id": ID, "dimension": enum("market", "resource"), "label": text(120),
                 "definition": text(600), "weight": {"type": "number", "exclusiveMinimum": 0, "maximum": 1000}})
COMPETITOR = obj({"id": ID, "name": text(120), "type": enum("direct", "indirect", "potential", "substitute"),
                  "description": text(600, 0)})
SOURCE = obj({"id": ID, "title": text(300), "url": text(2000), "publisher": text(150),
              "published_date": OPTIONAL_DATE, "accessed_date": DATE, "origin_group": text(100)})
CLAIM = obj({"id": ID, "competitor_id": ID, "kind": enum("observation", "inference"),
             "topic": enum("market", "resource", "move", "other"), "statement": text(1500),
             "observed_date": OPTIONAL_DATE, "source_ids": REFS})
ASSESSMENT = obj({"competitor_id": ID, "criterion_id": ID, "judgment": enum("yes", "no", "unknown"),
                  "claim_ids": REFS, "rationale": text(1200, 0)})
RESPONSE = obj({"id": ID, "competitor_id": ID, "response": text(400),
                "awareness": text(1200, 0), "motivation": text(1200, 0), "capability": text(1200, 0),
                "supporting_claim_ids": REFS, "counter_claim_ids": REFS,
                "watch_for": text(1200, 0), "our_contingency": text(1200, 0),
                "owner": text(120, 0), "next_check": OPTIONAL_DATE})
SCHEMA = {"$schema": "https://json-schema.org/draft/2020-12/schema", **obj({
    "schema_version": {"const": "1.0"}, "brief": BRIEF,
    "criteria": array(CRITERION, 24, 2), "competitors": array(COMPETITOR, 12, 1),
    "sources": array(SOURCE, 100), "claims": array(CLAIM, 300),
    "assessments": array(ASSESSMENT, 288), "responses": array(RESPONSE, 36),
})}


def parse_json(payload: str | bytes) -> dict:
    if isinstance(payload, bytes):
        try:
            payload = payload.decode("utf-8-sig")
        except UnicodeError as exc:
            raise DataProblem("Use UTF-8 JSON text.") from exc
    if len(payload.encode("utf-8")) > MAX_JSON_MB * 1024 * 1024:
        raise DataProblem(f"Use JSON smaller than {MAX_JSON_MB} MB.")
    payload = payload.strip().lstrip("\ufeff")
    fence = re.fullmatch(r"```(?:json)?\s*\n(.*?)\n```", payload, re.S | re.I)
    if fence:
        payload = fence.group(1)

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise DataProblem(f"Duplicate JSON key: {key}. Keep only one value.")
            result[key] = value
        return result

    def invalid_number(value):
        raise DataProblem(f"{value} is not a valid JSON number.")

    try:
        parsed = json.loads(payload, object_pairs_hook=pairs, parse_constant=invalid_number)
    except json.JSONDecodeError as exc:
        raise DataProblem(f"JSON syntax error at line {exc.lineno}, column {exc.colno}: {exc.msg}. Paste just the JSON object.") from exc
    except (RecursionError, ValueError) as exc:
        if isinstance(exc, DataProblem):
            raise
        raise DataProblem("The JSON is too deeply nested or contains an invalid value.") from exc
    if not isinstance(parsed, dict):
        raise DataProblem("The response must be one JSON object, not a list or prose.")
    return parsed


def safe_url(value: str) -> bool:
    """Links only. The app never fetches, executes or embeds imported URLs."""
    if any(c.isspace() or ord(c) < 32 for c in value) or "\\" in value:
        return False
    try:
        parsed = urlsplit(value)
        if parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.username or parsed.password:
            return False
        host = parsed.hostname.lower().rstrip(".")
        if host in {"localhost", "localhost.localdomain"} or host.endswith((".local", ".internal", ".localhost")):
            return False
        try:
            if not ipaddress.ip_address(host).is_global:
                return False
        except ValueError:
            if "." not in host:
                return False
        return parsed.port is None or 1 <= parsed.port <= 65535
    except ValueError:
        return False


def assessment_key(competitor: str, criterion: str) -> str:
    return f"{competitor}/{criterion}"


def validate_data(data: dict) -> dict:
    # Fail fast on oversized collections before validating every record against the full schema.
    if isinstance(data, dict):
        for name, spec in SCHEMA["properties"].items():
            if "maxItems" in spec and isinstance(data.get(name), list) and len(data[name]) > spec["maxItems"]:
                raise DataProblem(f"{name}: at most {spec['maxItems']} records are allowed; found {len(data[name])}.")
    errors = sorted(Draft202012Validator(SCHEMA, format_checker=FormatChecker()).iter_errors(data),
                    key=lambda e: str(list(e.absolute_path)))
    if errors:
        details = [f"{' / '.join(map(str, e.absolute_path)) or 'root'}: {e.message}" for e in errors[:8]]
        raise DataProblem("Invalid research format:\n" + "\n".join(details))
    data = deepcopy(data)
    maps = {}
    for name in ["criteria", "competitors", "sources", "claims", "responses"]:
        rows = data[name]
        maps[name] = {row["id"]: row for row in rows}
        if len(maps[name]) != len(rows):
            raise DataProblem(f"{name}: IDs must be unique.")
    if {c["dimension"] for c in data["criteria"]} != {"market", "resource"}:
        raise DataProblem("Include at least one market criterion and one resource criterion.")
    if any(not math.isfinite(c["weight"]) for c in data["criteria"]):
        raise DataProblem("Criterion weights must be finite, positive numbers.")
    if len({c["name"].strip().casefold() for c in data["competitors"]}) != len(data["competitors"]):
        raise DataProblem("Competitor names must be distinct.")
    for field in ["focal_company", "market", "decision"]:
        if not data["brief"][field].strip():
            raise DataProblem(f"Brief {field} must not be blank.")
    as_of = date.fromisoformat(data["brief"]["as_of"])
    for source in data["sources"]:
        if not safe_url(source["url"]):
            raise DataProblem(f"Source {source['id']}: use a public HTTP(S) URL without embedded credentials.")
        accessed = date.fromisoformat(source["accessed_date"])
        published = date.fromisoformat(source["published_date"]) if source["published_date"] else None
        if accessed > as_of or (published and published > accessed):
            raise DataProblem(f"Source {source['id']}: publication/access dates conflict with the brief's as-of date.")
    for claim in data["claims"]:
        if claim["competitor_id"] not in maps["competitors"]:
            raise DataProblem(f"Claim {claim['id']}: unknown competitor_id.")
        if not set(claim["source_ids"]) <= maps["sources"].keys():
            raise DataProblem(f"Claim {claim['id']}: an unknown source_id was cited.")
        if claim["kind"] == "observation" and not claim["source_ids"]:
            raise DataProblem(f"Claim {claim['id']}: an observation needs a cited source; use inference for an unsupported interpretation.")
        if claim["observed_date"] and date.fromisoformat(claim["observed_date"]) > as_of:
            raise DataProblem(f"Claim {claim['id']}: observed_date is after the as-of date. Future plans must be dated when announced.")
    seen = set()

    def linked_claims(row, field):
        for claim_id in row[field]:
            if claim_id not in maps["claims"] or maps["claims"][claim_id]["competitor_id"] != row["competitor_id"]:
                raise DataProblem(f"{field}: each claim must exist and concern the same competitor as its assessment or response.")

    for row in data["assessments"]:
        key = assessment_key(row["competitor_id"], row["criterion_id"])
        if row["competitor_id"] not in maps["competitors"] or row["criterion_id"] not in maps["criteria"]:
            raise DataProblem("An assessment refers to an unknown competitor or criterion.")
        if key in seen:
            raise DataProblem(f"Duplicate assessment for {key}.")
        seen.add(key)
        linked_claims(row, "claim_ids")
    for row in data["responses"]:
        if row["competitor_id"] not in maps["competitors"]:
            raise DataProblem(f"Response {row['id']}: unknown competitor.")
        linked_claims(row, "supporting_claim_ids")
        linked_claims(row, "counter_claim_ids")
        if set(row["supporting_claim_ids"]) & set(row["counter_claim_ids"]):
            raise DataProblem(f"Response {row['id']}: a claim cannot be listed as both support and counterevidence.")
    return data


def new_project(data: dict, source: str = "Imported research draft") -> dict:
    return {"format": "rivalsignal-project-v1", "data": validate_data(data),
            "reviews": {"claims": {}, "assessments": {}},
            "policy": {"max_age_days": 180}, "provenance": source}


def import_research(payload: str | bytes) -> dict:
    """AI content has no route to create human review decisions."""
    return new_project(parse_json(payload))


def restore_project(payload: str | bytes) -> dict:
    project = parse_json(payload)
    required = {"format", "data", "reviews", "policy", "provenance"}
    if set(project) != required or project["format"] != "rivalsignal-project-v1":
        raise DataProblem("This is not a Rival Signal saved project. Use AI import for a research JSON response.")
    project["data"] = validate_data(project["data"])
    if not isinstance(project["provenance"], str) or len(project["provenance"]) > 200:
        raise DataProblem("Invalid project provenance label.")
    if not isinstance(project["policy"], dict) or set(project["policy"]) != {"max_age_days"}:
        raise DataProblem("Saved project needs its freshness policy.")
    age = project["policy"]["max_age_days"]
    if type(age) is not int or not 1 <= age <= 3650:
        raise DataProblem("Evidence age must be between 1 and 3,650 days.")
    reviews = project["reviews"]
    if not isinstance(reviews, dict) or set(reviews) != {"claims", "assessments"}:
        raise DataProblem("Invalid saved reviews.")
    keys = {"claims": {c["id"] for c in project["data"]["claims"]},
            "assessments": {assessment_key(a["competitor_id"], a["criterion_id"]) for a in project["data"]["assessments"]}}
    review_schema = obj({"status": enum("pending", "accepted", "rejected"), "reviewer": text(120, 0),
                         "note": text(1500, 0), "checked_on": DATE})
    for kind in keys:
        if not isinstance(reviews[kind], dict) or not set(reviews[kind]) <= keys[kind]:
            raise DataProblem(f"Saved {kind} reviews refer to missing records.")
        for review in reviews[kind].values():
            if list(Draft202012Validator(review_schema, format_checker=FormatChecker()).iter_errors(review)):
                raise DataProblem("A saved review has an invalid format.")
            if review["status"] == "accepted" and (not review["reviewer"].strip() or not review["note"].strip()):
                raise DataProblem("Accepted reviews need a reviewer and a note explaining the source check or coding judgment.")
    return project
