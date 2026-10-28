"""
analysis_service.py
Shared analysis helpers used by app.py, the REST API and the alert engine
(kept out of app.py so app.py does not keep growing).
"""
from collections import Counter

from analyzers.file_analyzer import analyze_file
from analyzers.security_analyzer import RULES as SECURITY_RULES
from metrics.size_metrics import aggregate_size
from metrics.defect_metrics import defect_density
from metrics.maintainability import maintainability_index, project_maintainability
from metrics.quality_metrics import overall_quality_score
from prediction.risk_prediction import evaluate_risk
from models import CodeFile


def run_full_code_analysis(project_id, file_id=None):
    """Aggregate analyze_file() results (requirement 36). file_id=None -> whole project,
    otherwise only that file. Returns the same dict shape for both."""
    q = CodeFile.query.filter_by(project_id=project_id)
    if file_id:
        q = q.filter_by(id=file_id)
    code_files = q.order_by(CodeFile.filename).all()

    file_analyses, complexity_units, function_rows, file_rows, issues = [], [], [], [], []
    structure_totals = {"branches": 0, "loops": 0, "imports": 0, "max_nesting_depth": 0}
    security_findings = []

    for cf in code_files:
        res = analyze_file(cf)
        if res is None:
            continue
        label = cf.relpath or cf.filename
        size_result = res["size_result"]
        file_analyses.append(size_result)
        for f in res["functions"]:
            unit = {"name": f["name"], "line": f["line"], "complexity": f["complexity"],
                    "risk_level": f["risk_level"], "file": label}
            complexity_units.append(unit)
            function_rows.append({"file": label, "name": f["name"], "line": f["line"], "complexity": f["complexity"],
                                  "risk_level": f["risk_level"], "size_lines": f["size_lines"]})
        st = res["structure"]
        for k in ("branches", "loops", "imports"):
            structure_totals[k] += st.get(k, 0)
        structure_totals["max_nesting_depth"] = max(structure_totals["max_nesting_depth"], st.get("max_nesting_depth", 0))
        for sf in res["security_findings"]:
            security_findings.append({**sf, "file": label})
        for it in res["issues"]:
            issues.append({**it, "file": label, "file_id": cf.id})
        total_lines = size_result.get("total_lines", 0)
        mi = res["mi"]
        file_rows.append({"file": label, "file_id": cf.id, "loc": total_lines, "mi_score": mi["mi_score"],
                          "band": mi["band"], "avg_function_loc": mi["avg_function_loc"],
                          "avg_complexity": round(res["avg_complexity"] or 1, 2),
                          "halstead_volume": mi["halstead_volume"]})

    size_summary = aggregate_size(file_analyses)
    avg_complexity = (round(sum(u["complexity"] for u in complexity_units) / len(complexity_units), 2)
                      if complexity_units else 0)
    max_complexity = max((u["complexity"] for u in complexity_units), default=0)
    sec_counts = {"High": 0, "Medium": 0, "Low": 0}
    for f in security_findings:
        sec_counts[f["severity"]] = sec_counts.get(f["severity"], 0) + 1

    return {
        "file_analyses": file_analyses, "size": size_summary, "complexity_units": complexity_units,
        "function_rows": function_rows, "avg_complexity": avg_complexity, "max_complexity": max_complexity,
        "structure": structure_totals, "security_findings": security_findings, "security_counts": sec_counts,
        "file_maintainability": file_rows, "issues": issues, "has_code": bool(file_analyses),
    }


def security_summary(analysis):
    counts = analysis["security_counts"]
    findings = analysis["security_findings"]
    by_type = Counter(f["issue_type"] for f in findings)
    by_sev_types = {"High": Counter(), "Medium": Counter(), "Low": Counter()}
    for f in findings:
        by_sev_types[f["severity"]][f["issue_type"]] += 1

    def note(sev):
        if not by_sev_types[sev]:
            return "No findings at this level."
        return "; ".join(f"{t} x{n}" if n > 1 else t for t, n in by_sev_types[sev].most_common(3))

    level = "High" if counts["High"] else ("Medium" if counts["Medium"] else ("Low" if counts["Low"] else "None"))
    type_sev = {f["issue_type"]: f["severity"] for f in findings}
    return {
        "counts": counts, "files": analysis["size"]["num_files"], "rules": len(SECURITY_RULES),
        "notes": {s: note(s) for s in ("High", "Medium", "Low")},
        "level": level, "total": len(findings),
        "type_labels": list(by_type.keys()), "type_values": list(by_type.values()),
        "type_colors": [{"High": "#dc2626", "Medium": "#d97706", "Low": "#16a34a"}[type_sev[t]] for t in by_type],
    }


def compute_scores(bugs, analysis):
    """Standard bundle of derived metrics: defect density, maintainability, quality, risk."""
    dd = defect_density(bugs, analysis["size"]["total_loc"])
    mi = project_maintainability(analysis["file_maintainability"])
    sc = analysis["security_counts"]
    quality = overall_quality_score(mi["mi_score"], analysis["avg_complexity"], dd,
                                    sc["High"], sc["Medium"], sc["Low"])
    risk = evaluate_risk(analysis["avg_complexity"], dd, len(analysis["security_findings"]), mi["mi_score"])
    return dd, mi, quality, risk
