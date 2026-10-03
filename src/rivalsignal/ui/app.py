"""A local workspace for research, source review and competitor response reasoning."""
from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime
from html import escape
from itertools import count
import json
import os
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from rivalsignal import __version__, limits
from rivalsignal.analysis import analyze_project, assessment_readiness, claim_readiness, compare_projects, fingerprint, response_audit, set_review
from rivalsignal.examples import demo_data, demo_project
from rivalsignal.exports import evidence_pack, printable_html, project_bytes
from rivalsignal.prompts import build_research_prompt, repair_prompt, research_skeleton
from rivalsignal.research import LIMITS, SOURCES, SCOPE
from rivalsignal.schema import (DataProblem, active_schema, assessment_key, import_research, new_project,
                                restore_project, validate_data)
from rivalsignal.ui import signal_theme as sig

NS = "rival"
DIMENSIONS = {"market": "Market overlap", "resource": "Capability resemblance"}
STATUS = ["pending", "accepted", "rejected"]


def k(name):
    return f"{NS}:{name}"


def in_hub():
    """Signal Hub sets SIGNAL_HUB=1: session memory only, no file writes, no network calls."""
    return os.environ.get("SIGNAL_HUB") == "1"


def today():
    return datetime.now(ZoneInfo("Europe/Oslo")).date()


def project():
    return st.session_state[k("project")]


def replace_project(value):
    st.session_state[k("project")] = value
    st.session_state[k("revision")] = st.session_state.get(k("revision"), 0) + 1
    st.session_state.pop(k("candidate"), None)


def revision():
    return str(st.session_state.get(k("revision"), 0))


def table(frame, **kwargs):
    st.dataframe(frame, hide_index=True, width="stretch", **kwargs)


def go_page(name):
    st.session_state[k("page")] = name


def overview():
    sig.hero(NS, eyebrow="COMPETITOR EVIDENCE & RESPONSE PLANNING", title="Know the rival.", em="Question the next move.",
             body="Bring research from your preferred AI. Check the sources, see where rivals overlap with you, "
                  "and prepare for competing responses before treating a plausible story as a fact.",
             pills=["Bring your own AI", "Source review", "Competitive dynamics", "Printable briefs"])
    sig.cards([
        ("01 / RESEARCH", "Ask a better question", "Define your market, capabilities and planned move. Copy a precise research prompt into your own AI tool."),
        ("02 / CHALLENGE", "Make the evidence visible", "Paste the JSON response. Review observations and coding; missing, stale and inferred evidence stays unresolved."),
        ("03 / PREPARE", "Consider more than one response", "Use awareness, motivation and capability to compare hypotheses, counterevidence and signals to check next."),
    ])
    result = analyze_project(project())
    cols = st.columns(4)
    cols[0].metric("Competitors in scope", len(project()["data"]["competitors"]))
    cols[1].metric("Research claims", len(result["claims"]))
    cols[2].metric("Reviewed, current observations", int(result["claims"].eligible_for_mapping.sum()))
    cols[3].metric("Unresolved map cells", len(result["gaps"]))
    st.subheader("A distinct question for the Signal suite")
    st.write("Which firms or substitutes can contest our move, what evidence supports that view, "
             "and which observable developments would change our response?")
    table(pd.DataFrame(SCOPE, columns=["Existing app", "Its question", "Rival's boundary"]))
    left, right = st.columns(2)
    left.button("Create a research prompt", key=k("go_prompt"), type="primary", on_click=go_page, args=("1 · Brief & AI prompt",))
    right.button("Explore the competitor map", key=k("go_map"), on_click=go_page, args=("3 · Rival map",))
    sig.note("info", "**Academically informed, with explicit limits.** Competitive-dynamics research supplies the framework. "
             "The app's coding and weights are transparent decision aids, not a validated forecast of a rival's actions.")


