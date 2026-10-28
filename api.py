"""
api.py
REST API at /api/v1 (requirement 25).

Auth: a logged-in session OR the header  Authorization: Bearer <api_token>.
Unauthenticated calls get a JSON 401 (never an HTML redirect).
Session-cookie writes (POST/PUT/PATCH/DELETE) must also send header X-CSRF-Token;
Bearer-token calls do not need it.
Every response is  {"data": ..., "error": null}  (or {"data": null, "error": "...", "details": {...}}).
"""
from functools import wraps

from flask import Blueprint, jsonify, request, g, session

from auth import csrf_ok
from config import (OPEN_STATUSES, STATUSES, SEVERITIES, OWASP_CATEGORIES, OWASP_NONE)
from bug_service import validate_bug_data, create_bug, update_bug, bug_to_dict
from alerts_engine import recompute_bug_alerts
from metrics_summary import project_summary, summary_to_json
from metrics.release_metrics import sort_releases
from file_service import file_rows
from analyzers.file_analyzer import analyze_file
from models import db, User, Project, Bug, Release, CodeFile, Issue

bp = Blueprint("api", __name__, url_prefix="/api/v1")


def ok(data, status=200, meta=None):
    body = {"data": data, "error": None}
    if meta is not None:
        body["meta"] = meta
    return jsonify(body), status


def fail(message, status=400, details=None):
    body = {"data": None, "error": message}
    if details:
        body["details"] = details
    return jsonify(body), status


def api_auth(admin=False):
    def deco(view):
        @wraps(view)
        def wrapper(*a, **kw):
            user = None
            header = request.headers.get("Authorization", "")
            if header.lower().startswith("bearer "):
                token = header[7:].strip()
                user = User.query.filter_by(api_token=token).first() if token else None
                if not user:
                    return fail("Invalid API token.", 401)
            elif session.get("user_id"):
                user = db.session.get(User, session["user_id"])
                if user and request.method not in ("GET", "HEAD", "OPTIONS"):
                    if not csrf_ok(request.headers.get("X-CSRF-Token")):
                        return fail("Missing or wrong X-CSRF-Token header (or use a Bearer token).", 403)
            if not user:
                return fail("Authentication required. Log in or send 'Authorization: Bearer <token>'.", 401)
            if admin and not user.is_admin:
                return fail("Admin role required.", 403)
            g.user = user
            return view(*a, **kw)
        return wrapper
    return deco


def _project_or_404(project_id):
    return db.session.get(Project, project_id)


def _json_body():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else None


# ---------------------------------------------------------------- projects
@bp.route("/projects")
@api_auth()
def projects():
    return ok([{"id": p.id, "name": p.name, "description": p.description,
                "created_at": p.created_at.isoformat()} for p in Project.query.order_by(Project.id).all()])


@bp.route("/projects/<int:project_id>")
@api_auth()
def project_detail(project_id):
    p = _project_or_404(project_id)
    if not p:
        return fail("Project not found.", 404)
    return ok({"id": p.id, "name": p.name, "description": p.description, "created_at": p.created_at.isoformat()})


