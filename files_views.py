"""
files_views.py
Blueprint "files": Files list, File detail, re-analyse, Code Issues (+ export, Log as bug) and the
Project Metrics page (requirements 29-32, 35).
"""
import csv
import io
import json

from flask import (Blueprint, Response, abort, flash, redirect, render_template, request, url_for)

from config import ISSUE_CATEGORIES, OWASP_BY_KEYWORD, OWASP_NONE, MI_BANDS
from analyzers.file_analyzer import analyze_file
from bug_service import create_bug
from alerts_engine import recompute_bug_alerts
from bayesian.risk_model import compute_risk_probability
from file_service import (file_rows, group_by_folder, refresh_file, delete_code_file, file_risk, linked_bug_counts,
                          RISK_ORDER)
from metrics.defect_metrics import defect_density, reopen_rate
from metrics.quality_metrics import overall_quality_score
from analysis_service import run_full_code_analysis
from prediction.decision_tree import train_and_predict as decision_tree_predict
from prediction.risk_prediction import evaluate_risk
from models import db, Project, CodeFile, Issue, Bug, utcnow

bp = Blueprint("files", __name__)


def _project(pid):
    return db.get_or_404(Project, pid)


def _file(pid, fid):
    cf = db.get_or_404(CodeFile, fid)
    if cf.project_id != pid:
        abort(404)
    return cf


# ======================================================================  Files list
@bp.route("/project/<int:project_id>/files")
def files_page(project_id):
    project = _project(project_id)
    return render_template("files.html", project=project, rows=file_rows(project_id), active="files")


@bp.route("/project/<int:project_id>/files/reanalyze", methods=["POST"])
def reanalyze_all(project_id):
    _project(project_id)
    n = 0
    for cf in CodeFile.query.filter_by(project_id=project_id).all():
        if refresh_file(cf):
            n += 1
    db.session.commit()
    flash(f"Re-analysed {n} file(s).", "success")
    return redirect(request.referrer or url_for("files.files_page", project_id=project_id))


@bp.route("/project/<int:project_id>/file/<int:file_id>/reanalyze", methods=["POST"])
def reanalyze_one(project_id, file_id):
    cf = _file(project_id, file_id)
    refresh_file(cf)
    db.session.commit()
    flash("File re-analysed.", "success")
    return redirect(request.referrer or url_for("files.file_detail", project_id=project_id, file_id=file_id))


@bp.route("/project/<int:project_id>/file/<int:file_id>/delete", methods=["POST"])
def delete_file(project_id, file_id):
    cf = _file(project_id, file_id)
    delete_code_file(cf)
    db.session.commit()
    flash("File deleted.", "info")
    return redirect(request.referrer if request.referrer and f"/file/{file_id}" not in request.referrer
                    else url_for("files.files_page", project_id=project_id))


# ======================================================================  File detail (35)
@bp.route("/project/<int:project_id>/file/<int:file_id>")
def file_detail(project_id, file_id):
    project, cf = _project(project_id), _file(project_id, file_id)
    res = analyze_file(cf)
    if res is None:
        flash("The stored file is missing on disk. Delete it and upload it again.", "danger")
        return redirect(url_for("files.files_page", project_id=project_id))
    if cf.mi_band == "":
        refresh_file(cf)
        db.session.commit()

    bugs = Bug.query.filter_by(project_id=project_id, code_file_id=cf.id).all()
    size = res["size_result"]
    dd = defect_density(bugs, size.get("total_lines", 0))
    rr = reopen_rate(bugs)
    n_sec = len(res["security_findings"])
    sec = {"High": 0, "Medium": 0, "Low": 0}
    for s in res["security_findings"]:
        sec[s["severity"]] = sec.get(s["severity"], 0) + 1
    quality = overall_quality_score(res["mi"]["mi_score"], res["avg_complexity"], dd, sec["High"], sec["Medium"], sec["Low"])
    inputs = dict(loc=size.get("total_lines", 0), complexity=res["avg_complexity"], defect_density=dd,
                  reopen_rate=rr, security_issues=n_sec)
    tree = decision_tree_predict(**inputs)
    bayes = evaluate_risk(res["avg_complexity"], dd, n_sec, res["mi"]["mi_score"])
    risk = file_risk(cf, len(bugs))

    # source viewer
    try:
        with open(cf.filepath, "r", encoding="utf-8", errors="replace") as fh:
            source_lines = fh.read().splitlines()
    except OSError:
        source_lines = []
    issues = Issue.query.filter_by(code_file_id=cf.id).order_by(Issue.line_number).all()
    live_bug_ids = {b[0] for b in db.session.query(Bug.id).filter(Bug.project_id == project_id).all()}
    by_line = {}
    for i in issues:
        by_line.setdefault(i.line_number, []).append(i)
    siblings = CodeFile.query.filter_by(project_id=project_id).order_by(CodeFile.filename).all()
    idx = next((n for n, f in enumerate(siblings) if f.id == cf.id), 0)
    prev_f = siblings[idx - 1] if idx > 0 else None
    next_f = siblings[idx + 1] if idx + 1 < len(siblings) else None
    funcs = sorted(res["functions"], key=lambda f: f["line"])
    chart = {"labels": [f"{f['name']} (L{f['line']})" for f in funcs], "data": [f["complexity"] for f in funcs],
             "colors": [{"Low": "#16a34a", "Moderate": "#d97706", "High": "#dc2626", "Very High": "#7f1d1d"}[f["risk_level"]]
                        for f in funcs]}
    return render_template("file_detail.html", project=project, cf=cf, res=res, size=size, quality=quality, tree=tree,
                           bayes=bayes, risk=risk, issues=issues, by_line=by_line, source_lines=source_lines,
                           live_bug_ids=live_bug_ids, prev_f=prev_f, next_f=next_f, funcs=funcs, chart=chart,
                           linked_bugs=bugs, dd=dd, active="files")