def brief_and_prompt():
    sig.header("DEFINE → COPY → RESEARCH", "Give your AI a research contract.",
               "Use a browsing-capable AI or provide source material yourself. The app makes no AI calls.")
    data = project()["data"]
    with st.expander("Edit the research brief and start a new case", expanded=not data["claims"]):
        st.info("Starting a case replaces the active evidence and reviews in this session. Download the current project first if you want to keep it.")
        rev = revision()
        with st.form(k("brief_form:" + rev)):
            focal = st.text_input("Your company or offering", data["brief"]["focal_company"], max_chars=limits.chars("name"),
                                  key=k("brief_focal:" + rev))
            market = st.text_area("Customer need, geography and market boundary", data["brief"]["market"],
                                  max_chars=limits.chars("paragraph"),
                                  key=k("brief_market:" + rev))
            decision = st.text_area("The strategic move you are considering", data["brief"]["decision"],
                                    max_chars=limits.chars("decision"),
                                    key=k("brief_decision:" + rev))
            c1, c2 = st.columns(2)
            as_of = c1.date_input("Research cutoff", date.fromisoformat(data["brief"]["as_of"]), key=k("brief_as_of:" + rev))
            horizon = c2.number_input("Response horizon in days", 1, 1095, data["brief"]["horizon_days"],
                                      key=k("brief_horizon:" + rev))
            st.markdown("**Comparison criteria**")
            st.caption("Market criteria describe markets YOU serve; resource criteria describe capabilities YOU possess. "
                       "Keep criteria distinct. Weights express importance within each dimension and are normalized separately.")
            criteria = st.data_editor(pd.DataFrame(data["criteria"]), num_rows="dynamic", hide_index=True, width="stretch",
                                     column_config={"dimension": st.column_config.SelectboxColumn(options=["market", "resource"]),
                                                    "weight": st.column_config.NumberColumn(min_value=0.01, max_value=1000.0)},
                                     key=k("criteria_editor:" + revision()))
            st.markdown("**Named rivals and substitutes**")
            competitors = st.data_editor(pd.DataFrame(data["competitors"]), num_rows="dynamic", hide_index=True, width="stretch",
                                         column_config={"type": st.column_config.SelectboxColumn(options=["direct", "indirect", "potential", "substitute"])},
                                         key=k("competitor_editor:" + revision()))
            if st.form_submit_button("Start case from this brief", type="primary", key=k("brief_submit:" + rev)):
                brief = {"focal_company": focal, "market": market, "decision": decision, "as_of": as_of.isoformat(), "horizon_days": int(horizon)}
                skeleton = research_skeleton(brief, criteria.to_dict("records"), competitors.fillna("").to_dict("records"))
                replace_project(new_project(skeleton, "User-defined case — awaiting research"))
                st.session_state[k("expected_contract")] = {name: skeleton[name] for name in ["brief", "criteria", "competitors"]}
                st.rerun()
    st.markdown("**Active research brief**")
    st.text(f"{data['brief']['focal_company']}\n{data['brief']['market']}\n{data['brief']['decision']}\n"
            f"As of {data['brief']['as_of']} · {data['brief']['horizon_days']}-day response horizon")
    notes = st.text_area("Optional source links or source material to include in the prompt", height=100,
                         max_chars=limits.cap("source_material_chars"),
                         help="Anything entered here is included in the prompt you manually copy to your chosen AI.", key=k("prompt_notes"))
    prompt = build_research_prompt(data["brief"], data["criteria"], data["competitors"], notes)
    st.markdown("1. Copy the prompt below into your preferred AI and enable its web research if available.\n"
                "2. Ask it to return the specified JSON. Without web access, give it sources and keep other answers unknown.\n"
                "3. Paste the response into **Import & review**. Review the sources before accepting claims and assessments.")
    with st.expander("Copy the complete research prompt", expanded=True):
        st.code(prompt, language="text", height=360)
    c1, c2 = st.columns(2)
    c1.download_button("Download research prompt", prompt, "rival-research-prompt.txt", "text/plain", key=k("prompt_download"))
    c2.download_button("Download JSON schema", json.dumps(active_schema(), indent=2), "rival-research.schema.json", "application/json", key=k("schema_download"))
    st.caption("No API key is needed. Copying is manual: the app never submits the prompt or any of your data to an AI provider.")


