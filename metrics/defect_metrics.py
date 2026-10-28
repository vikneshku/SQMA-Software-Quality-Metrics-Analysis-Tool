"""
metrics/defect_metrics.py
Bug-tracking derived metrics. All functions take a list of Bug ORM objects.

Definitions
    Open   = Open, In Progress, Reopened
    Closed = Resolved, Closed
"""
from collections import defaultdict

from config import (OPEN_STATUSES, CLOSED_STATUSES, OWASP_NONE, AGING_BUG_DAYS)
from models import utcnow


def is_open(b) -> bool:
    return b.status in OPEN_STATUSES


def is_closed(b) -> bool:
    return b.status in CLOSED_STATUSES


def is_security_bug(b) -> bool:
    return bool(b.owasp_category) and b.owasp_category != OWASP_NONE


def bug_age_days(b, now=None) -> float:
    now = now or utcnow()
    return max(0.0, (now - b.created_at).total_seconds() / 86400.0)


def mttr_hours(bugs) -> float:
    """Mean Time To Repair, in hours, over bugs that have a resolved date."""
    durations = [(b.resolved_at - b.created_at).total_seconds() / 3600.0
                 for b in bugs if b.resolved_at and b.created_at]
    return round(sum(durations) / len(durations), 2) if durations else 0.0


def defect_density(bugs, total_loc: int) -> float:
    """Defects per 1000 lines of code (KLOC)."""
    if not total_loc:
        return 0.0
    return round(len(bugs) / (total_loc / 1000.0), 3)


def reopen_rate(bugs) -> float:
    if not bugs:
        return 0.0
    reopened = sum(1 for b in bugs if b.reopened_count and b.reopened_count > 0)
    return round(reopened / len(bugs) * 100, 2)


def open_closed(bugs) -> dict:
    """Open vs Closed counts, ratio text and percentage open (requirement 7)."""
    n_open = sum(1 for b in bugs if is_open(b))
    n_closed = sum(1 for b in bugs if is_closed(b))
    total = n_open + n_closed
    return {
        "open": n_open, "closed": n_closed, "total": total,
        "ratio_text": f"{n_open} : {n_closed}",
        "percent_open": round(n_open / total * 100, 1) if total else 0.0,
        "percent_closed": round(n_closed / total * 100, 1) if total else 0.0,
    }


def average_bug_age_days(bugs) -> float:
    """Average age (days) of OPEN bugs only: now - created_at (requirement 8)."""
    now = utcnow()
    ages = [bug_age_days(b, now) for b in bugs if is_open(b)]
    return round(sum(ages) / len(ages), 2) if ages else 0.0


def old_bug_count(bugs, days: int = AGING_BUG_DAYS) -> int:
    """Number of OPEN bugs older than `days` days."""
    now = utcnow()
    return sum(1 for b in bugs if is_open(b) and bug_age_days(b, now) > days)


def escape_rate(bugs) -> float:
    """Bugs found in Production / total bugs x 100 (requirement 9). 0 when no bugs."""
    if not bugs:
        return 0.0
    escaped = sum(1 for b in bugs if b.found_in == "Production")
    return round(escaped / len(bugs) * 100, 2)


def escaped_count(bugs) -> int:
    return sum(1 for b in bugs if b.found_in == "Production")


_WEIGHT = {"Low": 1, "Medium": 2, "High": 3, "Critical": 5}


def module_risk(bugs) -> dict:
    """Per-module bug table (requirement 11).

    risk_score = sum(severity weight of OPEN bugs) + 0.5 x sum(weight of CLOSED bugs)
                 + 0.5 x average CVSS (when any bug has a score)
    weights: Low 1, Medium 2, High 3, Critical 5.
    Level: <= 5 Low, <= 15 Medium, above 15 High.
    """
    rows = defaultdict(lambda: {"bug_count": 0, "open_count": 0, "critical": 0, "high": 0,
                                "cvss": [], "w_open": 0.0, "w_closed": 0.0})
    for b in bugs:
        r = rows[b.module or "General"]
        r["bug_count"] += 1
        w = _WEIGHT.get(b.severity, 2)
        if is_open(b):
            r["open_count"] += 1
            r["w_open"] += w
        else:
            r["w_closed"] += w
        if b.severity == "Critical":
            r["critical"] += 1
        if b.severity == "High":
            r["high"] += 1
        if b.cvss_score is not None:
            r["cvss"].append(b.cvss_score)

    result = {}
    for m, r in rows.items():
        avg_cvss = round(sum(r["cvss"]) / len(r["cvss"]), 2) if r["cvss"] else None
        score = r["w_open"] + 0.5 * r["w_closed"] + (0.5 * avg_cvss if avg_cvss else 0)
        score = round(score, 2)
        result[m] = {"bug_count": r["bug_count"], "open_count": r["open_count"],
                     "critical": r["critical"], "high": r["high"], "avg_cvss": avg_cvss,
                     "risk_score": score, "risk_level": _risk_label(score)}
    return result


def _risk_label(score: float) -> str:
    if score <= 5:
        return "Low"
    if score <= 15:
        return "Medium"
    return "High"


def severity_breakdown(bugs) -> dict:
    counts = defaultdict(int)
    for b in bugs:
        counts[b.severity] += 1
    return dict(counts)


def status_breakdown(bugs) -> dict:
    counts = defaultdict(int)
    for b in bugs:
        counts[b.status] += 1
    return dict(counts)
