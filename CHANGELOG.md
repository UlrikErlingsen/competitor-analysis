# Changelog

All notable changes to Rival Signal are documented here.

## [1.1.0] - 2026-10-03

### Changed

- **No data limits when run locally.** No maximum file size, number of rivals, criteria, sources, claims, assessments or hypotheses, text length or pasted text; the computer is the limit. The downloadable schema and the research prompt drop the length and count limits accordingly, the prompt keeps all added source material, and the repair prompt quotes the whole failed reply.
- **Hard caps only in a public demo** (`SIGNAL_PUBLIC=1`), all defined in the new `rivalsignal.limits`: 10 MB of JSON, 1,000,000 pasted characters, 12 rivals, 24 criteria, 100 sources, 300 claims, 288 assessments, 36 hypotheses, 20 cited IDs per record and per-field text lengths. Messages say they are demo limits.
- Upload cap raised to 10,000 MB: `.streamlit/config.toml`, launcher default `RIVALSIGNAL_MAX_UPLOAD_MB=10000`, Docker `STREAMLIT_SERVER_MAX_UPLOAD_SIZE=10000`.
- Crowded screens are shortened with a note (map chart: first 25 rivals; response lab: first 25 hypotheses per rival); tables, analysis and exports keep everything.
- Running out of memory shows a plain message instead of an error trace.

### Fixed

- New hypothesis IDs are no longer limited to H1–H999.

## [1.0.0] - 2026-10-03

First public release.

### Added

- **Brief & AI prompt:** a research brief (focal company, market, planned move, as-of date, horizon) with 2–24 weighted market and resource criteria and 1–12 rivals, including indirect, potential and substitute rivals. Builds a copyable research prompt with an all-unknown skeleton and downloads it with the JSON schema. The app makes no AI calls.
- **Import & review:** strict import of a JSON research reply (JSON Schema draft 2020-12, cross-references, date order, safe public links, duplicate keys, scope drift against the user's brief), a repair prompt for failed replies, and human review of every claim and coding cell with reviewer, note and date. Imported research always starts unreviewed.
- Evidence eligibility rules: only accepted, sourced, dated observations within the evidence age limit (180 days by default, measured from the observed date) can resolve a cell; inferences, stale, undated and unreviewed evidence stay unresolved.
- **Rival map:** market overlap × capability resemblance relative to the focal company, with per-dimension weight normalisation, lower and upper bounds for unresolved coding, and unresolved questions ordered by weight.
- **Response lab:** competing hypotheses with awareness, motivation and capability, supporting and counter observations, watch signals, contingencies, owners and next-check dates, with an audit of what is still undefined or due.
- **Compare & export:** saved-project JSON with reviews, restore, snapshot comparison that withholds numeric changes when the basis differs, a printable self-contained HTML brief, and a ZIP evidence pack with CSV tables, `method.json` and the project SHA-256. CSV text is neutralised against spreadsheet formulas.
- Research & limits page with verified references and interpretation boundaries; a fictional FjordDesk demo with reviewed, unknown, inferred and stale evidence.
- Signal Hub entry point `rivalsignal.ui.render()` with `APP_INFO`, `rival:`-namespaced keys and Hub mode (no file writes, no network calls, opens on the fictional demo, notes that the project lives in the browser session).
- JSON input up to 50 MB, matching the local upload cap; Windows and macOS launchers (port 8598, `RIVALSIGNAL_PORT`, `RIVALSIGNAL_MAX_UPLOAD_MB`), Dockerfile, `AI_ANALYST.md`, data guide, methods and sources documentation.
