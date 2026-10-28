"""
tests/smoke_test.py - end-to-end check of Phase 1 (run:  python tests/smoke_test.py)
Uses a temporary database; your real sqma.db is not touched.
"""
import io, os, re, sys, tempfile, json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import config
tmp = tempfile.mkdtemp()
config.DB_PATH = os.path.join(tmp, "test.db")
config.UPLOAD_DIR = os.path.join(tmp, "uploads")
import app as appmod
from app import app
from models import db, User, Bug, Alert, Release

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + config.DB_PATH
FAILS = []


def check(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name + (" " + str(extra) if (extra and not cond) else ""))
    if not cond:
        FAILS.append(name)


def tok(html):
    m = re.search(r'name="csrf_token" value="([^"]+)"', html)
    return m.group(1) if m else None


c = app.test_client()
with app.app_context():
    db.drop_all(); db.create_all()

# --- auth
check("anonymous redirected to login", c.get("/").status_code == 302)
t = tok(c.get("/register").get_data(as_text=True))
r = c.post("/register", data=dict(csrf_token=t, username="admin", password="password1", password2="password1"))
check("first user registered", r.status_code == 302)
with app.app_context():
    check("first user is Admin", User.query.first().role == "Admin")
c2 = app.test_client()
t2 = tok(c2.get("/register").get_data(as_text=True))
c2.post("/register", data=dict(csrf_token=t2, username="dev1", password="password1", password2="password1"))
with app.app_context():
    check("second user is Developer", User.query.filter_by(username="dev1").first().role == "Developer")
r = c2.get("/users"); check("users page visible to developer", r.status_code == 200)
t2 = tok(r.get_data(as_text=True))
r = c2.post("/users/new", data=dict(csrf_token=t2, username="x1", password="password1", role="Tester"))
check("developer cannot add users (403)", r.status_code == 403)
c3 = app.test_client()
t3 = tok(c3.get("/login").get_data(as_text=True))
r = c3.post("/login", data=dict(csrf_token=t3, username="admin", password="WRONG"))
check("wrong password rejected", b"Wrong username or password" in r.data)
r = c3.post("/login", data=dict(csrf_token=t3, username="admin", password="password1"))
check("correct password logs in", r.status_code == 302)
t3 = tok(c3.get("/").get_data(as_text=True))
r = c3.post("/logout", data=dict(csrf_token=t3)); check("logout", r.status_code == 302)
t3 = tok(c3.get("/login").get_data(as_text=True))
r = c3.post("/login?next=//evil.com", data=dict(csrf_token=t3, username="admin", password="password1"))
check("open redirect blocked", "evil.com" not in (r.headers.get("Location") or ""))

# --- project, users
t = tok(c.get("/").get_data(as_text=True))
r = c.post("/project/new", data=dict(csrf_token=t, name="P1")); pid = 1
check("project created", r.status_code == 302)
r = c.get("/users"); t = tok(r.get_data(as_text=True))
c.post("/users/new", data=dict(csrf_token=t, username="tester1", password="password1", role="Tester", full_name="Tess Ter"))
with app.app_context():
    check("admin added tester", User.query.filter_by(username="tester1").count() == 1)

# --- sample code
CODE = '''
import os
def simple(a):
    return a + 1

def complex_fn(x, y):
    total = 0
    for i in range(x):
        if i % 2 == 0 and y > 1:
            total += i
        elif i % 3 == 0 or y < 0:
            total -= i
        else:
            try:
                total += eval("1+1")
            except ValueError:
                pass
    return total

password = "hunter22"
'''
r = c.get(f"/project/{pid}/upload"); t = tok(r.get_data(as_text=True))
r = c.post(f"/project/{pid}/upload", data=dict(csrf_token=t, source_files=(io.BytesIO(CODE.encode()), "sample.py")),
           content_type="multipart/form-data")
check("upload ok", r.status_code == 302)

# --- every page renders for a project with only code
PAGES = ["dashboard", "goals", "upload", "files", "issues", "project-metrics", "bugs", "releases", "control-chart", "size", "complexity", "quality",
         "statistics", "correlation", "boxplot", "decision-tree", "defect-prediction", "risk-prediction",
         "security", "maintainability", "alerts", "ai", "report"]
