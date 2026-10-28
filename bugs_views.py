"""
bugs_views.py
Blueprint "bugs": Bug Management (add / list / edit / resolve / reopen / delete / demo data)
and the Releases pages (requirements 1-6, 9, 10, 15).
"""
import random
from datetime import datetime, timedelta, time as dtime, date

from flask import Blueprint, render_template, request, redirect, url_for, flash, g

from config import (SEVERITIES, PRIORITIES, STATUSES, FOUND_IN, OWASP_CATEGORIES, OPEN_STATUSES,
                    RELEASE_STATUSES, OWASP_NONE)
from models import db, Project, Bug, Release, User, CodeFile, utcnow
from bug_service import (validate_bug_data, create_bug, update_bug, apply_status, assignable_users)
from alerts_engine import recompute_bug_alerts
from metrics.release_metrics import release_table, sort_releases, latest_release

bp = Blueprint("bugs", __name__)


def _project(project_id):
    return db.get_or_404(Project, project_id)


def _bug(project_id, bug_id):
    b = db.get_or_404(Bug, bug_id)
    if b.project_id != project_id:
        from flask import abort
        abort(404)
    return b


def _form_lists(project_id):
    return dict(severities=SEVERITIES, priorities=PRIORITIES, statuses=STATUSES, found_in_options=FOUND_IN,
                owasp_options=OWASP_CATEGORIES, users=assignable_users(),
                releases=sort_releases(Release.query.filter_by(project_id=project_id).all()),
                code_files=CodeFile.query.filter_by(project_id=project_id).order_by(CodeFile.filename).all())


# =====================================================================  Bug list + add
@bp.route("/project/<int:project_id>/bugs", methods=["GET", "POST"])
def bug_list(project_id):
    project = _project(project_id)
    form_values, show_form = {}, False
    if request.method == "GET":
        rel_arg = request.args.get("release", "").strip()
        if rel_arg.isdigit():
            form_values["release_id"] = rel_arg
        elif len(project.releases) == 1:
            form_values["release_id"] = str(project.releases[0].id)
        if request.args.get("show_add") == "1":
            show_form = True
    elif request.method == "POST":
        clean, errors = validate_bug_data(request.form, project_id)
        if errors:
            for msg in errors.values():
                flash(msg, "danger")
            form_values, show_form = request.form.to_dict(), True
        else:
            create_bug(project_id, clean)
            db.session.commit()
            recompute_bug_alerts(project_id)
            flash("Bug added.", "success")
            return redirect(url_for("bugs.bug_list", project_id=project_id))

    q = Bug.query.filter_by(project_id=project_id)
    args = request.args
    flt = {k: args.get(k, "").strip() for k in ("status", "severity", "module", "assignee", "release", "owasp", "q")}
    flt["mine"] = args.get("mine") == "1"
    if flt["status"] == "open":
        q = q.filter(Bug.status.in_(OPEN_STATUSES))
    elif flt["status"] in STATUSES:
        q = q.filter(Bug.status == flt["status"])
    if flt["severity"] in SEVERITIES:
        q = q.filter(Bug.severity == flt["severity"])
    if flt["module"]:
        q = q.filter(Bug.module == flt["module"])
    if flt["mine"]:
        q = q.filter(Bug.assignee_id == g.user.id)
    elif flt["assignee"] == "none":
        q = q.filter(Bug.assignee_id.is_(None))
    elif flt["assignee"].isdigit():
        q = q.filter(Bug.assignee_id == int(flt["assignee"]))
    if flt["release"] == "none":
        q = q.filter(Bug.release_id.is_(None))
    elif flt["release"].isdigit():
        q = q.filter(Bug.release_id == int(flt["release"]))
    if flt["owasp"] == "any":
        q = q.filter(Bug.owasp_category != OWASP_NONE)
    elif flt["owasp"] in OWASP_CATEGORIES:
        q = q.filter(Bug.owasp_category == flt["owasp"])
    if flt["q"]:
        like = f"%{flt['q']}%"
        q = q.filter(db.or_(Bug.title.ilike(like), Bug.description.ilike(like)))
    bug_list_ = q.order_by(Bug.created_at.desc()).all()
    modules = [m[0] for m in db.session.query(Bug.module).filter_by(project_id=project_id).distinct().all()]
    total = Bug.query.filter_by(project_id=project_id).count()

    return render_template("bugs.html", project=project, bugs=bug_list_, total=total, flt=flt, modules=sorted(modules),
                           f=form_values, show_form=show_form, active="bugs",
                           today=utcnow().date().isoformat(), **_form_lists(project_id))