def _contract_matches(candidate):
    expected = st.session_state.get(k("expected_contract"))
    if expected is None:
        return True
    def normalize(value):
        return {"brief": value["brief"], "criteria": sorted(value["criteria"], key=lambda x: x["id"]),
                "competitors": sorted(value["competitors"], key=lambda x: x["id"])}
    return normalize(expected) == normalize(candidate["data"])


def _import_draft():
    with st.expander("Paste or upload an AI research response", expanded=not project()["data"]["claims"]):
        method = st.radio("Research input", ["Paste JSON", "Upload JSON"], horizontal=True, key=k("input_method"))
        if method == "Paste JSON":
            raw = st.text_area("AI response", height=230, max_chars=limits.cap("paste_chars"), key=k("ai_response"))
        else:
            uploaded = st.file_uploader("Research JSON", type=["json"], key=k("research_upload"))
            raw = uploaded.getvalue() if uploaded else b""
        if limits.public():
            st.caption(f"Public demo: pasted replies up to {limits.DEMO['paste_chars']:,} characters, files up to "
                       f"{limits.DEMO['json_mb']} MB. The downloaded app has no limits.")
        raw_text = raw.decode("utf-8-sig", errors="replace") if isinstance(raw, bytes) else raw
        digest = fingerprint(raw_text)
        if st.button("Validate AI response", type="primary", key=k("validate_import")):
            st.session_state.pop(k("candidate"), None)
            try:
                candidate = import_research(raw)
                if not _contract_matches(candidate):
                    raise DataProblem("The response changed your saved brief, competitors or criteria. Ask the AI to preserve the research contract exactly.")
                st.session_state[k("candidate")] = {"project": candidate, "digest": digest}
                st.session_state.pop(k("import_error"), None)
            except DataProblem as exc:
                st.session_state[k("import_error")] = {"message": str(exc), "digest": digest}
        failure = st.session_state.get(k("import_error"), {})
        if failure.get("digest") == digest:
            st.error(failure["message"])
            with st.expander("Copy a repair prompt for your AI"):
                st.code(repair_prompt(failure["message"], raw_text), language="text", height=220)
        candidate = st.session_state.get(k("candidate"))
        if candidate and candidate["digest"] == digest:
            incoming = candidate["project"]["data"]
            st.success("The structure and references are valid. Factual accuracy has not been verified.")
            st.text(f"Case: {incoming['brief']['focal_company']}\nDecision: {incoming['brief']['decision']}\n"
                    f"{len(incoming['competitors'])} rivals · {len(incoming['sources'])} sources · {len(incoming['claims'])} claims")
            st.caption("Loading replaces the active case and clears every human review. Download the current project first if needed.")
            if st.button("Load this draft for review", key=k("load_draft")):
                replace_project(candidate["project"])
                st.rerun()
        st.download_button("Download a fictional AI response to try", json.dumps(demo_data(), ensure_ascii=False, indent=2),
                           "rival-fictional-ai-response.json", "application/json", key=k("ai_example"))


def _review_form(kind, record_id):
    review = project()["reviews"][kind].get(record_id, {})
    form = f"review:{kind}:{record_id}:{revision()}"
    with st.form(k(form)):
        status = st.selectbox("Review decision", STATUS, index=STATUS.index(review.get("status", "pending")),
                              key=k(form + ":status"))
        reviewer = st.text_input("Reviewed by", review.get("reviewer", ""), max_chars=limits.chars("name"), key=k(form + ":reviewer"))
        note = st.text_area("What did you check?", review.get("note", ""), max_chars=limits.chars("statement"), key=k(form + ":note"),
                            help="For claims, record whether the source supports the wording and date. For assessments, explain the coding against the definition.")
        if st.form_submit_button("Save review", type="primary", key=k(form + ":save")):
            replace_project(set_review(project(), kind, record_id, status, reviewer, note, today().isoformat()))
            st.rerun()