for p in PAGES:
    r = c.get(f"/project/{pid}/{p}")
    check(f"page {p} (code only)", r.status_code == 200, r.status_code)

# --- bugs
r = c.get(f"/project/{pid}/bugs"); t = tok(r.get_data(as_text=True))
r = c.post(f"/project/{pid}/bugs/demo", data=dict(csrf_token=t))
with app.app_context():
    nb = Bug.query.count(); nr = Release.query.count()
check("demo bugs created", nb > 30, nb); check("3 demo releases", nr == 3)
for p in PAGES:
    r = c.get(f"/project/{pid}/{p}")
    check(f"page {p} (code+bugs)", r.status_code == 200, r.status_code)
html = c.get(f"/project/{pid}/dashboard").get_data(as_text=True)
check("dashboard verdict", "Project condition:" in html)
check("dashboard release chart + module table", "releaseChart" in html and "Module-wise" in html)

with app.app_context():
    levels = {(a.source, a.level) for a in Alert.query.all()}
    msgs = [a.message for a in Alert.query.all()]
    n1 = Alert.query.count()
check("aging alert exists", any("has been open for" in m for m in msgs))
check("backlog or security alert logic ran", any(s == "bug" for s, _ in levels))
c.get(f"/project/{pid}/alerts"); c.get(f"/project/{pid}/alerts")
with app.app_context():
    check("alerts do not duplicate on refresh", Alert.query.count() == n1, (n1, Alert.query.count()))

# --- add bug w/ validation
r = c.get(f"/project/{pid}/bugs"); t = tok(r.get_data(as_text=True))
r = c.post(f"/project/{pid}/bugs", data=dict(csrf_token=t, title="X", cvss_score="11", severity="Medium"))
check("cvss 11 rejected", r.status_code == 200 and b"CVSS score must be between" in r.data)
r = c.post(f"/project/{pid}/bugs", data=dict(csrf_token=t, title="SQLi login", severity="Critical", cvss_score="9.8",
                                             owasp_category="SQL Injection", found_in="Production", release_id="1",
                                             description="desc here", assignee_id="3"))
check("bug added", r.status_code == 302)
with app.app_context():
    b = Bug.query.filter_by(title="SQLi login").first(); bid = b.id
    check("bug stored cvss/owasp/found_in", b.cvss_score == 9.8 and b.owasp_category == "SQL Injection" and b.found_in == "Production")
r = c.get(f"/project/{pid}/bugs/{bid}/edit"); check("edit page", r.status_code == 200); t = tok(r.get_data(as_text=True))
r = c.post(f"/project/{pid}/bugs/{bid}/edit", data=dict(csrf_token=t, title="SQLi login v2", severity="Critical", status="Resolved",
                                                        cvss_score="9.8", owasp_category="SQL Injection", found_in="Production"))
with app.app_context():
    b = db.session.get(Bug, bid)
    check("resolve sets resolved_at", b.resolved_at is not None and b.status == "Resolved")
c.post(f"/project/{pid}/bugs/{bid}/edit", data=dict(csrf_token=t, title="SQLi login v2", severity="Critical", status="Reopened"))
with app.app_context():
    b = db.session.get(Bug, bid)
    check("reopen clears resolved_at, +1 count", b.resolved_at is None and b.reopened_count == 1, b.reopened_count)
r = c.get(f"/project/{pid}/bugs?status=open&severity=Critical&owasp=any&mine=1"); check("filters ok", r.status_code == 200)

# --- releases
r = c.get(f"/project/{pid}/releases"); t = tok(r.get_data(as_text=True))
c.post(f"/project/{pid}/releases", data=dict(csrf_token=t, name="v9", status="Planned"))
r = c.post(f"/project/{pid}/releases", data=dict(csrf_token=t, name="v9", status="Planned"))
check("duplicate release name rejected", b"already exists" in r.data)
with app.app_context():
    rid = Release.query.filter_by(name="v1.0").first().id
    nb_in = Bug.query.filter_by(release_id=rid).count()
c.post(f"/project/{pid}/releases/{rid}/delete", data=dict(csrf_token=t))
with app.app_context():
    check("release delete keeps bugs", Bug.query.count() == nb + 1 and Bug.query.filter_by(release_id=rid).count() == 0, nb_in)

