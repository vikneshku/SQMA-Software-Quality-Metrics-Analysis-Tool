"""
ai/context.py
Builds the compact project summary that is sent to the AI as system context before every call,
so answers use real numbers (requirement 16).
"""
import json

from config import AGING_BUG_DAYS
from metrics_summary import project_summary
from models import Alert

SYSTEM_PROMPT = (
    "You are the assistant inside SQMA, a Software Quality and Metrics Analysis tool. Answer using ONLY the project "
    "data below when the question is about this project; quote the real numbers. If the data does not contain the answer, "
    "say so instead of guessing. Be concise, practical and use plain English. Risk levels: Low, Medium, High, Critical. "
    "Maintainability bands: 55+ highly, 40-54.9 moderate, below 40 difficult. Release readiness: Red/Yellow/Green.\n\n"
    "PROJECT DATA (JSON):\n")


def build_project_context(project, s=None):
    s = s or project_summary(project.id)
    a, oc = s["analysis"], s["open_closed"]
    alerts = Alert.query.filter_by(project_id=project.id).order_by(Alert.created_at.desc()).limit(15).all()
    data = {
        "project": project.name,
        "code": {"files": a["size"]["num_files"], "loc": a["size"]["total_loc"], "functions": a["size"]["num_functions"],
                 "avg_complexity": a["avg_complexity"], "max_complexity": a["max_complexity"],
                 "security_findings": a["security_counts"]},
        "quality": {"score": s["quality"]["quality_score"], "level": s["quality"]["quality_level"]},
        "predicted_risk": s["risk"]["predicted_risk"],
        "maintainability": {"score": s["maintainability"]["mi_score"], "band": s["maintainability"]["band"]},
        "bugs": {"total": len(s["bugs"]), "open": oc["open"], "closed": oc["closed"],
                 "by_severity": s["severity_breakdown"], "by_status": s["status_breakdown"],
                 "defect_density_per_kloc": s["defect_density"], "escape_rate_percent": s["escape_rate"],
                 "avg_open_age_days": s["avg_open_age_days"], f"open_older_than_{AGING_BUG_DAYS}_days": s["old_bug_count"]},
        "modules": [{"module": m, **d} for m, d in s["modules"].items()],
        "releases": [{"name": r["name"], "total": r["total"], "open": r["open"], "critical_high": r["critical_high"],
                      "escaped": r["escaped"], "escape_rate": r["escape_rate"], "readiness": r["readiness"]["color"],
                      "reasons": r["readiness"]["reasons"]} for r in s["release_rows"]],
        "top_10_riskiest_files": [{"file": f["path"], "risk": f["risk"], "maintainability": f["mi"],
                                   "avg_complexity": f["avg_cc"], "issues": f["issues"]}
                                  for f in sorted(s["files"], key=lambda r: (-{"Critical": 3, "High": 2, "Medium": 1, "Low": 0}[r["risk"]], r["mi"]))[:10]],
        "active_alerts": [{"level": x.level, "message": x.message} for x in alerts],
    }
    return SYSTEM_PROMPT + json.dumps(data, default=str, separators=(",", ":"))[:24000]
