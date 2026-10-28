"""
file_service.py
Everything about stored source files: safe path handling, junk skipping, saving an upload,
caching per-file numbers on CodeFile, syncing Issue rows, per-file risk and folder grouping
(requirements 27-29, 33, 36).
"""
import os
import re
from collections import Counter, defaultdict

from config import (UPLOAD_DIR, MAX_FILES, MAX_FILE_BYTES, SKIP_DIRS, SUPPORTED_EXTS, BINARY_EXTS)
from analyzers.file_analyzer import analyze_file, language_for
from bayesian.risk_model import compute_risk_probability
from metrics.maintainability import mi_band
from models import db, CodeFile, Issue, Bug, utcnow

_BAD_CHARS = re.compile(r"[^A-Za-z0-9._\-+@()\[\] ]")


# ------------------------------------------------------------------ path safety
def sanitize_relpath(raw):
    """Return a safe relative path ('a/b/c.py') or None if the path is unsafe.
    Blocks '..', absolute paths, drive letters and empty names."""
    if not raw:
        return None
    raw = raw.replace("\\", "/")
    if raw.startswith("/") or re.match(r"^[A-Za-z]:", raw):
        return None
    parts = []
    for p in raw.split("/"):
        if p in ("", "."):
            continue
        if p == ".." or ":" in p or "\x00" in p:
            return None
        p = _BAD_CHARS.sub("_", p).rstrip(" .")           # keep leading dots (.git, .venv) but never trailing
        if not p:
            return None
        parts.append(p[:120])
    return "/".join(parts) if parts else None


def skip_reason(relpath, size=None, head=None):
    """Why a file should be skipped (None = keep). Mirrors the browser-side filter."""
    parts = relpath.split("/")
    for d in parts[:-1]:
        if d in SKIP_DIRS:
            return d
    name = parts[-1].lower()
    ext = os.path.splitext(name)[1]
    if ext in BINARY_EXTS or (head is not None and b"\x00" in head):
        return "binary"
    if name.endswith(".min.js"):
        return "minified"
    if size is not None and size > MAX_FILE_BYTES:
        return "too large (>2 MB)"
    if ext not in SUPPORTED_EXTS:
        return "unsupported type"
    return None


def summarize_skips(counter):
    if not counter:
        return ""
    return ", ".join(f"{k}: {v:,}" for k, v in counter.most_common())


# ------------------------------------------------------------------ cache + issues
def refresh_file(cf):
    """Re-analyse one file, update cached columns and sync Issue rows. Returns the analysis."""
    res = analyze_file(cf)
    if res is None:
        return None
    size = res["size_result"]
    total = size.get("total_lines", 0)
    cf.loc = total
    cf.language = res["language"]
    cf.basic_metrics = res["basic"]
    cf.comment_lines = size.get("comment_lines", 0)
    cf.num_functions = len(res["functions"])
    cf.num_classes = size.get("num_classes", 0)
    cf.num_imports = size.get("num_imports", 0)
    cf.avg_cc = res["avg_complexity"]
    cf.max_cc = res["max_complexity"]
    cf.max_nesting = res["structure"].get("max_nesting_depth", 0)
    cf.mi_score = res["mi"]["mi_score"]
    cf.mi_band = res["mi"]["band"]
    cf.issue_count = len(res["issues"])
    cf.high_issue_count = sum(1 for i in res["issues"] if i["severity"] == "High")
    cf.security_count = len(res["security_findings"])
    cf.parse_error = res["parse_error"] or ""
    try:
        cf.size_bytes = os.path.getsize(cf.filepath)
    except OSError:
        pass

    # keep issues already logged as bugs (so "Logged as bug #12" survives), replace the rest
    old = Issue.query.filter_by(code_file_id=cf.id).all()
    logged = {(i.issue_type, i.line_number, i.description): i for i in old if i.logged_bug_id}
    for i in old:
        if not i.logged_bug_id:
            db.session.delete(i)
    for it in res["issues"]:
        if (it["issue_type"], it["line_number"], it["description"]) in logged:
            continue
        db.session.add(Issue(code_file_id=cf.id, line_number=it["line_number"], issue_type=it["issue_type"],
                             severity=it["severity"], description=it["description"],
                             fix_suggestion=it.get("fix_suggestion", ""), category=it["category"]))
    return res


def store_file(project_id, relpath, data):
    """Write bytes to uploads/<project>/<relpath>, create/replace the CodeFile row, analyse it."""
    base = os.path.abspath(os.path.join(UPLOAD_DIR, str(project_id)))
    target = os.path.abspath(os.path.join(base, *relpath.split("/")))
    if os.path.commonpath([base, target]) != base:
        raise ValueError("unsafe path")
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "wb") as fh:
        fh.write(data)
    cf = CodeFile.query.filter_by(project_id=project_id, relpath=relpath).first()
    if cf:                                              # same path replaces the old copy
        cf.filepath, cf.uploaded_at = target, utcnow()
    else:
        cf = CodeFile(project_id=project_id, filename=relpath, relpath=relpath, filepath=target)
        db.session.add(cf)
    db.session.flush()
    refresh_file(cf)
    return cf


