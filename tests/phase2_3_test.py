"""
tests/phase2_3_test.py - Phase 2 (folder upload, per-file analysis, issues) and Phase 3 (AI) checks.
Run:  python tests/phase2_3_test.py     (temporary database; no internet or API key needed)
"""
import io, json, os, re, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import config
tmp = tempfile.mkdtemp()
config.DB_PATH = os.path.join(tmp, "t.db")
config.UPLOAD_DIR = os.path.join(tmp, "uploads")
import file_service
file_service.UPLOAD_DIR = config.UPLOAD_DIR
from app import app
from models import db, Bug, Issue, CodeFile, ChatMessage, BugComment, User
import urllib.error
from ai.provider import GeminiProvider, AIError
import ai_views

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + config.DB_PATH
FAILS = []


def check(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name + (" " + str(extra) if (extra and not cond) else ""))
    if not cond:
        FAILS.append(name)


def tok(h):
    m = re.search(r'name="csrf_token" value="([^"]+)"', h)
    return m.group(1) if m else None


with app.app_context():
    db.drop_all(); db.create_all()
c = app.test_client()
t = tok(c.get("/register").get_data(as_text=True))
c.post("/register", data=dict(csrf_token=t, username="boss", password="password1", password2="password1"))
t = tok(c.get("/").get_data(as_text=True))
c.post("/project/new", data=dict(csrf_token=t, name="Multi")); pid = 1

PY = "import os\n\ndef f(a):\n    '''doc'''\n    if a and a > 1:\n        return eval(str(a))\n    return os.getcwd()\n"
JAVA = "public class A {\n  // adds\n  public int add(int a, int b) { if (a > b && b > 0) { return a; } return b; }\n  void q(String u){ String s = \"SELECT * FROM t WHERE id=\" + u; }\n}\n"
JS = "// util\nfunction go(x){ if (x) { el.innerHTML = x; } return eval(x); }\nvar password = 'secret123';\n"
C = "#include <stdio.h>\nint main(void) { char b[8]; gets(b); return 0; }\n"
CPP = "#include <iostream>\nclass B { public: int v() { return 1; } };\nint main() { for (int i=0;i<2;i++) { if (i) {} } return 0; }\n"


def post_upload(files, pid=pid):
    t = tok(c.get(f"/project/{pid}/upload").get_data(as_text=True))
    data = {"csrf_token": t, "source_files": [], "paths": []}
    for path, content in files:
        data["source_files"].append((io.BytesIO(content if isinstance(content, bytes) else content.encode()), os.path.basename(path)))
        data["paths"].append(path)
    return c.post(f"/project/{pid}/upload", data=data, content_type="multipart/form-data",
                  headers={"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"})


big = b"x = 1\n" * 400000                      # ~2.4 MB -> skipped
files = [("proj/src/main.py", PY), ("proj/src/Util.java", JAVA), ("proj/web/app.js", JS), ("proj/native/m.c", C),
         ("proj/native/n.cpp", CPP), ("proj/venv/lib/x.py", PY), ("proj/node_modules/a/b.js", JS), ("proj/.git/hooks/h.py", PY),
         ("proj/logo.png", b"\x89PNG\x00\x00"), ("proj/bin_as_py.py", b"abc\x00def"), ("proj/big.py", big),
         ("proj/dist/min.js", JS), ("proj/web/lib.min.js", JS), ("proj/readme.md", "# hi"), ("../evil.py", PY),
         ("C:/win/evil.py", PY), ("/abs/evil.py", PY), ("proj/root.py", PY)]