# ======================================================================  Code Issues (30, 32)
def _issue_query(project_id, args):
    q = (Issue.query.join(CodeFile, Issue.code_file_id == CodeFile.id).filter(CodeFile.project_id == project_id))
    f = {"file": args.get("file", "").strip(), "severity": args.get("severity", "").strip(),
         "category": args.get("category", "").strip(), "type": args.get("type", "").strip(),
         "q": args.get("q", "").strip()}
    if f["file"].isdigit():
        q = q.filter(Issue.code_file_id == int(f["file"]))
    if f["severity"] in ("High", "Medium", "Low"):
        q = q.filter(Issue.severity == f["severity"])
    if f["category"] in ISSUE_CATEGORIES:
        q = q.filter(Issue.category == f["category"])
    if f["type"]:
        q = q.filter(Issue.issue_type == f["type"])
    if f["q"]:
        like = f"%{f['q']}%"
        q = q.filter(db.or_(Issue.description.ilike(like), Issue.issue_type.ilike(like), CodeFile.filename.ilike(like)))
    sev_rank = db.case((Issue.severity == "High", 0), (Issue.severity == "Medium", 1), else_=2)
    return q.order_by(sev_rank, CodeFile.filename, Issue.line_number), f


@bp.route("/project/<int:project_id>/issues")
def issues_page(project_id):
    project = _project(project_id)
    q, flt = _issue_query(project_id, request.args)
    total_matching = q.count()
    issues = q.limit(500).all()
    all_q = Issue.query.join(CodeFile, Issue.code_file_id == CodeFile.id).filter(CodeFile.project_id == project_id)
    sev_counts = {s: all_q.filter(Issue.severity == s).count() for s in ("High", "Medium", "Low")}
    types = [t[0] for t in db.session.query(Issue.issue_type).join(CodeFile, Issue.code_file_id == CodeFile.id)
             .filter(CodeFile.project_id == project_id).distinct().order_by(Issue.issue_type).all()]
    files = CodeFile.query.filter_by(project_id=project_id).order_by(CodeFile.filename).all()
    live_bug_ids = {b[0] for b in db.session.query(Bug.id).filter(Bug.project_id == project_id).all()}
    return render_template("issues.html", project=project, issues=issues, flt=flt, sev_counts=sev_counts,
                           total=sum(sev_counts.values()), total_matching=total_matching, types=types, files=files,
                           categories=ISSUE_CATEGORIES, live_bug_ids=live_bug_ids, active="issues")


def _safe_cell(v):
    s = "" if v is None else str(v)
    return "'" + s if s[:1] in ("=", "+", "-", "@") else s


