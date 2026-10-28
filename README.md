# SQMA - Software Quality & Metrics Analysis Tool

A Flask web app that measures software quality from **source code** (size, complexity, maintainability, security issues) and from
**bug tracking** (defect density, escape rate, bug age, release readiness), then adds statistics, prediction models, alerts,
a REST API and optional AI help. Everything except the AI features works **offline**.

Languages: **Python** (full AST analysis) and **Java, JavaScript, C, C++** (basic metrics: lines, functions, classes, imports,
cyclomatic complexity, nesting, security rules).

---------------------------------------------------------------------------------------------------

## 1. Quick start (Python 3.13 recommended; 3.11+ works)

### Option A - VS Code
1. Unzip `SQMA_Tool_Complete.zip` and open the `sqma` folder in VS Code (**File > Open Folder**).
2. Open a terminal in VS Code (**Terminal > New Terminal**) and run:
   ```bash
   python -m venv venv
   # activate it:
   venv\Scripts\activate            # Windows (cmd or PowerShell)
   source venv/bin/activate         # macOS / Linux
   pip install -r requirements.txt
   python app.py
   ```
3. Open **http://127.0.0.1:5000** in the browser. Click **Register** - the **first account becomes Admin**.

### Option B - Windows cmd (or macOS/Linux terminal)
```bat
cd path\to\sqma
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python app.py
```
Shortcut: double-click `start.bat` (Windows) or run `./start.sh` (macOS/Linux) - they create the venv, install and start the app.

### Try it in 2 minutes
1. Register, create a project.
2. **Bug Management > Load demo bugs** (adds ~37 bugs and releases v1.0 / v1.1 / v1.2).
3. **Source Code Upload > Choose Project Folder** (or drag a folder in), then look at Dashboard, Code Issues, Project Metrics, Files.

### Reset the database
```bash
python reset_db.py          # asks for confirmation; add --yes to skip
```
Deletes ALL data (projects, bugs, users) and creates an empty database. (An older Phase-1 database is upgraded automatically; a
pre-Phase-1 database must be reset - the app tells you.)

### Run the self-tests
```bash
python tests/smoke_test.py       # login, bugs, releases, alerts, API, every page (temporary DB)
python tests/phase2_3_test.py    # folder upload, per-file analysis, issues, Log-as-bug, AI (mocked)
```

---------------------------------------------------------------------------------------------------

## 2. Pages (sidebar)
| # | Page | What it does |
|---|------|--------------|
| 1 | Home Dashboard | One-line verdict, quality, risk, open:closed, bug age, escape rate, release readiness, release comparison chart, module risk table, 10 riskiest files, sub-folder comparison, alerts |
| 2 | Goals (GQM) | Goal - Question - Metric view |
| 3 | Source Code Upload | Choose Project Folder / Choose Files / drag-and-drop a folder; junk skipped automatically; progress bar |
| 4 | Files | All files with lines, functions, complexity, maintainability, issues, risk colour; search, sort, re-analyse, delete |
| 5 | Code Issues | Issues from the code (security, complexity, maintainability, style) with filters, CSV/JSON export, **Log as bug** |
| 6 | Project Metrics | Totals, per-file table, sub-folder comparison (1 or 2 levels) |
| 7 | Bug Management | Add/edit bugs: description, assignee, release, found-in, OWASP, CVSS, linked file, comments, **Ask AI** |
| 8 | Releases | Per-release counts, escape rate, Red/Yellow/Green readiness |
| 9-20 | Control Chart, Software Size, Complexity, Quality, Statistical Analysis (+ t-tests, chi-square), Correlation, Box Plot, Decision Tree, Defect Prediction, Risk Prediction, Security, Maintainability | **Every analysis page has an "All files / one file" selector** |
| 21 | Alerts | Recomputed on each visit (aging, backlog, security, red release, code thresholds) + AI recommendations |
| 22 | AI Assistant | Chat about your project's real numbers (needs a free Gemini key) |
| 23 | Reports | Printable report with a Rule / Formula / Working / Result card per metric |
| 24 | Users | Admin adds/edits/deletes users; everyone sees roles and open-bug counts |

### Upload rules (all in `config.py`)
* 100 MB per upload, 50 useful files per upload (checked in the browser AND on the server), a single file over 2 MB is skipped.
* Skipped folders: `venv .venv env node_modules .git __pycache__ build dist .idea .vscode site-packages target bin obj`;
  binary files (known extensions or a NUL byte), minified `*.min.js`, unsupported types.
* Supported: `.py .java .js .c .h .cpp .cc .hpp`. Sub-folder structure is kept under `uploads/<project_id>/`.
  Uploading again adds new files and replaces files with the same path.
* Paths are sanitised (`..`, absolute paths and drive letters are rejected).

---------------------------------------------------------------------------------------------------

## 3. Roles and login
Admin, Developer, Tester. First registered user = Admin; later registrations = Developer (an Admin can change roles).
Passwords are hashed; forms are CSRF-protected; only an Admin can manage users or delete a project. Your API token is on **your name > Profile**.

