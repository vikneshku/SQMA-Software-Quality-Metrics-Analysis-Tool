"""
app.py
Software Quality and Metrics Analysis Tool - Flask application.
Run with:  python app.py        then open  http://127.0.0.1:5000

Large features live in their own modules and are registered as blueprints:
    auth.py        login / register / users / profile / CSRF
    bugs_views.py  Bug Management + Releases
    api.py         REST API  (/api/v1)
"""
import os
import secrets
from collections import Counter
from datetime import datetime, timedelta

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session, abort, g
from sqlalchemy import inspect as sa_inspect
from werkzeug.utils import secure_filename

import auth
import api
import bugs_views
import files_views
import ai_views
from config import (BASE_DIR, UPLOAD_DIR, DB_PATH, SEVERITIES, VARIANCE_TYPES, SIGMA_CHOICES, DEFAULT_VARIANCE,
                    DEFAULT_SIGMA, DEFAULT_COMPLEXITY_TARGET, READINESS, MI_BANDS, ALPHA, AGING_BUG_DAYS)
from models import (db, Project, Bug, Release, CodeFile, Alert, Issue, utcnow)
from config import (MAX_UPLOAD_BYTES, MAX_FILES, MAX_FILE_BYTES, SKIP_DIRS, SUPPORTED_EXTS)
from file_service import process_upload, file_rows, group_by_folder, RISK_ORDER, refresh_file

from analyzers.security_analyzer import RULES as SECURITY_RULES
from analysis_service import run_full_code_analysis, security_summary, compute_scores
from alerts_engine import recompute_bug_alerts, recompute_code_alerts
from metrics_summary import project_summary, summary_to_json
from metrics.defect_metrics import (mttr_hours, defect_density, reopen_rate, average_bug_age_days, escape_rate,
                                    escaped_count, module_risk, severity_breakdown, open_closed, old_bug_count)
from metrics.cvss import cvss_band
from metrics.maintainability import maintainability_index, project_maintainability
from metrics.release_metrics import sort_releases, release_readiness, release_table, latest_release

from stats_engine.descriptive import describe
from stats_engine.correlation import pearson_correlation
from stats_engine.control_chart import build_control_chart
from stats_engine.boxplot import build_boxplot
from stats_engine.histogram import build_histogram
from stats_engine import hypothesis

from prediction.decision_tree import train_and_predict as decision_tree_predict
from prediction.defect_prediction import predict_defect_risk
from reports.report_generator import build_report, build_calculations, build_recommendations


def _secret_key():
    env = os.environ.get("SQMA_SECRET_KEY")
    if env:
        return env
    path = os.path.join(BASE_DIR, ".secret_key")
    if not os.path.exists(path):
        with open(path, "w") as fh:
            fh.write(secrets.token_hex(32))
    with open(path) as fh:
        return fh.read().strip()


app = Flask(__name__)
app.config["SECRET_KEY"] = _secret_key()
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{DB_PATH}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES        # 100 MB (config.py)
app.config["MAX_FORM_PARTS"] = 20000                       # folder uploads send many form parts
app.config["MAX_FORM_MEMORY_SIZE"] = MAX_UPLOAD_BYTES
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

db.init_app(app)
os.makedirs(UPLOAD_DIR, exist_ok=True)

auth.init_app(app)
auth.register_error_pages(app)
app.register_blueprint(bugs_views.bp)
app.register_blueprint(files_views.bp)
app.register_blueprint(ai_views.bp)
app.register_blueprint(api.bp)
app.jinja_env.filters["cvss_band"] = cvss_band


NEW_COLUMNS = {   # columns added after Phase 1: added automatically so old data survives
    "code_file": {"relpath": "VARCHAR(400) DEFAULT ''", "language": "VARCHAR(20) DEFAULT 'Python'",
                  "basic_metrics": "BOOLEAN DEFAULT 0", "size_bytes": "INTEGER DEFAULT 0",
                  "comment_lines": "INTEGER DEFAULT 0", "num_functions": "INTEGER DEFAULT 0",
                  "num_classes": "INTEGER DEFAULT 0", "num_imports": "INTEGER DEFAULT 0", "avg_cc": "FLOAT DEFAULT 0",
                  "max_cc": "INTEGER DEFAULT 0", "max_nesting": "INTEGER DEFAULT 0", "mi_score": "FLOAT DEFAULT 100",
                  "mi_band": "VARCHAR(40) DEFAULT ''", "issue_count": "INTEGER DEFAULT 0",
                  "high_issue_count": "INTEGER DEFAULT 0", "security_count": "INTEGER DEFAULT 0",
                  "parse_error": "TEXT DEFAULT ''"},
}


def init_database():
    """Create tables; add newer columns to old databases; refuse a Phase-0 schema (see reset_db.py)."""
    db.create_all()
    insp = sa_inspect(db.engine)
    need = {"bug": {"found_in", "owasp_category", "cvss_score", "assignee_id", "release_id", "updated_at"},
            "alert": {"source"}}
    for table, cols in need.items():
        have = {c["name"] for c in insp.get_columns(table)}
        if not cols <= have:
            raise SystemExit("\n*** Your sqma.db was created by an older version of SQMA.\n"
                             "*** Run:  python reset_db.py   (this deletes old data), then start the app again.\n")
    for table, cols in NEW_COLUMNS.items():
        have = {c["name"] for c in insp.get_columns(table)}
        for name, ddl in cols.items():
            if name not in have:
                with db.engine.begin() as conn:
                    conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")