def review():
    sig.header("DRAFT → SOURCES → HUMAN JUDGMENT", "Review what the research actually supports.",
               "Accepting a claim records your source check. It does not certify that the claim is objectively true.")
    _import_draft()
    data = project()["data"]
    st.subheader("Evidence freshness")
    st.caption("The cutoff uses the underlying observation date. Opening an old page today does not make its evidence new.")
    rev = revision()
    with st.form(k("freshness:" + rev)):
        c1, c2 = st.columns(2)
        as_of = c1.date_input("Analysis as-of date", date.fromisoformat(data["brief"]["as_of"]), key=k("fresh_as_of:" + rev))
        days = c2.number_input("Maximum evidence age in days", 1, 3650, project()["policy"]["max_age_days"],
                               key=k("fresh_days:" + rev))
        if st.form_submit_button("Update freshness policy", key=k("fresh_submit:" + rev)):
            updated = deepcopy(project())
            updated["data"]["brief"]["as_of"] = as_of.isoformat()
            updated["data"] = validate_data(updated["data"])
            updated["policy"]["max_age_days"] = int(days)
            replace_project(updated)
            st.session_state.pop(k("expected_contract"), None)
            st.rerun()
    result = analyze_project(project())
    if not data["claims"]:
        st.info("This case has no claims yet. Generate the prompt, research with your AI, then import its response above.")
        return
    ctab, atab = st.tabs(["1 · Check claims and sources", "2 · Check map coding"])
    with ctab:
        table(result["claims"][["id", "competitor_id", "kind", "statement", "observed_date", "review_status", "reason"]])
        selected = st.selectbox("Claim to inspect", [c["id"] for c in data["claims"]], key=k("claim_pick"))
        claim = next(c for c in data["claims"] if c["id"] == selected)
        st.text(claim["statement"])
        st.caption("Declared type: " + claim["kind"] + " · " + claim_readiness(project(), claim)[1])
        sources = {s["id"]: s for s in data["sources"]}
        for source_id in claim["source_ids"]:
            source = sources[source_id]
            st.text(f"{source_id} · {source['title']}\n{source['publisher']} · published {source['published_date'] or 'unknown'} · "
                    f"accessed {source['accessed_date']}\nDeclared source family: {source['origin_group']}")
            if ".example/" in source["url"]:
                st.caption("Fictional example URL — this is not a real source.")
            else:
                st.link_button(f"Open source {source_id}", source["url"], key=k(f"open_source:{selected}:{source_id}"))
        if not claim["source_ids"]:
            st.info("No source is cited. This inference cannot resolve a map cell.")
        _review_form("claims", selected)
    with atab:
        table(result["cells"][["competitor", "criterion", "proposed_judgment", "effective_judgment", "reason"]])
        supplied = {assessment_key(a["competitor_id"], a["criterion_id"]) for a in data["assessments"]}
        missing = [{"competitor_id": comp["id"], "criterion_id": criterion["id"],
                    "judgment": "unknown", "claim_ids": [], "rationale": "Not supplied in the research draft."}
                   for comp in data["competitors"] for criterion in data["criteria"]
                   if assessment_key(comp["id"], criterion["id"]) not in supplied]
        if missing and st.button("Add missing assessment rows as unknown", key=k("add_missing_coding")):
            updated = deepcopy(project())
            updated["data"]["assessments"].extend(missing)
            replace_project(updated)
            st.rerun()
        if data["assessments"]:
            keys = [assessment_key(a["competitor_id"], a["criterion_id"]) for a in data["assessments"]]
            selected = st.selectbox("Assessment to inspect", keys, key=k("assessment_pick"))
            row = next(a for a in data["assessments"] if assessment_key(a["competitor_id"], a["criterion_id"]) == selected)
            criterion = next(c for c in data["criteria"] if c["id"] == row["criterion_id"])
            st.text(f"Definition: {criterion['definition']}\nProposed judgment: {row['judgment']}\nRationale: {row['rationale']}")
            linked = [c for c in data["claims"] if c["id"] in row["claim_ids"]]
            if linked:
                table(pd.DataFrame(linked)[["id", "kind", "statement", "observed_date"]])
            st.caption("Effective result: " + " · ".join(assessment_readiness(project(), row)))
            with st.expander("Correct the proposed coding"):
                form = "edit_coding:" + selected + ":" + revision()
                with st.form(k(form)):
                    judgment = st.selectbox("Judgment", ["yes", "no", "unknown"], key=k(form + ":judgment"),
                                            index=["yes", "no", "unknown"].index(row["judgment"]))
                    ids = [c["id"] for c in data["claims"] if c["competitor_id"] == row["competitor_id"]]
                    refs = st.multiselect("Supporting observations", ids, default=row["claim_ids"], key=k(form + ":refs"))
                    rationale = st.text_area("Coding rationale", row["rationale"], max_chars=limits.chars("reasoning"), key=k(form + ":rationale"))
                    if st.form_submit_button("Save correction and reset its review", key=k(form + ":save")):
                        updated = deepcopy(project())
                        target = next(a for a in updated["data"]["assessments"] if assessment_key(a["competitor_id"], a["criterion_id"]) == selected)
                        target.update(judgment=judgment, claim_ids=refs, rationale=rationale)
                        updated["reviews"]["assessments"].pop(selected, None)
                        replace_project(updated)
                        st.rerun()
            _review_form("assessments", selected)


