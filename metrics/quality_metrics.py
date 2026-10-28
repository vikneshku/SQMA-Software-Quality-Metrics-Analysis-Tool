"""
metrics/quality_metrics.py
Quality Metrics / overall Quality Score (feeds Quality Dashboard, Feature 13).

Quality score is a documented weighted composite (project-defined
weights, not a universal industry standard):

    Quality Score =
        0.30 * maintainability_component +
        0.25 * complexity_component +
        0.25 * defect_component +
        0.20 * security_component

Each component is normalized to a 0-100 scale before weighting.
"""


def _complexity_component(avg_complexity: float) -> float:
    # lower complexity -> higher score. 1 -> 100, 30+ -> 0
    score = 100 - (avg_complexity - 1) * (100 / 29)
    return max(0.0, min(100.0, score))


def _defect_component(defect_density: float) -> float:
    # lower density -> higher score. 0 -> 100, 20+ per KLOC -> 0
    score = 100 - defect_density * 5
    return max(0.0, min(100.0, score))


def _security_component(num_high, num_medium, num_low) -> float:
    penalty = num_high * 15 + num_medium * 7 + num_low * 2
    return max(0.0, min(100.0, 100 - penalty))


def overall_quality_score(maintainability_score, avg_complexity, defect_density_value,
                           num_high, num_medium, num_low) -> dict:
    m = maintainability_score
    c = _complexity_component(avg_complexity)
    d = _defect_component(defect_density_value)
    s = _security_component(num_high, num_medium, num_low)

    total = round(0.30 * m + 0.25 * c + 0.25 * d + 0.20 * s, 2)

    if total >= 80:
        level = "Excellent"
    elif total >= 60:
        level = "Good"
    elif total >= 40:
        level = "Needs Improvement"
    else:
        level = "Poor"

    return {
        "quality_score": total,
        "quality_level": level,
        "components": {
            "maintainability": round(m, 2),
            "complexity": round(c, 2),
            "defects": round(d, 2),
            "security": round(s, 2),
        },
    }
