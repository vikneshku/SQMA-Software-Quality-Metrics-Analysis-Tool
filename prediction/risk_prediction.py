"""
prediction/risk_prediction.py
Converts raw measured metrics into boolean evidence and calls the
Bayesian risk model (Feature 8). Thresholds are project-defined and
documented alongside the results in the UI.
"""
from bayesian.risk_model import compute_risk_probability
from config import MI_LOW_THRESHOLD

THRESHOLDS = {
    "complexity": 10,          # avg complexity above this = "high_complexity"
    "defect_density": 3,       # defects per KLOC above this = "has_defect_history"
    "maintainability": MI_LOW_THRESHOLD,   # MI below this (40) = "low_maintainability"
}


def evaluate_risk(avg_complexity: float, defect_density_value: float,
                   num_security_issues: int, maintainability_score: float) -> dict:
    evidence = {
        "high_complexity": avg_complexity > THRESHOLDS["complexity"],
        "has_defect_history": defect_density_value > THRESHOLDS["defect_density"],
        "security_findings": num_security_issues > 0,
        "low_maintainability": maintainability_score < THRESHOLDS["maintainability"],
    }
    result = compute_risk_probability(**evidence)
    result["thresholds_used"] = THRESHOLDS
    return result