def rival_map():
    sig.header("TWO DIMENSIONS · VISIBLE UNKNOWNS", "Where do these rivals overlap with you?",
               "Compare markets and capabilities relative to the focal company, using only reviewed evidence and coding.")
    result = analyze_project(project())
    st.text(project()["data"]["brief"]["focal_company"] + " · " + project()["data"]["brief"]["market"])
    fig = go.Figure()
    colors = sig.colorway(NS)
    shown = limits.DISPLAY["map_rivals"]
    for index, row in result["profiles"].head(shown).iterrows():
        x0, x1, y0, y1 = row.market_low, row.market_high, row.resource_low, row.resource_high
        color = colors[index % len(colors)]
        complete = abs(x1 - x0) < 1e-8 and abs(y1 - y0) < 1e-8
        if not complete:
            fig.add_shape(type="rect", x0=x0, x1=x1, y0=y0, y1=y1,
                          line=dict(color=color, width=2), fillcolor=color, opacity=0.14)
        hover = (f"{escape(row.competitor)}<br>Market overlap: {x0:.0f}–{x1:.0f}<br>"
                 f"Capability resemblance: {y0:.0f}–{y1:.0f}<br>Range reflects unresolved coding, not a probability.")
        fig.add_trace(go.Scatter(x=[(x0 + x1) / 2], y=[(y0 + y1) / 2],
                                mode="markers+text" if complete else "text", text=[escape(row.competitor)],
                                textposition="top center" if complete else "middle center", textfont=dict(color=color),
                                marker=dict(size=12, color=color), name=escape(row.competitor), hovertemplate=hover + "<extra></extra>"))
    fig.update_layout(height=480, margin=dict(l=25, r=35, t=35, b=35), showlegend=False)
    fig.update_xaxes(title="Market overlap · weighted coding (%)", range=[-5, 110], dtick=25)
    fig.update_yaxes(title="Capability resemblance · weighted coding (%)", range=[-5, 110], dtick=25)
    sig.chart(NS, fig, key=k("map_chart"))
    if len(result["profiles"]) > shown:
        st.info(f"The chart shows the first {shown} of {len(result['profiles'])} rivals to stay readable. "
                "The table below, the analysis and every export include all of them.")
    st.caption("A box spans the range left unresolved by missing, stale, inferred or unreviewed evidence. "
               "Its label sits at the center only for readability; the center is not an estimate. A dot means all coding is resolved. "
               "A box can collapse to a line when just one dimension is unresolved.")
    table(result["profiles"].drop(columns="competitor_id").rename(columns={
        "market_low": "Market lower", "market_high": "Market upper", "market_resolved": "Market resolved %",
        "resource_low": "Capability lower", "resource_high": "Capability upper", "resource_resolved": "Capability resolved %"}).round(1))
    sig.note("info", "**The upper-right corner is not a prediction of aggression.** Shared markets and comparable resources "
             "describe competitive relationships. Incentives, mutual restraint and the particular move still matter.")
    st.subheader("What to research or review next")
    st.caption("Unresolved questions are ordered by their declared weight within each dimension. This orders gaps, not competitors by danger.")
    if result["gaps"].empty:
        st.success("All map cells are resolved under the current review and freshness policy. This does not establish complete knowledge of the market.")
    else:
        table(result["gaps"][["competitor", "dimension", "criterion", "weight_percent", "reason"]].round(1))
    with st.expander("See every coded cell and its linked evidence"):
        table(result["cells"].round(1))


