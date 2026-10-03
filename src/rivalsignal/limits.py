"""Data limits, all in one place (Signal app contract, section 9).

Run locally (standalone, a local Hub or an internal deployment), Rival Signal imposes no limits on file size,
records, text length or pasted text: the computer is the limit. A public demo sets SIGNAL_PUBLIC=1, and only then
do the hard caps below apply, to protect a shared server from large inputs and long pasted text.

Value ranges that belong to the method (positive weights up to 1,000, a 1–1,095-day horizon, a 1–3,650-day evidence
age limit) and the identifier format live in schema.py; they are not data-size limits.
"""
from __future__ import annotations

import os

# Public-demo caps. None of these apply locally.
DEMO = {
    "json_mb": 10,                  # uploaded or pasted JSON, in MB
    "paste_chars": 1_000_000,       # the AI-reply text box
    "source_material_chars": 25_000,  # optional source material added to the research prompt
    "repair_chars": 100_000,        # failed reply quoted in the repair prompt
    "repair_error_chars": 8_000,    # validation errors quoted in the repair prompt
    "criteria": 24,
    "competitors": 12,
    "sources": 100,
    "claims": 300,
    "assessments": 288,             # competitors x criteria
    "responses": 36,
    "refs": 20,                     # source or claim IDs cited by one record
}

# Public-demo text-field lengths, in characters.
TEXT = {
    "name": 120,          # focal company, criterion label, competitor name, owner, reviewer
    "paragraph": 600,     # market, criterion definition, competitor description
    "decision": 1000,
    "title": 300,
    "url": 2000,
    "publisher": 150,
    "origin_group": 100,
    "statement": 1500,    # claim statement, review note
    "response": 400,
    "reasoning": 1200,    # rationale, awareness, motivation, capability, watch signal, contingency
    "provenance": 200,
}

# On-screen only: crowded views are shortened with a note; analysis and exports always use everything.
DISPLAY = {"map_rivals": 25, "hypotheses": 25}

DEMO_NOTE = "This is a limit of the public demo; the downloaded app has none."
MEMORY_MESSAGE = ("There is not enough memory on this computer for this input. Close other programs or split the "
                  "case into smaller ones, then try again.")


def public() -> bool:
    """True only for a public demo deployment."""
    return os.environ.get("SIGNAL_PUBLIC") == "1"


def cap(name: str) -> int | None:
    """A public-demo cap, or None (no limit) when run locally."""
    return DEMO[name] if public() else None


def chars(field: str) -> int | None:
    """A public-demo text-field length, or None when run locally."""
    return TEXT[field] if public() else None


def clip(text: str, name: str) -> str:
    """Shorten text to a public-demo cap; unchanged locally."""
    limit = cap(name)
    return text if limit is None else text[:limit]