## 4. REST API (`/api/v1`)
```bash
TOKEN=paste_token_here
curl -H "Authorization: Bearer $TOKEN" http://127.0.0.1:5000/api/v1/projects
curl -H "Authorization: Bearer $TOKEN" "http://127.0.0.1:5000/api/v1/projects/1/bugs?status=open&severity=High&page=1&per_page=20"
curl -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
     -d '{"title":"Login fails","severity":"High","owasp_category":"Broken Authentication","cvss_score":7.5,"found_in":"Production"}' \
     http://127.0.0.1:5000/api/v1/projects/1/bugs
curl -X PATCH  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{"status":"Resolved"}' http://127.0.0.1:5000/api/v1/projects/1/bugs/5
curl -X DELETE -H "Authorization: Bearer $TOKEN" http://127.0.0.1:5000/api/v1/projects/1/bugs/5
curl -H "Authorization: Bearer $TOKEN" http://127.0.0.1:5000/api/v1/projects/1/metrics
curl -H "Authorization: Bearer $TOKEN" http://127.0.0.1:5000/api/v1/projects/1/releases
curl -H "Authorization: Bearer $TOKEN" http://127.0.0.1:5000/api/v1/projects/1/files
curl -H "Authorization: Bearer $TOKEN" http://127.0.0.1:5000/api/v1/projects/1/files/3/metrics
curl -H "Authorization: Bearer $TOKEN" http://127.0.0.1:5000/api/v1/users        # Admin only
```
Replies are `{"data": ..., "error": null}`; errors are `{"data": null, "error": "...", "details": {...}}` with codes 200, 201, 400, 401, 403, 404.
No token = JSON 401. Browser-session writes must send `X-CSRF-Token`.
Endpoints: `GET /projects`, `GET /projects/<id>`, `GET|POST /projects/<id>/bugs`, `GET|PUT|PATCH|DELETE /projects/<id>/bugs/<bug_id>`,
`GET /projects/<id>/metrics`, `/releases`, `/files`, `/files/<file_id>/metrics`, `GET /users` (Admin).

---------------------------------------------------------------------------------------------------

## 5. AI features (optional, free Gemini key)
Used by: **AI Assistant** page, **Ask AI** on a bug (root cause, fix, test, prevention; "Save as comment"), and **Get AI recommendations** on
Alerts and Report. The rule-based tips are always shown as a backup ("AI unavailable - showing rule-based tips").

1. Get a free key: open **https://aistudio.google.com/apikey** and click *Create API key*.
2. Set it (then restart the app / open a NEW terminal):
   * Windows: `setx GEMINI_API_KEY "your-key-here"`   (PowerShell for one session: `$env:GEMINI_API_KEY="your-key-here"`)
   * macOS / Linux: `export GEMINI_API_KEY="your-key-here"`
   * Optional: `GEMINI_MODEL` (default `gemini-2.5-flash`, set another current Gemini Flash model if Google retires it).
3. Without a key the AI pages show these steps; nothing else is affected. No internet, a rate limit (429), a timeout or an empty
   answer each show a friendly message. The key stays on the server and is never sent to the browser.
The provider sits behind one class (`ai/provider.py`) so it can be swapped.

## 6. Key formulas (full worked cards are on the Report page)
* Cyclomatic complexity = 1 + decision points. Defect density = bugs / KLOC. Escape rate = bugs found in Production / total x 100.
* Open = Open, In Progress, Reopened; Closed = Resolved, Closed. Bug age counts open bugs only.
* Maintainability Index (per file) = max(0, min(100, (171 - 5.2 ln HV - 0.23 CC - 16.2 ln avgFnLOC) x 100 / 171)), HV = avgFnLOC x log2(12); project = LOC-weighted average. Bands: 55+ high, 40-54.9 moderate, below 40 difficult.
* CVSS bands: 0 None, 0.1-3.9 Low, 4-6.9 Medium, 7-8.9 High, 9-10 Critical.
* Release readiness: RED = open Critical, or 3+ open High, or open security bug CVSS >= 9; YELLOW = open High, or open > closed, or open bug > 30 days; else GREEN. (`config.READINESS`)
* Control chart: CL = mean, limits = mean +/- k sigma (k = 1, 2, 3; sample n-1 or population n).

## 7. Project layout
```
app.py                 analysis pages + wiring         auth.py       login, users, CSRF
bugs_views.py          bugs + releases                 files_views.py files, issues, file detail, project metrics
api.py                 REST API                        ai_views.py   AI chat / ask-AI / recommendations
config.py              ALL constants and thresholds    file_service.py upload, path safety, per-file cache, risk
bug_service.py         bug validation (pages + API)    alerts_engine.py recomputed alerts
analysis_service.py    aggregates analyze_file()       metrics_summary.py project-wide numbers
analyzers/             file_analyzer (analyze_file), python (ast), multi_lang, python_issues, security, ...
metrics/ stats_engine/ prediction/ bayesian/ reports/ ai/     templates/ static/ tests/ docs/
```
Documents for the project report, PPT and demo video: `docs/PROJECT_DOCUMENTS.md`.

## 8. Limitations
* Java/JS/C/C++ use regex + brace matching (no full parser); minified code and unusual formatting can confuse it.
* Defect prediction trains on **synthetic** rule-derived data (stated on the page); the Maintainability HV is a documented approximation.
* SQLite and the Flask dev server are meant for single-team / demo use.
