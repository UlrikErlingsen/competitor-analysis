"""Portable project, printable brief and auditable evidence pack."""
from html import escape
from io import BytesIO
import json
from zipfile import ZipFile, ZIP_DEFLATED

import pandas as pd

from rivalsignal import __version__
from rivalsignal.analysis import analyze_project, fingerprint, response_audit
from rivalsignal.research import SOURCES, LIMITS


def project_bytes(project: dict) -> bytes:
    return json.dumps(project, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8")


def csv_bytes(frame: pd.DataFrame) -> bytes:
    output = frame.copy()
    for column in output.columns:
        if output[column].dtype == "object":
            def safe(value):
                value = ", ".join(map(str, value)) if isinstance(value, list) else value
                if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
                    return "'" + value
                return value
            output[column] = output[column].map(safe)
    return output.to_csv(index=False).encode("utf-8-sig")


def printable_html(project: dict) -> str:
    data = project["data"]
    result = analyze_project(project)
    def e(value):
        return escape(str(value))
    parts = ["<!doctype html><html lang='en'><meta charset='utf-8'><title>Rival Signal — competitor brief</title>",
             "<style>body{font:15px/1.6 system-ui,sans-serif;color:#201e1d;max-width:1050px;margin:40px auto;padding:0 24px}"
             "h1,h2{color:#3d472b}table{border-collapse:collapse;width:100%;font-size:12px;overflow-wrap:anywhere}"
             "th,td{text-align:left;border-bottom:1px solid #ccc;padding:7px}th{background:#e1eecc}"
             ".note{padding:16px;background:#f5ead8}section{break-inside:avoid}a{color:#326384}"
             "@media print{body{margin:0;max-width:none;font-size:10pt}h2{break-after:avoid}thead{display:table-header-group}}"
             "</style><body><h1>Rival Signal · competitor brief</h1>",
             f"<p class='note'>{e(project['provenance'])}</p>",
             f"<h2>{e(data['brief']['focal_company'])}</h2><p><b>Market:</b> {e(data['brief']['market'])}<br>"
             f"<b>Decision:</b> {e(data['brief']['decision'])}<br><b>As of:</b> {e(data['brief']['as_of'])} · "
             f"<b>Horizon:</b> {data['brief']['horizon_days']} days · <b>Evidence age limit:</b> {project['policy']['max_age_days']} days</p>",
             "<h2>Competitor profiles</h2><p>Bounds show unresolved coding, not statistical uncertainty or threat. "
             "Lower = accepted yes weight / total; upper = (accepted yes + unresolved weight) / total. "
             "Both source observations and coding require review. Inferences and stale observations remain unresolved.</p>",
             result["profiles"].round(1).to_html(index=False, escape=True),
             "<h2>Criteria and weights</h2>", pd.DataFrame(data["criteria"]).to_html(index=False, escape=True),
             "<h2>Unresolved questions</h2>", result["gaps"].round(1).to_html(index=False, escape=True),
             "<h2>Response hypotheses</h2>"]
    names = {c["id"]: c["name"] for c in data["competitors"]}
    for response in data["responses"]:
        audit = response_audit(project, response)
        parts.append(f"<section><h3>{e(names[response['competitor_id']])}: {e(response['response'])}</h3>")
        for field in ["awareness", "motivation", "capability", "watch_for", "our_contingency", "owner", "next_check"]:
            parts.append(f"<p><b>{e(field.replace('_', ' ').title())}:</b> {e(response[field] or 'Not specified')}</p>")
        parts.append(f"<p>Linked support: {e(response['supporting_claim_ids'])}; counterevidence: {e(response['counter_claim_ids'])}. "
                     f"Reviewed/current support: {e(audit['reviewed_support'])}; reviewed/current counterevidence: "
                     f"{e(audit['reviewed_counterevidence'])}. Unresolved: {e(audit['unresolved_claims'])}.</p></section>")
    parts.append("<h2>Evidence ledger</h2>")
    parts.append(result["claims"].to_html(index=False, escape=True))
    parts.append("<h2>Sources supplied for this case</h2>")
    for source in data["sources"]:
        parts.append(f"<p><b>{e(source['id'])}</b> · <a href='{e(source['url'])}' rel='noopener noreferrer'>{e(source['title'])}</a> "
                     f"· {e(source['publisher'])} · published {e(source['published_date'] or 'unknown')} · "
                     f"accessed {e(source['accessed_date'])} · declared origin {e(source['origin_group'])}</p>")
    parts.append("<h2>Interpretation limits</h2><ul>" + "".join(f"<li>{e(x)}</li>" for x in LIMITS) + "</ul>")
    parts.append("<h2>Method references</h2>")
    for source in SOURCES:
        parts.append(f"<p>{e(source['authors'])} ({source['year']}). <a href='{e(source['url'])}'>{e(source['title'])}</a>. "
                     f"{e(source['application'])}</p>")
    parts.append(f"<p>Rival Signal {__version__} · project SHA-256: {fingerprint(project)}</p></body></html>")
    return "\n".join(parts)


def evidence_pack(project: dict) -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        archive.writestr("project.json", project_bytes(project))
        archive.writestr("research-draft.json", json.dumps(project["data"], indent=2, ensure_ascii=False, allow_nan=False))
        archive.writestr("brief.html", printable_html(project))
        for name, frame in analyze_project(project).items():
            archive.writestr(name + ".csv", csv_bytes(frame))
        archive.writestr("method.json", json.dumps({"app": "Rival Signal", "version": __version__,
            "project_sha256": fingerprint(project), "references": SOURCES, "limits": LIMITS,
            "csv_note": "Formula-like text is prefixed with an apostrophe in CSV exports."}, ensure_ascii=False, indent=2))
    return buffer.getvalue()