def response_lab():
    sig.header("AWARENESS → MOTIVATION → CAPABILITY", "How could the rival respond?",
               "Compare alternative hypotheses, evidence against them and the signals that would change your plan.")
    data = project()["data"]
    names = {c["id"]: c["name"] for c in data["competitors"]}
    selected = st.selectbox("Rival", list(names), format_func=names.get, key=k("response_rival"))
    hypotheses = [r for r in data["responses"] if r["competitor_id"] == selected]
    st.text("Our proposed move: " + data["brief"]["decision"])
    if len(hypotheses) < 2:
        st.info("Add at least two plausible alternatives for this rival. Consider no immediate response, not only an aggressive reaction.")
    shown = limits.DISPLAY["hypotheses"]
    if len(hypotheses) > shown:
        st.info(f"Showing the first {shown} of {len(hypotheses)} hypotheses for this rival. "
                "Edit any of them below; the printable brief and exports include all of them.")
    for response in hypotheses[:shown]:
        audit = response_audit(project(), response)
        with st.container(border=True):
            st.text(response["id"] + " · " + response["response"])
            for label in ["awareness", "motivation", "capability"]:
                st.markdown("**" + label.title() + "**")
                st.text(response[label] or "Not specified")
            left, right = st.columns(2)
            with left:
                st.markdown("**Supporting observations**")
                for claim_id in response["supporting_claim_ids"]:
                    claim = next(c for c in data["claims"] if c["id"] == claim_id)
                    st.text(claim_id + ": " + claim["statement"])
                    st.caption(claim_readiness(project(), claim)[1])
                if not response["supporting_claim_ids"]:
                    st.caption("None linked. This remains an unsupported hypothesis.")
            with right:
                st.markdown("**Counterevidence**")
                for claim_id in response["counter_claim_ids"]:
                    claim = next(c for c in data["claims"] if c["id"] == claim_id)
                    st.text(claim_id + ": " + claim["statement"])
                    st.caption(claim_readiness(project(), claim)[1])
                if not response["counter_claim_ids"]:
                    st.caption("None linked. Seek evidence that could make this story wrong.")
            st.markdown("**Observable signal to check**")
            st.text(response["watch_for"] or "Not specified")
            st.markdown("**Our contingency**")
            st.text(response["our_contingency"] or "Not specified")
            st.text(f"Owner: {response['owner'] or 'Unassigned'} · next check: {response['next_check'] or 'Unscheduled'}")
            if audit["check_due"]:
                st.warning("The next check is due as of this case's analysis date.")
            if audit["missing"]:
                st.caption("Still to define: " + ", ".join(audit["missing"]))
    st.caption("These are planning hypotheses, not ranked predictions. The app schedules no reminders and sends no messages.")
    with st.expander("Add or edit a response hypothesis", expanded=not hypotheses):
        options = ["New hypothesis"] + [r["id"] for r in hypotheses]
        chosen = st.selectbox("Response to edit", options, key=k("response_edit_pick:" + selected))
        current = next((r for r in hypotheses if r["id"] == chosen), {})
        form = "response_form:" + selected + ":" + chosen + ":" + revision()
        with st.form(k(form)):
            title = st.text_input("Possible competitor response", current.get("response", ""),
                                  max_chars=limits.chars("response"),
                                  key=k(form + ":response"))
            fields = {label: st.text_area(label.title(), current.get(label, ""), max_chars=limits.chars("reasoning"),
                                           key=k(form + ":" + label))
                      for label in ["awareness", "motivation", "capability"]}
            claim_ids = [c["id"] for c in data["claims"] if c["competitor_id"] == selected]
            support = st.multiselect("Supporting claim IDs", claim_ids, default=current.get("supporting_claim_ids", []),
                                     key=k(form + ":support"))
            counter = st.multiselect("Counterevidence claim IDs", claim_ids, default=current.get("counter_claim_ids", []),
                                     key=k(form + ":counter"))
            watch = st.text_area("Observable watch signal", current.get("watch_for", ""), max_chars=limits.chars("reasoning"),
                                 key=k(form + ":watch_for"))
            contingency = st.text_area("Our contingency", current.get("our_contingency", ""),
                                       max_chars=limits.chars("reasoning"),
                                       key=k(form + ":our_contingency"))
            owner = st.text_input("Responsible owner", current.get("owner", ""), max_chars=limits.chars("name"), key=k(form + ":owner"))
            next_check = st.text_input("Next check · YYYY-MM-DD, or leave blank", current.get("next_check") or "",
                                       key=k(form + ":next_check"))
            if st.form_submit_button("Save hypothesis", type="primary", key=k(form + ":save")):
                updated = deepcopy(project())
                if chosen == "New hypothesis":
                    used = {r["id"] for r in data["responses"]}
                    new_id = next(f"H{i}" for i in count(1) if f"H{i}" not in used)
                else:
                    new_id = chosen
                entry = {"id": new_id, "competitor_id": selected, "response": title, **fields,
                         "supporting_claim_ids": support, "counter_claim_ids": counter,
                         "watch_for": watch, "our_contingency": contingency, "owner": owner,
                         "next_check": next_check.strip() or None}
                updated["data"]["responses"] = [r for r in data["responses"] if r["id"] != new_id] + [entry]
                updated["data"] = validate_data(updated["data"])
                replace_project(updated)
                st.rerun()