# ---------------------------------------------------------------- bugs
@bp.route("/projects/<int:project_id>/bugs", methods=["GET"])
@api_auth()
def bugs_list(project_id):
    if not _project_or_404(project_id):
        return fail("Project not found.", 404)
    a = request.args
    q = Bug.query.filter_by(project_id=project_id)
    status = a.get("status", "")
    if status == "open":
        q = q.filter(Bug.status.in_(OPEN_STATUSES))
    elif status:
        if status not in STATUSES:
            return fail(f"status must be 'open' or one of: {', '.join(STATUSES)}.", 400)
        q = q.filter(Bug.status == status)
    if a.get("severity"):
        if a["severity"] not in SEVERITIES:
            return fail(f"severity must be one of: {', '.join(SEVERITIES)}.", 400)
        q = q.filter(Bug.severity == a["severity"])
    if a.get("module"):
        q = q.filter(Bug.module == a["module"])
    for key, col in (("assignee", Bug.assignee_id), ("release", Bug.release_id)):
        if a.get(key):
            if not a[key].isdigit():
                return fail(f"{key} must be a numeric id.", 400)
            q = q.filter(col == int(a[key]))
    if a.get("owasp"):
        if a["owasp"] not in OWASP_CATEGORIES:
            return fail("Unknown owasp category.", 400, {"allowed": OWASP_CATEGORIES})
        q = q.filter(Bug.owasp_category == a["owasp"])
    try:
        page = max(1, int(a.get("page", 1)))
        per_page = min(100, max(1, int(a.get("per_page", 25))))
    except ValueError:
        return fail("page and per_page must be integers.", 400)
    total = q.count()
    rows = q.order_by(Bug.id).offset((page - 1) * per_page).limit(per_page).all()
    return ok([bug_to_dict(b) for b in rows],
              meta={"page": page, "per_page": per_page, "total": total, "pages": (total + per_page - 1) // per_page})


@bp.route("/projects/<int:project_id>/bugs", methods=["POST"])
@api_auth()
def bugs_create(project_id):
    if not _project_or_404(project_id):
        return fail("Project not found.", 404)
    data = _json_body()
    if data is None:
        return fail("Send a JSON object as the request body.", 400)
    clean, errors = validate_bug_data(data, project_id)
    if errors:
        return fail("Validation failed.", 400, errors)
    b = create_bug(project_id, clean)
    db.session.commit()
    recompute_bug_alerts(project_id)
    return ok(bug_to_dict(b), 201)


def _bug_or_none(project_id, bug_id):
    b = db.session.get(Bug, bug_id)
    return b if b and b.project_id == project_id else None


@bp.route("/projects/<int:project_id>/bugs/<int:bug_id>", methods=["GET", "PUT", "PATCH", "DELETE"])
@api_auth()
def bug_item(project_id, bug_id):
    if not _project_or_404(project_id):
        return fail("Project not found.", 404)
    b = _bug_or_none(project_id, bug_id)
    if not b:
        return fail("Bug not found.", 404)
    if request.method == "GET":
        return ok(bug_to_dict(b))
    if request.method == "DELETE":
        db.session.delete(b)
        db.session.commit()
        recompute_bug_alerts(project_id)
        return ok({"deleted": bug_id})
    data = _json_body()
    if data is None:
        return fail("Send a JSON object as the request body.", 400)
    clean, errors = validate_bug_data(data, project_id, partial=(request.method == "PATCH"))
    if errors:
        return fail("Validation failed.", 400, errors)
    update_bug(b, clean)
    db.session.commit()
    recompute_bug_alerts(project_id)
    return ok(bug_to_dict(b))


# ---------------------------------------------------------------- metrics / releases / users
@bp.route("/projects/<int:project_id>/metrics")
@api_auth()
def metrics(project_id):
    if not _project_or_404(project_id):
        return fail("Project not found.", 404)
    return ok(summary_to_json(project_summary(project_id)))


@bp.route("/projects/<int:project_id>/releases")
@api_auth()
def releases(project_id):
    if not _project_or_404(project_id):
        return fail("Project not found.", 404)
    s = project_summary(project_id)
    return ok(summary_to_json(s)["releases"])


@bp.route("/projects/<int:project_id>/files")
@api_auth()
def files(project_id):
    if not _project_or_404(project_id):
        return fail("Project not found.", 404)
    return ok([{"id": r["id"], "path": r["path"], "language": r["language"], "basic_metrics": r["basic"],
                "lines": r["loc"], "functions": r["functions"], "avg_complexity": r["avg_cc"],
                "max_complexity": r["max_cc"], "maintainability": r["mi"], "maintainability_band": r["band"],
                "issues": r["issues"], "risk": r["risk"]} for r in file_rows(project_id)])


@bp.route("/projects/<int:project_id>/files/<int:file_id>/metrics")
@api_auth()
def file_metrics(project_id, file_id):
    if not _project_or_404(project_id):
        return fail("Project not found.", 404)
    cf = db.session.get(CodeFile, file_id)
    if not cf or cf.project_id != project_id:
        return fail("File not found.", 404)
    res = analyze_file(cf)
    if res is None:
        return fail("The stored file is missing on disk.", 404)
    row = next(r for r in file_rows(project_id) if r["id"] == file_id)
    return ok({"id": cf.id, "path": row["path"], "language": row["language"], "basic_metrics": row["basic"],
               "risk": row["risk"], "lines": row["loc"], "comment_lines": row["comment_lines"],
               "functions": row["functions"], "classes": row["classes"], "avg_complexity": row["avg_cc"],
               "max_complexity": row["max_cc"], "max_nesting": cf.max_nesting, "maintainability": row["mi"],
               "maintainability_band": row["band"], "linked_bugs": row["bugs"],
               "function_details": [{"name": f["name"], "line": f["line"], "size_lines": f["size_lines"],
                                    "complexity": f["complexity"], "risk_level": f["risk_level"]} for f in res["functions"]],
               "issues": [{"line": i.line_number, "type": i.issue_type, "severity": i.severity, "category": i.category,
                           "description": i.description, "fix_suggestion": i.fix_suggestion,
                           "logged_bug_id": i.logged_bug_id}
                          for i in Issue.query.filter_by(code_file_id=cf.id).order_by(Issue.line_number)]})


@bp.route("/users")
@api_auth(admin=True)
def users():
    return ok([{"id": u.id, "username": u.username, "full_name": u.full_name, "email": u.email,
                "role": u.role, "created_at": u.created_at.isoformat()} for u in User.query.order_by(User.id)])


@bp.app_errorhandler(405)
def method_not_allowed(_e):
    if request.path.startswith("/api/"):
        return fail("Method not allowed.", 405)
    return "Method not allowed", 405