r = post_upload(files)
j = r.get_json()
check("mixed folder upload 200", r.status_code == 200 and j["accepted"] == 6, j)
check("junk skipped with summary", "venv" in j["message"] and "node_modules" in j["message"] and "binary" in j["message"], j["message"])
check("unsafe paths blocked", j["skipped"].get("unsafe path") == 3, j["skipped"])
check("too-large skipped", any("too large" in k for k in j["skipped"]), j["skipped"])
with app.app_context():
    paths = sorted(f.relpath for f in CodeFile.query.all())
    check("sub-folders preserved", "proj/src/main.py" in paths and "proj/native/m.c" in paths, paths)
    check("files stored on disk under uploads/<pid>/", os.path.exists(os.path.join(config.UPLOAD_DIR, "1", "proj", "src", "main.py")))
    check("no file escaped upload dir", not os.path.exists(os.path.join(tmp, "evil.py")))
    langs = {f.relpath: f.language for f in CodeFile.query.all()}
    check("languages detected", langs["proj/src/Util.java"] == "Java" and langs["proj/web/app.js"] == "JavaScript"
          and langs["proj/native/m.c"] == "C" and langs["proj/native/n.cpp"] == "C++")
    check("basic flag", CodeFile.query.filter_by(relpath="proj/web/app.js").first().basic_metrics is True
          and CodeFile.query.filter_by(relpath="proj/src/main.py").first().basic_metrics is False)
    check("issues stored", Issue.query.count() >= 8, Issue.query.count())
    types = {i.issue_type for i in Issue.query.all()}
    check("security rules per language", {"Use of eval()", "Use of gets()", "SQL string concatenation", "Hardcoded password/secret"} <= types, types)

# replace same path
before = None
with app.app_context():
    before = CodeFile.query.count()
post_upload([("proj/src/main.py", PY + "\n# changed\n")])
with app.app_context():
    check("same path replaces old copy", CodeFile.query.count() == before)

# > 50 files
many = [(f"many/f{i}.py", PY) for i in range(51)]
r = post_upload(many)
check(">50 files rejected with friendly message", r.status_code == 400 and "limit is 50" in r.get_json()["message"], r.get_json())
with app.app_context():
    check("nothing from rejected batch saved", CodeFile.query.filter(CodeFile.relpath.like("many/%")).count() == 0)

# pages with code, per-file selector
with app.app_context():
    fid = CodeFile.query.filter_by(relpath="proj/src/main.py").first().id
    jid = CodeFile.query.filter_by(relpath="proj/src/Util.java").first().id
SC = ["size", "complexity", "quality", "statistics", "correlation", "boxplot", "decision-tree", "defect-prediction",
      "risk-prediction", "security", "maintainability"]
for p in SC:
    r1 = c.get(f"/project/{pid}/{p}"); r2 = c.get(f"/project/{pid}/{p}?file={fid}"); r3 = c.get(f"/project/{pid}/{p}?file=99999")
    check(f"{p}: all / one file / bad file id", r1.status_code == r2.status_code == r3.status_code == 200, (r1.status_code, r2.status_code, r3.status_code))
h = c.get(f"/project/{pid}/size?file={fid}").get_data(as_text=True)
check("file selector shown & no-bugs note", "Analyse:" in h and "no bugs linked to this file" in h)
from analysis_service import run_full_code_analysis
with app.app_context():
    allr = run_full_code_analysis(pid); one = run_full_code_analysis(pid, fid)
    check("one file differs from all", one["size"]["num_files"] == 1 and allr["size"]["num_files"] == 6, (one["size"]["num_files"], allr["size"]["num_files"]))
    check("all == sum of files", allr["size"]["total_loc"] == sum(run_full_code_analysis(pid, f.id)["size"]["total_loc"] for f in CodeFile.query.filter_by(project_id=pid)))

for p in ("files", "issues", "project-metrics", "project-metrics?depth=2", f"file/{fid}", f"file/{jid}", "dashboard", "report"):
    r = c.get(f"/project/{pid}/{p}"); check(f"page {p}", r.status_code == 200, r.status_code)
h = c.get(f"/project/{pid}/dashboard").get_data(as_text=True)
check("dashboard: verdict with file count, riskiest files, folders", "files are High risk" in h and "riskiest files" in h and "Sub-folder comparison" in h)
h = c.get(f"/project/{pid}/project-metrics").get_data(as_text=True)
check("project metrics groups sub-folders", "src" in h and "native" in h and "(root)" in h)
h = c.get(f"/project/{pid}/file/{fid}").get_data(as_text=True)
check("file detail: source viewer + issues", 'id="L6"' in h and "issue-line" in h)
r = c.get(f"/project/{pid}/issues?severity=High&category=Security&q=eval"); check("issue filters", r.status_code == 200 and b"eval" in r.data)
r = c.get(f"/project/{pid}/issues/export.csv"); check("csv export", r.status_code == 200 and r.data.startswith(b"file,line"))
r = c.get(f"/project/{pid}/issues/export.json"); check("json export", r.status_code == 200 and isinstance(json.loads(r.data), list))

