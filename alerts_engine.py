"""
alerts_engine.py
Alert generation (requirements 12-15). Alerts are RECOMPUTED every time:
the project's old auto alerts of the same source are deleted and re-created, so
numbers never go stale or duplicate. Manual alerts are never touched.

    source = "bug"   aging bugs, growing backlog, critical security bugs, release turns Red
    source = "code"  defect density, complexity, security findings, maintainability
"""
from config import AGING_BUG_DAYS, CRITICAL_CVSS, MI_LOW_THRESHOLD
from metrics.defect_metrics import (is_open, is_closed, is_security_bug, bug_age_days)
from metrics.release_metrics import release_readiness
from models import db, Alert, Bug, Release, utcnow


def recompute_bug_alerts(project_id):
    Alert.query.filter_by(project_id=project_id, source="bug").delete()
    bugs = Bug.query.filter_by(project_id=project_id).all()
    now = utcnow()
    new = []

    # 12. aging bugs - one alert per bug open longer than 30 days
    for b in bugs:
        if is_open(b):
            age = bug_age_days(b, now)
            if age > AGING_BUG_DAYS:
                level = "Critical" if b.severity in ("Critical", "High") else "Warning"
                new.append((f'Bug "{b.title}" has been open for {int(age)} days.', level))

    # 13. growing backlog
    n_open = sum(1 for b in bugs if is_open(b))
    n_closed = sum(1 for b in bugs if is_closed(b))
    if n_open > n_closed:
        level = "Critical" if n_open > 2 * n_closed else "Warning"
        new.append((f"Backlog is growing: {n_open} open bugs vs {n_closed} closed bugs.", level))

    # 14. critical / high security bugs
    for b in bugs:
        if is_open(b) and is_security_bug(b) and (b.severity in ("Critical", "High")
                                                  or (b.cvss_score or 0) >= CRITICAL_CVSS):
            cv = f", CVSS {b.cvss_score}" if b.cvss_score is not None else ""
            new.append((f'Open security bug "{b.title}" ({b.owasp_category}, severity {b.severity}{cv}).',
                        "Critical"))

    # 15. release turns Red
    for r in Release.query.filter_by(project_id=project_id).all():
        rb = [b for b in bugs if b.release_id == r.id]
        ready = release_readiness(rb)
        if ready["color"] == "Red":
            new.append((f"Release {r.name} is RED (not ready): " + "; ".join(ready["reasons"][:3]) + ".",
                        "Critical"))

    for msg, level in new:
        db.session.add(Alert(project_id=project_id, message=msg, level=level, source="bug"))
    db.session.commit()
    return len(new)


def recompute_code_alerts(project_id, defect_density_value, avg_complexity, sec_counts, mi_score, has_code):
    Alert.query.filter_by(project_id=project_id, source="code").delete()
    msgs = []
    if defect_density_value > 8:
        msgs.append(("Defect density is high (%.2f per KLOC)." % defect_density_value, "Critical"))
    elif defect_density_value > 4:
        msgs.append(("Defect density is elevated (%.2f per KLOC)." % defect_density_value, "Warning"))
    if avg_complexity > 15:
        msgs.append(("Average cyclomatic complexity is very high (%.1f)." % avg_complexity, "Critical"))
    elif avg_complexity > 10:
        msgs.append(("Average cyclomatic complexity is high (%.1f)." % avg_complexity, "Warning"))
    if sec_counts.get("High", 0) > 0:
        msgs.append(("%d high-severity security issue(s) found in the code." % sec_counts["High"], "Critical"))
    if has_code and mi_score < MI_LOW_THRESHOLD:
        msgs.append(("Maintainability index is low (%.1f, below %d)." % (mi_score, MI_LOW_THRESHOLD), "Warning"))
    for m, level in msgs:
        db.session.add(Alert(project_id=project_id, message=m, level=level, source="code"))
    db.session.commit()
