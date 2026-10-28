"""
metrics/release_metrics.py
Per-release numbers, the release comparison data and the release readiness
indicator (requirements 9, 10, 15). Thresholds live in config.READINESS.
"""
from config import READINESS, CRITICAL_CVSS
from metrics.defect_metrics import (is_open, is_closed, is_security_bug, bug_age_days,
                                    escape_rate, escaped_count)
from models import utcnow


def release_readiness(bugs) -> dict:
    """Return {"color": Red|Yellow|Green, "reasons": [plain-words strings]}.
    `bugs` are the bugs that belong to ONE release."""
    T = READINESS
    now = utcnow()
    open_bugs = [b for b in bugs if is_open(b)]
    closed_n = sum(1 for b in bugs if is_closed(b))
    open_crit = [b for b in open_bugs if b.severity == "Critical"]
    open_high = [b for b in open_bugs if b.severity == "High"]
    sec9 = [b for b in open_bugs if is_security_bug(b) and (b.cvss_score or 0) >= T["red_security_cvss"]]
    old = [b for b in open_bugs if bug_age_days(b, now) > T["yellow_old_bug_days"]]

    red, yellow = [], []
    if len(open_crit) >= T["red_open_critical"]:
        red.append(f"{len(open_crit)} open Critical bug(s)")
    if len(open_high) >= T["red_open_high"]:
        red.append(f"{len(open_high)} open High bugs (limit is {T['red_open_high'] - 1})")
    if sec9:
        red.append(f"{len(sec9)} open security bug(s) with CVSS {T['red_security_cvss']} or higher")
    if len(open_high) >= T["yellow_open_high"] and len(open_high) < T["red_open_high"]:
        yellow.append(f"{len(open_high)} open High bug(s)")
    if len(open_bugs) > closed_n and open_bugs:
        yellow.append(f"more open bugs ({len(open_bugs)}) than closed bugs ({closed_n})")
    if old:
        yellow.append(f"{len(old)} open bug(s) older than {T['yellow_old_bug_days']} days")

    if red:
        return {"color": "Red", "reasons": red + yellow}
    if yellow:
        return {"color": "Yellow", "reasons": yellow}
    return {"color": "Green", "reasons": ["No open Critical/High bugs, no growing backlog and no stale bugs."]}


def release_table(releases, bugs) -> list:
    """One row per release with counts, escape rate and readiness."""
    rows = []
    for r in releases:
        rb = [b for b in bugs if b.release_id == r.id]
        open_n = sum(1 for b in rb if is_open(b))
        rows.append({
            "release": r, "id": r.id, "name": r.name, "date": r.release_date, "status": r.status,
            "total": len(rb), "open": open_n, "closed": sum(1 for b in rb if is_closed(b)),
            "critical_high": sum(1 for b in rb if b.severity in ("Critical", "High")),
            "escaped": escaped_count(rb), "escape_rate": escape_rate(rb),
            "readiness": release_readiness(rb),
        })
    return rows


def sort_releases(releases):
    """Oldest -> newest (release date, then id)."""
    return sorted(releases, key=lambda r: (r.release_date is None, r.release_date or 0, r.id))


def latest_release(releases):
    if not releases:
        return None
    dated = [r for r in releases if r.release_date]
    if dated:
        return max(dated, key=lambda r: (r.release_date, r.id))
    return max(releases, key=lambda r: r.id)


def comparison_data(rows) -> dict:
    """Data for the grouped bar chart (viz.js releaseComparison)."""
    return {
        "labels": [r["name"] for r in rows],
        "total": [r["total"] for r in rows],
        "open": [r["open"] for r in rows],
        "critical_high": [r["critical_high"] for r in rows],
        "escaped": [r["escaped"] for r in rows],
    }