# log as bug
with app.app_context():
    iss = Issue.query.filter_by(issue_type="Use of eval()").first(); iid = iss.id
t = tok(c.get(f"/project/{pid}/issues").get_data(as_text=True))
c.post(f"/project/{pid}/issues/{iid}/log-bug", data=dict(csrf_token=t))
with app.app_context():
    iss = db.session.get(Issue, iid); b = db.session.get(Bug, iss.logged_bug_id)
    check("log-as-bug creates linked bug", b is not None and b.code_file_id == iss.code_file_id and b.source_issue_id == iid
          and "Use of eval()" in b.title and b.severity == "High", b and b.title)
    check("module is the folder", b.module in ("proj/src", "proj/web"), b.module)
    n_bugs = Bug.query.count()
c.post(f"/project/{pid}/issues/{iid}/log-bug", data=dict(csrf_token=t))
with app.app_context():
    check("no duplicate bug on second click", Bug.query.count() == n_bugs)
h = c.get(f"/project/{pid}/issues").get_data(as_text=True)
check("button turns into 'Logged as bug #N'", f"Logged as bug #{b.id}" in h)
c.post(f"/project/{pid}/issues/log-high", data=dict(csrf_token=t))
with app.app_context():
    hi = Issue.query.filter_by(severity="High").all()
    check("bulk log High issues", all(i.logged_bug_id for i in hi) and Bug.query.count() == n_bugs + len([i for i in hi if i.id != iid]))
# per-file defect density uses only linked bugs
with app.app_context():
    one = run_full_code_analysis(pid, iss.code_file_id)
h = c.get(f"/project/{pid}/size?file={iss.code_file_id}").get_data(as_text=True)
check("selector hides 'no bugs' note when bugs are linked", "no bugs linked to this file" not in h)
# re-analyse keeps logged issues
t = tok(c.get(f"/project/{pid}/files").get_data(as_text=True))
c.post(f"/project/{pid}/files/reanalyze", data=dict(csrf_token=t))
with app.app_context():
    check("re-analyse keeps 'logged' links, no duplicates", db.session.get(Issue, iid).logged_bug_id == b.id
          and Issue.query.filter_by(issue_type="Use of eval()", code_file_id=iss.code_file_id).count() == 1)

# API file endpoints
with app.app_context():
    token = User.query.first().api_token
H = {"Authorization": "Bearer " + token}
a = app.test_client()
r = a.get(f"/api/v1/projects/{pid}/files", headers=H); check("API files", r.status_code == 200 and len(r.json["data"]) == 6)
r = a.get(f"/api/v1/projects/{pid}/files/{fid}/metrics", headers=H); check("API file metrics", r.status_code == 200 and "function_details" in r.json["data"] and "issues" in r.json["data"])
r = a.get(f"/api/v1/projects/{pid}/files/99999/metrics", headers=H); check("API file 404", r.status_code == 404)
r = a.get(f"/api/v1/projects/{pid}/metrics", headers=H); check("API metrics has riskiest files", r.status_code == 200 and "riskiest_files" in r.json["data"])

# delete a file
t = tok(c.get(f"/project/{pid}/files").get_data(as_text=True))
c.post(f"/project/{pid}/file/{jid}/delete", data=dict(csrf_token=t))
with app.app_context():
    check("file deleted", db.session.get(CodeFile, jid) is None)

# 413 friendly
app.config["MAX_CONTENT_LENGTH"] = 1000
t = tok(c.get(f"/project/{pid}/upload").get_data(as_text=True))
r = c.post(f"/project/{pid}/upload", data={"csrf_token": t, "source_files": (io.BytesIO(b"x" * 5000), "a.py"), "paths": "a.py"},
           content_type="multipart/form-data", headers={"X-Requested-With": "XMLHttpRequest"})
check("oversize upload -> friendly JSON 413", r.status_code == 413 and "Remove some files" in r.get_json()["message"], r.status_code)
app.config["MAX_CONTENT_LENGTH"] = config.MAX_UPLOAD_BYTES