# =====================================================================  Edit
def _values_from_bug(b):
    return {"title": b.title, "description": b.description or "", "module": b.module, "severity": b.severity,
            "priority": b.priority, "status": b.status, "reported_on": b.created_at.date().isoformat(),
            "assignee_id": b.assignee_id or "", "release_id": b.release_id or "", "code_file_id": b.code_file_id or "", "found_in": b.found_in,
            "owasp_category": b.owasp_category or OWASP_NONE,
            "cvss_score": "" if b.cvss_score is None else b.cvss_score}


@bp.route("/project/<int:project_id>/bugs/<int:bug_id>/edit", methods=["GET", "POST"])
def bug_edit(project_id, bug_id):
    project, bug = _project(project_id), _bug(project_id, bug_id)
    values = _values_from_bug(bug)
    if request.method == "POST":
        clean, errors = validate_bug_data(request.form, project_id)
        if errors:
            for msg in errors.values():
                flash(msg, "danger")
            values = request.form.to_dict()
        else:
            update_bug(bug, clean)
            db.session.commit()
            recompute_bug_alerts(project_id)
            flash("Bug saved.", "success")
            return redirect(url_for("bugs.bug_list", project_id=project_id))
    return render_template("bug_edit.html", project=project, bug=bug, f=values, active="bugs",
                           today=utcnow().date().isoformat(), **_form_lists(project_id))


# =====================================================================  Quick actions
@bp.route("/project/<int:project_id>/bugs/<int:bug_id>/resolve", methods=["POST"])
def bug_resolve(project_id, bug_id):
    b = _bug(project_id, bug_id)
    apply_status(b, "Resolved")
    db.session.commit()
    recompute_bug_alerts(project_id)
    return redirect(request.referrer or url_for("bugs.bug_list", project_id=project_id))


@bp.route("/project/<int:project_id>/bugs/<int:bug_id>/reopen", methods=["POST"])
def bug_reopen(project_id, bug_id):
    b = _bug(project_id, bug_id)
    apply_status(b, "Reopened")
    db.session.commit()
    recompute_bug_alerts(project_id)
    return redirect(request.referrer or url_for("bugs.bug_list", project_id=project_id))


@bp.route("/project/<int:project_id>/bugs/<int:bug_id>/delete", methods=["POST"])
def bug_delete(project_id, bug_id):
    b = _bug(project_id, bug_id)
    db.session.delete(b)
    db.session.commit()
    recompute_bug_alerts(project_id)
    flash("Bug deleted.", "info")
    return redirect(url_for("bugs.bug_list", project_id=project_id))


@bp.route("/project/<int:project_id>/bugs/clear", methods=["POST"])
def bugs_clear(project_id):
    _project(project_id)
    n = Bug.query.filter_by(project_id=project_id).delete()
    db.session.commit()
    recompute_bug_alerts(project_id)
    flash(f"{n} bug(s) deleted.", "info")
    return redirect(url_for("bugs.bug_list", project_id=project_id))


# =====================================================================  Demo data
DEMO_TITLES = {
    "Orders": ["Crash on checkout", "Wrong total after discount", "Order status not updating"],
    "Payments": ["Payment timeout", "Duplicate charge", "Refund not recorded"],
    "Database": ["Slow query on report page", "Deadlock on update", "Missing index"],
    "Frontend": ["Button misaligned", "Form loses data on refresh", "Dropdown not closing"],
    "Auth": ["Session expires early", "Password reset email delayed", "Role check bypass"],
}
DEMO_SECURITY = {"Auth": [("Broken Authentication", 8.1), ("Broken Access Control", 9.1)],
                 "Database": [("SQL Injection", 9.8)], "Frontend": [("Cross-Site Scripting (XSS)", 6.1)]}