def compare_export():
    sig.header("SAVE → COMPARE → SHARE", "Keep a traceable competitor brief.",
               "Save a project to resume its reviews. Export a printable brief or compare two research snapshots.")
    c1, c2, c3 = st.columns(3)
    c1.download_button("Save project JSON", project_bytes(project()), "rival-project.json", "application/json", key=k("save_project"))
    c2.download_button("Download printable brief", printable_html(project()), "rival-competitor-brief.html", "text/html", key=k("print_brief"))
    c3.download_button("Download evidence ZIP", evidence_pack(project()), "rival-evidence.zip", "application/zip", key=k("evidence_zip"))
    st.caption("Open the HTML brief in a browser and print or save it as PDF. The ZIP includes the loaded claims, sources, "
               "review notes, criteria, results, printable brief and academic references. No external assets are required.")
    st.caption("Project fingerprint: " + fingerprint(project()))
    if in_hub():
        sig.note("info", "**In Signal Hub, this project lives only in your browser session.** Nothing is saved on the "
                 "server. Download the project JSON to keep your reviews, then restore it here or in the local app.")
    with st.expander("Restore a saved project"):
        restore = st.file_uploader("Saved Rival project JSON", type=["json"], key=k("restore_upload"))
        st.write("This explicitly restores the review decisions in your file. It does not recheck the sources or authenticate who reviewed them.")
        if st.button("Restore project and its saved reviews", key=k("restore_project"), disabled=restore is None):
            restored = restore_project(restore.getvalue())
            replace_project(restored)
            st.session_state.pop(k("expected_contract"), None)
            st.rerun()
    st.subheader("Compare with an earlier snapshot")
    before = st.file_uploader("Earlier saved Rival project", type=["json"], key=k("compare_upload"))
    if before is not None:
        previous = restore_project(before.getvalue())
        diff = compare_projects(previous, project())
        st.text(f"Previous: {previous['data']['brief']['focal_company']} · as of {previous['data']['brief']['as_of']}")
        if diff["changes"].empty:
            st.info("No research records, reviews, scope or policy changes were found.")
        else:
            table(diff["changes"])
        if diff["comparable"]:
            st.markdown("**Change in coding bounds · percentage points**")
            table(diff["deltas"].round(1))
        else:
            st.warning("The brief, competitor definitions, criteria, weights or freshness policy changed. Numerical profile changes are withheld because the basis differs.")
        st.caption("Added or changed records are changes in your evidence file, not verified market events. "
                   "Profile ranges can change because of reviews or aging evidence without any real change at a competitor.")
    else:
        st.info("Save this project, update your research or reviews, then upload the earlier file here to see what changed.")