# ------------------------------------------------------------ Phase 3: AI
os.environ.pop("GEMINI_API_KEY", None)
H2 = {"X-CSRF-Token": tok(c.get(f"/project/{pid}/ai").get_data(as_text=True)), "Content-Type": "application/json"}
r = c.get(f"/project/{pid}/ai"); check("AI page w/o key shows setup steps", r.status_code == 200 and b"not set up yet" in r.data)
r = c.post(f"/project/{pid}/ai/chat", headers=H2, data=json.dumps({"message": "which module is riskiest?"}))
check("chat w/o key -> friendly message, 200", r.status_code == 200 and r.json["ok"] is False and r.json["kind"] == "no_key" and "GEMINI_API_KEY" in r.json["message"])
r = c.post(f"/project/{pid}/ai/chat", headers=H2, data=json.dumps({"message": ""})); check("empty question 400", r.status_code == 400)
r = c.post(f"/project/{pid}/ai/recommend", headers=H2, data="{}"); check("recommend w/o key -> fallback note", r.json["ok"] is False and "rule-based" in r.json["fallback_note"])

captured = {}
def fake_post(self, url, payload, headers):
    captured["payload"], captured["headers"], captured["url"] = payload, headers, url
    return {"candidates": [{"content": {"parts": [{"text": "**Likely root cause** test answer"}]}}]}
GeminiProvider._post = fake_post
os.environ["GEMINI_API_KEY"] = "fake-key"
r = c.post(f"/project/{pid}/ai/chat", headers=H2, data=json.dumps({"message": "which module is riskiest?"}))
check("chat with key returns answer", r.json["ok"] and "root cause" in r.json["answer"], r.json)
sysprompt = captured["payload"]["system_instruction"]["parts"][0]["text"]
check("system context has real project numbers", '"top_10_riskiest_files"' in sysprompt and '"escape_rate_percent"' in sysprompt and "Multi" in sysprompt)
check("key sent in header only, not in page", captured["headers"]["x-goog-api-key"] == "fake-key" and "fake-key" not in c.get(f"/project/{pid}/ai").get_data(as_text=True))
with app.app_context():
    check("chat history stored", ChatMessage.query.count() == 2)
r = c.post(f"/project/{pid}/ai/recommend", headers=H2, data="{}"); check("recommendations ok", r.json["ok"])
with app.app_context():
    bid = Bug.query.first().id
r = c.post(f"/project/{pid}/bugs/{bid}/ask-ai", headers=H2, data="{}"); check("ask AI on bug", r.json["ok"])
check("bug context sent", "Bug title:" in captured["payload"]["contents"][0]["parts"][0]["text"] and "File:" in captured["payload"]["contents"][0]["parts"][0]["text"])
r = c.post(f"/project/{pid}/bugs/{bid}/comments", headers=H2, data=json.dumps({"text": "AI suggestion: x", "source": "ai"}))
with app.app_context():
    check("save AI answer as comment", r.json["ok"] and BugComment.query.count() == 1)
check("comment shown on edit page", b"AI suggestion" in c.get(f"/project/{pid}/bugs/{bid}/edit").data)
for pth in ("alerts", "report"):
    h = c.get(f"/project/{pid}/{pth}").get_data(as_text=True)
    check(f"{pth}: AI button + rule-based tips visible", "Get AI recommendations" in h and "Rule-based tips" in h)

# error handling
def boom(exc):
    def f(self, url, payload, headers): raise exc
    return f
tests = [("429", urllib.error.HTTPError("u", 429, "x", {}, None), "rate_limit"),
         ("403", urllib.error.HTTPError("u", 403, "x", {}, None), "bad_key"),
         ("no internet", urllib.error.URLError("down"), "no_internet"), ("timeout", TimeoutError(), "timeout")]
for name, exc, kind in tests:
    GeminiProvider._post = boom(exc)
    r = c.post(f"/project/{pid}/ai/chat", headers=H2, data=json.dumps({"message": "hi"}))
    check(f"AI error handled: {name}", r.status_code == 200 and r.json["kind"] == kind, r.json)
GeminiProvider._post = lambda self, u, p, h: {"candidates": []}
r = c.post(f"/project/{pid}/ai/chat", headers=H2, data=json.dumps({"message": "hi"})); check("AI empty answer handled", r.json["kind"] == "empty")

print("\n%d failure(s)" % len(FAILS)); sys.exit(1 if FAILS else 0)