def process_upload(project_id, items):
    """items: list of (raw_relpath, FileStorage). Returns a result dict (never raises on bad input)."""
    skipped, accepted, errors = Counter(), [], []
    for raw, storage in items:
        rel = sanitize_relpath(raw or getattr(storage, "filename", ""))
        if not rel:
            skipped["unsafe path"] += 1
            continue
        data = storage.read(MAX_FILE_BYTES + 1)
        reason = skip_reason(rel, size=len(data), head=data[:8192])
        if reason:
            skipped[reason] += 1
            continue
        accepted.append((rel, data))
    if len(accepted) > MAX_FILES:
        return {"ok": False, "accepted": 0, "skipped": dict(skipped),
                "message": f"Too many files: {len(accepted)} useful files were sent but the limit is {MAX_FILES} per upload. "
                           "Remove some files or upload sub-folders separately."}
    for rel, data in accepted:
        try:
            store_file(project_id, rel, data)
        except (ValueError, OSError) as exc:
            errors.append(f"{rel}: {exc}")
    db.session.commit()
    n = len(accepted) - len(errors)
    total_skipped = sum(skipped.values())
    msg = f"Accepted {n} file{'s' if n != 1 else ''}, skipped {total_skipped:,}"
    if skipped:
        msg += f" ({summarize_skips(skipped)})"
    if errors:
        msg += ". Problems: " + "; ".join(errors[:3])
    return {"ok": n > 0 or total_skipped == 0 or True, "accepted": n, "skipped": dict(skipped), "message": msg + "."}


def delete_code_file(cf):
    Bug.query.filter_by(code_file_id=cf.id).update({"code_file_id": None})
    try:
        if os.path.exists(cf.filepath):
            os.remove(cf.filepath)
    except OSError:
        pass
    db.session.delete(cf)


# ------------------------------------------------------------------ per-file risk
def linked_bug_counts(project_id):
    rows = (db.session.query(Bug.code_file_id, db.func.count(Bug.id))
            .filter(Bug.project_id == project_id, Bug.code_file_id.isnot(None))
            .group_by(Bug.code_file_id).all())
    return dict(rows)


def file_risk(cf, linked_bugs=0):
    """Risk class of one file: Low / Medium / High / Critical (dark red).
    Bayesian evidence: avg complexity > 10, linked-bug density > 3 per KLOC, any security issue, MI < 40.
    Critical = Bayesian High AND (2+ High issues OR a function with complexity > 30)."""
    from config import MI_LOW_THRESHOLD
    kloc = max(cf.loc or 0, 1) / 1000.0
    res = compute_risk_probability(
        high_complexity=(cf.avg_cc or 0) > 10, has_defect_history=(linked_bugs / kloc) > 3,
        security_findings=(cf.security_count or 0) > 0, low_maintainability=(cf.mi_score or 100) < MI_LOW_THRESHOLD)
    level = res["predicted_risk"]
    if level == "High" and ((cf.high_issue_count or 0) >= 2 or (cf.max_cc or 0) > 30):
        level = "Critical"
    return level


def file_rows(project_id):
    """One dict per file with cached numbers + risk; used by lists, dashboard and metrics page."""
    files = CodeFile.query.filter_by(project_id=project_id).order_by(CodeFile.filename).all()
    counts = linked_bug_counts(project_id)
    rows = []
    for cf in files:
        rows.append({"id": cf.id, "path": cf.relpath or cf.filename, "folder": cf.folder, "language": cf.language,
                     "basic": cf.basic_metrics, "loc": cf.loc or 0, "comment_lines": cf.comment_lines or 0,
                     "functions": cf.num_functions or 0, "classes": cf.num_classes or 0, "avg_cc": cf.avg_cc or 0,
                     "max_cc": cf.max_cc or 0, "mi": cf.mi_score if cf.mi_score is not None else 100,
                     "band": cf.mi_band or "", "issues": cf.issue_count or 0, "high_issues": cf.high_issue_count or 0,
                     "security": cf.security_count or 0, "bugs": counts.get(cf.id, 0),
                     "risk": file_risk(cf, counts.get(cf.id, 0)), "parse_error": cf.parse_error})
    return rows


RISK_ORDER = {"Critical": 3, "High": 2, "Medium": 1, "Low": 0}


def group_by_folder(rows, depth=1):
    """Group file rows by the first `depth` folder levels; root files go to '(root)'."""
    groups = defaultdict(list)
    for r in rows:
        parts = [p for p in r["folder"].split("/") if p]
        key = "/".join(parts[:depth]) if parts else "(root)"
        groups[key].append(r)
    out = []
    for name, rs in sorted(groups.items()):
        loc = sum(r["loc"] for r in rs)
        cc_vals = [r["avg_cc"] for r in rs if r["functions"]]
        worst = max(rs, key=lambda r: RISK_ORDER[r["risk"]])["risk"]
        out.append({"name": name, "files": len(rs), "loc": loc, "functions": sum(r["functions"] for r in rs),
                    "avg_cc": round(sum(cc_vals) / len(cc_vals), 2) if cc_vals else 0,
                    "mi": round(sum(r["mi"] * r["loc"] for r in rs) / loc, 2) if loc else 100.0,
                    "issues": sum(r["issues"] for r in rs), "risk": worst,
                    "high_risk_files": sum(1 for r in rs if RISK_ORDER[r["risk"]] >= 2)})
    return out