# --- stats options
r = c.get(f"/project/{pid}/control-chart?variance=population&sigma=2"); h = r.get_data(as_text=True)
check("control chart shows options", "2-sigma" in h and "population" in h)
r = c.get(f"/project/{pid}/report"); h = r.get_data(as_text=True)
check("report prints options used", "2-sigma" in h and "population" in h)
r = c.get(f"/project/{pid}/statistics"); h = r.get_data(as_text=True)
check("hypothesis section present", "Welch t-test" in h and "Chi-square" in h and "reject H0" in h.replace("Reject", "reject") or "fail to reject" in h)

# --- API
with app.app_context():
    token = User.query.filter_by(username="admin").first().api_token
H = {"Authorization": "Bearer " + token}
a = app.test_client()
r = a.get(f"/api/v1/projects/{pid}/bugs"); check("API 401 JSON (not redirect)", r.status_code == 401 and r.is_json and r.json["data"] is None)
r = a.get(f"/api/v1/projects/{pid}/bugs?per_page=5&status=open", headers=H)
check("API list + pagination", r.status_code == 200 and r.json["meta"]["per_page"] == 5 and len(r.json["data"]) == 5)
r = a.post(f"/api/v1/projects/{pid}/bugs", headers=H, json={"title": "api bug", "severity": "High", "cvss_score": 7.5})
check("API create 201", r.status_code == 201 and r.json["data"]["cvss_band"] == "High"); abid = r.json["data"]["id"]
r = a.post(f"/api/v1/projects/{pid}/bugs", headers=H, json={"title": "", "severity": "Bogus"})
check("API validation 400", r.status_code == 400 and "title" in r.json["details"] and "severity" in r.json["details"])
r = a.patch(f"/api/v1/projects/{pid}/bugs/{abid}", headers=H, json={"status": "Resolved"})
check("API PATCH", r.status_code == 200 and r.json["data"]["status"] == "Resolved" and r.json["data"]["resolved_at"])
r = a.get(f"/api/v1/projects/{pid}/bugs/999999", headers=H); check("API 404", r.status_code == 404)
r = a.delete(f"/api/v1/projects/{pid}/bugs/{abid}", headers=H); check("API DELETE", r.status_code == 200)
r = a.get(f"/api/v1/projects/{pid}/metrics", headers=H)
check("API metrics", r.status_code == 200 and "escape_rate_percent" in r.json["data"]["bugs"] and "latest_release_readiness" in r.json["data"], r.status_code)
r = a.get("/api/v1/users", headers=H); check("API users (admin)", r.status_code == 200)
with app.app_context():
    dtoken = User.query.filter_by(username="dev1").first().api_token
r = a.get("/api/v1/users", headers={"Authorization": "Bearer " + dtoken}); check("API users 403 for non-admin", r.status_code == 403)
r = a.get("/api/v1/projects", headers={"Authorization": "Bearer nope"}); check("API bad token 401", r.status_code == 401)
r = c.post(f"/api/v1/projects/{pid}/bugs", json={"title": "csrf"}); check("API session write needs CSRF", r.status_code == 403)

# --- empty project (nothing) and bugs-only project
t = tok(c.get("/").get_data(as_text=True))
c.post("/project/new", data=dict(csrf_token=t, name="Empty")); pid2 = 2
for p in PAGES:
    r = c.get(f"/project/{pid2}/{p}"); check(f"page {p} (empty project)", r.status_code == 200, r.status_code)
t = tok(c.get(f"/project/{pid2}/bugs").get_data(as_text=True))
c.post(f"/project/{pid2}/bugs", data=dict(csrf_token=t, title="only bug"))
for p in ("dashboard", "report", "statistics", "alerts", "control-chart"):
    r = c.get(f"/project/{pid2}/{p}"); check(f"page {p} (bugs only)", r.status_code == 200, r.status_code)

# --- syntax error file
r = c.get(f"/project/{pid2}/upload"); t = tok(r.get_data(as_text=True))
c.post(f"/project/{pid2}/upload", data=dict(csrf_token=t, source_files=(io.BytesIO(b"def broken(:\n  pass"), "bad.py")), content_type="multipart/form-data")
for p in PAGES:
    r = c.get(f"/project/{pid2}/{p}"); check(f"page {p} (syntax-error file)", r.status_code == 200, r.status_code)

print("\n%d failure(s)" % len(FAILS)); sys.exit(1 if FAILS else 0)
