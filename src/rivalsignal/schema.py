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

from rivalsignal import limits
from rivalsignal.limits import DEMO, TEXT


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


# The schema below carries the public-demo caps from limits.py (maxLength, maxItems). Run locally, the app uses
# uncapped(): the same contract without any length or count limit. Value ranges and the ID format always apply.
ID = {"type": "string", "pattern": "^[A-Za-z][A-Za-z0-9_-]{0,39}$"}
DATE = {"type": "string", "format": "date"}
OPTIONAL_DATE = {"anyOf": [DATE, {"type": "null"}]}
REFS = {**array(ID, DEMO["refs"]), "uniqueItems": True}
BRIEF = obj({"focal_company": text(TEXT["name"]), "market": text(TEXT["paragraph"]), "decision": text(TEXT["decision"]),
             "as_of": DATE, "horizon_days": {"type": "integer", "minimum": 1, "maximum": 1095}})
CRITERION = obj({"id": ID, "dimension": enum("market", "resource"), "label": text(TEXT["name"]),
                 "definition": text(TEXT["paragraph"]), "weight": {"type": "number", "exclusiveMinimum": 0, "maximum": 1000}})
COMPETITOR = obj({"id": ID, "name": text(TEXT["name"]), "type": enum("direct", "indirect", "potential", "substitute"),
                  "description": text(TEXT["paragraph"], 0)})
SOURCE = obj({"id": ID, "title": text(TEXT["title"]), "url": text(TEXT["url"]), "publisher": text(TEXT["publisher"]),
              "published_date": OPTIONAL_DATE, "accessed_date": DATE, "origin_group": text(TEXT["origin_group"])})
CLAIM = obj({"id": ID, "competitor_id": ID, "kind": enum("observation", "inference"),
             "topic": enum("market", "resource", "move", "other"), "statement": text(TEXT["statement"]),
             "observed_date": OPTIONAL_DATE, "source_ids": REFS})
ASSESSMENT = obj({"competitor_id": ID, "criterion_id": ID, "judgment": enum("yes", "no", "unknown"),
                  "claim_ids": REFS, "rationale": text(TEXT["reasoning"], 0)})
REASONING = text(TEXT["reasoning"], 0)
RESPONSE = obj({"id": ID, "competitor_id": ID, "response": text(TEXT["response"]),
                "awareness": REASONING, "motivation": REASONING, "capability": REASONING,
                "supporting_claim_ids": REFS, "counter_claim_ids": REFS,
                "watch_for": REASONING, "our_contingency": REASONING,
                "owner": text(TEXT["name"], 0), "next_check": OPTIONAL_DATE})
SCHEMA = {"$schema": "https://json-schema.org/draft/2020-12/schema", **obj({
    "schema_version": {"const": "1.0"}, "brief": BRIEF,
    "criteria": array(CRITERION, DEMO["criteria"], 2), "competitors": array(COMPETITOR, DEMO["competitors"], 1),
    "sources": array(SOURCE, DEMO["sources"]), "claims": array(CLAIM, DEMO["claims"]),
    "assessments": array(ASSESSMENT, DEMO["assessments"]), "responses": array(RESPONSE, DEMO["responses"]),
})}
REVIEW = obj({"status": enum("pending", "accepted", "rejected"), "reviewer": text(TEXT["name"], 0),
              "note": text(TEXT["statement"], 0), "checked_on": DATE})


def uncapped(schema):
    """The same contract without maxLength or maxItems: no length or count limits."""
    if isinstance(schema, dict):
        return {key: uncapped(value) for key, value in schema.items() if key not in {"maxLength", "maxItems"}}
    if isinstance(schema, list):
        return [uncapped(value) for value in schema]
    return schema


_LOCAL = {"research": uncapped(SCHEMA), "review": uncapped(REVIEW),
          "records": uncapped({"sources_record": SOURCE, "claims_record": CLAIM, "responses_record": RESPONSE})}


def active_schema() -> dict:
    """The research schema in force: demo-capped with SIGNAL_PUBLIC=1, otherwise uncapped."""
    return SCHEMA if limits.public() else _LOCAL["research"]


def record_schemas() -> dict:
    """The source, claim and response record schemas in force, for the research prompt."""
    if limits.public():
        return {"sources_record": SOURCE, "claims_record": CLAIM, "responses_record": RESPONSE}
    return _LOCAL["records"]


def parse_json(payload: str | bytes) -> dict:
    if isinstance(payload, bytes):
        try:
            payload = payload.decode("utf-8-sig")
        except UnicodeError as exc:
            raise DataProblem("Use UTF-8 JSON text.") from exc
    max_mb = limits.cap("json_mb")
    if max_mb is not None and len(payload.encode("utf-8")) > max_mb * 1024 * 1024:
        raise DataProblem(f"Use JSON smaller than {max_mb} MB. {limits.DEMO_NOTE}")
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
    except MemoryError as exc:
        raise DataProblem(limits.MEMORY_MESSAGE) from exc
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
    schema = active_schema()
    # Public demo: fail fast on oversized collections before validating every record against the full schema.
    if isinstance(data, dict):
        for name, spec in schema["properties"].items():
            if "maxItems" in spec and isinstance(data.get(name), list) and len(data[name]) > spec["maxItems"]:
                raise DataProblem(f"{name}: at most {spec['maxItems']} records are allowed; found {len(data[name])}. "
                                  + limits.DEMO_NOTE)
    errors = sorted(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(data),
                    key=lambda e: str(list(e.absolute_path)))
    if errors:
        details = [f"{' / '.join(map(str, e.absolute_path)) or 'root'}: {e.message}" for e in errors[:8]]
        if any(e.validator in {"maxLength", "maxItems"} for e in errors):
            details.append(limits.DEMO_NOTE)
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
    longest = limits.chars("provenance")
    if not isinstance(project["provenance"], str) or (longest is not None and len(project["provenance"]) > longest):
        raise DataProblem("Invalid project provenance label." + (f" {limits.DEMO_NOTE}" if longest else ""))
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
    review_schema = REVIEW if limits.public() else _LOCAL["review"]
    for kind in keys:
        if not isinstance(reviews[kind], dict) or not set(reviews[kind]) <= keys[kind]:
            raise DataProblem(f"Saved {kind} reviews refer to missing records.")
        for review in reviews[kind].values():
            if list(Draft202012Validator(review_schema, format_checker=FormatChecker()).iter_errors(review)):
                raise DataProblem("A saved review has an invalid format.")
            if review["status"] == "accepted" and (not review["reviewer"].strip() or not review["note"].strip()):
                raise DataProblem("Accepted reviews need a reviewer and a note explaining the source check or coding judgment.")
    return project