def make_demo_bugs(project_id):
    """~35 demo bugs over 28 days (one 'bad day' spike) plus two old open bugs, spread over
    three releases, so every chart, alert and the readiness indicator have data to show."""
    rnd = random.Random(11)
    today = utcnow()
    rels = sort_releases(Release.query.filter_by(project_id=project_id).all())
    if not rels:
        for name, offset, status in (("v1.0", -45, "Released"), ("v1.1", -20, "Released"), ("v1.2", 10, "Planned")):
            r = Release(project_id=project_id, name=name, release_date=(today + timedelta(days=offset)).date(),
                        status=status)
            db.session.add(r)
            rels.append(r)
        db.session.flush()
    users = assignable_users()
    per_day = [1, 0, 2, 1, 1, 0, 2, 1, 1, 2, 0, 1, 1, 9, 0, 1, 2, 1, 0, 1, 1, 2, 0, 1, 1, 0, 2, 1]
    modules = list(DEMO_TITLES)
    made = 0

    def build(created, module, title):
        severity = rnd.choices(SEVERITIES, [3, 5, 3, 1])[0]
        sec = DEMO_SECURITY.get(module)
        owasp, cvss = (rnd.choice(sec) if sec and rnd.random() < 0.35 else (OWASP_NONE, None))
        # releases by age: oldest third -> first release, etc.
        age_days = (today - created).days
        rel = rels[0] if age_days > 19 else (rels[1] if age_days > 9 else rels[min(2, len(rels) - 1)])
        b = Bug(project_id=project_id, title="[Demo] " + title, module=module, severity=severity,
                priority=rnd.choice(PRIORITIES), description=f"Demo bug in the {module} module: {title.lower()}.",
                created_at=created, updated_at=created, status="Open", release_id=rel.id,
                found_in="Production" if rnd.random() < 0.18 else "Testing",
                owasp_category=owasp, cvss_score=cvss,
                assignee_id=rnd.choice(users).id if users and rnd.random() < 0.7 else None)
        if rnd.random() < 0.70:
            fixed = created + timedelta(hours=rnd.randint(4, 96))
            if fixed < today:
                b.status, b.resolved_at = ("Resolved" if rnd.random() < 0.8 else "Closed"), fixed
        if rnd.random() < 0.18:
            b.reopened_count = rnd.randint(1, 2)
            if b.status in ("Resolved", "Closed"):
                b.status, b.resolved_at = "Reopened", None
        return b

    for i, n in enumerate(per_day):
        day = today - timedelta(days=len(per_day) - 1 - i)
        for _ in range(n):
            module = rnd.choice(modules)
            created = datetime.combine(day.date(), dtime(rnd.randint(8, 17), rnd.randint(0, 59)))
            created = min(created, today)
            db.session.add(build(created, module, rnd.choice(DEMO_TITLES[module])))
            made += 1
    for days_ago, module in ((41, "Database"), (36, "Auth")):          # stale open bugs -> aging alerts
        created = today - timedelta(days=days_ago)
        b = build(created, module, rnd.choice(DEMO_TITLES[module]))
        b.status, b.resolved_at, b.release_id = "Open", None, rels[0].id
        db.session.add(b)
        made += 1
    db.session.commit()
    return made


@bp.route("/project/<int:project_id>/bugs/demo", methods=["POST"])
def bugs_demo(project_id):
    _project(project_id)
    made = make_demo_bugs(project_id)
    recompute_bug_alerts(project_id)
    flash(f"{made} demo bugs added (titles start with [Demo]) with 3 demo releases. "
          "Open the Control Chart and the Dashboard to see them.", "success")
    return redirect(url_for("bugs.bug_list", project_id=project_id))


# =====================================================================  Releases
def _validate_release(form, project_id, current_id=None):
    errors = {}
    name = form.get("name", "").strip()
    if not name:
        errors["name"] = "Release name is required."
    elif len(name) > 60:
        errors["name"] = "Release name must be at most 60 characters."
    else:
        dup = Release.query.filter(Release.project_id == project_id, db.func.lower(Release.name) == name.lower())
        if current_id:
            dup = dup.filter(Release.id != current_id)
        if dup.first():
            errors["name"] = f'A release called "{name}" already exists.'
    rdate = None
    raw = form.get("release_date", "").strip()
    if raw:
        try:
            rdate = datetime.strptime(raw, "%Y-%m-%d").date()
        except ValueError:
            errors["release_date"] = "Date must look like YYYY-MM-DD."
    status = form.get("status", "Planned")
    if status not in RELEASE_STATUSES:
        errors["status"] = "Status must be Planned or Released."
    return errors, name, rdate, status