with app.app_context():
    init_database()


def _wants_json():
    return request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.accept_mimetypes.best == "application/json"


@app.errorhandler(413)
def too_large(_e):
    msg = (f"Upload too large: the total size is limited to {MAX_UPLOAD_BYTES // (1024 * 1024)} MB. "
           "Remove some files or upload sub-folders separately.")
    if _wants_json():
        return jsonify({"ok": False, "message": msg}), 413
    flash(msg, "danger")
    return redirect(request.referrer or url_for("index"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def get_project_or_404(project_id):
    return db.get_or_404(Project, project_id)


SCOPED_ENDPOINTS = {"size_page", "complexity_page", "quality_page", "statistics_page", "correlation_page",
                    "boxplot_page", "decision_tree_page", "defect_prediction_page", "risk_prediction_page",
                    "security_page", "maintainability_page"}


def scope_file_id(project_id):
    """?file=<id> from the file selector (None = whole project). Ignores ids of other projects."""
    raw = request.args.get("file", "")
    if raw.isdigit():
        cf = db.session.get(CodeFile, int(raw))
        if cf and cf.project_id == project_id:
            return cf.id
    return None


def scoped_bugs(project_id):
    """Whole project -> all bugs; one file -> only bugs linked to that file."""
    fid = scope_file_id(project_id)
    q = Bug.query.filter_by(project_id=project_id)
    if fid:
        q = q.filter(Bug.code_file_id == fid)
    return q.all()


def analysis_for(project_id):
    return run_full_code_analysis(project_id, scope_file_id(project_id))


@app.context_processor
def file_selector_context():
    """Adds the 'All files / one file' selector to every analysis page (requirement 36)."""
    if request.endpoint not in SCOPED_ENDPOINTS or not request.view_args:
        return {}
    pid = request.view_args.get("project_id")
    files = CodeFile.query.filter_by(project_id=pid).order_by(CodeFile.filename).all()
    if not files:
        return {}
    fid = scope_file_id(pid)
    no_bugs = bool(fid) and Bug.query.filter_by(project_id=pid, code_file_id=fid).count() == 0
    return {"show_selector": True, "sel_files": files, "sel_id": fid, "sel_no_bugs": no_bugs,
            "sel_hidden": [(k, v) for k, v in request.args.items(multi=True) if k != "file"]}


def no_code_page(project, active, title):
    return render_template("no_code.html", project=project, active=active, page_title=title)


def stat_options():
    """Variance type + control-chart sigma, from the query string, remembered in the session."""
    vt, sg = request.args.get("variance"), request.args.get("sigma")
    if vt in VARIANCE_TYPES:
        session["variance"] = vt
    if sg in [str(s) for s in SIGMA_CHOICES]:
        session["sigma"] = int(sg)
    vt = session.get("variance", DEFAULT_VARIANCE)
    sg = session.get("sigma", DEFAULT_SIGMA)
    return (vt if vt in VARIANCE_TYPES else DEFAULT_VARIANCE), (sg if sg in SIGMA_CHOICES else DEFAULT_SIGMA)


def refresh_alerts(project_id, analysis=None, bugs=None):
    analysis = analysis or run_full_code_analysis(project_id)
    bugs = bugs if bugs is not None else Bug.query.filter_by(project_id=project_id).all()
    dd, mi, _q, _r = compute_scores(bugs, analysis)
    recompute_code_alerts(project_id, dd, analysis["avg_complexity"], analysis["security_counts"],
                          mi["mi_score"], analysis["has_code"])
    recompute_bug_alerts(project_id)


def severity_chart_data(bugs):
    counts = severity_breakdown(bugs)
    labels = [s for s in SEVERITIES if counts.get(s)]
    return labels, [counts[s] for s in labels]


def bug_series(bugs, by="day", release=None, project=None):
    """Time series of bug counts used by the Control Chart (per day or per Monday-start week).
    Correlates with releases and project history so a valid control chart is always available."""
    if not bugs:
        return [], [], by
    dates = [b.created_at.date() for b in bugs if b.created_at]
    if not dates:
        return [], [], by

    start_candidates = [min(dates)]
    if release and getattr(release, "release_date", None):
        start_candidates.append(release.release_date)
    if project and getattr(project, "created_at", None):
        start_candidates.append(project.created_at.date())

    cur_raw = min(start_candidates)
    end_raw = max(max(dates), utcnow().date())

    if by == "day" and (max(dates) - min(dates)).days > 120:
        by = "week"
    if by == "week":
        keyfn, step = (lambda d: d - timedelta(days=d.weekday())), 7
        if (end_raw - cur_raw).days < 21:
            cur_raw = end_raw - timedelta(days=21)
    else:
        keyfn, step = (lambda d: d), 1
        if (end_raw - cur_raw).days < 6:
            cur_raw = end_raw - timedelta(days=6)

    counts = Counter(keyfn(d) for d in dates)
    cur, end = keyfn(cur_raw), keyfn(end_raw)
    labels, values = [], []
    while cur <= end:
        labels.append(cur.strftime("%d %b") if by == "day" else "Wk " + cur.strftime("%d %b"))
        values.append(counts.get(cur, 0))
        cur += timedelta(days=step)
    return labels, values, by


# ---------------------------------------------------------------------------
# Project selection / creation
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    projects = Project.query.order_by(Project.created_at.desc()).all()
    return render_template("index.html", projects=projects)


@app.route("/project/new", methods=["POST"])
def create_project():
    name = request.form.get("name", "").strip()
    description = request.form.get("description", "").strip()
    if not name:
        flash("Project name is required.", "danger")
        return redirect(url_for("index"))
    if len(name) > 150:
        flash("Project name must be at most 150 characters.", "danger")
        return redirect(url_for("index"))
    p = Project(name=name, description=description[:2000])
    db.session.add(p)
    db.session.commit()
    os.makedirs(os.path.join(UPLOAD_DIR, str(p.id)), exist_ok=True)
    return redirect(url_for("dashboard", project_id=p.id))


@app.route("/project/<int:project_id>/delete", methods=["POST"])
@auth.admin_required
def delete_project(project_id):
    p = get_project_or_404(project_id)
    Bug.query.filter_by(project_id=p.id).update({"release_id": None})
    db.session.delete(p)
    db.session.commit()
    flash("Project deleted.", "info")
    return redirect(url_for("index"))


# ---------------------------------------------------------------------------
# 1. Home Dashboard
# ---------------------------------------------------------------------------
def build_verdict(s):
    n_bugs, a = len(s["bugs"]), s["analysis"]
    if not a["has_code"] and not n_bugs:
        return "Project condition: no data yet - upload source code and log bugs to see the overall picture.", "secondary"
    parts = []
    if a["has_code"]:
        lvl = s["quality"]["quality_level"]
        hi = sum(1 for r in s["files"] if RISK_ORDER[r["risk"]] >= 2)
        parts.append(f"{lvl} - {hi} of {len(s['files'])} files are High risk (quality {s['quality']['quality_score']}%, predicted risk {s['risk']['predicted_risk']})")
    else:
        lvl = None
        parts.append("no source code uploaded yet")
    oc = s["open_closed"]
    parts.append(f"{oc['open']} open / {oc['closed']} closed bugs")
    if s["latest_release"]:
        parts.append(f"latest release {s['latest_release']['name']} is {s['latest_release']['readiness']['color']}")
    colour = {"Excellent": "success", "Good": "success", "Needs Improvement": "warning", "Poor": "danger"}.get(lvl, "secondary")
    return "Project condition: " + " - ".join(parts) + ".", colour


@app.route("/project/<int:project_id>/dashboard")
def dashboard(project_id):
    project = get_project_or_404(project_id)
    s = project_summary(project_id)
    refresh_alerts(project_id, s["analysis"], s["bugs"])
    alerts = Alert.query.filter_by(project_id=project_id).order_by(
        db.case((Alert.level == "Critical", 0), (Alert.level == "Warning", 1), else_=2), Alert.created_at.desc()).limit(6).all()
    sev_labels, sev_values = severity_chart_data(s["bugs"])
    verdict, verdict_colour = build_verdict(s)
    frows = s["files"]
    riskiest = sorted(frows, key=lambda r: (-RISK_ORDER[r["risk"]], r["mi"], -r["avg_cc"]))[:10]
    return render_template("dashboard.html", project=project, riskiest=riskiest, groups=group_by_folder(frows, 1),
                           folder_chart={"labels": [g["name"] for g in group_by_folder(frows, 1)],
                                         "files": [g["files"] for g in group_by_folder(frows, 1)],
                                         "loc": [g["loc"] for g in group_by_folder(frows, 1)],
                                         "avg_cc": [g["avg_cc"] for g in group_by_folder(frows, 1)],
                                         "mi": [g["mi"] for g in group_by_folder(frows, 1)],
                                         "issues": [g["issues"] for g in group_by_folder(frows, 1)]}, s=s, analysis=s["analysis"], bugs=s["bugs"],
                           defect_density_value=s["defect_density"], maintainability=s["maintainability"],
                           quality=s["quality"], risk=s["risk"], alerts=alerts, active="dashboard",
                           sev_labels=sev_labels, sev_values=sev_values, verdict=verdict,
                           verdict_colour=verdict_colour, aging_days=AGING_BUG_DAYS)


# ---------------------------------------------------------------------------
# 3. Source Code Upload (single .py files - folders arrive in Phase 2)
# ---------------------------------------------------------------------------
@app.route("/project/<int:project_id>/upload", methods=["GET", "POST"])
def upload_source(project_id):
    project = get_project_or_404(project_id)
    if request.method == "POST":
        files = request.files.getlist("source_files")
        paths = request.form.getlist("paths")                       # parallel list: relative path of each file
        items = [(paths[i] if i < len(paths) and paths[i] else f.filename, f) for i, f in enumerate(files)
                 if f and f.filename]
        if not items:
            result = {"ok": False, "accepted": 0, "skipped": {}, "message": "No file selected."}
        else:
            result = process_upload(project_id, items)
        if _wants_json():
            return jsonify({**result, "redirect": url_for("upload_source", project_id=project_id)}), (200 if result["ok"] else 400)
        flash(result["message"], "success" if result.get("accepted") else "warning")
        return redirect(url_for("upload_source", project_id=project_id))

    return render_template("upload.html", project=project, rows=file_rows(project_id), active="upload",
                           limits={"max_files": MAX_FILES, "max_mb": MAX_UPLOAD_BYTES // (1024 * 1024),
                                   "max_file_mb": MAX_FILE_BYTES // (1024 * 1024),
                                   "skip_dirs": sorted(SKIP_DIRS), "exts": sorted(SUPPORTED_EXTS)})


# ---------------------------------------------------------------------------
# 5. Control Chart  (built from the bugs logged in Bug Management & Releases)
# ---------------------------------------------------------------------------
@app.route("/project/<int:project_id>/control-chart")
def control_chart_page(project_id):
    project = get_project_or_404(project_id)
    all_bugs = Bug.query.filter_by(project_id=project_id).order_by(Bug.created_at).all()
    releases = sort_releases(Release.query.filter_by(project_id=project_id).all())

    release_id_raw = request.args.get("release", "").strip()
    selected_release = None
    if release_id_raw.isdigit():
        selected_release = db.session.get(Release, int(release_id_raw))
        if selected_release and selected_release.project_id == project_id:
            bugs_list = [b for b in all_bugs if b.release_id == selected_release.id]
        else:
            selected_release = None
            bugs_list = all_bugs
    elif release_id_raw == "none":
        bugs_list = [b for b in all_bugs if b.release_id is None]
    else:
        bugs_list = all_bugs

    by = "week" if request.args.get("by") == "week" else "day"
    variance, sigma = stat_options()
    labels, values, by_used = bug_series(bugs_list, by=by, release=selected_release, project=project)

    if not bugs_list:
        if selected_release:
            chart_data = {"error": f"No bugs are currently assigned to release '{selected_release.name}'. Tag bugs with this release in Bug Management."}
        else:
            chart_data = {"error": "No bugs have been logged yet. The control chart is calculated from the bugs in Bug Management."}
    else:
        chart_data = build_control_chart(values, labels, sigma, variance)
        if not chart_data.get("error"):
            chart_data["x_title"] = "Day (sub-group)" if by_used == "day" else "Week (sub-group)"
            chart_data["y_title"] = "Bugs reported per " + by_used

    # Calculate release readiness if a release is selected
    rel_readiness = release_readiness(bugs_list) if selected_release else None

    return render_template("control_chart.html", project=project, chart_data=chart_data, by=by_used,
                           bug_count=len(bugs_list), total_project_bugs=len(all_bugs),
                           active="control_chart", variance=variance, sigma=sigma,
                           releases=releases, selected_release=selected_release,
                           rel_readiness=rel_readiness, release_id=release_id_raw,
                           variance_types=VARIANCE_TYPES, sigma_choices=SIGMA_CHOICES)


# ---------------------------------------------------------------------------
# 6. Software Size
# ---------------------------------------------------------------------------
@app.route("/project/<int:project_id>/size")
def size_page(project_id):
    project = get_project_or_404(project_id)
    analysis = analysis_for(project_id)
    if not analysis["has_code"]:
        return no_code_page(project, "size", "Software Size")
    return render_template("size.html", project=project, analysis=analysis, active="size")


# ---------------------------------------------------------------------------
# 7. Complexity
# ---------------------------------------------------------------------------
@app.route("/project/<int:project_id>/complexity")
def complexity_page(project_id):
    project = get_project_or_404(project_id)
    analysis = analysis_for(project_id)
    if not analysis["has_code"]:
        return no_code_page(project, "complexity", "Complexity")
    units_sorted = sorted(analysis["complexity_units"], key=lambda u: u["complexity"], reverse=True)
    return render_template("complexity.html", project=project, analysis=analysis, units=units_sorted, active="complexity")


# ---------------------------------------------------------------------------
# 8. Quality Metrics
# ---------------------------------------------------------------------------
@app.route("/project/<int:project_id>/quality")
def quality_page(project_id):
    project = get_project_or_404(project_id)
    bugs_list = scoped_bugs(project_id)
    analysis = analysis_for(project_id)
    if not analysis["has_code"]:
        return no_code_page(project, "quality", "Quality Metrics")
    dd, mi, quality, _risk = compute_scores(bugs_list, analysis)
    return render_template("quality.html", project=project, analysis=analysis, defect_density_value=dd,
                           maintainability=mi, quality=quality, active="quality")


# ---------------------------------------------------------------------------
# 9. Statistical Analysis (descriptive + histogram + hypothesis tests)
# ---------------------------------------------------------------------------
@app.route("/project/<int:project_id>/statistics")
def statistics_page(project_id):
    project = get_project_or_404(project_id)
    analysis = analysis_for(project_id)
    variance, sigma = stat_options()
    rows = analysis["function_rows"]
    complexity_values = [r["complexity"] for r in rows]
    func_sizes = [r["size_lines"] for r in rows]

    try:
        target = float(request.args.get("target", DEFAULT_COMPLEXITY_TARGET))
        if not (0 < target <= 100):
            raise ValueError
    except ValueError:
        flash("Target complexity must be a number between 0 and 100; 10 was used.", "warning")
        target = DEFAULT_COMPLEXITY_TARGET
    bugs_list = Bug.query.filter_by(project_id=project_id).all()
    releases_by_id = {r.id: r for r in Release.query.filter_by(project_id=project_id).all()}
    tests = hypothesis.run_all(bugs_list, complexity_values, target, releases_by_id)

    return render_template(
        "statistics.html", project=project, active="statistics", has_code=analysis["has_code"],
        stats_complexity=describe(complexity_values, variance), stats_func_size=describe(func_sizes, variance),
        hist_complexity=build_histogram(complexity_values), hist_size=build_histogram(func_sizes),
        complexity_values=complexity_values, func_sizes=func_sizes, variance=variance, sigma=sigma,
        variance_types=VARIANCE_TYPES, tests=tests, target=target, alpha=ALPHA)


# ---------------------------------------------------------------------------
# 10. Correlation
# ---------------------------------------------------------------------------
@app.route("/project/<int:project_id>/correlation")
def correlation_page(project_id):
    project = get_project_or_404(project_id)
    analysis = analysis_for(project_id)
    if not analysis["has_code"]:
        return no_code_page(project, "correlation", "Correlation")
    rows = analysis["function_rows"]
    sizes = [r["size_lines"] for r in rows]
    complexities = [r["complexity"] for r in rows]
    result = pearson_correlation(sizes, complexities)
    points = [{"x": r["size_lines"], "y": r["complexity"], "name": r["name"]} for r in rows]
    return render_template("correlation.html", project=project, result=result, points=points, active="correlation")


# ---------------------------------------------------------------------------
# 11. Box Plot
# ---------------------------------------------------------------------------
@app.route("/project/<int:project_id>/boxplot")
def boxplot_page(project_id):
    project = get_project_or_404(project_id)
    analysis = analysis_for(project_id)
    if not analysis["has_code"]:
        return no_code_page(project, "boxplot", "Box Plot")
    metric = "size" if request.args.get("metric") == "size" else "complexity"
    rows = analysis["function_rows"]
    values = [r["size_lines"] if metric == "size" else r["complexity"] for r in rows]
    result = build_boxplot(values) if values else {"error": "No functions found in the uploaded code."}
    unit = "Function size (lines of code)" if metric == "size" else "Cyclomatic complexity of each function"
    return render_template("boxplot.html", project=project, result=result, metric=metric, unit=unit, active="boxplot")


# ---------------------------------------------------------------------------
# 12. Decision Tree
# ---------------------------------------------------------------------------
def _model_inputs(project_id, analysis):
    bugs_list = scoped_bugs(project_id)
    dd = defect_density(bugs_list, analysis["size"]["total_loc"])
    return dict(loc=analysis["size"]["total_loc"], complexity=analysis["avg_complexity"], defect_density=dd,
                reopen_rate=reopen_rate(bugs_list), security_issues=len(analysis["security_findings"]))


@app.route("/project/<int:project_id>/decision-tree")
def decision_tree_page(project_id):
    project = get_project_or_404(project_id)
    analysis = analysis_for(project_id)
    if not analysis["has_code"]:
        return no_code_page(project, "decision_tree", "Decision Tree")
    inputs = _model_inputs(project_id, analysis)
    result = decision_tree_predict(**inputs)
    return render_template("decision_tree.html", project=project, result=result, active="decision_tree", inputs=inputs)


# ---------------------------------------------------------------------------
# 13. Defect Prediction
# ---------------------------------------------------------------------------
@app.route("/project/<int:project_id>/defect-prediction")
def defect_prediction_page(project_id):
    project = get_project_or_404(project_id)
    analysis = analysis_for(project_id)
    if not analysis["has_code"]:
        return no_code_page(project, "defect_prediction", "Defect Prediction")
    inputs = _model_inputs(project_id, analysis)
    result = predict_defect_risk(**inputs)
    return render_template("defect_prediction.html", project=project, result=result, inputs=inputs,
                           active="defect_prediction")


# ---------------------------------------------------------------------------
# 14. Risk Prediction (Bayesian)
# ---------------------------------------------------------------------------
@app.route("/project/<int:project_id>/risk-prediction")
def risk_prediction_page(project_id):
    project = get_project_or_404(project_id)
    bugs_list = scoped_bugs(project_id)
    analysis = analysis_for(project_id)
    if not analysis["has_code"]:
        return no_code_page(project, "risk_prediction", "Risk Prediction")
    _dd, mi, _quality, result = compute_scores(bugs_list, analysis)
    return render_template("risk_prediction.html", project=project, result=result, maintainability=mi,
                           active="risk_prediction")


# ---------------------------------------------------------------------------
# 15. Security Analysis
# ---------------------------------------------------------------------------
@app.route("/project/<int:project_id>/security")
def security_page(project_id):
    project = get_project_or_404(project_id)
    analysis = analysis_for(project_id)
    if not analysis["has_code"]:
        return no_code_page(project, "security", "Security Analysis")
    return render_template("security.html", project=project, analysis=analysis,
                           summary=security_summary(analysis), rules=[(r[0], r[1]) for r in SECURITY_RULES],
                           active="security")


# ---------------------------------------------------------------------------
# 16. Maintainability
# ---------------------------------------------------------------------------
@app.route("/project/<int:project_id>/maintainability")
def maintainability_page(project_id):
    project = get_project_or_404(project_id)
    analysis = analysis_for(project_id)
    if not analysis["has_code"]:
        return no_code_page(project, "maintainability", "Maintainability")
    mi = project_maintainability(analysis["file_maintainability"])
    files = sorted(analysis["file_maintainability"], key=lambda r: r["mi_score"])
    return render_template("maintainability.html", project=project, analysis=analysis, maintainability=mi,
                           files=files, bands=MI_BANDS, active="maintainability")


# ---------------------------------------------------------------------------
# 17. Alerts
# ---------------------------------------------------------------------------
@app.route("/project/<int:project_id>/alerts")
def alerts_page(project_id):
    project = get_project_or_404(project_id)
    s = project_summary(project_id)
    refresh_alerts(project_id, s["analysis"], s["bugs"])
    tips = build_recommendations(s["quality"], {"average_complexity": s["analysis"]["avg_complexity"]},
                                 s["analysis"]["security_counts"], s["maintainability"], s["defect_density"])
    alerts_list = Alert.query.filter_by(project_id=project_id).order_by(
        db.case((Alert.level == "Critical", 0), (Alert.level == "Warning", 1), else_=2), Alert.created_at.desc()).all()
    return render_template("alerts.html", project=project, alerts=alerts_list, tips=tips, active="alerts")


@app.route("/project/<int:project_id>/alerts/<int:alert_id>/delete", methods=["POST"])
def delete_alert(project_id, alert_id):
    a = db.get_or_404(Alert, alert_id)
    if a.project_id != project_id:
        abort(404)
    db.session.delete(a)
    db.session.commit()
    flash("Alert dismissed. Automatic alerts reappear while their condition is still true.", "info")
    return redirect(url_for("alerts_page", project_id=project_id))


# ---------------------------------------------------------------------------
# 18. Reports
# ---------------------------------------------------------------------------
@app.route("/project/<int:project_id>/report")
def report_page(project_id):
    project = get_project_or_404(project_id)
    s = project_summary(project_id)
    bugs_list = sorted(s["bugs"], key=lambda b: b.created_at)
    analysis, dd, mi, quality, risk = s["analysis"], s["defect_density"], s["maintainability"], s["quality"], s["risk"]
    variance, sigma = stat_options()
    rr = s["reopen_rate"]
    n_sec = len(analysis["security_findings"])

    resolved = [b for b in bugs_list if b.resolved_at and b.created_at]
    total_hours = round(sum((b.resolved_at - b.created_at).total_seconds() / 3600.0 for b in resolved), 2)
    ages_open = [(utcnow() - b.created_at).total_seconds() / 86400.0 for b in bugs_list
                 if b.status in ("Open", "In Progress", "Reopened")]
    defect_stats = {
        "total_bugs": len(bugs_list), "defect_density": dd, "mttr_hours": s["mttr_hours"], "reopen_rate": rr,
        "escape_rate": s["escape_rate"], "average_bug_age_days": s["avg_open_age_days"],
        "old_bug_count": s["old_bug_count"], "open_ages_total": round(sum(ages_open), 2),
        "open_count": s["open_closed"]["open"], "closed_count": s["open_closed"]["closed"],
        "percent_open": s["open_closed"]["percent_open"],
        "resolved_count": len(resolved), "resolved_hours_total": total_hours,
        "reopened_count": sum(1 for b in bugs_list if b.reopened_count and b.reopened_count > 0),
        "escaped_count": s["escaped_count"],
    }

    rows = analysis["function_rows"]
    cx_values = [r["complexity"] for r in rows]
    size_values = [r["size_lines"] for r in rows]
    stats_summary = describe(cx_values, variance)
    box_cx = build_boxplot(cx_values) if cx_values else {"error": "No data yet. Upload source files first."}
    hist_cx = build_histogram(cx_values)
    corr = pearson_correlation(size_values, cx_values)
    points = [{"x": r["size_lines"], "y": r["complexity"], "name": r["name"]} for r in rows]

    labels, values, _by = bug_series(bugs_list, "day")
    ctrl = build_control_chart(values, labels, sigma, variance) if bugs_list else {"error": "No bugs logged yet."}
    if not ctrl.get("error"):
        ctrl["x_title"], ctrl["y_title"] = "Day (sub-group)", "Bugs reported per day"

    dt_inputs = dict(loc=analysis["size"]["total_loc"], complexity=analysis["avg_complexity"],
                     defect_density=dd, reopen_rate=rr, security_issues=n_sec)
    dtree = decision_tree_predict(**dt_inputs)
    prediction = predict_defect_risk(**dt_inputs)
    sec = security_summary(analysis)
    sev_labels, sev_values = severity_chart_data(bugs_list)

    top_fn = sorted(rows, key=lambda r: r["complexity"], reverse=True)[:10]
    charts = {
        "sev_labels": sev_labels, "sev_values": sev_values, "quality": quality["components"],
        "cx_labels": [f'{r["name"]} ({r["file"]})' for r in top_fn], "cx_values": [r["complexity"] for r in top_fn],
        "cx_colors": [{"Low": "#16a34a", "Moderate": "#d97706", "High": "#dc2626", "Very High": "#7f1d1d"}[r["risk_level"]] for r in top_fn],
        "hist": hist_cx, "box": box_cx, "ctrl": ctrl, "points": points, "trend": corr.get("trend"),
        "corr_kind": corr.get("kind"), "tree": dtree["tree_structure"], "tree_path": dtree["path_steps"],
        "tree_class": dtree["predicted_risk"],
        "tree_imp_labels": list(dtree["feature_importances"].keys()), "tree_imp_values": list(dtree["feature_importances"].values()),
        "dp_labels": list(prediction["feature_importances"].keys()), "dp_values": list(prediction["feature_importances"].values()),
        "bayes_labels": list(risk["probabilities"].keys()), "bayes_values": list(risk["probabilities"].values()),
        "security": sec, "release": s["release_chart"],
    }

    ctx = dict(bugs_n=len(bugs_list), loc=analysis["size"]["total_loc"], size=analysis["size"], dd=dd,
               defect_stats=defect_stats, analysis=analysis, mi=mi, quality=quality, ctrl=ctrl, box=box_cx,
               hist=hist_cx, corr=corr, dtree=dtree, dt_inputs=dt_inputs, risk=risk, sec=sec,
               cx_values=cx_values, n_sec=n_sec, prediction=prediction, variance=variance, sigma=sigma,
               stats_summary=stats_summary, release_rows=s["release_rows"], modules=s["modules"], bugs=bugs_list)
    calc_by_group = {}
    for item in build_calculations(ctx):
        calc_by_group.setdefault(item["group"], []).append(item)

    report = build_report(project, analysis["size"], analysis, defect_stats, analysis["security_counts"], mi,
                          stats_summary, risk, prediction, quality)
    return render_template("report.html", report=report, project=project, charts=charts, calcs=calc_by_group,
                           corr=corr, hist=hist_cx, box=box_cx, ctrl=ctrl, dtree=dtree, sec=sec, s=s,
                           variance=variance, sigma=sigma, readiness=READINESS, mi_bands=MI_BANDS,
                           aging_days=AGING_BUG_DAYS,
                           generated=utcnow().strftime("%Y-%m-%d %H:%M UTC"), active="report")


# ---------------------------------------------------------------------------
# Goal-Based Measurement (GQM)
# ---------------------------------------------------------------------------
@app.route("/project/<int:project_id>/goals")
def goals_page(project_id):
    project = get_project_or_404(project_id)
    bugs_list = Bug.query.filter_by(project_id=project_id).all()
    analysis = run_full_code_analysis(project_id)
    rels = sort_releases(Release.query.filter_by(project_id=project_id).all())
    rel_rows = release_table(rels, bugs_list)
    latest_rel = latest_release(rels)
    latest_row = next((r for r in rel_rows if latest_rel and r["id"] == latest_rel.id), None) if latest_rel else None

    # Control chart stability status
    labels, values, by_used = bug_series(bugs_list, by="day", project=project)
    variance, sigma = stat_options()
    ctrl = build_control_chart(values, labels, sigma, variance) if bugs_list else None
    if ctrl and not ctrl.get("error"):
        ctrl_val = "Stable" if ctrl.get("stable") else "Unusual Variation"
        ctrl_unit = "" if ctrl.get("stable") else f"({len(ctrl.get('out_of_control_points', []))} out-of-control point(s))"
        ctrl_status = "success" if ctrl.get("stable") else "danger"
    else:
        ctrl_val = "Pending bugs"
        ctrl_unit = ""
        ctrl_status = "secondary"

    # Maintainability and defect derived scores
    _dd, mi, quality, _r = compute_scores(bugs_list, analysis)
    dd = defect_density(bugs_list, analysis["size"]["total_loc"])
    rr = reopen_rate(bugs_list)
    er = escape_rate(bugs_list)

    # Open security & critical bugs
    sec_bugs_open = sum(1 for b in bugs_list if (b.status in ("Open", "In Progress", "Reopened")) and (b.owasp_category != "None" or (b.cvss_score or 0) >= 7.0))
    open_crit = sum(1 for b in bugs_list if (b.status in ("Open", "In Progress", "Reopened")) and b.severity == "Critical")

    rel_color = latest_row["readiness"]["color"] if latest_row else "None"
    rel_status = "success" if rel_color == "Green" else ("warning" if rel_color == "Yellow" else ("danger" if rel_color == "Red" else "secondary"))

    gqm = [
        {"goal": "Improve Software Reliability", "icon": "fa-shield-halved",
         "question": "Are defects increasing or under control?",
         "summary": f"Defect process is {ctrl_val.lower()}; latest release is {rel_color.lower()}.",
         "metrics": [
             {"name": "Process Stability (Control Chart)", "value": ctrl_val, "unit": ctrl_unit,
              "target": "Stable process within UCL/LCL", "status": ctrl_status,
              "url": url_for("control_chart_page", project_id=project.id)},
             {"name": "Latest Release Readiness", "value": f"{latest_row['name']} ({rel_color})" if latest_row else "No release",
              "unit": "", "target": "Green (Ready to ship)", "status": rel_status,
              "url": url_for("bugs.releases", project_id=project.id)},
             {"name": "Defect Density", "value": dd, "unit": "per KLOC",
              "target": "< 5.0 per KLOC", "status": "success" if dd <= 4 else ("warning" if dd <= 8 else "danger"),
              "url": url_for("defect_prediction_page", project_id=project.id)},
             {"name": "Escape Rate", "value": er, "unit": "%",
              "target": "< 10.0%", "status": "success" if er < 10 else ("warning" if er < 20 else "danger"),
              "url": url_for("bugs.bug_list", project_id=project.id, found_in="Production")},
             {"name": "Open Critical Defects", "value": open_crit, "unit": "bugs",
              "target": "0 open Critical bugs", "status": "success" if open_crit == 0 else "danger",
              "url": url_for("bugs.bug_list", project_id=project.id, severity="Critical")},
             {"name": "Reopen Rate", "value": rr, "unit": "%",
              "target": "< 5.0%", "status": "success" if rr <= 5 else "warning",
              "url": url_for("bugs.bug_list", project_id=project.id)},
         ]},
        {"goal": "Improve Maintainability", "icon": "fa-screwdriver-wrench",
         "question": "Is the code easy to understand, test, and change?",
         "summary": f"Maintainability Index is {mi['mi_score']}% ({mi['band']}); average complexity is {analysis['avg_complexity']}.",
         "metrics": [
             {"name": "Maintainability Index (MI)", "value": mi["mi_score"], "unit": "% (" + mi["band"] + ")",
              "target": ">= 55.0% (Highly Maintainable)", "status": "success" if mi["mi_score"] >= 55 else ("warning" if mi["mi_score"] >= 40 else "danger"),
              "url": url_for("maintainability_page", project_id=project.id)},
             {"name": "Average Cyclomatic Complexity", "value": analysis["avg_complexity"], "unit": "",
              "target": "<= 10.0", "status": "success" if analysis["avg_complexity"] <= 10 else ("warning" if analysis["avg_complexity"] <= 15 else "danger"),
              "url": url_for("complexity_page", project_id=project.id)},
             {"name": "Avg Function Size", "value": analysis["size"]["avg_function_size"], "unit": "lines",
              "target": "<= 50 lines", "status": "success" if analysis["size"]["avg_function_size"] <= 50 else "warning",
              "url": url_for("size_page", project_id=project.id)},
             {"name": "Comment Ratio", "value": analysis["size"]["comment_ratio_percent"], "unit": "%",
              "target": ">= 15%", "status": "success" if analysis["size"]["comment_ratio_percent"] >= 15 else "secondary",
              "url": url_for("size_page", project_id=project.id)},
         ]},
        {"goal": "Improve Security Posture", "icon": "fa-lock",
         "question": "Are there exploitable vulnerabilities in code or open backlog?",
         "summary": f"{analysis['security_counts']['High']} High code findings; {sec_bugs_open} open security defects.",
         "metrics": [
             {"name": "High Severity Code Findings", "value": analysis["security_counts"]["High"], "unit": "issues",
              "target": "0 findings", "status": "success" if analysis["security_counts"]["High"] == 0 else "danger",
              "url": url_for("security_page", project_id=project.id)},
             {"name": "Open Security Defects (OWASP)", "value": sec_bugs_open, "unit": "bugs",
              "target": "0 open security bugs", "status": "success" if sec_bugs_open == 0 else "danger",
              "url": url_for("bugs.bug_list", project_id=project.id, owasp="any")},
             {"name": "Medium Severity Findings", "value": analysis["security_counts"]["Medium"], "unit": "issues",
              "target": "Remediate before release", "status": "success" if analysis["security_counts"]["Medium"] == 0 else "warning",
              "url": url_for("security_page", project_id=project.id)},
             {"name": "Low Severity Findings", "value": analysis["security_counts"]["Low"], "unit": "issues",
              "target": "Review as time permits", "status": "success",
              "url": url_for("security_page", project_id=project.id)},
         ]},
    ]
    return render_template("goals.html", project=project, gqm=gqm, active="goals",
                           has_code=analysis["has_code"], bug_count=len(bugs_list))


# ---------------------------------------------------------------------------
# JSON export
# ---------------------------------------------------------------------------
@app.route("/project/<int:project_id>/export/<data_type>")
def export_data(project_id, data_type):
    get_project_or_404(project_id)
    if data_type == "bugs":
        from bug_service import bug_to_dict
        return jsonify([bug_to_dict(b) for b in Bug.query.filter_by(project_id=project_id).all()])
    if data_type == "analysis":
        analysis = run_full_code_analysis(project_id)
        return jsonify({"size": analysis["size"], "avg_complexity": analysis["avg_complexity"],
                        "security_counts": analysis["security_counts"]})
    return jsonify({"error": "Unknown data_type"}), 400


if __name__ == "__main__":
    # Uploaded .py files live inside this folder; the exclude pattern stops Flask's auto-reloader
    # from restarting the server every time a file is uploaded.
    app.run(debug=True, host="127.0.0.1", port=5000,
            exclude_patterns=[os.path.join(UPLOAD_DIR, "*"), os.path.join(UPLOAD_DIR, "*", "*")])
