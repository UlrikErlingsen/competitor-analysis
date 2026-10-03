# Data guide

Rival Signal reads one kind of input: a UTF-8 JSON object describing one competitor case. It arrives in two forms.

- A **research draft** is what your AI assistant (or your own desk research) returns from the research prompt. Importing it never carries review decisions; every claim and cell starts unreviewed.
- A **saved project** is what the app downloads from **5 · Compare & export**. It wraps the same research with your reviews, the evidence age limit and a provenance label, and restoring it brings those reviews back.

The app's **1 · Brief & AI prompt** page downloads the exact prompt and the JSON schema (`rival-research.schema.json`). **2 · Import & review** downloads a complete fictional reply to practise with.

## Size limits

- Uploaded files: 50 MB (the local upload cap; `RIVALSIGNAL_MAX_UPLOAD_MB` changes it in the launchers). The parser applies the same 50 MB limit to pasted text and uploads.
- Pasted replies: 1,000,000 characters. A browser text box is not a good place for more; upload the file instead.
- Records: 2–24 criteria (at least one market and one resource criterion), 1–12 competitors, 100 sources, 300 claims, 288 assessments (12 × 24) and 36 response hypotheses. A file with more records is rejected straight away with the count.
- Text fields have length limits (for example 1,500 characters for a claim statement and 2,000 for a URL); the schema lists every one.
- In the prompt, optional source material you add is cut at 25,000 characters. The repair prompt includes the first 100,000 characters of the failed reply and the first 8,000 characters of the error list. These keep the prompts within what assistants accept; they do not limit what the app can import.

A typical reply is tens of kilobytes; the fictional demo is about 15 KB. The record limits, not the byte cap, are what keep a case small: every claim and cell needs a human check.

## Research draft

Top-level keys, all required, no others allowed:

```json
{
  "schema_version": "1.0",
  "brief": {...},
  "criteria": [...],
  "competitors": [...],
  "sources": [...],
  "claims": [...],
  "assessments": [...],
  "responses": [...]
}
```

Use `[]` for an empty collection and `null` for an unknown optional date. Every record key is required; extra keys such as `verified`, `confidence` or `review_status` are rejected.

**IDs** start with a letter, then letters, digits, `_` or `-`, at most 40 characters, unique within their collection. **Dates** are `YYYY-MM-DD`.

### `brief`

| Field | Meaning |
|---|---|
| `focal_company` | Your company or offering (up to 120 characters) |
| `market` | Customer need, geography and market boundary |
| `decision` | The move you are considering |
| `as_of` | Evidence cutoff: nothing may be observed or accessed after it |
| `horizon_days` | Response horizon, 1–1,095 days |

### `criteria`

| Field | Meaning |
|---|---|
| `id` | e.g. `M1`, `R1` |
| `dimension` | `market` (a market you serve) or `resource` (a capability you have) |
| `label`, `definition` | Short name and what counts as a match |
| `weight` | Positive, finite, at most 1,000. Normalised within its dimension |

### `competitors`

`id`, `name` (distinct, ignoring case), `type` (`direct`, `indirect`, `potential`, `substitute`) and `description` (may be empty).

### `sources`

| Field | Meaning |
|---|---|
| `title`, `publisher` | As published |
| `url` | Public `http` or `https` link. Rejected: other schemes, embedded user names or passwords, `localhost`, `.local`, `.internal`, `.localhost`, private or reserved IP addresses, single-label host names, spaces, control characters and backslashes |
| `published_date` | Publication date, or `null` |
| `accessed_date` | When the source was actually inspected; no later than `as_of`, and not before `published_date` |
| `origin_group` | A declared family: reprints of one press release share it. This is a grouping you propose, not proof of independence |

The app never opens these links. It shows them as buttons for you to check, and marks the demo's `.example` URLs as fictional.

### `claims`

| Field | Meaning |
|---|---|
| `competitor_id` | The rival the claim is about |
| `kind` | `observation` (something a source shows) or `inference` (an interpretation) |
| `topic` | `market`, `resource`, `move` or `other` |
| `statement` | In your own words, not a long quotation |
| `observed_date` | When the underlying event or evidence happened, not when it was retrieved; `null` if unknown; never after `as_of`. A future plan is an announcement dated when it was announced |
| `source_ids` | Up to 20 sources. An observation needs at least one |

### `assessments`

One per rival × criterion: `competitor_id`, `criterion_id`, `judgment` (`yes`, `no`, `unknown`), `claim_ids` (claims about the same rival) and `rationale`. A missing row is treated as unknown, and **Add missing assessment rows as unknown** fills the grid for manual coding.

Coding rules from the prompt: market "yes" needs demonstrated participation in the defined customer, need and geography; resource "yes" needs a demonstrated, functionally comparable capability. "No" needs explicit evidence of exclusion or difference. No evidence means unknown.

### `responses`

`competitor_id`, `response` (the hypothesis), `awareness`, `motivation`, `capability`, `supporting_claim_ids`, `counter_claim_ids` (claims about the same rival; a claim cannot be in both lists), `watch_for`, `our_contingency`, `owner` and `next_check` (a date or `null`). Text fields may be empty; the app lists what is still undefined.

## What gets rejected

The app explains the first problems it finds and offers a repair prompt. A draft is rejected when:

- it is not a single JSON object (prose around it, a list, `NaN` or `Infinity`), or a key appears twice in one object; a Markdown code fence around the JSON is accepted;
- a field is missing, has the wrong type or length, or an extra field is present;
- IDs repeat, competitor names repeat, or a brief field is blank;
- the criteria do not include both a market and a resource criterion;
- a claim cites an unknown source or rival, an observation has no source, or evidence is dated after `as_of`;
- a source was accessed after `as_of` or published after it was accessed, or its URL is not a safe public link;
- an assessment refers to an unknown rival or criterion, is duplicated, or links a claim about another rival;
- a response links unknown claims, claims about another rival, or the same claim as support and counterevidence;
- you started a case from your own brief in this session and the reply changed the brief, criteria or rivals.

Passing validation means the structure and references are consistent. It says nothing about whether the claims are true.

## Saved project

```json
{
  "format": "rivalsignal-project-v1",
  "data": { ...research draft... },
  "reviews": {
    "claims": {"E1": {"status": "accepted", "reviewer": "...", "note": "...", "checked_on": "2026-10-03"}},
    "assessments": {"C1/M1": {...}}
  },
  "policy": {"max_age_days": 180},
  "provenance": "..."
}
```

Review statuses are `pending`, `accepted` or `rejected`. An accepted review needs a reviewer name (up to 120 characters) and a note (up to 1,500) saying what was checked. Assessment reviews are keyed `competitor_id/criterion_id`. The age limit is 1–3,650 days. The review date is set by the app from today's date in Norwegian time.

Restoring checks the format, the research, every review and that each review refers to an existing record. It does not recheck sources or authenticate who reviewed them. Feeding a saved project into the research import is refused, so reviews cannot slip in through the AI route.

## Before you research

- Write criteria that describe *your* markets and capabilities, one idea each, with a definition a reviewer can apply.
- Include indirect rivals, likely entrants and substitutes (including "do nothing" or a manual workaround) where customers could choose them.
- Set the as-of date to the day research ends, and choose an age limit that fits how fast the market moves.
- If your assistant cannot browse, add the sources yourself in the prompt's source box and expect most cells to stay unknown.