@bp.route("/project/<int:project_id>/releases", methods=["GET", "POST"])
def releases(project_id):
    project = _project(project_id)
    if request.method == "POST":
        errors, name, rdate, status = _validate_release(request.form, project_id)
        if errors:
            for m in errors.values():
                flash(m, "danger")
        else:
            db.session.add(Release(project_id=project_id, name=name, release_date=rdate, status=status))
            db.session.commit()
            recompute_bug_alerts(project_id)
            flash(f"Release {name} added.", "success")
            return redirect(url_for("bugs.releases", project_id=project_id))
    rels = sort_releases(Release.query.filter_by(project_id=project_id).all())
    bugs = Bug.query.filter_by(project_id=project_id).all()
    rows = release_table(rels, bugs)
    latest = latest_release(rels)
    latest_row = next((r for r in rows if latest and r["id"] == latest.id), None)
    unassigned_count = sum(1 for b in bugs if b.release_id is None)
    return render_template("releases.html", project=project, rows=rows, latest=latest_row,
                           statuses=RELEASE_STATUSES, active="releases", today=utcnow().date().isoformat(),
                           unassigned_count=unassigned_count)


@bp.route("/project/<int:project_id>/releases/<int:release_id>/edit", methods=["GET", "POST"])
def release_edit(project_id, release_id):
    project = _project(project_id)
    r = db.get_or_404(Release, release_id)
    if r.project_id != project_id:
        from flask import abort
        abort(404)
    if request.method == "POST":
        errors, name, rdate, status = _validate_release(request.form, project_id, r.id)
        if errors:
            for m in errors.values():
                flash(m, "danger")
        else:
            r.name, r.release_date, r.status = name, rdate, status
            db.session.commit()
            recompute_bug_alerts(project_id)
            flash("Release saved.", "success")
            return redirect(url_for("bugs.releases", project_id=project_id))
    return render_template("release_edit.html", project=project, r=r, statuses=RELEASE_STATUSES, active="releases")


@bp.route("/project/<int:project_id>/releases/<int:release_id>/delete", methods=["POST"])
def release_delete(project_id, release_id):
    r = db.get_or_404(Release, release_id)
    if r.project_id != project_id:
        from flask import abort
        abort(404)
    n = Bug.query.filter_by(release_id=r.id).update({"release_id": None})   # un-tag, never delete bugs
    db.session.delete(r)
    db.session.commit()
    recompute_bug_alerts(project_id)
    flash(f"Release deleted. {n} bug(s) were un-tagged (not deleted).", "info")
    return redirect(url_for("bugs.releases", project_id=project_id))


@bp.route("/project/<int:project_id>/releases/assign-unassigned", methods=["POST"])
def assign_unassigned(project_id):
    _project(project_id)
    rid = (request.form.get("target_release_id") or request.form.get("release_id") or "").strip()
    if rid.isdigit():
        r = db.session.get(Release, int(rid))
        if r and r.project_id == project_id:
            count = Bug.query.filter_by(project_id=project_id, release_id=None).update({"release_id": r.id})
            db.session.commit()
            recompute_bug_alerts(project_id)
            flash(f"{count} unassigned bug(s) assigned to release {r.name}.", "success")
    return redirect(url_for("bugs.releases", project_id=project_id))


@bp.route("/project/<int:project_id>/bugs/<int:bug_id>/assign-release", methods=["POST"])
def bug_assign_release(project_id, bug_id):
    b = _bug(project_id, bug_id)
    rid = request.form.get("release_id", "").strip()
    if rid.isdigit():
        r = db.session.get(Release, int(rid))
        if r and r.project_id == project_id:
            b.release_id = r.id
            flash(f'Bug #{b.id} assigned to release "{r.name}".', "success")
    elif rid in ("", "none", "0"):
        b.release_id = None
        flash(f"Bug #{b.id} unassigned from release.", "info")
    db.session.commit()
    recompute_bug_alerts(project_id)
    return redirect(request.referrer or url_for("bugs.bug_list", project_id=project_id))
