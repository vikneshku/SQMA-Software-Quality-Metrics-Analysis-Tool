# CHANGES

## Phase 2 + 3 (this release)
### Phase 2 - folder upload and per-file analysis
- Upload page: Choose Project Folder, Choose Files, drag-and-drop folders (sub-folders kept), preview, progress bar, junk skipped in the browser AND on the server, summary "Accepted N files, skipped M (venv: .., binary: ..)". Limits 100 MB / 50 files / 2 MB per file in config.py; friendly message instead of a raw 413. Paths sanitised.
- `analyze_file()` is the single analysis path; project results are aggregations of file results. Per-file numbers cached on CodeFile (re-analyse buttons).
- Files page, Code Issues page (filters, CSV/JSON export, Log as bug, "Log all High issues"), Project Metrics page (totals, per-file table, sub-folder comparison 1 or 2 levels), File detail page (metrics, functions, chart, issues, source viewer with highlighted lines, previous/next).
- Java, JavaScript, C, C++ with basic metrics + security/issue rules (`analyzers/multi_lang.py`). Python issue rules by AST (too complex/long, too many parameters, deep nesting, missing docstring, bare except, unused import).
- "All files / one file" selector on every analysis page; bugs can be linked to files (per-file defect density uses only linked bugs). Dashboard: riskiest 10 files, sub-folder comparison, "N of M files are High risk" verdict.
- API: `/projects/<id>/files`, `/files/<file_id>/metrics`.
### Phase 3 - AI and documents
- `ai/provider.py` (Gemini via urllib), AI Assistant chat with stored history and a compact project summary as context, Ask AI on bugs with Save as comment, AI recommendations on Alerts and Report with rule-based fallback. Handles missing key, no internet, 429, timeouts, empty answers.
- `docs/PROJECT_DOCUMENTS.md`: report outline, 15-slide PPT text, timed demo-video script.
### Fixes found while testing
- Path sanitiser no longer strips the leading dot of `.git` / `.venv`; `.git` content is skipped correctly.
- Phase-1 databases are upgraded automatically (new CodeFile columns are added on start).
### Notes
- Only an Admin can delete a project. Static AI answers are never stored except in chat history and bug comments you save.

---

# CHANGES - Phase 1

## Added
- Login / register / logout (hashed passwords, Flask session, CSRF token on every POST). First user = Admin. Roles Admin / Developer / Tester. Users page (Admin manages), Profile page with API token.
- Bugs: description, edit page, 5 statuses, assignee, release, found-in (Testing/Production), OWASP category, CVSS score with live band badge, updated_at; filters, "My bugs", sortable list.
- Releases page (add/edit/delete; deleting un-tags bugs) with per-release counts, escape rate and Red/Yellow/Green readiness.
- Dashboard: verdict line, open:closed card, average age of OPEN bugs + count older than 30 days, escape rate, release readiness light, release comparison chart, sortable module risk table (open, Critical, High, avg CVSS).
- Alerts recomputed on every visit (source = bug/code/manual): aging bug, growing backlog, critical/high security bug, release turns Red.
- Hypothesis tests (scipy): Welch t-test, one-sample t-test (editable target), chi-square (module/release vs severity).
- Variance type (sample/population) and control-chart sigma (1/2/3) selectors, remembered in the session and printed on the Report.
- REST API /api/v1 (session or Bearer token). reset_db.py, tests/smoke_test.py.

## Changed
- Maintainability Index is now per file (avg function size + complexity), project = LOC-weighted; bands 55 / 40. Updated risk model (MI < 40), alerts, recommendations, Report and page legend.
- Defect prediction: removed duplicate module_size feature, balanced stratified synthetic data, class_weight balanced, hold-out accuracy and class counts shown.
- Escape rate = bugs found in Production / total (removed the manual "Escaped" checkbox).
- Average bug age uses open bugs only.
- Code-based pages show a shared "Upload your source code first" page when no code exists.
- requirements.txt pinned to Python 3.13 wheels; Query.get replaced by db.session.get / db.get_or_404.
- Only Admins can delete a project. Secret key is read from SQMA_SECRET_KEY or an auto-created .secret_key file.

## Not yet done (Phases 2 and 3)
Folder upload, per-file analysis, Code Issues / Project Metrics / file detail pages, multi-language analyzers, AI features, report/PPT/video text.

---
# What was changed (from UPDATIONS.docx)

Everything that already worked was kept. Only the issues listed in UPDATIONS.docx were corrected,
plus the bugs found while testing them.

## Your 6 requested items + the other issues in the document

