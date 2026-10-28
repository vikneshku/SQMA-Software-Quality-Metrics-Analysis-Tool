"""
bug_service.py
One place for bug validation, status transitions and serialisation.
Used by the HTML views AND the REST API so both behave identically.
"""
from datetime import datetime, date, time as dtime

from config import (SEVERITIES, PRIORITIES, STATUSES, OPEN_STATUSES, CLOSED_STATUSES, FOUND_IN,
                    OWASP_CATEGORIES, OWASP_NONE, ASSIGNABLE_ROLES)
from metrics.cvss import parse_cvss, cvss_band
from models import db, User, Release, Bug, CodeFile, utcnow


def apply_status(bug, new_status):
    """Move a bug to a new status and keep resolved_at / reopened_count consistent."""
    old = bug.status
    if new_status == old:
        return
    bug.status = new_status
    if new_status in CLOSED_STATUSES:
        bug.resolved_at = utcnow()
    else:
        bug.resolved_at = None
    if new_status == "Reopened":
        bug.reopened_count = (bug.reopened_count or 0) + 1


def assignable_users():
    return User.query.filter(User.role.in_(ASSIGNABLE_ROLES)).order_by(User.username).all()


def _to_int(raw):
    if raw in (None, "", "0", 0):
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        raise ValueError


def validate_bug_data(data, project_id, partial=False):
    """Validate a dict of raw values (form or JSON).
    Returns (clean_dict, errors_dict). With partial=True only supplied keys are checked."""
    clean, errors = {}, {}

    def has(k):
        return (k in data) or not partial

    def text(key, label, maxlen, required=False, default=""):
        if not has(key):
            return
        v = data.get(key)
        v = "" if v is None else str(v).strip()
        if required and not v:
            errors[key] = f"{label} is required."
        elif len(v) > maxlen:
            errors[key] = f"{label} must be at most {maxlen} characters."
        else:
            clean[key] = v or default

    def choice(key, label, options, default):
        if not has(key):
            return
        v = data.get(key)
        v = default if v in (None, "") else str(v).strip()
        if v not in options:
            errors[key] = f"{label} must be one of: {', '.join(options)}."
        else:
            clean[key] = v

    text("title", "Title", 250, required=True)
    text("description", "Description", 5000)
    text("module", "Module", 120, default="General")
    choice("severity", "Severity", SEVERITIES, "Medium")
    choice("priority", "Priority", PRIORITIES, "Medium")
    choice("status", "Status", STATUSES, "Open")
    choice("found_in", "Found in", FOUND_IN, "Testing")

    if has("owasp_category"):
        v = data.get("owasp_category")
        v = OWASP_NONE if v in (None, "") else str(v).strip()
        if v not in OWASP_CATEGORIES:
            errors["owasp_category"] = "Unknown OWASP category."
        else:
            clean["owasp_category"] = v

    if has("cvss_score"):
        val, err = parse_cvss(data.get("cvss_score"))
        if err:
            errors["cvss_score"] = err
        else:
            clean["cvss_score"] = val

    if has("assignee_id"):
        try:
            uid = _to_int(data.get("assignee_id"))
        except ValueError:
            uid = -1
        if uid is None:
            clean["assignee_id"] = None
        else:
            u = db.session.get(User, uid) if uid > 0 else None
            if not u or u.role not in ASSIGNABLE_ROLES:
                errors["assignee_id"] = "Assignee must be an existing Developer or Tester."
            else:
                clean["assignee_id"] = u.id

    if has("release_id"):
        try:
            rid = _to_int(data.get("release_id"))
        except ValueError:
            rid = -1
        if rid is None:
            clean["release_id"] = None
        else:
            r = db.session.get(Release, rid) if rid > 0 else None
            if not r or r.project_id != project_id:
                errors["release_id"] = "Release does not belong to this project."
            else:
                clean["release_id"] = r.id

    if has("code_file_id"):
        try:
            fid = _to_int(data.get("code_file_id"))
        except ValueError:
            fid = -1
        if fid is None:
            clean["code_file_id"] = None
        else:
            f = db.session.get(CodeFile, fid) if fid > 0 else None
            if not f or f.project_id != project_id:
                errors["code_file_id"] = "File does not belong to this project."
            else:
                clean["code_file_id"] = f.id

    if has("reported_on"):
        raw = (data.get("reported_on") or "").strip() if data.get("reported_on") is not None else ""
        if raw:
            try:
                d = datetime.strptime(raw[:10], "%Y-%m-%d").date()
                if d > utcnow().date():
                    errors["reported_on"] = "Date reported cannot be in the future."
                else:
                    clean["reported_on"] = d
            except ValueError:
                errors["reported_on"] = "Date must look like YYYY-MM-DD."
    return clean, errors


def create_bug(project_id, clean):
    created = utcnow()
    d = clean.get("reported_on")
    if d and d < created.date():
        created = datetime.combine(d, dtime(9, 0))
    b = Bug(project_id=project_id, created_at=created, updated_at=utcnow(),
            title=clean.get("title", "Untitled bug"), description=clean.get("description", ""),
            module=clean.get("module", "General"), severity=clean.get("severity", "Medium"),
            priority=clean.get("priority", "Medium"), found_in=clean.get("found_in", "Testing"),
            owasp_category=clean.get("owasp_category", OWASP_NONE), cvss_score=clean.get("cvss_score"),
            assignee_id=clean.get("assignee_id"), release_id=clean.get("release_id"),
            code_file_id=clean.get("code_file_id"),
            status="Open")
    status = clean.get("status", "Open")
    if status != "Open":
        apply_status(b, status)
        if status == "Reopened":
            b.reopened_count = 1
    db.session.add(b)
    return b


def update_bug(bug, clean):
    for k in ("title", "description", "module", "severity", "priority", "found_in", "owasp_category",
              "cvss_score", "assignee_id", "release_id", "code_file_id"):
        if k in clean:
            setattr(bug, k, clean[k])
    d = clean.get("reported_on")
    if d:
        bug.created_at = datetime.combine(d, bug.created_at.time() if bug.created_at else dtime(9, 0))
    if "status" in clean:
        apply_status(bug, clean["status"])
    bug.updated_at = utcnow()


def bug_to_dict(b):
    return {
        "id": b.id, "project_id": b.project_id, "title": b.title, "description": b.description or "",
        "module": b.module, "severity": b.severity, "priority": b.priority, "status": b.status,
        "reopened_count": b.reopened_count or 0, "found_in": b.found_in,
        "owasp_category": b.owasp_category or OWASP_NONE, "cvss_score": b.cvss_score,
        "cvss_band": cvss_band(b.cvss_score),
        "assignee_id": b.assignee_id, "assignee": b.assignee.username if b.assignee else None,
        "release_id": b.release_id, "release": b.release.name if b.release else None,
        "code_file_id": b.code_file_id,
        "code_file": (b.code_file.relpath or b.code_file.filename) if b.code_file else None,
        "created_at": b.created_at.isoformat() if b.created_at else None,
        "updated_at": b.updated_at.isoformat() if b.updated_at else None,
        "resolved_at": b.resolved_at.isoformat() if b.resolved_at else None,
    }
