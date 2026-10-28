"""
metrics_summary.py
Builds the project-wide bundle of numbers used by the Dashboard, the Report and the REST API,
so they can never disagree with each other.
"""
from analysis_service import run_full_code_analysis, compute_scores
from config import AGING_BUG_DAYS
from metrics.defect_metrics import (open_closed, average_bug_age_days, old_bug_count, escape_rate, escaped_count,
                                    module_risk, mttr_hours, reopen_rate, severity_breakdown, status_breakdown)
from metrics.release_metrics import release_table, sort_releases, latest_release, comparison_data
from file_service import file_rows, RISK_ORDER
from models import Bug, Release


def project_summary(project_id, analysis=None):
    bugs = Bug.query.filter_by(project_id=project_id).all()
    analysis = analysis or run_full_code_analysis(project_id)
    dd, mi, quality, risk = compute_scores(bugs, analysis)
    releases = sort_releases(Release.query.filter_by(project_id=project_id).all())
    rows = release_table(releases, bugs)
    latest = latest_release(releases)
    latest_row = next((r for r in rows if latest and r["id"] == latest.id), None)
    modules = module_risk(bugs)
    return {
        "bugs": bugs, "analysis": analysis, "defect_density": dd, "maintainability": mi,
        "quality": quality, "risk": risk,
        "open_closed": open_closed(bugs), "avg_open_age_days": average_bug_age_days(bugs),
        "old_bug_count": old_bug_count(bugs, AGING_BUG_DAYS), "escape_rate": escape_rate(bugs),
        "escaped_count": escaped_count(bugs), "mttr_hours": mttr_hours(bugs), "reopen_rate": reopen_rate(bugs),
        "severity_breakdown": severity_breakdown(bugs), "status_breakdown": status_breakdown(bugs),
        "release_rows": rows, "release_chart": comparison_data(rows), "latest_release": latest_row,
        "modules": modules, "files": file_rows(project_id),
    }


def summary_to_json(s):
    """Plain JSON-safe version for the REST API."""
    a = s["analysis"]
    rel = []
    for r in s["release_rows"]:
        rel.append({"id": r["id"], "name": r["name"], "date": r["date"].isoformat() if r["date"] else None,
                    "status": r["status"], "total_bugs": r["total"], "open_bugs": r["open"],
                    "closed_bugs": r["closed"], "critical_high_bugs": r["critical_high"],
                    "escaped_bugs": r["escaped"], "escape_rate_percent": r["escape_rate"],
                    "readiness": r["readiness"]})
    lr = s["latest_release"]
    return {
        "quality": {"score": s["quality"]["quality_score"], "level": s["quality"]["quality_level"],
                    "components": s["quality"]["components"]},
        "risk": {"predicted": s["risk"]["predicted_risk"], "probabilities": s["risk"]["probabilities"]},
        "maintainability": {"score": s["maintainability"]["mi_score"], "band": s["maintainability"]["band"]},
        "code": {"files": a["size"]["num_files"], "loc": a["size"]["total_loc"],
                 "functions": a["size"]["num_functions"], "avg_complexity": a["avg_complexity"],
                 "max_complexity": a["max_complexity"], "security_findings": a["security_counts"]},
        "bugs": {"total": len(s["bugs"]), "defect_density_per_kloc": s["defect_density"],
                 "open": s["open_closed"]["open"], "closed": s["open_closed"]["closed"],
                 "percent_open": s["open_closed"]["percent_open"],
                 "avg_open_bug_age_days": s["avg_open_age_days"], "old_bug_count": s["old_bug_count"],
                 "escape_rate_percent": s["escape_rate"], "escaped_bugs": s["escaped_count"],
                 "mttr_hours": s["mttr_hours"], "reopen_rate_percent": s["reopen_rate"],
                 "by_severity": s["severity_breakdown"], "by_status": s["status_breakdown"]},
        "releases": rel,
        "latest_release_readiness": ({"release": lr["name"], **lr["readiness"]} if lr else None),
        "modules": [{"module": m, **d} for m, d in s["modules"].items()],
        "riskiest_files": [{"id": r["id"], "path": r["path"], "risk": r["risk"], "maintainability": r["mi"],
                            "avg_complexity": r["avg_cc"], "issues": r["issues"]}
                           for r in sorted(s["files"], key=lambda r: (-RISK_ORDER[r["risk"]], r["mi"]))[:10]],
    }