| # | Section (UPDATIONS.docx) | What was wrong | What was done |
|---|---|---|---|
| 1 | **Box Plot** | Only numbers and a text line, no diagram | Real **box-and-whisker diagram** (box Q1-Q3, median line, whiskers, red outlier dots, dashed outlier fences, IQR arrow, labelled quartiles) like the reference image. Toggle: Complexity / Function size |
| 2 | **Control Chart** | Empty page: "No bug data yet" | It is **built from Bug Management** (bug date reported -> counted per day/week). Now drawn like the reference **X chart**: blue data line, **red UCL/LCL**, **green centre line**, red dot for out-of-control points. Per day / Per week buttons. If there is no data, the page explains why and offers a button to Bug Management and "Load demo bugs". Moved to **section 5**, right after Bug Management |
| 3 | **Correlation Analysis** | Only "r = 0.988 strong positive" in text | Added the **Positive / Zero / Negative reference diagram** with your project's case highlighted, a **scatter plot with trend line**, r squared, and the plain-English meaning |
| 4 | **Complexity Values (Histogram)** - Statistical Analysis | Blank box (and the old code drew one bar per function, which is not a histogram) | A true **histogram**: touching bars, class intervals (Sturges' rule), axis titles, frequency labels. Added one for function size too |
| 5 | **Decision Tree** | Class Probabilities and Feature Importance blank; only text rules | Both charts work. Added the **flowchart diagram** (root node, decision nodes, leaf nodes, Yes/No branches) with **your project's path highlighted in orange**, plus a step-by-step path list. Buttons: Actual size / Fit to screen |
| 6 | **Security Analysis** | Table only | Added the **database + padlock process diagram** (layers: High / Medium / Low / files scanned / rules applied; padlock open = High issues exist, closed = clean) and a findings-by-type chart |
| 7 | Home Dashboard | Severity and Quality Components charts blank | Fixed (see root cause below). Empty state now explains itself |
| 8 | Quality Metrics | Blank chart; quality label invisible | Fixed chart; fixed invisible `Good/Excellent/Poor` labels |
| 9 | Defect Prediction | Feature Importance blank | Fixed |
| 10 | Risk Prediction | Probabilities chart blank | Fixed |
| 11 | **Bug Management** | Doubt: is it connected to Control Chart? | **Yes.** Added a *Date reported* field so a time series can be built, a "Load demo bugs (28 days)" button, "Delete all", and a Reported column. Page now says which pages use the data |
| 12 | **Reports** | Needed the final graphs + clear rules and calculations | Report now contains **every graph** and, for each metric, a card with **Rule, Formula, Working (with this project's numbers), Result and the code file**. Prints cleanly to PDF |

## Root cause of the blank charts
Chart.js 4.x ships `chart.umd.js` only. The old page asked the CDN for `chart.umd.min.js`, which does not exist (404),
so the `Chart` object was undefined and **every** chart was blank. Chart.js, Bootstrap and Font Awesome are now
**bundled inside the project** (`static/js`, `static/vendor`) so the tool also works **without internet**.

## Other bugs found and fixed while testing
* **Server restarted on every upload** (Flask's auto-reloader treated each uploaded `.py` file as a code change and dropped the next request). Uploads folder is now excluded from the reloader.
* **Uploading the same file twice double-counted** its metrics. A re-upload now replaces the old copy.
* **Non-.py files were skipped silently.** Now a warning is shown. Oversized uploads (over 10 MB) now show a friendly message.
* **Decision Tree could never predict "Low"** (its training data had no Low examples, so a clean project was always Medium/High). Training data now covers Low / Medium / High; a clean project is rated Low, a risky one High.
* Missing badge colours (`Good`, `Warning`, `Info`, ...) made some labels invisible.
* Zero-valued bars (e.g. Defects = 0) were drawn with no label; they now show "0".
* Function size and complexity are now paired per function (correlation was pairing by list position).

## New / changed files
```
static/js/viz.js              shared graph library (all 10 graph types)
static/js/chart.umd.js        Chart.js 4.4.4 (local copy)
static/vendor/                Bootstrap 5.3.3 + Font Awesome 6.5.2 (local copies)
stats_engine/histogram.py     NEW  histogram binning (Sturges' rule)
stats_engine/boxplot.py       + whiskers, raw values
stats_engine/control_chart.py + mean, sigma
stats_engine/correlation.py   + trend line, r squared, direction
prediction/decision_tree.py   + tree structure and decision path for the flowchart; balanced training data
reports/report_generator.py   + worked calculation builder
app.py                        new routes (demo/clear bugs), daily control-chart series, report data
templates/                    bugs, control_chart, statistics, correlation, boxplot, decision_tree,
                              defect_prediction, risk_prediction, security, quality, dashboard, report, base
```