@bp.route("/project/<int:project_id>/issues/export.<fmt>")
def issues_export(project_id, fmt):
    _project(project_id)
    if fmt not in ("csv", "json"):
        abort(404)
    q, _ = _issue_query(project_id, request.args)
    rows = [{"file": i.code_file.relpath or i.code_file.filename, "line": i.line_number, "type": i.issue_type,
             "severity": i.severity, "category": i.category, "description": i.description,
             "fix_suggestion": i.fix_suggestion, "logged_bug_id": i.logged_bug_id} for i in q.all()]
    if fmt == "json":
        return Response(json.dumps(rows, indent=2), mimetype="application/json",
                        headers={"Content-Disposition": "attachment; filename=code_issues.json"})
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["file", "line", "type", "severity", "category", "description", "fix_suggestion", "logged_bug_id"])
    for r in rows:
        w.writerow([_safe_cell(r[k]) for k in ("file", "line", "type", "severity", "category", "description",
                                               "fix_suggestion", "logged_bug_id")])
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=code_issues.csv"})


def owasp_for(issue):
    if issue.category != "Security":
        return OWASP_NONE
    t = issue.issue_type.lower()
    for key, cat in OWASP_BY_KEYWORD:
        if key in t:
            return cat
    return "Other"


def log_issue(issue, project_id):
    """Create a Bug from an Issue unless it is already logged. Returns the Bug or None."""
    if issue.logged_bug_id and db.session.get(Bug, issue.logged_bug_id):
        return None
    cf = issue.code_file
    path = cf.relpath or cf.filename
    folder = cf.folder or "(root)"
    desc = (f"{issue.description}\nFile: {path}\nLine: {issue.line_number}\n"
            f"Suggested fix: {issue.fix_suggestion or 'n/a'}")
    clean = {"title": f"{issue.issue_type} in {path}:{issue.line_number}"[:250], "description": desc,
             "module": folder[:120], "severity": issue.severity if issue.severity in ("Low", "Medium", "High") else "Medium",
             "owasp_category": owasp_for(issue), "priority": "High" if issue.severity == "High" else "Medium"}
    bug = create_bug(project_id, clean)
    bug.code_file_id = cf.id
    db.session.flush()
    bug.source_issue_id = issue.id
    issue.logged_bug_id = bug.id
    return bug


@bp.route("/project/<int:project_id>/issues/<int:issue_id>/log-bug", methods=["POST"])
def issue_log_bug(project_id, issue_id):
    issue = db.get_or_404(Issue, issue_id)
    if issue.code_file.project_id != project_id:
        abort(404)
    bug = log_issue(issue, project_id)
    db.session.commit()
    if bug:
        recompute_bug_alerts(project_id)
        flash(f"Logged as bug #{bug.id}.", "success")
    else:
        flash(f"This issue is already logged as bug #{issue.logged_bug_id}.", "info")
    return redirect(request.referrer or url_for("files.issues_page", project_id=project_id))


@bp.route("/project/<int:project_id>/issues/log-high", methods=["POST"])
def issues_log_high(project_id):
    _project(project_id)
    q = (Issue.query.join(CodeFile, Issue.code_file_id == CodeFile.id)
         .filter(CodeFile.project_id == project_id, Issue.severity == "High"))
    n = 0
    for issue in q.all():
        if log_issue(issue, project_id):
            n += 1
    db.session.commit()
    recompute_bug_alerts(project_id)
    flash(f"{n} High-severity issue(s) logged as bugs (already-logged ones were skipped).", "success")
    return redirect(request.referrer or url_for("files.issues_page", project_id=project_id))


# ======================================================================  Project Metrics (31)
@bp.route("/project/<int:project_id>/project-metrics")
def project_metrics_page(project_id):
    project = _project(project_id)
    depth = 2 if request.args.get("depth") == "2" else 1
    analysis = run_full_code_analysis(project_id)
    rows = file_rows(project_id)
    groups = group_by_folder(rows, depth)
    from analysis_service import compute_scores
    bugs = Bug.query.filter_by(project_id=project_id).all()
    _dd, mi, quality, _risk = compute_scores(bugs, analysis)
    issue_counts = {s: sum(1 for i in analysis["issues"] if i["severity"] == s) for s in ("High", "Medium", "Low")}
    chart = {"labels": [g["name"] for g in groups], "files": [g["files"] for g in groups],
             "loc": [g["loc"] for g in groups], "avg_cc": [g["avg_cc"] for g in groups],
             "mi": [g["mi"] for g in groups], "issues": [g["issues"] for g in groups]}
    return render_template("project_metrics.html", project=project, analysis=analysis, rows=rows, groups=groups,
                           depth=depth, mi=mi, quality=quality, issue_counts=issue_counts, chart=chart,
                           active="project_metrics")