def research_limits():
    sig.header("ACADEMIC BASIS & IMPLEMENTATION", "The theory behind the questions.",
               "Four academic references support the scope; a separate AI sourcing study informs the review workflow.")
    st.subheader("What is implemented")
    st.write("The unit of analysis is a focal company–competitor pair in a declared market and decision context. "
             "Users define market and resource criteria, then review observations and code each criterion yes, no or unknown.")
    st.latex(r"L_d = 100\frac{\sum_{i\in reviewed\ yes}w_i}{\sum_{i\in d}w_i},\qquad U_d = L_d + 100\frac{\sum_{i\in unresolved}w_i}{\sum_{i\in d}w_i}")
    st.write("Weights are normalized separately within each dimension. Unreviewed assessments, rejected claims, "
             "inferences, missing dates and old evidence leave the cell unresolved. Every linked observation must be eligible. "
             "Confirmed no lowers the upper bound; simply finding no evidence does not.")
    sig.note("warn", "**These are custom descriptive proxies.** Neither the coding nor the weighting reproduces "
             "a validated academic instrument. The map is not a calibrated threat model, causal analysis or prediction of response.")
    st.subheader("Research references")
    for source in SOURCES:
        st.markdown(f"**[{source['title']}]({source['url']})**  \n{source['authors']} · {source['year']}")
        st.caption(source["basis"])
        st.write(source["finding"])
        st.write("In Rival Signal: " + source["application"])
        if source.get("access"):
            st.link_button("Open author or university record", source["access"], key=k("source:" + str(source["year"])))
        st.divider()
    st.subheader("How this differs from existing apps")
    table(pd.DataFrame(SCOPE, columns=["App", "Existing scope", "Boundary"]))
    st.subheader("Limits to keep beside the output")
    for item in LIMITS:
        st.markdown("- " + item)
    if limits.public():
        d = limits.DEMO
        st.caption(f"Public demo limits: UTF-8 JSON up to {d['json_mb']} MB and pasted replies up to "
                   f"{d['paste_chars']:,} characters; at most {d['competitors']} competitors, {d['criteria']} criteria, "
                   f"{d['sources']} sources, {d['claims']} claims and {d['responses']} hypotheses. "
                   "The downloaded app has none of these limits.")
    else:
        st.caption("Inputs: UTF-8 JSON with no size, record or text-length limit; your computer's memory is the limit.")
    st.caption("Everything stays in session memory until you explicitly download a file. There is no automatic persistence.")


PAGES = {"Overview": overview, "1 · Brief & AI prompt": brief_and_prompt, "2 · Import & review": review,
         "3 · Rival map": rival_map, "4 · Response lab": response_lab,
         "5 · Compare & export": compare_export, "Research & limits": research_limits}


def render():
    sig.apply(NS)
    if k("project") not in st.session_state:
        st.session_state[k("project")] = demo_project()
        st.session_state[k("revision")] = 0
    sig.sidebar_brand(NS, "Competitor evidence. Better response questions.")
    with st.sidebar:
        page = st.radio("Navigate", list(PAGES), label_visibility="collapsed", key=k("page"))
        st.divider()
        st.caption("BRING YOUR OWN AI")
        st.write("Copy a prompt. Return with evidence.")
        st.caption("No API key · no AI calls · source review")
        if st.button("Reset to fictional demo", key=k("demo_reset")):
            replace_project(demo_project())
            st.session_state.pop(k("expected_contract"), None)
            st.rerun()
    sig.masthead(NS, ["Trace the source", "Keep the unknowns", "Challenge the response"], "RESEARCH → RIVALS → RESPONSES")
    st.text(project()["provenance"])
    try:
        PAGES[page]()
    except DataProblem as exc:
        st.error(str(exc))
    except MemoryError:
        st.error(limits.MEMORY_MESSAGE)
    sig.footer(NS, __version__, "competitive reasoning, with evidence in view")
